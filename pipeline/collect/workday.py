"""Workday reader.

Workday documents no public job feed. Every Workday careers site
(https://{tenant}.wd{N}.myworkdayjobs.com/{site}) loads its postings from two
JSON addresses on the same host, which this reader uses:

    POST https://{tenant}.wd{N}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs
         {"appliedFacets": {}, "limit": 20, "offset": N, "searchText": ""}
    GET  https://{tenant}.wd{N}.myworkdayjobs.com/wday/cxs/{tenant}/{site}{externalPath}

The search is a POST that reads and changes nothing. It answers 20 postings a
page; `total` is reliable only on the first page, so it is kept from there.
The list has title, location text and a relative date ("Posted 3 Days Ago"),
so the reader asks each posting for its description, locations, time type and
start date: one request per posting. Hosts get 2 s between requests
(fetch.HOST_INTERVALS).

The board token is "{tenant}.wd{N}/{site}", for example
"solvenergy.wd1/SOLV_External_Career": the host's tenant and wd number and the
site name from the careers site address.

Terms: see the A1 report (recorded for the owner's risk list; the reader is on
by default under the standing rule, PLAN.md decision 6).

Fields read. Search: total, jobPostings[] (title, externalPath, locationsText,
bulletFields). Posting: jobPostingInfo (title, jobDescription (HTML),
location, additionalLocations, country.descriptor, timeType, remoteType,
startDate, jobReqId, externalUrl). There is no structured pay.
"""
from __future__ import annotations

import re

from pipeline.collect import normalize
from pipeline.collect.fetch import Blocked, FetchError, Fetcher
from pipeline.collect.locations import parse_location, split_locations
from pipeline.collect.text import html_to_text

PAGE = 20
# A guard against a feed that never ends, set above the largest real board: GE Vernova's
# holds about 2,260, read in full by the owner's decision (PLAN.md decision 20).
MAX_POSTINGS = 4000
_BOARD = re.compile(r"^([A-Za-z0-9_-]+)\.(wd\d+)/([A-Za-z0-9_.\-]+)$")


def parse_board(board: str) -> tuple[str, str, str]:
    match = _BOARD.match(board or "")
    if not match:
        raise FetchError(f"Workday board must be '{{tenant}}.wd{{N}}/{{site}}', not {board!r}")
    return match.groups()


def addresses(board: str) -> tuple[str, str, str]:
    """(search address, posting-API prefix, public posting prefix)."""
    tenant, wd, site = parse_board(board)
    host = f"https://{tenant}.{wd}.myworkdayjobs.com"
    return f"{host}/wday/cxs/{tenant}/{site}/jobs", f"{host}/wday/cxs/{tenant}/{site}", f"{host}/{site}"


def _posting_id(info: dict, path: str) -> str:
    if isinstance(info.get("jobReqId"), str) and info["jobReqId"].strip():
        return info["jobReqId"].strip()
    tail = path.rstrip("/").rsplit("/", 1)[-1]
    return tail.rsplit("_", 1)[-1] if "_" in tail else tail


def _locations(info: dict, listed: str | None) -> list[dict]:
    texts = [info.get("location")] + list(info.get("additionalLocations") or [])
    texts = [text for text in texts if isinstance(text, str) and text.strip()] or ([listed] if listed else [])
    found = [parse_location(piece) for text in texts for piece in split_locations(text)]
    country = ((info.get("country") or {}).get("descriptor") or "") if isinstance(info.get("country"), dict) else ""
    if country and len(found) == 1 and "country" not in found[0]:
        enriched = parse_location(f"{found[0]['text']}, {country}")
        if enriched.get("country"):
            found = [{**enriched, "text": found[0]["text"]}]
    return list({location["text"].lower(): location for location in found}.values())


def _workplace(info: dict) -> str | None:
    kind = (info.get("remoteType") or "").lower()
    if "hybrid" in kind:
        return "hybrid"
    if "remote" in kind:
        return "remote"
    if "on-site" in kind or "onsite" in kind or "on site" in kind:
        return "onsite"
    return None


def _draft(listed: dict, info: dict, public_prefix: str) -> dict:
    path = listed.get("externalPath") or info.get("externalPath") or ""
    title = info.get("title") or listed.get("title") or ""
    url = info.get("externalUrl") if str(info.get("externalUrl") or "").startswith("https://") else f"{public_prefix}{path}"
    employment = normalize.employment_from_text(info.get("timeType"))
    title_kind = normalize.employment_from_title(title)
    if title_kind in ("intern", "contract"):
        employment = title_kind
    return normalize.draft(
        posting_id=_posting_id(info, path),
        title=title,
        url=url,
        locations=_locations(info, listed.get("locationsText")),
        workplace=_workplace(info),
        employment=employment if employment != "unknown" else title_kind,
        pay=None,
        posted_date=normalize.iso_date(info.get("startDate")) if isinstance(info.get("startDate"), str) else None,
        department=None,
        description_text=html_to_text(info.get("jobDescription")),
    )


def read(board: str, fetcher: Fetcher) -> list[dict]:
    search, api_prefix, public_prefix = addresses(board)
    listed, total, offset = [], None, 0
    while offset < MAX_POSTINGS:
        answer = fetcher.post_json(search, {"appliedFacets": {}, "limit": PAGE, "offset": offset, "searchText": ""})
        page = [item for item in answer.get("jobPostings") or [] if isinstance(item, dict) and item.get("externalPath")]
        if total is None:
            total = answer.get("total") or 0
        listed += page
        offset += PAGE
        if not page or offset >= total:
            break
    drafts, seen = [], set()
    for item in listed:
        if item["externalPath"] in seen:
            continue
        seen.add(item["externalPath"])
        try:
            info = (fetcher.get_json(f"{api_prefix}{item['externalPath']}") or {}).get("jobPostingInfo") or {}
        except Blocked:
            raise
        except FetchError:
            info = {}      # keep the posting from the list without its description
        drafts.append(_draft(item, info, public_prefix))
    return drafts
