"""SmartRecruiters reader. Its terms restrict automated reading: see below.

Documentation: the Posting API,
https://developers.smartrecruiters.com/reference/v1listpostings and
https://developers.smartrecruiters.com/reference/v1getposting (updated 2026-04-23).

    GET https://api.smartrecruiters.com/v1/companies/{companyIdentifier}/postings?limit=100&offset=N
    GET https://api.smartrecruiters.com/v1/companies/{companyIdentifier}/postings/{postingId}

The reference allows calls without a key for public postings; the overview page
mentions only API keys and OAuth. `limit` is at most 100, so the list is paged
with `offset` until `totalFound` is reached. The list has no description, pay
or posting address, so the reader makes one detail request per posting. The
documented limit is 10 requests a second; the collector asks one a second.

Terms: the developer site says use of the APIs "is governed by the SAP API
Policy" (https://developers.smartrecruiters.com/docs/the-smartrecruiters-platform).
That policy (v.4.2026a, section 2.2.2(b)) prohibits "scraping, harvesting, or
systematic and/or large-scale data extraction". robots.txt on
api.smartrecruiters.com also disallows every client but LinkedInBot. The reader
runs by the owner's decision (PLAN.md decision 6), at most one request every
6 s to the host; --disable-reader smartrecruiters turns it off for a run.

Fields read. List: id, name, releasedDate, location (city, region, country,
fullLocation, remote, hybrid), department.label, typeOfEmployment, totalFound.
Detail: postingUrl, jobAd.sections.*.text (HTML), compensation (min, max,
currency, period).
"""
from __future__ import annotations

from pipeline.collect import normalize
from pipeline.collect.fetch import Blocked, FetchError, Fetcher
from pipeline.collect.locations import structured_location
from pipeline.collect.text import html_to_text, join_text

API = "https://api.smartrecruiters.com/v1/companies/{board}/postings"
HOSTED = "https://jobs.smartrecruiters.com/{board}/{posting}"
PAGE = 100
MAX_PAGES = 50          # 5,000 postings: a guard against a feed that never ends
PERIOD = {"YEARLY": "year", "HOURLY": "hour"}
SECTIONS = ("jobDescription", "qualifications", "additionalInformation", "companyDescription")


def _location(place) -> list[dict]:
    if not isinstance(place, dict):
        return []
    city, region, country = place.get("city"), place.get("region"), (place.get("country") or "").upper() or None
    # fullLocation keeps empty parts ("Remote, , United States"); they are dropped.
    full = ", ".join(part.strip() for part in (place.get("fullLocation") or "").split(",") if part.strip())
    text = full or ", ".join(part for part in (city, region, country) if part)
    return [structured_location(text, city, region, country)] if text else []


def _workplace(place) -> str | None:
    if not isinstance(place, dict):
        return None
    if place.get("remote") is True:
        return "remote"
    if place.get("hybrid") is True:
        return "hybrid"
    if (place.get("city") or "").strip().lower() == "remote":
        # The flags say on-site but the place is "Remote": the location rules decide.
        return None
    # The API filters on locationType REMOTE, HYBRID or ONSITE, so two explicit
    # false flags mean on-site.
    if place.get("remote") is False and place.get("hybrid") is False:
        return "onsite"
    return None


def _pay(compensation) -> dict | None:
    if not isinstance(compensation, dict):
        return None
    return normalize.pay(compensation.get("min"), compensation.get("max"), compensation.get("currency"),
                         PERIOD.get((compensation.get("period") or "").upper()))


def _description(detail: dict) -> str:
    sections = ((detail.get("jobAd") or {}).get("sections")) or {}
    return join_text(*(html_to_text((sections.get(name) or {}).get("text")) for name in SECTIONS))


def _draft(item: dict, detail: dict, board: str) -> dict:
    posting = str(item.get("id") or "")
    title = item.get("name") or detail.get("name") or ""
    url = detail.get("postingUrl") or ""
    if not url.startswith("https://"):
        url = HOSTED.format(board=board, posting=posting)
    kind = item.get("typeOfEmployment") or {}
    employment = normalize.employment_from_text(kind.get("label") or kind.get("id"))
    place = item.get("location") or detail.get("location")
    return normalize.draft(
        posting_id=posting,
        title=title,
        url=url,
        locations=_location(place),
        workplace=_workplace(place),
        employment=employment if employment != "unknown" else normalize.employment_from_title(title),
        pay=_pay(detail.get("compensation")),
        posted_date=normalize.iso_date(item.get("releasedDate")),
        department=normalize.department((item.get("department") or {}).get("label")),
        description_text=_description(detail),
    )


def read(board: str, fetcher: Fetcher) -> list[dict]:
    base = API.format(board=board)
    items: list[dict] = []
    for page in range(MAX_PAGES):
        # The offset is written into the address so each page is saved apart.
        answer = fetcher.get_json(f"{base}?limit={PAGE}&offset={page * PAGE}")
        content = answer.get("content") or []
        items += [item for item in content if isinstance(item, dict) and item.get("id")]
        if not content or len(items) >= (answer.get("totalFound") or 0):
            break
    drafts = []
    details = normalize.Details()
    for item in items:
        # A failed request keeps the posting from the list without its description.
        detail = details.ask(lambda: fetcher.get_json(f"{base}/{item['id']}"), default={})
        drafts.append(_draft(item, detail if isinstance(detail, dict) else {}, board))
    return details.result(drafts)
