"""Tag the collector's raw postings.

    uv run python -m pipeline.tag --raw data/jobs.raw.json --out data/jobs.json

Every posting is written to the jobs file with a function. The command
prints the count per function (marking the ones taxonomy.yml lists on the
board), disciplines, levels and pay. `--report` also writes one record per
posting as JSON, for the evaluation sheet and for checking a single decision.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pipeline.io import ROOT, dump_json, load_json
from pipeline.tag.tagger import hardest_titles, listed_functions, tag_file


def _share(part: int, whole: int) -> str:
    return f"{part} ({100 * part / whole:.1f}%)" if whole else f"{part}"


def print_summary(summary: dict, records: list[dict], hardest: int) -> None:
    total = summary["postings"]
    listed = listed_functions()
    print(f"Postings tagged: {total}  (with posting text: {summary['with_text']})")
    print(f"In functions listed on the board: {_share(summary['in_listed_functions'], total)}")
    print(f"In functions not listed:          {_share(summary['in_unlisted_functions'], total)}")
    print("Functions:")
    for function, count in summary["by_function"].items():
        print(f"    {function:<22} {count:>5}  {'listed' if function in listed else 'not listed'}")
    print(f"Function decided from: {summary['function_by_evidence']}   confidence: {summary['function_by_confidence']}")
    print("Disciplines (a role can carry up to three):")
    for discipline, count in summary["by_discipline"].items():
        print(f"    {discipline:<22} {count:>5}")
    print(f"Engineering and science roles with no discipline: {summary['technical_without_discipline']}")
    print("Levels:")
    for level, count in summary["by_level"].items():
        print(f"    {level:<22} {count:>5}")
    print(f"With pay: {_share(summary['with_pay'], total)}  {summary['pay_by_basis']}; "
          f"in listed functions: {_share(summary['with_pay_listed'], summary['in_listed_functions'])}")
    if summary["feed_pay_refused"]:
        print(f"Feed pay refused (figures do not fit the period): {summary['feed_pay_refused']}")
    print(f"Workplace refined from the text or title: {summary['workplace_refined']}")
    if hardest:
        print(f"\nThe {hardest} titles the rules were least sure of:")
        for group in hardest_titles(records, hardest):
            fields = ", ".join(group["disciplines"]) or "no discipline"
            notes = f"  [{'; '.join(group['notes'])}]" if group["notes"] else ""
            print(f"    {group['count']:>3} x {group['title']}  ->  {group['function']} "
                  f"(from {group['function_evidence']}): {fields}{notes}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Tag raw postings with function, disciplines, level and pay.")
    parser.add_argument("--raw", type=Path, default=ROOT / "data" / "jobs.raw.json")
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "jobs.json")
    parser.add_argument("--report", type=Path, default=None, help="write one record per posting")
    parser.add_argument("--hardest", type=int, default=0, help="print this many of the least certain titles")
    args = parser.parse_args()
    # A Windows console may not encode every character in a title; print
    # what it can rather than fail after the files are written.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")

    if not args.raw.exists():
        print(f"Raw file not found: {args.raw}", file=sys.stderr)
        return 2
    jobs_file, report = tag_file(load_json(args.raw))

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
