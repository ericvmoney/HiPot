"""Lever reader.

Documentation: https://github.com/lever/postings-api (Postings API README).

    GET https://api.lever.co/v0/postings/{site}?mode=json

No key for GET. The README says published postings "are publicly viewable"
and "may be scraped by third parties"; it states no rate limit for GET.

Fields read: id, text, hostedUrl, categories (location, allLocations,
commitment, department, team), country, workplaceType, salaryRange (currency,
interval, min, max), descriptionPlain, lists[] (text, content), additionalPlain,
salaryDescriptionPlain, and createdAt (present in every answer, though the
README does not list it).
"""
from __future__ import annotations

from pipeline.collect import normalize
from pipeline.collect.fetch import Fetcher
from pipeline.collect.locations import parse_location, split_locations
from pipeline.collect.text import html_to_text, join_text

API = "https://api.lever.co/v0/postings/{board}"

WORKPLACE = {"on-site": "onsite", "onsite": "onsite", "remote": "remote", "hybrid": "hybrid"}
# The README does not list the interval values. These are the ones the feeds use.
PERIOD = {"per-year-salary": "year", "per-hour-wage": "hour"}


def _pay(salary) -> dict | None:
    if not isinstance(salary, dict):
        return None
    return normalize.pay(salary.get("min"), salary.get("max"), salary.get("currency"), PERIOD.get(salary.get("interval")))


def _draft(posting: dict) -> dict:
    categories = posting.get("categories") or {}
    places = categories.get("allLocations") or ([categories["location"]] if categories.get("location") else [])
    pieces = [piece for place in places for piece in split_locations(place)]
    locations = [parse_location(piece) for piece in dict.fromkeys(pieces)]
    country = posting.get("country")
    if len(locations) == 1 and "country" not in locations[0] and isinstance(country, str) and len(country) == 2:
        # The feed states one country for the posting; safe to attach when
        # there is a single place.
        locations[0]["country"] = country.upper()
    lists = [f"{item.get('text') or ''}\n{html_to_text(item.get('content'))}" for item in posting.get("lists") or []]
    commitment = normalize.employment_from_text(categories.get("commitment"))
    return normalize.draft(
        posting_id=str(posting["id"]),
        title=posting.get("text") or "",
        url=posting.get("hostedUrl") or "",
        locations=locations,
        workplace=WORKPLACE.get((posting.get("workplaceType") or "").lower()),
        employment=commitment if commitment != "unknown" else normalize.employment_from_title(posting.get("text") or ""),
        pay=_pay(posting.get("salaryRange")),
        posted_date=normalize.epoch_ms_date(posting.get("createdAt")),
        department=normalize.department(categories.get("department"), categories.get("team")),
        description_text=join_text(
            posting.get("descriptionPlain"), *lists, posting.get("additionalPlain"),
            posting.get("salaryDescriptionPlain"),
        ),
    )


def read(board: str, fetcher: Fetcher) -> list[dict]:
    answer = fetcher.get_json(API.format(board=board), {"mode": "json"})
    if not isinstance(answer, list):
        raise ValueError(f"expected a list of postings, found {type(answer).__name__}")
    return [_draft(posting) for posting in answer]
