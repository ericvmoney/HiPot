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
from pipeline.publish.__main__ import main
from tools.validate import is_listed

TAXONOMY = load_yaml(ROOT / "taxonomy.yml")
JOBS = load_json(ROOT / "data" / "seed" / "jobs.json")
REGISTRY = load_yaml(ROOT / "companies.yml")
BOARD_SCHEMA = load_json(ROOT / "pipeline" / "publish" / "board.schema.json")

LISTED_IDS = {company["id"] for company in REGISTRY["companies"] if is_listed(company)}


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
        "locations": [], "metros": [], "workplace": "unknown", "disciplines": [], "level": None,
        "employment": "unknown", "pay": None, "posted_date": None,
        "first_seen": "2026-11-20T08:00:00-07:00", "last_seen": "2026-11-23T08:00:00-07:00",
        "tagging": {"disciplines_by": "rule", "level_by": "rule", "model": None},
    }
    record.update(extra)
    return record


def jobs_file(jobs: list[dict]) -> dict:
    return {"schema_version": 0, "generated_at": "2026-11-23T12:00:00-07:00", "source": "test", "jobs": jobs}


def registry(companies: list[dict]) -> dict:
    return {"registry_version": 0, "companies": companies}


# --- Listing rule -----------------------------------------------------------

def test_seed_default_build_holds_only_listed_companies():
    board = build_board(JOBS, REGISTRY, TAXONOMY)
    expected = [j for j in JOBS["jobs"] if j["company_id"] in LISTED_IDS]
    assert board["scope"] == "listed"
    assert len(board["roles"]) == len(expected) > 0
    assert {role["co"] for role in board["roles"]} <= LISTED_IDS
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


# --- Shape ------------------------------------------------------------------

@pytest.mark.parametrize("include_unlisted", [False, True])
def test_seed_build_matches_the_board_schema(include_unlisted):
    assert board_errors(build_board(JOBS, REGISTRY, TAXONOMY, include_unlisted=include_unlisted)) == []


@pytest.mark.parametrize("include_unlisted", [False, True])
def test_every_role_has_a_company_record_and_every_company_has_a_role(include_unlisted):
    board = build_board(JOBS, REGISTRY, TAXONOMY, include_unlisted=include_unlisted)
    used = {role["co"] for role in board["roles"]}
    assert used == set(board["companies"])
    assert board["counts"] == {
        "roles": len(board["roles"]), "companies": len(board["companies"]),
        "roles_left_out": len(JOBS["jobs"]) - len(board["roles"]),
        "companies_provisional": sum(1 for record in board["companies"].values() if record.get("provisional")),
    }
    for record in board["companies"].values():
        assert record["name"] and record["tier"]
        if record["tier"] in ("core", "enabling"):
            assert record["reason"]


@pytest.mark.parametrize("include_unlisted", [False, True])
def test_every_id_used_has_a_label(include_unlisted):
    board = build_board(JOBS, REGISTRY, TAXONOMY, include_unlisted=include_unlisted)
    labels = {key: {entry["id"] for entry in entries} for key, entries in board["taxonomy"].items()}
    for role in board["roles"]:
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
    board = build_board(jobs_file([full, job("a2", "alpha")]), reg, TAXONOMY)
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
        "loc": ["Denver, CO", "US remote"], "metros": ["denver"], "wp": "remote", "disc": ["controls", "systems"],
        "level": "staff", "emp": "full-time", "pay": {"min": 150000, "max": 190000, "cur": "USD", "per": "year"},
        "posted": "2026-11-21", "seen": "2026-11-20", "summary": "Own the inverter control loop.",
    }
    # Nothing stated stays nothing stated: no pay, level or workplace is invented.
    assert by_id["a2"] == {"id": "a2", "co": "alpha", "title": "Engineer a2",
                           "url": "https://example.com/jobs/a2", "seen": "2026-11-20"}
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


def test_command_line_writes_the_file(tmp_path, capsys):
    out = tmp_path / "data" / "board.json"
    assert main(["--out", str(out)]) == 0
    assert out.read_text(encoding="utf-8") == dumps_board(build_board(JOBS, REGISTRY, TAXONOMY))
    assert load_json(out)["scope"] == "listed"
    assert "DEVELOPMENT BUILD" not in capsys.readouterr().out

    assert main(["--out", str(out), "--include-unlisted"]) == 0
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
