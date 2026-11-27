"""Breezy HR reader. Its terms restrict automated reading: see below.

Breezy documents no public job feed. Its help centre describes only an embed
widget, and its developer documentation (https://developer.breezy.hr) covers
the authenticated API. This reader uses an address every Breezy careers site
answers, seen working on 2026-11-24:

    GET https://{company}.breezy.hr/json

It returns a list of the published positions, without descriptions. The
description is read from each posting's own page
(https://{company}.breezy.hr/p/{id}-{slug}), from the schema.org JobPosting
block the page carries for search engines: one request per posting.

Terms: Breezy's Terms of Service (updated 2026-08-10,
https://breezy.hr/policies/terms), section 5 item (ix), prohibit accessing the
Service "by any means other than our publicly supported interfaces (for
example, 'scraping')". Whether /json is such an interface is not stated. The
reader runs by the owner's decision (PLAN.md decision 6); --disable-reader
breezy turns it off for a run.

Fields read. List: id, name, url, published_date, type (id, name), location
and locations[] (city, state, country, is_remote, remote_details.value, name),
department, salary (free text, "$120,000 – $180,000 / year"). Posting page:
the JobPosting block's description (HTML).
"""
from __future__ import annotations

import re

from pipeline.collect import normalize
from pipeline.collect.fetch import Blocked, FetchError, Fetcher
from pipeline.collect.locations import structured_location
from pipeline.collect.text import html_to_text, job_posting_description

API = "https://{board}.breezy.hr/json"

# The salary field as Breezy writes it: a range and a period, nothing else.
_SALARY = re.compile(
    r"^\s*([$€£])\s?([\d,]+(?:\.\d+)?)\s*[–—-]\s*[$€£]?\s?([\d,]+(?:\.\d+)?)\s*/\s*(year|hour|yr|hr)\s*$", re.I)
_PERIOD = {"year": "year", "yr": "year", "hour": "hour", "hr": "hour"}


def _name(value) -> str | None:
    if isinstance(value, dict):
        return value.get("id") or value.get("name")
    return value if isinstance(value, str) else None


def _place(item: dict) -> dict | None:
    city = item.get("city") if isinstance(item.get("city"), str) else None
    if city and "," in city:
        # Some boards type the whole place into the city field ("Marlborough, MA",
        # with no state field); the state is then read from the location text.
        city = city.split(",")[0].strip()
    state, country = _name(item.get("state")), _name(item.get("country"))
    text = item.get("name") or ", ".join(part for part in (city, state, country) if part)
    if not text and item.get("is_remote"):
        text = "Remote"
    return structured_location(text, city, state, country) if text else None


def _locations(job: dict) -> list[dict]:
    found = [_place(item) for item in job.get("locations") or [] if isinstance(item, dict)]
    found = [location for location in found if location]
    if not found and isinstance(job.get("location"), dict):
        single = _place(job["location"])
        found = [single] if single else []
    return list({location["text"].lower(): location for location in found}.values())


def _workplace(job: dict) -> str | None:
    place = job.get("location") if isinstance(job.get("location"), dict) else {}
    if place.get("is_remote") is True:
        detail = ((place.get("remote_details") or {}).get("value") or "").lower()
        return "hybrid" if "hybrid" in detail else "remote"
    return None


def pay_from_text(text, country: str | None) -> dict | None:
    """Structured pay from the salary field, only when it is a plain range with a stated period."""
    match = _SALARY.match(text or "")
    if not match:
        return None
    symbol, low, high, period = match.groups()
    # A dollar sign is read as US dollars only on a US posting.
    currency = {"€": "EUR", "£": "GBP"}.get(symbol) or ("USD" if country == "US" else None)
    number = lambda value: float(value.replace(",", ""))
    return normalize.pay(number(low), number(high), currency, _PERIOD[period.lower()])


def _draft(job: dict, description: str) -> dict:
    title = job.get("name") or ""
    kind = job.get("type") or {}
    employment = normalize.employment_from_text(kind.get("name") or kind.get("id"))
    if employment == "unknown":
        employment = {"fulltime": "full-time", "parttime": "part-time"}.get((kind.get("id") or "").lower(), "unknown")
    country = _name((job.get("location") or {}).get("country")) if isinstance(job.get("location"), dict) else None
    return normalize.draft(
        posting_id=str(job.get("id") or ""),
        title=title,
        url=job.get("url") or "",
        locations=_locations(job),
        workplace=_workplace(job),
        employment=employment if employment != "unknown" else normalize.employment_from_title(title),
        pay=pay_from_text(job.get("salary"), country),
        posted_date=normalize.iso_date(job.get("published_date")),
        department=normalize.department(job.get("department")),
        description_text=description,
    )


def read(board: str, fetcher: Fetcher) -> list[dict]:
    answer = fetcher.get_json(API.format(board=board))
    if not isinstance(answer, list):
        raise FetchError("answer was not a list of positions")
    drafts = []
    details = normalize.Details()
    for job in answer:
        if not isinstance(job, dict) or not job.get("id"):
            continue
        description = ""
        if (job.get("url") or "").startswith("https://"):
            # A failed request keeps the posting from the list without its description.
            page = details.ask(lambda: fetcher.get_text(job["url"]), default="")
            description = job_posting_description(page) if page else ""
        drafts.append(_draft(job, description))
    return details.result(drafts)
