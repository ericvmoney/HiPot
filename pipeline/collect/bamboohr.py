"""BambooHR reader. Switched off by default (run.SWITCHED_OFF): see below.

BambooHR documents no public job feed. Its API documentation
(https://documentation.bamboohr.com) covers only the authenticated
applicant-tracking endpoints, which need a customer's key and are not used.
This reader uses the two JSON addresses the hosted careers page
(https://{company}.bamboohr.com/careers) loads, seen working on 2026-11-24:

    GET https://{company}.bamboohr.com/careers/list
    GET https://{company}.bamboohr.com/careers/{id}/detail

The list has no description, date or pay, so the reader makes one detail
request per posting. A company that no longer uses BambooHR answers 302 to
www.bamboohr.com, which the fetcher reports as a redirect.

Terms: BambooHR's Terms of Service (updated 2026-09-18,
https://www.bamboohr.com/legal/terms-of-service) say in section 4.2 that the
Service may not be used with "any robot, spider, other automated device" to
copy content. The careers pages are on the Service's domain, so the reader is
off until the owner decides.

Fields read. List: id, jobOpeningName, departmentLabel, employmentStatusLabel,
location (city, state), atsLocation, isRemote. Detail (result.jobOpening):
jobOpeningShareUrl, description (HTML), compensation (free text), datePosted,
location (city, state, addressCountry), atsLocation. `locationType` is not
read: its values ("0" on every posting seen) are not documented.

Pay is free text ("$90,000 to $115,000") with no period, so it is not turned
into structured pay; it is added to the description text for the tagger.
"""
from __future__ import annotations

from pipeline.collect import normalize
from pipeline.collect.fetch import Blocked, FetchError, Fetcher
from pipeline.collect.locations import structured_location
from pipeline.collect.text import html_to_text, join_text

BASE = "https://{board}.bamboohr.com/careers"


def _place(*sources) -> list[dict]:
    for source in sources:
        if not isinstance(source, dict):
            continue
        city, region = source.get("city"), source.get("state") or source.get("province")
        country = source.get("addressCountry") or source.get("country")
        parts = [part.strip() for part in (city, region, country) if isinstance(part, str) and part.strip()]
        if parts:
            return [structured_location(", ".join(parts), city, region, country)]
    return []


def _draft(item: dict, opening: dict, board: str) -> dict:
    posting = str(item.get("id") or "")
    title = opening.get("jobOpeningName") or item.get("jobOpeningName") or ""
    url = opening.get("jobOpeningShareUrl") or ""
    if not url.startswith("https://"):
        url = f"{BASE.format(board=board)}/{posting}"
    employment = normalize.employment_from_text(opening.get("employmentStatusLabel") or item.get("employmentStatusLabel"))
    compensation = (opening.get("compensation") or "").strip()
    return normalize.draft(
        posting_id=posting,
        title=title,
        url=url,
        locations=_place(opening.get("location"), opening.get("atsLocation"), item.get("location"), item.get("atsLocation")),
        workplace="remote" if (opening.get("isRemote") or item.get("isRemote")) is True else None,
        employment=employment if employment != "unknown" else normalize.employment_from_title(title),
        pay=None,
        posted_date=normalize.iso_date(opening.get("datePosted")),
        department=normalize.department(opening.get("departmentLabel") or item.get("departmentLabel")),
        description_text=join_text(html_to_text(opening.get("description")),
                                   f"Compensation: {compensation}" if compensation else None),
    )


def read(board: str, fetcher: Fetcher) -> list[dict]:
    base = BASE.format(board=board)
    answer = fetcher.get_json(f"{base}/list")
    drafts = []
    for item in answer.get("result") or []:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        try:
            detail = fetcher.get_json(f"{base}/{item['id']}/detail")
            opening = ((detail or {}).get("result") or {}).get("jobOpening") or {}
        except Blocked:
            raise
        except FetchError:
            opening = {}   # keep the posting from the list without its description
        drafts.append(_draft(item, opening, board))
    return drafts
