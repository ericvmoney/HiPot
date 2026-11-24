"""Build the label sheet for checking the tagger, and score it once labelled.

    uv run python -m pipeline.tag.eval_sheet build --raw data/jobs.raw.json --out data/eval/labels.csv
    uv run python -m pipeline.tag.eval_sheet score --sheet data/eval/labels.csv

`build` samples up to 300 postings across companies and departments, kept
and left out, and writes the tagger's proposal for each with
`confirmed` set to false. It takes five rows led by each discipline, then
the rows the rules were least sure of (marked `unsure`), then the rest by
company and department. The tagger does not mark its own work
correct: a separate verification pass and the owner fill the `label_`
columns and set `confirmed` to true.

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
from pipeline.tag.rules import JUDGEMENT_REASONS
from pipeline.tag.tagger import tag_file

SAMPLE_SIZE = 300
UNSURE_SHARE = 0.4
PER_DISCIPLINE = 5
SEED = 20261124

COLUMNS = [
    "sample", "id", "company_id", "title", "department", "url",
    "proposed_in_scope", "proposed_reason", "proposed_disciplines", "proposed_level",
    "confidence", "evidence", "notes", "unsure", "unsure_why",
    "confirmed", "label_in_scope", "label_disciplines", "label_level", "label_notes",
]


def unsure_why(record: dict) -> str:
    """Why the rules may be wrong about this record, or '' when they are confident."""
    reasons = []
    if record["confidence"] != "high":
        reasons.append(f"{record['confidence']} confidence")
    if record["reason"] == "unplaced-engineering-title":
        reasons.append("engineering title no rule placed")
    if record["reason"] in JUDGEMENT_REASONS:
        reasons.append(f"left out by a judgement ({record['reason']})")
    if record["evidence"] in ("department", "text"):
        reasons.append(f"decided from the {record['evidence']}")
    gaps = [note.split(":", 1)[1] for note in record["notes"] if note.startswith("taxonomy-gap:")]
    if gaps:
        reasons.append("no discipline in the taxonomy for " + ", ".join(gaps))
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


def sample(records: list[dict], size: int = SAMPLE_SIZE, seed: int = SEED) -> list[dict]:
    rng = random.Random(seed)
    # One row per distinct title at a company: repeats of one title teach nothing new.
    distinct: dict[tuple, dict] = {}
    for record in sorted(records, key=lambda r: r["id"]):
        distinct.setdefault((record["company_id"], record["title"].strip().lower()), record)
    pool = list(distinct.values())

    # Every discipline gets a few rows where it leads, so each rule family is checked.
    picked: list[dict] = []
    by_lead = defaultdict(list)
    for record in pool:
        if record["in_scope"]:
            by_lead[record["disciplines"][0]].append(record)
    for discipline in sorted(by_lead):
        picked += rng.sample(by_lead[discipline], min(PER_DISCIPLINE, len(by_lead[discipline])))
    taken = {r["id"] for r in picked}

    unsure = [r for r in pool if unsure_why(r) and r["id"] not in taken]
    by_company = defaultdict(list)
    for record in unsure:
        by_company[record["company_id"]].append(record)
    picked += _round_robin(by_company, int(size * UNSURE_SHARE), rng)
    taken = {r["id"] for r in picked}

    # The rest: each company gets a share in proportion to the square root of
    # its postings, so the large boards do not crowd out the small ones; inside
    # a company, departments take turns.
    rest = [r for r in pool if r["id"] not in taken]
    companies = defaultdict(list)
    for record in rest:
        companies[record["company_id"]].append(record)
    remaining = size - len(picked)
    weights = {c: math.sqrt(len(items)) for c, items in companies.items()}
    total = sum(weights.values()) or 1
    for company in sorted(companies):
        share = max(1, round(remaining * weights[company] / total))
        departments = defaultdict(list)
        for record in companies[company]:
            departments[(record["department"] or "").split(" / ")[0]].append(record)
        picked += _round_robin(departments, share, rng)
    picked = picked[:size]
    return sorted(picked, key=lambda r: (r["company_id"], r["title"].lower()))


def build(raw_path: Path, out_path: Path, size: int) -> int:
    _, report = tag_file(load_json(raw_path))
    rows = sample(report["records"], size)
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
                "proposed_in_scope": "yes" if record["in_scope"] else "no",
                "proposed_reason": record["reason"] or "",
                "proposed_disciplines": ";".join(record["disciplines"]),
                "proposed_level": record["level"] or "",
                "confidence": record["confidence"],
                "evidence": record["evidence"],
                "notes": ";".join(record["notes"]),
                "unsure": "yes" if why else "no",
                "unsure_why": why,
                "confirmed": "false",
                "label_in_scope": "", "label_disciplines": "", "label_level": "", "label_notes": "",
            })
    kept = sum(1 for r in rows if r["in_scope"])
    print(f"Wrote {out_path}: {len(rows)} rows ({kept} kept, {len(rows) - kept} left out, "
          f"{sum(1 for r in rows if unsure_why(r))} marked unsure, "
          f"{len({r['company_id'] for r in rows})} companies)")
    return 0


def score(sheet: Path) -> int:
    with open(sheet, encoding="utf-8-sig", newline="") as handle:
        rows = [row for row in csv.DictReader(handle) if row["confirmed"].strip().lower() == "true"]
    if not rows:
        print("No confirmed rows yet.")
        return 0
    scope_right = sum(row["proposed_in_scope"] == row["label_in_scope"].strip().lower() for row in rows)
    both_in = [row for row in rows if row["proposed_in_scope"] == "yes" and row["label_in_scope"].strip().lower() == "yes"]
    proposed = sum(len([d for d in row["proposed_disciplines"].split(";") if d]) for row in both_in)
    correct = sum(len({d for d in row["proposed_disciplines"].split(";") if d}
                      & {d.strip() for d in row["label_disciplines"].split(";") if d.strip()}) for row in both_in)
    labelled = sum(len([d for d in row["label_disciplines"].split(";") if d.strip()]) for row in both_in)
    first_right = sum(row["proposed_disciplines"].split(";")[0] in {d.strip() for d in row["label_disciplines"].split(";")}
                      for row in both_in)
    level_right = sum(row["proposed_level"] == row["label_level"].strip() for row in rows)
    print(f"Confirmed rows: {len(rows)}")
    print(f"Scope decision right: {scope_right}/{len(rows)}")
    if both_in:
        print(f"Discipline precision: {correct}/{proposed}   recall: {correct}/{labelled}   "
              f"first discipline right: {first_right}/{len(both_in)}")
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
