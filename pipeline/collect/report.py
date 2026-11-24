"""Summarize a raw jobs file.

    uv run python -m pipeline.collect.report [data/jobs.raw.json] [--top 40]

Prints postings per company and per ATS, every company that was skipped,
blocked or failed, the workplace and employment breakdowns, how many postings
carry structured pay, and the most common US locations that map to no metro in
taxonomy.yml.
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

from pipeline.collect.locations import is_remote_only, metro_for
from pipeline.collect.run import DEFAULT_OUT
from pipeline.io import load_json


def unmapped_us_locations(jobs: list[dict]) -> tuple[Counter, Counter]:
    """(postings per unmapped 'City, ST', postings per US location text with no city)."""
    cities, vague = Counter(), Counter()
    for job in jobs:
        seen = set()
        for location in job["locations"]:
            if location.get("country") != "US" or metro_for(location):
                continue
            if "city" in location and "state" in location:
                key = f"{location['city']}, {location['state']}"
                if key not in seen:
                    cities[key] += 1
                    seen.add(key)
            elif not is_remote_only(location):
                vague[location["text"]] += 1
    return cities, vague


def _counts(counter: Counter) -> str:
    return ", ".join(f"{key} {count}" for key, count in sorted(counter.items(), key=lambda item: (-item[1], str(item[0]))))


def render(raw: dict, top: int = 40) -> str:
    jobs, entries = raw["jobs"], raw["run"]["companies"]
    lines = [
        f"Run {raw['run']['started_at']} to {raw['run']['finished_at']}: {len(jobs)} postings",
        "Companies: " + _counts(Counter(entry["status"] for entry in entries)),
        "",
        "Postings per ATS: " + _counts(Counter(job["source"]["ats"] for job in jobs)),
        "",
        "Postings per company (read):",
    ]
    lines += [f"  {entry['company_id']:<28}{entry['ats']:<12}{entry['postings']:>5}"
              for entry in entries if entry["status"] == "ok"]
    for status in ("error", "blocked"):
        found = [entry for entry in entries if entry["status"] == status]
        lines += ["", f"{status.capitalize()}: {len(found)}"]
        lines += [f"  {entry['company_id']} ({entry['ats']}): {entry['error']}" for entry in found]
    skipped = [entry for entry in entries if entry["status"] == "skipped"]
    lines += ["", f"Skipped: {len(skipped)}"]
    for reason, count in Counter(entry["error"] for entry in skipped).most_common():
        names = ", ".join(entry["company_id"] for entry in skipped if entry["error"] == reason)
        lines.append(f"  {count:>3}  {reason}: {names}")

    pay = [job["pay"] for job in jobs if job["pay"]]
    lines += [
        "",
        f"Structured pay (basis feed): {len(pay)} of {len(jobs)} postings; "
        + _counts(Counter(f"{p['currency']}/{p['period']}" for p in pay)),
        "  by ATS: " + _counts(Counter(job["source"]["ats"] for job in jobs if job["pay"])),
        "Workplace: " + _counts(Counter(job["workplace"] for job in jobs)),
        "  by ATS: " + _counts(Counter(f"{job['source']['ats']}/{job['workplace']}" for job in jobs)),
        "Employment: " + _counts(Counter(job["employment"] for job in jobs)),
        "Metros: " + _counts(Counter(metro for job in jobs for metro in job["metros"]))
        + f"; postings with no metro: {sum(not job['metros'] for job in jobs)}",
        "Countries: " + _counts(Counter(
            location.get("country", "not parsed") for job in jobs for location in job["locations"])),
    ]
    cities, vague = unmapped_us_locations(jobs)
    lines += ["", f"US locations with no metro: {len(cities)} distinct cities. Top {top} by postings:"]
    lines += [f"  {count:>4}  {name}" for name, count in cities.most_common(top)]
    lines += ["", "US locations with a state or country but no city: " + (_counts(vague) or "none")]
    unparsed = Counter(location["text"] for job in jobs for location in job["locations"]
                       if "country" not in location and not is_remote_only(location))
    lines += ["Location text the parser could not read: " + (_counts(unparsed) or "none")]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m pipeline.collect.report", description=__doc__.split("\n\n")[0])
    parser.add_argument("raw", type=Path, nargs="?", default=DEFAULT_OUT)
    parser.add_argument("--top", type=int, default=40)
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(render(load_json(args.raw), args.top))
    return 0


if __name__ == "__main__":
    sys.exit(main())
