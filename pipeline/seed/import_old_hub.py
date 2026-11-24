"""Import a snapshot of the old personal job hub as seed data.

Reads the saved artifact page, and writes:

  data/seed/jobs.json   every role that links to the company's own board
  companies.yml         one entry per company (only if the file does not exist,
                        or with --force; after M0 the registry belongs to the
                        company scout and must not be regenerated)

The old hub listed only senior-and-above roles that matched one person's five
profiles, so this is a starting set for the front end and the tagger to build
against, not a picture of what the collector will produce.

Run from the repository root:

    uv run python -m pipeline.seed.import_old_hub
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from pipeline.io import ROOT, dump_json, dump_yaml, load_yaml

DEFAULT_SNAPSHOT = ROOT / "data" / "seed" / "raw" / "old_hub_2026-11-23.html"
SCREEN_FILE = ROOT / "data" / "seed" / "provisional_screen.yml"
JOBS_OUT = ROOT / "data" / "seed" / "jobs.json"
COMPANIES_OUT = ROOT / "companies.yml"

# Hosts that are not the company's own board. Roles found there are dropped.
AGGREGATOR_HOSTS = ("linkedin.com", "indeed.com", "glassdoor.com", "ziprecruiter.com")

COMPANIES_HEADER = """\
# HiPot company registry.
#
# Seeded from the old personal job hub on {date}. A company's roles are listed
# only when climate.tier is core or enabling AND startup.status is in.
#
# climate.basis 'provisional' means a first pass from general knowledge that has
# not been checked against the company's own site. Nothing here is approved yet.
#
# Owned by workstream A2 (company scout). New companies arrive as proposals in
# data/screening/ and are added here only after approval.

"""


def script_block(html: str, block_id: str) -> str:
    match = re.search(rf'<script[^>]*id="{re.escape(block_id)}"[^>]*>(.*?)</script>', html, re.S)
    if not match:
        raise SystemExit(f"Block '{block_id}' not found in the snapshot")
    return match.group(1)


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    if not slug:
        raise ValueError(f"Cannot make an id from {name!r}")
    return slug


def parse_source(url: str) -> dict:
    """Work out the ATS, board token and posting id from a posting address."""
    parts = urlsplit(url)
    host = parts.netloc.lower()
    path = [segment for segment in parts.path.split("/") if segment]
    ats, board, posting = "unknown", None, None

    if host in ("job-boards.greenhouse.io", "boards.greenhouse.io") and len(path) >= 3 and path[1] == "jobs":
        ats, board, posting = "greenhouse", path[0], path[2]
    elif host == "jobs.ashbyhq.com" and len(path) >= 2:
        ats, board, posting = "ashby", path[0], path[1]
    elif host == "jobs.lever.co" and len(path) >= 2:
        ats, board, posting = "lever", path[0], path[1]
    elif host == "ats.rippling.com" and len(path) >= 3 and path[1] == "jobs":
        ats, board, posting = "rippling", path[0], path[2]
    elif host.endswith(".myworkdayjobs.com"):
        ats, board = "workday", host.split(".")[0]
    elif host.endswith(".bamboohr.com"):
        ats, board = "bamboohr", host.split(".")[0]
    elif host == "workforcenow.adp.com":
        ats = "adp"
    elif host.endswith(".eightfold.ai"):
        ats, board = "eightfold", host.split(".")[0]
    elif "gh_jid" in parse_qs(parts.query):
        # A Greenhouse posting embedded in the company's own site. The board
        # token is not in the address.
        ats, posting = "greenhouse", parse_qs(parts.query)["gh_jid"][0]
    return {"ats": ats, "board": board, "posting_id": posting}


def _id_part(text: str) -> str:
    """A board token or posting id made safe for an id: decoded from the address,
    with anything outside letters, digits, '.', '_' and '-' replaced by '-'.
    Some boards have spaces in their token ("Karman%20Industries")."""
    return re.sub(r"[^A-Za-z0-9._-]+", "-", unquote(text)).strip("-")


def job_id(url: str, source: dict, title: str = "", location: str = "") -> str:
    """Stable id for a posting.

    Some boards (ADP, for one) give every role the same address, so when there
    is no posting id the title and location go into the hash as well.
    """
    if source["board"] and source["posting_id"]:
        return f"{source['ats']}:{_id_part(source['board'])}:{_id_part(source['posting_id'])}"
    key = "\n".join((url, title.strip().lower(), location.strip().lower()))
    return "web:" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


def parse_pay(text: str) -> dict | None:
    """The old hub wrote pay as '$140k-$205k', or left it empty."""
    match = re.fullmatch(r"\$(\d+(?:\.\d+)?)k-\$(\d+(?:\.\d+)?)k", text.strip())
    if not match:
        return None
    low, high = (int(round(float(value) * 1000)) for value in match.groups())
    if low > high:
        return None
    return {"min": low, "max": high, "currency": "USD", "period": "year", "basis": "seed"}


def level_from_title(title: str) -> str | None:
    """Level from the title alone. Ported from the old hub and extended downward.

    Roman numerals are matched case-sensitively so 'v' in a title is not read
    as level five.
    """
    lowered = title.lower()
    if re.search(r"\bvp\b|vice president|\bchief \w+ officer\b", lowered):
        return "executive"
    if re.search(r"director|head of", lowered):
        return "director"
    is_pm_title = re.search(r"(product|program|project) manager|product management", lowered)
    if "manager" in lowered and not is_pm_title:
        return "manager"
    if re.search(r"principal|distinguished|fellow|architect|tech(nical)? specialist", lowered) or re.search(r"\bV\b", title):
        return "principal"
    if re.search(r"staff|\blead\b", lowered) or re.search(r"\bIV\b", title):
        return "staff"
    if re.search(r"senior|\bsr\b", lowered) or re.search(r"\bIII\b", title):
        return "senior"
    if re.search(r"\bintern(ship)?\b|\bco-?op\b", lowered):
        return "intern"
    if re.search(r"\bjunior\b|\bjr\b|\bassociate\b|entry[- ]level|new grad", lowered) or re.search(r"\bI\b", title):
        return "entry"
    if re.search(r"\bII\b", title):
        return "mid"
    return None


def read_rows(html: str) -> list[dict]:
    rows = []
    for block_id, read in (("jobs-auto", "auto"), ("jobs-manual", "manual")):
        for number, line in enumerate(script_block(html, block_id).splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            fields = line.split("|")
            if len(fields) != 10:
                raise SystemExit(f"{block_id} line {number}: expected 10 fields, found {len(fields)}")
            company, title, location, where, pay, updated, url, profiles, _core, first_seen = fields
            rows.append({
                "read": read, "company": company.strip(), "title": title.strip(),
                "location": location.strip(), "where": [w for w in where.split(",") if w],
                "pay": pay, "updated": updated.strip(), "url": url.strip(),
                "profiles": [p for p in profiles.split(",") if p], "first_seen": first_seen.strip(),
            })
    return rows


SEED_FUNCTION_RULES = (
    # Order matters: the first match wins. The old hub kept only engineering-led
    # searches, so anything unmatched is engineering. The tagger replaces these.
    (re.compile(r"\b(program|project|construction|deployment)\s+(manager|management|lead|director)\b|\bTPM\b", re.I), "project-program"),
    (re.compile(r"\bproduct\s+(manager|management|lead|owner|director)\b|\bindustrial design", re.I), "product"),
    (re.compile(r"\btechnician\b", re.I), "technician"),
)


def seed_function(title: str, profiles: list[str]) -> str:
    """A first-pass function for an old-hub row: from the title, then the 'prod' profile."""
    for pattern, function in SEED_FUNCTION_RULES:
        if pattern.search(title):
            return function
    if profiles == ["prod"] and not re.search(r"\bengineer", title, re.I):
        return "product"
    return "engineering"


def build(snapshot: Path) -> tuple[dict, dict, dict]:
    html = snapshot.read_text(encoding="utf-8")
    taxonomy = load_yaml(ROOT / "taxonomy.yml")
    profile_map = taxonomy["seed_maps"]["old_hub_profiles"]
    where_map = taxonomy["seed_maps"]["old_hub_where"]
    last_run = json.loads(script_block(html, "meta"))["last_run"]
    screen = load_yaml(SCREEN_FILE)["companies"] if SCREEN_FILE.exists() else {}

    rows = read_rows(html)
    stats = Counter(rows_read=len(rows))
    jobs, seen_ids = [], set()
    by_company: dict[str, list[dict]] = defaultdict(list)

    for row in rows:
        host = urlsplit(row["url"]).netloc.lower()
        if any(host == bad or host.endswith("." + bad) for bad in AGGREGATOR_HOSTS):
            stats["dropped_aggregator_link"] += 1
            by_company[row["company"]].append({"row": row, "source": None})
            continue
        source = parse_source(row["url"])
        identifier = job_id(row["url"], source, row["title"], row["location"])
        if identifier in seen_ids:
            stats["dropped_duplicate"] += 1
            continue
        seen_ids.add(identifier)
        by_company[row["company"]].append({"row": row, "source": source})

        level = level_from_title(row["title"])
        jobs.append({
            "id": identifier,
            "company_id": slugify(row["company"]),
            "title": row["title"],
            "url": row["url"],
            "source": {**source, "read": row["read"]},
            "locations": [{"text": part.strip(" ,")} for part in row["location"].split(";") if part.strip(" ,")],
            "metros": sorted({where_map[w] for w in row["where"] if w in where_map}),
            "workplace": "remote" if "remote" in row["where"] else "unknown",
            "function": seed_function(row["title"], row["profiles"]),
            "disciplines": sorted({profile_map[p] for p in row["profiles"] if p in profile_map})[:3],
            "level": level,
            "employment": "unknown",
            "pay": parse_pay(row["pay"]),
            "posted_date": row["updated"] or None,
            "first_seen": row["first_seen"],
            "last_seen": last_run,
            "tagging": {"function_by": "seed", "disciplines_by": "seed", "level_by": "rule", "model": None},
        })

    jobs.sort(key=lambda job: (job["company_id"], job["title"].lower(), job["id"]))
    stats["jobs_written"] = len(jobs)

    companies = []
    unused_screen = set(screen)
    for name in sorted(by_company, key=str.lower):
        entries = by_company[name]
        sources = [entry["source"] for entry in entries if entry["source"]]
        ats_counts = Counter(source["ats"] for source in sources)
        ats_type = ats_counts.most_common(1)[0][0] if ats_counts else "unknown"
        board = next((s["board"] for s in sources if s["ats"] == ats_type and s["board"]), None)
        read = "auto" if any(entry["row"]["read"] == "auto" for entry in entries) else "manual"
        verdict = screen.get(name, {})
        unused_screen.discard(name)
        company = {
            "id": slugify(name),
            "name": name,
            "website": None,
            "careers_url": None,
            "hq": None,
            "ats": {"type": ats_type, "board": board},
            "read": read,
            "sectors": verdict.get("sectors", []),
            "stage": None,
            "founded": None,
            "headcount": None,
            "climate": {
                "tier": verdict.get("tier", "unscreened"),
                "reason": verdict.get("reason"),
                "basis": "provisional" if "tier" in verdict else None,
                "approved": False,
            },
            "startup": {
                "status": verdict.get("startup", "unscreened"),
                "reason": verdict.get("startup_reason"),
            },
        }
        if not sources:
            company["notes"] = "The old hub read this company through LinkedIn only; its own board has not been located."
        elif ats_type == "unknown" and read == "auto":
            company["notes"] = "The old hub read this automatically from the company's own site; the feed behind it has to be rediscovered."
        companies.append(company)

    if unused_screen:
        raise SystemExit(f"provisional_screen.yml names companies not in the snapshot: {sorted(unused_screen)}")

    stats["companies"] = len(companies)
    jobs_file = {
        "schema_version": 0,
        "generated_at": last_run,
        "source": f"seed:{snapshot.stem}",
        "jobs": jobs,
    }
    return jobs_file, {"registry_version": 0, "companies": companies}, dict(stats)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT)
    parser.add_argument("--force", action="store_true", help="Overwrite companies.yml if it exists")
    args = parser.parse_args()

    jobs_file, registry, stats = build(args.snapshot)
    JOBS_OUT.parent.mkdir(parents=True, exist_ok=True)
    dump_json(jobs_file, JOBS_OUT)
    print(f"Wrote {JOBS_OUT.relative_to(ROOT)}")

    if COMPANIES_OUT.exists() and not args.force:
        print(f"Kept existing {COMPANIES_OUT.name} (use --force to regenerate it from the snapshot)")
    else:
        dump_yaml(registry, COMPANIES_OUT, COMPANIES_HEADER.format(date=jobs_file["generated_at"][:10]))
        print(f"Wrote {COMPANIES_OUT.name}")

    for key, value in stats.items():
        print(f"  {key}: {value}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
