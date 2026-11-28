"""The Companies page's data, site/data/companies.json (PLAN.md decision 27).

Every listed company, hiring or not, with its registry facts, where its open roles are, how many there are,
a pay note built from the board's market grades, and how its jobs are read. Written by the publish step
beside board.json, with the same generated_at.

Pay note, from the company's open roles on the board:
- unlisted: none of them publishes pay;
- few ("too few to say"): pay is published, but fewer than MIN_GRADED roles could be graded;
- above / at / below: the median of its graded roles' midpoints against their market (grades.py) is more
  than GRADE_MARGIN above, within it, or more than it below.
A company with no open roles has no pay note. Pay is never estimated.

Read status, from the registry and the collector's careers state:
- daily: the collector reads its job board every run;
- weekly: its listing's robots.txt disallows reading (decisions 12b and 24), so it is read at most weekly;
- not-read: not read automatically ('manual', 'none', or no known board); the page points to its careers link.
"""
from __future__ import annotations

from statistics import median
from typing import Any
from urllib.parse import urlsplit

from pipeline.publish import grades as paygrades
from pipeline.publish.states import US_STATES, elsewhere_states, metro_states, place_class, states_for
from tools.validate import company_categories, company_type, is_listed

COMPANIES_VERSION = 0
MIN_GRADED = 3
PAY_NOTES = (("above", "Above market"), ("at", "At market"), ("below", "Below market"),
             ("few", "Too few to say"), ("unlisted", "Unlisted salaries"))
READ_STATUSES = (("daily", "Read daily"), ("weekly", "Read weekly"), ("not-read", "Not read automatically"))


def pay_note(roles: list[dict], graded: dict[str, dict]) -> dict | None:
    """The company's pay note from its open roles (board jobs) and the market grades by role id."""
    if not roles:
        return None
    paid = sum(1 for job in roles if job["pay"])
    pcts = [graded[job["id"]]["pct"] for job in roles if job["id"] in graded]
    note: dict[str, Any] = {"roles": len(roles), "paid": paid, "graded": len(pcts)}
    if not paid:
        return {"v": "unlisted", **note}
    if len(pcts) < MIN_GRADED:
        return {"v": "few", **note}
    mid = median(pcts)
    margin = paygrades.GRADE_MARGIN * 100
    verdict = "above" if mid > margin else "below" if mid < -margin else "at"
    return {"v": verdict, **note, "pct": round(mid)}


def read_status(company: dict, careers_sites: dict | None = None) -> str:
    """daily, weekly or not-read (see the module notes)."""
    from pipeline.collect.run import READERS, WEEKLY   # the collector's own list of what it reads
    ats, board = company["ats"]["type"], company["ats"].get("board")
    if company["read"] != "auto" or not board or ats not in READERS:
        return "not-read"
    if ats in WEEKLY:
        return "weekly"
    if ats == "other" and careers_sites:
        from pipeline.collect.careers import registrable
        # The careers reader keeps state only for pages whose robots.txt disallows them: those are weekly.
        if registrable(urlsplit(board).netloc) in careers_sites:
            return "weekly"
    return "daily"


def _record(company: dict, roles: list[dict], new_ids: set[str], graded: dict[str, dict], careers_sites: dict | None,
            metro_codes: dict[str, list[str]] | None = None) -> dict:
    record: dict[str, Any] = {"id": company["id"], "name": company["name"], "cats": company_categories(company),
                              "tier": company["climate"]["tier"], "type": company_type(company)}
    if company["climate"].get("reason"):
        record["reason"] = company["climate"]["reason"]
    if company["startup"].get("reason"):
        record["type_why"] = company["startup"]["reason"]
    if company["sectors"]:
        record["sectors"] = list(company["sectors"])
    for key in ("stage", "founded", "parent", "hq"):
        if company.get(key):
            record[key] = company[key]
    if company.get("headcount"):
        count = company["headcount"]
        record["hc"] = {"n": count["value"], "as_of": count["as_of"], "src": count["source"]}
    for key, source in (("website", "website"), ("careers", "careers_url")):
        if company.get(source):
            record[key] = company[source]
    # Where its open roles are; with none, its headquarters (above) stands in.
    metros = sorted({metro for job in roles for metro in job["metros"]})
    states = sorted({state for job in roles for state in states_for(job["locations"])})
    if metros:
        record["metros"] = metros
    if states:
        record["st"] = states
    # As on the board: remote means remote in the US; roles outside every metro area are abroad, in the US
    # (a rural plant, or a city not yet placed) or unclear; "elsewhere in" a state is outside its metro areas.
    classes = {job["id"]: place_class(job) for job in roles}
    if any(job["workplace"] == "remote" and classes[job["id"]] != "abroad" for job in roles):
        record["remote"] = True
    outside = [kind for kind in ("abroad", "us", "unclear")
               if any(classes[job["id"]] == kind and (kind == "abroad" or job["workplace"] != "remote") for job in roles)]
    if outside:
        record["out"] = outside
    elsewhere = sorted({state for job in roles for state in elsewhere_states(job, metro_codes or {})})
    if elsewhere:
        record["es"] = elsewhere
    record["roles"] = len(roles)
    fresh = sum(1 for job in roles if job["id"] in new_ids)
    if fresh:
        record["new"] = fresh
    if roles:
        by_fn: dict[str, int] = {}
        for job in roles:
            by_fn[job["function"]] = by_fn.get(job["function"], 0) + 1
        record["fns"] = dict(sorted(by_fn.items(), key=lambda item: (-item[1], item[0])))
    note = pay_note(roles, graded)
    if note:
        record["pay"] = note
    record["read"] = read_status(company, careers_sites)
    return record


def build_companies(companies: dict[str, dict], kept: list[dict], taxonomy: dict, generated_at: str,
                    new_ids: set[str], include_unlisted: bool = False, careers_sites: dict | None = None) -> dict:
    """companies.json as a dict. `kept` are the board's roles (jobs), `new_ids` the new ones among them."""
    graded = paygrades.grades(kept)
    by_company: dict[str, list[dict]] = {}
    for job in kept:
        by_company.setdefault(job["company_id"], []).append(job)
    chosen = [company for company in companies.values() if include_unlisted or is_listed(company)]
    chosen.sort(key=lambda company: (company["name"].casefold(), company["id"]))
    metro_codes = {entry["id"]: metro_states(entry["label"]) for entry in taxonomy["metros"]}
    records = [_record(company, by_company.get(company["id"], []), new_ids, graded, careers_sites, metro_codes)
               for company in chosen]

    used_metros = {metro for record in records for metro in record.get("metros", [])}
    used_states = {state for record in records for state in record.get("st", []) + record.get("es", [])}
    labels = {
        "categories": [{"id": e["id"], "label": e["label"], **({"default": True} if e.get("default") else {})}
                       for e in taxonomy.get("categories", [])],
        "sectors": [{"id": e["id"], "label": e["label"]} for e in taxonomy["sectors"]],
        "stages": [{"id": e["id"], "label": e["label"]} for e in taxonomy["stages"]],
        "functions": [{"id": e["id"], "label": e["label"]} for e in taxonomy["functions"]],
        "climate_tiers": [{"id": e["id"], "label": e["label"]} for e in taxonomy["climate_tiers"]],
        "metros": [{"id": e["id"], "label": e["label"]} for e in taxonomy["metros"] if e["id"] in used_metros],
        "states": [{"id": code.lower(), "label": name} for code, name in sorted(US_STATES.items(), key=lambda item: item[1])
                   if code.lower() in used_states],
        "pay": [{"id": key, "label": label} for key, label in PAY_NOTES],
        "read": [{"id": key, "label": label} for key, label in READ_STATUSES],
    }
    return {
        "companies_version": COMPANIES_VERSION,
        "generated_at": generated_at,
        "scope": "all" if include_unlisted else "listed",
        "counts": {
            "companies": len(records),
            "hiring": sum(1 for record in records if record["roles"]),
            "read": {key: sum(1 for record in records if record["read"] == key) for key, _ in READ_STATUSES},
            "pay": {key: sum(1 for record in records if record.get("pay", {}).get("v") == key) for key, _ in PAY_NOTES},
        },
        "labels": labels,
        "companies": records,
    }
