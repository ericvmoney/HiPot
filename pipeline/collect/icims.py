"""iCIMS reader.

iCIMS documents no public job feed: its Standard XML Feed and Job Portal API
(https://developer-community.icims.com) are for approved vendors with
credentials. This reader reads a company's career portal the way a browser
does, as seen working on 2026-11-25:

    GET https://careers-{company}.icims.com/jobs/search?ss=1&in_iframe=1&pr={page}
    GET https://careers-{company}.icims.com/jobs/{id}/{slug}/job?in_iframe=1

The search answers 20 job cards a page ("Page 1 of 8"; `pr` counts from 0),
each with the posting id, title, location ("US-CA-Marina") and category. Each
posting page is read for its description: its schema.org JobPosting block
when it has one, else its text. One request per page and per posting; the
portal hosts get 2 s between requests.

The board token is the portal's company name ("jobyaviation" for
careers-jobyaviation.icims.com), or the portal's whole host when it is not of
that form.

Terms: iCIMS's Terms of Use (https://www.icims.com/legal/terms-of-use/,
modified 2024-04-01) cover icims.com "including its related domains and
subdomains" and bar any "robot, spider or other automatic device" (Prohibited
Uses). The reader runs by the owner's standing rule (PLAN.md decision 6) and
is on the risk list. robots.txt on the portals allows /jobs/search and the
posting pages.
"""
from __future__ import annotations

import html as html_lib
import re
from urllib.parse import urlsplit

from pipeline.collect import normalize
from pipeline.collect.careers import draft_from_ld, job_posting_items
from pipeline.collect.fetch import Blocked, FetchError, Fetcher
from pipeline.collect.locations import parse_location
from pipeline.collect.probe_careers import refusal
from pipeline.collect.text import html_to_text

MAX_PAGES = 50
_CARD = re.compile(r'<li class="iCIMS_JobCardItem">(.*?)</li>', re.S)
_ANCHOR = re.compile(r'<a href="(https://[^"]+/jobs/(\d+)/[^"]+)"[^>]*class="iCIMS_Anchor"[^>]*title="([^"]*)"', re.S)
_ANCHOR_ANY = re.compile(r'<a[^>]+href="(https://[^"]+/jobs/(\d+)/[^"/]+/job[^"]*)"[^>]*>', re.S)
_HEADING = re.compile(r"<h3[^>]*>(.*?)</h3>", re.S)
_LOCATION = re.compile(r'Job Locations</span>\s*<span[^>]*>(.*?)</span>', re.S)
_FIELD = re.compile(r'<dt class="iCIMS_JobHeaderField">(.*?)</dt>\s*<dd class="iCIMS_JobHeaderData">(.*?)</dd>', re.S)
_PAGES = re.compile(r"Page\s+\d+\s+of\s+(\d+)")
_CONTENT = re.compile(r'<div[^>]+class="[^"]*iCIMS_JobContent[^"]*"[^>]*>(.*)', re.S)


def host_for(board: str) -> str:
    return board if "." in board else f"careers-{board}.icims.com"


def _text(markup: str) -> str:
    return " ".join(html_lib.unescape(re.sub(r"<[^>]+>", " ", markup or "")).split())


def place(text: str) -> dict:
    """iCIMS writes places as 'US-CA-Marina' (country, state, city) or 'US-Remote'."""
    parts = [part.strip() for part in text.split("-")]
    if len(parts) >= 3 and len(parts[0]) == 2 and len(parts[1]) == 2 and parts[0].isupper():
        city = "-".join(parts[2:])
        return parse_location(f"{city}, {parts[1]}, {parts[0]}") | {"text": text}
    if len(parts) == 2 and len(parts[0]) == 2 and parts[1].lower() == "remote":
        return parse_location(f"Remote, {parts[0]}") | {"text": text}
    return parse_location(text)


def cards(page: str) -> list[dict]:
    found = []
    for card in _CARD.findall(page):
        anchor = _ANCHOR.search(card) or _ANCHOR_ANY.search(card)
        if not anchor:
            continue
        url, posting = anchor.group(1), anchor.group(2)
        heading = _HEADING.search(card)
        title = _text(heading.group(1)) if heading else _text(anchor.group(3)).split(" - ", 1)[-1] if anchor.lastindex >= 3 else ""
        where = _LOCATION.search(card)
        fields = {_text(name).lower(): _text(value) for name, value in _FIELD.findall(card)}
        found.append({"id": posting, "url": url.replace("?in_iframe=1", "").replace("&in_iframe=1", ""),
                      "title": title, "location": _text(where.group(1)) if where else "",
                      "category": fields.get("category")})
    return found


def _draft(card: dict, page: str, today) -> dict:
    items = job_posting_items(page)
    made = draft_from_ld(items[0], card["url"], today) if items else None
    locations = [place(piece.strip()) for piece in re.split(r"\s*\|\s*|\s*;\s*", card["location"]) if piece.strip()]
    if made:
        made["posting_id"], made["url"], made["title"] = card["id"], card["url"], card["title"] or made["title"]
        if not made["locations"]:
            made["locations"] = locations
        if not made["department"]:
            made["department"] = normalize.department(card["category"])
        return made
    content = _CONTENT.search(page)
    return normalize.draft(
        posting_id=card["id"],
        title=card["title"],
        url=card["url"],
        locations=locations,
        workplace=None,
        employment=normalize.employment_from_title(card["title"]),
        pay=None,
        posted_date=None,
        department=normalize.department(card["category"]),
        description_text=html_to_text(content.group(1)) if content else "",
    )


def read(board: str, fetcher: Fetcher) -> list[dict]:
    from datetime import datetime, timezone
    host = host_for(board)
    stay = lambda url: urlsplit(url).netloc.lower() == host
    listed, seen, last = [], set(), None
    for number in range(MAX_PAGES):
        _final, page = fetcher.get_page(f"https://{host}/jobs/search?ss=1&in_iframe=1&pr={number}", stay)
        why = refusal(page)
        if why:
            raise Blocked(f"{why} on {host}")
        found = [card for card in cards(page) if card["id"] not in seen]
        seen.update(card["id"] for card in found)
        listed += found
        pages = _PAGES.search(page)
        last = int(pages.group(1)) if pages else last
        if not found or (last is not None and number + 1 >= last):
            break
    today = datetime.now(timezone.utc)
    drafts = []
    for card in listed:
        try:
            _final, body = fetcher.get_page(f"{card['url']}?in_iframe=1", stay)
        except Blocked:
            raise
        except FetchError:
            body = ""      # keep the posting from its card
        drafts.append(_draft(card, body, today))
    return drafts
