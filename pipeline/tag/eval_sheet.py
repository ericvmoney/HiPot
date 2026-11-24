"""Build the label sheet for checking the tagger, and score it once labelled.

    uv run python -m pipeline.tag.eval_sheet build --raw data/jobs.raw.json --out data/eval/labels.csv
    uv run python -m pipeline.tag.eval_sheet score --sheet data/eval/labels.csv

`build` samples up to 300 postings and writes the tagger's proposal for
each (function, disciplines, level) with `confirmed` set to false. It takes,
in order: ten rows of each function listed on the board and five of each
other function; five rows led by each discipline; the rows the rules were
least sure of (marked `unsure`); then the rest, shared between companies
and their departments. The tagger does not mark its own work correct: a
separate verification pass and the owner fill the `label_` columns and set
`confirmed` to true.

`score` compares the proposals with the confirmed labels.
"""
from __future__ import annotations

import argparse
import csv
import math
import random
import sys
from collections import defaultdict
from pathlib import Path

from pipeline.io import ROOT, load_json
from pipeline.tag.tagger import listed_functions, tag_file

SAMPLE_SIZE = 300
PER_LISTED_FUNCTION = 10
PER_OTHER_FUNCTION = 5
PER_DISCIPLINE = 5
UNSURE_SHARE = 0.25
SEED = 20261124
TECHNICAL = ("engineering", "science")

COLUMNS = [
    "sample", "id", "company_id", "title", "department", "url",
    "proposed_function", "function_listed", "function_evidence", "function_confidence",
    "proposed_disciplines", "proposed_level", "discipline_confidence", "discipline_evidence", "notes",
    "unsure", "unsure_why",
    "confirmed", "label_function", "label_disciplines", "label_level", "label_notes",
]


def unsure_why(record: dict) -> str:
    """Why the rules may be wrong about this record, or '' when they are confident."""
    reasons = []
    if record["function_confidence"] != "high":
        reasons.append(f"function: {record['function_confidence']} confidence")
    if record["function_evidence"] in ("department", "text", "default"):
        reasons.append(f"function decided from the {record['function_evidence']}")
    if record["function"] in TECHNICAL:
        if not record["disciplines"]:
            reasons.append("no discipline found")
        elif record["confidence"] != "high":
            reasons.append(f"disciplines: {record['confidence']} confidence")
        if record["evidence"] in ("department", "text"):
            reasons.append(f"disciplines decided from the {record['evidence']}")
    gaps = [note.split(":", 1)[1] for note in record["notes"] if note.startswith("taxonomy-gap:")]
    if gaps:
        reasons.append("no discipline in the taxonomy for " + ", ".join(gaps))
    for note, why in (("general-application", "an applicant pool, not a role"),
                      ("it-department", "engineering title in an IT department"),
                      ("supervisor", "supervisor placed by the team's department"),
                      ("technical-writer", "no function covers technical writing")):
        if note in record["notes"]:
            reasons.append(why)
    return "; ".join(dict.fromkeys(reasons))


def _round_robin(groups: dict[str, list[dict]], limit: int, rng: random.Random) -> list[dict]:
    """Take records one group at a time so no company or department dominates."""
    queues = {key: rng.sample(items, len(items)) for key, items in groups.items()}
    order = sorted(queues)
    picked: list[dict] = []
    while len(picked) < limit and any(queues.values()):
        for key in order:
            if queues[key] and len(picked) < limit:
                picked.append(queues[key].pop())
    return picked


def _spread(records: list[dict], limit: int, rng: random.Random) -> list[dict]:
    """Up to `limit` records, taken in turn from each company."""
    by_company = defaultdict(list)
    for record in records:
        by_company[record["company_id"]].append(record)
    return _round_robin(by_company, limit, rng)


def sample(records: list[dict], size: int = SAMPLE_SIZE, seed: int = SEED,
           listed: set[str] | None = None) -> list[dict]:
    rng = random.Random(seed)
    listed = listed_functions() if listed is None else listed
    # One row per distinct title at a company: repeats of one title teach nothing new.
    distinct: dict[tuple, dict] = {}
    for record in sorted(records, key=lambda r: r["id"]):
        distinct.setdefault((record["company_id"], record["title"].strip().lower()), record)
    pool = list(distinct.values())
    picked: list[dict] = []
    taken: set[str] = set()

    def take(chosen: list[dict]) -> None:
        for record in chosen:
            if record["id"] not in taken and len(picked) < size:
                picked.append(record)
                taken.add(record["id"])

    def free(records_: list[dict]) -> list[dict]:
        return [r for r in records_ if r["id"] not in taken]

    # 1. Every function, so each one's rules are checked.
    by_function = defaultdict(list)
    for record in pool:
        by_function[record["function"]].append(record)
    for name in sorted(by_function):
        quota = PER_LISTED_FUNCTION if name in listed else PER_OTHER_FUNCTION
        take(_spread(by_function[name], quota, rng))

    # 2. Every discipline that leads an engineering or science role.
    by_lead = defaultdict(list)
    for record in pool:
        if record["function"] in TECHNICAL and record["disciplines"]:
            by_lead[record["disciplines"][0]].append(record)
    for discipline in sorted(by_lead):
        already = sum(1 for r in picked if r["function"] in TECHNICAL and r["disciplines"][:1] == [discipline])
        take(_spread(free(by_lead[discipline]), max(0, PER_DISCIPLINE - already), rng))

    # 3. The rows the rules were least sure of.
    take(_spread(free([r for r in pool if unsure_why(r)]), int(size * UNSURE_SHARE), rng))

    # 4. The rest: each company gets a share in proportion to the square root
    # of its postings; inside a company, departments take turns.
    companies = defaultdict(list)
    for record in free(pool):
        companies[record["company_id"]].append(record)
    remaining = size - len(picked)
    weights = {c: math.sqrt(len(items)) for c, items in companies.items()}
    total = sum(weights.values()) or 1
    for company in sorted(companies):
        share = max(1, round(remaining * weights[company] / total))
        departments = defaultdict(list)
        for record in companies[company]:
            departments[(record["department"] or "").split(" / ")[0]].append(record)
        take(_round_robin(departments, share, rng))
    return sorted(picked[:size], key=lambda r: (r["company_id"], r["title"].lower()))


def build(raw_path: Path, out_path: Path, size: int) -> int:
    _, report = tag_file(load_json(raw_path))
    listed = listed_functions()
    rows = sample(report["records"], size, listed=listed)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # UTF-8 with a byte-order mark so a spreadsheet opens the dashes correctly.
    with open(out_path, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        for number, record in enumerate(rows, 1):
            why = unsure_why(record)
            writer.writerow({
                "sample": number,
                "id": record["id"],
                "company_id": record["company_id"],
                "title": record["title"],
                "department": record["department"] or "",
                "url": record["url"],
                "proposed_function": record["function"],
                "function_listed": "yes" if record["function"] in listed else "no",
                "function_evidence": record["function_evidence"],
                "function_confidence": record["function_confidence"],
                "proposed_disciplines": ";".join(record["disciplines"]),
                "proposed_level": record["level"] or "",
                "discipline_confidence": record["confidence"],
                "discipline_evidence": record["evidence"],
                "notes": ";".join(record["notes"]),
                "unsure": "yes" if why else "no",
                "unsure_why": why,
                "confirmed": "false",
                "label_function": "", "label_disciplines": "", "label_level": "", "label_notes": "",
            })
    functions = defaultdict(int)
    for record in rows:
        functions[record["function"]] += 1
    print(f"Wrote {out_path}: {len(rows)} rows, {sum(1 for r in rows if unsure_why(r))} marked unsure, "
          f"{len({r['company_id'] for r in rows})} companies")
    print("Rows per function: " + ", ".join(f"{name} {count}" for name, count in sorted(functions.items())))
    return 0


def _ids(value: str) -> list[str]:
    return [part.strip() for part in value.split(";") if part.strip()]


def score(sheet: Path) -> int:
    with open(sheet, encoding="utf-8-sig", newline="") as handle:
        rows = [row for row in csv.DictReader(handle) if row["confirmed"].strip().lower() == "true"]
    if not rows:
        print("No confirmed rows yet.")
        return 0
    function_right = sum(row["proposed_function"] == row["label_function"].strip() for row in rows)
    technical = [row for row in rows if row["label_function"].strip() in TECHNICAL]
    proposed = sum(len(_ids(row["proposed_disciplines"])) for row in technical)
    labelled = sum(len(_ids(row["label_disciplines"])) for row in technical)
    correct = sum(len(set(_ids(row["proposed_disciplines"])) & set(_ids(row["label_disciplines"]))) for row in technical)
    first_right = sum(_ids(row["proposed_disciplines"])[:1] == _ids(row["label_disciplines"])[:1] for row in technical)
    level_right = sum(row["proposed_level"] == row["label_level"].strip() for row in rows)
    print(f"Confirmed rows: {len(rows)}")
    print(f"Function right: {function_right}/{len(rows)}")
    if technical:
        print(f"Engineering and science rows: {len(technical)}   discipline precision: {correct}/{proposed}   "
              f"recall: {correct}/{labelled}   first discipline right: {first_right}/{len(technical)}")
    print(f"Level right: {level_right}/{len(rows)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Build or score the tagger's label sheet.")
    commands = parser.add_subparsers(dest="command", required=True)
    build_args = commands.add_parser("build")
    build_args.add_argument("--raw", type=Path, default=ROOT / "data" / "jobs.raw.json")
    build_args.add_argument("--out", type=Path, default=ROOT / "data" / "eval" / "labels.csv")
    build_args.add_argument("--size", type=int, default=SAMPLE_SIZE)
    score_args = commands.add_parser("score")
    score_args.add_argument("--sheet", type=Path, default=ROOT / "data" / "eval" / "labels.csv")
    args = parser.parse_args()
    if args.command == "build":
        return build(args.raw, args.out, args.size)
    return score(args.sheet)


if __name__ == "__main__":
    sys.exit(main())
