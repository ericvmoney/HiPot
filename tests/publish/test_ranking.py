"""Ranking roles for a persona (Milestone 2): the board's own code (`<script id="hipot-rank">` in
site/index.html), run in V8. It ranks roles for a person, never people."""
from __future__ import annotations

import re

import pytest

from pipeline.publish.pagejs import PageScripts, script_block
from tests.publish.test_page import PAGE, SCRIPT

LABELS = {
    "functions": {"engineering": "Engineering", "technician": "Technicians", "supply-chain": "Supply chain"},
    "disciplines": {"controls": "Controls", "systems": "Systems", "mechanical": "Mechanical", "firmware": "Firmware and embedded"},
    "levels": {"mid": "Mid", "senior": "Senior", "staff": "Staff", "principal": "Principal", "manager": "Manager", "director": "Director"},
    "metros": {"denver": "Denver-Aurora-Greeley, CO", "austin-tx": "Austin-Round Rock-San Marcos, TX"},
    "sectors": {"energy-storage": "Energy storage", "solar": "Solar", "fission": "Nuclear fission"},
    "stages": {"series-a": "Series A", "series-b": "Series B", "late": "Series D and later"},
}

PERSONA = {
    "persona_version": 0,
    "generated": {"by": "form", "on_device": True, "date": "2026-11-25"},
    "disciplines": ["controls", "systems"], "level": "staff",
    "skills": [{"name": "Simulink", "years": 9, "evidence": "Built the Simulink plant model"}],
    "locations": {"metros": ["denver"], "remote": True, "relocate": False},
    "preferences": {"sectors": ["energy-storage"], "stage": ["series-a", "series-b"], "min_base_usd": 185000},
    "exclude": {"sectors": ["fission"], "companies": ["Acme Reactors"]},
    "notes": "private note",
}

COMPANY = {"id": "kestrel", "name": "Kestrel", "sectors": ["energy-storage"], "stage": "series-a"}


def role(**fields):
    base = {"fn": "engineering", "level": "staff", "disc": ["controls"], "metros": ["denver"], "loc": ["Denver, CO"], "wp": "hybrid",
            "pay": {"min": 185000, "max": 220000, "cur": "USD", "per": "year"}}
    base.update(fields)
    return base


@pytest.fixture(scope="module")
def js():
    with PageScripts("hipot-rank") as scripts:
        yield scripts


def match(js, the_role, persona=PERSONA, company=COMPANY):
    return js.eval(f"HiPotRank.match({_j(the_role)}, {_j(company)}, HiPotRank.normalize({_j(persona)}), {_j(LABELS)})")


def _j(value):
    import json
    return json.dumps(value)


def test_a_perfect_fit_scores_100_and_says_why_in_one_line(js):
    result = match(js, role(wp="remote"))
    assert result["score"] == 100 and result["excluded"] is None
    assert result["why"] == "Controls · Staff · Denver or remote · energy storage · Series A · pays $185K–$220K"


def test_normalize_rejects_what_is_not_a_persona_and_defaults_to_engineering(js):
    for bad in ({}, {"persona_version": 1, "disciplines": ["controls"]}, {"persona_version": 0, "disciplines": []}, [1, 2]):
        with pytest.raises(Exception):
            js.call("HiPotRank.normalize", bad)
    assert js.call("HiPotRank.normalize", {"persona_version": 0, "disciplines": ["controls"]})["functions"] == ["engineering"]


def test_the_function_counts(js):
    assert match(js, role())["parts"]["fn"] == 25
    tech = match(js, role(fn="technician"))
    assert tech["parts"]["fn"] == 0 and tech["why"].startswith("Technicians role")


def test_the_personas_discipline_order_is_its_weight(js):
    first, second = match(js, role(disc=["controls"])), match(js, role(disc=["systems"]))
    both, other, unknown = match(js, role(disc=["controls", "systems"])), match(js, role(disc=["mechanical"])), match(js, role(disc=[]))
    assert both["parts"]["disc"] == first["parts"]["disc"] == 25
    assert 25 > second["parts"]["disc"] > unknown["parts"]["disc"] > other["parts"]["disc"] == 0
    # A second shared discipline adds a little to a lower one.
    three = dict(PERSONA, disciplines=["mechanical", "controls", "systems"])
    assert match(js, role(disc=["controls", "systems"]), three)["parts"]["disc"] > match(js, role(disc=["controls"]), three)["parts"]["disc"]
    assert other["why"].startswith("Mechanical, not one of your disciplines")


@pytest.mark.parametrize("level,points,said", [
    ("staff", 20, "Staff"), ("senior", 12, "Senior (one level down)"), ("principal", 12, "Principal (one level up)"),
    ("manager", 12, "Manager (a management role)"), ("mid", 4, "Mid (2 levels down)"), ("director", 4, "Director (one level up)"),
    (None, 8, "level not stated"),
])
def test_level_fit_exact_then_one_step_then_further(js, level, points, said):
    result = match(js, role(level=level))
    assert result["parts"]["level"] == points and said in result["why"]


def test_place_metro_remote_and_relocation(js):
    assert match(js, role())["parts"]["place"] == 15
    assert match(js, role(metros=[], loc=["Remote, US"], wp="remote"))["parts"]["place"] == 15
    elsewhere = role(metros=["austin-tx"], loc=["Round Rock, TX"], wp="onsite")
    not_moving = match(js, elsewhere)
    assert not_moving["parts"]["place"] == -10 and "Round Rock, not where you want to work" in not_moving["why"]
    moving = dict(PERSONA, locations={"metros": ["denver"], "remote": False, "relocate": True})
    assert match(js, elsewhere, moving)["parts"]["place"] == 8
    unstated = dict(PERSONA, locations={"metros": ["denver"], "remote": False})
    assert match(js, elsewhere, unstated)["parts"]["place"] == 4
    not_remote = dict(PERSONA, locations={"metros": ["denver"], "remote": False})
    assert match(js, role(metros=[], loc=["Remote"], wp="remote"), not_remote)["parts"]["place"] == 6


def test_preferred_sectors_and_stages(js):
    assert match(js, role())["parts"]["sector"] == 8
    assert match(js, role(), company=dict(COMPANY, sectors=["solar"]))["parts"]["sector"] == 0
    assert match(js, role(), company=dict(COMPANY, stage="late"))["parts"]["stage"] == 0
    assert match(js, role(), company=dict(COMPANY, stage=None))["parts"]["stage"] == 3


@pytest.mark.parametrize("company,the_role,reason", [
    (dict(COMPANY, name="ACME Reactors"), role(), "a company you left out"),
    (dict(COMPANY, sectors=["fission"]), role(), "a sector you left out (nuclear fission)"),
    (COMPANY, role(pay={"min": 150000, "max": 180000, "cur": "USD", "per": "year"}), "published pay below your minimum"),
    (COMPANY, role(pay={"min": 40, "max": 60, "cur": "USD", "per": "hour"}), "published pay below your minimum"),
])
def test_hard_exclusions(js, company, the_role, reason):
    assert match(js, the_role, company=company)["excluded"] == reason


def test_unpublished_pay_costs_a_few_points_and_never_hides_a_role(js):
    paid, unpaid = match(js, role()), match(js, role(pay=None))
    assert unpaid["excluded"] is None and unpaid["parts"]["pay"] == -3 and paid["score"] - unpaid["score"] == 3
    assert "pay not published" in unpaid["why"]
    straddles = match(js, role(pay={"min": 160000, "max": 200000, "cur": "USD", "per": "year"}))
    assert straddles["parts"]["pay"] == -1 and straddles["excluded"] is None
    no_minimum = dict(PERSONA, preferences={})
    assert match(js, role(pay=None), no_minimum)["parts"]["pay"] == 0
    assert match(js, role(pay={"min": 90, "max": 120, "cur": "EUR", "per": "hour"}))["parts"]["pay"] == -3


def test_rank_orders_by_score_keeps_ties_in_order_and_drops_exclusions(js):
    roles = [{"id": "a", "match": {"score": 50, "excluded": None}}, {"id": "b", "match": {"score": 80, "excluded": None}},
             {"id": "c", "match": {"score": 50, "excluded": None}}, {"id": "d", "match": {"score": 99, "excluded": "a company you left out"}}]
    assert [r["id"] for r in js.call("HiPotRank.rank", roles)] == ["b", "a", "c"]


def test_the_tab_keeps_only_what_the_ranking_reads(js):
    kept = js.call("HiPotRank.forTab", PERSONA)
    assert "skills" not in kept and "notes" not in kept and "generated" not in kept
    assert js.call("HiPotRank.normalize", kept) == js.call("HiPotRank.normalize", PERSONA)


# --- The board page: the persona stays in the tab --------------------------------------------------

RANK = script_block("hipot-rank")


def test_the_ranking_block_is_pure():
    for needle in ("fetch(", "XMLHttpRequest", "sendBeacon", "Storage", "document.", "window.", "location."):
        assert needle not in RANK, needle


def test_the_persona_is_kept_in_session_storage_only_and_never_in_the_address():
    assert "var PERSONA_KEY = 'hipot-persona';" in SCRIPT
    assert set(re.findall(r"sessionStorage\.(\w+)\(PERSONA_KEY", SCRIPT)) == {"setItem", "getItem", "removeItem"}
    code = re.sub(r"//[^\n]*", "", SCRIPT)
    assert len(re.findall(r"sessionStorage", code)) == 3 and "localStorage" not in PAGE
    encode = SCRIPT[SCRIPT.index("function encodeState()"):SCRIPT.index("function decodeState(")]
    assert "persona" not in encode
    # What is stored is the reduced form, never the file as opened.
    assert "JSON.stringify(HiPotRank.forTab(data))" in SCRIPT


def test_persona_controls_are_on_the_board():
    for needle in ('id="persona-use">Use my persona<', 'id="persona-stop">Stop using it<', ">Persona in use<",
                   "'Why it matches: '", "text: 'Best match'"):
        assert needle in PAGE, needle
    assert "return HiPotRank.rank(rolesInOrder);" in SCRIPT
    assert "if (role.match && role.match.excluded) continue;" in SCRIPT
