"""Ashby reader.

Documentation: https://developers.ashbyhq.com/docs/public-job-posting-api

    GET https://api.ashbyhq.com/posting-api/job-board/{JOB_BOARD_NAME}?includeCompensation=true

The board name is case-sensitive. The page states no authentication, no rate
limit and no terms for automated use; it describes the feed as the data a
company uses to build its own careers page.

Fields read: title, jobUrl, id (present in every answer, though the page does
not list it), location, address.postalAddress (addressLocality, addressRegion,
addressCountry), secondaryLocations[] (location, address), workplaceType,
employmentType, department, team, publishedAt, descriptionPlain (or
descriptionHtml), isListed, and compensation.summaryComponents[]
(compensationType, interval, currencyCode, minValue, maxValue).

A posting with isListed false is reachable only by direct link and is left out.
"""
from __future__ import annotations

from pipeline.collect import normalize
from pipeline.collect.fetch import Fetcher
from pipeline.collect.locations import parse_location, split_locations, structured_location
from pipeline.collect.text import collapse, html_to_text
from pipeline.seed.import_old_hub import parse_source

API = "https://api.ashbyhq.com/posting-api/job-board/{board}"

WORKPLACE = {"onsite": "onsite", "remote": "remote", "hybrid": "hybrid"}
EMPLOYMENT = {
    "fulltime": "full-time", "parttime": "part-time", "intern": "intern",
    "contract": "contract", "temporary": "contract",
}
# The page shows "1 YEAR" in its example and lists no other values.
PERIOD = {"1 YEAR": "year", "1 HOUR": "hour"}


def _pay(compensation) -> dict | None:
    if not isinstance(compensation, dict):
        return None
    for component in compensation.get("summaryComponents") or []:
        if not isinstance(component, dict) or component.get("compensationType") != "Salary":
            continue
        found = normalize.pay(
            component.get("minValue"), component.get("maxValue"),
            component.get("currencyCode"), PERIOD.get(component.get("interval")),
        )
        if found:
            return found
    return None


def _place(text: str | None, address: dict | None) -> list[dict]:
    """One feed location: structured when the feed gives an address, else parsed."""
    text = (text or "").strip()
    postal = (address or {}).get("postalAddress") or address or {}
    city, region, country = (postal.get(key) for key in ("addressLocality", "addressRegion", "addressCountry"))
    if text and (city or region or country) and len(split_locations(text)) <= 1:
        return [structured_location(text, city, region, country)]
    return [parse_location(piece) for piece in split_locations(text)]


def _draft(job: dict) -> dict:
    url = job.get("jobUrl") or ""
    posting = parse_source(url)["posting_id"] or job.get("id")
    locations = _place(job.get("location"), job.get("address"))
    for extra in job.get("secondaryLocations") or []:
        locations += _place(extra.get("location"), extra.get("address"))
    unique = list({location["text"].lower(): location for location in reversed(locations)}.values())[::-1]
    employment = EMPLOYMENT.get((job.get("employmentType") or "").lower())
    return normalize.draft(
        posting_id=str(posting) if posting else "",
        title=job.get("title") or "",
        url=url,
        locations=unique,
        workplace=WORKPLACE.get((job.get("workplaceType") or "").lower()),
        employment=employment or normalize.employment_from_title(job.get("title") or ""),
        pay=_pay(job.get("compensation")),
        posted_date=normalize.iso_date(job.get("publishedAt")),
        department=normalize.department(job.get("department"), job.get("team")),
        description_text=collapse(job["descriptionPlain"]) if job.get("descriptionPlain") else html_to_text(job.get("descriptionHtml")),
    )


def read(board: str, fetcher: Fetcher) -> list[dict]:
    answer = fetcher.get_json(API.format(board=board), {"includeCompensation": "true"})
    return [_draft(job) for job in answer["jobs"] if job.get("isListed", True)]
