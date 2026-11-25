"""Apply the company scout's screening and the owner's rulings to companies.yml.

Inputs
  companies.yml                          the registry as it stands
  data/screening/seed-review.yml         the scout's checks of the seed companies
  data/screening/proposals-*.yml         the scout's new companies, every file
  data/screening/registry-fixes-*.yml    facts the registry lacks (filled, never overwritten)
  data/screening/careers-probe-*.yml     careers addresses and job boards found by the collector
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
PROBE_FILES = "careers-probe-*.yml"       # the collector's careers-page probes
LOG = SCREENING / "applied-latest.md"     # applied-01.md keeps the first run's log
HEADCOUNT_LINE, BORDERLINE = 4000, 5000   # agreed 2026-11-24: 4,000 people, about 25 percent tolerance
VENTURE_STAGES = {"pre-seed", "seed", "series-a", "series-b", "series-c", "late"}
READABLE = set(COLLECTOR_READERS)   # systems the collector reads with no switch needed
TODAY = "2026-11-24"
YEAR = int(TODAY[:4])

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
                "reason": "Battery-electric delivery aircraft for retail, restaurant and hospital deliveries, replacing car and van trips."},
    "wing": {"q": "A1", "tier": "enabling", "sectors": ["electric-aviation"]},
    # A2, as revised by the owner later on 2026-11-24: "Data center companies of any
    # kind" are out, "exceptions for energy sector companies that interact with data
    # center folks". So energy companies (generation, storage, grid equipment) that
    # sell to data centers stay in; equipment, cooling and computing made for data
    # centers, and companies that build or run them, are out. Fossil-fuelled
    # products (Arbor, Hyliion, Scale Microgrids) and compute (Crusoe) stay out.
    "veir": {"q": "A2", "tier": "core", "sectors": ["grid"],
             "reason": "High-temperature superconducting power cables that move electricity with far lower losses; first product serves AI data centers."},
    "amperesand": {"q": "A2", "tier": "enabling", "sectors": ["grid", "components"],
                   "reason": "Silicon-carbide solid-state transformers for grid and data-center power conversion."},
    "atomic-machines": {"q": "A2", "tier": "out", "sectors": ["components"],
                        "reason": "Relays and switches made first for AI data-center power systems; data-center equipment is out."},
    "spinor-energy": {"q": "A2", "tier": "core", "sectors": ["energy-storage"],
                      "reason": "Superconducting magnetic energy storage, aimed first at AI data centers."},
    "karman-industries": {"q": "A2", "tier": "out", "sectors": ["industrial-heat"],
                          "reason": "Heat pumps now aimed at data-center cooling; data-center equipment is out."},
    "panthalassa": {"q": "A2", "tier": "out", "sectors": ["distributed-generation"],
                    "reason": "Wave-powered ocean nodes whose stated product is on-board computing; computing is out."},
    "on-energy": {"q": "A2", "tier": "enabling", "sectors": ["energy-storage"], "basis": "provisional",
                  "reason": "Battery storage and power systems for data centers and industrial sites."},
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
    "mainspring-energy": {"q": "A7", "tier": "out",
                          "reason": "Linear generators that mostly run on natural gas or biogas today; excluded for now."},
    # A8: SENS is included.
    "stored-energy-systems-sens": {"q": "A8", "tier": "enabling", "sectors": ["grid", "components"],
                                   "reason": "DC power systems, chargers and controls for utilities, switchgear and backup power."},
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


def parent_is_large(text) -> bool:
    """True when the owner's headcount (the first figure in the scout's note) is
    at or above the cap. No figure counts as small: investment firms."""
    if isinstance(text, int):
        return text >= HEADCOUNT_LINE
    found = re.search(r"\d[\d,]*", str(text or ""))
    return bool(found) and int(found.group().replace(",", "")) >= HEADCOUNT_LINE


SHARE_SALE = re.compile(r"at-the-market|\bATM\b|registered direct|follow-on|secondary|shelf", re.I)


def fill_missing(company: dict, fix: dict) -> None:
    """Fill hq, founded, stage and headcount where the registry has none."""
    for field in ("hq", "founded", "stage"):
        value = (fix.get(field) or {}).get("value")
        if company.get(field) is None and value is not None:
            company[field] = value
    newer = headcount_from_review(fix) if (fix.get("headcount") or {}).get("value") is not None else None
    if newer and (company.get("headcount") is None or newer["as_of"] > company["headcount"]["as_of"]):
        company["headcount"] = newer
    # Startup-definition facts (registry-fixes-03 onward). An owner makes a company
    # not independent only when the owner itself is at or above the cap; a company
    # owned by an investment firm or a small company counts as independent.
    if fix.get("parent") and company.get("parent") is None:
        parent = fix["parent"].get("value") if isinstance(fix["parent"], dict) else fix["parent"]
        if parent_is_large(fix.get("parent_headcount")):
            company["parent"] = parent
        else:
            note = f"Owned by {parent}; counted as independent (owner under {HEADCOUNT_LINE:,} people or an investment firm)."
            if note not in (company.get("notes") or ""):
                company["notes"] = f"{company.get('notes') or ''} {note}".strip()
    raise_ = fix.get("last_raise")
    if raise_ and company.get("last_raise") is None and raise_.get("date"):
        company["last_raise"] = {"date": str(raise_["date"]), "type": raise_.get("type") or "equity round",
                                 "source": raise_.get("source") or "registry-fixes"}
    ipo = fix.get("ipo_year")
    ipo = ipo.get("value") if isinstance(ipo, dict) else ipo
    if ipo and company.get("ipo_year") is None:
        company["ipo_year"] = int(ipo)
    note = "Missing facts filled from data/screening/registry-fixes."
    if any(fix.get(f) for f in ("hq", "founded", "stage", "headcount", "parent", "last_raise", "ipo_year")) \
            and note not in (company.get("notes") or ""):
        company["notes"] = f"{company.get('notes') or ''} {note}".strip()


def startup_test(company: dict) -> tuple[str, str]:
    """The startup definition agreed on 2026-11-24 (PLAN.md section 9, item 10).

    Independent; under 4,000 people with about 25 percent tolerance (in when no
    figure exists); and at least one growth sign: founded within 15 years, an
    equity raise within 5 years, or public for under 5 years. Where the facts
    for the growth sign are missing, a private venture-stage company is given
    the benefit of the doubt and a public one is not.
    """
    head = company.get("headcount") or {}
    count = head.get("value")
    size = f"{count:,} people ({head.get('source')}, {head.get('as_of')})" if count else "no headcount figure found"
    if company.get("parent"):
        return "out", f"Part of {company['parent']}; not independent."
    if count and count > BORDERLINE:
        return "out", f"{size}: over the 4,000-person line."
    signs = []
    founded, stage = company.get("founded"), company.get("stage")
    if founded and founded >= YEAR - 15:          # "within the last 15 years" includes the boundary year
        signs.append(f"founded {founded}")
    raise_ = company.get("last_raise")
    # A share sale by a company that is already public is not startup funding.
    five_years_ago = f"{YEAR - 5}{TODAY[4:7]}"          # compared by year and month
    already_public = company.get("stage") == "public" or company.get("ipo_year")
    if raise_ and str(raise_["date"])[:7] >= five_years_ago[:len(str(raise_["date"])[:7])] \
            and not (already_public and SHARE_SALE.search(raise_["type"])):
        signs.append(f"{raise_['type']} in {str(raise_['date'])[:4]}")
    ipo = company.get("ipo_year")
    if ipo and ipo > YEAR - 5:
        signs.append(f"public since {ipo}")
    owner = "owner not yet checked" if stage == "subsidiary" else "independent"
    if signs:
        return "in", f"{owner.capitalize()}; {size}; growth sign: {', '.join(signs)}."
    if founded is None:
        return "in", f"{owner.capitalize()}; {size}; founding year not found, so included."
    if stage in VENTURE_STAGES and not raise_:
        return "in", (f"{owner.capitalize()}; {size}; founded {founded} but venture-backed ({stage}); "
                      f"latest round not yet checked, so included.")
    return "out", f"{owner.capitalize()}; {size}; founded {founded}, with no equity raise in 5 years or recent listing found."


LISTED = re.compile(r"\b(?:listed|went public|IPO|SPAC)\b[^.;]*?\b((?:19|20)\d\d)\b", re.I)


def listing_year(reason: str | None) -> int | None:
    """The year a public company listed, from the scout's wording ("listed via
    SPAC in 2022", "listed 2022 or 2023"): the first year named, the earlier
    and so stricter reading when sources differ."""
    found = LISTED.search(reason or "")
    return int(found.group(1)) if found else None


def apply_probe(company: dict, entry: dict) -> None:
    """A careers-page probe result: fill the careers address, and take a job
    board it found when the registry has none (ats type 'unknown')."""
    if entry.get("careers_url") and not company.get("careers_url"):
        company["careers_url"] = entry["careers_url"]
    boards = [b for b in (entry.get("ats") or []) if b.get("readable") and b.get("type") and b.get("board")]
    if entry.get("outcome") == "ats-found" and boards and company["ats"]["type"] == "unknown":
        company["ats"] = {"type": boards[0]["type"], "board": boards[0]["board"]}
        company["read"] = "auto"
        note = "Job board found by the collector's careers-page probe (data/screening/careers-probe-*.yml)."
        if note not in (company.get("notes") or ""):
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
    # Listing years the scout wrote only in prose: read them from its own
    # proposal text (the registry's reason is rewritten by startup_test).
    scout_reason = {p["id"]: (p.get("startup") or {}).get("reason") for p in proposals}
    for company in companies.values():
        if company.get("stage") == "public" and company.get("ipo_year") is None:
            year = listing_year(scout_reason.get(company["id"]) or company["startup"].get("reason"))
            if year:
                company["ipo_year"] = year

    for fix in fixes:
        if fix["id"] in companies:
            fill_missing(companies[fix["id"]], fix)

    probes = [e for path in sorted(SCREENING.glob(PROBE_FILES)) for e in load_yaml(path).get("companies", [])]
    for entry in probes:
        if entry.get("company_id") in companies:
            apply_probe(companies[entry["company_id"]], entry)

    # The agreed startup definition, for every company that has been looked at.
    # An owner ruling that names a company (OWNER_RULINGS) still wins, below.
    for company in companies.values():
        if company["startup"]["status"] != "unscreened":
            status, reason = startup_test(company)
            company["startup"] = {"status": status, "reason": reason}

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
