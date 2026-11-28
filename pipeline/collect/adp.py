"""ADP Workforce Now career-center reader, read weekly (PLAN.md decision 24).

ADP documents only its authenticated staffing API. A company's public career
center (recruitment.html?cid=...) is a JavaScript page that reads its
postings from a public JSON address, as seen working on 2026-11-27 with no
sign-in and no session:

    GET https://workforcenow.adp.com/mascsr/default/careercenter/public/events/staffing/v1/job-requisitions
        ?cid={cid}&ccId={ccId}&lang=en_US&locale=en_US&$top=20&$skip=N
    GET .../job-requisitions/{itemID}?cid=...      one per posting, for its description

The board token is the company's cid (a GUID), or the whole career-center
address with its cid= and ccId= (ccId defaults to 19000101_000001).

robots.txt on workforcenow.adp.com answers with a redirect to ADP's sign-in
page. The owner decided (decision 24) that public career-center listings are
read at most weekly; run.py wraps this reader in weekly.reader. This reader
never asks robots.txt, the sign-in page or anything behind a sign-in: a
redirect is not followed, and an answer that is not the JSON list stops the
company. ADP's terms (adp.com/legal.aspx) bar sending "more requests to ADP
servers than a human can reasonably produce" (section 3) and name data
scrapers (section 10); whether they cover career centers is not stated. ADP
is on the section 8 risk list.

Fields: itemID, requisitionTitle, requisitionLocations (address cityName,
countrySubdivisionLevel1.codeValue; nameCode.shortName " Longmont, CO, US"),
workLevelCode.shortName ("Full-Time Salary"), postDate, payGradeRange
(minimumRate/maximumRate amountValue, currencyCode), customFieldGroup
(SalaryType AN or HR, ExternalJobID, PostingDate), meta.totalNumber; the
detail adds requisitionDescription (HTML).

A posting's own address is the career center with &jobId={ExternalJobID},
which is the address ADP's page shows when a posting is opened (checked in a
browser on 2026-11-27).
"""
from __future__ import annotations

import re
from urllib.parse import parse_qs, urlencode, urlsplit

from pipeline.collect import normalize
from pipeline.collect.fetch import Blocked, FetchError, Fetcher
from pipeline.collect.locations import parse_location, structured_location
from pipeline.collect.text import html_to_text

API = "https://workforcenow.adp.com/mascsr/default/careercenter/public/events/staffing/v1/job-requisitions"
CAREER_CENTER = "https://workforcenow.adp.com/mascsr/default/mdf/recruitment/recruitment.html"
DEFAULT_CC = "19000101_000001"
PAGE_SIZE = 20
MAX_PAGES = 25
PERIOD = {"AN": "year", "ANNUAL": "year", "HR": "hour", "HOURLY": "hour"}
_GUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


def ids(board: str) -> tuple[str, str]:
    """(cid, ccId) from a cid or a career-center address."""
    board = board.strip()
    if _GUID.match(board):
        return board, DEFAULT_CC
    query = parse_qs(urlsplit(board).query)
    cid = (query.get("cid") or [""])[0]
    if not _GUID.match(cid):
        raise FetchError(f"no cid in the ADP board {board!r}")
    return cid, (query.get("ccId") or [DEFAULT_CC])[0]


def _fields(item: dict, kind: str) -> dict:
    """customFieldGroup's {name: value} for one kind of field ("codeFields", "stringFields", ...)."""
    found = {}
    for field in ((item.get("customFieldGroup") or {}).get(kind) or []):
        if not isinstance(field, dict):
            continue
        name = (field.get("nameCode") or field.get("categoryCode") or {}).get("codeValue")
        value = field.get("codeValue") if kind == "codeFields" else field.get("stringValue") if kind == "stringFields" \
            else field.get("dateValue") if kind == "dateFields" else None
        if name and value is not None:
            found[name] = value
    return found


def place(location: dict) -> dict | None:
    if not isinstance(location, dict):
        return None
    text = " ".join(((location.get("nameCode") or {}).get("shortName") or "").split())
    address = location.get("address") or {}
    city = address.get("cityName")
    state = (address.get("countrySubdivisionLevel1") or {}).get("codeValue")
    if not text:
        text = ", ".join(part for part in (city, state) if part)
    if not text:
        return None
    # "Longmont, CO, US"; "Remote - CO" names only a state.
    remote = re.fullmatch(r"Remote\s*-\s*([A-Z]{2})", text)
    if remote:
        return parse_location(f"Remote, {remote.group(1)}, US") | {"text": text}
    country = text.rsplit(",", 1)[-1].strip() if text.count(",") >= 2 else None
    return structured_location(text, city, state, country)


def pay(item: dict) -> dict | None:
    """The range the career center publishes, with its period; nothing without one."""
    grade = item.get("payGradeRange") or {}
    low, high = grade.get("minimumRate") or {}, grade.get("maximumRate") or {}
    period = PERIOD.get(str(_fields(item, "codeFields").get("SalaryType") or "").upper())
    return normalize.pay(low.get("amountValue"), high.get("amountValue"),
                         low.get("currencyCode") or high.get("currencyCode"), period)


def posting_url(cid: str, cc: str, item: dict) -> str:
    job = _fields(item, "stringFields").get("ExternalJobID")
    query = {"cid": cid, "ccId": cc, "source": "CC2", "lang": "en_US", "selectedMenuKey": "CurrentOpenings"}
    if job:
        query["jobId"] = job
    return f"{CAREER_CENTER}?{urlencode(query)}"


def _draft(cid: str, cc: str, item: dict, description: str) -> dict:
    title = " ".join((item.get("requisitionTitle") or "").split())
    places = [found for found in (place(location) for location in item.get("requisitionLocations") or []) if found]
    kind = normalize.employment_from_title(title)
    if kind == "unknown":
        kind = normalize.employment_from_text((item.get("workLevelCode") or {}).get("shortName"))
    posted = _fields(item, "dateFields").get("PostingDate") or item.get("postDate")
    return normalize.draft(
        posting_id=str(item.get("itemID")),
        title=title,
        url=posting_url(cid, cc, item),
        locations=list({location["text"].lower(): location for location in places}.values()),
        workplace="remote" if any(location["text"].lower().startswith("remote") for location in places) else None,
        employment=kind,
        pay=pay(item),
        posted_date=normalize.iso_date(posted),
        department=None,
        description_text=description,
    )


def read(board: str, fetcher: Fetcher) -> list[dict]:
    cid, cc = ids(board)
    common = {"cid": cid, "ccId": cc, "lang": "en_US", "locale": "en_US"}
    listed, seen, total = [], set(), None
    for number in range(MAX_PAGES):
        try:
            answer = fetcher.get_json(API, {**common, "$top": str(PAGE_SIZE), "$skip": str(number * PAGE_SIZE)})
        except Blocked:
            raise
        except FetchError as error:
            # A redirect (to the sign-in page) or a 401 means the list is no longer public: stop there.
            if re.match(r"HTTP (?:30\d|401)\b", str(error)):
                raise Blocked(f"ADP asked for a sign-in or session ({error}); nothing behind it is read") from error
            raise
        if not isinstance(answer, dict) or not isinstance(answer.get("jobRequisitions"), list):
            raise FetchError("answer has no list of job requisitions (a sign-in or session would be needed)")
        found = [item for item in answer["jobRequisitions"]
                 if isinstance(item, dict) and item.get("itemID") and item["itemID"] not in seen]
        seen.update(item["itemID"] for item in found)
        listed += found
        meta = answer.get("meta") or {}
        total = meta.get("totalNumber") if isinstance(meta.get("totalNumber"), int) else total
        if not found or (total is not None and len(listed) >= total):
            break

    drafts = []
    details = normalize.Details()
    for item in listed:
        # A failed request keeps the posting from the list, without its description.
        more = details.ask(lambda: fetcher.get_json(f"{API}/{item['itemID']}", common), default={})
        description = html_to_text(more.get("requisitionDescription")) if isinstance(more, dict) else ""
        drafts.append(_draft(cid, cc, item, description))
    return details.result(drafts)
