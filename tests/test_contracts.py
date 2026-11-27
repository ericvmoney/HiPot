"""Contract checks: the seed data validates, and the validator rejects bad data.

Run from the repository root:  uv run pytest
"""
from __future__ import annotations

import copy

import pytest

from pipeline.io import ROOT, load_json, load_yaml
from pipeline.seed.import_old_hub import job_id, level_from_title, parse_pay, parse_source, seed_function
from tools.validate import (
    check_companies, check_jobs, check_persona, check_raw_jobs, listed_functions, schema_errors, schema_registry,
)

REGISTRY, SCHEMAS = schema_registry()
TAXONOMY = load_yaml(ROOT / "taxonomy.yml")
JOBS = load_json(ROOT / "data" / "seed" / "jobs.json")
COMPANIES = load_yaml(ROOT / "companies.yml")
PERSONA = load_yaml(ROOT / "schema" / "examples" / "persona.example.yml")


def job_errors(job: dict) -> list[str]:
    return schema_errors(job, SCHEMAS["job.schema.json"], REGISTRY)


def test_seed_jobs_validate():
    assert schema_errors(JOBS, SCHEMAS["jobs-file.schema.json"], REGISTRY) == []
    company_ids = {company["id"] for company in COMPANIES["companies"]}
    assert check_jobs(JOBS, TAXONOMY, company_ids) == []
    assert len(JOBS["jobs"]) > 400


def test_registry_validates():
    assert schema_errors(COMPANIES, SCHEMAS["companies-file.schema.json"], REGISTRY) == []
    assert check_companies(COMPANIES, TAXONOMY) == []


def test_example_persona_validates():
    assert schema_errors(PERSONA, SCHEMAS["persona.schema.json"], REGISTRY) == []
    assert check_persona(PERSONA, TAXONOMY) == []


def test_no_seed_job_links_to_an_aggregator():
    for job in JOBS["jobs"]:
        assert "linkedin.com" not in job["url"]


@pytest.mark.parametrize("field,value", [
    ("url", "http://example.com/job"),          # not https
    ("url", "not a url"),
    ("first_seen", "2026-11-23"),               # date where a date-time is required
    ("posted_date", "23 Nov 2026"),
    ("workplace", "wfh"),
    ("level", "Senior"),                        # not a slug
    ("disciplines", ["Systems Engineering"]),
    ("disciplines", ["systems", "electrical", "mechanical", "test"]),   # more than three
    ("function", "Engineering"),               # not a slug
    ("function", None),
    ("pay", {"min": 1, "max": 2, "currency": "usd", "period": "year", "basis": "seed"}),
    ("pay", {"min": 1, "max": 2, "currency": "USD", "period": "year", "basis": "estimate"}),
])
def test_bad_job_fields_are_rejected(field, value):
    job = copy.deepcopy(JOBS["jobs"][0])
    assert job_errors(job) == []
    job[field] = value
    assert job_errors(job), f"{field}={value!r} should not validate"


def test_unknown_job_field_and_missing_field_are_rejected():
    job = copy.deepcopy(JOBS["jobs"][0])
    job["score"] = 0.9
    assert job_errors(job)
    job = copy.deepcopy(JOBS["jobs"][0])
    del job["tagging"]
    assert job_errors(job)
    job = copy.deepcopy(JOBS["jobs"][0])
    del job["function"]
    assert job_errors(job)
    job = copy.deepcopy(JOBS["jobs"][0])
    del job["tagging"]["function_by"]
    assert job_errors(job)


def test_taxonomy_membership_is_checked():
    jobs = copy.deepcopy(JOBS)
    jobs["jobs"] = jobs["jobs"][:1]
    jobs["jobs"][0]["disciplines"] = ["underwater-basket-weaving"]
    jobs["jobs"][0]["function"] = "astrology"
    jobs["jobs"][0]["company_id"] = "no-such-company"
    problems = check_jobs(jobs, TAXONOMY, {"some-company"})
    assert any("unknown discipline" in line for line in problems)
    assert any("unknown function" in line for line in problems)
    assert any("not in the registry" in line for line in problems)


def test_functions_are_complete_and_switchable():
    functions = TAXONOMY["functions"]
    assert len({f["id"] for f in functions}) == len(functions)
    for entry in functions:
        assert entry["label"] and entry["covers"] and isinstance(entry["listed"], bool), entry["id"]
    listed = listed_functions(TAXONOMY)
    # Every function is listed since 2026-11-24, when the owner brought corporate roles in.
    assert listed == {entry["id"] for entry in functions}
    # Product and program moved from disciplines to functions in taxonomy version 1.
    assert not {"product", "program"} & {d["id"] for d in TAXONOMY["disciplines"]}


@pytest.mark.parametrize("title,profiles,expected", [
    ("Senior Systems Engineer", ["sys"], "engineering"),
    ("Staff Product Manager, Hardware", ["prod"], "product"),
    ("Product Design Engineer", ["prod", "mech"], "engineering"),
    ("Fusion Program Lead - Plant Control Systems", ["sys"], "project-program"),
    ("Senior Construction Manager", ["elec"], "project-program"),
    ("Test Technician II", ["test"], "technician"),
])
def test_seed_function(title, profiles, expected):
    assert seed_function(title, profiles) == expected


def test_categories_clean_tech_is_the_default_and_never_written():
    categories = {c["id"]: c for c in TAXONOMY["categories"]}
    assert [cid for cid, c in categories.items() if c.get("default")] == ["clean-tech"]
    for cid in ("autonomy-robotics", "aerospace-space", "semis-electronics", "advanced-manufacturing",
                "data-centers", "defense", "mining", "oil-gas"):
        assert categories[cid]["label"] and categories[cid]["covers"]
    company = copy.deepcopy(COMPANIES["companies"][0])
    company["categories"] = ["clean-tech"]
    assert schema_errors(company, SCHEMAS["company.schema.json"], REGISTRY)      # implied by the tier, never written
    registry = {"companies": [dict(company, categories=["astrology"])]}
    assert any("unknown category" in line for line in check_companies(registry, TAXONOMY))


def test_screened_company_needs_a_reason():
    company = copy.deepcopy(COMPANIES["companies"][0])
    company["climate"] = {"tier": "out", "reason": None, "basis": "human", "approved": True}
    assert schema_errors(company, SCHEMAS["company.schema.json"], REGISTRY)


def test_persona_rejects_identity_fields():
    persona = copy.deepcopy(PERSONA)
    persona["email"] = "someone@example.com"
    assert schema_errors(persona, SCHEMAS["persona.schema.json"], REGISTRY)


def test_persona_function_membership_is_checked():
    persona = copy.deepcopy(PERSONA)
    persona["functions"] = ["engineering", "astrology"]
    assert check_persona(persona, TAXONOMY) == ["unknown function 'astrology'"]


@pytest.mark.parametrize("url,expected", [
    ("https://job-boards.greenhouse.io/antora/jobs/123", ("greenhouse", "antora", "123")),
    ("https://boards.greenhouse.io/redwoodmaterials/jobs/456", ("greenhouse", "redwoodmaterials", "456")),
    ("https://jobs.ashbyhq.com/Ridealso/9aba06b4", ("ashby", "Ridealso", "9aba06b4")),
    ("https://jobs.lever.co/xcimer/790e748f", ("lever", "xcimer", "790e748f")),
    ("https://ats.rippling.com/aptera/jobs/b166d73d", ("rippling", "aptera", "b166d73d")),
    ("https://motional.com/open-positions/?gh_jid=7799671003#/7799671003", ("greenhouse", None, "7799671003")),
    ("https://woodward.wd5.myworkdayjobs.com/en-US/x/job/y", ("workday", "woodward", None)),
    ("https://www.zipline.com/careers/open-roles/1", ("unknown", None, None)),
])
def test_parse_source(url, expected):
    source = parse_source(url)
    assert (source["ats"], source["board"], source["posting_id"]) == expected
    if expected[1] and expected[2]:
        assert job_id(url, source) == ":".join(expected)
    else:
        assert job_id(url, source).startswith("web:")


@pytest.mark.parametrize("title,expected", [
    ("Senior Staff Mechanical Engineer", "staff"),
    ("Sr. Firmware Engineer", "senior"),
    ("Principal Engineer, SCADA", "principal"),
    ("Manufacturing Engineering Manager", "manager"),
    ("Senior Product Manager", "senior"),
    ("Technical Program Manager", None),
    ("Director, Power Device Engineering", "director"),
    ("VP of Engineering", "executive"),
    ("Engineer III, Energy Storage", "senior"),
    ("Test Engineer II", "mid"),
    ("Electrical Engineer I", "entry"),
    ("Mechanical Engineering Intern", "intern"),
    ("Mechanical Engineer, Machined Parts", None),
    ("Validation Engineer - HV systems", None),   # lower-case v is not level five
])
def test_level_from_title(title, expected):
    assert level_from_title(title) == expected


def test_a_board_token_with_a_space_gives_a_valid_id():
    url = "https://jobs.ashbyhq.com/Karman%20Industries/5863cf02-a3c9-47ac-8d67-11cc42db2670"
    identifier = job_id(url, parse_source(url))
    assert identifier == "ashby:Karman-Industries:5863cf02-a3c9-47ac-8d67-11cc42db2670"
    job = copy.deepcopy(JOBS["jobs"][0])
    job["id"] = identifier
    assert job_errors(job) == []


def test_ids_without_unsafe_characters_are_unchanged():
    # The seed ids must not move when the id rule learns to clean tokens.
    for job in JOBS["jobs"]:
        if job["source"]["board"] and job["source"]["posting_id"]:
            assert job["id"] == job_id(job["url"], job["source"])


def test_roles_sharing_one_address_get_different_ids():
    url = "https://workforcenow.adp.com/mascsr/default/mdf/recruitment/recruitment.html?cid=x"
    source = parse_source(url)
    first = job_id(url, source, "Senior Systems Engineer", "Longmont, CO")
    second = job_id(url, source, "Electrical Test Engineer", "Longmont, CO")
    assert first != second
    assert first == job_id(url, source, "senior systems engineer ", "Longmont, CO")


def test_parse_pay():
    assert parse_pay("$140k-$205k") == {"min": 140000, "max": 205000, "currency": "USD", "period": "year", "basis": "seed"}
    assert parse_pay("") is None
    assert parse_pay("$205k-$140k") is None


RAW = load_json(ROOT / "schema" / "examples" / "raw-jobs.example.json")


def test_example_raw_jobs_validate():
    assert schema_errors(RAW, SCHEMAS["raw-jobs-file.schema.json"], REGISTRY) == []
    company_ids = {company["id"] for company in COMPANIES["companies"]}
    assert check_raw_jobs(RAW, TAXONOMY, company_ids) == []


def test_raw_job_rejects_tagger_fields_and_needs_a_description():
    tagged = copy.deepcopy(RAW)
    tagged["jobs"][0]["disciplines"] = ["controls"]
    assert schema_errors(tagged, SCHEMAS["raw-jobs-file.schema.json"], REGISTRY)
    bare = copy.deepcopy(RAW)
    del bare["jobs"][0]["description_text"]
    assert schema_errors(bare, SCHEMAS["raw-jobs-file.schema.json"], REGISTRY)


def test_raw_jobs_check_catches_unknown_metro_and_company():
    bad = copy.deepcopy(RAW)
    bad["jobs"][0]["metros"] = ["atlantis"]
    bad["jobs"][0]["company_id"] = "no-such-company"
    problems = check_raw_jobs(bad, TAXONOMY, {company["id"] for company in COMPANIES["companies"]})
    assert any("metro" in line for line in problems) and any("registry" in line for line in problems)


def test_disciplines_are_optional_only_for_non_technical_personas():
    persona = copy.deepcopy(PERSONA)
    persona["functions"], persona["disciplines"] = ["supply-chain"], []
    assert schema_errors(persona, SCHEMAS["persona.schema.json"], REGISTRY) == []
    assert check_persona(persona, TAXONOMY) == []
    persona["functions"] = ["engineering"]
    assert any("discipline is needed" in line for line in check_persona(persona, TAXONOMY))
    del persona["functions"]                                   # absent means engineering
    assert any("discipline is needed" in line for line in check_persona(persona, TAXONOMY))
