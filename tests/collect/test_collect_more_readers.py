"""Readers added after the first four: Workable, BambooHR, and those that follow.

Fixtures are real answers recorded on 2026-11-24, trimmed.
"""
from __future__ import annotations

import httpx
import pytest
from collect_helpers import FakeFetcher, company

from pipeline.collect import bamboohr, jazzhr, recruitee, run as run_module, smartrecruiters, workable
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


# ---------------------------------------------------------- SmartRecruiters

SR_LIST = "https://api.smartrecruiters.com/v1/companies/EnPowerInc/postings"


def test_smartrecruiters_is_switched_off_by_default():
    assert "smartrecruiters" not in run_module.READERS and "smartrecruiters" in run_module.SWITCHED_OFF


def test_smartrecruiters_asks_one_page_then_each_posting():
    fetcher = FakeFetcher()
    smartrecruiters.read("EnPowerInc", fetcher)
    urls = [url for url, _ in fetcher.calls]
    assert urls[0] == f"{SR_LIST}?limit=100&offset=0"
    assert urls[1:] == [f"{SR_LIST}/{posting}" for posting in
                        ("744000163336380", "744000158306981", "744000158308679", "744000153041479")]


def test_smartrecruiters_pages_until_total_found():
    page = lambda ids, total: {"offset": 0, "limit": 100, "totalFound": total,
                               "content": [{"id": str(i), "name": f"Role {i}"} for i in ids]}
    fetcher = FakeFetcher(extra={
        "https://api.smartrecruiters.com/v1/companies/Big/postings?limit=100&offset=0": page(range(100), 150),
        "https://api.smartrecruiters.com/v1/companies/Big/postings?limit=100&offset=100": page(range(100, 150), 150),
    })
    drafts = smartrecruiters.read("Big", fetcher)
    assert len(drafts) == 150
    assert sum("postings?limit" in url for url, _ in fetcher.calls) == 2


def test_smartrecruiters_fields():
    drafts = {draft["posting_id"]: draft for draft in smartrecruiters.read("EnPowerInc", FakeFetcher())}
    engineer = drafts["744000163336380"]
    assert engineer["title"] == "Manufacturing Engineer"
    assert engineer["url"] == "https://jobs.smartrecruiters.com/EnPowerInc/744000163336380-manufacturing-engineer"
    assert engineer["locations"] == [{"text": "Indianapolis, IN, United States", "city": "Indianapolis", "state": "IN", "country": "US"}]
    assert engineer["workplace"] == "onsite" and engineer["employment"] == "full-time"
    assert engineer["posted_date"] == "2026-11-23"
    assert engineer["description_text"].startswith("Responsible for leading process development")
    # The feed gives a maximum and no minimum: not a range the contract can hold.
    assert engineer["pay"] is None
    # No detail recorded: kept from the list, with an address built from the id.
    technician = drafts["744000158306981"]
    assert technician["url"] == "https://jobs.smartrecruiters.com/EnPowerInc/744000158306981"
    assert technician["description_text"] == ""


@pytest.mark.parametrize("compensation,expected", [
    ({"min": 80000, "max": 100000, "currency": "USD", "period": "YEARLY"}, (80000, 100000, "year")),
    ({"min": 25, "max": 32, "currency": "USD", "period": "HOURLY"}, (25, 32, "hour")),
    ({"min": 5000, "max": 6000, "currency": "USD", "period": "MONTHLY"}, None),
    ({"max": 87550, "currency": "USD", "period": "YEARLY"}, None),
])
def test_smartrecruiters_pay(compensation, expected):
    found = smartrecruiters._pay(compensation)
    assert (found and (found["min"], found["max"], found["period"])) == expected or (found is None and expected is None)


@pytest.mark.parametrize("place,expected", [
    ({"remote": True, "hybrid": False}, "remote"),
    ({"remote": False, "hybrid": True}, "hybrid"),
    ({"remote": False, "hybrid": False}, "onsite"),
    ({}, None),
])
def test_smartrecruiters_workplace(place, expected):
    assert smartrecruiters._workplace(place) == expected


# ---------------------------------------------------------------- Recruitee

def test_recruitee_asks_once_per_board():
    fetcher = FakeFetcher()
    recruitee.read("fastned", fetcher)
    assert fetcher.calls == [("https://fastned.recruitee.com/api/offers/", None)]


def test_recruitee_fields():
    drafts = {draft["posting_id"]: draft for draft in recruitee.read("fastned", FakeFetcher())}
    remote = drafts["2794271"]
    assert remote["workplace"] == "remote" and remote["employment"] == "full-time"
    assert remote["locations"] == [{"text": "Hamburg, Hamburg, Germany", "city": "Hamburg", "country": "DE"}]
    assert remote["url"] == "https://fastned.recruitee.com/o/elektriker-elektroniker-im-aussendienst-nord-mwd"
    assert remote["posted_date"] == "2026-10-22"
    assert remote["description_text"]
    assert drafts["2818749"]["workplace"] == "onsite"
    student = drafts["2835151"]
    assert student["workplace"] == "hybrid" and student["employment"] == "contract"


def test_recruitee_pay_and_a_custom_domain():
    drafts = {draft["title"]: draft for draft in recruitee.read("greenerpowersolutions", FakeFetcher())}
    specialist = drafts["Procurement Specialist"]
    # The feed writes the figures as strings.
    assert specialist["pay"] == {"min": 40000, "max": 67000, "currency": "EUR", "period": "year", "basis": "feed"}
    assert specialist["url"] == "https://careers.greenerpowersolutions.com/o/procurement-specialist"
    # A monthly stipend is not a period the contract holds.
    assert drafts["Marketing Internship"]["pay"] is None and drafts["Marketing Internship"]["employment"] == "intern"


@pytest.mark.parametrize("code,expected", [
    ("fulltime_permanent", "full-time"), ("fulltime", "full-time"), ("fulltime_fixed_term", "contract"),
    ("parttime_permanent", "part-time"), ("internship", "intern"), ("traineeship", "intern"),
    ("temporary", "contract"), ("freelance", "contract"), (None, "unknown"),
])
def test_recruitee_employment_codes(code, expected):
    assert recruitee._employment(code, "Engineer") == expected


def test_recruitee_ids_are_stable():
    raw = collect([company("fastned", "recruitee", "fastned")], FakeFetcher(), SeenState(), now=lambda: "2026-11-24T16:00:00Z")
    assert sorted(job["id"] for job in raw["jobs"]) == ["recruitee:fastned:2794271", "recruitee:fastned:2818749",
                                                         "recruitee:fastned:2835151"]


# ------------------------------------------------------------------- JazzHR

def test_jazzhr_asks_the_feed_once():
    fetcher = FakeFetcher()
    jazzhr.read("coreshelltech", fetcher)
    assert fetcher.calls == [("https://app.jazz.co/feeds/export/jobs/coreshelltech", None)]


def test_jazzhr_fields():
    drafts = jazzhr.read("coreshelltech", FakeFetcher())
    assert len(drafts) == 3
    first = drafts[0]
    assert first["title"] == "Human Resources Generalist"
    assert first["posting_id"] == "H2WUH8feDa"
    assert first["url"].startswith("https://coreshelltech.applytojob.com/apply/H2WUH8feDa/")
    assert first["locations"] == [{"text": "San Leandro, CA, United States", "city": "San Leandro", "state": "CA", "country": "US"}]
    assert first["employment"] == "full-time" and first["department"] == "Human Resources"
    assert first["posted_date"] is None and first["pay"] is None and first["workplace"] is None
    assert first["description_text"]


def test_jazzhr_ids_come_from_the_posting_address():
    assert jazzhr.posting_code("https://coreshelltech.applytojob.com/apply/U9Oe7DLe6N/Battery-Technician") == "U9Oe7DLe6N"
    assert jazzhr.posting_code("https://example.com/careers/1") is None
    raw = collect([company("coreshell", "jazzhr", "coreshelltech")], FakeFetcher(), SeenState(), now=lambda: "2026-11-24T16:00:00Z")
    assert "jazzhr:coreshelltech:H2WUH8feDa" in {job["id"] for job in raw["jobs"]}


def test_jazzhr_closed_jobs_are_left_out_and_bad_answers_are_errors():
    feed = ("<jobs><job><id>job_1</id><status>Closed</status><title>Old</title>"
            "<url>https://a.applytojob.com/apply/X1/Old</url></job>"
            "<job><id>job_2</id><status>Open</status><title>New</title>"
            "<url>https://a.applytojob.com/apply/X2/New</url><type>Internship</type></job></jobs>")
    drafts = jazzhr.read("a", FakeFetcher(extra={"https://app.jazz.co/feeds/export/jobs/a": feed}))
    assert [(draft["posting_id"], draft["employment"]) for draft in drafts] == [("X2", "intern")]
    with pytest.raises(FetchError, match="not XML"):
        jazzhr.parse("<html><body>Not found")
    with pytest.raises(FetchError, match="not a JazzHR job feed"):
        jazzhr.parse("<html><body>Not found</body></html>")
    with pytest.raises(FetchError, match="document type"):
        jazzhr.parse('<!DOCTYPE jobs [<!ENTITY a "aaaa">]><jobs>&a;</jobs>')


def test_the_jazzhr_host_is_spaced_out():
    from pipeline.collect.fetch import HOST_INTERVALS
    assert HOST_INTERVALS["app.jazz.co"] >= 10
