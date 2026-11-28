"""Careers-page probe: one measured look at companies' own careers pages.

    uv run python -m pipeline.collect.probe_careers --out data/screening/careers-probe-01.yml

For each company that is listed (core or enabling, startup 'in'), has a
website, and whose ATS type is 'unknown', the probe makes at most four page
requests:

  1. robots.txt on the website's host (rules for '*' are obeyed throughout);
  2. the home page;
  3. and 4. at most two careers pages: the best careers links on the home page,
     or /careers and /jobs when the home page has none.

Redirects are followed only within the company's own domain, and each hop
counts as a request (at most six hops per company in all). The probe reads no
posting page, runs no JavaScript and sends no forms. It stops at once for a
company on HTTP 403 or 429, a sign-in page or a bot check. Hosts are asked at
most every 3 s.

It classifies what it found (see OUTCOMES) and writes one YAML entry per
company. It does not write postings: it measures what a careers-page reader
would find, before such a reader is built.
"""
from __future__ import annotations

import argparse
import html as html_lib
import json
import re
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import yaml

from pipeline.collect.fetch import Blocked, FetchError, Fetcher, RecordingFetcher, ReplayFetcher, is_timeout
from pipeline.io import ROOT, load_yaml
from tools.validate import company_type, is_listed

PAGE_INTERVAL = 3.0
MAX_PAGES = 4          # robots.txt, home page, two careers pages
MAX_HOPS = 6           # page requests plus redirects within the site

OUTCOMES = {
    "ok": "postings found on the careers page (JobPosting blocks, or links to posting pages on the site)",
    "ats-found": "the site links to a job-board system; see ats",
    "none-open": "a careers page was read and says there are no openings",
    "unclear": "a careers page was read but shows neither postings nor a no-openings notice",
    "unreadable": "the careers page builds its list with JavaScript, or gives postings only as PDFs",
    "no-careers-page": "no careers page was found on the site",
    "robots-disallowed": "robots.txt disallows the page the probe needed",
    "blocked": "the site refused the probe (403 or 429, a sign-in page or a bot check)",
    "error": "the site could not be reached",
}

# Job-board systems, readable or not, as they appear in links and embeds.
# Each pattern's group 1 is the board token where the address carries one.
ATS_PATTERNS = [
    ("greenhouse", r"(?:job-boards|boards)(?:\.eu)?\.greenhouse\.io/(?:embed/job_board(?:/js)?\?for=)?([A-Za-z0-9_]+)"),
    ("greenhouse", r"boards-api\.greenhouse\.io/v1/boards/([A-Za-z0-9_]+)"),
    ("lever", r"jobs\.(?:eu\.)?lever\.co/([A-Za-z0-9_.\-]+)"),
    ("ashby", r"jobs\.ashbyhq\.com/([A-Za-z0-9_.%\-]+)"),
    ("rippling", r"ats\.rippling\.com/(?:embed/)?(?:[a-z]{2}-[A-Z]{2}/)?([A-Za-z0-9_\-]+)"),
    # apply.workable.com/j/<code> is a short posting link that names no account.
    ("workable", r"apply\.workable\.com/(?!j/)([A-Za-z0-9_\-]+)"),
    ("workable", r"apply\.workable\.com/j/"),
    ("workable", r"//([A-Za-z0-9\-]+)\.workable\.com"),
    ("bamboohr", r"//([A-Za-z0-9\-]+)\.bamboohr\.com"),
    ("smartrecruiters", r"(?:jobs|careers)\.smartrecruiters\.com/([A-Za-z0-9_\-]+)"),
    ("recruitee", r"//([A-Za-z0-9\-]+)\.recruitee\.com"),
    ("recruitee", r"id=\"recruitee-careers\""),          # the widget, which names no account
    ("jazzhr", r"//([A-Za-z0-9\-]+)\.applytojob\.com"),
    ("jazzhr", r"app\.jazz\.co/widgets/[a-z]+/create/([A-Za-z0-9_\-]+)"),
    ("breezy", r"//([A-Za-z0-9\-]+)\.breezy\.hr"),
    ("teamtailor", r"//([A-Za-z0-9\-]+)\.(?:na\.)?teamtailor\.com"),
    ("gem", r"jobs\.gem\.com/([A-Za-z0-9_\-]+)"),
    ("paylocity", r"recruiting\.paylocity\.com/recruiting/jobs/All/([0-9a-fA-F\-]{36})"),
    ("paylocity", r"recruiting\.paylocity\.com/recruiting/jobs/Details/\d+"),   # a posting; no board
    ("workday", r"//([A-Za-z0-9\-]+)\.wd\d+\.myworkdayjobs\.com"),
    ("icims", r"//([A-Za-z0-9\-]+)\.icims\.com"),
    ("adp", r"workforcenow\.adp\.com|myjobs\.adp\.com"),
    ("ukg", r"\.ultipro\.com|recruiting\d*\.ultipro\.com|\.ukg\.net"),
    ("paycom", r"paycomonline\.net"),
    ("pinpoint", r"//([A-Za-z0-9\-]+)\.pinpointhq\.com"),
    ("dover", r"(?:app|jobs)\.dover\.com/(?:jobs/)?([A-Za-z0-9_\-]+)"),
    ("jobvite", r"jobs\.jobvite\.com/([A-Za-z0-9_\-]+)"),
    ("successfactors", r"\.sapsf\.com|\.jobs2web\.com|successfactors\.com"),
    ("gohire", r"widget\.gohire\.io|jobs\.gohire\.io"),
    ("other", r"recruitingbypaycor\.com|\.isolvedhire\.com|jobs\.gusto\.com|trinethire\.com|zohorecruit\.com|"
              r"\.careerplug\.com|\.applicantpro\.com|\.hirehive\.com|jobs\.polymer\.co|\.jobs\.personio\."),
]
# Readers the collector has (pipeline.collect.run.READERS).
# Boards a company's page still links or embeds but that no longer answer
# (410 Gone, 404, or a redirect to the vendor's home page), checked on the dates
# given in the registry-fixes files. A link to one is not a job board: the page
# is read as if it were not there. Keep in step with tools/apply_screening.py.
RETIRED_BOARDS = {
    ("bamboohr", "kiverdi"), ("bamboohr", "amberkinetics"),          # registry-fixes-06
    ("ashby", "Lime"), ("greenhouse", "navierboat"),                  # registry-fixes-11
    ("jazzhr", "calysta"), ("breezy", "mito-material-solutions"),     # registry-fixes-15
    ("lever", "sustaera"),
}


def live_systems(systems: list[dict]) -> list[dict]:
    return [s for s in systems if (s["type"], s["board"]) not in RETIRED_BOARDS]


READABLE = {"greenhouse", "lever", "ashby", "rippling", "workable", "bamboohr", "smartrecruiters", "recruitee",
            "jazzhr", "breezy", "teamtailor", "gem", "paylocity", "jobvite"}
NOT_TOKENS = {"embed", "v1", "boards", "api", "jobs", "job_board", "js", "www", "careers", "apply", "en-us", "app"}

AGGREGATORS = re.compile(r"indeed\.|linkedin\.com|ziprecruiter\.|glassdoor\.|builtin|wellfound\.|angel\.co|"
                         r"monster\.com|simplyhired\.|careerbuilder\.|dice\.com|climatebase\.org|idealist\.org", re.I)

_HREF = re.compile(r"""<a\b[^>]*?\bhref\s*=\s*["']([^"'#][^"']*)["'][^>]*>(.*?)</a>""", re.I | re.S)
_SRC = re.compile(r"""\b(?:src|href|action|data-src)\s*=\s*["']([^"']+)["']""", re.I)
_TAGS = re.compile(r"<[^>]+>")
_SCRIPTS = re.compile(r"<(script|style|noscript|template)\b.*?</\1>", re.I | re.S)
_LD = re.compile(r"""<script[^>]+type=["']application/ld\+json["'][^>]*>(.*?)</script>""", re.I | re.S)
_CAREERS = re.compile(r"career|jobs?\b|join[- ]?(us|our[- ]team|the[- ]team)|work[- ]with[- ]us|work[- ]here|"
                      r"open[- ](roles|positions)|openings|hiring|employment|opportunities", re.I)
_POSTING_PATH = re.compile(r"^/(?:[a-z]{2}(?:-[a-z]{2})?/)?(?:careers?|jobs?|positions?|openings?|opportunities|"
                           r"open-positions|current-openings|job-openings|career-opportunities|roles?|join-us|work-with-us|vacancies|employment)/[^/?#]+", re.I)
_NOT_POSTING = re.compile(r"^(?:apply|benefits?|culture|life|team|teams|faq|faqs|values|perks|students?|"
                          r"university|internships?|locations?|search|all|page|category|tag|feed|why-.*|"
                          r"our-.*|meet-.*|contact)$", re.I)
_NONE_OPEN = re.compile(r"no (?:current |open )?(?:openings|open positions|positions (?:available|open)|"
                        r"vacancies|job openings|opportunities (?:available|at this time))|"
                        r"not (?:currently )?hiring|(?:there are|we have) no (?:current |open )?(?:openings|positions|roles)|"
                        r"no (?:current|open) (?:roles|jobs)|check back (?:soon|later)|"
                        r"(?:do not|don.t) have any (?:current |open )?(?:openings|positions|roles|vacancies)|"
                        r"(?:job )?openings will be posted (?:on|here)|^no items found$|\bno items found\b|"
                        # Iontra: "Currently, our team is complete"; Ampt: "If no postings are listed, ..."
                        # (read only once the page has shown no postings).
                        r"our team is (?:currently )?complete|if no (?:postings|positions|openings|jobs) are listed", re.I)
# An empty jobs list with no words to say so: a jobs heading followed, before
# any other heading, by Elementor's empty loop grid (Prometheus Materials,
# "Available positions" over <div class="e-loop-nothing-found-message">).
_EMPTY_LISTING = re.compile(r"<h[1-6][^>]*>\s*((?:available|open|current) (?:positions|openings|roles|jobs)|"
                            r"(?:job )?openings|open roles)\s*</h[1-6]>(?:(?!<h[1-6]\b).){0,3000}?"
                            r"class=\"e-loop-nothing-found-message\"", re.I | re.S)


def empty_listing(page: str) -> str | None:
    """A note when the page's jobs list is there but empty (see _EMPTY_LISTING)."""
    match = _EMPTY_LISTING.search(page or "")
    return f"the '{' '.join(match.group(1).split())}' list is empty" if match else None
# A bot check or block page. "captcha" alone is not one: ordinary pages load
# reCAPTCHA for their contact forms, and site builders name it in their config.
_CHALLENGE_TITLE = re.compile(r"<title>\s*(?:just a moment|attention required|access denied|"
                              r"security check|are you a robot|please wait)", re.I)
_CHALLENGE = re.compile(r"cf-chl|challenge-platform|cf-browser-verification|verify you are human|"
                        r"are you a robot|access denied", re.I)
_SIGN_IN = re.compile(r"""<input[^>]+type=["']password["']""", re.I)
_JOB_WORDS = re.compile(r"job|position|career|opening|description|apply|engineer|technician|manager|"
                        r"scientist|operator|specialist|intern", re.I)
_HIRING = re.compile(r"we.re hiring|now hiring|careers?\b|job openings|open positions|join our team|current openings", re.I)
_JS_APP = re.compile(r"""id=["'](?:root|__next|app|__nuxt)["']|ng-app|data-reactroot|__NEXT_DATA__""", re.I)


# ------------------------------------------------------------------ helpers

def registrable(host: str) -> str:
    """The registered domain of a host (example.co.uk, example.com)."""
    labels = host.lower().strip(".").split(".")
    if labels and labels[0] == "www":
        labels = labels[1:]
    if len(labels) >= 3 and len(labels[-1]) == 2 and labels[-2] in ("co", "com", "org", "net", "ac", "gov"):
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def on_site(url: str, domain: str) -> bool:
    host = urlsplit(url).netloc.lower().split(":")[0]
    return host == domain or host.endswith("." + domain)


def visible_text(page: str) -> str:
    return " ".join(html_lib.unescape(_TAGS.sub(" ", _SCRIPTS.sub(" ", page))).split())


def links(page: str, base: str) -> list[tuple[str, str]]:
    """(absolute address, link text) for each <a href> on a page."""
    found = []
    for href, label in _HREF.findall(page):
        href = html_lib.unescape(href.strip())
        if href.lower().startswith(("mailto:", "tel:", "javascript:")):
            continue
        found.append((urljoin(base, href), " ".join(html_lib.unescape(_TAGS.sub(" ", label)).split())))
    return found


def ats_links(page: str) -> list[dict]:
    """Job-board systems the page links to or embeds, with board tokens."""
    text = html_lib.unescape(page).replace("\\/", "/")
    addresses = " ".join(_SRC.findall(text)) + " " + " ".join(re.findall(r"https?://[^\s\"'<>]+", text))
    addresses += " " + " ".join(re.findall(r'id="recruitee-careers"', text))      # widgets that name no address
    found, seen = [], set()
    for system, pattern in ATS_PATTERNS:
        for match in re.finditer(pattern, addresses):
            token = match.group(1) if match.groups() else None
            token = token.strip(".").split("?")[0] if token else None
            if token and token.lower() in NOT_TOKENS:
                continue
            if (system, token) not in seen:
                seen.add((system, token))
                found.append({"type": system, "board": token, "readable": system in READABLE})
    return found


def job_postings(page: str) -> int:
    """How many schema.org JobPosting objects the page's JSON-LD blocks hold."""
    count = 0
    for block in _LD.findall(page):
        try:
            data = json.loads(html_lib.unescape(block) if "&quot;" in block else block)
        except ValueError:
            continue
        stack = [data]
        while stack:
            item = stack.pop()
            if isinstance(item, list):
                stack.extend(item)
            elif isinstance(item, dict):
                kind = item.get("@type")
                if kind == "JobPosting" or (isinstance(kind, list) and "JobPosting" in kind):
                    count += 1
                stack.extend(value for key, value in item.items() if key in ("@graph", "itemListElement", "item"))
    return count


# Words that make a heading or an address read as one job. Whole words:
# "Engineer" is a title, "Engineering" (a team) is not.
_JOB_TITLE = re.compile(
    r"\b(?:engineer|technician|technologist|scientist|researcher|manager|director|designer|developer|programmer|"
    r"analyst|specialist|operator|mechanic|electrician|chemist|physicist|metallurgist|lead|head|chief|vp|president|"
    r"executive|associate|coordinator|intern|assistant|planner|buyer|accountant|controller|architect|machinist|"
    r"welder|fitter|fabricator|assembler|installer|inspector|tester|supervisor|foreman|superintendent|estimator|"
    r"scheduler|officer|administrator|representative|consultant|recruiter|generalist|clerk|driver|lineman|"
    r"millwright|advisor|strategist|counsel|paralegal|writer|editor)s?\b", re.I)
# A posting id in an address: a long number, or a UUID.
_POSTING_ID = re.compile(r"^(?:\d{4,}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$", re.I)


_JOB_TITLE_ONE = re.compile(_JOB_TITLE.pattern.replace(")s?\\b", ")\\b"), re.I)
_JOB_TITLE_MANY = re.compile(_JOB_TITLE.pattern.replace(")s?\\b", ")s\\b"), re.I)
_VACANCY = re.compile(r"/vacanc(?:y|ies)/[^/]+", re.I)
_SECTION_WORDS = re.compile(r"partner|board|team|leadership|management|about|contact|investor|news|blog|press|"
                            r"product|solution|service|customer|support|project|director(?:s|y)|executives?$", re.I)


def _shared_words(label: str, slug_words: str) -> set[str]:
    words = lambda text: {w for w in re.findall(r"[a-z]{4,}", text.lower())}
    return words(label) & words(slug_words)


def posting_links(page: str, base: str, domain: str) -> list[str]:
    """Links on a careers page that look like single postings on the company's own site."""
    careers_path = urlsplit(base).path.rstrip("/")
    found = []
    for url, label in links(page, base):
        if not on_site(url, domain) or AGGREGATORS.search(url):
            continue
        path = urlsplit(url).path.rstrip("/")
        if not path or path == careers_path or path.lower().endswith((".pdf", ".jpg", ".png")):
            continue
        last = path.rsplit("/", 1)[-1]
        under_careers = careers_path and path.startswith(careers_path + "/") and path.count("/") > careers_path.count("/")
        # One job, not a careers section ("who-we-are", "life-at-acme", "jobs-us"): the address or the
        # link names a job title, or the address ends in a posting id.
        words = last.replace("-", " ").replace("_", " ")
        reads_as_job = bool(_JOB_TITLE.search(words) or _JOB_TITLE.search(label or "") or _POSTING_ID.match(last)
                            or _POSTING_ID.match(path.rsplit("/", 2)[-2] if path.count("/") >= 2 else ""))
        # "/vacancy/<slug>" anywhere in the path (AMSC, NWL's /blog/vacancy/), and a
        # root-level slug whose link names a job title the slug repeats
        # ("/vp-of-sales-au", "/open-roles-lab-manager").
        vacancy = bool(_VACANCY.search(path))
        # Singular only at the root: "Fabricator" is a role, "Fabricators" an audience
        # (LuxWall's "EnThermal Plus Fabricators" page).
        # A job title's link is short; a menu blurb ("LuxWall Certified Fabricator
        # ... Become a certified fabricator") is not.
        root_job = (path.count("/") == 1 and len(label or "") <= 80 and bool(_JOB_TITLE_ONE.search(label or ""))
                    and not _SECTION_WORDS.search(last) and not _JOB_TITLE_MANY.search(label or "")
                    and not _JOB_TITLE_MANY.search(words) and bool(_shared_words(label or "", words)))
        if (under_careers or _POSTING_PATH.match(path) or vacancy or root_job) and not _NOT_POSTING.match(last) and reads_as_job:
            if url.split("#")[0] not in found:
                found.append(url.split("#")[0])
    return found


def careers_candidates(page: str, base: str, domain: str) -> list[str]:
    """The best careers links on a home page, on the company's own site."""
    scored = []
    for url, label in links(page, base):
        if not on_site(url, domain) or AGGREGATORS.search(url):
            continue
        path = urlsplit(url).path.lower()
        score = (2 if _CAREERS.search(path) else 0) + (1 if _CAREERS.search(label) else 0)
        if score and url.split("#")[0].rstrip("/") != base.split("#")[0].rstrip("/"):
            scored.append((-score, len(path), url.split("#")[0]))
    ordered = []
    for _score, _length, url in sorted(scored):
        if url not in ordered:
            ordered.append(url)
    return ordered[:2]


_LINKEDIN_JOBS = re.compile(r"linkedin\.com/(?:jobs/view/|company/[^/?#\s]+/jobs)", re.I)


def linkedin_jobs_links(page: str, base: str) -> list[str]:
    """Links to LinkedIn job pages, or to a company's LinkedIn jobs, labelled as
    jobs; a plain LinkedIn icon is not one."""
    found = []
    for url, label in links(page, base):
        if "linkedin.com" not in url.lower():
            continue
        if _LINKEDIN_JOBS.search(url) or (re.search(r"linkedin\.com/company/", url, re.I) and _JOB_WORDS.search(label or "")):
            if url not in found:
                found.append(url)
    return found


def refusal(page: str) -> str | None:
    head = page[:20000]
    if _CHALLENGE_TITLE.search(head) or (_CHALLENGE.search(head) and len(visible_text(page)) < 1500):
        return "bot check"
    if _SIGN_IN.search(head) and len(visible_text(page)) < 2000:
        return "sign-in page"
    return None


def classify_careers_page(page: str, url: str, domain: str) -> dict:
    """What a careers page shows, without reading any posting."""
    systems = live_systems(ats_links(page))
    if systems:
        return {"outcome": "ats-found", "method": "ats-link", "ats": systems}
    blocks = job_postings(page)
    postings = posting_links(page, url, domain)
    pdfs = [link for link, label in links(page, url) if link.lower().split("?")[0].endswith(".pdf")
            and _JOB_WORDS.search(link + " " + label)]
    text = visible_text(page)
    if blocks:
        return {"outcome": "ok", "method": "jobposting-blocks", "postings": blocks, "posting_links": len(postings)}
    if postings:
        return {"outcome": "ok", "method": "plain-listing", "postings": len(postings), "examples": postings[:3]}
    linkedin = linkedin_jobs_links(page, url)
    if linkedin:
        # The careers reader follows these (decision 12a); the probe does not ask LinkedIn.
        return {"outcome": "unclear", "method": "linkedin", "postings": 0,
                "note": f"careers page points to LinkedIn for its jobs ({len(linkedin)} links); the careers reader follows them"}
    if pdfs:
        return {"outcome": "unreadable", "method": "pdf", "postings": len(pdfs), "note": "postings given as PDFs"}
    if _NONE_OPEN.search(text):
        return {"outcome": "none-open", "method": "notice", "postings": 0,
                "note": _NONE_OPEN.search(text).group(0)[:80]}
    if empty_listing(page):
        return {"outcome": "none-open", "method": "empty-list", "postings": 0, "note": empty_listing(page)}
    if len(text) < 600:
        # Almost no text and nothing to read: built by JavaScript, or empty.
        return {"outcome": "unreadable", "method": "javascript", "postings": 0,
                "note": "page text is built by JavaScript" if _JS_APP.search(page)
                else f"careers page has almost no text ({len(text)} characters); built by JavaScript or empty"}
    return {"outcome": "unclear", "method": None, "postings": 0,
            "note": f"careers page read ({len(text)} characters of text); no postings, links or notice found"}


# -------------------------------------------------------------------- probe

CAP = "request cap reached before a careers page was read"
COMPANY_BUDGET = 300.0     # seconds per company; a site that holds connections must not hold the probe
clock = time.monotonic


class Budget(Exception):
    """No more requests for this company: the request cap, a timeout, or the time budget."""

    def __init__(self, why: str = CAP) -> None:
        super().__init__(why)
        self.why = why


class SavedPages:
    """Pages saved by an earlier probe (RecordingFetcher.get_page). A page that
    was not saved failed in that run; it is reported as not found, unless
    `live` is given, in which case it is fetched now (and saved)."""

    def __init__(self, directory: Path, live=None) -> None:
        self._replay = ReplayFetcher(directory)
        self._live = live
        self.requests = 0
        self.live_requests = 0

    def get_page(self, url, stay_within, max_redirects=2, max_bytes=1_000_000):
        try:
            answer = self._replay.get_page(url)
            self.requests += 1
            return answer
        except FetchError:
            if self._live is None:
                self.requests += 1
                raise FetchError("HTTP 404: not saved in the earlier pass (it failed then)") from None
        before = self._live.requests
        try:
            return self._live.get_page(url, stay_within, max_redirects, max_bytes)
        finally:
            self.requests += self._live.requests - before
            self.live_requests += self._live.requests - before

    def close(self) -> None:
        if self._live is not None:
            self._live.close()


def probe(company: dict, fetcher, obey_robots: bool = True) -> dict:
    """One company. With obey_robots false (PLAN.md decision 12b), pages that
    robots.txt disallows are read anyway and the entry's 'robots' says which."""
    website = company["website"]
    parts = urlsplit(website)
    home = f"https://{parts.netloc}{parts.path or '/'}"
    domain = registrable(parts.netloc)
    entry = {"company_id": company["id"], "name": company["name"], "website": website, "careers_url": None,
             "outcome": None, "method": None, "postings": 0, "ats": None, "requests": 0, "note": None}
    start = fetcher.requests
    stay = lambda url: on_site(url, domain)

    started = clock()

    def get(url: str) -> tuple[str, str]:
        if clock() - started > COMPANY_BUDGET:
            raise Budget(f"stopped after the {COMPANY_BUDGET:g} s time budget")
        if entry["page_requests"] >= MAX_PAGES or fetcher.requests - start >= MAX_HOPS:
            raise Budget()
        entry["page_requests"] += 1
        try:
            return fetcher.get_page(url, stay, max_redirects=max(0, min(2, MAX_HOPS - (fetcher.requests - start) - 1)))
        except FetchError as error:
            if is_timeout(error):
                # The first timeout ends this company's probe (see careers.read).
                raise Budget(f"stopped after a timeout on {urlsplit(url).path or '/'}") from None
            raise

    entry["page_requests"] = 0
    robots = RobotFileParser()
    try:
        try:
            _final, text = get(f"https://{parts.netloc}/robots.txt")
            robots.parse(text.splitlines())
        except Blocked:
            raise
        except FetchError as error:
            # No robots.txt (404 or 410, or sent elsewhere) means nothing is
            # disallowed. Any other failure: the rules are unknown, so stop.
            if not str(error).startswith(("HTTP 404", "HTTP 410", "HTTP 30")):
                if obey_robots:
                    return _done(entry, start, fetcher, "error", note=f"robots.txt could not be read: {str(error)[:100]}")
                entry["robots"] = f"robots.txt could not be read ({str(error)[:60]}); read under decision 12b"
            robots.parse([])
        if not robots.can_fetch("*", home):
            if obey_robots:
                return _done(entry, start, fetcher, "robots-disallowed", note="robots.txt disallows the home page")
            entry["robots"] = "robots.txt disallows the home page; read under decision 12b"

        final_home, page = get(home)
        why = refusal(page)
        if why:
            return _done(entry, start, fetcher, "blocked", note=why)
        systems = ats_links(page)
        candidates = careers_candidates(page, final_home, domain)
        if systems and not candidates:
            return _done(entry, start, fetcher, "ats-found", method="ats-link", ats=systems, note="linked from the home page")
        home_text = visible_text(page)
        if not candidates and _HIRING.search(home_text):
            # A hiring section on the home page itself (one opening, a PDF).
            result = classify_careers_page(page, final_home, domain)
            if result["outcome"] in ("ok", "ats-found", "none-open", "unreadable"):
                return _done(entry, start, fetcher, careers_url=final_home,
                             **{**result, "note": result.get("note") or "postings on the home page"})
        if not candidates:
            root = f"https://{urlsplit(final_home).netloc}"
            candidates = [f"{root}/careers", f"{root}/jobs"]
            entry["note"] = "no careers link on the home page; tried /careers and /jobs"

        found_page = False
        for candidate in candidates:
            if not robots.can_fetch("*", candidate):
                if obey_robots:
                    entry["note"] = f"robots.txt disallows {urlsplit(candidate).path}"
                    continue
                entry["robots"] = f"robots.txt disallows {urlsplit(candidate).path}; read under decision 12b"
            try:
                final, careers = get(candidate)
            except Blocked:
                raise
            except Budget as stop:
                if stop.why != CAP:
                    raise                      # a timeout or the time budget ends the company
                break
            except FetchError as error:
                entry["note"] = f"{urlsplit(candidate).path}: {str(error)[:80]}"
                continue
            why = refusal(careers)
            if why:
                return _done(entry, start, fetcher, "blocked", note=why, careers_url=final)
            found_page = True
            result = classify_careers_page(careers, final, domain)
            if result["outcome"] == "unclear" and systems:
                result = {"outcome": "ats-found", "method": "ats-link", "ats": systems, "note": "linked from the home page"}
            if result["outcome"] in ("ok", "ats-found", "none-open", "unreadable") or candidate == candidates[-1]:
                return _done(entry, start, fetcher, careers_url=final, **result)
        if systems:
            return _done(entry, start, fetcher, "ats-found", method="ats-link", ats=systems, note="linked from the home page")
        if found_page:
            return _done(entry, start, fetcher, "unclear", note=entry["note"])
        disallowed = entry["note"] and entry["note"].startswith("robots.txt disallows")
        if disallowed:
            return _done(entry, start, fetcher, "robots-disallowed", note=entry["note"])
        if len(home_text) < 300 and len(links(page, final_home)) < 10:
            return _done(entry, start, fetcher, "unreadable", method="javascript",
                         note=f"home page has almost no text or links ({len(home_text)} characters); built by JavaScript or empty")
        return _done(entry, start, fetcher, "no-careers-page", note=entry["note"])
    except Blocked as error:
        return _done(entry, start, fetcher, "blocked", note=str(error)[:120])
    except Budget as stop:
        if stop.why != CAP:
            return _done(entry, start, fetcher, "error", note=stop.why)
        return _done(entry, start, fetcher, "unclear", note=CAP)
    except FetchError as error:
        return _done(entry, start, fetcher, "error", note=str(error)[:160])


def _done(entry: dict, start: int, fetcher, outcome: str, **values) -> dict:
    entry.update(values)
    entry["outcome"] = outcome
    entry["requests"] = fetcher.requests - start
    entry.pop("page_requests", None)
    return entry


def companies_to_probe(registry: list[dict], established: bool = False) -> list[dict]:
    """Companies with a website and no known job-board system: listed ones, or
    with `established`, every core or enabling company (PLAN.md decision 14)."""
    def wanted(company):
        if established:
            return company["climate"]["tier"] in ("core", "enabling")
        return is_listed(company) and company_type(company) == "startup"
    return [company for company in registry
            if wanted(company) and company["ats"]["type"] == "unknown" and company.get("website")]


def summary(entries: list[dict]) -> dict:
    outcomes = Counter(entry["outcome"] for entry in entries)
    ok = [entry for entry in entries if entry["outcome"] == "ok"]
    return {
        "companies": len(entries),
        "requests": sum(entry["requests"] for entry in entries),
        "outcomes": dict(outcomes.most_common()),
        "ok_by_method": dict(Counter(entry["method"] for entry in ok)),
        "postings_seen": {method: sum(e["postings"] for e in ok if e["method"] == method) for method in {e["method"] for e in ok}},
        "ats_found": dict(Counter(system["type"] for entry in entries if entry["outcome"] == "ats-found"
                                  for system in entry["ats"])),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m pipeline.collect.probe_careers", description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "screening" / "careers-probe-01.yml")
    parser.add_argument("--companies", type=Path, default=ROOT / "companies.yml")
    parser.add_argument("--record", type=Path, metavar="DIR", help="also save every page (data/fixtures-live is ignored by git)")
    parser.add_argument("--replay", type=Path, metavar="DIR",
                        help="read pages saved by an earlier --record run; a page not saved counts as not found")
    parser.add_argument("--live-for", action="append", default=[], metavar="ID",
                        help="with --replay: fetch (and save) this company's pages that were not saved; may be repeated")
    parser.add_argument("--keep", action="append", default=[], metavar="ID",
                        help="with --replay: keep this company's entry from the existing --out file unchanged")
    parser.add_argument("--only", action="append", help="probe only this company id (may be repeated)")
    parser.add_argument("--name", default="careers-probe-01", help="the probe's name, written into the file")
    parser.add_argument("--established", action="store_true",
                        help="probe every core or enabling company, established ones too (decision 14)")
    parser.add_argument("--read-disallowed", action="store_true",
                        help="read pages robots.txt disallows, noting it (decision 12b)")
    parser.add_argument("--skip-probed", action="store_true",
                        help="leave out companies already in another data/screening/careers-probe-*.yml")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")

    targets = companies_to_probe(load_yaml(args.companies)["companies"], established=args.established)
    if args.skip_probed:
        probed = {entry["company_id"] for path in sorted((ROOT / "data" / "screening").glob("careers-probe-*.yml"))
                  if path.resolve() != args.out.resolve() for entry in load_yaml(path).get("companies", [])}
        targets = [company for company in targets if company["id"] not in probed]
    if args.only:
        targets = [company for company in targets if company["id"] in args.only]
    previous = {}
    if args.keep and args.out.exists():
        previous = {entry["company_id"]: entry for entry in load_yaml(args.out)["companies"]}
    live = None
    if args.replay:
        fetcher = SavedPages(args.replay)
        if args.live_for:
            live = SavedPages(args.replay, live=RecordingFetcher(args.replay, min_interval=PAGE_INTERVAL))
    elif args.record:
        fetcher = RecordingFetcher(args.record, min_interval=PAGE_INTERVAL)
    else:
        fetcher = Fetcher(min_interval=PAGE_INTERVAL)
    entries = []
    started = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        for company in targets:
            if company["id"] in previous and company["id"] in args.keep:
                entry = previous[company["id"]]
            else:
                entry = probe(company, live if live is not None and company["id"] in args.live_for else fetcher,
                              obey_robots=not args.read_disallowed)
            entries.append(entry)
            print(f"{entry['outcome']:<17} {company['id']}: {entry['note'] or entry['method'] or ''} "
                  f"({entry['postings']} postings, {entry['requests']} requests)")
    finally:
        fetcher.close()
        if live is not None:
            live.close()
            print(f"{live.live_requests} live requests for pages the earlier pass had not saved")
    document = {
        "probe": args.name,
        "made_by": "A1 collector, python -m pipeline.collect.probe_careers",
        "started_at": started,
        "rules": ("robots.txt read for '*' and disallowed pages read anyway, noted per company (decision 12b); "
                  if args.read_disallowed else "robots.txt obeyed for '*'; ") + "at most 4 page requests and 6 requests with redirects per company; "
                 "3 s between requests to a host; GET only; no JavaScript, no forms; stop on 403, 429, sign-in or bot check",
        "outcomes": OUTCOMES,
        "summary": summary(entries),
        "companies": entries,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline="\n") as handle:
        yaml.safe_dump(document, handle, sort_keys=False, allow_unicode=True, width=110)
    print(json.dumps(document["summary"], indent=1))
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
