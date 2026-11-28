"""SAP SuccessFactors and Jobvite readers.

Fixtures are real answers recorded on 2026-11-27, trimmed: a few sitemap
entries, posting pages cut to their posting block, descriptions shortened.
"""
from __future__ import annotations

from collect_helpers import FIXTURES, company

from pipeline.collect import jobvite, normalize, successfactors as sf
from pipeline.collect.fetch import Blocked, FetchError
from pipeline.collect.run import board_problem, collect, skip_reason
from pipeline.collect.state import SeenState

VESTAS = "https://careers.vestas.com"
NUSCALE = "https://jobs.jobvite.com/nuscale-power"
TIMED_OUT = FetchError("timed out (ReadTimeout: no complete answer within 120s)")


class Site:
    """Pages by address; anything else is a 404. Records what was asked."""

    def __init__(self, pages: dict, failures: dict | None = None) -> None:
        self.pages, self.failures = pages, failures or {}
        self.asked: list[str] = []

    def get_page(self, url, stay_within, max_redirects=2, max_bytes=1_000_000):
        self.asked.append(url)
        assert stay_within(url), f"left the site: {url}"
        if url in self.failures:
            raise self.failures[url]
        if url in self.pages:
            return url, self.pages[url]
        raise FetchError(f"HTTP 404: no page at {url}")

    def close(self):
        pass


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def vestas_site(**changes) -> Site:
    pages = {
        f"{VESTAS}/robots.txt": fixture("successfactors_vestas_robots.txt"),
        f"{VESTAS}/sitemap.xml": fixture("successfactors_vestas_sitemap.xml"),
        f"{VESTAS}/job/Brighton-Warehouse-Supervisor-CO/1459982433/": fixture("successfactors_vestas_1459982433.html"),
        f"{VESTAS}/job/Windsor-Senior-Process-Engineer-CO-80550-3397/1460005633/":
            fixture("successfactors_vestas_1460005633.html"),
        f"{VESTAS}/job/Jurien-Bay-Service-Technician-AU-WA/1460007833/": fixture("successfactors_vestas_1460007833.html"),
    }
    pages.update(changes)
    return Site(pages)


# --------------------------------------------------------------- SuccessFactors

def test_us_candidates_from_the_slug():
    job = lambda slug: f"{VESTAS}/job/{slug}/1459982433/"
    assert sf.us_candidate(job("Brighton-Warehouse-Supervisor-CO"))
    assert sf.us_candidate(job("Windsor-Senior-Process-Engineer-CO-80550-3397"))
    assert sf.us_candidate(job("Iraan-Stock-Keeper-Crockett-County%2C-TX-TX-79744"))
    assert sf.us_candidate(job("Camden-Project-Engineer-II-NJ-08101"))          # "II" before the state is fine
    assert sf.us_candidate(job("Jurien-Bay-Service-Technician-AU-WA"))          # a candidate; its page says AU
    assert not sf.us_candidate(job("Zistersdorf-Service-Technician-%28mfd%29-in-Zistersdorf-Lowe"))
    assert not sf.us_candidate(job("Pune-Nuclear-Analyst-MH"))                  # Maharashtra: not a state code
    assert not sf.us_candidate(f"{VESTAS}/search/?q=CO")                          # not a posting address


def test_reads_robots_sitemap_then_only_us_candidate_pages():
    site = vestas_site()
    result = sf.read(VESTAS, site)
    assert site.asked[:2] == [f"{VESTAS}/robots.txt", f"{VESTAS}/sitemap.xml"]
    assert not any("/services/" in url or "/search" in url for url in site.asked)
    assert not any("Zistersdorf" in url for url in site.asked)                  # Austria: never asked
    drafts = {draft["posting_id"]: draft for draft in result}
    # Jurien Bay's page places it in Australia; Austin's and Houston's pages failed (404): nothing to keep.
    assert set(drafts) == {"1459982433", "1460005633"}
    windsor = drafts["1460005633"]
    assert windsor["title"] == "Senior Process Engineer"
    assert windsor["url"] == f"{VESTAS}/job/Windsor-Senior-Process-Engineer-CO-80550-3397/1460005633/"
    assert windsor["locations"] == [{"text": "Windsor, CO", "city": "Windsor", "state": "CO", "country": "US"}]
    assert windsor["posted_date"] == "2026-11-19"                               # "19/11/2026" on an en-GB page
    assert windsor["department"] == "Engineering"
    assert windsor["description_text"].startswith("Senior Process Engineer")
    assert windsor["pay"] is None
    assert drafts["1459982433"]["posted_date"] == "2026-11-02"


def test_the_sitemap_address_is_unescaped():
    site = vestas_site()
    sf.read(VESTAS, site)
    assert f"{VESTAS}/job/Houston-Leave-&-Workers-Compensation-Specialist-TX-77002/1459981233/" in site.asked


def test_microdata_address_and_date_when_the_site_has_them():
    holtec = "https://holtec.jobs.hr.cloud.sap/job/Camden-Project-Controls-Estimator-III-NJ-08101/1401953800/"
    made = sf.draft(holtec, fixture("successfactors_holtec_1401953800.html"))
    assert made["locations"] == [{"text": "Camden, NJ", "city": "Camden", "state": "NJ", "country": "US"}]
    assert made["posted_date"] == "2026-11-14"                                  # "Sat Nov 14 08:00:00 UTC 2026"
    assert made["department"] == "Project Management"
    quantumscape = "https://careers.quantumscape.com/job/Staff-Engineer%2C-Process-Development-Req-1545-CA-95131/1407715700/"
    made = sf.draft(quantumscape, fixture("successfactors_quantumscape_1407715700.html"))
    assert made["title"] == "Staff Engineer, Process Development - Req 1545"
    assert made["locations"] == [{"text": "CA", "state": "CA", "country": "US"}]  # "CA, US, 95131"
    assert made["workplace"] == "onsite"                                          # "Work Location Type: On-site"
    assert made["posted_date"] == "2026-11-03"


def test_place_needs_a_country():
    assert sf.place({}, {"location": "Jurien Bay, WA / AU"})["country"] == "AU"
    assert sf.place({}, {"location": "Chennai, TN"}) is None                    # could be read as Tennessee
    assert sf.place({}, {"location": "Austin, TX, 78701 / US"})["city"] == "Austin"


def test_dates_written_month_first_on_us_pages():
    page = '<span lang="en-US" itemprop="title">x</span>'
    assert sf.posted({}, {"date": "11/03/2026"}, page) == "2026-11-03"
    assert sf.posted({}, {"date": "11/03/2026"}, page.replace("en-US", "en-GB")) == "2026-03-11"
    assert sf.posted({}, {"date": "19/11/2026"}, page) == "2026-11-19"           # cannot be month first
    assert sf.posted({}, {"date": "Nov 3, 2026"}, "") == "2026-11-03"


def test_robots_that_disallow_the_sitemap_stop_the_reader():
    site = vestas_site(**{f"{VESTAS}/robots.txt": "User-agent: *\nDisallow: /sitemap.xml\n"})
    try:
        sf.read(VESTAS, site)
    except FetchError as error:
        assert "disallows" in str(error)
    else:
        raise AssertionError("expected a refusal")
    assert site.asked == [f"{VESTAS}/robots.txt"]


def test_robots_that_disallow_posting_pages_are_obeyed():
    site = vestas_site(**{f"{VESTAS}/robots.txt": "User-agent: *\nDisallow: /job/\n"})
    try:
        sf.read(VESTAS, site)
    except FetchError as error:
        assert "posting pages" in str(error)
    else:
        raise AssertionError("expected a refusal")
    assert not any("/job/" in url for url in site.asked)


def test_a_bot_check_blocks_the_company():
    challenge = "<html><head><title>Just a moment...</title></head><body>Checking your browser</body></html>"
    site = vestas_site(**{f"{VESTAS}/sitemap.xml": challenge})
    try:
        sf.read(VESTAS, site)
    except Blocked:
        pass
    else:
        raise AssertionError("expected Blocked")


def test_cap_and_timeouts_give_a_partial_result(monkeypatch):
    monkeypatch.setattr(sf, "MAX_PAGES", 1)
    result = sf.read(VESTAS, vestas_site())
    assert isinstance(result, normalize.ReadResult) and result.status == "partial"
    assert "the first 1 of 5 US posting pages" in result.note
    site = vestas_site()
    site.failures = {url: TIMED_OUT for url in sf.sitemap_postings(fixture("successfactors_vestas_sitemap.xml"))}
    monkeypatch.setattr(sf, "MAX_PAGES", 400)
    result = sf.read(VESTAS, site)
    assert result.status == "partial" and "3 timeouts in a row" in result.note
    assert sum("/job/" in url for url in site.asked) == 3


def test_a_sitemap_with_no_us_postings_is_none_open():
    only_abroad = ('<urlset><url><loc>https://careers.vestas.com/job/Zistersdorf-Service-Technician-%28mfd%29-in-'
                   'Zistersdorf-Lowe/1459937033/</loc></url></urlset>')
    site = vestas_site(**{f"{VESTAS}/sitemap.xml": only_abroad})
    result = sf.read(VESTAS, site)
    assert result.status == "none-open" and "none in the US" in result.note
    assert len(site.asked) == 2
    empty = sf.read(VESTAS, vestas_site(**{f"{VESTAS}/sitemap.xml": "<urlset></urlset>"}))
    assert empty.status == "none-open" and "lists no postings" in empty.note


def test_successfactors_board_shape_and_collect():
    assert board_problem(company("vestas", "successfactors", "https://careers.vestas.com")) is None
    assert "not in the form" in board_problem(company("vestas", "successfactors", "careers.vestas.com"))
    assert "not in the form" in board_problem(company("vestas", "successfactors", "https://careers.vestas.com/search/"))
    raw = collect([company("vestas", "successfactors", VESTAS)], vestas_site(), SeenState(), now=lambda: "2026-11-27T16:00:00Z")
    assert {job["id"] for job in raw["jobs"]} == {"successfactors:https-careers.vestas.com:1459982433",
                                                  "successfactors:https-careers.vestas.com:1460005633"}
    assert raw["run"]["companies"][0]["status"] == "ok"


# -------------------------------------------------------------------- Jobvite

def nuscale_site() -> Site:
    return Site({
        f"{NUSCALE}/jobs": fixture("jobvite_nuscale-power_jobs.html"),
        f"{NUSCALE}/job/o9tMAfwI": fixture("jobvite_nuscale-power_o9tMAfwI.html"),
    })


def test_jobvite_cards_from_a_real_list():
    cards = jobvite.cards(fixture("jobvite_nuscale-power_jobs.html"), "nuscale-power")
    assert len(cards) == 29
    assert cards[0] == {"id": "oiOZAfwp", "url": f"{NUSCALE}/job/oiOZAfwp",
                        "title": "Contractor - Electrical Engineer (Plant Systems)",
                        "location": "Remote, United States", "category": "Contract Assignment"}
    assert {card["location"] for card in cards} == {"Remote, United States", "Houston, TX", "Remote, 3 Locations"}
    assert all(card["category"] for card in cards)


def test_jobvite_reads_the_list_then_each_posting():
    site = nuscale_site()
    drafts = {draft["posting_id"]: draft for draft in jobvite.read("nuscale-power", site)}
    assert site.asked[0] == f"{NUSCALE}/jobs" and len(site.asked) == 30
    assert len(drafts) == 29
    engineer = drafts["o9tMAfwI"]
    assert engineer["title"] == "Nuclear Engineer 4"
    assert engineer["url"] == f"{NUSCALE}/job/o9tMAfwI"
    assert engineer["posted_date"] == "2026-09-10" and engineer["employment"] == "full-time"
    assert engineer["workplace"] == "remote"                                     # jobLocationType TELECOMMUTE
    assert engineer["locations"][0]["country"] == "US"
    assert engineer["pay"] is None                                               # baseSalary is empty
    assert "$140,940" in engineer["description_text"]
    # A posting page that failed: kept from the list, with its category.
    houston = next(draft for draft in drafts.values() if draft["locations"] and draft["locations"][0].get("city") == "Houston")
    assert houston["locations"][0]["state"] == "TX" and houston["description_text"] == "" and houston["department"]
    many = next(draft for draft in drafts.values() if draft["posting_id"] != "o9tMAfwI" and not draft["locations"])
    assert many["title"]                                                         # "Remote, 3 Locations": no single place


def test_jobvite_a_retired_site_is_an_error():
    site = Site({})
    site.failures = {f"https://jobs.jobvite.com/view/jobs":
                     FetchError("HTTP 302: redirected to http://search.jobvite.com/?invalid=1 (left the site or too many redirects)")}
    try:
        jobvite.read("view", site)
    except FetchError as error:
        assert "search.jobvite.com" in str(error)
    else:
        raise AssertionError("expected an error")


def test_jobvite_board_shape_and_ids():
    assert board_problem(company("nuscale-power", "jobvite", "nuscale-power")) is None
    assert "not in the form" in board_problem(company("nuscale-power", "jobvite", "https://jobs.jobvite.com/nuscale-power"))
    assert skip_reason(company("nuscale-power", "jobvite", "nuscale-power")) is None
    raw = collect([company("nuscale-power", "jobvite", "nuscale-power")], nuscale_site(), SeenState(),
                  now=lambda: "2026-11-27T16:00:00Z")
    assert "jobvite:nuscale-power:o9tMAfwI" in {job["id"] for job in raw["jobs"]}
