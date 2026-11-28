"""Jobvite reader. Jobvite's terms restrict automated reading: see below.

Jobvite documents no public job feed: its API (api.jobvite.com) needs keys
issued to partners. This reader reads a company's Jobvite career site the way
a browser does, as seen working on 2026-11-27:

    GET https://jobs.jobvite.com/{company}/jobs          the list, plain HTML
    GET https://jobs.jobvite.com/{company}/job/{id}      one request per posting

The list groups postings under category headings (<h3 class="h2">), one table
row per posting with its title link and a location cell ("Houston, TX",
"Remote, United States", "Remote, 3 Locations"). Each posting page carries a
schema.org JobPosting block: title, datePosted, employmentType,
jobLocationType (TELECOMMUTE for remote), the full description, and a
baseSalary that was empty on every posting seen; pay, where a posting gives
it, is only in the description text. No list seen had more than one page; a
list that shows page links is read as far as its first page and reported
partial.

The board token is the career site's company name ("nuscale-power").

robots.txt: jobs.jobvite.com has none (HTTP 404 on 2026-11-27).

Terms: Jobvite's Terms of Use (https://www.jobvite.com/terms-of-use/, last
updated 2021-02-23) say "You may not copy, distribute, scrape, disassemble,
reverse engineer" (Intellectual Property and Restrictions); they name
www.jobvite.com, not the career sites. The reader runs by the owner's standing
rule for readers whose vendor terms restrict reading (PLAN.md decision 6) and
is on the risk list; --disable-reader jobvite turns it off for a run.
"""
from __future__ import annotations

import html as html_lib
import re
from datetime import datetime, timezone
from urllib.parse import urlsplit

from pipeline.collect import normalize
from pipeline.collect.careers import draft_from_ld, job_posting_items
from pipeline.collect.fetch import Blocked, Fetcher
from pipeline.collect.locations import parse_location
from pipeline.collect.probe_careers import refusal

HOST = "jobs.jobvite.com"
_SECTION = re.compile(r'<h3 class="h2">(.*?)</h3>', re.S)
_ROW = re.compile(r'<td class="jv-job-list-name">\s*<a href="/([^/"]+)/job/([A-Za-z0-9]+)"[^>]*>(.*?)</a>.*?'
                  r'<td class="jv-job-list-location">(.*?)</td>', re.S)
_PAGINATION = re.compile(r'class="[^"]*jv-pagination', re.I)
_MANY_PLACES = re.compile(r"\b\d+\s+Locations\b", re.I)


def _text(markup: str) -> str:
    return " ".join(html_lib.unescape(re.sub(r"<[^>]+>", " ", markup or "")).split()).replace(" ,", ",")


def cards(page: str, board: str) -> list[dict]:
    """The postings on a list page: id, title, location text and category."""
    found, seen = [], set()
    pieces = _SECTION.split(page)
    # split() gives [before, heading, section, heading, section, ...]
    sections = [(None, pieces[0])] + [(pieces[i], pieces[i + 1]) for i in range(1, len(pieces) - 1, 2)]
    for heading, body in sections:
        for company, posting, title, where in _ROW.findall(body):
            if company != board or posting in seen:
                continue
            seen.add(posting)
            found.append({"id": posting, "url": f"https://{HOST}/{board}/job/{posting}", "title": _text(title),
                          "location": _text(where), "category": _text(heading) if heading else None})
    return found


def _draft(card: dict, page: str, today: datetime) -> dict:
    items = job_posting_items(page)
    made = draft_from_ld(items[0], card["url"], today) if items else None
    listed = [] if _MANY_PLACES.search(card["location"]) or not card["location"] else [parse_location(card["location"])]
    if made:
        made["posting_id"], made["url"] = card["id"], card["url"]
        made["title"] = card["title"] or made["title"]
        # The list's "Houston, TX" says more than the posting's country-only address.
        made["locations"] = listed or made["locations"]
        kind = items[0].get("employmentType")
        if made["employment"] == "unknown" and isinstance(kind, str):
            # Jobvite writes "Full-Time", not schema.org's FULL_TIME.
            found = normalize.employment_from_text(kind)
            made["employment"] = found if found != "unknown" else made["employment"]
        if not made["department"]:
            made["department"] = normalize.department(card["category"])
        return made
    return normalize.draft(
        posting_id=card["id"],
        title=card["title"],
        url=card["url"],
        locations=listed,
        workplace=None,
        employment=normalize.employment_from_title(card["title"]),
        pay=None,
        posted_date=None,
        department=normalize.department(card["category"]),
        description_text="",
    )


def read(board: str, fetcher: Fetcher) -> "list[dict] | normalize.ReadResult":
    stay = lambda url: urlsplit(url).netloc.lower() == HOST
    # A retired site redirects off the host (View's went to search.jobvite.com),
    # which get_page refuses to follow.
    _final, page = fetcher.get_page(f"https://{HOST}/{board}/jobs", stay)
    why = refusal(page)
    if why:
        raise Blocked(f"{why} on {HOST}")
    listed = cards(page, board)
    today = datetime.now(timezone.utc)
    drafts = []
    details = normalize.Details()
    for card in listed:
        # A failed request keeps the posting from the list, without its description.
        _final, body = details.ask(lambda: fetcher.get_page(card["url"], stay), default=("", ""))
        drafts.append(_draft(card, body, today))
    result = details.result(drafts)
    if _PAGINATION.search(page):
        note = "the list has more than one page; only the first is read"
        if isinstance(result, normalize.ReadResult):
            return normalize.ReadResult(result.drafts, "partial", f"{result.note}; {note}")
        return normalize.ReadResult(result, "partial", note)
    return result
