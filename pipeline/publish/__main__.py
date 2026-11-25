"""Command line for the publish step.

    uv run python -m pipeline.publish                 # data/jobs.json if it exists, else the seed
    uv run python -m pipeline.publish --jobs data/jobs.json --out site/data/board.json
    uv run python -m pipeline.publish --include-unlisted      # development only

Exits 1, writing nothing, if the jobs file or the registry fails the contracts.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pipeline.io import ROOT, load_json, load_yaml
from pipeline.publish.build import PublishError, build_board, build_pay, write_board, write_pay, write_taxonomy_file

MAX_SHOWN = 15


def default_jobs(root: Path | None = None) -> tuple[Path, str]:
    """The jobs file to use when --jobs is not given, and why.

    The tagger's output, data/jobs.json, when it exists; otherwise the seed, so the
    board can still be built on a fresh checkout before the pipeline has run.
    """
    root = ROOT if root is None else root
    tagged = root / "data" / "jobs.json"
    if tagged.is_file():
        return tagged, "default: the tagged data"
    return root / "data" / "seed" / "jobs.json", "default: data/jobs.json not found, using the seed"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m pipeline.publish",
        description="Join jobs, companies and taxonomy into the data file the board page loads.",
    )
    parser.add_argument("--jobs", type=Path, default=None,
                        help="jobs file; default data/jobs.json if it exists, else data/seed/jobs.json")
    parser.add_argument("--companies", type=Path, default=ROOT / "companies.yml")
    parser.add_argument("--taxonomy", type=Path, default=ROOT / "taxonomy.yml")
    parser.add_argument("--out", type=Path, default=ROOT / "site" / "data" / "board.json")
    parser.add_argument("--wages", type=Path, default=ROOT / "data" / "pay" / "bls-oews-2025.json",
                        help="government wage reference for the pay page; skipped if the file is missing")
    parser.add_argument("--pay-out", type=Path, default=None,
                        help="pay bands for the pay page; default pay.json beside --out")
    parser.add_argument(
        "--grades", action=argparse.BooleanOptionalAction, default=True,
        help="grade each role's published pay against comparable roles (default on; --no-grades to leave out)",
    )
    parser.add_argument(
        "--include-unlisted", action="store_true",
        help="development only: keep roles at unlisted companies and in unlisted functions. Never publish this build.",
    )
    args = parser.parse_args(argv)

    if args.jobs is None:
        args.jobs, why = default_jobs()
    else:
        why = "given with --jobs"
    print(f"Input: {args.jobs} ({why})")
    if not args.jobs.is_file():
        print(f"FAIL  nothing written: no jobs file at {args.jobs}", file=sys.stderr)
        return 1

    try:
        inputs = (load_json(args.jobs), load_yaml(args.companies), load_yaml(args.taxonomy))
        board = build_board(*inputs, include_unlisted=args.include_unlisted, grades=args.grades)
        wages = load_json(args.wages) if args.wages and args.wages.is_file() else None
        pay = build_pay(*inputs, include_unlisted=args.include_unlisted, wages=wages)
    except PublishError as error:
        print(f"FAIL  nothing written: {len(error.problems)} problem(s)", file=sys.stderr)
        for line in error.problems[:MAX_SHOWN]:
            print(f"        {line}", file=sys.stderr)
        if len(error.problems) > MAX_SHOWN:
            print(f"        ... and {len(error.problems) - MAX_SHOWN} more", file=sys.stderr)
        return 1

    size = write_board(board, args.out)
    counts = board["counts"]
    print(f"Wrote {args.out}")
    print(f"  scope: {board['scope']}" + ("  (DEVELOPMENT BUILD: includes unlisted companies and functions; do not publish)"
                                           if board["scope"] == "all" else ""))
    print(f"  roles: {counts['roles']} at {counts['companies']} companies; {counts['roles_left_out']} left out "
          f"({counts['left_out_company']} at unlisted companies, {counts['left_out_function']} in unlisted functions)")
    by_function = ", ".join(f"{fid} {n}" for fid, n in counts["functions"].items() if n)
    print(f"  by function: {by_function or 'none'}")
    if board["grades"]:
        graded = [role["grade"]["v"] for role in board["roles"] if "grade" in role]
        with_pay = sum(1 for role in board["roles"] if role.get("pay"))
        print(f"  pay grades: {len(graded)} of {with_pay} roles with pay "
              f"(above {graded.count('above')}, at {graded.count('at')}, below {graded.count('below')}); "
              f"--no-grades leaves them out")
    else:
        print("  pay grades: off (--no-grades)")
    print(f"  size: {size:,} bytes ({size / 1024:.1f} KB)")

    taxonomy_out = args.out.with_name("taxonomy.json")
    taxonomy_size = write_taxonomy_file(inputs[2], taxonomy_out)
    print(f"Wrote {taxonomy_out} (for the persona page, {taxonomy_size:,} bytes)")

    pay_out = args.pay_out or args.out.with_name("pay.json")
    pay_size = write_pay(pay, pay_out)
    shown = sum(1 for band in pay["bands"] if "mid" in band)
    print(f"Wrote {pay_out}")
    print(f"  pay bands: {len(pay['bands'])} ({shown} with 3+ postings) from {pay['counts']['postings']} postings "
          f"with published US-dollar pay ({pay['counts']['year']} yearly, {pay['counts']['hour']} hourly)")
    if "gov" in pay:
        gov = pay["gov"]
        print(f"  gov. wages: {len(gov['occupations'])} occupations in {len(gov['figures'])} metro regions "
              f"(from {args.wages.name})")
    else:
        print(f"  gov. wages: none (no file at {args.wages})")
    print(f"  size: {pay_size:,} bytes ({pay_size / 1024:.1f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
