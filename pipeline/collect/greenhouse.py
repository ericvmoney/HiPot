"""Greenhouse reader.

Documentation: https://docs.greenhouse.io/job-board.html (Job Board API).

    GET https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true

No authentication for GET. `content=true` adds the description, departments
and offices. The documentation says requests "may be rate limited for security
and traffic reasons" and gives no figures.

Fields read: id, title, absolute_url, location.name, offices[].name (only when
the location is empty), departments[].name, content (HTML with its markup
entity-encoded), metadata[] (custom fields a company chose to expose),
first_published and updated_at.

Greenhouse has no workplace field, so workplace comes from an exposed custom
field when there is one and otherwise from the location rules.

Pay is not in the list answer. The documented single-posting endpoint returns
`pay_input_ranges` when asked with `pay_transparency=true`; `read(...,
with_pay=True)` makes that one extra request per posting.
"""
from __future__ import annotations

import re

from pipeline.collect import normalize
from pipeline.collect.fetch import FetchError, Fetcher
from pipeline.collect.locations import parse_location, split_locations, workplace_from_text
from pipeline.collect.text import escaped_html_to_text

API = "https://boards-api.greenhouse.io/v1/boards/{board}/jobs"
HOSTED = "https://job-boards.greenhouse.io/{board}/jobs/{posting}"

_WORKPLACE_FIELD = re.compile(r"workplace|work ?(model|mode|style|arrangement|location type)|location type|remote|hybrid", re.I)
_EMPLOYMENT_FIELD = re.compile(r"employment|time type|job type|worker type|position type|commitment", re.I)


def _metadata(job: dict, name_pattern: re.Pattern) -> list:
    return [
        (field.get("name") or "", field.get("value"))
        for field in job.get("metadata") or []
        if isinstance(field, dict) and name_pattern.search(field.get("name") or "")
    ]


def _workplace(job: dict) -> str | None:
    for name, value in _metadata(job, _WORKPLACE_FIELD):
        values = value if isinstance(value, list) else [value]
        for item in values:
            if isinstance(item, str):
                found = workplace_from_text(item)
                if found != "unknown":
                    return found
                if item.strip().lower() in ("yes", "true") and re.search(r"remote", name, re.I):
                    return "remote"
            elif item is True and re.search(r"remote", name, re.I):
                return "remote"
    return None


def _employment(job: dict) -> str:
    for _name, value in _metadata(job, _EMPLOYMENT_FIELD):
        values = value if isinstance(value, list) else [value]
        for item in values:
            found = normalize.employment_from_text(item if isinstance(item, str) else None)
            if found != "unknown":
                return found
    return normalize.employment_from_title(job.get("title") or "")


def pay_from_ranges(ranges) -> dict | None:
    """Pay from `pay_input_ranges`. The feed gives cents and no period.

    A range is read as yearly when it is at least 10,000 in its currency and as
    hourly when it is under 1,000; anything between is left out. When a posting
    has several ranges (one per region), the first that fits is used.
    """
    for item in ranges or []:
        if not isinstance(item, dict):
            continue
        low, high = item.get("min_cents"), item.get("max_cents")
        if not all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in (low, high)):
            continue
        low, high = low / 100, high / 100
        period = "year" if low >= 10_000 else "hour" if high < 1_000 else None
        found = normalize.pay(low, high, item.get("currency_type"), period)
        if found:
            return found
    return None


def _draft(job: dict, board: str) -> dict:
    posting = str(job["id"])
    url = job.get("absolute_url") or ""
    if not url.startswith("https://"):
        url = HOSTED.format(board=board, posting=posting)
    place = ((job.get("location") or {}).get("name") or "").strip()
    pieces = split_locations(place)
    if not pieces:
        pieces = [office["name"] for office in job.get("offices") or [] if office.get("name")]
    return normalize.draft(
        posting_id=posting,
        title=job.get("title") or "",
        url=url,
        locations=[parse_location(piece) for piece in pieces],
        workplace=_workplace(job),
        employment=_employment(job),
        pay=pay_from_ranges(job.get("pay_input_ranges")),
        posted_date=normalize.iso_date(job.get("first_published")) or normalize.iso_date(job.get("updated_at")),
        department=normalize.department(*(d.get("name") for d in job.get("departments") or [])),
        description_text=escaped_html_to_text(job.get("content")),
    )


def read(board: str, fetcher: Fetcher, with_pay: bool = False) -> list[dict]:
    answer = fetcher.get_json(API.format(board=board), {"content": "true"})
    jobs = answer["jobs"]
    drafts = []
    for job in jobs:
        made = _draft(job, board)
        if with_pay and made["pay"] is None:
            try:
                detail = fetcher.get_json(f"{API.format(board=board)}/{job['id']}", {"pay_transparency": "true"})
            except FetchError:
                # Pay is an extra. If a detail request fails or is refused, keep
                # the postings already read and ask for no more details.
                with_pay = False
            else:
                made["pay"] = pay_from_ranges(detail.get("pay_input_ranges"))
        drafts.append(made)
    return drafts
