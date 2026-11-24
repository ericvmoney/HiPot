"""Recruitee reader.

Documentation: the Careers Site API, https://docs.recruitee.com/reference/offers
(updated 2025-06-09) and https://docs.recruitee.com/reference/authentication-1
(updated 2026-08-12).

    GET https://{company}.recruitee.com/api/offers/

One request per board: the answer holds every published offer with its full
description, and there is no paging. No rate limit is published.

Authentication is changing. The documentation says that from 10 February 2027
calls without an `X-Careers-Sites-Token` header, a token each company creates
for itself, "will return the 401 Unauthorized error". Until then the feed
answers without one. After that date this reader will fail for every company
that has not given HiPot a token; 401 is reported as an error, never worked
around.

Terms: nothing found that prohibits reading. Tellent's terms (15 June 2026)
bind subscribers, and say the careers site "is not intended to be private".

Fields read: id, title, careers_url (may be on the company's own domain),
status, location, city, state_name, country, locations[] (city, state,
country), remote, hybrid, on_site, employment_type_code, department,
published_at (or created_at), salary (min, max, period, currency),
description and requirements (HTML).
"""
from __future__ import annotations

import re

from pipeline.collect import normalize
from pipeline.collect.fetch import Fetcher
from pipeline.collect.locations import structured_location
from pipeline.collect.text import html_to_text, join_text

API = "https://{board}.recruitee.com/api/offers/"
HOSTED = "https://{board}.recruitee.com/o/{slug}"
PERIOD = {"year": "year", "hour": "hour"}     # "month" and others are not in the contract


def _employment(code: str | None, title: str) -> str:
    code = (code or "").lower()
    if "intern" in code or "trainee" in code:
        return "intern"
    if "parttime" in code:
        return "part-time"
    if any(word in code for word in ("temporary", "fixed_term", "freelance", "contract")):
        return "contract"
    if "fulltime" in code:
        return "full-time"
    return normalize.employment_from_title(title)


def _workplace(offer: dict) -> str | None:
    if offer.get("remote") is True:
        return "remote"
    if offer.get("hybrid") is True:
        return "hybrid"
    if offer.get("on_site") is True:
        return "onsite"
    return None


def _place(city, region, country) -> dict | None:
    parts = [part.strip() for part in (city, region, country) if isinstance(part, str) and part.strip()]
    return structured_location(", ".join(parts), city, region, country) if parts else None


def _locations(offer: dict) -> list[dict]:
    found = [_place(item.get("city"), item.get("state"), item.get("country"))
             for item in offer.get("locations") or [] if isinstance(item, dict)]
    found = [location for location in found if location]
    if not found:
        single = _place(offer.get("city"), offer.get("state_name"), offer.get("country"))
        found = [single] if single else []
    return list({location["text"].lower(): location for location in found}.values())


def _number(value):
    if isinstance(value, str) and re.fullmatch(r"\d+(\.\d+)?", value.strip()):
        return float(value)
    return value


def _pay(salary) -> dict | None:
    if not isinstance(salary, dict):
        return None
    return normalize.pay(_number(salary.get("min")), _number(salary.get("max")), salary.get("currency"),
                         PERIOD.get((salary.get("period") or "").lower()))


def _date(value) -> str | None:
    # The feed writes "2026-11-20 15:22:36 UTC".
    return normalize.iso_date(value.replace(" UTC", "")) if isinstance(value, str) else None


def _draft(offer: dict, board: str) -> dict:
    title = offer.get("title") or ""
    url = offer.get("careers_url") or ""
    if not url.startswith("https://") and offer.get("slug"):
        url = HOSTED.format(board=board, slug=offer["slug"])
    return normalize.draft(
        posting_id=str(offer.get("id") or ""),
        title=title,
        url=url,
        locations=_locations(offer),
        workplace=_workplace(offer),
        employment=_employment(offer.get("employment_type_code"), title),
        pay=_pay(offer.get("salary")),
        posted_date=_date(offer.get("published_at")) or _date(offer.get("created_at")),
        department=normalize.department(offer.get("department")),
        description_text=join_text(html_to_text(offer.get("description")), html_to_text(offer.get("requirements"))),
    )


def read(board: str, fetcher: Fetcher) -> list[dict]:
    answer = fetcher.get_json(API.format(board=board))
    return [_draft(offer, board) for offer in answer["offers"]
            if isinstance(offer, dict) and offer.get("status", "published") == "published"]
