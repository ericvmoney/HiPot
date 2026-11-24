"""Gem reader.

Documentation: the Job Board API, https://api.gem.com/job_board/v0/reference
(OpenAPI at https://api.gem.com/job_board/v0/openapi.json, version v0) and
https://help.gem.com/databases/gem-help-center/the-job-board-api.

    GET https://api.gem.com/job_board/v0/{vanity_url_path}/job_posts/

No key: the documentation says most endpoints "are public and do not require
authentication" (only submitting an application needs one). The list holds
every post with its description; there is no paging. The documented limit is
20 requests a second per API key; nothing is said of calls without a key.

Terms: nothing found that prohibits reading. Gem's Terms of Service (2025-03-07)
and Acceptable Use Policy (2023-06-22) are written for customers; the API
documentation says the job board "can be read by anyone". api.gem.com
answered 403 to a request for /robots.txt during research, so there is no
robots file to read.

Fields read: id, title, absolute_url, location.name, offices[].location.name
(when there is no location), location_type (in_office, hybrid, remote),
employment_type (full_time, part_time, contract, temporary, intern),
departments[].name, first_published_at (or created_at), content (HTML) or
content_plain. There is no pay field.
"""
from __future__ import annotations

import re

from pipeline.collect import normalize
from pipeline.collect.fetch import FetchError, Fetcher
from pipeline.collect.locations import US_STATE_CODES, US_STATES, parse_location, split_locations
from pipeline.collect.text import collapse, html_to_text

API = "https://api.gem.com/job_board/v0/{board}/job_posts/"
WORKPLACE = {"in_office": "onsite", "onsite": "onsite", "hybrid": "hybrid", "remote": "remote"}
EMPLOYMENT = {"full_time": "full-time", "part_time": "part-time", "contract": "contract",
              "temporary": "contract", "intern": "intern", "internship": "intern"}


def _locations(post: dict) -> list[dict]:
    names = [((post.get("location") or {}).get("name") or "").strip()]
    if not names[0]:
        names = [((office.get("location") or {}).get("name") or office.get("name") or "").strip()
                 for office in post.get("offices") or [] if isinstance(office, dict)]
    pieces = [piece for name in names if name for piece in split_locations(name)]
    found = [_with_state(parse_location(piece), post) for piece in pieces]
    return list({location["text"].lower(): location for location in found}.values())


def _with_state(location: dict, post: dict) -> dict:
    """Gem's location is "{City}, {Country}" with no state. An office's display
    name often holds the address ("11261 Trade Center Drive Rancho Cordova, CA
    95742", "410 West Rd, Houston Texas 77038"); when one names the same city
    followed by a state code or state name, that state is used."""
    city = location.get("city")
    if not city and location.get("country") == "US":
        head = location["text"].split(",")[0].strip()
        if head and head != location["text"] and "remote" not in head.lower():
            city = head
    if location.get("country") != "US" or location.get("state") or not city:
        return location
    names = "|".join(re.escape(name) for name in sorted(US_STATES, key=len, reverse=True))
    pattern = re.compile(rf"\b{re.escape(city)},?\s+([A-Z]{{2}}\b|(?i:{names})\b)")
    for office in post.get("offices") or []:
        match = pattern.search((office or {}).get("name") or "")
        if not match:
            continue
        found = match.group(1)
        state = found if found in US_STATE_CODES else US_STATES.get(found.lower())
        if state:
            return {"text": location["text"], "city": city, "state": state, "country": "US"}
    return location


def _draft(post: dict) -> dict:
    title = post.get("title") or ""
    employment = EMPLOYMENT.get((post.get("employment_type") or "").lower())
    return normalize.draft(
        posting_id=str(post.get("id") or ""),
        title=title,
        url=post.get("absolute_url") or "",
        locations=_locations(post),
        workplace=WORKPLACE.get((post.get("location_type") or "").lower()),
        employment=employment or normalize.employment_from_title(title),
        pay=None,
        posted_date=normalize.iso_date(post.get("first_published_at")) or normalize.iso_date(post.get("created_at")),
        department=normalize.department(*(d.get("name") for d in post.get("departments") or [] if isinstance(d, dict))),
        description_text=html_to_text(post.get("content")) or collapse(post.get("content_plain") or ""),
    )


def read(board: str, fetcher: Fetcher) -> list[dict]:
    answer = fetcher.get_json(API.format(board=board))
    if not isinstance(answer, list):
        raise FetchError("answer was not a list of job posts")
    return [_draft(post) for post in answer if isinstance(post, dict) and post.get("id")]
