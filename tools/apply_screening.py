"""Apply the company scout's screening and the owner's rulings to companies.yml.

Inputs
  companies.yml                          the registry as it stands
  data/screening/seed-review.yml         the scout's checks of the seed companies
  data/screening/proposals-*.yml         the scout's new companies, every file
  data/screening/registry-fixes-*.yml    facts the registry lacks (filled, never overwritten)
  OWNER_RULINGS below                    the owner's answers to decisions-needed.md

Outputs
  companies.yml                          updated in place
  data/screening/applied-latest.md       what the last run changed, company by company

Re-running gives the same result. Order of precedence: owner rulings, then the
scout's checked facts, then what the registry already held.

    uv run python -m tools.apply_screening
"""
from __future__ import annotations

import copy
import re
import sys
from collections import Counter

from pipeline.io import ROOT, dump_yaml, load_yaml
from pipeline.collect.run import READERS as COLLECTOR_READERS
from tools.validate import check_companies, is_listed, schema_errors, schema_registry

REGISTRY = ROOT / "companies.yml"
REVIEW = ROOT / "data" / "screening" / "seed-review.yml"
SCREENING = ROOT / "data" / "screening"
PROPOSAL_FILES = "proposals-*.yml"        # proposals-01.yml, proposals-02-colorado.yml, ...
FIX_FILES = "registry-fixes-*.yml"        # facts for companies already in the registry
LOG = SCREENING / "applied-latest.md"     # applied-01.md keeps the first run's log
HEADCOUNT_LINE, BORDERLINE = 1000, 1250   # B2: up to about 25 percent over counts as borderline
READABLE = set(COLLECTOR_READERS)   # systems the collector reads with no switch needed
TODAY = "2026-11-24"

HEADER = """\
# HiPot company registry.
#
# A company's roles are listed only when climate.tier is core or enabling AND
# startup.status is in.
#
# climate.basis: 'agent' = checked against real sources by the company scout
# (data/screening/); 'provisional' = a first pass from general knowledge, not yet
# checked. climate.approved stays false until the owner approves each company.
# Owner rulings of 2026-11-24 are applied by tools/apply_screening.py; the change
# log is data/screening/applied-01.md.
#
# Edited by the supervisor. New companies arrive as proposals in data/screening/.

"""

# Owner's answers to data/screening/decisions-needed.md, 2026-11-24, in his words:
#   A1 Electric aviation. A2 Not ideal but include for now. A3 Defense business is
#   fine so long as it isn't their primary or only business. A4 Archer is OK to
#   include. A5 Purely autonomous cars out; transit-oriented EVs in (Glydways in,
#   Parallel Systems in). A6 Include for now. A6b Mining out. A7 Exclude for now.
#   A8 Include. B1 Years is a guide, not a hard rule. B2 If borderline, include.
#   B3 If no figure is available, include.
STARTUP_IN_BY_RULE = {
    "age": "Older than 10 years but well under 1,000 people; age is a guide, not a rule (owner, 2026-11-24).",
    "no figure": "No headcount figure found; included under the owner's rule for missing figures (2026-11-24).",
    "near-line": "Near the 1,000-person line; borderline companies are included (owner, 2026-11-24).",
}
# Each entry: the question it settles, and the fields it sets.
OWNER_RULINGS: dict[str, dict] = {
    # A1: drone delivery is electric aviation.
    "zipline": {"q": "A1", "tier": "enabling", "sectors": ["electric-aviation"],
                "reason": "Battery-electric delivery aircraft for retail, restaurant and hospital deliveries, replacing car and van trips.",
                "startup": "in", "startup_rule": "no figure"},
    "wing": {"q": "A1", "tier": "enabling", "sectors": ["electric-aviation"], "startup": "in", "startup_rule": "age"},
    # A2: clean products sold to data centers are included for now. Fossil-fuelled
    # products (Arbor, Hyliion, Scale Microgrids) and compute (Crusoe) stay out.
    "veir": {"q": "A2", "tier": "core", "sectors": ["grid"],
             "reason": "High-temperature superconducting power cables that move electricity with far lower losses; first product serves AI data centers."},
    "amperesand": {"q": "A2", "tier": "enabling", "sectors": ["grid", "components"],
                   "reason": "Silicon-carbide solid-state transformers for grid and data-center power conversion."},
    "atomic-machines": {"q": "A2", "tier": "enabling", "sectors": ["components"],
                        "reason": "Micro-manufactured relays and switches for 800 V DC power systems, first for AI data centers."},
    "spinor-energy": {"q": "A2", "tier": "core", "sectors": ["energy-storage"],
                      "reason": "Superconducting magnetic energy storage, aimed first at AI data centers."},
    "karman-industries": {"q": "A2", "tier": "enabling", "sectors": ["industrial-heat"],
                          "reason": "Electric heat pumps for industrial heat and data-center cooling.", "startup": "in", "startup_rule": "no figure"},
    "panthalassa": {"q": "A2", "tier": "enabling", "sectors": ["distributed-generation"],
                    "reason": "Wave-powered ocean nodes that generate their own electricity, first used to run on-board computing."},
    "on-energy": {"q": "A2", "tier": "enabling", "sectors": ["energy-storage"], "basis": "provisional",
                  "reason": "Battery storage and power systems for data centers and industrial sites.", "startup": "in", "startup_rule": "no figure"},
    # A3: defense as a side business is fine; as the main business it is out.
    "antares": {"q": "A3", "tier": "out",
                "reason": "Factory-built nuclear microreactors whose main customers so far are the US military; defense as the main business is out."},
    "h3x-technologies": {"q": "A3", "tier": "out",
                         "reason": "Electric motor drives; the company says defense is its current focus, and defense as the main business is out."},
    # A4: Archer is included despite its headcount.
    "archer": {"q": "A4", "startup": "in",
               "startup_reason": "About 1,160 full-time employees (2025 Form 10-K); included by owner decision despite the 1,000-person line (2026-11-24)."},
    # A5: autonomous transit and freight on guideways or rail are in.
    "glydways": {"q": "A5", "tier": "enabling", "sectors": ["electric-mobility"],
                 "reason": "Small autonomous electric pods on dedicated guideways, sold to transit agencies to replace car trips."},
    "parallel-systems": {"q": "A5", "tier": "enabling", "sectors": ["electric-mobility"],
                         "reason": "Autonomous battery-electric rail cars that move freight containers on existing track instead of diesel trucks."},
    # A6: robots built only to deploy solar are in for now.
    "built-robotics": {"q": "A6", "tier": "enabling", "sectors": ["solar"],
                       "reason": "Autonomous pile-driving machines that speed up building solar farms."},
    "charge-robotics": {"q": "A6", "tier": "enabling", "sectors": ["solar"],
                        "reason": "Robots that assemble and install solar modules on utility-scale plants."},
    "cosmic-robotics": {"q": "A6", "tier": "enabling", "sectors": ["solar"],
                        "reason": "Robots that install solar modules on utility-scale plants."},
    # A6b: mine operators are out.
    "mariana-minerals": {"q": "A6b", "tier": "out",
                         "reason": "Operates mines and refineries for copper, lithium and nickel; mine operation is out."},
    # A7: Mainspring is excluded for now.
    "mainspring-energy": {"q": "A7", "tier": "out", "startup": "in", "startup_rule": "age",
                          "reason": "Linear generators that mostly run on natural gas or biogas today; excluded for now."},
    # A8: SENS is included.
    "stored-energy-systems-sens": {"q": "A8", "tier": "enabling", "sectors": ["grid", "components"], "startup": "in", "startup_rule": "age",
                                   "reason": "DC power systems, chargers and controls for utilities, switchgear and backup power."},
    # B2: borderline headcount is included. Not borderline: Scout Motors (a
    # Volkswagen subsidiary at about 1,250 and planning 4,000), ChargePoint (1,440),
    # Atoms (2,000).
    "form-energy": {"q": "B2", "startup": "in", "startup_rule": "near-line"},
    "redwood-materials": {"q": "B2", "startup": "in", "startup_rule": "near-line"},
    "commonwealth-fusion-systems": {"q": "B2", "startup": "in",
                                    "startup_reason": "Sources say just over 1,000 people; borderline companies are included (owner, 2026-11-24)."},
}


def headcount_from_review(entry: dict) -> dict | None:
    head = entry.get("headcount") or {}
    if head.get("value") is None:
        return None
    as_of = str(head.get("as_of") or "")
    source = head.get("source") or "unknown source"
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", as_of):
        source += f" (undated; read {TODAY})"
        as_of = TODAY
    if head.get("url"):
        source += f" {head['url']}"
    return {"value": int(head["value"]), "as_of": as_of, "source": source}


def apply_review(company: dict, entry: dict) -> None:
    proposed = entry.get("proposed") or {}
    if proposed.get("tier"):
        company["climate"].update(tier=proposed["tier"], reason=proposed.get("reason"), basis="agent")
    if proposed.get("sectors") is not None:
        company["sectors"] = proposed["sectors"]
    if proposed.get("startup"):
        company["startup"] = {"status": proposed["startup"], "reason": proposed.get("startup_reason")}
    for field in ("hq", "stage", "founded"):
        if entry.get(field) is not None:
            company[field] = entry[field]
    if entry.get("headcount") is not None:
        company["headcount"] = headcount_from_review(entry) or company.get("headcount")
    board = entry.get("board") or {}
    if board.get("confirmed") and board.get("ats"):
        company["ats"] = {"type": board["ats"], "board": board.get("token")}
        company["read"] = "auto" if board["ats"] in READABLE else "manual"
    company["notes"] = f"Checked by the company scout on {TODAY}; facts and sources in data/screening/seed-review.yml."


def fill_missing(company: dict, fix: dict) -> None:
    """Fill hq, founded, stage and headcount where the registry has none."""
    for field in ("hq", "founded", "stage"):
        value = (fix.get(field) or {}).get("value")
        if company.get(field) is None and value is not None:
            company[field] = value
    if company.get("headcount") is None and (fix.get("headcount") or {}).get("value") is not None:
        company["headcount"] = headcount_from_review(fix)
    note = "Missing facts filled from data/screening/registry-fixes."
    if any(fix.get(f) for f in ("hq", "founded", "stage", "headcount")) and note not in (company.get("notes") or ""):
        company["notes"] = f"{company.get('notes') or ''} {note}".strip()


def apply_ruling(company: dict, ruling: dict) -> None:
    if "tier" in ruling:
        company["climate"]["tier"] = ruling["tier"]
        company["climate"]["basis"] = ruling.get("basis", company["climate"].get("basis") or "agent")
    if "reason" in ruling:
        company["climate"]["reason"] = ruling["reason"]
    if "sectors" in ruling:
        company["sectors"] = ruling["sectors"]
    if "startup" in ruling:
        reason = ruling.get("startup_reason")
        if reason is None and ruling.get("startup_rule"):
            reason = rule_reason(company["startup"].get("reason"), ruling["startup_rule"])
        company["startup"] = {"status": ruling["startup"], "reason": reason or company["startup"].get("reason")}
    note = f"Owner ruling {ruling['q']} (2026-11-24) applied."
    if note not in (company.get("notes") or ""):
        company["notes"] = f"{company.get('notes') or ''} {note}".strip()


def rule_reason(old: str | None, rule: str) -> str:
    kept = re.sub(r"\s*(Older than 10 years: owner to decide\.|Needs a headcount figure before listing\.)", "", old or "").strip()
    if STARTUP_IN_BY_RULE[rule] in kept:       # already applied on an earlier run
        return kept
    return f"{kept} {STARTUP_IN_BY_RULE[rule]}".strip()


def summary(company: dict) -> str:
    return f"{company['climate']['tier']}/{company['startup']['status']}"


def main() -> int:
    registry = load_yaml(REGISTRY)
    original = copy.deepcopy(registry)
    review = {entry["id"]: entry for entry in load_yaml(REVIEW)["companies"]}
    proposals = [c for path in sorted(SCREENING.glob(PROPOSAL_FILES)) for c in load_yaml(path)["companies"]]
    fixes = [f for path in sorted(SCREENING.glob(FIX_FILES)) for f in load_yaml(path)["fixes"]]
    companies = {company["id"]: company for company in registry["companies"]}
    before = {cid: (summary(c), is_listed(c)) for cid, c in companies.items()}

    for cid, entry in review.items():
        if cid in companies:
            apply_review(companies[cid], entry)
    added = []
    for proposal in proposals:
        if proposal["id"] not in companies:
            companies[proposal["id"]] = proposal
            added.append(proposal["id"])

    for fix in fixes:
        if fix["id"] in companies:
            fill_missing(companies[fix["id"]], fix)

    # The headcount line: a dated figure beyond the borderline allowance takes a
    # listed company out, unless the owner ruled on it by name (OWNER_RULINGS).
    for company in companies.values():
        head = company.get("headcount") or {}
        if company["startup"]["status"] == "in" and (head.get("value") or 0) > BORDERLINE and company["id"] not in OWNER_RULINGS:
            company["startup"] = {"status": "out", "reason": (
                f"{head['value']:,} people ({head['source']}, {head['as_of']}): over the 1,000-person line "
                f"by more than the borderline allowance.")}

    # B1 and B3 as blanket rules: a company held at 'review' only for its age or
    # for a missing headcount is in. Anything held for another reason stays.
    for company in companies.values():
        reason = company["startup"].get("reason") or ""
        if company["startup"]["status"] == "review" and company["id"] not in OWNER_RULINGS:
            if "Older than 10 years" in reason or re.search(r"founded (19|20)(0\d|1[0-5])", reason, re.I):
                company["startup"] = {"status": "in", "reason": rule_reason(reason, "age")}
            elif "No headcount" in reason or "not found" in reason.lower() or "Headcount not found" in reason:
                company["startup"] = {"status": "in", "reason": rule_reason(reason, "no figure")}

    missing = [cid for cid in OWNER_RULINGS if cid not in companies]
    if missing:
        sys.exit(f"owner rulings name companies not in the registry: {missing}")
    for cid, ruling in OWNER_RULINGS.items():
        apply_ruling(companies[cid], ruling)

    ordered = [companies[cid] for cid in sorted(companies)]
    out = {"registry_version": registry["registry_version"], "companies": ordered}

    schema_reg, schemas = schema_registry()
    taxonomy = load_yaml(ROOT / "taxonomy.yml")
    problems = schema_errors(out, schemas["companies-file.schema.json"], schema_reg) or check_companies(out, taxonomy)
    if problems:
        print("\n".join(problems[:20]))
        sys.exit("the new registry does not validate; nothing written")
    if out == original:
        print("companies.yml already matches the screening and rulings; nothing written (change log kept).")
        return 0
    dump_yaml(out, REGISTRY, header=HEADER)

    lines = ["# Screening applied to companies.yml", "",
             f"Generated by `tools/apply_screening.py` on {TODAY}. Owner rulings are listed in that script with the question each settles.", ""]
    listed_now = [c for c in ordered if is_listed(c)]
    review_left = [c for c in ordered if c["climate"]["tier"] in ("core", "enabling") and c["startup"]["status"] != "in"]
    lines += [f"- Companies: {len(before)} before, {len(ordered)} after ({len(added)} added from proposals-01).",
              f"- Listed (core or enabling, startup in): {sum(v[1] for v in before.values())} before, {len(listed_now)} after.",
              f"- Tiers now: " + ", ".join(f"{k} {v}" for k, v in sorted(Counter(c['climate']['tier'] for c in ordered).items())) + ".", ""]
    lines += ["## Listing changes", "", "| Company | Before | After | Listed | Why |", "|---|---|---|---|---|"]
    for company in ordered:
        cid = company["id"]
        old = before.get(cid)
        now = (summary(company), is_listed(company))
        if old is None or old != now:
            why = f"owner ruling {OWNER_RULINGS[cid]['q']}" if cid in OWNER_RULINGS else ("new proposal" if old is None else "scout's check")
            lines.append(f"| {company['name']} | {old[0] if old else 'not in registry'} | {now[0]} | {'yes' if now[1] else 'no'} | {why} |")
    lines += ["", "## Core or enabling but not listed", "", "| Company | Startup status | Reason |", "|---|---|---|"]
    lines += [f"| {c['name']} | {c['startup']['status']} | {c['startup'].get('reason') or ''} |" for c in review_left]
    LOG.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")

    print(f"companies: {len(before)} -> {len(ordered)}; listed: {sum(v[1] for v in before.values())} -> {len(listed_now)}")
    print(f"core or enabling but not listed: {[c['id'] for c in review_left]}")
    print(f"wrote {REGISTRY.name} and {LOG.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
