"""Workable reader.

Documentation: https://workable.readme.io/reference/jobs-1 (updated 2025-06-10)
and https://help.workable.com/hc/en-us/articles/115012771647 ("Using the
Workable API to create a careers page").

    GET https://www.workable.com/api/accounts/{subdomain}?details=true

No authentication. `details=true` "includes description field for jobs". On
2026-11-24 the documented address answered 302 to
https://apply.workable.com/api/v1/widget/accounts/{subdomain} (query kept), so
the reader asks that address directly: the fetcher never follows redirects.
No rate limit is published for this feed.

Fields read: title, shortcode (the posting id), url, employment_type,
telecommuting, workplace_type (documented; absent from the answers seen),
experience, department, published_on (or created_at), locations[] (city,
region, country, hidden) and, when that is empty, the top-level city, state and
country, and description (HTML).

The feed has no pay. The undocumented per-posting answer the hosted careers
page uses does carry a salary; it is not read.
"""
from __future__ import annotations

from pipeline.collect import normalize
from pipeline.collect.fetch import Fetcher
from pipeline.collect.locations import structured_location
from pipeline.collect.text import html_to_text

API = "https://apply.workable.com/api/v1/widget/accounts/{board}"
HOSTED = "https://apply.workable.com/{board}/j/{posting}/"

WORKPLACE = {"on_site": "onsite", "onsite": "onsite", "hybrid": "hybrid", "remote": "remote"}


def _place(city, region, country) -> dict | None:
    parts = [part.strip() for part in (city, region, country) if isinstance(part, str) and part.strip()]
    if not parts:
        return None
    return structured_location(", ".join(parts), city, region, country)


def _locations(job: dict) -> list[dict]:
    found = [
        _place(item.get("city"), item.get("region"), item.get("country"))
        for item in job.get("locations") or []
        if isinstance(item, dict) and not item.get("hidden")
    ]
    found = [location for location in found if location]
    if not found:
        single = _place(job.get("city"), job.get("state"), job.get("country"))
        found = [single] if single else []
    return list({location["text"].lower(): location for location in found}.values())


def _workplace(job: dict) -> str | None:
    if job.get("telecommuting") is True:
        return "remote"
    return WORKPLACE.get((job.get("workplace_type") or "").lower())


def _employment(job: dict) -> str:
    found = normalize.employment_from_text(job.get("employment_type"))
    if found == "unknown" and (job.get("experience") or "").lower() == "internship":
        found = "intern"
    return found if found != "unknown" else normalize.employment_from_title(job.get("title") or "")


def _draft(job: dict, board: str) -> dict:
    posting = str(job.get("shortcode") or "")
    url = job.get("url") or job.get("shortlink") or ""
    if not url.startswith("https://") and posting:
        url = HOSTED.format(board=board, posting=posting)
    return normalize.draft(
        posting_id=posting,
        title=job.get("title") or "",
        url=url,
        locations=_locations(job),
        workplace=_workplace(job),
        employment=_employment(job),
        pay=None,
        posted_date=normalize.iso_date(job.get("published_on")) or normalize.iso_date(job.get("created_at")),
        department=normalize.department(job.get("department")),
        description_text=html_to_text(job.get("description")),
    )


def read(board: str, fetcher: Fetcher) -> list[dict]:
    answer = fetcher.get_json(API.format(board=board), {"details": "true"})
    return [_draft(job, board) for job in answer["jobs"]]
