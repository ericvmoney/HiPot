"""Rippling reader.

Read on the owner's instruction of 2026-11-24, against two cautions:

  * Rippling's own documentation for this feed
    (https://developer.rippling.com/documentation/job-board-api) is behind a
    sign-in. The endpoints below come from third-party write-ups and from what
    the feed returned when probed, not from documentation.
  * Rippling's User Terms (https://app.rippling.com/legal/user, section 2.2,
    last updated 2026-11-23) list as prohibited extracting "data from Rippling
    for use outside of the Rippling Services", including through automated
    tools, and automated systems that send more requests than a person could
    with a browser.

So this reader is the slowest and most cautious of the four: requests to the
Rippling host are spaced HOST_INTERVALS["api.rippling.com"] seconds apart (see
fetch.py), and a refusal stops it as for every other host.

    GET https://api.rippling.com/platform/api/ats/v1/board/{board}/jobs
    GET https://api.rippling.com/platform/api/ats/v1/board/{board}/jobs/{uuid}

The list gives uuid, name, url, department.label and workLocation.label, with
one entry per posting per location. Everything else needs the detail request,
one per posting: description (company and role, HTML), workLocations,
employmentType (label is a code such as SALARIED_FT), createdOn and
payRangeDetails (location, currency, frequency, rangeStart, rangeEnd).
"""
from __future__ import annotations

import re

from pipeline.collect import normalize
from pipeline.collect.fetch import Blocked, FetchError, Fetcher
from pipeline.collect.locations import parse_location, split_locations
from pipeline.collect.text import html_to_text, join_text

API = "https://api.rippling.com/platform/api/ats/v1/board/{board}/jobs"
PERIOD = {"YEAR": "year", "HOUR": "hour"}


def employment(kind) -> str:
    """From employmentType: a code in `label` (SALARIED_FT) and words in `id`."""
    if not isinstance(kind, dict):
        return "unknown"
    code = str(kind.get("label") or "").upper()
    if "INTERN" in code:
        return "intern"
    if re.search(r"CONTRACT|TEMP|SEASONAL", code):
        return "contract"
    if re.search(r"(^|_)PT($|_)|PART", code):
        return "part-time"
    if re.search(r"(^|_)FT($|_)|FULL", code):
        return "full-time"
    return normalize.employment_from_text(kind.get("id") if isinstance(kind.get("id"), str) else None)


def pay(ranges) -> dict | None:
    """The first pay range that fits the contract. One posting may give one per location."""
    for item in ranges or []:
        if not isinstance(item, dict):
            continue
        found = normalize.pay(item.get("rangeStart"), item.get("rangeEnd"), item.get("currency"),
                              PERIOD.get(str(item.get("frequency") or "").upper()))
        if found:
            return found
    return None


def _labels(entries: list[dict]) -> list[str]:
    labels = []
    for entry in entries:
        label = ((entry.get("workLocation") or {}).get("label") or "").strip()
        if label:
            labels.append(label)
    return labels


def _draft(uuid: str, entries: list[dict], detail: dict | None) -> dict:
    first = entries[0]
    detail = detail or {}
    places = [place for place in detail.get("workLocations") or [] if isinstance(place, str) and place.strip()]
    pieces = [piece for place in (places or _labels(entries)) for piece in split_locations(place)]
    description = detail.get("description") or {}
    if not isinstance(description, dict):
        description = {"role": description if isinstance(description, str) else ""}
    department = (detail.get("department") or {}).get("name") or (first.get("department") or {}).get("label")
    title = detail.get("name") or first.get("name") or ""
    # Rippling files interns under TEMP ("Temporary / Intern"), so a title that
    # says intern wins over the code.
    from_title = normalize.employment_from_title(title)
    found = "intern" if from_title == "intern" else employment(detail.get("employmentType"))
    return normalize.draft(
        posting_id=uuid,
        title=title,
        url=first.get("url") or detail.get("url") or "",
        locations=[parse_location(piece) for piece in dict.fromkeys(pieces)],
        workplace=None,          # the feed has no workplace field; the location rules decide
        employment=found if found != "unknown" else from_title,
        pay=pay(detail.get("payRangeDetails")),
        posted_date=normalize.iso_date(detail.get("createdOn")),
        department=normalize.department(department),
        description_text=join_text(html_to_text(description.get("company")), html_to_text(description.get("role"))),
    )


def read(board: str, fetcher: Fetcher) -> list[dict]:
    listing = fetcher.get_json(API.format(board=board))
    if not isinstance(listing, list):
        raise ValueError(f"expected a list of postings, found {type(listing).__name__}")
    by_uuid: dict[str, list[dict]] = {}
    for entry in listing:
        if isinstance(entry, dict) and entry.get("uuid"):
            by_uuid.setdefault(str(entry["uuid"]), []).append(entry)

    drafts = []
    for uuid, entries in by_uuid.items():
        try:
            detail = fetcher.get_json(f"{API.format(board=board)}/{uuid}")
        except Blocked:
            raise                # a refusal blocks the whole company, as for every other host
        except FetchError:
            detail = None        # keep what the list gave: title, address, location, department
        drafts.append(_draft(uuid, entries, detail if isinstance(detail, dict) else None))
    return drafts
