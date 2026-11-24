"""Readers added after the first four: Workable, BambooHR, and those that follow.

Fixtures are real answers recorded on 2026-11-24, trimmed.
"""
from __future__ import annotations

import httpx
import pytest
from collect_helpers import FakeFetcher, company

from pipeline.collect import bamboohr, run as run_module, workable
from pipeline.collect.fetch import Blocked, FetchError, Fetcher
from pipeline.collect.run import collect, skip_reason
from pipeline.collect.state import SeenState


def by_title(drafts):
    return {draft["title"]: draft for draft in drafts}


# ----------------------------------------------------------------- Workable

def test_workable_asks_the_widget_feed_once_with_descriptions():
    fetcher = FakeFetcher()
    workable.read("anthro", fetcher)
    assert fetcher.calls == [("https://apply.workable.com/api/v1/widget/accounts/anthro", {"details": "true"})]


def test_workable_fields():
    drafts = by_title(workable.read("anthro", FakeFetcher()))
    engineer = drafts["Associate Manufacturing Engineer - Cell"]
    assert engineer["posting_id"] == "1318B10262"
    assert engineer["url"] == "https://apply.workable.com/j/1318B10262"
    assert engineer["locations"] == [{"text": "Alameda, California, United States", "city": "Alameda", "state": "CA", "country": "US"}]
    assert engineer["employment"] == "full-time"
    assert engineer["workplace"] is None          # telecommuting false says only "not remote"
    assert engineer["posted_date"] == "2026-11-10"
    assert engineer["pay"] is None
    assert engineer["description_text"]
    # An empty employment type falls back to the title.
    assert drafts["Electrolyte Research Intern"]["employment"] == "intern"
    assert drafts["Head of People"]["employment"] == "unknown"


@pytest.mark.parametrize("job,expected", [
    ({"telecommuting": True}, "remote"),
    ({"telecommuting": False, "workplace_type": "hybrid"}, "hybrid"),
    ({"telecommuting": False, "workplace_type": "on_site"}, "onsite"),
    ({"telecommuting": False}, None),
])
def test_workable_workplace(job, expected):
    assert workable._workplace(job) == expected


def test_workable_hidden_locations_are_left_out_and_top_level_fields_fill_in():
    job = {"locations": [{"city": "Austin", "region": "Texas", "country": "United States", "hidden": True}],
           "city": "Denver", "state": "Colorado", "country": "United States"}
    assert workable._locations(job) == [{"text": "Denver, Colorado, United States", "city": "Denver", "state": "CO", "country": "US"}]
    assert workable._locations({"locations": []}) == []


def test_workable_ids_are_stable():
    fetcher = FakeFetcher()
    raw = collect([company("anthro-energy", "workable", "anthro")], fetcher, SeenState(), now=lambda: "2026-11-24T16:00:00Z")
    ids = {job["id"] for job in raw["jobs"]}
    assert "workable:anthro:1318B10262" in ids and len(ids) == 4
    assert all(job["source"]["ats"] == "workable" and job["source"]["board"] == "anthro" for job in raw["jobs"])


# ----------------------------------------------------------------- BambooHR

def test_bamboohr_is_switched_off_by_default():
    assert "bamboohr" not in run_module.READERS and "bamboohr" in run_module.SWITCHED_OFF
    reason = skip_reason(company("lunar-outpost", "bamboohr", "lunaroutpost"))
    assert reason == "bamboohr: reader switched off pending a terms decision (--enable-reader bamboohr)"


def test_bamboohr_asks_the_list_then_each_posting():
    fetcher = FakeFetcher()
    bamboohr.read("lunaroutpost", fetcher)
    assert [url for url, _ in fetcher.calls] == [
        "https://lunaroutpost.bamboohr.com/careers/list",
        "https://lunaroutpost.bamboohr.com/careers/297/detail",
        "https://lunaroutpost.bamboohr.com/careers/389/detail",
    ]


def test_bamboohr_fields_and_the_fallback_when_a_detail_fails():
    drafts = by_title(bamboohr.read("lunaroutpost", FakeFetcher()))
    engineer = drafts["R&D Engineer"]
    assert engineer["posting_id"] == "297"
    assert engineer["url"] == "https://lunaroutpost.bamboohr.com/careers/297"
    assert engineer["locations"] == [{"text": "Golden, Colorado, United States", "city": "Golden", "state": "CO", "country": "US"}]
    assert engineer["employment"] == "full-time"
    assert engineer["posted_date"] == "2026-01-29"
    assert engineer["department"] == "Business Development"
    assert engineer["pay"] is None                       # free text without a period
    assert engineer["description_text"].endswith("Compensation: $90,000 to $115,000")
    # No detail was recorded for the intern posting: it is kept from the list.
    intern = drafts["Project Management Intern - Summer 2027"]
    assert intern["employment"] == "intern" and intern["description_text"] == ""
    assert intern["locations"][0]["city"] == "Golden"


def test_bamboohr_a_refused_detail_blocks_the_company():
    fetcher = FakeFetcher(failures={"https://lunaroutpost.bamboohr.com/careers/297/detail": Blocked("HTTP 429 from x")})
    with pytest.raises(Blocked):
        bamboohr.read("lunaroutpost", fetcher)


def test_bamboohr_runs_when_switched_on():
    readers = {**run_module.READERS, "bamboohr": run_module.SWITCHED_OFF["bamboohr"]}
    raw = collect([company("lunar-outpost", "bamboohr", "lunaroutpost")], FakeFetcher(), SeenState(),
                  readers=readers, now=lambda: "2026-11-24T16:00:00Z")
    assert sorted(job["id"] for job in raw["jobs"]) == ["bamboohr:lunaroutpost:297", "bamboohr:lunaroutpost:389"]


def test_a_redirect_is_reported_as_a_board_that_is_not_available():
    # A company that left BambooHR is sent to the vendor's home page.
    def handler(request):
        return httpx.Response(302, headers={"location": "https://www.bamboohr.com/"})
    fetcher = Fetcher(client=httpx.Client(transport=httpx.MockTransport(handler)), sleep=lambda _: None)
    with pytest.raises(FetchError, match=r"HTTP 302: redirected to https://www.bamboohr.com/ \(board moved or not available\)"):
        fetcher.get_json("https://ambri.bamboohr.com/careers/list")
    assert fetcher.requests == 1
