"""UKG UltiPro (UKG Pro Recruiting) reader, read weekly (PLAN.md decision 24).

UKG documents no public job feed. A company's job board is a page on
recruiting.ultipro.com (or recruiting2.ultipro.com) that asks for its list
with a POST, as seen working on 2026-11-27:

    POST https://{board}/JobBoardView/LoadSearchResults
         {"opportunitySearch": {"Top": 50, "Skip": N, "QueryString": "", "OrderBy": [...], "Filters": []}}
    GET  https://{board}/OpportunityDetail?opportunityId={id}     one per posting

The board token is "{host}/{tenant}/JobBoard/{board id}", e.g.
"recruiting.ultipro.com/POW1009POWS/JobBoard/42398959-f1c7-48da-a3e2-94e525e29808".

robots.txt on the UltiPro hosts allows the board and OpportunityDetail pages
but disallows */JobBoardView, so the list request is disallowed. The owner
allowed it to be read at most weekly (decision 24); run.py wraps this reader
in weekly.reader. UKG's terms page answered 403 to the research pass; search
results quote it barring "robot, spider, scraper or other automated means"
(not verified), so UKG is on the section 8 risk list.

List fields: Id, Title, RequisitionNumber, FullTime, JobCategoryName,
PostedDate, Locations[].Address (City, State.Code, Country.Code "USA"),
totalCount. The posting page carries the same object with Description (HTML)
and the compensation fields. Pay is kept only when PayRangeVisible is true:
boards also send CompensationAnnualMinimum and the like for postings that do
not show them (Yaskawa's did, with PayRangeVisible false), and those are not
published pay.
"""
from __future__ import annotations

import json
import re
from urllib.parse import urlsplit

from pipeline.collect import normalize
from pipeline.collect.fetch import Blocked, FetchError, Fetcher
from pipeline.collect.locations import structured_location
from pipeline.collect.probe_careers import refusal
from pipeline.collect.text import html_to_text

PAGE_SIZE = 50
MAX_PAGES = 20
ORDER = [{"Value": "postedDateDesc", "PropertyName": "PostedDate", "Ascending": False}]
_DETAIL = re.compile(r"US\.Opportunity\.CandidateOpportunityDetail\((\{.*?\})\);", re.S)
COUNTRIES = {"USA": "US", "CAN": "CA", "MEX": "MX", "GBR": "GB", "DEU": "DE", "IND": "IN", "CHN": "CN", "JPN": "JP"}


def search(skip: int) -> dict:
    return {"opportunitySearch": {"Top": PAGE_SIZE, "Skip": skip, "QueryString": "", "OrderBy": ORDER, "Filters": []}}


def place(location: dict) -> dict | None:
    address = location.get("Address") if isinstance(location, dict) else None
    if not isinstance(address, dict):
        return None
    city = address.get("City")
    state = (address.get("State") or {}).get("Code")
    code = (address.get("Country") or {}).get("Code")
    country = COUNTRIES.get(code, code if code and len(code) == 2 else None)
    text = location.get("LocalizedName") or ", ".join(part for part in (city, state) if part)
    return structured_location(text, city, state, country) if text else None


def detail(page: str) -> dict:
    match = _DETAIL.search(page or "")
    if not match:
        return {}
    try:
        found = json.loads(match.group(1))
    except ValueError:
        return {}
    return found if isinstance(found, dict) else {}


def _number(value) -> float | None:
    """UKG writes amounts as numbers or as strings ("86000.00")."""
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def published_pay(item: dict) -> dict | None:
    """The pay range the posting shows; nothing when the board hides it."""
    if item.get("PayRangeVisible") is not True:
        return None
    shown = item.get("PayRange") or {}
    low, high = _number(shown.get("PayRangeMinimum")), _number(shown.get("PayRangeMaximum"))
    currency = item.get("PayRangeCurrencyCode") or item.get("CompensationCurrencyCode")
    return normalize.pay(low, high, currency, "year" if item.get("Salaried") else "hour")


def _draft(item: dict, url: str, more: dict) -> dict:
    merged = {**item, **{key: value for key, value in more.items() if value is not None}}
    title = merged.get("Title") or ""
    places = [found for found in (place(location) for location in merged.get("Locations") or []) if found]
    from_title = normalize.employment_from_title(title)
    if from_title != "unknown":
        employment = from_title
    else:
        employment = {True: "full-time", False: "part-time"}.get(merged.get("FullTime"), "unknown")
    return normalize.draft(
        posting_id=str(item.get("Id")),
        title=title,
        url=url,
        locations=list({location["text"].lower(): location for location in places}.values()),
        workplace=None,          # JobLocationType is a number whose meaning UKG does not document
        employment=employment,
        pay=published_pay(more) if more else None,
        posted_date=normalize.iso_date(merged.get("PostedDate")),
        department=normalize.department(merged.get("JobCategoryName")),
        description_text=html_to_text(more.get("Description")) or html_to_text(item.get("BriefDescription")),
    )


def read(board: str, fetcher: Fetcher) -> list[dict]:
    board = board.strip("/")
    host = board.split("/")[0].lower()
    stay = lambda url: urlsplit(url).netloc.lower() == host
    listed, seen = [], set()
    total = None
    for number in range(MAX_PAGES):
        answer = fetcher.post_json(f"https://{board}/JobBoardView/LoadSearchResults", search(number * PAGE_SIZE))
        if not isinstance(answer, dict) or not isinstance(answer.get("opportunities"), list):
            raise FetchError("answer has no list of opportunities")
        found = [item for item in answer["opportunities"] if isinstance(item, dict) and item.get("Id") and item["Id"] not in seen]
        seen.update(item["Id"] for item in found)
        listed += found
        total = answer.get("totalCount") if isinstance(answer.get("totalCount"), int) else total
        if not found or (total is not None and len(listed) >= total):
            break

    drafts = []
    details = normalize.Details()
    for item in listed:
        url = f"https://{board}/OpportunityDetail?opportunityId={item['Id']}"
        # A failed page keeps the posting from the list, with its short description and no pay.
        _final, page = details.ask(lambda: fetcher.get_page(url, stay), default=("", ""))
        why = refusal(page) if page else None
        if why:
            raise Blocked(f"{why} on {host}")
        drafts.append(_draft(item, url, detail(page)))
    return details.result(drafts)
