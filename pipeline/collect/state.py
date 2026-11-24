"""First-seen and last-seen dates, kept between runs.

The state file is `data/state/seen.json`, keyed by job id:

    {"state_version": 0, "jobs": {"<id>": {"first_seen": "...", "last_seen": "..."}}}

A posting seen on an earlier run keeps its first date. A posting that leaves a
feed stays in the file with its last date, so one that comes back is not
treated as new; entries not seen for FORGET_AFTER_DAYS are dropped.

On the very first run there is no state file. The old hub's first-seen dates
are then taken from the seed data, for the postings whose ids match.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from pathlib import Path

from pipeline.io import ROOT, load_json

DEFAULT_STATE = ROOT / "data" / "state" / "seen.json"
SEED_JOBS = ROOT / "data" / "seed" / "jobs.json"
FORGET_AFTER_DAYS = 180


def _parse(stamp: str) -> datetime:
    return datetime.fromisoformat(stamp.replace("Z", "+00:00"))


def write_json_atomic(data, path: Path, indent: int | None = 1) -> None:
    """Write to a temporary file beside the target, then swap it in."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with open(temporary, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=indent)
        handle.write("\n")
    os.replace(temporary, path)


class SeenState:
    def __init__(self, jobs: dict[str, dict] | None = None, primed_from_seed: int = 0) -> None:
        self.jobs = jobs or {}
        self.primed_from_seed = primed_from_seed

    @classmethod
    def load(cls, path: Path = DEFAULT_STATE, seed: Path | None = SEED_JOBS) -> "SeenState":
        if path.exists():
            return cls(load_json(path)["jobs"])
        if seed is None or not seed.exists():
            return cls()
        jobs = {
            job["id"]: {"first_seen": job["first_seen"], "last_seen": job["last_seen"]}
            for job in load_json(seed)["jobs"]
        }
        return cls(jobs, primed_from_seed=len(jobs))

    def observe(self, job_id: str, now: str) -> tuple[str, str]:
        """Record that a posting is on its board now. Returns (first_seen, last_seen)."""
        entry = self.jobs.get(job_id)
        if entry is None or _parse(entry["first_seen"]) > _parse(now):
            entry = self.jobs[job_id] = {"first_seen": now, "last_seen": now}
        else:
            entry["last_seen"] = now
        return entry["first_seen"], entry["last_seen"]

    def forget_old(self, now: str, days: int = FORGET_AFTER_DAYS) -> int:
        cutoff = _parse(now) - timedelta(days=days)
        stale = [job_id for job_id, entry in self.jobs.items() if _parse(entry["last_seen"]) < cutoff]
        for job_id in stale:
            del self.jobs[job_id]
        return len(stale)

    def save(self, path: Path = DEFAULT_STATE) -> None:
        write_json_atomic({"state_version": 0, "jobs": dict(sorted(self.jobs.items()))}, path)
