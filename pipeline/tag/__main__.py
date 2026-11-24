"""Tag the collector's raw postings.

    uv run python -m pipeline.tag --raw data/jobs.raw.json --out data/jobs.json

Writes the jobs file and prints what was kept and what was left out, with
the reasons. `--report` also writes one record per posting (kept or not) as
JSON, for the evaluation sheet and for checking a single decision.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pipeline.io import ROOT, dump_json, load_json
from pipeline.tag.tagger import hardest_titles, tag_file


def _share(part: int, whole: int) -> str:
    return f"{part} ({100 * part / whole:.1f}%)" if whole else f"{part}"


def print_summary(summary: dict, records: list[dict], hardest: int) -> None:
    total, kept = summary["postings"], summary["kept"]
    print(f"Postings read:  {total}  (with posting text: {summary['with_text']})")
    print(f"Kept:           {_share(kept, total)}")
    print(f"Left out:       {_share(summary['left_out'], total)}")
    for reason, count in summary["left_out_by_reason"].items():
        print(f"    {reason:<28} {count}")
    print("Disciplines (a role can carry up to three):")
    for discipline, count in summary["by_discipline"].items():
        print(f"    {discipline:<28} {count}")
    print("Levels:")
    for level, count in summary["by_level"].items():
        print(f"    {level:<28} {count}")
    print(f"With pay:       {_share(summary['with_pay'], kept)}  {summary['pay_by_basis']}")
    if summary["feed_pay_refused"]:
        print(f"Feed pay refused (figures do not fit the period): {summary['feed_pay_refused']}")
    print(f"Workplace refined from the text or title: {summary['workplace_refined']}")
    print(f"Confidence of kept roles: {summary['by_confidence']}   decided from: {summary['by_evidence']}")
    if hardest:
        print(f"\nThe {hardest} titles the rules were least sure of:")
        for group in hardest_titles(records, hardest):
            outcome = ", ".join(group["disciplines"]) if group["in_scope"] else f"left out: {group['reason']}"
            notes = f"  [{'; '.join(group['notes'])}]" if group["notes"] else ""
            print(f"    {group['count']:>3} x {group['title']}  ->  {outcome}{notes}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Tag raw postings with disciplines, level and pay.")
    parser.add_argument("--raw", type=Path, default=ROOT / "data" / "jobs.raw.json")
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "jobs.json")
    parser.add_argument("--report", type=Path, default=None, help="write one record per posting, kept or not")
    parser.add_argument("--technicians", choices=("keep", "drop"), default="keep",
                        help="technician and trade roles (default: keep)")
    parser.add_argument("--hardest", type=int, default=0, help="print this many of the least certain titles")
    args = parser.parse_args()

    if not args.raw.exists():
        print(f"Raw file not found: {args.raw}", file=sys.stderr)
        return 2
    raw_file = load_json(args.raw)
    jobs_file, report = tag_file(raw_file, keep_technicians=args.technicians == "keep")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    dump_json(jobs_file, args.out)
    print(f"Wrote {args.out} ({len(jobs_file['jobs'])} jobs)")
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        dump_json(report, args.report)
        print(f"Wrote {args.report}")
    print_summary(report["summary"], report["records"], args.hardest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
