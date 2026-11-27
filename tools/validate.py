"""Validate the data files against the contracts.

Checks, in order:
  1. Each file against its JSON Schema (formats included).
  2. Every taxonomy id used (function, discipline, level, metro, sector, stage) exists in taxonomy.yml.
  3. Job ids are unique and every job's company_id is in the registry.
  4. Company ids are unique.

Run from the repository root:

    uv run python -m tools.validate                      # seed jobs + registry + example persona
    uv run python -m tools.validate --jobs data/jobs.json
    uv run python -m tools.validate --raw data/jobs.raw.json
    uv run python -m tools.validate --persona my.yml

Exits 1 if anything fails.
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from pipeline.io import ROOT, load_json, load_yaml

SCHEMA_DIR = ROOT / "schema"
MAX_SHOWN = 15


def schema_registry() -> tuple[Registry, dict]:
    schemas = {path.name: load_json(path) for path in sorted(SCHEMA_DIR.glob("*.schema.json"))}
    for name, schema in schemas.items():
        Draft202012Validator.check_schema(schema)
    registry = Registry().with_resources(
        (schema["$id"], Resource.from_contents(schema)) for schema in schemas.values()
    )
    return registry, schemas


def schema_errors(data, schema: dict, registry: Registry) -> list[str]:
    validator = Draft202012Validator(schema, registry=registry, format_checker=FormatChecker())
    found = []
    for error in sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path)):
        where = "/".join(str(part) for part in error.absolute_path) or "(root)"
        found.append(f"{where}: {error.message[:200]}")
    return found


def ids(taxonomy: dict, key: str) -> set[str]:
    return {entry["id"] for entry in taxonomy[key]}


def listed_functions(taxonomy: dict) -> set[str]:
    """Functions whose roles reach the public board (`listed: true` in taxonomy.yml)."""
    return {entry["id"] for entry in taxonomy["functions"] if entry.get("listed")}


def check_jobs(jobs_file: dict, taxonomy: dict, company_ids: set[str]) -> list[str]:
    disciplines, levels, metros = ids(taxonomy, "disciplines"), ids(taxonomy, "levels"), ids(taxonomy, "metros")
    functions = ids(taxonomy, "functions")
    problems = []
    counts = Counter(job["id"] for job in jobs_file["jobs"])
    problems += [f"duplicate job id {job_id} ({n} times)" for job_id, n in counts.items() if n > 1]
    for job in jobs_file["jobs"]:
        tag = f"job {job['id']}"
        if job["function"] not in functions:
            problems.append(f"{tag}: unknown function '{job['function']}'")
        problems += [f"{tag}: unknown discipline '{d}'" for d in job["disciplines"] if d not in disciplines]
        problems += [f"{tag}: unknown metro '{m}'" for m in job["metros"] if m not in metros]
        if job["level"] is not None and job["level"] not in levels:
            problems.append(f"{tag}: unknown level '{job['level']}'")
        if job["company_id"] not in company_ids:
            problems.append(f"{tag}: company_id '{job['company_id']}' is not in the registry")
        if job["pay"] and job["pay"]["min"] > job["pay"]["max"]:
            problems.append(f"{tag}: pay min is above max")
    return problems


def check_raw_jobs(raw_file: dict, taxonomy: dict, company_ids: set[str]) -> list[str]:
    metros = ids(taxonomy, "metros")
    problems = []
    counts = Counter(job["id"] for job in raw_file["jobs"])
    problems += [f"duplicate job id {job_id} ({n} times)" for job_id, n in counts.items() if n > 1]
    for job in raw_file["jobs"]:
        tag = f"job {job['id']}"
        problems += [f"{tag}: unknown metro '{m}'" for m in job["metros"] if m not in metros]
        if job["company_id"] not in company_ids:
            problems.append(f"{tag}: company_id '{job['company_id']}' is not in the registry")
    problems += [f"run entry: company_id '{entry['company_id']}' is not in the registry"
                 for entry in raw_file["run"]["companies"] if entry["company_id"] not in company_ids]
    return problems


def check_companies(registry_file: dict, taxonomy: dict) -> list[str]:
    sectors, stages = ids(taxonomy, "sectors"), ids(taxonomy, "stages")
    categories = ids(taxonomy, "categories") - {"clean-tech"}
    problems = []
    counts = Counter(company["id"] for company in registry_file["companies"])
    for company in registry_file["companies"]:
        problems += [f"company {company['id']}: unknown category '{c}'" for c in company.get("categories") or [] if c not in categories]
    problems += [f"duplicate company id {cid} ({n} times)" for cid, n in counts.items() if n > 1]
    for company in registry_file["companies"]:
        tag = f"company {company['id']}"
        problems += [f"{tag}: unknown sector '{s}'" for s in company["sectors"] if s not in sectors]
        if company["stage"] is not None and company["stage"] not in stages:
            problems.append(f"{tag}: unknown stage '{company['stage']}'")
    return problems


def check_persona(persona: dict, taxonomy: dict) -> list[str]:
    disciplines, levels = ids(taxonomy, "disciplines"), ids(taxonomy, "levels")
    sectors, stages = ids(taxonomy, "sectors"), ids(taxonomy, "stages")
    problems = [f"unknown discipline '{d}'" for d in persona.get("disciplines", []) if d not in disciplines]
    problems += [f"unknown function '{f}'" for f in persona.get("functions", []) if f not in ids(taxonomy, "functions")]
    # Disciplines are technical fields: required for engineering, science and
    # technician work (no functions means engineering), optional otherwise.
    technical = set(persona.get("functions") or ["engineering"]) & {"engineering", "science", "technician"}
    if technical and not persona.get("disciplines"):
        problems.append(f"at least one discipline is needed for {', '.join(sorted(technical))} work")
    if persona.get("level") is not None and persona["level"] not in levels:
        problems.append(f"unknown level '{persona['level']}'")
    problems += [f"unknown domain '{s}'" for s in persona.get("domains", []) if s not in sectors]
    preferences = persona.get("preferences", {})
    problems += [f"unknown preferred stage '{s}'" for s in preferences.get("stage", []) if s not in stages]
    problems += [f"unknown preferred sector '{s}'" for s in preferences.get("sectors", []) if s not in sectors]
    problems += [f"unknown excluded sector '{s}'" for s in persona.get("exclude", {}).get("sectors", []) if s not in sectors]
    return problems


def is_clean_tech(company: dict) -> bool:
    """Core or enabling under the climate rubric."""
    return company["climate"]["tier"] in ("core", "enabling")


def company_categories(company: dict) -> list[str]:
    """Every category the company is in: clean tech first when its tier makes it so, then the
    adjacent ones it carries in `categories` (decision 23)."""
    return (["clean-tech"] if is_clean_tech(company) else []) + list(company.get("categories") or [])


def is_listed(company: dict) -> bool:
    """A company's roles reach the board when it is clean tech (core or enabling, decision 14)
    or in one of the adjacent categories (decision 23).

    The startup test does not decide listing; it labels the company (see company_type).
    """
    return bool(company_categories(company))


def company_type(company: dict) -> str:
    """'startup' when the startup test says in, 'established' when it says out, else 'unchecked'."""
    return {"in": "startup", "out": "established"}.get(company["startup"]["status"], "unchecked")


def report(name: str, problems: list[str]) -> bool:
    if not problems:
        print(f"PASS  {name}")
        return True
    print(f"FAIL  {name}: {len(problems)} problem(s)")
    for line in problems[:MAX_SHOWN]:
        print(f"        {line}")
    if len(problems) > MAX_SHOWN:
        print(f"        ... and {len(problems) - MAX_SHOWN} more")
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate HiPot data files against the contracts.")
    parser.add_argument("--jobs", type=Path, default=ROOT / "data" / "seed" / "jobs.json")
    parser.add_argument("--companies", type=Path, default=ROOT / "companies.yml")
    parser.add_argument("--raw", type=Path, action="append", default=None, help="a collector output file (data/jobs.raw.json)")
    parser.add_argument("--persona", type=Path, action="append", default=None)
    args = parser.parse_args()
    personas = args.persona or sorted((SCHEMA_DIR / "examples").glob("persona*.yml"))

    registry, schemas = schema_registry()
    taxonomy = load_yaml(ROOT / "taxonomy.yml")
    ok = True

    registry_file = load_yaml(args.companies)
    problems = schema_errors(registry_file, schemas["companies-file.schema.json"], registry)
    if not problems:
        problems = check_companies(registry_file, taxonomy)
    ok &= report(f"{args.companies.name} ({len(registry_file.get('companies', []))} companies)", problems)
    company_ids = {company["id"] for company in registry_file.get("companies", []) if "id" in company}

    jobs_file = load_json(args.jobs)
    problems = schema_errors(jobs_file, schemas["jobs-file.schema.json"], registry)
    if not problems:
        problems = check_jobs(jobs_file, taxonomy, company_ids)
    ok &= report(f"{args.jobs.name} ({len(jobs_file.get('jobs', []))} jobs)", problems)

    for path in args.raw or sorted((SCHEMA_DIR / "examples").glob("raw-jobs*.json")):
        raw_file = load_json(path)
        problems = schema_errors(raw_file, schemas["raw-jobs-file.schema.json"], registry)
        if not problems:
            problems = check_raw_jobs(raw_file, taxonomy, company_ids)
        ok &= report(f"{path.name} ({len(raw_file.get('jobs', []))} raw jobs)", problems)

    for path in personas:
        persona = load_yaml(path)
        problems = schema_errors(persona, schemas["persona.schema.json"], registry)
        if not problems:
            problems = check_persona(persona, taxonomy)
        ok &= report(path.name, problems)

    if ok:
        companies = registry_file["companies"]
        listed = {company["id"] for company in companies if is_listed(company)}
        by_type = Counter(company_type(c) for c in companies if is_listed(c))
        review = {c["id"] for c in companies if c["climate"]["tier"] in ("core", "enabling") and c["startup"]["status"] == "review"}
        tiers = Counter(company["climate"]["tier"] for company in companies)
        jobs = jobs_file["jobs"]
        print()
        print("Registry: " + ", ".join(f"{tier} {n}" for tier, n in sorted(tiers.items())))
        print(f"Listed now (clean tech or an adjacent category): {len(listed)} companies "
              f"({', '.join(f'{kind} {n}' for kind, n in sorted(by_type.items()))}), "
              f"{sum(job['company_id'] in listed for job in jobs)} of {len(jobs)} jobs")
        print(f"Waiting on the startup test (status 'review'): {len(review)} companies, "
              f"{sum(job['company_id'] in review for job in jobs)} jobs")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
