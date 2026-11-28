"""UKG UltiPro and ADP Workforce Now readers, and the weekly schedule they run on (decision 24).

Fixtures are real answers recorded on 2026-11-27, trimmed: a few postings
per list, descriptions shortened.
"""
from __future__ import annotations

import copy
import json
from datetime import datetime, timezone

import pytest
from collect_helpers import FIXTURES, company

from pipeline.collect import adp, careers, normalize, ukg, weekly
from pipeline.collect.fetch import Blocked, FetchError
from pipeline.collect.run import board_problem, collect
from pipeline.collect.state import SeenState

UKG_BOARD = "recruiting.ultipro.com/POW1009POWS/JobBoard/42398959-f1c7-48da-a3e2-94e525e29808"
UKG_FIRST = "2fe5cd14-70b1-41de-b3d6-85659692c726"
SENS = "4b01b1ef-1960-4219-8f3f-6c0652a81377"


def fixture(name: str):
    text = (FIXTURES / name).read_text(encoding="utf-8")
    return json.loads(text) if name.endswith(".json") else text


class Fake:
    """Answers by address; records each request. Anything else is a 404."""

    def __init__(self, posts=None, json_answers=None, pages=None, failures=None) -> None:
        self.posts, self.json, self.pages = posts or {}, json_answers or {}, pages or {}
        self.failures = failures or {}
        self.asked: list[tuple] = []

    @property
    def requests(self) -> int:
        return len(self.asked)

    def _fail(self, url):
        if url in self.failures:
            raise self.failures[url]

    def post_json(self, url, payload):
        self.asked.append(("POST", url, payload["opportunitySearch"]["Skip"]))
        self._fail(url)
        answers = self.posts.get(url) or []
        skip = payload["opportunitySearch"]["Skip"] // ukg.PAGE_SIZE
        if skip < len(answers):
            return answers[skip]
        return {"opportunities": [], "totalCount": 0}

    def get_json(self, url, params=None):
        key = (url, (params or {}).get("$skip"))
        self.asked.append(("GET", url, (params or {}).get("$skip")))
        self._fail(url)
        if key in self.json:
            return copy.deepcopy(self.json[key])
        if (url, None) in self.json:
            return copy.deepcopy(self.json[(url, None)])
        raise FetchError("HTTP 404: no board at this address")

    def get_page(self, url, stay_within, max_redirects=2, max_bytes=1_000_000):
        self.asked.append(("PAGE", url, None))
        assert stay_within(url)
        self._fail(url)
        if url in self.pages:
            return url, self.pages[url]
        raise FetchError("HTTP 404: no page")

    def close(self):
        pass


# ------------------------------------------------------------------- UKG

def ukg_site(**changes) -> Fake:
    detail = f"https://{UKG_BOARD}/OpportunityDetail?opportunityId={UKG_FIRST}"
    return Fake(posts={f"https://{UKG_BOARD}/JobBoardView/LoadSearchResults": [fixture("ukg_powersecure_list.json")]},
                pages={detail: fixture(f"ukg_powersecure_{UKG_FIRST}.html"), **changes})


def test_ukg_reads_the_list_then_each_posting_page():
    site = ukg_site()
    drafts = {draft["posting_id"]: draft for draft in ukg.read(UKG_BOARD, site)}
    assert site.asked[0] == ("POST", f"https://{UKG_BOARD}/JobBoardView/LoadSearchResults", 0)
    assert len(drafts) == 3 and len(site.asked) == 4                     # one list page, three posting pages
    manager = drafts[UKG_FIRST]
    assert manager["title"] == "Construction Manager (EPC Construction)"
    assert manager["url"] == f"https://{UKG_BOARD}/OpportunityDetail?opportunityId={UKG_FIRST}"
    assert manager["locations"][1] == {"text": "Killeen, TX", "city": "Killeen", "state": "TX", "country": "US"}
    assert manager["posted_date"] == "2026-11-24" and manager["employment"] == "full-time"
    assert manager["department"] == "Engineering, Procurement & Construction"
    assert manager["description_text"].startswith("Summary")
    assert manager["pay"] is None                                       # the board shows none
    # A posting page that failed: kept from the list with its short description.
    other = drafts["9855674e-fde9-447e-95e9-eeea03ae5b41"]
    assert other["title"].startswith("Team Leader") and other["description_text"]


def test_ukg_pay_only_when_the_posting_shows_it():
    hidden = {"PayRangeVisible": False, "Salaried": True, "CompensationAnnualMinimum": "86000.00",
              "CompensationAnnualMaximum": "133300.00", "CompensationCurrencyCode": "USD",
              "PayRange": {"PayRangeMinimum": None, "PayRangeMaximum": None}}
    assert ukg.published_pay(hidden) is None                            # Yaskawa's: figures sent but not shown
    shown = dict(hidden, PayRangeVisible=True, PayRange={"PayRangeMinimum": "86000.00", "PayRangeMaximum": "133300.00"})
    assert ukg.published_pay(shown) == normalize.pay(86000, 133300, "USD", "year")


def test_ukg_pages_through_the_list():
    first = fixture("ukg_powersecure_list.json")
    full = dict(first, totalCount=53, opportunities=[dict(item, Id=f"id-{n}") for n, item in
                                                    enumerate(first["opportunities"] * 17 + first["opportunities"][:1])][:50])
    rest = dict(first, totalCount=53, opportunities=[dict(item, Id=f"more-{n}") for n, item in enumerate(first["opportunities"])])
    site = Fake(posts={f"https://{UKG_BOARD}/JobBoardView/LoadSearchResults": [full, rest]})
    drafts = ukg.read(UKG_BOARD, site)
    assert [entry[2] for entry in site.asked if entry[0] == "POST"] == [0, 50]
    assert len(drafts) == 53


def test_ukg_board_shape():
    assert board_problem(company("powersecure", "ukg", UKG_BOARD)) is None
    assert board_problem(company("tae", "ukg", "recruiting2.ultipro.com/TRI1021TRIAE/JobBoard/49386e5d-f909-4648-8335-415ce97e3f15")) is None
    assert "not in the form" in board_problem(company("x", "ukg", f"https://{UKG_BOARD}"))


# ------------------------------------------------------------------- ADP

def adp_site(**json_answers) -> Fake:
    answers = {(adp.API, "0"): fixture("adp_sens_list.json"),
               (f"{adp.API}/9201310521902_492", None): fixture("adp_sens_9201310521902_492.json")}
    answers.update(json_answers)
    return Fake(json_answers=answers)


def test_adp_reads_the_public_list_then_each_posting():
    site = adp_site()
    drafts = {draft["posting_id"]: draft for draft in adp.read(SENS, site)}
    assert site.asked[0] == ("GET", adp.API, "0")
    assert all(url.startswith(adp.API) for _kind, url, _skip in site.asked)  # never robots.txt or a sign-in page
    assert len(drafts) == 4
    manager = drafts["9201310521902_492"]
    assert manager["title"] == "Senior Manager, Manufacturing Engineering"
    assert manager["url"] == (f"{adp.CAREER_CENTER}?cid={SENS}&ccId=19000101_000001&source=CC2&lang=en_US"
                              "&selectedMenuKey=CurrentOpenings&jobId=569894")
    assert manager["locations"] == [{"text": "Longmont, CO, US", "city": "Longmont", "state": "CO", "country": "US"}]
    assert manager["pay"] == normalize.pay(120000, 175000, "USD", "year")
    assert manager["employment"] == "full-time" and manager["posted_date"] == "2026-11-20"
    assert manager["description_text"]
    # A detail that failed keeps the posting from the list, pay included.
    assert drafts["9201313978919_633"]["pay"] == normalize.pay(105000, 155000, "USD", "year")
    assert drafts["9201313978919_633"]["description_text"] == ""


def test_adp_board_forms():
    assert adp.ids(SENS) == (SENS, "19000101_000001")
    url = f"https://workforcenow.adp.com/mascsr/default/mdf/recruitment/recruitment.html?cid={SENS}&ccId=9200&lang=en_US"
    assert adp.ids(url) == (SENS, "9200")
    assert board_problem(company("sens", "adp", url)) is None
    assert board_problem(company("sens", "adp", SENS)) is None
    assert "not in the form" in board_problem(company("sens", "adp", "sens"))


@pytest.mark.parametrize("error", [
    FetchError("HTTP 302: redirected to https://online.adp.com/signin/v1/ (board moved or not available)"),
    FetchError("HTTP 401"),
])
def test_adp_stops_at_a_sign_in(error):
    site = adp_site()
    site.failures = {adp.API: error}
    with pytest.raises(Blocked, match="sign-in"):
        adp.read(SENS, site)
    assert len(site.asked) == 1


def test_adp_places():
    assert adp.place({"nameCode": {"shortName": "Remote - CO"}}) == {"text": "Remote - CO", "state": "CO", "country": "US"}
    assert adp.place({"nameCode": {"shortName": " Hatfield, Hatfield, PA, US"}})["country"] == "US"


# ---------------------------------------------------------------- weekly

def test_weekly_reads_once_then_carries_the_postings():
    context = careers.Context(now=datetime(2026, 11, 27, 8, tzinfo=timezone.utc))
    site = adp_site()
    read = weekly.reader("adp", adp.read, context)
    first = read(SENS, site)
    assert first.status == "ok" and len(first.drafts) == 4 and "7-day schedule" in first.note
    asked = len(site.asked)
    context.now = datetime(2026, 12, 2, 8, tzinfo=timezone.utc)          # five days later
    again = read(SENS, site)
    assert len(site.asked) == asked                                      # nothing asked
    assert len(again.drafts) == 4 and again.seen_at == "2026-11-27T08:00:00Z"
    assert "not read this run, 4 postings carried from 2026-11-27" in again.note
    context.now = datetime(2026, 12, 4, 9, tzinfo=timezone.utc)          # seven days later: read again
    read(SENS, site)
    assert len(site.asked) > asked


def test_weekly_does_not_remember_a_failure():
    context = careers.Context(now=datetime(2026, 11, 27, 8, tzinfo=timezone.utc))
    site = adp_site()
    site.failures = {adp.API: FetchError("HTTP 500")}
    with pytest.raises(FetchError):
        weekly.reader("adp", adp.read, context)(SENS, site)
    assert context.sites == {}


def test_collect_uses_the_weekly_reader_for_ukg_and_adp(tmp_path, monkeypatch):
    import yaml

    from pipeline.collect import run as run_module
    registry = tmp_path / "companies.yml"
    registry.write_text(yaml.safe_dump({"registry_version": 0, "companies": [company("sens", "adp", SENS)]}), encoding="utf-8")
    monkeypatch.setattr(run_module, "Fetcher", lambda **kwargs: adp_site())
    state = tmp_path / "careers.json"
    out = tmp_path / "raw.json"
    assert run_module.main(["--companies", str(registry), "--out", str(out), "--careers-state", str(state),
                            "--state", str(tmp_path / "seen.json"), "--runs", str(tmp_path / "runs.json")]) == 0
    saved = json.loads(state.read_text(encoding="utf-8"))["sites"]
    assert list(saved) == [f"adp:{SENS}"] and len(saved[f"adp:{SENS}"]["drafts"]) == 4
    raw = json.loads(out.read_text(encoding="utf-8"))
    assert "decision 24" in raw["run"]["companies"][0]["error"]


def test_ukg_and_adp_ids_are_stable():
    raw = collect([company("sens", "adp", SENS)], adp_site(), SeenState(), now=lambda: "2026-11-27T16:00:00Z")
    assert f"adp:{SENS}:9201310521902_492" in {job["id"] for job in raw["jobs"]}
