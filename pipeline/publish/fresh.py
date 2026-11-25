"""New roles: first seen in the last 3 business days (decision 15).

A role is new when its `first_seen` date, in Mountain time, falls on or after the third
business day (Monday to Friday, no holiday calendar) counting back from the date of the
board's `generated_at`, that date included. Generated on a Tuesday, the window is Friday,
Monday and Tuesday, with the weekend between.

The first read of a company is not news: every role on its board looks new then, whether
the company has just been added to the registry or the collector has just been set up on a
fresh machine. So a role first seen before the company's first read ended is never new:

- Run history (`data/state/runs.json`, written by the collector): a company's first read is
  the first run whose `read` list holds it, and it ends at that run's `finished_at`.
- Inference, for companies the history does not cover (it starts with the first run after
  it was added): the earliest `first_seen` among the company's roles, and the read is taken
  to end `FIRST_RUN_HOURS` later.
- When both exist, the earlier start wins: a company read before the history began keeps
  its inferred first read; one whose first-read roles have all closed still has its run.
- Roles whose first_seen the collector primed from the old hub's seed (`data/seed/jobs.json`
  ids) are never new and do not count towards a company's first read.
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
    """Inferred: each company's earliest first_seen in the jobs file, seed-primed roles left out."""
    earliest: dict[str, datetime] = {}
    for job in jobs:
        if job["id"] in seed_ids:
            continue
        seen = _parse(job["first_seen"])
        if job["company_id"] not in earliest or seen < earliest[job["company_id"]]:
            earliest[job["company_id"]] = seen
    return earliest


def first_reads_from_runs(runs: dict | None) -> dict[str, tuple[datetime, datetime]]:
    """From the run history: each company's first run that read it, as (started, finished)."""
    found: dict[str, tuple[datetime, datetime]] = {}
    ordered = sorted((runs or {}).get("runs", []), key=lambda run: _parse(run["started_at"]))
    for run in ordered:
        span = (_parse(run["started_at"]), _parse(run.get("finished_at") or run["started_at"]))
        for company_id in run.get("read", []):
            found.setdefault(company_id, span)
    return found


def first_read_ends(jobs: Iterable[dict], seed_ids: set[str] = frozenset(), runs: dict | None = None) -> dict[str, datetime]:
    """When each company's first read ended: from the run history, or inferred, whichever began first."""
    jobs = list(jobs)
    inferred = {cid: (start, start + timedelta(hours=FIRST_RUN_HOURS)) for cid, start in first_collection(jobs, seed_ids).items()}
    recorded = first_reads_from_runs(runs)
    ends = {}
    for company_id in set(inferred) | set(recorded):
        options = [span for span in (recorded.get(company_id), inferred.get(company_id)) if span]
        ends[company_id] = min(options, key=lambda span: span[0])[1]
    return ends


def new_role_ids(jobs: list[dict], generated_at: str, read_ends: dict[str, datetime] | None = None,
                 seed_ids: set[str] = frozenset(), runs: dict | None = None) -> set[str]:
    """Ids of the roles that count as new on a board generated at `generated_at`."""
    start = window_start(generated_at)
    read_ends = read_ends if read_ends is not None else first_read_ends(jobs, seed_ids, runs)
    found = set()
    for job in jobs:
        if job["id"] in seed_ids or job["company_id"] not in read_ends:
            continue
        if _parse(job["first_seen"]) <= read_ends[job["company_id"]]:
            continue
        if mountain_date(job["first_seen"]) >= start:
            found.add(job["id"])
    return found
