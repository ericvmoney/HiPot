"""The careers-page reader (ATS type 'other'), against small sites written for the tests."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from collect_helpers import company
from test_collect_probe import FakeSite

from pipeline.collect import careers
from pipeline.collect.fetch import Blocked, FetchError
from pipeline.collect.run import collect
from pipeline.collect.state import SeenState

NOW = datetime(2026, 11, 25, 16, 0, tzinfo=timezone.utc)
CAREERS = "https://acme.example.com/careers"
ROBOTS = "https://acme.example.com/robots.txt"
BODY = "<p>" + "You will design power electronics for grid batteries and test them in our lab. " * 5 + "</p>"


def context(**kwargs):
    return careers.Context(now=kwargs.pop("now", NOW), **kwargs)


def ld(**fields):
    import json
    return f'<script type="application/ld+json">{json.dumps({"@context": "https://schema.org", "@type": "JobPosting", **fields})}</script>'


def test_job_posting_blocks():
    page = ld(title="Controls Engineer", description="<p>" + "Build controls. " * 20 + "</p>",
              datePosted="2026-11-20", employmentType="FULL_TIME",
              jobLocation={"@type": "Place", "address": {"addressLocality": "Golden", "addressRegion": "CO", "addressCountry": "US"}},
              baseSalary={"currency": "USD", "value": {"minValue": 110000, "maxValue": 140000, "unitText": "YEAR"}})
    page += ld(title="Old Role", validThrough="2026-01-01", description="x")
    result = careers.read(CAREERS, FakeSite({CAREERS: page}), context())
    assert result.status == "ok" and len(result.drafts) == 1
    made = result.drafts[0]
    assert made["title"] == "Controls Engineer" and made["url"] == CAREERS
    assert made["posting_id"] == "careers#controls-engineer"
    assert made["locations"] == [{"text": "Golden, CO, US", "city": "Golden", "state": "CO", "country": "US"}]
    assert made["pay"] == {"min": 110000, "max": 140000, "currency": "USD", "period": "year", "basis": "feed"}
    assert made["employment"] == "full-time" and made["posted_date"] == "2026-11-20"


def test_plain_listing_reads_each_posting_page():
    site = FakeSite({
        CAREERS: '<a href="/careers/power-electronics-engineer">Power Electronics Engineer</a>'
                 '<a href="/careers/field-technician">Field Technician</a>'
                 '<a href="https://www.indeed.com/viewjob?jk=1">Indeed</a>',
        "https://acme.example.com/careers/power-electronics-engineer":
            "<html><title>Power Electronics Engineer | Acme</title><body><nav>Home About</nav><main>"
            "<h1>Power Electronics Engineer</h1><p>Location: Boulder, CO</p>" + BODY + "</main></body></html>",
    })
    result = careers.read(CAREERS, site, context())
    assert result.status == "partial" and "1 of 2 listed postings read" in result.note
    made = result.drafts[0]
    assert made["title"] == "Power Electronics Engineer"
    assert made["posting_id"] == "careers/power-electronics-engineer"
    assert made["locations"][0]["city"] == "Boulder" and "design power electronics" in made["description_text"]
    assert not any("indeed" in url for url in site.asked)


@pytest.mark.parametrize("page,status", [
    ('<a href="https://jobs.lever.co/acme">Open roles</a>', "ats-found"),
    ("<p>We have no open positions at this time.</p>", "none-open"),
    ('<div id="root"></div>', "unreadable"),
    ('<a href="/files/welder-job-description.pdf">Welder</a>', "unreadable"),
    ("<p>" + "We build heat pumps. " * 50 + "</p>", "unreadable"),
])
def test_outcomes_without_postings(page, status):
    result = careers.read(CAREERS, FakeSite({CAREERS: page}), context())
    assert result.status == status and result.drafts == []
    if status == "ats-found":
        assert result.note == "careers page links to lever:acme"


def test_a_careers_page_that_is_gone():
    assert careers.read(CAREERS, FakeSite({}), context()).status == "no-careers-page"


def test_a_bot_check_blocks_the_company():
    with pytest.raises(Blocked):
        careers.read(CAREERS, FakeSite({CAREERS: "<title>Just a moment...</title>"}), context())


def test_robots_disallow_means_a_weekly_read_with_postings_carried_between():
    page = ld(title="Controls Engineer", description="<p>" + "Build controls. " * 20 + "</p>")
    pages = {ROBOTS: "User-agent: *\nDisallow: /careers\n", CAREERS: page}
    shared = context()
    first = careers.read(CAREERS, FakeSite(pages), shared)
    assert first.status == "ok" and len(first.drafts) == 1
    assert first.note.startswith("robots.txt disallows the careers page: read on the 7-day schedule")
    # Two days later: not read, the postings are carried with their real time.
    site = FakeSite(pages)
    later = careers.read(CAREERS, site, careers.Context(sites=shared.sites, now=NOW + timedelta(days=2)))
    assert site.asked == [ROBOTS]
    assert later.status == "ok" and later.drafts == first.drafts and later.seen_at == "2026-11-25T16:00:00Z"
    assert "not read this run, 1 postings carried from 2026-11-25" in later.note
    # Eight days later: read again.
    site = FakeSite(pages)
    careers.read(CAREERS, site, careers.Context(sites=shared.sites, now=NOW + timedelta(days=8)))
    assert CAREERS in site.asked


def test_carried_postings_keep_their_last_seen(tmp_path):
    pages = {ROBOTS: "User-agent: *\nDisallow: /\n",
             CAREERS: ld(title="Controls Engineer", description="<p>" + "Build controls. " * 20 + "</p>")}
    shared = context()
    acme = {**company("acme", "other", CAREERS)}
    state = SeenState()
    collect([acme], FakeSite(pages), state, readers={"other": lambda b, f: careers.read(b, f, shared)},
            now=lambda: "2026-11-25T16:00:00Z")
    later = careers.Context(sites=shared.sites, now=NOW + timedelta(days=3))
    raw = collect([acme], FakeSite(pages), state, readers={"other": lambda b, f: careers.read(b, f, later)},
                  now=lambda: "2026-11-28T16:00:00Z")
    job = raw["jobs"][0]
    assert job["last_seen"] == "2026-11-25T16:00:00Z"
    assert raw["run"]["companies"][0]["status"] == "ok" and "carried" in raw["run"]["companies"][0]["error"]


LINKEDIN_JOB = "https://www.linkedin.com/jobs/view/4012345678"


def test_linkedin_jobs_the_careers_page_points_to_are_read():
    page = '<p>We post our openings on LinkedIn.</p><a href="https://www.linkedin.com/jobs/view/senior-engineer-at-acme-4012345678?trk=x">Senior Engineer</a>'
    job_page = ld(title="Senior Engineer", description="<p>" + "Design flywheels. " * 20 + "</p>",
                  datePosted="2026-11-18", jobLocation={"address": {"addressLocality": "Denver", "addressRegion": "CO", "addressCountry": "US"}})
    shared = context()
    result = careers.read(CAREERS, FakeSite({CAREERS: page, LINKEDIN_JOB: job_page}), shared)
    assert result.status == "ok" and len(result.drafts) == 1
    made = result.drafts[0]
    assert made["url"] == LINKEDIN_JOB and made["posting_id"] == "linkedin-4012345678"
    assert made["locations"][0]["city"] == "Denver"
    assert shared.linkedin_requests == 1


def test_a_linkedin_footer_icon_is_not_followed():
    page = "<p>" + "We build heat pumps. " * 50 + '</p><a href="https://www.linkedin.com/company/acme">LinkedIn</a>'
    site = FakeSite({CAREERS: page})
    assert careers.read(CAREERS, site, context()).status == "unreadable"
    assert not any("linkedin" in url for url in site.asked)


def test_a_linkedin_sign_in_wall_blocks_and_stops_linkedin_for_the_run():
    page = '<a href="https://www.linkedin.com/company/acme/jobs">See our jobs on LinkedIn</a>'
    site = FakeSite({CAREERS: page}, redirects={
        "https://www.linkedin.com/company/acme/jobs": "https://www.linkedin.com/authwall?trk=bf"})
    shared = context()
    with pytest.raises(Blocked, match="sign-in wall"):
        careers.read(CAREERS, site, shared)
    assert shared.linkedin_blocked
    other = FakeSite({CAREERS: page})
    result = careers.read(CAREERS, other, shared)
    assert result.status == "blocked" and "LinkedIn not asked" in result.note
    assert not any("linkedin" in url for url in other.asked)


def test_the_linkedin_cap():
    page = "".join(f'<a href="https://www.linkedin.com/jobs/view/{4012345600 + n}">Role {n}</a>' for n in range(5))
    pages = {CAREERS: page}
    for n in range(5):
        pages[f"https://www.linkedin.com/jobs/view/{4012345600 + n}"] = ld(title=f"Role {n}", description="<p>" + "x " * 150 + "</p>")
    shared = context(linkedin_requests=careers.LINKEDIN_CAP - 2)
    result = careers.read(CAREERS, FakeSite(pages), shared)
    assert result.status == "partial" and len(result.drafts) == 2 and "cap" in result.note


def test_run_statuses_reach_the_run_entry_and_hosts_are_kept_apart():
    gone = {**company("gone", "other", "https://gone.example.org/careers")}
    refusing = {**company("refusing", "other", "https://refusing.example.net/careers")}
    acme = {**company("acme", "other", CAREERS)}
    site = FakeSite({CAREERS: "<p>No current openings.</p>"},
                    failures={"https://refusing.example.net/robots.txt": Blocked("HTTP 429 from refusing.example.net")})
    raw = collect([refusing, gone, acme], site, SeenState(), now=lambda: "2026-11-25T16:00:00Z",
                  readers={"other": lambda b, f: careers.read(b, f, context())})
    statuses = {entry["company_id"]: entry["status"] for entry in raw["run"]["companies"]}
    # One site's 429 does not stop the others.
    assert statuses == {"refusing": "blocked", "gone": "no-careers-page", "acme": "none-open"}


def test_context_round_trip(tmp_path):
    path = tmp_path / "careers.json"
    saved = careers.Context(path=path, sites={"example.com": {"read_at": "2026-11-25T16:00:00Z", "drafts": []}})
    saved.save()
    assert careers.Context.load(path).sites == saved.sites


def test_found_in_the_first_live_run():
    # Big Blue: a JobPosting block with no address or identifier on each posting
    # page, and a standing "Any Position" invitation. Steelhead: a posting page
    # whose text is outside <main>.
    site = FakeSite({
        CAREERS: '<a href="/jobs/foundry-operator/">Foundry Operator</a><a href="/jobs/any-position/">Any Position</a>'
                 '<a href="/careers/production-technician">Production Technician</a>',
        "https://acme.example.com/jobs/foundry-operator/": ld(title="Foundry Operator", description=BODY, datePosted="2026-10-31T19:49:09-06:00"),
        "https://acme.example.com/jobs/any-position/": ld(title="Any Position", description=BODY),
        "https://acme.example.com/careers/production-technician":
            "<html><body><main><h1>Production Technician</h1></main><div class='content'>" + BODY + "</div></body></html>",
    })
    result = careers.read(CAREERS, site, context())
    assert result.status == "ok"
    by_title = {made["title"]: made for made in result.drafts}
    assert set(by_title) == {"Foundry Operator", "Production Technician"}
    assert by_title["Foundry Operator"]["posting_id"] == "jobs/foundry-operator"
    assert by_title["Foundry Operator"]["posted_date"] == "2026-10-31"
    assert "design power electronics" in by_title["Production Technician"]["description_text"]
