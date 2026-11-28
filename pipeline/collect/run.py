"""Collect every posting from the public feeds of the companies in the registry.

    uv run python -m pipeline.collect [--company <id>] [--out data/jobs.raw.json]

Writes a raw jobs file (schema/raw-jobs-file.schema.json). A company is
collected when its climate tier is core or enabling and its ATS has a reader
and a board token, whatever its startup status: established companies are
collected too (PLAN.md decision 14), and the board decides what it shows.
Every other company gets a `skipped` entry with the reason. One company
failing does not stop the run.
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from typing import Callable

from pipeline.collect import normalize
from pipeline.collect import (adp, ashby, bamboohr, breezy, careers, gem, greenhouse, icims, jazzhr, jobvite, lever, paylocity,
                              recruitee, rippling, smartrecruiters, successfactors, teamtailor, ukg, weekly, workable, workday)
from pipeline.collect.fetch import Blocked, Fetcher, RecordingFetcher, ReplayFetcher
from pipeline.collect.locations import decide_workplace, metros_for
from pipeline.collect.probe_careers import AGGREGATORS
from pipeline.collect.state import DEFAULT_RUNS, DEFAULT_STATE, SeenState, record_run, write_json_atomic
from pipeline.collect.text import clip
from pipeline.io import ROOT, load_yaml
from pipeline.seed.import_old_hub import job_id, parse_source

DEFAULT_OUT = ROOT / "data" / "jobs.raw.json"
READERS: dict[str, Callable] = {
    "greenhouse": greenhouse.read,
    "lever": lever.read,
    "ashby": ashby.read,
    "workable": workable.read,
    "recruitee": recruitee.read,
    "jazzhr": jazzhr.read,
    "teamtailor": teamtailor.read,
    "gem": gem.read,
    "paylocity": paylocity.read,
    "workday": workday.read,
    "icims": icims.read,                       # Terms of Use, Prohibited Uses (robots)
    # SAP SuccessFactors career sites, on the company's own domain: the sitemap
    # and US posting pages only, never the robots-disallowed /services/ search.
    "successfactors": successfactors.read,
    # These vendors' terms restrict automated reading. They run by the owner's
    # decision of 2026-11-24 (PLAN.md decision 6, recorded as a risk there);
    # each can be turned off for a run with --disable-reader TYPE.
    "rippling": rippling.read,                 # User Terms section 2.2
    "bamboohr": bamboohr.read,                 # Terms of Service section 4.2
    "smartrecruiters": smartrecruiters.read,   # SAP API Policy 2.2.2(b); robots.txt
    "breezy": breezy.read,                     # Terms of Service section 5(ix)
    "jobvite": jobvite.read,                   # Terms of Use, Intellectual Property and Restrictions
    # Listings robots.txt disallows, read at most weekly (decision 24): main()
    # wraps these two in weekly.reader. ADP's robots.txt redirects to a sign-in
    # page, which is never asked; only the public career-center list is read.
    "ukg": ukg.read,                           # terms page answered 403; quoted as barring scrapers
    "adp": adp.read,                           # adp.com/legal.aspx sections 3 and 10
    # Companies' own careers pages; the board is the careers page address.
    # Follows a company's LinkedIn jobs where its page sends candidates there
    # (LinkedIn User Agreement 8.2 restricts automated access; decision 12).
    "other": careers.read,
}
HOSTS = {"greenhouse": "boards-api.greenhouse.io", "lever": "api.lever.co", "ashby": "api.ashbyhq.com",
         "rippling": "api.rippling.com", "workable": "apply.workable.com",
         # Each BambooHR company has its own host; a 429 from one stops them all.
         "bamboohr": "bamboohr.com", "smartrecruiters": "api.smartrecruiters.com",
         # Each Recruitee company has its own host; a 429 from one stops them all.
         "recruitee": "recruitee.com", "jazzhr": "app.jazz.co",
         # Each Breezy company has its own host; a 429 from one stops them all.
         "breezy": "breezy.hr",
         # Teamtailor careers sites are on teamtailor.com or the company's own domain.
         "teamtailor": "teamtailor.com", "gem": "api.gem.com",
         "paylocity": "recruiting.paylocity.com",
         # Each Workday tenant has its own host; a 429 from one stops them all.
         "workday": "myworkdayjobs.com", "icims": "icims.com", "jobvite": "jobs.jobvite.com",
         "ukg": "ultipro.com", "adp": "workforcenow.adp.com"}
WEEKLY = ("ukg", "adp")          # decision 24
# Readers whose board is a site's own address: a 429 there says nothing about other sites.
OWN_SITE = {"other", "successfactors"}
COLLECT_TIERS = ("core", "enabling")


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# The board shapes some readers need. A board that does not fit is skipped
# with the reason, and `--check-boards` lists them all before a run.
BOARD_SHAPES = {
    "workday": (re.compile(r"^[A-Za-z0-9_-]+\.wd\d+/[A-Za-z0-9_.\-]+$"), "'{tenant}.wd{N}/{site}', e.g. 'solvenergy.wd1/SOLV_External_Career'"),
    "paylocity": (re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}(/[A-Za-z0-9-]+)?$"),
                  "the company GUID from recruiting.paylocity.com/recruiting/jobs/All/{GUID}"),
    "other": (re.compile(r"^https://[^/\s]+\.[^/\s]+"), "the careers page's https address"),
    "successfactors": (re.compile(r"^https://[^/\s]+\.[^/\s]+/?$"), "the career site's https address, e.g. 'https://careers.vestas.com'"),
    "jobvite": (re.compile(r"^[A-Za-z0-9_-]+$"), "the career site's company name from jobs.jobvite.com/{company}/jobs"),
    "ukg": (re.compile(r"^recruiting\d*\.ultipro\.com/[A-Za-z0-9]+/JobBoard/[0-9a-fA-F-]{36}$"),
            "'{host}/{tenant}/JobBoard/{board id}', e.g. 'recruiting.ultipro.com/POW1009POWS/JobBoard/42398959-...'"),
    "adp": (re.compile(r"^(?:[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
                       r"|https://workforcenow\.adp\.com/\S*[?&]cid=[0-9a-fA-F-]{36}\S*)$"),
            "the career center's cid, or its workforcenow.adp.com address with cid="),
    "teamtailor": (re.compile(r"^(?!(?:na|www|app|career|careers|jobs)$)[A-Za-z0-9.-]+$"),
                   "the careers site's host, or its subdomain on teamtailor.com (not a region prefix like 'na')"),
}


def board_problem(company: dict) -> str | None:
    """Why a company's board cannot be read by its reader, or None."""
    ats, board = company["ats"]["type"], company["ats"]["board"]
    shape = BOARD_SHAPES.get(ats)
    if board and shape and not shape[0].match(board):
        return f"{ats} board {board!r} is not in the form the reader needs: {shape[1]}"
    if ats in OWN_SITE and board and AGGREGATORS.search(urlsplit(board).netloc):
        return f"careers board {board!r} is an aggregator's page; roles come only from the company's own pages"
    return None


def skip_reason(company: dict, readers: dict = READERS, disabled=()) -> str | None:
    """Why a company is not collected, or None when it is."""
    tier = company["climate"]["tier"]
    if tier not in COLLECT_TIERS:
        return f"not collected: climate tier is '{tier}'"
    if company.get("read") == "none":
        return "not collected: the registry says read: none"
    # 'read: manual' does not stop a company being collected: the field says
    # how its board was read before there was a reader for its system.
    ats = company["ats"]["type"]
    if ats not in readers:
        if ats in disabled:
            return f"{ats}: reader turned off for this run (--disable-reader {ats})"
        return f"no reader for {ats}"
    if not company["ats"]["board"]:
        return f"no board token for {ats}"
    problem = board_problem(company)
    if problem:
        return f"not collected: {problem}"
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


def shared_workday_postings(jobs: list[dict], entries: list[dict], order: list[str],
                            log: Callable[[str], None] = lambda line: None) -> list[dict]:
    """One posting per requisition within a Workday tenant.

    A company can list the same requisition on two sites of one tenant (Canadian
    Solar's 'CanadianSolar' and 'eStorage' sites share 67). When two companies
    read such sites, the posting stays with the company whose site listed fewer
    postings this run: a narrower site is a subsidiary's or a brand's. A tie goes
    to the company that comes first in the registry. The other company's copy is
    dropped and its run entry says where the postings were left.
    """
    workday_jobs = [job for job in jobs if job["source"]["ats"] == "workday" and job["source"].get("posting_id")]
    site_size = Counter((job["company_id"], job["source"]["board"]) for job in workday_jobs)
    rank = {company_id: index for index, company_id in enumerate(order)}
    groups: dict[tuple[str, str], list[dict]] = {}
    for job in workday_jobs:
        tenant = job["source"]["board"].split(".", 1)[0].lower()
        groups.setdefault((tenant, job["source"]["posting_id"]), []).append(job)
    dropped_ids: set[int] = set()
    left_with: dict[str, Counter] = {}
    for copies in groups.values():
        if len({job["company_id"] for job in copies}) < 2:
            continue
        keeper = min(copies, key=lambda job: (site_size[(job["company_id"], job["source"]["board"])],
                                              rank.get(job["company_id"], len(rank))))
        for job in copies:
            if job["company_id"] != keeper["company_id"]:
                dropped_ids.add(id(job))
                left_with.setdefault(job["company_id"], Counter())[keeper["company_id"]] += 1
    if not dropped_ids:
        return jobs
    by_company = {entry["company_id"]: entry for entry in entries}
    for company_id, keepers in left_with.items():
        entry = by_company.get(company_id)
        note = "; ".join(f"{count} postings left under {keeper}, which reads a narrower site on the same Workday tenant"
                         for keeper, count in keepers.most_common())
        if entry:
            entry["postings"] -= sum(keepers.values())
            entry["error"] = "; ".join(part for part in (entry["error"], note) if part)[:500]
        log(f"shared   {company_id}: {note}")
    return [job for job in jobs if id(job) not in dropped_ids]


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
    disabled=(),
) -> dict:
    """Run every reader and return the raw jobs file as a dict."""
    readers = READERS if readers is None else readers
    started = now()
    entries, jobs, seen_ids = [], [], set()
    limited_hosts: set[str] = set()

    for company in companies:
        reason = skip_reason(company, readers, disabled)
        if reason:
            entries.append(_entry(company, "skipped", error=reason))
            continue
        ats, board = company["ats"]["type"], company["ats"]["board"]
        # A careers page is on the company's own host; one site's 429 says
        # nothing about the others.
        host = urlsplit(board).netloc.lower() if ats in OWN_SITE else HOSTS.get(ats, ats)
        if host in limited_hosts:
            entries.append(_entry(company, "blocked", error=f"not requested: {host} answered HTTP 429 earlier in this run"))
            log(f"blocked  {company['id']}: {host} is rate limiting")
            continue
        try:
            result = readers[ats](board, fetcher)
            if isinstance(result, normalize.ReadResult):
                drafts, status, note_from_reader = result.drafts, result.status, result.note
                stamp = result.seen_at or now()
            else:
                drafts, status, note_from_reader = result, "ok", None
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
        entries.append(_entry(company, status, postings=len(kept), error=note_from_reader))
        note = "".join(f"; dropped {n} ({why})" for why, n in dropped.items())
        extra = f" [{note_from_reader}]" if note_from_reader else ""
        log(f"{status:<8} {company['id']}: {len(kept)} postings from {ats}{note}{extra}")

    jobs = shared_workday_postings(jobs, entries, [company["id"] for company in companies], log)
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
    parser.add_argument("--careers-state", type=Path, default=careers.STATE_PATH,
                        help="careers-page reader state (weekly reads where robots.txt disallows)")
    parser.add_argument("--runs", type=Path, default=DEFAULT_RUNS,
                        help="run history: per run, the companies read (not written with --replay)")
    parser.add_argument("--greenhouse-pay", action="store_true",
                        help="one extra request per Greenhouse posting to read its structured pay range")
    parser.add_argument("--check-boards", action="store_true",
                        help="list collectable companies whose board is not in the form its reader needs, then stop")
    parser.add_argument("--disable-reader", action="append", default=[], metavar="TYPE", choices=sorted(READERS),
                        help="do not run this reader in this run (a vendor or company objected); may be repeated")
    parser.add_argument("--record", type=Path, metavar="DIR",
                        help="also save every raw feed answer here (data/fixtures-live is ignored by git)")
    parser.add_argument("--replay", type=Path, metavar="DIR",
                        help="read saved answers from here instead of the network")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")   # an error message may hold text the console cannot show

    companies = load_yaml(args.companies)["companies"]
    if args.check_boards:
        problems = [(company["id"], board_problem(company)) for company in companies
                    if company["climate"]["tier"] in COLLECT_TIERS and company.get("read") != "none"]
        problems = [(cid, why) for cid, why in problems if why]
        for cid, why in problems:
            print(f"{cid}: {why}")
        print(f"{len(problems)} boards to fix" if problems else "every board is in the form its reader needs")
        return 1 if problems else 0
    if args.company:
        known = {company["id"] for company in companies}
        unknown = [wanted for wanted in args.company if wanted not in known]
        if unknown:
            print(f"Not in {args.companies.name}: {', '.join(unknown)}", file=sys.stderr)
            return 2
        companies = [company for company in companies if company["id"] in args.company]

    readers = dict(READERS)
    careers_context = careers.Context.load(args.careers_state)
    readers["other"] = lambda board, fetcher: careers.read(board, fetcher, careers_context)
    for name in WEEKLY:
        readers[name] = weekly.reader(name, READERS[name], careers_context)
    for name in args.disable_reader:
        readers.pop(name, None)
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
        raw = collect(companies, fetcher, state, readers=readers, log=print, disabled=set(args.disable_reader))
    finally:
        fetcher.close()
    careers_context.save()
    state.forget_old(raw["generated_at"])
    write_json_atomic(raw, args.out)
    state.save(args.state)
    if not args.replay:
        record_run(raw, args.runs)

    print(summary(raw))
    print(f"{fetcher.requests} requests; wrote {args.out}")
    return 0
