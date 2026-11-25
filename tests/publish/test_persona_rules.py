"""The persona page's resume rules (`<script id="persona-rules">` in site/persona.html), run in V8 on
synthetic resumes. No real resume or personal data is used anywhere."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from pipeline.io import ROOT, load_json, load_yaml
from pipeline.publish.build import build_taxonomy_file
from pipeline.publish.pagejs import PageScripts

TAXONOMY = build_taxonomy_file(load_yaml(ROOT / "taxonomy.yml"))
SCHEMA = Draft202012Validator(load_json(ROOT / "schema" / "persona.schema.json"), format_checker=FormatChecker())
FIXTURES = Path(__file__).parent / "fixtures"
RESUME_01 = (ROOT / "spikes" / "ollama-persona" / "resume_synthetic_01.txt").read_text(encoding="utf-8")
TECHNICIAN = (FIXTURES / "resume_synthetic_02_technician.txt").read_text(encoding="utf-8")
SUPPLY_CHAIN = (FIXTURES / "resume_synthetic_03_supply_chain.txt").read_text(encoding="utf-8")
TODAY = 2026 + 10 / 12   # November 2026, so "present" does not move


@pytest.fixture(scope="module")
def js():
    with PageScripts("persona-rules") as scripts:
        yield scripts


def extract(js, text):
    return js.call("PersonaRules.extract", text, TAXONOMY, {"today": TODAY})


def skills(found):
    return {skill["name"]: skill for skill in found["persona"]["skills"]}


@pytest.mark.parametrize("text", [RESUME_01, TECHNICIAN, SUPPLY_CHAIN], ids=["controls", "technician", "supply-chain"])
def test_each_synthetic_resume_gives_a_valid_persona_with_no_identity(js, text):
    saved = js.call("PersonaRules.forSaving", extract(js, text)["persona"])
    assert [error.message for error in SCHEMA.iter_errors(saved)] == []
    flat = json.dumps(saved)
    for needle in ("@example", "555", "Okafor", "Lindqvist", "Morgan", "Kestrel", "Northfork", "Alder", "Jordan", "Reyes",
                   "Bluebonnet", "Pecan Grove", "Lone Star", "Casey", "Moreau", "Ridgeline", "Buckeye", "Hocking"):
        assert needle not in flat, needle


def test_the_controls_resume(js):
    found = extract(js, RESUME_01)
    persona = found["persona"]
    assert persona["disciplines"] == ["controls", "systems"] and persona["level"] == "staff"
    assert persona["locations"] == {"metros": ["fort-collins-co"], "remote": True, "relocate": False}
    assert found["home"] == {"place": "Fort Collins, CO", "metros": ["fort-collins-co"]}
    assert [role["title"] for role in found["roles"]] == ["Staff Controls Engineer", "Senior Systems Engineer", "Controls Engineer"]


def test_years_come_from_every_role_that_names_a_skill(js):
    found = skills(extract(js, RESUME_01))
    assert found["Simulink"]["years"] == 10 and found["Simulink"]["from"] == ["2021 - present", "2017 - 2021"]
    # CAN: 2021 to now and 2014 to 2017, not joined across the gap.
    assert found["CAN"]["years"] == 9 and found["CAN"]["from"] == ["2021 - present", "2014 - 2017"]
    assert found["Python"]["years"] == 3 and found["Python"]["basis"] == "roles"


def test_a_skill_named_only_in_the_skills_list_borrows_years_from_a_related_skill_and_says_so(js):
    found = skills(extract(js, RESUME_01))
    assert found["Stateflow"]["basis"] == "related" and found["Stateflow"]["via"] == ["Simulink", "MATLAB"]
    assert found["Stateflow"]["years"] == found["Simulink"]["years"]
    assert found["Speedgoat"]["via"] == ["Hardware-in-the-loop testing"] and found["Speedgoat"]["years"] == 6
    assert found["Git"]["via"] == ["Python"] and found["Git"]["years"] == 3
    # Nothing related in a dated role: no years.
    tech = skills(extract(js, TECHNICIAN))
    assert tech["PLC programming"]["basis"] == "listed" and "years" not in tech["PLC programming"]


def test_years_written_beside_a_skill_are_taken_as_said(js):
    tech = skills(extract(js, TECHNICIAN))
    assert tech["Python"] == {**tech["Python"], "years": 2, "basis": "said"}
    text = RESUME_01.replace("Python, C, CAN", "Python (12 years), C, CAN")
    assert skills(extract(js, text))["Python"]["years"] == 12


def test_one_word_is_not_a_discipline(js):
    # A controls engineer who mentions an inverter once: no power-electronics credit from the body.
    one = "EXPERIENCE\nControls Engineer, Acme, Denver, CO   2019 - 2024\n- Tuned the controller for the plant's inverter.\n"
    assert "power-electronics" not in extract(js, one)["shortList"]
    two = one + "- Designed gate drive and magnetics for the converter.\n"
    assert "power-electronics" in extract(js, two)["shortList"]


HEADERS = {
    "title, company, place, dates": "Staff Controls Engineer, Acme Grid (fictional), Boulder, CO   2020 - present",
    "company dash title": "Acme Grid (fictional) — Staff Controls Engineer\nMar 2020 – Present",
    "title over company and dates": "Staff Controls Engineer\nAcme Grid (fictional) | 2020 - present",
    "company over title over dates": "Acme Grid (fictional)\nStaff Controls Engineer\n2020 - present",
    "title and dates over company": "Staff Controls Engineer   2020 - present\nAcme Grid (fictional), Boulder, CO",
    "dates over title and company": "2020 - present\nStaff Controls Engineer, Acme Grid (fictional)",
    "pipes": "Staff Controls Engineer | Acme Grid (fictional) | 2020 – Present",
}


@pytest.mark.parametrize("header", HEADERS.values(), ids=HEADERS.keys())
def test_role_headers_on_one_or_two_lines_in_either_order(js, header):
    text = ("EXPERIENCE\n\n" + header + "\n- Built the plant controller in Simulink.\n- Ran HIL regression.\n\n"
            "Controls Engineer, Other Co (fictional), Denver, CO   2015 - 2020\n- Wrote Python test tools.\n")
    found = extract(js, text)
    first = found["roles"][0]
    assert first["title"] == "Staff Controls Engineer"
    assert first["bullets"] == ["Built the plant controller in Simulink.", "Ran HIL regression."]
    assert "Acme Grid" in found["identity"]["employers"] and found["roles"][1]["title"] == "Controls Engineer"
    assert "Acme" not in json.dumps(found["persona"])


def test_the_home_metro_is_proposed_only_when_the_candidate_will_not_relocate(js):
    assert extract(js, TECHNICIAN)["persona"]["locations"]["metros"] == ["austin-tx"]   # Round Rock, TX 78664
    willing = extract(js, RESUME_01.replace("not looking to relocate", "happy to relocate"))
    assert willing["persona"]["locations"]["metros"] == [] and willing["home"] is None
    assert extract(js, SUPPLY_CHAIN)["persona"]["locations"] == {"metros": [], "remote": True, "relocate": True}
