"""Each reader against a trimmed real answer from its feed."""
from __future__ import annotations

import copy

from collect_helpers import ADDRESSES, FIXTURES, FakeFetcher

from pipeline.collect import ashby, greenhouse, lever, normalize
from pipeline.collect.fetch import Blocked
from pipeline.io import load_json


def by_title(drafts: list[dict]) -> dict[str, dict]:
    return {made["title"].strip(): made for made in drafts}


def check_shape(drafts: list[dict]) -> None:
    for made in drafts:
        assert tuple(made) == normalize.DRAFT_KEYS
        assert made["posting_id"] and made["title"].strip()
        assert made["url"].startswith("https://")
        assert made["description_text"] and "<" not in made["description_text"][:200]
        assert "&lt;" not in made["description_text"] and "&amp;" not in made["description_text"]
        assert all(location["text"] for location in made["locations"])
        assert made["employment"] in ("full-time", "part-time", "contract", "intern", "unknown")
        assert made["workplace"] in (None, "onsite", "hybrid", "remote")


# ---------------------------------------------------------------- Greenhouse

def test_greenhouse_asks_for_content_on_the_documented_address(fetcher):
    greenhouse.read("antora", fetcher)
    assert fetcher.calls == [("https://boards-api.greenhouse.io/v1/boards/antora/jobs", {"content": "true"})]


def test_greenhouse_fields(fetcher):
    drafts = greenhouse.read("antora", fetcher)
    check_shape(drafts)
    assert len(drafts) == 4
    counsel = by_title(drafts)["Associate General Counsel, Commercial"]
    assert counsel["posting_id"] == "6151698004"
    assert counsel["url"] == "https://job-boards.greenhouse.io/antora/jobs/6151698004"
    assert counsel["locations"] == [{"text": "San Jose, CA", "city": "San Jose", "state": "CA", "country": "US"}]
    assert counsel["posted_date"] == "2026-10-28"
    assert counsel["department"] == "Business Operations"
    assert counsel["pay"] is None                      # the list answer carries no pay
    assert counsel["workplace"] is None                # Greenhouse has no workplace field
    assert counsel["description_text"].startswith("Antora Energy delivers affordable, reliable energy")
    assert "\n" in counsel["description_text"]         # paragraphs stay on their own lines


def test_greenhouse_location_shapes(fetcher):
    drafts = by_title(greenhouse.read("antora", fetcher))
    assert drafts["Director of Grid Policy"]["locations"] == [{"text": "Remote, USA", "country": "US"}]
    assert drafts["HR & Site Administrator"]["locations"][0]["state"] == "KS"
    assert drafts["Materials R&D Lab Technician"]["locations"][0]["text"] == "San Jose, CA"   # trailing space in the feed
    redwood = by_title(greenhouse.read("redwoodmaterials", fetcher))
    assert [l["text"] for l in redwood["Principal Engineer, Extractive Metallurgy"]["locations"]] == [
        "Carson City, NV", "San Francisco, California, United States"]


def test_greenhouse_employment_from_an_exposed_custom_field(fetcher):
    drafts = by_title(greenhouse.read("pacificfusion", fetcher))
    assert drafts["Summer 2027 Controls Electrical Engineer Internship"]["employment"] == "intern"
    assert drafts["CAD Administrator"]["employment"] == "full-time"
    # No custom field on this board, and the title says nothing.
    assert by_title(greenhouse.read("antora", fetcher))["Director of Grid Policy"]["employment"] == "unknown"


def test_greenhouse_workplace_from_an_exposed_custom_field():
    answer = load_json(FIXTURES / "greenhouse_antora.json")
    answer["jobs"][0]["metadata"] = [{"id": 1, "name": "Workplace Type", "value": "Hybrid", "value_type": "single_select"}]
    answer["jobs"][1]["metadata"] = [{"id": 2, "name": "Travel Requirement", "value": "Remote sites, 20%", "value_type": "short_text"}]
    drafts = greenhouse.read("antora", FakeFetcher(extra={"https://boards-api.greenhouse.io/v1/boards/antora/jobs": answer}))
    assert drafts[0]["workplace"] == "hybrid"
    assert drafts[1]["workplace"] is None              # an unrelated field that mentions 'remote' is not read


def test_greenhouse_falls_back_to_the_hosted_address_when_the_feed_gives_http():
    answer = load_json(FIXTURES / "greenhouse_antora.json")
    answer["jobs"][0]["absolute_url"] = "http://careers.example.com/open-roles?gh_jid=6151698004"
    drafts = greenhouse.read("antora", FakeFetcher(extra={"https://boards-api.greenhouse.io/v1/boards/antora/jobs": answer}))
    assert drafts[0]["url"] == "https://job-boards.greenhouse.io/antora/jobs/6151698004"


def test_greenhouse_pay_ranges_need_a_stated_period():
    # The shape documented for the single-posting endpoint with pay_transparency=true.
    yearly = [{"min_cents": 5000000, "max_cents": 7500000, "currency_type": "USD", "title": "NYC Annual Salary Range", "blurb": "..."}]
    assert greenhouse.pay_from_ranges(yearly) == {"min": 50000, "max": 75000, "currency": "USD", "period": "year", "basis": "feed"}
    hourly = [{"min_cents": 2800, "max_cents": 3550, "currency_type": "USD", "title": "Hourly Range"}]
    assert greenhouse.pay_from_ranges(hourly) == {"min": 28, "max": 36, "currency": "USD", "period": "hour", "basis": "feed"}
    # The documentation's own example title names no period, so it is not read.
    unstated = [{"min_cents": 5000000, "max_cents": 7500000, "currency_type": "USD", "title": "NYC Salary Range", "blurb": "..."}]
    assert greenhouse.pay_from_ranges(unstated) is None
    assert greenhouse.pay_from_ranges([{"min_cents": 2800, "max_cents": 3550, "currency_type": "USD"}]) is None
    assert greenhouse.pay_from_ranges([{"min_cents": None, "max_cents": 7500000, "currency_type": "USD", "title": "Annual"}]) is None
    assert greenhouse.pay_from_ranges([]) is None and greenhouse.pay_from_ranges(None) is None


def test_greenhouse_with_pay_asks_once_per_posting_and_survives_a_refusal():
    base = "https://boards-api.greenhouse.io/v1/boards/antora/jobs"
    ranges = [{"min_cents": 15000000, "max_cents": 19000000, "currency_type": "USD", "title": "Annual base salary"}]
    fetcher = FakeFetcher(
        extra={f"{base}/6151698004": {"id": 6151698004, "pay_input_ranges": ranges}},
        failures={f"{base}/6128211004": Blocked("HTTP 429 from boards-api.greenhouse.io")},
    )
    drafts = greenhouse.read("antora", fetcher, with_pay=True)
    assert len(drafts) == 4                               # nothing lost when a detail request is refused
    assert drafts[0]["pay"] == {"min": 150000, "max": 190000, "currency": "USD", "period": "year", "basis": "feed"}
    assert [d["pay"] for d in drafts[1:]] == [None, None, None]
    assert [url for url, _ in fetcher.calls] == [base, f"{base}/6151698004", f"{base}/6128211004"]  # stopped asking
    assert fetcher.calls[1][1] == {"pay_transparency": "true"}


# --------------------------------------------------------------------- Lever

def test_lever_asks_for_json_on_the_documented_address(fetcher):
    lever.read("lightship", fetcher)
    assert fetcher.calls == [("https://api.lever.co/v0/postings/lightship", {"mode": "json"})]


def test_lever_fields(fetcher):
    drafts = lever.read("lightship", fetcher)
    check_shape(drafts)
    harness = by_title(drafts)["Staff Harness Design Engineer - Power Systems"]
    assert harness["url"].startswith("https://jobs.lever.co/lightship/") and harness["url"].endswith(harness["posting_id"])
    assert harness["locations"] == [{"text": "Broomfield, CO", "city": "Broomfield", "state": "CO", "country": "US"}]
    assert harness["workplace"] == "onsite"
    assert harness["employment"] == "full-time"
    assert harness["pay"] == {"min": 155000, "max": 170000, "currency": "USD", "period": "year", "basis": "feed"}
    assert harness["department"] == "Power Systems Engineering"
    assert harness["posted_date"] is not None and harness["posted_date"].startswith("202")
    text = harness["description_text"]
    assert text.startswith("Overview\nLightship is the first American all-electric recreational vehicle manufacturer")
    assert "Responsibilities" in text                  # list headings and items are part of the body
    software = by_title(drafts)["Software/UI Engineer"]
    assert software["workplace"] == "hybrid"
    general = by_title(drafts)["General Submission"]
    assert general["pay"] is None and general["employment"] == "unknown"


def test_lever_hourly_pay_remote_and_several_locations(fetcher):
    drafts = by_title(lever.read("mainspringenergy", fetcher))
    hourly = drafts["Associate Operations Support Specialist II"]
    assert hourly["pay"] == {"min": 20, "max": 27, "currency": "USD", "period": "hour", "basis": "feed"}
    assert hourly["workplace"] == "remote"
    assert hourly["locations"] == [{"text": "Remote", "country": "US"}]     # country from the feed's own field
    assert hourly["employment"] == "unknown"           # the feed's commitment is 'Hourly', which is not a type
    assert hourly["department"] == "O&M - Operations and Maintenance"       # department and team are the same; said once
    field = drafts["Field Service Operations Supervisor (Southern California)"]
    assert [l["text"] for l in field["locations"]] == ["Torrance, CA", "Bakersfield, CA", "San Diego, CA"]
    assert all("country" in l for l in field["locations"])


def test_lever_pay_needs_a_period_the_contract_knows():
    assert lever._pay({"min": 6000, "max": 8000, "currency": "USD", "interval": "per-month-salary"}) is None
    assert lever._pay({"min": 100000, "currency": "USD", "interval": "per-year-salary"}) is None
    assert lever._pay(None) is None


# --------------------------------------------------------------------- Ashby

def test_ashby_asks_for_compensation_on_the_documented_address(fetcher):
    ashby.read("Ridealso", fetcher)
    assert fetcher.calls == [("https://api.ashbyhq.com/posting-api/job-board/Ridealso", {"includeCompensation": "true"})]


def test_ashby_fields(fetcher):
    drafts = ashby.read("Ridealso", fetcher)
    check_shape(drafts)
    staff = by_title(drafts)["Staff Mechanical Design Engineer, Vehicle Integration"]
    assert staff["posting_id"] == "2afce359-065c-4b70-b0c1-f01469bd6224"
    assert staff["url"] == "https://jobs.ashbyhq.com/Ridealso/2afce359-065c-4b70-b0c1-f01469bd6224"
    # The location text is only "Palo Alto"; city, state and country come from the feed's address.
    assert staff["locations"] == [{"text": "Palo Alto", "city": "Palo Alto", "state": "CA", "country": "US"}]
    assert staff["workplace"] == "onsite"
    assert staff["employment"] == "full-time"
    assert staff["posted_date"] == "2025-06-16"
    assert staff["department"] == "Engineering / Mechanical & Electrical Engineering"
    assert staff["pay"] is None                        # this board publishes no compensation
    assert by_title(drafts)["Sales Associate (Part-Time), Miami"]["employment"] == "part-time"


def test_ashby_pay_workplace_and_secondary_locations(fetcher):
    drafts = by_title(ashby.read("formenergy", fetcher))
    quality = drafts["Supplier Quality Engineer"]
    assert quality["pay"] == {"min": 97240, "max": 167728, "currency": "USD", "period": "year", "basis": "feed"}
    assert quality["workplace"] == "remote"
    assert quality["locations"] == [
        {"text": "Remote (USA)", "country": "US"},
        {"text": "Somerville, MA", "city": "Somerville", "state": "MA", "country": "US"},
        {"text": "Weirton, WV", "city": "Weirton", "state": "WV", "country": "US"},
    ]
    recruiter = drafts["Staff Recruiter- Contract"]
    assert recruiter["pay"] == {"min": 75, "max": 95, "currency": "USD", "period": "hour", "basis": "feed"}
    assert recruiter["employment"] == "contract" and recruiter["workplace"] == "hybrid"
    assert drafts["Don't see the job you're looking for?"]["workplace"] is None   # the feed left it empty


def test_ashby_pay_is_the_salary_component_not_equity_or_commission(fetcher):
    drafts = by_title(ashby.read("span", fetcher))
    sales = drafts["Territory Sales Manager - Southwest"]
    assert sales["pay"] == {"min": 130000, "max": 150000, "currency": "USD", "period": "year", "basis": "feed"}
    assert sales["locations"] == [{"text": "Remote"}]  # no address in the feed and no place in the text
    assert drafts["Senior Software Product Manager - Homeowner"]["locations"] == [
        {"text": "San Francisco", "city": "San Francisco", "state": "CA", "country": "US"}]


def test_ashby_leaves_out_unlisted_postings():
    address = "https://api.ashbyhq.com/posting-api/job-board/Ridealso"
    answer = copy.deepcopy(load_json(FIXTURES / ADDRESSES[address]))
    answer["jobs"][0]["isListed"] = False
    drafts = ashby.read("Ridealso", FakeFetcher(extra={address: answer}))
    assert [made["title"] for made in drafts] == ["Sales Associate (Part-Time), Miami"]


# ----------------------------------------------------------------- normalize

def test_employment_from_text_and_title():
    assert normalize.employment_from_text("Full Time") == "full-time"
    assert normalize.employment_from_text("Full-time") == "full-time"
    assert normalize.employment_from_text("Internship") == "intern"
    assert normalize.employment_from_text("Contractor") == "contract"
    assert normalize.employment_from_text("Temporary") == "contract"
    assert normalize.employment_from_text("Salary") == "unknown"
    assert normalize.employment_from_text(None) == "unknown"
    assert normalize.employment_from_title("Summer 2027 Firmware Intern") == "intern"
    assert normalize.employment_from_title("Battery Engineering Co-op") == "intern"
    assert normalize.employment_from_title("Test Technician (Contract)") == "contract"
    assert normalize.employment_from_title("Technical Writer (6 Month Contract)") == "contract"
    assert normalize.employment_from_title("Staff Recruiter- Contract") == "contract"
    assert normalize.employment_from_title("Contracts Manager") == "unknown"
    assert normalize.employment_from_title("Internal Tools Engineer") == "unknown"


def test_ashby_hourly_figures_labelled_yearly_are_left_out():
    """Base Power's feed labels $23 to $25 as "1 YEAR" (recorded 2026-11-24)."""
    answer = load_json(FIXTURES / "ashby_base-power.json")
    labelled = [(c["interval"], c["minValue"], c["maxValue"])
                for c in answer["jobs"][0]["compensation"]["summaryComponents"] if c["compensationType"] == "Salary"]
    assert labelled == [("1 YEAR", 23, 25)]
    drafts = ashby.read("base-power", FakeFetcher())
    assert drafts[0]["pay"] is None                    # not relabelled as hourly; the tagger reads the text
    assert drafts[1]["pay"] is None                    # $32 to $39 across two tiers, also labelled "1 YEAR"
    yearly = by_title(ashby.read("formenergy", FakeFetcher()))["Supplier Quality Engineer"]["pay"]
    assert yearly["period"] == "year" and yearly["min"] >= normalize.YEAR_MIN   # a real salary still passes


def test_pay_bounds_match_the_tagger():
    from pipeline.tag import pay as tag_pay
    assert (normalize.HOUR_MIN, normalize.HOUR_MAX) == (tag_pay.HOUR_MIN, tag_pay.HOUR_MAX)
    assert (normalize.YEAR_MIN, normalize.YEAR_MAX) == (tag_pay.YEAR_MIN, tag_pay.YEAR_MAX)


def test_pay_rejects_what_the_contract_cannot_hold():
    good = {"min": 100000, "max": 120000, "currency": "USD", "period": "year", "basis": "feed"}
    assert normalize.pay(100000, 120000, "usd", "year") == good
    assert normalize.pay(100000.4, 120000.0, "USD", "year") == good
    assert normalize.pay(120000, 100000, "USD", "year") is None      # minimum above maximum
    assert normalize.pay(100000, None, "USD", "year") is None        # one end only
    assert normalize.pay(0, 120000, "USD", "year") is None
    assert normalize.pay(100000, 120000, None, "year") is None
    assert normalize.pay(100000, 120000, "USD", "month") is None
    assert normalize.pay(True, 120000, "USD", "year") is None
    assert normalize.pay(23, 25, "USD", "year") is None               # an hourly rate labelled yearly
    assert normalize.pay(90000, 120000, "USD", "hour") is None        # a salary labelled hourly
    assert normalize.pay(23, 25, "USD", "hour")["period"] == "hour"


def test_dates_and_department():
    assert normalize.iso_date("2026-10-28T14:13:13-04:00") == "2026-10-28"
    assert normalize.iso_date("2025-06-16T21:53:01.620+00:00") == "2025-06-16"
    assert normalize.iso_date("yesterday") is None and normalize.iso_date(None) is None
    assert normalize.epoch_ms_date(1790774665276) == "2026-09-30"
    assert normalize.epoch_ms_date(None) is None
    assert normalize.department("Engineering", "Controls") == "Engineering / Controls"
    assert normalize.department("Quality", "quality", None, "") == "Quality"
    assert normalize.department(None, "") is None
