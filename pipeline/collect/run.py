"""Collect every posting from the public feeds of the companies in the registry.

    uv run python -m pipeline.collect [--company <id>] [--out data/jobs.raw.json]

Writes a raw jobs file (schema/raw-jobs-file.schema.json). A company is
collected when its climate tier is core or enabling, its startup status is in
or review, and its ATS has a reader and a board token. Every other company gets
a `skipped` entry with the reason. One company failing does not stop the run.
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from pipeline.collect import ashby, greenhouse, lever
from pipeline.collect.fetch import Blocked, Fetcher, RecordingFetcher, ReplayFetcher
from pipeline.collect.locations import decide_workplace, metros_for
from pipeline.collect.state import DEFAULT_STATE, SeenState, write_json_atomic
from pipeline.collect.text import clip
from pipeline.io import ROOT, load_yaml
from pipeline.seed.import_old_hub import job_id, parse_source

DEFAULT_OUT = ROOT / "data" / "jobs.raw.json"
READERS: dict[str, Callable] = {
    "greenhouse": greenhouse.read,
    "lever": lever.read,
    "ashby": ashby.read,
}
HOSTS = {"greenhouse": "boards-api.greenhouse.io", "lever": "api.lever.co", "ashby": "api.ashbyhq.com"}
COLLECT_TIERS = ("core", "enabling")
COLLECT_STARTUP = ("in", "review")


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def skip_reason(company: dict, readers: dict = READERS) -> str | None:
    """Why a company is not collected, or None when it is."""
    tier, status = company["climate"]["tier"], company["startup"]["status"]
    if tier not in COLLECT_TIERS:
        return f"not collected: climate tier is '{tier}'"
    if status not in COLLECT_STARTUP:
        return f"not collected: startup status is '{status}'"
    ats = company["ats"]["type"]
    if ats not in readers:
        return f"no reader for {ats}"
    if not company["ats"]["board"]:
        return f"no board token for {ats}"
    return None


def finish(made: dict, company: dict, state: SeenState, now: str) -> dict:
    """Turn a reader's draft into a raw job."""
    ats, board = company["ats"]["type"], company["ats"]["board"]
    title = " ".join(made["title"].split())[:200]
    url = made["url"]
    if not title:
        raise ValueError("posting has no title")
    if not url.startswith("https://"):
        raise ValueError(f"posting address is not https: {url[:80]!r}")
    if not made["posting_id"]:
        raise ValueError("posting has no id")

    # The address is parsed the way the seed import parsed it, so a posting the
    # old hub listed keeps the same id. When the address is on the company's
    # own site the feed's board and posting id are used instead.
    source = parse_source(url)
    if not (source["ats"] == ats and source["board"] and source["posting_id"]):
        source = {"ats": ats, "board": board, "posting_id": made["posting_id"]}
    location_text = "; ".join(location["text"] for location in made["locations"])
    identifier = job_id(url, source, title, location_text)
    first_seen, last_seen = state.observe(identifier, now)
    return {
        "id": identifier,
        "company_id": company["id"],
        "title": title,
        "url": url,
        "source": {**source, "read": "auto"},
        "locations": made["locations"],
        "metros": metros_for(made["locations"]),
        "workplace": decide_workplace(made["workplace"], [l["text"] for l in made["locations"]], title),
        "employment": made["employment"],
        "pay": made["pay"],
        "posted_date": made["posted_date"],
        "first_seen": first_seen,
        "last_seen": last_seen,
        "department": made["department"],
        "description_text": clip(made["description_text"]),
    }


def _entry(company: dict, status: str, postings: int = 0, error: str | None = None) -> dict:
    return {
        "company_id": company["id"], "ats": company["ats"]["type"], "status": status,
        "postings": postings, "error": error[:500] if error else None,
    }


def collect(
    companies: list[dict],
    fetcher: Fetcher,
    state: SeenState,
    readers: dict | None = None,
    now: Callable[[], str] = utc_now,
    log: Callable[[str], None] = lambda line: None,
) -> dict:
    """Run every reader and return the raw jobs file as a dict."""
    readers = READERS if readers is None else readers
    started = now()
    entries, jobs, seen_ids = [], [], set()
    limited_hosts: set[str] = set()

    for company in companies:
        reason = skip_reason(company, readers)
        if reason:
            entries.append(_entry(company, "skipped", error=reason))
            continue
        ats, board = company["ats"]["type"], company["ats"]["board"]
        host = HOSTS.get(ats, ats)
        if host in limited_hosts:
            entries.append(_entry(company, "blocked", error=f"not requested: {host} answered HTTP 429 earlier in this run"))
            log(f"blocked  {company['id']}: {host} is rate limiting")
            continue
        try:
            drafts = readers[ats](board, fetcher)
            stamp = now()
            kept, dropped = [], Counter()
            for made in drafts:
                try:
                    job = finish(made, company, state, stamp)
                except ValueError as error:
                    dropped[str(error)[:80]] += 1
                    continue
                if job["id"] in seen_ids:
                    dropped["duplicate id"] += 1
                    continue
                seen_ids.add(job["id"])
                kept.append(job)
        except Blocked as error:
            if "429" in str(error):
                limited_hosts.add(host)
            entries.append(_entry(company, "blocked", error=str(error)))
            log(f"blocked  {company['id']}: {error}")
            continue
        except Exception as error:  # one company failing must not stop the run
            entries.append(_entry(company, "error", error=f"{type(error).__name__}: {error}"))
            log(f"error    {company['id']}: {type(error).__name__}: {error}")
            continue
        jobs += kept
        entries.append(_entry(company, "ok", postings=len(kept)))
        note = "".join(f"; dropped {n} ({why})" for why, n in dropped.items())
        log(f"ok       {company['id']}: {len(kept)} postings from {ats}{note}")

    finished = now()
    jobs.sort(key=lambda job: (job["company_id"], job["title"].lower(), job["id"]))
    return {
        "schema_version": 0,
        "generated_at": finished,
        "run": {"started_at": started, "finished_at": finished, "companies": entries},
        "jobs": jobs,
    }


def summary(raw: dict) -> str:
    statuses = Counter(entry["status"] for entry in raw["run"]["companies"])
    by_ats = Counter(job["source"]["ats"] for job in raw["jobs"])
    workplace = Counter(job["workplace"] for job in raw["jobs"])
    lines = [
        f"{len(raw['jobs'])} postings; companies: " + ", ".join(f"{k} {v}" for k, v in sorted(statuses.items())),
        "by ATS: " + (", ".join(f"{k} {v}" for k, v in sorted(by_ats.items())) or "none"),
        "workplace: " + (", ".join(f"{k} {v}" for k, v in sorted(workplace.items())) or "none"),
        f"with structured pay: {sum(job['pay'] is not None for job in raw['jobs'])}",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m pipeline.collect", description=__doc__.split("\n\n")[0])
    parser.add_argument("--company", action="append", help="collect only this company id (may be repeated)")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--companies", type=Path, default=ROOT / "companies.yml")
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE, help="first-seen state file")
    parser.add_argument("--greenhouse-pay", action="store_true",
                        help="one extra request per Greenhouse posting to read its structured pay range")
    parser.add_argument("--record", type=Path, metavar="DIR",
                        help="also save every raw feed answer here (data/fixtures-live is ignored by git)")
    parser.add_argument("--replay", type=Path, metavar="DIR",
                        help="read saved answers from here instead of the network")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")   # an error message may hold text the console cannot show

    companies = load_yaml(args.companies)["companies"]
    if args.company:
        known = {company["id"] for company in companies}
        unknown = [wanted for wanted in args.company if wanted not in known]
        if unknown:
            print(f"Not in {args.companies.name}: {', '.join(unknown)}", file=sys.stderr)
            return 2
        companies = [company for company in companies if company["id"] in args.company]

    readers = dict(READERS)
    if args.greenhouse_pay:
        readers["greenhouse"] = lambda board, fetcher: greenhouse.read(board, fetcher, with_pay=True)

    state = SeenState.load(args.state)
    if state.primed_from_seed:
        print(f"No state file yet: took first-seen dates for {state.primed_from_seed} postings from the seed data")
    if args.replay:
        fetcher = ReplayFetcher(args.replay)
    elif args.record:
        fetcher = RecordingFetcher(args.record)
    else:
        fetcher = Fetcher()
    try:
        raw = collect(companies, fetcher, state, readers=readers, log=print)
    finally:
        fetcher.close()
    state.forget_old(raw["generated_at"])
    write_json_atomic(raw, args.out)
    state.save(args.state)

    print(summary(raw))
    print(f"{fetcher.requests} requests; wrote {args.out}")
    return 0
