"""Grade each role's published pay against comparable published ranges.

A grade compares published ranges with each other. It is not a salary estimate and says
nothing about any candidate.

Rule
    A role's midpoint is compared with the median midpoint of comparable roles, the role
    itself left out: same pay period, role group and level (as in `pay.py`), in the
    role's primary market (its first metro region, else Remote (US), else all US). With
    fewer than `MIN_COMPARE` other postings there, the comparison falls back to the same
    role group and level across all US; with fewer still, the role gets no grade. More
    than `GRADE_MARGIN` above that median is "above", more than `GRADE_MARGIN` below is
    "below", anything between is "at".
"""
from __future__ import annotations

from collections import defaultdict
from statistics import median
from typing import Any, Iterable

from pipeline.publish.pay import US, _round, level_key, markets, midpoint, primary_market, role_group, usable_pay

MIN_COMPARE = 5       # other postings a grade needs in its comparison group
GRADE_MARGIN = 0.10   # above or below market: more than 10 percent from the median midpoint
GRADES = (("above", "Above market"), ("at", "At market"), ("below", "Below market"))


def grades(jobs: Iterable[dict]) -> dict[str, dict[str, Any]]:
    """A grade for each job id that can have one.

    Each grade: `v` above, at or below; `g` and `m` the role group and market compared
    with (the level and pay period are the role's own); `n` how many other postings that
    group holds; `med` their median midpoint; `pct` how far this role's midpoint is from
    it, in percent.
    """
    jobs = list(jobs)
    pools: dict[tuple, list[tuple[str, float]]] = defaultdict(list)
    for job in jobs:
        pay = usable_pay(job)
        if not pay:
            continue
        for market in markets(job):
            pools[(pay["period"], role_group(job), level_key(job), market)].append((job["id"], midpoint(pay)))

    out: dict[str, dict[str, Any]] = {}
    for job in jobs:
        pay, market = usable_pay(job), primary_market(job)
        if not pay or market is None:
            continue
        key = (pay["period"], role_group(job), level_key(job))
        for candidate in dict.fromkeys((market, US)):
            others = [mid for job_id, mid in pools[key + (candidate,)] if job_id != job["id"]]
            if len(others) >= MIN_COMPARE:
                break
        else:
            continue
        typical = median(others)
        ratio = midpoint(pay) / typical
        verdict = "above" if ratio > 1 + GRADE_MARGIN else "below" if ratio < 1 - GRADE_MARGIN else "at"
        out[job["id"]] = {
            "v": verdict, "g": key[1], "m": candidate,
            "n": len(others), "med": _round(typical, key[0]), "pct": int(round((ratio - 1) * 100)),
        }
    return out
