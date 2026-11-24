"""Coverage: how much of each region's climate-hardware companies HiPot has.

The denominator is a reference list per region, built by the company scout from
named sources independently of the registry (data/screening/universe/<region>.yml).
Each entry is one company that plausibly builds physical clean-technology or
electrification products in that region. Coverage is then measured against the
registry (companies.yml) and the latest board data.

Reference list format (one file per region; region ids: colorado, bay-area,
remote, and any others added later):

    region: colorado
    built: 2026-11-25
    sources:                       # every list the entries were drawn from
      - id: ccia-members
        name: Colorado Cleantech Industries Association member directory
        url: https://...
    companies:
      - name: Example Energy
        website: https://example.com
        hq: Boulder, CO
        sources: [ccia-members]    # ids from the list above; at least one
        registry_id: example-energy   # the companies.yml id once added, else null
        decision: null             # null while unchecked; 'registry' once in
                                   # companies.yml; 'not-in-scope' (no physical
                                   # climate product), 'closed' or 'duplicate'
                                   # with a reason when dropped
        reason: null
        ats: {type: workable, token: example}   # what the careers page uses, or null
        open_roles: 12             # approximate, from one look at the board, or null

Figures per region:
  reference      companies on the list, minus 'not-in-scope', 'closed', 'duplicate'
  screened       of those, in companies.yml with a climate tier and startup status
  listed         of those, listed on the board (core or enabling, startup 'in')
  readable       of the listed, whose boards the collector reads automatically
  board roles    roles on the published board at the listed companies

    uv run python -m tools.coverage                 # all regions
    uv run python -m tools.coverage --region colorado
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from pipeline.io import ROOT, load_yaml
from tools.validate import is_listed

UNIVERSE = ROOT / "data" / "screening" / "universe"
BOARD = ROOT / "site" / "data" / "board.json"
READERS = {"greenhouse", "lever", "ashby", "rippling"}
DROPPED = {"not-in-scope", "closed", "duplicate"}


def readers() -> set[str]:
    """ATS types the collector reads; grows as readers are added."""
    try:
        from pipeline.collect import run
        found = getattr(run, "READERS", None)
        if isinstance(found, dict) and found:
            return set(found)
    except Exception:
        pass
    return READERS


def region_figures(universe: dict, registry: dict[str, dict], roles_by_company: Counter, supported: set[str]) -> dict:
    entries = universe.get("companies") or []
    in_scope = [e for e in entries if e.get("decision") not in DROPPED]
    screened, listed, readable, unknown_ids = [], [], [], []
    for entry in in_scope:
        company = registry.get(entry.get("registry_id") or "")
        if entry.get("registry_id") and company is None:
            unknown_ids.append(entry["registry_id"])
        if company is None or company["climate"]["tier"] == "unscreened" or company["startup"]["status"] == "unscreened":
            continue
        screened.append(company)
        if is_listed(company):
            listed.append(company)
            if company.get("read") == "auto" and company["ats"]["type"] in supported:
                readable.append(company)
    unread_ats = Counter((e.get("ats") or {}).get("type") or "none found" for e in in_scope
                         if (e.get("ats") or {}).get("type") not in supported)
    total = len(in_scope)
    pct = lambda n, d: f"{100 * n / d:.0f}%" if d else "n/a"
    return {
        "reference": total,
        "screened": (len(screened), pct(len(screened), total)),
        "listed": (len(listed), pct(len(listed), total)),
        "readable": (len(readable), pct(len(readable), len(listed))),
        "board_roles": sum(roles_by_company[c["id"]] for c in listed),
        "unchecked": sum(1 for e in in_scope if not e.get("decision")),
        "dropped": Counter(e.get("decision") for e in entries if e.get("decision") in DROPPED),
        "boards_not_read": unread_ats,
        "unknown_registry_ids": unknown_ids,
        "sources": len(universe.get("sources") or []),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--region", action="append")
    args = parser.parse_args()

    files = sorted(UNIVERSE.glob("*.yml")) if UNIVERSE.exists() else []
    if args.region:
        files = [f for f in files if f.stem in args.region]
    if not files:
        print(f"No reference lists in {UNIVERSE.relative_to(ROOT)} yet.")
        return 1
    registry = {c["id"]: c for c in load_yaml(ROOT / "companies.yml")["companies"]}
    roles = Counter()
    if BOARD.exists():
        roles = Counter(role["co"] for role in json.loads(BOARD.read_text(encoding="utf-8"))["roles"])
    supported = readers()

    print(f"{'region':10} {'reference':>9} {'screened':>14} {'listed':>14} {'readable':>14} {'roles':>6}  unchecked")
    for path in files:
        figures = region_figures(load_yaml(path), registry, roles, supported)
        s, l, r = figures["screened"], figures["listed"], figures["readable"]
        print(f"{path.stem:10} {figures['reference']:>9} {s[0]:>7} ({s[1]:>4}) {l[0]:>7} ({l[1]:>4}) "
              f"{r[0]:>7} ({r[1]:>4}) {figures['board_roles']:>6}  {figures['unchecked']}")
        if figures["boards_not_read"]:
            print("           boards the collector cannot read yet: "
                  + ", ".join(f"{k} {v}" for k, v in figures["boards_not_read"].most_common()))
        if figures["unknown_registry_ids"]:
            print(f"           registry_id not in companies.yml: {figures['unknown_registry_ids'][:10]}")
    print("\nreadable % is of listed companies; the other percentages are of the reference list.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
