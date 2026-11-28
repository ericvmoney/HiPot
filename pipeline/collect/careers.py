"""Careers-page reader: companies' own careers pages (ATS type 'other').

The registry's board for such a company is the address of its careers page.
The reader asks robots.txt, then the careers page, and works out what the page
offers, in this order:

  1. a link to a job-board system: nothing is read here; the run entry says
     'ats-found' and names the system and token, for the registry;
  2. schema.org JobPosting blocks on the page;
  3. links to posting pages on the company's own site (a plain listing): each
     posting page is read, for its JobPosting block or else its title and text;
  4. links to the company's jobs on LinkedIn, when the page sends candidates
     there to apply (PLAN.md decision 12). Only public job pages
     (linkedin.com/jobs/view/<id>) are read, at least 10 s apart, at most
     LINKEDIN_CAP a run. Any sign-in wall, CAPTCHA or bot check stops LinkedIn
     for the rest of the run and the company is 'blocked'.

Other aggregators (Indeed, ZipRecruiter, Glassdoor and the like) are never
followed, and a posting is kept only when its address is on the company's own
domain or, for case 4, on linkedin.com.

robots.txt is read but not taken at face value (decision 12): when it
disallows the careers page, the page is still read, but at most once every
ROBOTS_DISALLOWED_EVERY days per site. In between, the postings from the last
read are carried forward with their real last-seen time, and the run entry
says so. A state file (data/state/careers.json) remembers those reads.

Every other rule of polite fetching holds: at least 3 s between requests to a
host (10 s for LinkedIn), at most MAX_REQUESTS per company, GET only, no
JavaScript, no forms, and a stop on any 403, 429, sign-in page or bot check.

Run statuses (schema/raw-jobs-file.schema.json): ok, partial (a cap was hit or
posting pages failed), none-open, unreadable (JavaScript-built list, PDFs only,
or nothing recognisable), no-careers-page (the page is gone), ats-found,
blocked, skipped.
"""
from __future__ import annotations

import hashlib
import html as html_lib
import json
import re
from dataclasses import dataclass, field
import time
from datetime import datetime, timedelta, timezone
from typing import Callable
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

from pipeline.collect import normalize
from pipeline.collect.fetch import Blocked, FetchError, is_timeout
from pipeline.collect.locations import parse_location, structured_location
from pipeline.collect.probe_careers import (_JS_APP, _LD, _NONE_OPEN, AGGREGATORS, _JOB_TITLE, _JOB_WORDS, ats_links, links,
                                            empty_listing, live_systems,
                                            on_site, posting_links, refusal, registrable, visible_text)
from pipeline.collect.text import html_to_text
from pipeline.io import ROOT

STATE_PATH = ROOT / "data" / "state" / "careers.json"
MAX_REQUESTS = 25                 # per company per run, robots.txt included
COMPANY_BUDGET = 300.0            # seconds of reading per company per run; then it stops, keeping what it has
LINKEDIN_CAP = 30                 # LinkedIn requests per run, all companies together
ROBOTS_DISALLOWED_EVERY = 7       # days between reads of a site whose robots.txt disallows the page
MIN_DESCRIPTION = 200

_LINKEDIN_HOST = re.compile(r"(^|\.)linkedin\.com$", re.I)
_LINKEDIN_JOB = re.compile(r"https?://(?:[a-z]{2,3}\.)?(?:www\.)?linkedin\.com/jobs/view/(?:[^/?#]*-)?(\d{6,})", re.I)
_LINKEDIN_COMPANY_JOBS = re.compile(r"https?://(?:[a-z]{2,3}\.)?(?:www\.)?linkedin\.com/company/([^/?#]+)/jobs", re.I)
_LINKEDIN_WALL = re.compile(r"/authwall|/login|/signup|/checkpoint|/uas/", re.I)
_H1 = re.compile(r"<h1\b[^>]*>(.*?)</h1>", re.I | re.S)
_TITLE = re.compile(r"<title\b[^>]*>(.*?)</title>", re.I | re.S)
_MAIN = re.compile(r"<(main|article)\b[^>]*>(.*?)</\1>", re.I | re.S)
_CHROME = re.compile(r"<(nav|header|footer|aside|form)\b.*?</\1>", re.I | re.S)
_LOCATION_LINE = re.compile(r"\b(?i:location)\s*[:\-]\s*([A-Z][A-Za-z .'-]+,\s*[A-Z]{2}\b|[A-Z][A-Za-z .'-]+,\s*[A-Z][a-z]+)")
_PERIOD = {"YEAR": "year", "ANNUAL": "year", "HOUR": "hour", "HOURLY": "hour"}
_EMPLOYMENT = {"FULL_TIME": "full-time", "PART_TIME": "part-time", "CONTRACTOR": "contract", "TEMPORARY": "contract",
               "INTERN": "intern", "PER_DIEM": "contract"}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ------------------------------------------------------------------- state

@dataclass
class Context:
    """What the reader keeps across companies in a run and across runs."""
    path: Path | None = None
    sites: dict = field(default_factory=dict)          # domain -> {"read_at": iso, "drafts": [...]}
    linkedin_requests: int = 0
    linkedin_blocked: str | None = None
    now: datetime = field(default_factory=utc_now)
    budget: float = COMPANY_BUDGET                       # seconds of reading per company
    clock: Callable[[], float] = time.monotonic

    @classmethod
    def load(cls, path: Path = STATE_PATH) -> "Context":
        sites = {}
        if path.exists():
            with open(path, encoding="utf-8") as handle:
                sites = json.load(handle).get("sites", {})
        return cls(path=path, sites=sites)

    def save(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        with open(temporary, "w", encoding="utf-8", newline="\n") as handle:
            json.dump({"state_version": 0, "sites": self.sites}, handle, ensure_ascii=False, indent=1)
        temporary.replace(self.path)


# --------------------------------------------------------- page helpers

def job_posting_items(page: str) -> list[dict]:
    """The schema.org JobPosting objects in a page's JSON-LD blocks."""
    found = []
    for block in _LD.findall(page or ""):
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
                    found.append(item)
                stack.extend(value for key, value in item.items() if key in ("@graph", "itemListElement", "item"))
    return found


def _text_of(markup) -> str:
    return " ".join(html_lib.unescape(re.sub(r"<[^>]+>", " ", markup or "")).split())


def _place_from_ld(item: dict) -> list[dict]:
    places = item.get("jobLocation") or []
    places = places if isinstance(places, list) else [places]
    found = []
    for place in places:
        address = (place or {}).get("address") if isinstance(place, dict) else None
        if isinstance(address, str):
            found.append(parse_location(address))
            continue
        if not isinstance(address, dict):
            continue
        city, region = address.get("addressLocality"), address.get("addressRegion")
        country = address.get("addressCountry")
        country = country.get("name") if isinstance(country, dict) else country
        parts = [part for part in (city, region, country) if isinstance(part, str) and part.strip()]
        if parts:
            found.append(structured_location(", ".join(parts), city, region, country))
    if not found and str(item.get("jobLocationType", "")).upper() == "TELECOMMUTE":
        found.append(parse_location("Remote"))
    return found


def _pay_from_ld(item: dict) -> dict | None:
    salary = item.get("baseSalary")
    if not isinstance(salary, dict):
        return None
    value = salary.get("value") if isinstance(salary.get("value"), dict) else salary
    low, high = value.get("minValue"), value.get("maxValue")
    unit = str(value.get("unitText") or salary.get("unitText") or "").upper()
    number = lambda v: float(v) if isinstance(v, str) and re.fullmatch(r"\d+(\.\d+)?", v) else v
    return normalize.pay(number(low), number(high), salary.get("currency"), _PERIOD.get(unit))


def _employment_from_ld(item: dict, title: str) -> str:
    kinds = item.get("employmentType")
    for kind in (kinds if isinstance(kinds, list) else [kinds]):
        if isinstance(kind, str) and kind.upper() in _EMPLOYMENT:
            return _EMPLOYMENT[kind.upper()]
    return normalize.employment_from_title(title)


def _expired(item: dict, today: datetime) -> bool:
    through = normalize.iso_date(item.get("validThrough")) if isinstance(item.get("validThrough"), str) else None
    return bool(through) and through < today.date().isoformat()


def _posting_id(url: str) -> str:
    """The posting address's path (and query, when it identifies the posting)."""
    parts = urlsplit(url)
    key = parts.path.strip("/") + (f"?{parts.query}" if parts.query else "")
    return key or hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]


def draft_from_ld(item: dict, url: str, today: datetime) -> dict | None:
    title = _text_of(item.get("title") or item.get("name"))
    if not title or _expired(item, today):
        return None
    posting_url = item.get("url") if isinstance(item.get("url"), str) and item["url"].startswith("https://") else url
    identifier = item.get("identifier")
    if isinstance(identifier, dict):
        identifier = identifier.get("value")
    if posting_url != url:
        posting = _posting_id(posting_url)
    else:
        # Several postings on one page: told apart by identifier, else by title.
        tail = str(identifier) if identifier else re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:80]
        posting = f"{_posting_id(url)}#{tail}"
    department = item.get("occupationalCategory") if isinstance(item.get("occupationalCategory"), str) else None
    return normalize.draft(
        posting_id=posting,
        title=title,
        url=posting_url,
        locations=_place_from_ld(item),
        workplace="remote" if str(item.get("jobLocationType", "")).upper() == "TELECOMMUTE" else None,
        employment=_employment_from_ld(item, title),
        pay=_pay_from_ld(item),
        posted_date=normalize.iso_date(item.get("datePosted")) if isinstance(item.get("datePosted"), str) else None,
        department=normalize.department(department),
        description_text=html_to_text(item.get("description")),
    )


def draft_from_page(page: str, url: str, today: datetime) -> dict | None:
    """A posting page without a JobPosting block: its heading and main text."""
    items = job_posting_items(page)
    if items:
        made = draft_from_ld(items[0], url, today)
        if made and made["url"] == url:
            made["posting_id"] = _posting_id(url)      # the page is the posting
        return made
    micro = _microdata(page)
    title = micro.get("title") or _page_title(page)
    text = micro.get("description") or ""
    if len(text) < MIN_DESCRIPTION:
        body = _MAIN.search(page)
        text = html_to_text(_CHROME.sub(" ", body.group(2))) if body else ""
    if len(text) < MIN_DESCRIPTION:
        # Some sites keep the posting outside <main>: the whole page, less its chrome.
        text = html_to_text(_CHROME.sub(" ", page))
    if not title or len(text) < MIN_DESCRIPTION:
        return None
    where = micro.get("location") or (_LOCATION_LINE.search(text).group(1) if _LOCATION_LINE.search(text) else None)
    return normalize.draft(
        posting_id=_posting_id(url),
        title=title,
        url=url,
        locations=[parse_location(where)] if where else [],
        workplace=None,
        employment=normalize.employment_from_title(title),
        pay=None,
        posted_date=micro.get("date"),
        department=None,
        description_text=text,
    )


# A page's first heading that names the section, not the posting.
_GENERIC_HEADING = re.compile(r"^(?:current |our |open |job )?(?:openings?|open (?:positions|roles)|positions|careers?|"
                              r"jobs|join (?:us|our team)|opportunities|vacancies|job details)$", re.I)


def _page_title(page: str) -> str:
    """The posting's title: a first-level heading that reads as a job title,
    else the page's <title> when it does ("VP of Sales - AU — Luminous"), else
    the first heading that is not a section name ("ABOUT LUMINOUS" is one)."""
    headings = [_text_of(m.group(2)) for m in re.finditer(r"<h([12])\b[^>]*>(.*?)</h\1>", page, re.I | re.S)]
    headings = [text for text in headings if text and not _GENERIC_HEADING.match(text)]
    for text in headings:
        if _JOB_TITLE.search(text) and len(text) <= 100:
            return text
    title = _TITLE.search(page)
    if title:
        whole = _text_of(title.group(1))
        # The company name follows a pipe or a long dash; a hyphen inside the title stays.
        named = re.split(r"\s+[|–—]\s+", whole)[0].strip()
        if named == whole:
            named = re.split(r"\s+-\s+", whole)[0].strip()
        if _JOB_TITLE.search(named):
            return named
    return headings[0] if headings else ""


_ITEMPROP = re.compile(r"<(\w+)\b[^>]*\bitemprop=\"(title|description|datePosted)\"[^>]*>", re.I)


def _microdata(page: str) -> dict:
    """Fields a posting page marks with schema.org microdata (SAP SuccessFactors
    career sites do): itemprop title, description and datePosted, and the
    jobGeoLocation text. The description runs to the end of its element's
    enclosing block, which is enough for these pages."""
    found = {}
    for match in _ITEMPROP.finditer(page):
        tag, prop = match.group(1), match.group(2)
        if prop == "datePosted":
            content = re.search(r'content="([^"]+)"', match.group(0))
            found.setdefault("date", normalize.iso_date(content.group(1)) if content else None)
            continue
        close = page.find(f"</{tag}>", match.end())
        if prop == "description":
            # The description holds nested elements of the same tag; read to the
            # next field marker or the end of the page's main block.
            nxt = re.search(r'data-careersite-propertyid="(?!description)|</main>|<footer\b', page[match.end():])
            close = match.end() + nxt.start() if nxt else len(page)
        value = page[match.end():close] if close > 0 else ""
        found.setdefault(prop, _text_of(value) if prop == "title" else html_to_text(value))
    geo = re.search(r'class="jobGeoLocation"[^>]*>([^<]+)<', page)
    if geo and geo.group(1).strip():
        found["location"] = geo.group(1).strip()
    return {key: value for key, value in found.items() if value}


def linkedin_targets(page: str, base: str) -> tuple[list[str], list[str]]:
    """LinkedIn job pages, and LinkedIn company-jobs pages, that a careers page
    sends candidates to. A plain LinkedIn profile link (a footer icon) is not one."""
    jobs, company_pages = [], []
    for url, label in links(page, base):
        job = _LINKEDIN_JOB.match(url)
        if job:
            canonical = f"https://www.linkedin.com/jobs/view/{job.group(1)}"
            if canonical not in jobs:
                jobs.append(canonical)
            continue
        company = _LINKEDIN_COMPANY_JOBS.match(url)
        if company or (re.search(r"linkedin\.com/company/", url, re.I) and _JOB_WORDS.search(label or "")):
            slug = company.group(1) if company else url.rstrip("/").split("/company/")[1].split("/")[0]
            target = f"https://www.linkedin.com/company/{slug}/jobs"
            if target not in company_pages:
                company_pages.append(target)
    return jobs, company_pages


# ------------------------------------------------------------------- reader

class _Cap(Exception):
    """No more requests for this company: the request cap, a timeout, or the time budget."""

    def __init__(self, why: str = "request cap reached") -> None:
        super().__init__(why)
        self.why = why


def _canonical(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit(("https", parts.netloc.lower(), parts.path or "/", parts.query, ""))


def read(board: str, fetcher, context: Context | None = None) -> normalize.ReadResult:
    context = context or Context()
    careers_url = _canonical(board)
    host = urlsplit(careers_url).netloc
    if AGGREGATORS.search(host):
        # Roles enter only from the company's own pages, never an aggregator's.
        return normalize.ReadResult(status="skipped", note=f"board {careers_url} is an aggregator's page; not read")
    domain = registrable(host)
    stay = lambda url: on_site(url, domain)
    used = [0]
    started = context.clock()
    stopped: list[str] = []

    def get(url: str, within=stay) -> tuple[str, str]:
        # A site that holds connections makes every request wait out the
        # deadline (a full run once stalled on one for 40 minutes), so a
        # company's first timeout ends its reading, and so does its time budget.
        if stopped:
            raise _Cap(stopped[0])
        if context.clock() - started > context.budget:
            stopped.append(f"stopped after the {context.budget:g} s time budget")
            raise _Cap(stopped[0])
        if used[0] >= MAX_REQUESTS:
            raise _Cap()
        used[0] += 1
        before = fetcher.requests
        try:
            return fetcher.get_page(url, within, max_redirects=2)
        except FetchError as error:
            if is_timeout(error):
                stopped.append("stopped after a timeout")
            raise
        finally:
            used[0] += max(0, fetcher.requests - before - 1)     # redirect hops count too

    # robots.txt: read, but not taken at face value.
    robots = RobotFileParser()
    try:
        _final, text = get(f"https://{host}/robots.txt")
        robots.parse(text.splitlines())
    except FetchError as error:
        if isinstance(error, Blocked):
            raise
        robots.parse([])
    disallowed = not robots.can_fetch("*", careers_url)
    site = context.sites.get(domain)
    if disallowed and site and site.get("read_at"):
        last = datetime.fromisoformat(site["read_at"].replace("Z", "+00:00"))
        if context.now - last < timedelta(days=ROBOTS_DISALLOWED_EVERY):
            drafts = site.get("drafts") or []
            return normalize.ReadResult(
                drafts=drafts, status=site.get("status", "ok"), seen_at=site["read_at"],
                note=(f"robots.txt disallows the careers page: read at most every {ROBOTS_DISALLOWED_EVERY} days; "
                      f"not read this run, {len(drafts)} postings carried from {site['read_at'][:10]}"))

    result = _read_page(careers_url, get, stay, domain, context)
    if disallowed:
        result.note = "; ".join(part for part in (
            f"robots.txt disallows the careers page: read on the {ROBOTS_DISALLOWED_EVERY}-day schedule", result.note) if part)
        stamp = context.now.strftime("%Y-%m-%dT%H:%M:%SZ")
        if result.status in ("ok", "partial", "none-open"):
            context.sites[domain] = {"read_at": stamp, "status": result.status, "drafts": result.drafts}
        result.seen_at = None
    else:
        context.sites.pop(domain, None)
    return result


def _read_page(careers_url: str, get, stay, domain: str, context: Context) -> normalize.ReadResult:
    try:
        final, page = get(careers_url)
    except FetchError as error:
        if isinstance(error, Blocked):
            raise
        if str(error).startswith(("HTTP 404", "HTTP 410")):
            return normalize.ReadResult(status="no-careers-page", note=f"{careers_url}: {str(error)[:120]}")
        raise
    except _Cap as cap:
        # Nothing read yet: a stop before the careers page is an error, not a partial read.
        status = "partial" if cap.why == "request cap reached" else "error"
        return normalize.ReadResult(status=status, note=f"{cap.why}; the careers page was not read")
    why = refusal(page)
    if why:
        raise Blocked(f"{why} on {urlsplit(final).netloc}")

    systems = ats_links(page)
    systems = live_systems(systems)          # a retired board's link is not a board
    readable = [s for s in systems if s["readable"]]
    if readable:
        named = ", ".join(f"{s['type']}:{s['board'] or '?'}" for s in readable)
        return normalize.ReadResult(status="ats-found", note=f"careers page links to {named}")
    # A system the collector has no reader for (SuccessFactors, GoHire...): the
    # page itself may still list the postings, so it is read as usual.
    unread = ", ".join(sorted({s["type"] for s in systems}))

    today = context.now
    drafts: list[dict] = []
    for item in job_posting_items(page):
        made = draft_from_ld(item, final, today)
        if made and (on_site(made["url"], domain)):
            drafts.append(made)
    if drafts:
        return normalize.ReadResult(drafts=_unique(drafts), note="read from JobPosting blocks")

    postings = posting_links(page, final, domain)
    if postings:
        failed, capped = 0, None
        for url in postings:
            try:
                landed, body = get(url)
            except _Cap as cap:
                capped = cap.why
                break
            except FetchError as error:
                if isinstance(error, Blocked):
                    raise
                failed += 1
                continue
            if refusal(body):
                raise Blocked(f"{refusal(body)} on {urlsplit(landed).netloc}")
            made = draft_from_page(body, landed, today)
            if made and on_site(made["url"], domain):
                drafts.append(made)
            else:
                failed += 1
        drafts = _unique(drafts)
        if capped or failed:
            missing = len(postings) - len(drafts)
            why = capped or f"{failed} posting pages could not be read"
            return normalize.ReadResult(drafts=drafts, status="partial",
                                        note=f"{why}; {len(drafts)} of {len(postings)} listed postings read ({missing} missing)")
        return normalize.ReadResult(drafts=drafts, note=f"read {len(drafts)} posting pages from the listing")

    inline = inline_postings(page, final, today)
    if inline:
        return normalize.ReadResult(drafts=_unique(inline), note=f"read {len(inline)} postings written on the careers page")

    jobs, company_pages = linkedin_targets(page, final)
    if jobs or company_pages:
        return _read_linkedin(jobs, company_pages, get, context)

    text = visible_text(page)
    pdfs = [url for url, label in links(page, final) if url.lower().split("?")[0].endswith(".pdf")
            and _JOB_WORDS.search(url + " " + label)]
    if pdfs:
        return normalize.ReadResult(status="unreadable", note=f"postings given only as PDFs ({len(pdfs)})")
    if _NONE_OPEN.search(text):
        return normalize.ReadResult(status="none-open", note=_NONE_OPEN.search(text).group(0)[:80])
    if empty_listing(page):
        return normalize.ReadResult(status="none-open", note=empty_listing(page))
    if len(text) < 600 and _JS_APP.search(page):
        return normalize.ReadResult(status="unreadable", note="the list is built by JavaScript")
    note = "neither postings nor a no-openings notice found on the page"
    if unread:
        note += f"; the page uses {unread}, which the collector has no reader for"
    return normalize.ReadResult(status="unreadable", note=note)


# Where a page's openings begin: a heading, a labelled section or a label span
# ("Current Open Positions", <section aria-label="Open roles">, <span>Open roles</span>).
_OPENINGS_HEADING = re.compile(
    r"(?:<h[1-6][^>]*>|<span[^>]*>|aria-label=\")\s*(?:<[^>]+>\s*)*(?:current |our |open |job )?"
    r"(?:open (?:positions|roles)|openings|opportunities|positions|vacancies)\b", re.I)
_DETAILS = re.compile(r"<details\b[^>]*>\s*<summary\b[^>]*>(.*?)</summary>(.*?)</details>", re.I | re.S)
_SMALL = re.compile(r"<small\b[^>]*>(.*?)</small>", re.I | re.S)


def inline_postings(page: str, url: str, today) -> list[dict]:
    """Postings written on the careers page itself, one per <details> block
    under an openings heading ("Current open positions"): the summary is the
    title (a <small> in it gives place and type), the block the description."""
    heading = _OPENINGS_HEADING.search(page)
    if not heading:
        # No openings heading: job-title headings still count, but only when the
        # text under each reads like a posting (not a leadership bio).
        return heading_postings(page, 0, url, strict=True)
    drafts = []
    for summary, body in _DETAILS.findall(page[heading.end():]):
        small = _SMALL.search(summary)
        facts = _text_of(small.group(1)) if small else ""
        title = _text_of(_SMALL.sub(" ", summary))
        description = html_to_text(body)
        if not title or len(description) < MIN_DESCRIPTION or GENERAL_APPLICATION.search(title):
            continue
        parts = [part.strip() for part in re.split(r"[·•|]", facts) if part.strip()]
        employment = next((normalize.employment_from_text(part) for part in parts
                           if normalize.employment_from_text(part) != "unknown"), normalize.employment_from_title(title))
        places = [parse_location(part) for part in parts if normalize.employment_from_text(part) == "unknown"]
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:80]
        drafts.append(normalize.draft(
            posting_id=f"{_posting_id(url)}#{slug}", title=title, url=url,
            locations=[place for place in places if len(place) > 1][:3], workplace=None, employment=employment,
            pay=None, posted_date=None, department=None, description_text=description))
    return drafts or heading_postings(page, heading.end(), url)


_ANY_HEADING = re.compile(r"<(h[1-6])\b[^>]*>(.*?)</\1>", re.I | re.S)
_PAGE_END = re.compile(r"<footer\b", re.I)


# Words a posting's text has and a bio or a product section does not.
_POSTING_WORDS = re.compile(r"responsibilit|qualification|requirement|you will|you.ll|we are (?:looking|seeking)|"
                            r"we.re (?:looking|seeking)|looking for|to apply|apply (?:now|here|today|for)|duties|"
                            r"years of (?:relevant )?experience|job (?:summary|description)|what you.ll do|"
                            r"about the role|the ideal candidate|preferred skills|required skills|benefits", re.I)


def heading_postings(page: str, start: int, url: str, strict: bool = False) -> list[dict]:
    """Postings written as headings under the openings heading, each followed by
    its description ("Senior Mechanical Design Engineer", then its text). A
    heading counts only when it reads like a job title and at least
    MIN_DESCRIPTION characters of text follow it before the next heading of its
    level or above."""
    end = _PAGE_END.search(page, start)
    region = page[start:end.start() if end else len(page)]
    headings = [(m.start(), m.end(), m.group(1).lower(), clean_title(_text_of(m.group(2)))[0])
                for m in _ANY_HEADING.finditer(region)]
    places_in = {i: clean_title(_text_of(m.group(2)))[1] for i, m in enumerate(_ANY_HEADING.finditer(region))}
    is_title = lambda text: (3 <= len(text) <= 100 and bool(_JOB_TITLE.search(text))
                             and not _SECTION_HEADING.match(text))
    titled = [h for h in headings if is_title(h[3])]
    if not titled:
        return []
    level = titled[0][2]
    drafts = []
    for index, (_s, e, tag, title) in enumerate(headings):
        if tag != level or not is_title(title):
            continue
        following = [h for h in headings[index + 1:] if h[2] <= level]
        stop = following[0][0] if following else len(region)
        description = html_to_text(region[e:stop])
        if len(description) < MIN_DESCRIPTION or GENERAL_APPLICATION.search(title):
            continue
        if strict and not _POSTING_WORDS.search(description):
            continue
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:80]
        # A short first line of facts under the title: "Berkeley, CA • Full Time".
        first = description.split("\n", 1)[0]
        facts = [part.strip() for part in re.split(r"[·•|]", first) if part.strip()] if len(first) <= 80 and re.search(r"[·•|]", first) else []
        employment = next((normalize.employment_from_text(part) for part in facts
                           if normalize.employment_from_text(part) != "unknown"), normalize.employment_from_title(title))
        places = [parse_location(part) for part in facts if normalize.employment_from_text(part) == "unknown"]
        if places_in.get(index):
            places.insert(0, parse_location(places_in[index]))
        drafts.append(normalize.draft(
            posting_id=f"{_posting_id(url)}#{slug}", title=title, url=url,
            locations=[place for place in places if len(place) > 1][:3], workplace=None,
            employment=employment, pay=None, posted_date=None, department=None, description_text=description))
    return drafts


# A heading that opens a section, not a job: "Hear From Our Interns", "Meet the Team".
_SECTION_HEADING = re.compile(r"^(?:hear|meet|our|why|life|about|join|working|benefits|what|how|who|where|"
                              r"explore|discover|see|learn|read|watch|careers? at|opportunities)\b", re.I)
_TITLE_LABEL = re.compile(r"^(?:job position|open position|position|job title|now hiring|hiring|role|opening)\s*:\s*", re.I)
_TITLE_TAIL = re.compile(r"\s+(?:job description\b.*|location\s*:\s*(.+))$", re.I)


def clean_title(text: str) -> tuple[str, str | None]:
    """A heading as a job title: labels ("Open Position: ") and tails ("Job
    Description Location: Houston, TX") cut off; a place in the tail is returned."""
    text = _TITLE_LABEL.sub("", text.strip())
    place = None
    tail = _TITLE_TAIL.search(text)
    if tail:
        place = (tail.group(1) or "").strip() or None
        if place is None:
            inner = re.search(r"location\s*:\s*(.+)$", tail.group(0), re.I)
            place = inner.group(1).strip() if inner else None
        text = text[:tail.start()].strip()
    return text, place


def _read_linkedin(jobs: list[str], company_pages: list[str], get, context: Context) -> normalize.ReadResult:
    """Public LinkedIn job pages the company's careers page sends candidates to."""
    if context.linkedin_blocked:
        return normalize.ReadResult(status="blocked", note=f"LinkedIn not asked: {context.linkedin_blocked} earlier in this run")
    on_linkedin = lambda url: bool(_LINKEDIN_HOST.search(urlsplit(url).netloc)) and not _LINKEDIN_WALL.search(urlsplit(url).path)

    def ask(url: str) -> tuple[str, str]:
        if context.linkedin_requests >= LINKEDIN_CAP:
            raise _Cap(f"LinkedIn cap of {LINKEDIN_CAP} requests a run reached")
        context.linkedin_requests += 1
        try:
            landed, body = get(url, on_linkedin)
        except Blocked as error:
            context.linkedin_blocked = str(error)[:120]
            raise
        except FetchError as error:
            if "redirected" in str(error) and ("authwall" in str(error) or "login" in str(error) or "signup" in str(error)):
                context.linkedin_blocked = "LinkedIn showed a sign-in wall"
                raise Blocked(context.linkedin_blocked) from None
            raise
        why = refusal(body) or ("sign-in wall" if _LINKEDIN_WALL.search(urlsplit(landed).path) else None)
        if why:
            context.linkedin_blocked = f"LinkedIn showed a {why}"
            raise Blocked(context.linkedin_blocked)
        return landed, body

    today = context.now
    drafts, failed, capped = [], 0, None
    try:
        for company_page in company_pages:
            if jobs:
                break
            _landed, body = ask(company_page)
            for url, _label in links(body, company_page):
                found = _LINKEDIN_JOB.match(url)
                if found:
                    canonical = f"https://www.linkedin.com/jobs/view/{found.group(1)}"
                    if canonical not in jobs:
                        jobs.append(canonical)
        for url in jobs:
            _landed, body = ask(url)
            items = job_posting_items(body)
            made = draft_from_ld(items[0], url, today) if items else None
            if made:
                made["url"], made["posting_id"] = url, "linkedin-" + url.rsplit("/", 1)[-1]
                drafts.append(made)
            else:
                failed += 1
    except _Cap as cap:
        capped = cap.why
    except FetchError as error:
        if isinstance(error, Blocked):
            raise
        failed += 1
    drafts = _unique(drafts)
    if not jobs and not drafts and not capped:
        return normalize.ReadResult(status="none-open", note="careers page points to LinkedIn, which lists no public jobs")
    if capped or failed:
        why = capped or f"{failed} LinkedIn pages could not be read"
        return normalize.ReadResult(drafts=drafts, status="partial", note=f"{why}; {len(drafts)} of {len(jobs)} read")
    return normalize.ReadResult(drafts=drafts, note=f"read {len(drafts)} postings on LinkedIn, where the careers page points")


# A standing invitation to apply is not a posting.
GENERAL_APPLICATION = re.compile(r"\b(?:any position|general application|open application|spontaneous application|"
                                 r"talent (?:pool|network|community)|future (?:opportunities|openings|roles))\b", re.I)


def _unique(drafts: list[dict]) -> list[dict]:
    seen, kept = set(), []
    for made in drafts:
        if GENERAL_APPLICATION.search(made["title"]):
            continue
        if made["posting_id"] not in seen:
            seen.add(made["posting_id"])
            kept.append(made)
    return kept
