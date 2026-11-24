"""Paylocity reader.

Paylocity documents no public job feed: its developer site
(https://developer.paylocity.com) covers only the authenticated HR and payroll
APIs. This reader uses the hosted job board every Paylocity customer has, as
seen working on 2026-11-24:

    GET https://recruiting.paylocity.com/recruiting/jobs/All/{companyGuid}

The page carries all of the company's open jobs as JSON in a
`window.pageData = {...};` script, without paging and with a cut-off
description. The full description is read from each posting's page,
https://recruiting.paylocity.com/Recruiting/Jobs/Details/{JobId}, from its
schema.org JobPosting block: one request per posting.

The board token is the company GUID from the board address. If the GUID alone
stops answering, the token may hold the GUID and the name segment
("{guid}/{Company-Name}"), which is put into the address as it is.

Terms: nothing found that prohibits reading. Paylocity's published terms
(https://www.paylocity.com/terms-and-conditions/) cover its API and developer
tools; recruiting.paylocity.com has no robots.txt (404). No rate limit is
published; the host is asked at most every 2 s (fetch.HOST_INTERVALS).

Fields read. Board: Jobs[] (JobId, JobTitle, PublishedDate, HiringDepartment,
IsInternal, IsRemote, LocationName, JobLocation: City, State, Country).
Posting page: the JobPosting block's description. There is no employment type
and no pay.
"""
from __future__ import annotations

import json

from pipeline.collect import normalize
from pipeline.collect.fetch import Blocked, FetchError, Fetcher
from pipeline.collect.locations import parse_location, structured_location
from pipeline.collect.text import job_posting_description

BOARD = "https://recruiting.paylocity.com/recruiting/jobs/All/{board}"
POSTING = "https://recruiting.paylocity.com/Recruiting/Jobs/Details/{posting}"
_MARK = "window.pageData"


def page_data(page: str) -> dict:
    """The object assigned to window.pageData on a board page."""
    start = (page or "").find(_MARK)
    brace = page.find("{", start) if start >= 0 else -1
    if brace < 0:
        raise FetchError("board page has no window.pageData (not a Paylocity job board?)")
    try:
        data, _ = json.JSONDecoder().raw_decode(page, brace)
    except ValueError as error:
        raise FetchError(f"window.pageData was not JSON ({error})") from error
    if not isinstance(data, dict) or not isinstance(data.get("Jobs"), list):
        raise FetchError("window.pageData has no job list")
    return data


def _locations(job: dict) -> list[dict]:
    place = job.get("JobLocation") if isinstance(job.get("JobLocation"), dict) else {}
    city, state, country = place.get("City"), place.get("State"), place.get("Country")
    parts = [part.strip() for part in (city, state) if isinstance(part, str) and part.strip()]
    if parts:
        return [structured_location(", ".join(parts), city, state, country)]
    name = (job.get("LocationName") or "").strip()
    return [parse_location(name)] if name and job.get("ShouldDisplayLocation", True) else []


def _draft(job: dict, description: str) -> dict:
    posting = str(job.get("JobId") or "")
    title = job.get("JobTitle") or ""
    return normalize.draft(
        posting_id=posting,
        title=title,
        url=POSTING.format(posting=posting),
        locations=_locations(job),
        workplace="remote" if job.get("IsRemote") is True else None,
        employment=normalize.employment_from_title(title),
        pay=None,
        posted_date=normalize.iso_date(job.get("PublishedDate")),
        department=normalize.department(job.get("HiringDepartment")),
        description_text=description or (job.get("Description") or "").strip(),
    )


def read(board: str, fetcher: Fetcher) -> list[dict]:
    jobs = page_data(fetcher.get_text(BOARD.format(board=board)))["Jobs"]
    drafts = []
    for job in jobs:
        if not isinstance(job, dict) or not job.get("JobId") or job.get("IsInternal"):
            continue
        try:
            description = job_posting_description(fetcher.get_text(POSTING.format(posting=job["JobId"])))
        except Blocked:
            raise
        except FetchError:
            description = ""   # keep the posting with the board's short description
        drafts.append(_draft(job, description))
    return drafts
