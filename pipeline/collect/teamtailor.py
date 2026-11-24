"""Teamtailor reader.

Documentation: "RSS feed: how-to guide",
https://support.teamtailor.com/en/articles/11171756-rss-feed-how-to-guide

    GET https://{careers-host}/jobs.rss?per_page=100&offset=N

Every Teamtailor careers site publishes this feed, with the full description,
without a key. The page says the feed gives the first 100 jobs by default and
documents `offset` and `per_page` for the rest, so the reader pages until a
page comes back short. No rate limit is published for the careers sites.

The board token is the careers site's host: `{company}` for
{company}.teamtailor.com, or the whole host when the company uses its own
domain (`career.airahome.com`). A token with a dot in it is taken as a host.

Terms: nothing found that prohibits reading. Teamtailor's terms (updated
2026-05-02) bind customers; robots.txt on the careers sites does not disallow
/jobs.rss.

Fields read (each item): title, description (HTML), pubDate, link,
remoteStatus (none, onsite, hybrid, fully), guid, tt:locations/tt:location
(city, country, name) and tt:department. There is no employment type, no
region or state and no pay. The posting id is the number in the posting
address (https://{host}/jobs/{number}-{slug}); guid is used only when the
address has none.
"""
from __future__ import annotations

import re
from email.utils import parsedate_to_datetime

from pipeline.collect import normalize
from pipeline.collect.fetch import FetchError, Fetcher
from pipeline.collect.locations import structured_location
from pipeline.collect.text import NotXML, html_to_text, parse_xml

PAGE = 100
MAX_PAGES = 50
TT = "{https://teamtailor.com/locations}"
WORKPLACE = {"fully": "remote", "hybrid": "hybrid", "none": "onsite", "onsite": "onsite"}
_POSTING = re.compile(r"/jobs/(\d+)(?:-|$)")


def host_for(board: str) -> str:
    return board if "." in board else f"{board}.teamtailor.com"


def feed_url(board: str, offset: int) -> str:
    return f"https://{host_for(board)}/jobs.rss?per_page={PAGE}&offset={offset}"


def _text(element, tag: str) -> str:
    found = element.find(tag)
    return (found.text or "").strip() if found is not None else ""


def _date(value: str) -> str | None:
    try:
        return parsedate_to_datetime(value).date().isoformat()
    except (TypeError, ValueError, IndexError):
        return None


def _locations(item) -> list[dict]:
    found = []
    for place in item.iter(f"{TT}location"):
        city, country = _text(place, f"{TT}city"), _text(place, f"{TT}country")
        parts = [part for part in (city, country) if part] or [_text(place, f"{TT}name")]
        if parts[0]:
            found.append(structured_location(", ".join(parts), city or None, None, country or None))
    return list({location["text"].lower(): location for location in found}.values())


def _draft(item) -> dict:
    url = _text(item, "link")
    title = _text(item, "title")
    match = _POSTING.search(url)
    return normalize.draft(
        posting_id=match.group(1) if match else _text(item, "guid"),
        title=title,
        url=url,
        locations=_locations(item),
        workplace=WORKPLACE.get(_text(item, "remoteStatus").lower()),
        employment=normalize.employment_from_title(title),
        pay=None,
        posted_date=_date(_text(item, "pubDate")),
        department=normalize.department(_text(item, f"{TT}department")),
        description_text=html_to_text(_text(item, "description")),
    )


def parse(text: str) -> list:
    try:
        root = parse_xml(text)
    except NotXML as error:
        raise FetchError(str(error)) from error
    channel = root.find("channel")
    if root.tag != "rss" or channel is None:
        raise FetchError(f"answer was not an RSS feed (root element <{root.tag}>)")
    return channel.findall("item")


def read(board: str, fetcher: Fetcher) -> list[dict]:
    drafts, seen = [], set()
    for page in range(MAX_PAGES):
        items = parse(fetcher.get_text(feed_url(board, page * PAGE)))
        for item in items:
            made = _draft(item)
            if made["posting_id"] not in seen:     # a posting can move across pages between requests
                seen.add(made["posting_id"])
                drafts.append(made)
        if len(items) < PAGE:
            break
    return drafts
