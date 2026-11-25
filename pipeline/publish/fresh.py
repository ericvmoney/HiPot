"""New roles: first seen in the last 3 business days (decision 15).

A role is new when its `first_seen` date, in Mountain time, falls on or after the third
business day (Monday to Friday, no holiday calendar) counting back from the date of the
board's `generated_at`, that date included. Generated on a Tuesday, the window is Friday,
Monday and Tuesday, with the weekend between.

The first collection of a company is not news: every role on its board looks new then,
whether the company has just been added to the registry or the collector has just been
set up on a fresh machine. The collector's state keeps no run history yet, so:

- Roles whose first_seen the collector primed from the old hub's seed (`data/seed/jobs.json`
  ids) are never new and do not count towards a company's first collection.
- A company's first collection is taken to be the earliest `first_seen` among its other
  roles in the jobs file, and a role first seen within `FIRST_RUN_HOURS` of that is never
  flagged.

Caveat: once every role from a company's first collection has closed, its earliest
remaining role becomes the baseline and is not flagged either. A run history in
`data/state/` (when each company was first collected) would remove that guess.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Iterable
from zoneinfo import ZoneInfo

MOUNTAIN = ZoneInfo("America/Denver")
BUSINESS_DAYS = 3
FIRST_RUN_HOURS = 6


def _parse(stamp: str) -> datetime:
    when = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    return when if when.tzinfo else when.replace(tzinfo=MOUNTAIN)


def mountain_date(stamp: str) -> date:
    return _parse(stamp).astimezone(MOUNTAIN).date()


def window_start(generated_at: str, business_days: int = BUSINESS_DAYS) -> date:
    """The earliest date that still counts as new."""
    day, counted = mountain_date(generated_at), 0
    while True:
        if day.weekday() < 5:
            counted += 1
            if counted == business_days:
                return day
        day -= timedelta(days=1)


def first_collection(jobs: Iterable[dict], seed_ids: set[str] = frozenset()) -> dict[str, datetime]:
    """Each company's earliest first_seen in the jobs file, seed-primed roles left out."""
    earliest: dict[str, datetime] = {}
    for job in jobs:
        if job["id"] in seed_ids:
            continue
        seen = _parse(job["first_seen"])
        if job["company_id"] not in earliest or seen < earliest[job["company_id"]]:
            earliest[job["company_id"]] = seen
    return earliest


def new_role_ids(jobs: list[dict], generated_at: str, baselines: dict[str, datetime] | None = None,
                 seed_ids: set[str] = frozenset()) -> set[str]:
    """Ids of the roles that count as new on a board generated at `generated_at`."""
    start = window_start(generated_at)
    baselines = baselines if baselines is not None else first_collection(jobs, seed_ids)
    found = set()
    for job in jobs:
        if job["id"] in seed_ids or job["company_id"] not in baselines:
            continue
        seen = _parse(job["first_seen"])
        if seen - baselines[job["company_id"]] <= timedelta(hours=FIRST_RUN_HOURS):
            continue
        if mountain_date(job["first_seen"]) >= start:
            found.add(job["id"])
    return found
