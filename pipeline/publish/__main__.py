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
from pipeline.publish.build import PublishError, build_board, write_board

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
        board = build_board(
            load_json(args.jobs), load_yaml(args.companies), load_yaml(args.taxonomy),
            include_unlisted=args.include_unlisted,
        )
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
    print(f"  size: {size:,} bytes ({size / 1024:.1f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
