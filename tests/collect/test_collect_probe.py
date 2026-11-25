"""The careers-page probe, against small sites written for the tests. No network."""
from __future__ import annotations

import httpx
import pytest
from collect_helpers import company

from pipeline.collect import probe_careers as probe_module
from pipeline.collect.fetch import Blocked, FetchError, Fetcher
from pipeline.collect.probe_careers import (ats_links, careers_candidates, classify_careers_page, job_postings,
                                            posting_links, probe, registrable)


class FakeSite:
    """Pages by address; anything else is a 404. Counts requests like a Fetcher."""

    def __init__(self, pages: dict, redirects: dict | None = None, failures: dict | None = None) -> None:
        self.pages, self.redirects, self.failures = pages, redirects or {}, failures or {}
        self.asked: list[str] = []
        self.requests = 0

    def get_page(self, url, stay_within, max_redirects=2, max_bytes=1_000_000):
        for _hop in range(max_redirects + 1):
            self.asked.append(url)
            self.requests += 1
            if url in self.failures:
                raise self.failures[url]
            if url in self.redirects:
                target = self.redirects[url]
                if not stay_within(target):
                    raise FetchError(f"HTTP 301: redirected to {target} (left the site or too many redirects)")
                url = target
                continue
            if url in self.pages:
                return url, self.pages[url]
            raise FetchError("HTTP 404: no board at this address")
        raise FetchError("HTTP 301: too many redirects")

    def close(self):
        pass


def entry(website="https://acme.example.com"):
    return {**company("acme", "unknown", None), "website": website}


HOME = '<html><body><a href="/about">About</a><a href="/careers">Careers</a><a href="https://www.linkedin.com/company/acme/jobs">Jobs on LinkedIn</a></body></html>'


def test_registrable_domain():
    assert registrable("www.acme.example.com") == "example.com"
    assert registrable("careers.acme.co.uk") == "acme.co.uk"
    assert registrable("acme.com") == "acme.com"


def test_ats_links_with_tokens():
    page = ('<a href="https://boards.greenhouse.io/acmeenergy">Jobs</a>'
            '<iframe src="https://jobs.lever.co/acme-power?embed=1"></iframe>'
            '<a href="https://acme.wd5.myworkdayjobs.com/External">Workday</a>')
    found = {(system["type"], system["board"], system["readable"]) for system in ats_links(page)}
    assert found == {("greenhouse", "acmeenergy", True), ("lever", "acme-power", True), ("workday", "acme", False)}


def test_job_posting_blocks_are_counted_in_graphs_and_lists():
    page = ('<script type="application/ld+json">{"@graph": [{"@type": "JobPosting"}, {"@type": "Organization"}]}</script>'
            '<script type="application/ld+json">[{"@type": "JobPosting"}, {"@type": ["JobPosting"]}]</script>'
            '<script type="application/ld+json">{broken</script>')
    assert job_postings(page) == 3


def test_posting_links_stay_on_the_site_and_skip_section_pages():
    page = ('<a href="/careers/senior-controls-engineer">Senior Controls Engineer</a>'
            '<a href="/careers/benefits">Benefits</a>'
            '<a href="/careers/">All</a>'
            '<a href="https://jobs.acme.example.com/jobs/field-technician-2">Field Technician</a>'
            '<a href="https://www.indeed.com/viewjob?jk=1">Indeed</a>'
            '<a href="https://other.example.org/careers/welder-fitter">Elsewhere</a>'
            '<a href="/news/we-are-growing">News</a>')
    found = posting_links(page, "https://acme.example.com/careers", "example.com")
    assert found == ["https://acme.example.com/careers/senior-controls-engineer",
                     "https://jobs.acme.example.com/jobs/field-technician-2"]


def test_careers_candidates_prefer_the_path_and_skip_aggregators():
    found = careers_candidates(HOME, "https://acme.example.com/", "example.com")
    assert found == ["https://acme.example.com/careers"]


@pytest.mark.parametrize("page,outcome,method", [
    ('<a href="https://jobs.ashbyhq.com/Acme">Open roles</a>', "ats-found", "ats-link"),
    ('<script type="application/ld+json">{"@type": "JobPosting", "title": "Engineer"}</script>', "ok", "jobposting-blocks"),
    ('<a href="/careers/battery-test-engineer">Battery Test Engineer</a>', "ok", "plain-listing"),
    ('<a href="/files/job-description-welder.pdf">Welder (PDF)</a>', "unreadable", "pdf"),
    ("<p>There are no current openings. Check back soon.</p>", "none-open", "notice"),
    ('<div id="root"></div><script src="/app.js"></script>', "unreadable", "javascript"),
    ("<p>" + "We build heat pumps. " * 50 + "</p>", "unclear", None),
])
def test_classify_careers_page(page, outcome, method):
    result = classify_careers_page(page, "https://acme.example.com/careers", "example.com")
    assert (result["outcome"], result["method"]) == (outcome, method)


def test_probe_reads_robots_home_and_one_careers_page():
    site = FakeSite({
        "https://acme.example.com/robots.txt": "User-agent: *\nDisallow: /admin\n",
        "https://acme.example.com/": HOME,
        "https://acme.example.com/careers": '<a href="/careers/power-electronics-engineer">Power Electronics Engineer</a>',
    })
    result = probe(entry(), site)
    assert result["outcome"] == "ok" and result["method"] == "plain-listing" and result["postings"] == 1
    assert result["careers_url"] == "https://acme.example.com/careers"
    assert result["requests"] == 3 and len(site.asked) == 3
    assert not any("linkedin" in url for url in site.asked)


def test_probe_obeys_robots():
    site = FakeSite({"https://acme.example.com/robots.txt": "User-agent: *\nDisallow: /\n"})
    result = probe(entry(), site)
    assert result["outcome"] == "robots-disallowed" and site.asked == ["https://acme.example.com/robots.txt"]
    site = FakeSite({"https://acme.example.com/robots.txt": "User-agent: *\nDisallow: /careers\n",
                     "https://acme.example.com/": HOME})
    result = probe(entry(), site)
    assert result["outcome"] == "robots-disallowed" and "https://acme.example.com/careers" not in site.asked


def test_probe_stops_when_robots_cannot_be_read():
    site = FakeSite({}, failures={"https://acme.example.com/robots.txt": FetchError("timed out after 30s")})
    result = probe(entry(), site)
    assert result["outcome"] == "error" and "robots.txt could not be read" in result["note"]
    assert site.asked == ["https://acme.example.com/robots.txt"]


def test_probe_stops_on_a_block_or_a_bot_check():
    site = FakeSite({}, failures={"https://acme.example.com/robots.txt": Blocked("HTTP 403 from acme.example.com")})
    assert probe(entry(), site)["outcome"] == "blocked"
    site = FakeSite({"https://acme.example.com/": "<title>Just a moment...</title>"})
    result = probe(entry(), site)
    assert result["outcome"] == "blocked" and result["note"] == "bot check" and len(site.asked) == 2


TEXT = "<p>" + "We design and build flywheel storage for the grid. " * 20 + "</p>"
NAV = "".join(f'<a href="/page-{n}">Page {n}</a>' for n in range(12))


def test_probe_tries_the_usual_paths_and_stays_within_four_pages():
    site = FakeSite({"https://acme.example.com/": TEXT + NAV})
    result = probe(entry(), site)
    assert result["outcome"] == "no-careers-page"
    assert site.asked == ["https://acme.example.com/robots.txt", "https://acme.example.com/",
                          "https://acme.example.com/careers", "https://acme.example.com/jobs"]


def test_a_near_empty_home_page_is_unreadable_not_missing():
    site = FakeSite({"https://acme.example.com/": "<html><body><div>Acme</div></body></html>"})
    result = probe(entry(), site)
    assert result["outcome"] == "unreadable" and result["method"] == "javascript"


def test_recaptcha_on_an_ordinary_page_is_not_a_bot_check():
    page = TEXT + '<script src="https://www.google.com/recaptcha/api.js"></script>{"captchaSettings": {}}'
    assert probe_module.refusal(page) is None
    assert probe_module.refusal("<html><title>Just a moment...</title></html>") == "bot check"
    assert probe_module.refusal("<p>Access denied</p>") == "bot check"
    assert probe_module.refusal(TEXT * 2 + "<p>Access denied for staff areas</p>") is None


def test_a_hiring_section_on_the_home_page_is_read_without_another_request():
    # Seen live: one opening on the home page, as a PDF on the site builder's CDN.
    home = (TEXT + "<h2>We're hiring</h2><p>Business Manager</p>"
            '<a href="https://cdn.example-builder.com/files/Business%20Manager%20-%202026.pdf">Apply Here</a>')
    site = FakeSite({"https://acme.example.com/": home})
    result = probe(entry(), site)
    assert result["outcome"] == "unreadable" and result["method"] == "pdf" and result["postings"] == 1
    assert result["careers_url"] == "https://acme.example.com/" and len(site.asked) == 2


def test_saved_pages_replay_and_fill_in_only_what_is_missing(tmp_path):
    from pipeline.collect.fetch import RecordingFetcher
    def handler(request):
        return httpx.Response(200, text=f"<p>{request.url.path}</p>")
    live = RecordingFetcher(tmp_path, client=httpx.Client(transport=httpx.MockTransport(handler)), sleep=lambda _: None)
    stay = lambda url: True
    live.get_page("https://a.example.com/", stay)                 # saved by an earlier pass
    saved = probe_module.SavedPages(tmp_path)
    assert saved.get_page("https://a.example.com/", stay) == ("https://a.example.com/", "<p>/</p>")
    with pytest.raises(FetchError, match="not saved"):
        saved.get_page("https://a.example.com/careers", stay)
    filled = probe_module.SavedPages(tmp_path, live=live)
    assert filled.get_page("https://a.example.com/careers", stay)[1] == "<p>/careers</p>"
    assert filled.live_requests == 1 and filled.requests == 1


def test_probe_follows_redirects_only_on_the_site_and_counts_them():
    site = FakeSite({"https://www.example.com/": '<a href="https://jobs.lever.co/acme">Careers</a>'},
                    redirects={"https://acme.example.com/": "https://www.example.com/"})
    result = probe(entry(), site)
    assert result["outcome"] == "ats-found" and result["ats"][0]["board"] == "acme"
    assert result["requests"] == 3        # robots, the redirect, the home page
    site = FakeSite({}, redirects={"https://acme.example.com/": "https://parked-domains.example.net/"})
    assert probe(entry(), site)["outcome"] == "error"


def test_the_real_fetcher_follows_a_redirect_on_the_site_only():
    def handler(request):
        if request.url.host == "acme.example.com":
            return httpx.Response(301, headers={"location": "https://www.example.com/"})
        if request.url.host == "www.example.com":
            return httpx.Response(200, text="<p>home</p>")
        return httpx.Response(500)
    fetcher = Fetcher(client=httpx.Client(transport=httpx.MockTransport(handler)), sleep=lambda _: None)
    stay = lambda url: probe_module.on_site(url, "example.com")
    assert fetcher.get_page("https://acme.example.com/", stay) == ("https://www.example.com/", "<p>home</p>")
    assert fetcher.requests == 2
    with pytest.raises(FetchError, match="left the site"):
        fetcher.get_page("https://acme.example.com/", lambda url: False)


def test_companies_to_probe_are_listed_unknown_and_have_a_website():
    listed = {**company("a", "unknown", None), "website": "https://a.example.com",
              "startup": {"status": "in", "reason": None}}
    assert probe_module.companies_to_probe([listed]) == [listed]
    assert probe_module.companies_to_probe([{**listed, "website": None}]) == []
    assert probe_module.companies_to_probe([{**listed, "ats": {"type": "greenhouse", "board": "a"}}]) == []


def test_decision_12b_reads_what_robots_disallows_and_says_so():
    site = FakeSite({"https://acme.example.com/robots.txt": "User-agent: *\nDisallow: /\n",
                     "https://acme.example.com/": HOME,
                     "https://acme.example.com/careers": '<a href="/careers/controls-engineer">Controls Engineer</a>'})
    result = probe(entry(), site, obey_robots=False)
    assert result["outcome"] == "ok" and "decision 12b" in result["robots"]
    assert probe(entry(), FakeSite(site.pages))["outcome"] == "robots-disallowed"


def test_established_companies_are_probed_with_the_flag():
    established = {**company("b", "unknown", None, status="out"), "website": "https://b.example.com"}
    assert probe_module.companies_to_probe([established]) == []
    assert probe_module.companies_to_probe([established], established=True) == [established]


def test_workable_short_links_name_the_system_without_a_token():
    found = ats_links('<a href="https://apply.workable.com/j/1A2B3C4D5E">Apply</a>')
    assert found == [{"type": "workable", "board": None, "readable": True}]


def test_a_careers_page_with_almost_no_text_is_unreadable():
    result = classify_careers_page("<html><body><div>Careers</div></body></html>", "https://acme.example.com/careers", "example.com")
    assert result["outcome"] == "unreadable" and "almost no text" in result["note"]


def test_a_careers_page_that_points_to_linkedin_is_routed_to_the_careers_reader():
    page = TEXT + '<p>We post our openings on LinkedIn.</p><a href="https://www.linkedin.com/company/acme/jobs/">See our open jobs</a>'
    result = classify_careers_page(page, "https://acme.example.com/careers", "example.com")
    assert result["outcome"] == "unclear" and result["method"] == "linkedin"
    icon = TEXT + '<a href="https://www.linkedin.com/company/acme/">LinkedIn</a>'
    assert classify_careers_page(icon, "https://acme.example.com/careers", "example.com")["method"] != "linkedin"
