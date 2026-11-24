"""Checks on the publish step: what reaches the board data file, and that it is stable.

Run from the repository root:  uv run pytest tests/publish
"""
from __future__ import annotations

import copy
import itertools
import json
import random

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from pipeline.io import ROOT, load_json, load_yaml
from pipeline.publish import PublishError, build_board, dumps_board
from pipeline.publish import __main__ as cli
from pipeline.publish.__main__ import default_jobs, main
from tools.validate import is_listed, listed_functions

TAXONOMY = load_yaml(ROOT / "taxonomy.yml")
JOBS = load_json(ROOT / "data" / "seed" / "jobs.json")
REGISTRY = load_yaml(ROOT / "companies.yml")
BOARD_SCHEMA = load_json(ROOT / "pipeline" / "publish" / "board.schema.json")

LISTED_IDS = {company["id"] for company in REGISTRY["companies"] if is_listed(company)}
LISTED_FUNCTIONS = listed_functions(TAXONOMY)
UNLISTED_FUNCTIONS = {entry["id"] for entry in TAXONOMY["functions"]} - LISTED_FUNCTIONS


def board_errors(board: dict) -> list[str]:
    validator = Draft202012Validator(BOARD_SCHEMA, format_checker=FormatChecker())
    return [f"{list(error.absolute_path)}: {error.message[:160]}" for error in validator.iter_errors(board)]


def company(cid: str, tier: str, status: str, **extra) -> dict:
    record = {
        "id": cid, "name": cid.title(), "website": None, "careers_url": None, "hq": None,
        "ats": {"type": "greenhouse", "board": cid}, "read": "auto", "sectors": [], "stage": None,
        "founded": None, "headcount": None,
        "climate": {"tier": tier, "reason": None if tier == "unscreened" else f"{cid} reason.",
                    "basis": "provisional", "approved": False},
        "startup": {"status": status, "reason": None},
    }
    record.update(extra)
    return record


def job(jid: str, cid: str, **extra) -> dict:
    record = {
        "id": jid, "company_id": cid, "title": f"Engineer {jid}", "url": f"https://example.com/jobs/{jid}",
        "source": {"ats": "greenhouse", "board": cid, "posting_id": jid, "read": "auto"},
        "locations": [], "metros": [], "workplace": "unknown", "function": "engineering", "disciplines": [],
        "level": None, "employment": "unknown", "pay": None, "posted_date": None,
        "first_seen": "2026-11-20T08:00:00-07:00", "last_seen": "2026-11-23T08:00:00-07:00",
        "tagging": {"function_by": "rule", "disciplines_by": "rule", "level_by": "rule", "model": None},
    }
    record.update(extra)
    return record


def jobs_file(jobs: list[dict]) -> dict:
    return {"schema_version": 0, "generated_at": "2026-11-23T12:00:00-07:00", "source": "test", "jobs": jobs}


def registry(companies: list[dict]) -> dict:
    return {"registry_version": 0, "companies": companies}


# --- Listing rule -----------------------------------------------------------

def test_seed_default_build_holds_only_listed_companies_and_functions():
    board = build_board(JOBS, REGISTRY, TAXONOMY)
    expected = [j for j in JOBS["jobs"] if j["company_id"] in LISTED_IDS and j["function"] in LISTED_FUNCTIONS]
    assert board["scope"] == "listed"
    assert len(board["roles"]) == len(expected) > 0
    assert {role["co"] for role in board["roles"]} <= LISTED_IDS
    assert {role["fn"] for role in board["roles"]} <= LISTED_FUNCTIONS
    assert set(board["companies"]) <= LISTED_IDS
    assert not any(record.get("unlisted") for record in board["companies"].values())
    assert board["counts"]["roles_left_out"] == len(JOBS["jobs"]) - len(expected)


@pytest.mark.parametrize("tier,status", list(itertools.product(
    ["core", "enabling", "out", "unscreened"], ["in", "out", "review", "unscreened"])))
def test_listing_rule_for_every_tier_and_status(tier, status):
    reg = registry([company("alpha", tier, status), company("beta", "core", "in")])
    board = build_board(jobs_file([job("a1", "alpha"), job("b1", "beta")]), reg, TAXONOMY)
    should_list = tier in ("core", "enabling") and status == "in"
    assert ("alpha" in board["companies"]) is should_list
    assert ("a1" in {role["id"] for role in board["roles"]}) is should_list
    assert "b1" in {role["id"] for role in board["roles"]}
    # No trace of an unlisted company anywhere in the serialized file.
    if not should_list:
        assert "alpha" not in dumps_board(board)


def test_include_unlisted_keeps_everything_and_says_so():
    board = build_board(JOBS, REGISTRY, TAXONOMY, include_unlisted=True)
    assert board["scope"] == "all"
    assert len(board["roles"]) == len(JOBS["jobs"])
    assert board["counts"]["roles_left_out"] == 0
    for cid, record in board["companies"].items():
        assert bool(record.get("unlisted")) is (cid not in LISTED_IDS)


def test_every_function_is_listed_today():
    # The owner asked on 2026-11-24 for corporate roles to be brought in, so every
    # function is listed. If this fails, taxonomy.yml hid one again: check that the
    # board's "How this board is built" text still says the right thing.
    assert UNLISTED_FUNCTIONS == set()
    assert {"engineering", "sales-bd", "finance-legal"} <= LISTED_FUNCTIONS


def taxonomy_hiding(*hidden: str) -> dict:
    """A copy of the taxonomy with some functions switched to listed: false."""
    taxonomy = copy.deepcopy(TAXONOMY)
    for entry in taxonomy["functions"]:
        if entry["id"] in hidden:
            entry["listed"] = False
    return taxonomy


@pytest.mark.parametrize("function", ["sales-bd", "marketing", "finance-legal", "people-admin", "it"])
def test_a_role_in_an_unlisted_function_never_appears_by_default(function):
    # No function is unlisted today, so the switch is exercised on a modified copy.
    taxonomy = taxonomy_hiding(function)
    reg = registry([company("alpha", "core", "in")])
    jobs = [job("a1", "alpha"), job("a2", "alpha", function=function, title="Account Executive, Utilities")]
    board = build_board(jobs_file(jobs), reg, taxonomy)
    assert [role["id"] for role in board["roles"]] == ["a1"]
    assert "Account Executive" not in dumps_board(board)
    assert board["counts"]["left_out_function"] == 1 and board["counts"]["left_out_company"] == 0
    assert board["counts"]["functions"][function] == 0
    # The development build keeps it, and the taxonomy block marks the function as unlisted.
    dev = build_board(jobs_file(jobs), reg, taxonomy, include_unlisted=True)
    assert sorted(role["id"] for role in dev["roles"]) == ["a1", "a2"]
    assert {"id": function, "label": next(f["label"] for f in taxonomy["functions"] if f["id"] == function),
            "listed": False} in dev["taxonomy"]["functions"]


def test_a_listed_function_at_an_unlisted_company_counts_as_a_company_exclusion():
    reg = registry([company("alpha", "core", "in"), company("beta", "out", "in")])
    jobs = [job("a1", "alpha"), job("b1", "beta"), job("b2", "beta", function="sales-bd")]
    counts = build_board(jobs_file(jobs), reg, TAXONOMY)["counts"]
    assert (counts["roles"], counts["roles_left_out"], counts["left_out_company"], counts["left_out_function"]) == (1, 2, 2, 0)


@pytest.mark.parametrize("function", sorted(LISTED_FUNCTIONS))
def test_every_listed_function_reaches_the_board(function):
    reg = registry([company("alpha", "core", "in")])
    board = build_board(jobs_file([job("a1", "alpha", function=function)]), reg, TAXONOMY)
    assert [role["fn"] for role in board["roles"]] == [function]
    assert board["counts"]["functions"][function] == 1


# --- Shape ------------------------------------------------------------------

@pytest.mark.parametrize("include_unlisted", [False, True])
def test_seed_build_matches_the_board_schema(include_unlisted):
    assert board_errors(build_board(JOBS, REGISTRY, TAXONOMY, include_unlisted=include_unlisted)) == []


@pytest.mark.parametrize("include_unlisted", [False, True])
def test_every_role_has_a_company_record_and_every_company_has_a_role(include_unlisted):
    board = build_board(JOBS, REGISTRY, TAXONOMY, include_unlisted=include_unlisted)
    used = {role["co"] for role in board["roles"]}
    assert used == set(board["companies"])
    left_company = 0 if include_unlisted else sum(1 for j in JOBS["jobs"] if j["company_id"] not in LISTED_IDS)
    left_function = 0 if include_unlisted else sum(
        1 for j in JOBS["jobs"] if j["company_id"] in LISTED_IDS and j["function"] not in LISTED_FUNCTIONS)
    assert board["counts"] == {
        "roles": len(board["roles"]), "companies": len(board["companies"]),
        "roles_left_out": len(JOBS["jobs"]) - len(board["roles"]),
        "left_out_company": left_company, "left_out_function": left_function,
        "companies_provisional": sum(1 for record in board["companies"].values() if record.get("provisional")),
        "functions": {f["id"]: sum(1 for role in board["roles"] if role["fn"] == f["id"]) for f in TAXONOMY["functions"]},
    }
    assert list(board["counts"]["functions"]) == [f["id"] for f in TAXONOMY["functions"]]
    for record in board["companies"].values():
        assert record["name"] and record["tier"]
        if record["tier"] in ("core", "enabling"):
            assert record["reason"]


@pytest.mark.parametrize("include_unlisted", [False, True])
def test_every_id_used_has_a_label(include_unlisted):
    board = build_board(JOBS, REGISTRY, TAXONOMY, include_unlisted=include_unlisted)
    labels = {key: {entry["id"] for entry in entries} for key, entries in board["taxonomy"].items()}
    for role in board["roles"]:
        assert role["fn"] in labels["functions"]
        assert set(role.get("disc", [])) <= labels["disciplines"]
        assert set(role.get("metros", [])) <= labels["metros"]
        assert role.get("level") is None or role["level"] in labels["levels"]
        assert role.get("wp") is None or role["wp"] in labels["workplace"]
    for record in board["companies"].values():
        assert set(record.get("sectors", [])) <= labels["sectors"]
        assert record.get("stage") is None or record["stage"] in labels["stages"]
        assert record["tier"] in labels["climate_tiers"]


def test_company_and_role_fields_are_carried_over():
    reg = registry([company(
        "alpha", "enabling", "in", name="Alpha Motors", website="https://alpha.example", hq="Denver, CO",
        careers_url="https://alpha.example/careers", sectors=["ev", "charging"], stage="series-b",
    )])
    reg["companies"][0]["climate"]["approved"] = True
    pay = {"min": 150000, "max": 190000, "currency": "USD", "period": "year", "basis": "feed"}
    full = job(
        "a1", "alpha", title="Staff Controls Engineer", locations=[{"text": "Denver, CO"}, {"text": "US remote"}],
        metros=["denver"], workplace="remote", disciplines=["controls", "systems"], level="staff",
        employment="full-time", pay=pay, posted_date="2026-11-21", summary="Own the inverter control loop.",
    )
    product = job("a2", "alpha", function="product")   # no disciplines, as product roles usually have
    board = build_board(jobs_file([full, product]), reg, TAXONOMY)
    assert board["generated_at"] == "2026-11-23T12:00:00-07:00"
    assert board["companies"]["alpha"] == {
        "name": "Alpha Motors", "tier": "enabling", "reason": "alpha reason.", "sectors": ["ev", "charging"],
        "stage": "series-b", "hq": "Denver, CO", "website": "https://alpha.example",
        "careers": "https://alpha.example/careers",
    }
    assert board["counts"]["companies_provisional"] == 0
    by_id = {role["id"]: role for role in board["roles"]}
    assert by_id["a1"] == {
        "id": "a1", "co": "alpha", "title": "Staff Controls Engineer", "url": "https://example.com/jobs/a1",
        "fn": "engineering", "loc": ["Denver, CO", "US remote"], "metros": ["denver"], "st": ["co"], "wp": "remote", "disc": ["controls", "systems"],
        "level": "staff", "emp": "full-time", "pay": {"min": 150000, "max": 190000, "cur": "USD", "per": "year"},
        "posted": "2026-11-21", "seen": "2026-11-20", "summary": "Own the inverter control loop.",
    }
    # Nothing stated stays nothing stated: no pay, level, workplace or discipline is invented.
    assert by_id["a2"] == {"id": "a2", "co": "alpha", "title": "Engineer a2",
                           "url": "https://example.com/jobs/a2", "fn": "product", "seen": "2026-11-20"}
    assert board_errors(board) == []


def test_seed_pay_is_copied_exactly():
    board = build_board(JOBS, REGISTRY, TAXONOMY, include_unlisted=True)
    source = {j["id"]: j["pay"] for j in JOBS["jobs"]}
    for role in board["roles"]:
        pay = source[role["id"]]
        if pay is None:
            assert "pay" not in role
        else:
            assert role["pay"] == {"min": pay["min"], "max": pay["max"], "cur": pay["currency"], "per": pay["period"]}


def test_roles_are_newest_first():
    reg = registry([company("alpha", "core", "in")])
    jobs = [
        job("old", "alpha", posted_date="2026-11-01"),
        job("new", "alpha", posted_date="2026-11-22"),
        job("undated", "alpha", first_seen="2026-11-10T08:00:00-07:00"),   # falls back to first seen
    ]
    board = build_board(jobs_file(jobs), reg, TAXONOMY)
    assert [role["id"] for role in board["roles"]] == ["new", "undated", "old"]


# --- Stability --------------------------------------------------------------

@pytest.mark.parametrize("include_unlisted", [False, True])
def test_same_input_gives_the_same_bytes(include_unlisted):
    first = dumps_board(build_board(JOBS, REGISTRY, TAXONOMY, include_unlisted=include_unlisted))
    second = dumps_board(build_board(copy.deepcopy(JOBS), copy.deepcopy(REGISTRY), copy.deepcopy(TAXONOMY),
                                     include_unlisted=include_unlisted))
    assert first == second


def test_input_order_does_not_change_the_output():
    shuffled_jobs = copy.deepcopy(JOBS)
    shuffled_registry = copy.deepcopy(REGISTRY)
    rng = random.Random(7)
    rng.shuffle(shuffled_jobs["jobs"])
    rng.shuffle(shuffled_registry["companies"])
    assert dumps_board(build_board(shuffled_jobs, shuffled_registry, TAXONOMY, include_unlisted=True)) == \
        dumps_board(build_board(JOBS, REGISTRY, TAXONOMY, include_unlisted=True))


def test_build_does_not_change_its_inputs():
    jobs, reg = copy.deepcopy(JOBS), copy.deepcopy(REGISTRY)
    build_board(jobs, reg, TAXONOMY)
    assert jobs == JOBS and reg == REGISTRY


# --- Size -------------------------------------------------------------------

def test_two_thousand_roles_stay_well_under_five_megabytes():
    """Worst case on purpose: every role has pay, three locations and a full 500-character summary."""
    listed = [c for c in REGISTRY["companies"] if is_listed(c)]
    jobs = []
    for n in range(2000):
        jobs.append(job(
            f"greenhouse:board{n % 40}:{5400000000 + n}", listed[n % len(listed)]["id"],
            title="Senior Staff Power Electronics Hardware Design Engineer, Grid Storage Inverters",
            url=f"https://job-boards.greenhouse.io/board{n % 40}/jobs/{5400000000 + n}",
            locations=[{"text": "South San Francisco, California, United States"},
                       {"text": "Denver, Colorado, United States"}, {"text": "Remote (United States)"}],
            metros=["sf-bay-area", "denver"], workplace="hybrid",
            disciplines=["power-electronics", "electrical", "systems"], level="staff", employment="full-time",
            pay={"min": 170000, "max": 230000, "currency": "USD", "period": "year", "basis": "posting-text"},
            posted_date="2026-11-20", summary="x" * 500,
        ))
    text = dumps_board(build_board(jobs_file(jobs), REGISTRY, TAXONOMY))
    assert text.count("\n") > 2000
    assert len(text.encode("utf-8")) < 2_500_000


# --- Refusing bad input, and the command line -------------------------------

def test_bad_jobs_are_refused():
    bad = jobs_file([job("a1", "alpha", url="http://example.com/not-https")])
    with pytest.raises(PublishError):
        build_board(bad, registry([company("alpha", "core", "in")]), TAXONOMY)


def test_a_role_at_an_unknown_company_is_refused():
    with pytest.raises(PublishError):
        build_board(jobs_file([job("a1", "ghost")]), registry([company("alpha", "core", "in")]), TAXONOMY)


SEED_PATH = str(ROOT / "data" / "seed" / "jobs.json")
# The registry and taxonomy stay the real ones when a test points the repository root elsewhere.
CONTRACT_ARGS = ["--companies", str(ROOT / "companies.yml"), "--taxonomy", str(ROOT / "taxonomy.yml")]


def test_command_line_writes_the_file(tmp_path, capsys):
    # --jobs is explicit so the test means the same in a checkout that has data/jobs.json.
    out = tmp_path / "data" / "board.json"
    assert main(["--jobs", SEED_PATH, "--out", str(out)]) == 0
    assert out.read_text(encoding="utf-8") == dumps_board(build_board(JOBS, REGISTRY, TAXONOMY))
    assert load_json(out)["scope"] == "listed"
    assert "DEVELOPMENT BUILD" not in capsys.readouterr().out

    assert main(["--jobs", SEED_PATH, "--out", str(out), "--include-unlisted"]) == 0
    assert load_json(out)["scope"] == "all"
    assert "DEVELOPMENT BUILD" in capsys.readouterr().out


def test_command_line_writes_nothing_on_bad_input(tmp_path, capsys):
    bad = copy.deepcopy(JOBS)
    bad["jobs"][0]["company_id"] = "not-in-the-registry"
    jobs_path, out = tmp_path / "jobs.json", tmp_path / "board.json"
    jobs_path.write_text(json.dumps(bad), encoding="utf-8")
    assert main(["--jobs", str(jobs_path), "--out", str(out)]) == 1
    assert not out.exists()
    assert "nothing written" in capsys.readouterr().err


# --- Which jobs file the bare command reads ---------------------------------

def test_default_input_is_the_tagged_data_when_it_exists(tmp_path):
    (tmp_path / "data" / "seed").mkdir(parents=True)
    (tmp_path / "data" / "seed" / "jobs.json").write_text("{}", encoding="utf-8")
    (tmp_path / "data" / "jobs.json").write_text("{}", encoding="utf-8")
    path, why = default_jobs(tmp_path)
    assert path == tmp_path / "data" / "jobs.json" and "tagged" in why


def test_default_input_falls_back_to_the_seed(tmp_path):
    path, why = default_jobs(tmp_path)
    assert path == tmp_path / "data" / "seed" / "jobs.json" and "seed" in why


def test_bare_command_uses_and_names_the_tagged_data(tmp_path, monkeypatch, capsys):
    tagged = tmp_path / "data" / "jobs.json"
    tagged.parent.mkdir(parents=True)
    small = copy.deepcopy(JOBS)
    small["jobs"] = [j for j in small["jobs"] if j["company_id"] in LISTED_IDS][:3]
    tagged.write_text(json.dumps(small), encoding="utf-8")
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    out = tmp_path / "board.json"
    assert main(["--out", str(out), *CONTRACT_ARGS]) == 0
    assert f"Input: {tagged} (default: the tagged data)" in capsys.readouterr().out
    assert len(load_json(out)["roles"]) == 3


def test_bare_command_falls_back_to_the_seed_and_says_so(tmp_path, monkeypatch, capsys):
    seed = tmp_path / "data" / "seed" / "jobs.json"
    seed.parent.mkdir(parents=True)
    seed.write_text(json.dumps(JOBS), encoding="utf-8")
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    out = tmp_path / "board.json"
    assert main(["--out", str(out), *CONTRACT_ARGS]) == 0
    assert "(default: data/jobs.json not found, using the seed)" in capsys.readouterr().out
    assert load_json(out)["source"] == JOBS["source"]


def test_a_missing_jobs_file_is_a_clear_error_not_a_traceback(tmp_path, capsys):
    out = tmp_path / "board.json"
    assert main(["--jobs", str(tmp_path / "nope.json"), "--out", str(out)]) == 1
    assert "no jobs file at" in capsys.readouterr().err
    assert not out.exists()
