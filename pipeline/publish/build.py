"""Build the board data file.

Rules, in the order they are applied:

1. The jobs file and the registry must pass the contract checks in
   `tools/validate.py`. Nothing is written from data that fails them.
2. A role reaches the file only when its company is listed (climate tier core
   or enabling AND startup status `in`, `tools.validate.is_listed`) AND its
   function is listed (`listed: true` in taxonomy.yml,
   `tools.validate.listed_functions`). `include_unlisted=True` is a
   development switch that keeps every role and marks the file, each unlisted
   company and each unlisted function so the page can say so.
3. A role keeps only what a visitor needs. Null, empty and "unknown" values
   are left out to keep the file small; the page treats a missing field as
   "not stated". Pay is copied as published and never derived.
4. Location: the taxonomy block carries only the metros used by roles in the
   file, and a `states` list of the US states they name. Every role carries
   its states (`st`), so a role outside every metro can still be found.
5. The output depends only on the input: the generated time is the jobs
   file's own `generated_at`, roles are sorted newest first with a fixed
   tie-break, and keys are written in a fixed order. The same input gives the
   same bytes.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pipeline.publish import grades as paygrades
from pipeline.publish import pay as paybands
from pipeline.publish import wages as paywages
from pipeline.publish.states import US_STATES, states_for
from tools.validate import check_companies, check_jobs, is_listed, listed_functions, schema_errors, schema_registry

BOARD_VERSION = 0
PAY_VERSION = 0

# Taxonomy lists the page needs labels for, in the order the page shows them.
TAXONOMY_KEYS = ("functions", "disciplines", "levels", "sectors", "stages", "workplace", "metros", "climate_tiers")


class PublishError(Exception):
    """The input failed a contract check; nothing should be written."""

    def __init__(self, problems: list[str]):
        super().__init__(f"{len(problems)} problem(s): " + "; ".join(problems[:5]))
        self.problems = problems


def _check_inputs(jobs_file: dict, registry_file: dict, taxonomy: dict) -> None:
    registry, schemas = schema_registry()
    problems = schema_errors(registry_file, schemas["companies-file.schema.json"], registry)
    if not problems:
        problems = check_companies(registry_file, taxonomy)
    if problems:
        raise PublishError([f"companies: {line}" for line in problems])
    problems = schema_errors(jobs_file, schemas["jobs-file.schema.json"], registry)
    if not problems:
        company_ids = {company["id"] for company in registry_file["companies"]}
        problems = check_jobs(jobs_file, taxonomy, company_ids)
    if problems:
        raise PublishError([f"jobs: {line}" for line in problems])


def _labels(taxonomy: dict, kept: list[dict]) -> dict[str, list[dict[str, Any]]]:
    labels = {key: [{"id": entry["id"], "label": entry["label"]} for entry in taxonomy[key]] for key in TAXONOMY_KEYS}
    listed = listed_functions(taxonomy)
    for entry in labels["functions"]:
        if entry["id"] not in listed:
            entry["listed"] = False
    # The metro list has hundreds of regions; keep only those used, in taxonomy order.
    used_metros = {metro for job in kept for metro in job["metros"]}
    labels["metros"] = [entry for entry in labels["metros"] if entry["id"] in used_metros]
    used_states = {state for job in kept for state in states_for(job["locations"])}
    labels["states"] = [{"id": code.lower(), "label": name}
                        for code, name in sorted(US_STATES.items(), key=lambda item: item[1])
                        if code.lower() in used_states]
    return labels


def _company_record(company: dict) -> dict[str, Any]:
    record: dict[str, Any] = {"name": company["name"], "tier": company["climate"]["tier"]}
    if company["climate"].get("reason"):
        record["reason"] = company["climate"]["reason"]
    if not company["climate"]["approved"]:
        record["provisional"] = True
    if company["sectors"]:
        record["sectors"] = list(company["sectors"])
    if company.get("stage"):
        record["stage"] = company["stage"]
    if company.get("hq"):
        record["hq"] = company["hq"]
    for key, source in (("website", "website"), ("careers", "careers_url")):
        if company.get(source):
            record[key] = company[source]
    if not is_listed(company):
        record["unlisted"] = True
    return record


def _role_date(job: dict) -> str:
    """The date a role is sorted by: the posted date, or the day it was first seen."""
    return job["posted_date"] or job["first_seen"][:10]


def _role_record(job: dict) -> dict[str, Any]:
    record: dict[str, Any] = {
        "id": job["id"],
        "co": job["company_id"],
        "title": job["title"],
        "url": job["url"],
        "fn": job["function"],
    }
    if job["locations"]:
        record["loc"] = [place["text"] for place in job["locations"]]
    if job["metros"]:
        record["metros"] = list(job["metros"])
    states = states_for(job["locations"])
    if states:
        record["st"] = states
    if job["workplace"] != "unknown":
        record["wp"] = job["workplace"]
    if job["disciplines"]:
        record["disc"] = list(job["disciplines"])
    if job["level"]:
        record["level"] = job["level"]
    if job["employment"] != "unknown":
        record["emp"] = job["employment"]
    if job["pay"]:
        pay = job["pay"]
        record["pay"] = {"min": pay["min"], "max": pay["max"], "cur": pay["currency"], "per": pay["period"]}
    if job["posted_date"]:
        record["posted"] = job["posted_date"]
    record["seen"] = job["first_seen"][:10]
    if job.get("summary"):
        record["summary"] = job["summary"]
    return record


def _select(jobs_file: dict, registry_file: dict, taxonomy: dict, include_unlisted: bool) -> dict[str, Any]:
    """The roles that reach the board, newest first, with the counts the board reports."""
    _check_inputs(jobs_file, registry_file, taxonomy)

    companies = {company["id"]: company for company in registry_file["companies"]}
    functions = listed_functions(taxonomy)
    company_ok = {cid: is_listed(company) for cid, company in companies.items()}
    left_out_company = sum(1 for job in jobs_file["jobs"] if not company_ok[job["company_id"]])
    left_out_function = sum(1 for job in jobs_file["jobs"]
                            if company_ok[job["company_id"]] and job["function"] not in functions)
    kept = [job for job in jobs_file["jobs"]
            if include_unlisted or (company_ok[job["company_id"]] and job["function"] in functions)]

    # Newest first; ties broken by company name, title and id so the order never depends on the input order.
    kept.sort(key=lambda job: (companies[job["company_id"]]["name"].casefold(), job["title"].casefold(), job["id"]))
    kept.sort(key=_role_date, reverse=True)
    return {"companies": companies, "kept": kept,
            "left_out_company": left_out_company, "left_out_function": left_out_function}


def build_board(jobs_file: dict, registry_file: dict, taxonomy: dict, include_unlisted: bool = False,
                grades: bool = True) -> dict:
    """Return the board data as a dict. Raises PublishError on input that fails the contracts.

    `grades` adds a pay-vs-market grade to each role with a published range (see grades.py).
    """
    selected = _select(jobs_file, registry_file, taxonomy, include_unlisted)
    companies, kept = selected["companies"], selected["kept"]
    left_out_company, left_out_function = selected["left_out_company"], selected["left_out_function"]

    used = {job["company_id"] for job in kept}
    company_records = {
        cid: _company_record(companies[cid])
        for cid in sorted(used, key=lambda cid: (companies[cid]["name"].casefold(), cid))
    }

    labels = _labels(taxonomy, kept)
    records = [_role_record(job) for job in kept]
    if grades:
        found = paygrades.grades(kept)
        for record in records:
            if record["id"] in found:
                record["grade"] = found[record["id"]]
        labels["grades"] = [{"id": key, "label": label} for key, label in paygrades.GRADES]

    return {
        "board_version": BOARD_VERSION,
        "generated_at": jobs_file["generated_at"],
        "source": jobs_file["source"],
        "scope": "all" if include_unlisted else "listed",
        "grades": grades,
        "counts": {
            "roles": len(kept),
            "companies": len(company_records),
            "roles_left_out": len(jobs_file["jobs"]) - len(kept),
            "left_out_company": 0 if include_unlisted else left_out_company,
            "left_out_function": 0 if include_unlisted else left_out_function,
            "companies_provisional": sum(1 for record in company_records.values() if record.get("provisional")),
            "functions": {entry["id"]: sum(1 for job in kept if job["function"] == entry["id"])
                          for entry in taxonomy["functions"]},
        },
        "taxonomy": labels,
        "companies": company_records,
        "roles": records,
    }


def build_pay(jobs_file: dict, registry_file: dict, taxonomy: dict, include_unlisted: bool = False,
              wages: dict | None = None) -> dict:
    """Pay bands for the candidate pay page, from the same roles the board shows.

    `wages` is the government wage reference (data/pay/bls-oews-2025.json); when given, the
    slice the page needs goes into `gov`.
    """
    kept = _select(jobs_file, registry_file, taxonomy, include_unlisted)["kept"]
    found = paybands.bands(kept)
    out = {
        "pay_version": PAY_VERSION,
        "generated_at": jobs_file["generated_at"],
        "scope": "all" if include_unlisted else "listed",
        "min_postings": paybands.MIN_BAND,
        "counts": {
            "postings": sum(1 for job in kept if paybands.usable_pay(job) and paybands.markets(job)),
            "year": sum(1 for job in kept if paybands.usable_pay(job) and job["pay"]["period"] == "year"
                        and paybands.markets(job)),
            "hour": sum(1 for job in kept if paybands.usable_pay(job) and job["pay"]["period"] == "hour"
                        and paybands.markets(job)),
            "left_out": sum(1 for job in kept if job["pay"] and not (paybands.usable_pay(job) and paybands.markets(job))),
        },
        "labels": {
            "groups": paybands.group_labels(taxonomy, (band["g"] for band in found)),
            "levels": [{"id": entry["id"], "label": entry["label"]} for entry in taxonomy["levels"]]
                      + [{"id": "none", "label": "Level not stated"}],
            "markets": paybands.market_labels(taxonomy, (band["m"] for band in found)),
        },
        "bands": found,
    }
    if wages:
        out["gov"] = paywages.page_wages(wages, found, (paybands.US, paybands.REMOTE))
    return out


def dumps_pay(pay: dict) -> str:
    """One band per line, like the board file."""
    head = {key: value for key, value in pay.items() if key != "bands"}
    lines = ["{"] + [f"{_compact(key)}:{_compact(value)}," for key, value in head.items()]
    lines.append('"bands":[')
    lines.append(",\n".join(_compact(band) for band in pay["bands"]))
    lines += ["]", "}"]
    return "\n".join(lines) + "\n"


def write_pay(pay: dict, path: Path | str) -> int:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = dumps_pay(pay).encode("utf-8")
    path.write_bytes(data)
    return len(data)


def _compact(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def dumps_board(board: dict) -> str:
    """Serialize with one company and one role per line: small, stable, and readable in a diff."""
    lines = ["{"]
    for key in ("board_version", "generated_at", "source", "scope", "grades", "counts", "taxonomy"):
        lines.append(f"{_compact(key)}:{_compact(board[key])},")
    lines.append('"companies":{')
    entries = [f"{_compact(cid)}:{_compact(record)}" for cid, record in board["companies"].items()]
    lines.append(",\n".join(entries))
    lines.append("},")
    lines.append('"roles":[')
    lines.append(",\n".join(_compact(role) for role in board["roles"]))
    lines.append("]")
    lines.append("}")
    return "\n".join(lines) + "\n"


def write_board(board: dict, path: Path | str) -> int:
    """Write the board file and return its size in bytes."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = dumps_board(board).encode("utf-8")
    path.write_bytes(data)
    return len(data)
