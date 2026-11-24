"""The polite-fetching rules, checked against a fake transport and a fake clock."""
from __future__ import annotations

import httpx
import pytest

from pipeline.collect import fetch
from pipeline.collect.fetch import Blocked, FetchError, Fetcher, RecordingFetcher, ReplayFetcher
from pipeline.collect.text import clip, escaped_html_to_text, html_to_text, join_text


class Clock:
    """Time that moves only when someone sleeps, or when a request takes time."""

    def __init__(self) -> None:
        self.now = 1000.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def make(handler, clock: Clock | None = None) -> tuple[Fetcher, Clock, list[httpx.Request]]:
    clock = clock or Clock()
    seen: list[httpx.Request] = []

    def wrapped(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    client = httpx.Client(
        transport=httpx.MockTransport(wrapped), timeout=fetch.TIMEOUT,
        headers={"User-Agent": fetch.USER_AGENT, "Accept": "application/json"},
    )
    return Fetcher(client=client, clock=clock, sleep=clock.sleep), clock, seen


def ok(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"jobs": []})


def test_at_least_one_second_between_requests_to_the_same_host():
    fetcher, clock, _ = make(ok)
    fetcher.get_json("https://api.example.com/a")
    fetcher.get_json("https://api.example.com/b")
    fetcher.get_json("https://api.example.com/c")
    assert clock.sleeps == [1.0, 1.0]


def test_no_wait_when_enough_time_has_already_passed_or_the_host_differs():
    fetcher, clock, _ = make(ok)
    fetcher.get_json("https://api.example.com/a")
    fetcher.get_json("https://other.example.org/a")     # a different host
    clock.now += 0.4
    fetcher.get_json("https://api.example.com/b")       # 0.4 s gone, so 0.6 s to wait
    clock.now += 5
    fetcher.get_json("https://api.example.com/c")       # long enough already
    assert clock.sleeps == [pytest.approx(0.6)]


def test_the_interval_is_measured_from_the_end_of_the_previous_request():
    clock = Clock()

    def slow(request):
        clock.now += 3.0                                # the answer took three seconds
        return httpx.Response(200, json={})

    fetcher, _, _ = make(slow, clock)
    fetcher.get_json("https://api.example.com/a")
    fetcher.get_json("https://api.example.com/b")
    assert clock.sleeps == [1.0]


def test_the_client_name_is_generic():
    fetcher, _, seen = make(ok)
    fetcher.get_json("https://api.example.com/a", {"content": "true"})
    agent = seen[0].headers["user-agent"].lower()
    assert agent == fetch.USER_AGENT.lower()
    for word in ("hipot", "@", "http:", "https:"):
        assert word not in agent
    assert str(seen[0].url) == "https://api.example.com/a?content=true"


def test_the_real_client_has_a_timeout_and_does_not_follow_redirects():
    fetcher = Fetcher()
    try:
        assert fetcher._client.timeout == httpx.Timeout(fetch.TIMEOUT)
        assert fetcher._client.follow_redirects is False
        assert fetcher._client.headers["user-agent"] == fetch.USER_AGENT
    finally:
        fetcher.close()


@pytest.mark.parametrize("status", [403, 429])
def test_a_refusal_is_reported_as_blocked_and_never_retried(status):
    fetcher, clock, seen = make(lambda request: httpx.Response(status, text="no"))
    with pytest.raises(Blocked, match=str(status)):
        fetcher.get_json("https://api.example.com/a")
    assert len(seen) == 1 and clock.sleeps == []


def test_a_missing_board_is_an_error_not_a_block():
    fetcher, _, seen = make(lambda request: httpx.Response(404, json={"status": 404}))
    with pytest.raises(FetchError, match="404") as caught:
        fetcher.get_json("https://api.example.com/a")
    assert not isinstance(caught.value, Blocked) and len(seen) == 1


def test_a_server_error_is_retried_once_after_a_pause():
    answers = iter([httpx.Response(503), httpx.Response(200, json={"jobs": [1]})])
    fetcher, clock, seen = make(lambda request: next(answers))
    assert fetcher.get_json("https://api.example.com/a") == {"jobs": [1]}
    assert len(seen) == 2 and clock.sleeps == [fetch.RETRY_WAIT]


def test_two_server_errors_give_up():
    fetcher, _, seen = make(lambda request: httpx.Response(500))
    with pytest.raises(FetchError, match="HTTP 500"):
        fetcher.get_json("https://api.example.com/a")
    assert len(seen) == 2


def test_a_timeout_is_an_error():
    def timeout(request):
        raise httpx.ReadTimeout("slow", request=request)

    fetcher, _, seen = make(timeout)
    with pytest.raises(FetchError, match="timed out"):
        fetcher.get_json("https://api.example.com/a")
    assert len(seen) == 2


def test_a_redirect_or_a_non_json_answer_is_an_error():
    fetcher, _, _ = make(lambda request: httpx.Response(302, headers={"location": "https://elsewhere.example"}))
    with pytest.raises(FetchError, match="HTTP 302"):
        fetcher.get_json("https://api.example.com/a")
    fetcher, _, _ = make(lambda request: httpx.Response(200, text="<html>Sign in</html>"))
    with pytest.raises(FetchError, match="not JSON"):
        fetcher.get_json("https://api.example.com/a")


def test_record_then_replay(tmp_path):
    clock = Clock()
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"jobs": ["é"]})))
    recorder = RecordingFetcher(tmp_path / "live", client=client, clock=clock, sleep=clock.sleep)
    url = "https://api.example.com/v1/boards/acme/jobs"
    assert recorder.get_json(url, {"content": "true"}) == {"jobs": ["é"]}
    assert [path.name for path in (tmp_path / "live").iterdir()] == ["api.example.com_v1_boards_acme_jobs.json"]
    replay = ReplayFetcher(tmp_path / "live")
    assert replay.get_json(url, {"content": "true"}) == {"jobs": ["é"]}
    with pytest.raises(FetchError, match="no saved answer"):
        replay.get_json("https://api.example.com/v1/boards/other/jobs")


def test_text_answers_follow_the_same_rules_and_record_and_replay(tmp_path):
    seen = []

    def handler(request):
        seen.append(request.headers["accept"])
        if request.url.path == "/refused":
            return httpx.Response(429)
        return httpx.Response(200, text="<jobs><job>Ä</job></jobs>\r\n")
    clock = Clock()
    client = httpx.Client(transport=httpx.MockTransport(handler))
    recorder = RecordingFetcher(tmp_path / "live", client=client, clock=clock, sleep=clock.sleep)
    url = "https://feeds.example.com/export/jobs/acme"
    assert recorder.get_text(url) == "<jobs><job>Ä</job></jobs>\r\n"
    assert "xml" in seen[0]
    with pytest.raises(Blocked):
        recorder.get_text("https://feeds.example.com/refused")
    assert [path.name for path in (tmp_path / "live").iterdir()] == ["feeds.example.com_export_jobs_acme.txt"]
    assert ReplayFetcher(tmp_path / "live").get_text(url) == "<jobs><job>Ä</job></jobs>\r\n"


# ---------------------------------------------------------------------- text

def test_html_to_text():
    markup = '<div class="intro"><p>Own the <strong>plant&nbsp;controller</strong>.</p><ul><li>C &amp; C++</li><li>HIL</li></ul></div><script>x()</script>'
    assert html_to_text(markup) == "Own the plant controller.\nC & C++\nHIL"
    assert html_to_text(None) == "" and html_to_text("") == ""


def test_escaped_html_as_greenhouse_sends_it():
    markup = "&lt;p&gt;Salary range: $160,000 &amp;amp; up&lt;/p&gt;&lt;p&gt;Second   paragraph&lt;/p&gt;"
    assert escaped_html_to_text(markup) == "Salary range: $160,000 & up\nSecond paragraph"


def test_clip_and_join():
    assert len(clip("x" * 30000)) == 20000
    assert clip("short") == "short"
    assert join_text("A  b", None, "", "c\n\n\nd") == "A b\nc\nd"


def test_record_names_keep_a_query_written_into_the_address():
    from pipeline.collect.fetch import record_name
    assert record_name("https://api.lever.co/v0/postings/lightship") == "api.lever.co_v0_postings_lightship.json"
    first = record_name("https://api.example.com/v1/companies/X/postings?offset=0")
    second = record_name("https://api.example.com/v1/companies/X/postings?offset=100")
    assert first != second and first.endswith("offset_0.json")
