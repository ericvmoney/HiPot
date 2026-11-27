"""Readers added after the first four: Workable, BambooHR, and those that follow.

Fixtures are real answers recorded on 2026-11-24, trimmed.
"""
from __future__ import annotations

import httpx
import pytest
from collect_helpers import FakeFetcher, company

from pipeline.collect import bamboohr, breezy, gem, jazzhr, paylocity, recruitee, run as run_module, smartrecruiters, teamtailor, workable
from pipeline.collect.fetch import Blocked, FetchError, Fetcher
from pipeline.collect.run import collect, skip_reason
from pipeline.collect.state import SeenState
from pipeline.collect.text import job_posting_description


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

@pytest.mark.parametrize("ats", ["rippling", "bamboohr", "smartrecruiters", "breezy"])
def test_readers_with_restricted_terms_run_by_default_and_can_be_turned_off(ats):
    # The owner's standing rule (PLAN.md decision 6): they run, and each can be
    # turned off for a run if a vendor or company objects.
    assert ats in run_module.READERS
    entry = company("a", ats, "a")
    assert skip_reason(entry) is None
    readers = {name: read for name, read in run_module.READERS.items() if name != ats}
    assert skip_reason(entry, readers, {ats}) == f"{ats}: reader turned off for this run (--disable-reader {ats})"


def test_disable_reader_on_the_command_line(tmp_path, monkeypatch):
    import yaml
    registry = tmp_path / "companies.yml"
    registry.write_text(yaml.safe_dump({"registry_version": 0, "companies": [company("lunar-outpost", "bamboohr", "lunaroutpost")]}),
                        encoding="utf-8")
    monkeypatch.setattr(run_module, "Fetcher", FakeFetcher)
    out = tmp_path / "raw.json"
    assert run_module.main(["--companies", str(registry), "--out", str(out), "--state", str(tmp_path / "s.json"),
                            "--disable-reader", "bamboohr"]) == 0
    from pipeline.io import load_json
    raw = load_json(out)
    assert raw["jobs"] == []
    assert raw["run"]["companies"][0]["error"] == "bamboohr: reader turned off for this run (--disable-reader bamboohr)"


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


def test_bamboohr_ids_are_stable():
    raw = collect([company("lunar-outpost", "bamboohr", "lunaroutpost")], FakeFetcher(), SeenState(),
                  now=lambda: "2026-11-24T16:00:00Z")
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


def test_smartrecruiters_a_remote_place_with_on_site_flags():
    # Seen live at Mission Critical Group: city "Remote", both flags false.
    place = {"city": "Remote", "region": "", "country": "us", "remote": False, "hybrid": False,
             "fullLocation": "Remote, , United States"}
    assert smartrecruiters._workplace(place) is None
    assert smartrecruiters._location(place) == [{"text": "Remote, United States", "country": "US"}]


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


def test_hosts_that_get_more_room():
    fetcher = Fetcher(client=httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200))))
    assert fetcher._interval_for("app.jazz.co") >= 10
    assert fetcher._interval_for("api.smartrecruiters.com") >= 6     # robots.txt admits only LinkedInBot
    assert fetcher._interval_for("lunaroutpost.bamboohr.com") >= 6   # matched by suffix
    assert fetcher._interval_for("zeno-power.breezy.hr") >= 2
    assert fetcher._interval_for("bamboohr.com.example.net") == 0.0
    assert fetcher._interval_for("api.lever.co") == 0.0              # MIN_INTERVAL still applies


# ------------------------------------------------------------------- Breezy

ZENO_CONTRACT = "https://zeno-power.breezy.hr/p/783342e25463-electrical-engineer-contractor"
# The contractor's posting page is a real page recorded on 2026-11-24
# (fixtures/breezy_zeno-power_783342e25463.html); the other pages answer 404.


def test_breezy_asks_the_list_then_each_posting_page():
    fetcher = FakeFetcher()
    breezy.read("zeno-power", fetcher)
    urls = [url for url, _ in fetcher.calls]
    assert urls[0] == "https://zeno-power.breezy.hr/json"
    assert urls[1] == ZENO_CONTRACT and len(urls) == 5


def test_breezy_fields():
    drafts = {d["posting_id"]: d for d in breezy.read("zeno-power", FakeFetcher())}
    contractor = drafts["783342e25463"]
    assert contractor["title"] == "Electrical Engineer (Contractor)" and contractor["url"] == ZENO_CONTRACT
    assert contractor["locations"] == [{"text": "Seattle, WA", "city": "Seattle", "state": "WA", "country": "US"}]
    assert contractor["workplace"] == "hybrid" and contractor["employment"] == "contract"
    assert contractor["pay"] == {"min": 55, "max": 75, "currency": "USD", "period": "hour", "basis": "feed"}
    assert contractor["posted_date"]
    assert contractor["description_text"].startswith("Company Overview\nZeno Power is the leading developer of nuclear batteries")
    assert len(contractor["description_text"]) > 3000
    operator = drafts["9a5f4f91f333"]
    assert operator["pay"]["min"] == 46 and operator["pay"]["max"] == 60 and operator["workplace"] is None
    # No page answered for these: kept from the list without a description.
    assert drafts["c81dbf07b00e"]["description_text"] == "" and drafts["c81dbf07b00e"]["pay"] is None
    assert drafts["583f0039dfe1"]["locations"][0]["state"] == "DC"


@pytest.mark.parametrize("text,country,expected", [
    ("$120,000 – $180,000 / year", "US", (120000, 180000, "USD", "year")),
    ("$45.67 – $60.10 / hour", "US", (46, 60, "USD", "hour")),
    ("€50,000 - €60,000 / year", "DE", (50000, 60000, "EUR", "year")),
    ("$120,000 – $180,000 / year", "CA", None),         # a dollar sign outside the US is not assumed
    ("$120,000 – $180,000", "US", None),                # no period
    ("$5,000 – $6,000 / month", "US", None),
    ("Competitive", "US", None),
    ("", "US", None),
])
def test_breezy_salary_text(text, country, expected):
    found = breezy.pay_from_text(text, country)
    assert (None if found is None else (found["min"], found["max"], found["currency"], found["period"])) == expected


def test_breezy_a_whole_place_typed_into_the_city_field():
    # XL Batteries writes "Marlborough, MA" as the city, with no state field.
    place = {"country": {"name": "United States", "id": "US"}, "city": "Marlborough, MA", "is_remote": False,
             "name": "Marlborough, MA, US"}
    assert breezy._place(place) == {"text": "Marlborough, MA, US", "city": "Marlborough", "state": "MA", "country": "US"}


def test_breezy_page_without_a_job_block_gives_no_description():
    assert job_posting_description("<html><script type='application/ld+json'>{\"@type\": \"Organization\"}</script></html>") == ""
    assert job_posting_description("<html><script type='application/ld+json'>{not json</script></html>") == ""


def test_breezy_a_refused_page_blocks_the_company():
    with pytest.raises(Blocked):
        breezy.read("zeno-power", FakeFetcher(failures={ZENO_CONTRACT: Blocked("HTTP 429 from zeno-power.breezy.hr")}))


# --------------------------------------------------------------- Teamtailor

AIRA = "https://career.airahome.com/jobs.rss?per_page=100&offset=0"


def test_teamtailor_board_is_a_subdomain_or_a_whole_host():
    assert teamtailor.feed_url("acme", 0) == "https://acme.teamtailor.com/jobs.rss?per_page=100&offset=0"
    assert teamtailor.feed_url("career.airahome.com", 100) == "https://career.airahome.com/jobs.rss?per_page=100&offset=100"


def test_teamtailor_fields():
    fetcher = FakeFetcher()
    drafts = {d["posting_id"]: d for d in teamtailor.read("career.airahome.com", fetcher)}
    assert fetcher.calls == [(AIRA, None)]               # a short page is the last
    installer = drafts["8790006"]
    assert installer["title"] == "Heat Pump Installer"
    assert installer["url"] == "https://career.airahome.com/jobs/8790006-heat-pump-installer"
    assert installer["locations"] == [{"text": "Bury St Edmunds, United Kingdom", "city": "Bury St Edmunds", "country": "GB"}]
    assert installer["workplace"] == "remote"            # remoteStatus "fully", as the company set it
    assert installer["posted_date"] == "2026-11-24" and installer["department"] == "Service Operations"
    assert installer["description_text"] and installer["pay"] is None
    assert drafts["8784267"]["workplace"] == "hybrid"
    assert drafts["8490762"]["workplace"] == "onsite" and drafts["8293908"]["workplace"] == "onsite"
    assert [l["city"] for l in drafts["8782208"]["locations"]] == ["Manchester", "Sheffield"]


def test_teamtailor_pages_until_a_short_page():
    item = lambda n: (f"<item><title>Role {n}</title><link>https://acme.teamtailor.com/jobs/{n}-role</link>"
                      f"<guid>g{n}</guid><pubDate>Tue, 24 Nov 2026 15:12:35 +0000</pubDate></item>")
    feed = lambda numbers: f'<rss version="2.0"><channel>{"".join(item(n) for n in numbers)}</channel></rss>'
    fetcher = FakeFetcher(extra={teamtailor.feed_url("acme", 0): feed(range(100)),
                                 teamtailor.feed_url("acme", 100): feed(range(99, 130))})
    drafts = teamtailor.read("acme", fetcher)
    assert len(fetcher.calls) == 2
    assert len(drafts) == 130                            # the posting on both pages is kept once


def test_teamtailor_ids_and_a_bad_answer():
    raw = collect([company("aira", "teamtailor", "career.airahome.com")], FakeFetcher(), SeenState(), now=lambda: "2026-11-24T16:00:00Z")
    assert "teamtailor:career.airahome.com:8790006" in {job["id"] for job in raw["jobs"]}
    with pytest.raises(FetchError, match="not an RSS feed"):
        teamtailor.parse("<html><body>Sign in</body></html>")


# ---------------------------------------------------------------------- Gem

def test_gem_asks_once_per_board():
    fetcher = FakeFetcher()
    gem.read("butcher-power-products", fetcher)
    assert fetcher.calls == [("https://api.gem.com/job_board/v0/butcher-power-products/job_posts/", None)]


def test_gem_fields_and_the_state_from_an_office_address():
    drafts = {d["title"]: d for d in gem.read("butcher-power-products", FakeFetcher())}
    inspector = drafts["Quality Control Inspector (Fabrication & Assembly)"]
    assert inspector["posting_id"] == "am9icG9zdDrAinBn0igPiiY7k5M-csUZ"
    assert inspector["url"] == "https://jobs.gem.com/butcher-power-products/am9icG9zdDrAinBn0igPiiY7k5M-csUZ"
    # "Rancho Cordova, United States"; the office is "11261 Trade Center Drive Rancho Cordova, CA 95742".
    assert inspector["locations"] == [{"text": "Rancho Cordova, United States", "city": "Rancho Cordova", "state": "CA", "country": "US"}]
    assert inspector["workplace"] == "onsite" and inspector["employment"] == "full-time"
    assert inspector["posted_date"] == "2026-06-10" and inspector["department"] == "Quality Control"
    assert inspector["description_text"] and inspector["pay"] is None
    # "410 West Rd, Houston Texas 77038": a state name without a comma.
    assert drafts["Project Director, Houston"]["locations"][0]["state"] == "TX"
    remote = drafts["Electrical Engineering Manager"]
    assert remote["workplace"] == "remote" and remote["locations"] == [{"text": "United States - Remote", "country": "US"}]


def test_gem_a_city_with_no_matching_office_keeps_no_state():
    drafts = gem.read("piqenergy", FakeFetcher())
    places = sorted(d["locations"][0]["text"] for d in drafts)
    assert places == ["Athens, Greece", "San Francisco, United States"]
    athens = next(d for d in drafts if d["locations"][0]["text"] == "Athens, Greece")
    assert athens["locations"][0] == {"text": "Athens, Greece", "city": "Athens", "country": "GR"}
    assert athens["workplace"] == "hybrid"


def test_gem_ids_are_stable():
    raw = collect([company("butcher-power", "gem", "butcher-power-products")], FakeFetcher(), SeenState(),
                  now=lambda: "2026-11-24T16:00:00Z")
    assert "gem:butcher-power-products:am9icG9zdDrAinBn0igPiiY7k5M-csUZ" in {job["id"] for job in raw["jobs"]}
    assert {tuple(job["metros"]) for job in raw["jobs"]} == {("sacramento-ca",), ("houston-tx",), ()}


# ---------------------------------------------------------------- Paylocity

PTT = "3c0c9b43-2c62-43f8-b766-5f9fe7284368"


def test_paylocity_asks_the_board_then_each_posting_page():
    fetcher = FakeFetcher()
    drafts = paylocity.read(PTT, fetcher)
    urls = [url for url, _ in fetcher.calls]
    assert urls[0] == f"https://recruiting.paylocity.com/recruiting/jobs/All/{PTT}"
    assert urls[1] == "https://recruiting.paylocity.com/Recruiting/Jobs/Details/4692187"
    assert len(urls) == 1 + len(drafts) == 20


def test_paylocity_fields():
    drafts = {d["posting_id"]: d for d in paylocity.read(PTT, FakeFetcher())}
    supervisor = drafts["4692187"]
    assert supervisor["title"] == "Production Supervisor"
    assert supervisor["url"] == "https://recruiting.paylocity.com/Recruiting/Jobs/Details/4692187"
    assert supervisor["locations"] == [{"text": "Canonsburg, PA", "city": "Canonsburg", "state": "PA", "country": "US"}]
    assert supervisor["posted_date"] == "2026-11-24" and supervisor["workplace"] is None
    # The full description from the posting page's schema.org block.
    assert supervisor["description_text"].startswith("Description\nThe Production Supervisor leads and develops")
    assert len(supervisor["description_text"]) > 1000
    # No posting page recorded: the board's short description is kept.
    assistant = drafts["4692030"]
    assert 0 < len(assistant["description_text"]) < 200
    assert drafts["2696450"]["workplace"] == "remote"
    assert drafts["4656379"]["department"] == "Human Resources"
    assert drafts["3923835"]["locations"][0]["city"] == "Raeford"


def test_paylocity_board_page_problems_are_errors():
    with pytest.raises(FetchError, match="no window.pageData"):
        paylocity.page_data("<html>Sign in</html>")
    with pytest.raises(FetchError, match="not JSON"):
        paylocity.page_data("<script>window.pageData = {broken</script>")
    with pytest.raises(FetchError, match="no job list"):
        paylocity.page_data('<script>window.pageData = {"Jobs": null};</script>')
    page = '<script>window.pageData = {"Jobs": [{"JobId": 1, "JobTitle": "Internal", "IsInternal": true}]};</script>'
    assert paylocity.read("x", FakeFetcher(extra={"https://recruiting.paylocity.com/recruiting/jobs/All/x": page})) == []


def test_paylocity_ids_are_stable():
    raw = collect([company("pa-transformer", "paylocity", PTT)], FakeFetcher(), SeenState(), now=lambda: "2026-11-24T16:00:00Z")
    assert f"paylocity:{PTT}:4692187" in {job["id"] for job in raw["jobs"]}


# ------------------------------------------------------------------ Workday

from pipeline.collect import workday  # noqa: E402

SOLV = "solvenergy.wd1/SOLV_External_Career"
SOLV_SEARCH = "https://solvenergy.wd1.myworkdayjobs.com/wday/cxs/solvenergy/SOLV_External_Career/jobs"


def test_workday_board_format():
    assert workday.addresses(SOLV) == (
        SOLV_SEARCH,
        "https://solvenergy.wd1.myworkdayjobs.com/wday/cxs/solvenergy/SOLV_External_Career",
        "https://solvenergy.wd1.myworkdayjobs.com/SOLV_External_Career")
    with pytest.raises(FetchError, match="must be"):
        workday.addresses("solvenergy")


def test_workday_searches_with_a_post_then_asks_each_posting():
    fetcher = FakeFetcher()
    drafts = workday.read(SOLV, fetcher)
    assert fetcher.calls[0] == (SOLV_SEARCH, {"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": ""})
    assert len(fetcher.calls) == 1 + len(drafts) == 4


def test_workday_fields():
    drafts = {d["posting_id"]: d for d in workday.read(SOLV, FakeFetcher())}
    assert len(drafts) == 3
    onsite = next(d for d in drafts.values() if d["title"].startswith("Energy Storage Project Manager"))
    assert onsite["posting_id"].startswith("J") and onsite["url"].startswith("https://solvenergy.wd1.myworkdayjobs.com/SOLV_External_Career/job/")
    assert onsite["workplace"] == "onsite" and onsite["employment"] == "full-time"
    assert onsite["locations"][0]["text"] == "Lost Hills, CA" and onsite["locations"][0]["state"] == "CA"
    assert onsite["posted_date"] and onsite["description_text"]
    remote = next(d for d in drafts.values() if "(Remote)" in d["title"])
    assert remote["workplace"] == "remote"
    hybrid = next(d for d in drafts.values() if d["title"] == "Senior Brand Coordinator")
    assert hybrid["workplace"] == "hybrid"


def test_workday_pages_and_keeps_the_first_total():
    page = lambda numbers, total: {"total": total, "jobPostings": [
        {"title": f"Role {n}", "externalPath": f"/job/Austin-TX/Role-{n}_R{n}", "locationsText": "Austin, TX"} for n in numbers]}
    search = "https://acme.wd5.myworkdayjobs.com/wday/cxs/acme/Careers/jobs"
    # Later pages answer total 0, as Workday's do.
    fetcher = FakeFetcher(extra={(search, 0): page(range(20), 25), (search, 20): page(range(20, 25), 0)})
    drafts = workday.read("acme.wd5/Careers", fetcher)
    assert len(drafts) == 25 and sum(1 for url, _ in fetcher.calls if url == search) == 2
    # The posting answers were 404s: kept from the list, the id from the address.
    assert drafts[0]["posting_id"] == "R0" and drafts[0]["locations"][0]["city"] == "Austin"


def test_workday_ids_are_stable():
    raw = collect([company("solv-energy", "workday", SOLV)], FakeFetcher(), SeenState(), now=lambda: "2026-11-25T16:00:00Z")
    assert all(job["id"].startswith("workday:solvenergy.wd1-SOLV_External_Career:J") for job in raw["jobs"])


# Two companies reading two sites of one Workday tenant (Canadian Solar's
# 'CanadianSolar' and 'eStorage' sites share 67 requisitions).

def workday_site(tenant: str, wd: str, site: str, requisitions: list[str]) -> dict:
    search = f"https://{tenant}.{wd}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs"
    page = {"total": len(requisitions), "jobPostings": [
        {"title": f"Role {r}", "externalPath": f"/job/US---Remote/Role-{r}_{r}", "locationsText": "US - Remote"}
        for r in requisitions]}
    return {(search, 0): page}


def test_a_requisition_on_two_sites_stays_with_the_narrower_site():
    sites = {**workday_site("canadiansolar", "wd5", "CanadianSolar", ["10000001", "10000002", "10000003", "10000858"]),
             **workday_site("canadiansolar", "wd5", "eStorage", ["10000858", "10000900"])}
    parent = company("canadian-solar", "workday", "canadiansolar.wd5/CanadianSolar")
    storage = company("canadian-solar-e-storage", "workday", "canadiansolar.wd5/eStorage")
    raw = collect([parent, storage], FakeFetcher(extra=sites), SeenState(), now=lambda: "2026-11-27T16:00:00Z")
    owners = {job["source"]["posting_id"]: job["company_id"] for job in raw["jobs"]}
    assert owners["10000858"] == "canadian-solar-e-storage"          # 2 postings on eStorage, 4 on CanadianSolar
    assert sorted(job["source"]["posting_id"] for job in raw["jobs"]) == ["10000001", "10000002", "10000003", "10000858", "10000900"]
    entries = {entry["company_id"]: entry for entry in raw["run"]["companies"]}
    assert entries["canadian-solar"]["postings"] == 3 and entries["canadian-solar"]["status"] == "ok"
    assert entries["canadian-solar"]["error"] == ("1 postings left under canadian-solar-e-storage, which reads a "
                                                  "narrower site on the same Workday tenant")
    assert entries["canadian-solar-e-storage"]["postings"] == 2 and entries["canadian-solar-e-storage"]["error"] is None


def test_a_tie_goes_to_the_company_first_in_the_registry():
    sites = {**workday_site("acme", "wd1", "SiteA", ["R1", "R2"]), **workday_site("acme", "wd1", "SiteB", ["R2", "R3"])}
    first = company("acme-b", "workday", "acme.wd1/SiteB")
    second = company("acme-a", "workday", "acme.wd1/SiteA")
    raw = collect([first, second], FakeFetcher(extra=sites), SeenState(), now=lambda: "2026-11-27T16:00:00Z")
    owners = {job["source"]["posting_id"]: job["company_id"] for job in raw["jobs"]}
    assert owners["R2"] == "acme-b"                                   # both sites list 2: registry order decides
    flipped = collect([second, first], FakeFetcher(extra=sites), SeenState(), now=lambda: "2026-11-27T16:00:00Z")
    assert {job["source"]["posting_id"]: job["company_id"] for job in flipped["jobs"]}["R2"] == "acme-a"


def test_other_tenants_and_one_company_are_left_alone():
    sites = {**workday_site("acme", "wd1", "Careers", ["R1"]), **workday_site("other", "wd5", "Careers", ["R1"])}
    raw = collect([company("acme", "workday", "acme.wd1/Careers"), company("other", "workday", "other.wd5/Careers")],
                  FakeFetcher(extra=sites), SeenState(), now=lambda: "2026-11-27T16:00:00Z")
    assert len(raw["jobs"]) == 2                                      # the same number on two tenants is two postings


# -------------------------------------------------------------------- iCIMS

from pipeline.collect import icims  # noqa: E402
from collect_helpers import FIXTURES  # noqa: E402
from test_collect_probe import FakeSite  # noqa: E402

JOBY = "https://careers-jobyaviation.icims.com"


def joby_site():
    page0 = (FIXTURES / "icims_joby_search_0.html").read_text(encoding="utf-8")
    return FakeSite({
        f"{JOBY}/jobs/search?ss=1&in_iframe=1&pr=0": page0,
        f"{JOBY}/jobs/search?ss=1&in_iframe=1&pr=1": page0,      # nothing new: the list ends
        f"{JOBY}/jobs/5248/aircraft-integration-assembly-technician/job?in_iframe=1":
            (FIXTURES / "icims_joby_5248.html").read_text(encoding="utf-8"),
    })


def test_icims_board_and_places():
    assert icims.host_for("jobyaviation") == "careers-jobyaviation.icims.com"
    assert icims.host_for("jobs.example.icims.com") == "jobs.example.icims.com"
    assert icims.place("US-CA-San Carlos") == {"text": "US-CA-San Carlos", "city": "San Carlos", "state": "CA", "country": "US"}
    assert icims.place("US-Remote")["country"] == "US"


def test_icims_cards_from_a_real_search_page():
    cards = icims.cards((FIXTURES / "icims_joby_search_0.html").read_text(encoding="utf-8"))
    assert len(cards) == 20
    assert cards[0] == {"id": "5248", "url": f"{JOBY}/jobs/5248/aircraft-integration-assembly-technician/job",
                        "title": "Aircraft Integration Assembly Technician", "location": "US-CA-Marina",
                        "category": "Manufacturing & Production"}


def test_icims_reads_the_search_then_each_posting():
    site = joby_site()
    drafts = {d["posting_id"]: d for d in icims.read("jobyaviation", site)}
    assert site.asked[:2] == [f"{JOBY}/jobs/search?ss=1&in_iframe=1&pr=0", f"{JOBY}/jobs/search?ss=1&in_iframe=1&pr=1"]
    assert len(drafts) == 20
    technician = drafts["5248"]
    assert technician["url"] == f"{JOBY}/jobs/5248/aircraft-integration-assembly-technician/job"
    assert technician["title"] == "Aircraft Integration Assembly Technician"
    assert technician["locations"][0]["city"] == "Marina" and technician["locations"][0]["state"] == "CA"
    assert technician["posted_date"] and technician["description_text"].startswith("Company Overview")
    assert technician["department"] == "Manufacturing & Production"
    # A posting page that failed: kept from its card.
    other = drafts["5894"]
    assert other["title"] == "Aircraft Maintenance Instructor (Contract)" and other["employment"] == "contract"
    assert other["description_text"] == ""


def test_icims_ids_are_stable():
    raw = collect([company("joby-aviation", "icims", "jobyaviation")], joby_site(), SeenState(), now=lambda: "2026-11-25T16:00:00Z")
    assert "icims:jobyaviation:5248" in {job["id"] for job in raw["jobs"]}


# ------------------------------------------- detail requests that time out

from pipeline.collect import normalize  # noqa: E402

TIMED_OUT = FetchError("timed out (ReadTimeout: no complete answer within 120s)")


def test_details_stop_after_three_timeouts_in_a_row():
    details = normalize.Details()
    calls = []

    def fails(error):
        def call():
            calls.append(error)
            raise error
        return call
    assert details.ask(fails(TIMED_OUT), default="none") == "none"
    assert details.ask(fails(TIMED_OUT)) is None
    assert details.ask(lambda: "answer") == "answer"                 # a success resets the streak
    assert details.ask(fails(FetchError("HTTP 404"))) is None        # not a timeout: resets it too
    for _ in range(3):
        details.ask(fails(TIMED_OUT))
    assert details.stopped and len(calls) == 6
    assert details.ask(lambda: pytest.fail("no request once stopped"), default={}) == {}
    result = details.result([{"title": "kept"}])
    assert result.status == "partial" and result.drafts == [{"title": "kept"}]
    assert result.note == "stopped after 3 timeouts in a row; 1 postings kept from the board's list without their details"
    assert normalize.Details().result(["a"]) == ["a"]                # no stop: the plain list


def test_a_refusal_still_ends_the_company():
    with pytest.raises(Blocked):
        normalize.Details().ask(lambda: (_ for _ in ()).throw(Blocked("HTTP 429 from x")))


def test_a_workday_board_whose_details_time_out_is_partial():
    search = "https://acme.wd1.myworkdayjobs.com/wday/cxs/acme/Careers/jobs"
    page = {"total": 5, "jobPostings": [
        {"title": f"Role {n}", "externalPath": f"/job/Austin-TX/Role-{n}_R{n}", "locationsText": "Austin, TX"} for n in range(5)]}
    api = "https://acme.wd1.myworkdayjobs.com/wday/cxs/acme/Careers"
    fetcher = FakeFetcher(extra={(search, 0): page}, failures={f"{api}/job/Austin-TX/Role-{n}_R{n}": TIMED_OUT for n in range(5)})
    raw = collect([company("acme", "workday", "acme.wd1/Careers")], fetcher, SeenState(), now=lambda: "2026-11-27T16:00:00Z")
    assert len(raw["jobs"]) == 5                                     # every posting kept from the list
    assert sum(1 for url, _ in fetcher.calls if "/job/" in url) == 3   # no detail asked after the third timeout
    entry = raw["run"]["companies"][0]
    assert entry["status"] == "partial" and entry["postings"] == 5
    assert entry["error"].startswith("stopped after 3 timeouts in a row; 2 postings kept")


def test_an_icims_portal_whose_posting_pages_time_out_is_partial():
    site = joby_site()
    cards = icims.cards((FIXTURES / "icims_joby_search_0.html").read_text(encoding="utf-8"))
    site.failures = {f"{card['url']}?in_iframe=1": TIMED_OUT for card in cards[:3]}
    result = icims.read("jobyaviation", site)
    assert result.status == "partial" and len(result.drafts) == 20     # all 20 cards kept
    assert result.note.startswith("stopped after 3 timeouts in a row; 17 postings kept")
    assert sum(1 for url in site.asked if "/job?" in url) == 3
