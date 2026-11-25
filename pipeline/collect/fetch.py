"""Polite HTTP access to public job-board feeds.

The rules, which have no exceptions:

  * one request at a time (the collector is single-threaded), and at least
    MIN_INTERVAL seconds between two requests to the same host;
  * a timeout on every request;
  * a generic User-Agent that names neither the project nor a person;
  * HTTP 403 or 429 means the host refused us: raise Blocked and let the caller
    move on. A block is never retried and never worked around.

A transport failure or a 5xx answer is retried once after a pause. That is the
only retry there is.
"""
from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Callable
from urllib.parse import urljoin, urlsplit

import httpx

USER_AGENT = "job-feed-reader/0.1 (python-httpx)"
MIN_INTERVAL = 1.0
# Hosts that get more room than MIN_INTERVAL. Rippling publishes no limit we can
# read; one third-party write-up cites 100 requests per 10 minutes, so its host
# is asked at most once every 6 seconds.
# JazzHR calls its feed "heavily rate-limited" and gives no figure; it is one
# request per company, so ten seconds apart costs little.
# SmartRecruiters documents 10 requests a second, but its robots.txt admits only
# LinkedIn's crawler, so it gets the same room as Rippling. BambooHR says only
# that requests "can be throttled" if too frequent; its company hosts get 6 s too.
# Breezy and Paylocity publish nothing; their hosts get 2 s. A key starting with "."
# matches every host ending in it.
HOST_INTERVALS = {"api.rippling.com": 6.0, "app.jazz.co": 10.0, "api.smartrecruiters.com": 6.0,
                  ".bamboohr.com": 6.0, ".breezy.hr": 2.0, "recruiting.paylocity.com": 2.0,
                  # LinkedIn job pages, read only where a company's careers page points
                  # to them (PLAN.md decision 12): at least 10 s apart.
                  "www.linkedin.com": 10.0, ".linkedin.com": 10.0,
                  # Workday publishes no limit for its careers sites.
                  ".myworkdayjobs.com": 2.0, ".icims.com": 2.0}
# Companies' own web pages (careers pages, posting pages) are asked at most
# every PAGE_INTERVAL seconds per host.
PAGE_INTERVAL = 3.0
TIMEOUT = 30.0
MAX_PAGE_BYTES = 1_000_000
PAGE_HEADERS = {"Accept": "text/html, application/xhtml+xml;q=0.9, text/plain;q=0.5"}
RETRY_WAIT = 5.0
BLOCK_STATUSES = (403, 429)


class FetchError(Exception):
    """The request failed or the answer could not be used."""


class Blocked(FetchError):
    """The host refused the request (HTTP 403 or 429)."""


class Fetcher:
    """Fetches JSON, spacing requests to each host."""

    def __init__(
        self,
        client: httpx.Client | None = None,
        min_interval: float = MIN_INTERVAL,
        host_intervals: dict[str, float] | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._client = client or httpx.Client(
            timeout=TIMEOUT,
            follow_redirects=False,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        )
        self._min_interval = min_interval
        self._host_intervals = HOST_INTERVALS if host_intervals is None else host_intervals
        self._clock = clock
        self._sleep = sleep
        self._last: dict[str, float] = {}
        self.requests = 0

    def close(self) -> None:
        self._client.close()

    def _interval_for(self, host: str) -> float:
        if host in self._host_intervals:
            return self._host_intervals[host]
        return max((seconds for key, seconds in self._host_intervals.items()
                    if key.startswith(".") and host.endswith(key)), default=0.0)

    def _wait_at_least(self, host: str, seconds: float) -> None:
        last = self._last.get(host)
        if last is not None:
            remaining = seconds - (self._clock() - last)
            if remaining > 0:
                self._sleep(remaining)

    def _wait_for(self, host: str) -> None:
        last = self._last.get(host)
        if last is not None:
            interval = max(self._min_interval, self._interval_for(host))
            remaining = interval - (self._clock() - last)
            if remaining > 0:
                self._sleep(remaining)

    def _get(self, url: str, params: dict | None, headers: dict | None = None, payload=None) -> httpx.Response:
        host = urlsplit(url).netloc.lower()
        self._wait_for(host)
        try:
            if payload is not None:
                return self._client.post(url, params=params, headers=headers, json=payload)
            return self._client.get(url, params=params, headers=headers)
        finally:
            # Counted from the end of the request, so a slow answer still
            # leaves a full interval before the next one.
            self._last[host] = self._clock()
            self.requests += 1

    def get_json(self, url: str, params: dict | None = None) -> Any:
        """GET a URL and return its parsed JSON body."""
        response = self._answer(url, params)
        try:
            return response.json()
        except ValueError as error:
            raise FetchError(f"answer was not JSON ({error})") from error

    def post_json(self, url: str, payload: dict) -> Any:
        """POST a JSON query and return the parsed JSON answer. Only for feeds
        that are read this way (Workday's careers sites search with a POST);
        the request reads, it changes nothing."""
        response = self._answer(url, None, None, payload=payload)
        try:
            return response.json()
        except ValueError as error:
            raise FetchError(f"answer was not JSON ({error})") from error

    def get_text(self, url: str, params: dict | None = None) -> str:
        """GET a URL and return its body as text (an XML feed, a posting page)."""
        return self._answer(url, params, {"Accept": "application/xml, text/xml, text/html;q=0.9, */*;q=0.5"}).text

    def get_page(self, url: str, stay_within: Callable[[str], bool], max_redirects: int = 2,
                 max_bytes: int = MAX_PAGE_BYTES) -> tuple[str, str]:
        """GET a web page on a company's own site; return (final address, text).

        Redirects are followed only while `stay_within(address)` holds (the
        company's own domain), at most `max_redirects` times. Each hop is a
        request under the same spacing and block rules. A page is cut at
        `max_bytes`."""
        for hop in range(max_redirects + 1):
            self._wait_at_least(urlsplit(url).netloc.lower(), PAGE_INTERVAL)
            response = self._answer(url, None, PAGE_HEADERS, redirects=True)
            if 300 <= response.status_code < 400:
                target = urljoin(url, response.headers.get("location", ""))
                if hop == max_redirects or not target.startswith("https://") or not stay_within(target):
                    raise FetchError(f"HTTP {response.status_code}: redirected to {target[:120]} (left the site or too many redirects)")
                url = target
                continue
            return url, response.text[:max_bytes]
        raise FetchError("too many redirects")

    def _answer(self, url: str, params: dict | None, headers: dict | None = None,
                redirects: bool = False, payload=None) -> httpx.Response:
        """One GET with the rules applied: a block raises, one retry on 5xx or a
        transport failure, and anything but 200 is an error (a redirect is
        returned when `redirects` is true)."""
        response = None
        for attempt in (1, 2):
            try:
                response = self._get(url, params, headers, payload)
            except httpx.TimeoutException as error:
                failure = f"timed out after {TIMEOUT:g}s ({type(error).__name__})"
            except httpx.HTTPError as error:
                failure = f"request failed ({type(error).__name__}: {error})"
            else:
                if response.status_code in BLOCK_STATUSES:
                    raise Blocked(f"HTTP {response.status_code} from {urlsplit(url).netloc}")
                if response.status_code < 500:
                    break
                failure = f"HTTP {response.status_code}"
            if attempt == 2:
                raise FetchError(failure)
            self._sleep(RETRY_WAIT)

        if response.status_code == 404:
            raise FetchError("HTTP 404: no board at this address (wrong or retired board token)")
        if 300 <= response.status_code < 400 and redirects:
            return response
        if 300 <= response.status_code < 400:
            # Redirects are not followed. Some systems send a retired board to
            # their own home page instead of answering 404.
            target = response.headers.get("location", "")[:120]
            raise FetchError(f"HTTP {response.status_code}: redirected to {target or 'an unstated address'} "
                             "(board moved or not available)")
        if response.status_code != 200:
            raise FetchError(f"HTTP {response.status_code}")
        return response


def record_name(url: str) -> str:
    """File name for a saved answer: host and path, made safe for a file system."""
    parts = urlsplit(url)
    # A query written into the address (a paging offset) is part of the name;
    # parameters passed separately are not, so older recordings still replay.
    key = parts.netloc + parts.path + (f"_{parts.query}" if parts.query else "")
    safe = "".join(ch if ch.isalnum() or ch in "-." else "_" for ch in key)
    return safe.strip("_") + ".json"


class RecordingFetcher(Fetcher):
    """A Fetcher that also saves every answer under a directory.

    The saved files are raw feed answers for building test fixtures and for
    re-running the collector offline with ReplayFetcher. The directory used by
    the command line, data/fixtures-live/, is ignored by git.
    """

    def __init__(self, directory, **kwargs) -> None:
        super().__init__(**kwargs)
        self._directory = directory
        directory.mkdir(parents=True, exist_ok=True)

    def get_json(self, url: str, params: dict | None = None) -> Any:
        data = super().get_json(url, params)
        with open(self._directory / record_name(url), "w", encoding="utf-8", newline="\n") as handle:
            json.dump(data, handle, ensure_ascii=False)
        return data

    def post_json(self, url: str, payload: dict) -> Any:
        data = super().post_json(url, payload)
        with open(self._directory / post_record_name(url, payload), "w", encoding="utf-8", newline="\n") as handle:
            json.dump(data, handle, ensure_ascii=False)
        return data

    def get_page(self, url: str, stay_within, max_redirects: int = 2, max_bytes: int = MAX_PAGE_BYTES):
        final, text = super().get_page(url, stay_within, max_redirects, max_bytes)
        with open(self._directory / page_record_name(url), "w", encoding="utf-8", newline="\n") as handle:
            json.dump({"url": url, "final_url": final, "text": text}, handle, ensure_ascii=False)
        return final, text

    def get_text(self, url: str, params: dict | None = None) -> str:
        text = super().get_text(url, params)
        with open(self._directory / text_record_name(url), "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
        return text


def post_record_name(url: str, payload) -> str:
    digest = hashlib.sha1(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:10]
    return record_name(url)[: -len(".json")] + f"_post_{digest}.json"


def page_record_name(url: str) -> str:
    return record_name(url)[: -len(".json")] + ".page.json"


def text_record_name(url: str) -> str:
    return record_name(url)[: -len(".json")] + ".txt"


class ReplayFetcher:
    """Answers from files saved by RecordingFetcher. Makes no network request."""

    def __init__(self, directory) -> None:
        self._directory = directory
        self.requests = 0

    def close(self) -> None:
        pass

    def get_json(self, url: str, params: dict | None = None) -> Any:
        path = self._directory / record_name(url)
        if not path.exists():
            raise FetchError(f"no saved answer for {url}")
        self.requests += 1
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)

    def get_text(self, url: str, params: dict | None = None) -> str:
        path = self._directory / text_record_name(url)
        if not path.exists():
            raise FetchError(f"no saved answer for {url}")
        self.requests += 1
        with open(path, encoding="utf-8", newline="") as handle:
            return handle.read()

    def get_page(self, url: str, stay_within=None, max_redirects: int = 2, max_bytes: int = MAX_PAGE_BYTES):
        path = self._directory / page_record_name(url)
        if not path.exists():
            raise FetchError(f"no saved answer for {url}")
        self.requests += 1
        with open(path, encoding="utf-8") as handle:
            saved = json.load(handle)
        return saved["final_url"], saved["text"]

    def post_json(self, url: str, payload: dict) -> Any:
        path = self._directory / post_record_name(url, payload)
        if not path.exists():
            raise FetchError(f"no saved answer for POST {url}")
        self.requests += 1
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
