"""Discipline and scope rules. Offline; titles only unless a case says otherwise."""
from __future__ import annotations

import pytest

from pipeline.io import ROOT, load_yaml
from pipeline.tag.rules import MAX_DISCIPLINES, RULES, classify

TAXONOMY_IDS = {entry["id"] for entry in load_yaml(ROOT / "taxonomy.yml")["disciplines"]}


def tags(title, department=None, text=None):
    decision = classify(title, department, text)
    assert decision.in_scope, f"{title!r} left out: {decision.reason}"
    return decision.disciplines


# One or more titles per discipline: (title, the discipline that must lead).
LEADS = [
    ("Senior Systems Engineer", "systems"),
    ("Requirements Engineer", "systems"),
    ("Staff Electrical Engineer, PCB Design", "electrical"),
    ("Senior Harness Design Engineer", "electrical"),
    ("Senior Power Electronics Engineer", "power-electronics"),
    ("Inverter Design Engineer", "power-electronics"),
    ("Staff Battery Cell Engineer", "battery"),
    ("BMS Engineer", "battery"),
    ("Power Systems Engineer", "power-systems"),
    ("Substation Protection and Control Engineer, EPC", "power-systems"),
    ("Senior Mechanical Design Engineer", "mechanical"),
    ("Stress Engineer", "mechanical"),
    ("Thermal Engineer", "thermal"),
    ("CFD Engineer", "thermal"),
    ("Staff Controls Engineer", "controls"),
    ("Senior Motor Controls Engineer", "controls"),
    ("Staff Firmware Engineer", "firmware"),
    ("Senior Embedded Software Engineer", "firmware"),
    ("Senior SCADA Engineer, Design (Remote)", "software"),
    ("Test Automation Engineer", "software"),
    ("Senior Test Engineer", "test"),
    ("Reliability Engineer", "test"),
    ("Mechanical Test Engineer, Avionics", "test"),
    ("Senior Manufacturing Engineer", "manufacturing"),
    ("NPI Manufacturing Engineer", "manufacturing"),
    ("Chemical Engineer", "chemical-process"),
    ("Process Engineer - Electrolyzer Scale-Up", "chemical-process"),
    ("Materials Scientist", "materials"),
    ("Senior Scientist, Electrochemistry", "materials"),
    ("Quality Engineer", "quality"),
    ("Supplier Quality Engineer", "quality"),
    ("Commissioning Engineer", "field"),
    ("Field Service Technician", "field"),
    ("Senior Product Manager, Hardware", "product"),
    ("Technical Program Manager, Battery", "program"),
    ("Project Engineer", "program"),
]


@pytest.mark.parametrize("title,lead", LEADS)
def test_title_names_the_lead_discipline(title, lead):
    assert tags(title)[0] == lead


@pytest.mark.parametrize("title,expected", [
    ("Electrical Systems Engineer", ["electrical", "systems"]),
    ("Senior Electrical Engineer - Inverter & Grid Integration", ["electrical", "power-electronics", "power-systems"]),
    ("Staff Engineer, BMS Embedded Software", ["firmware", "battery"]),
    ("Senior Thermo Mechanical Engineer", ["thermal", "mechanical"]),
    ("Mechanical Engineer, Plant Process Systems", ["mechanical", "chemical-process"]),
    ("Senior Mechatronics Engineer", ["mechanical", "electrical"]),
])
def test_title_with_several_disciplines(title, expected):
    assert tags(title) == expected


def test_general_words_do_not_reread_a_specific_phrase():
    # "power electronics" is not also "electronics" (electrical).
    assert tags("Senior Power Electronics Engineer") == ["power-electronics"]
    # "Control Systems Engineer" is controls, not systems.
    assert tags("Control Systems Engineer II") == ["controls"]
    # "Quality Control" is quality, not controls.
    assert tags("Quality Control Technician") == ["quality"]
    # "Project controls" is program work.
    assert tags("Project Controls Engineer - Cost & Planning") == ["program"]
    # "Fuel cell" is not battery.
    assert "battery" not in classify("Fuel Cell Engineer").disciplines


def test_mechanical_title_with_the_word_hardware_stays_mechanical():
    assert tags("Staff Mechanical Engineer, Hardware Engineering") == ["mechanical"]


def test_controls_at_a_factory_is_manufacturing():
    assert tags("Controls Engineer, Factory Automation") == ["controls", "manufacturing"]
    assert tags("Manufacturing Controls Engineer") == ["controls", "manufacturing"]
    assert tags("Senior Controls Engineer", department="Manufacturing Operations") == ["manufacturing", "controls"]
    factory_text = ("Program PLCs for our production lines, support conveyor and robot cells, "
                    "and work with equipment vendors and machine builders on factory automation.")
    assert tags("Controls Engineer", text=factory_text) == ["manufacturing", "controls"]


def test_controls_for_the_product_stays_controls():
    product_text = "Design control algorithms and plant models in Simulink for the thermal battery."
    assert tags("Controls Engineer", text=product_text) == ["controls"]
    assert tags("Senior Controls Engineer, Power Plant Controller (PPC)") == ["controls", "power-systems"]


def test_process_engineer_follows_its_context():
    assert tags("Senior Process Engineer, Welding") == ["manufacturing"]
    assert tags("Process Engineer", department="Manufacturing Operations") == ["manufacturing"]
    chemical_text = "Own the P&IDs and PFDs, run Aspen models and HAZOP reviews for the pilot plant reactors."
    assert tags("Process Engineer", text=chemical_text) == ["chemical-process"]
    unsure = classify("Process Engineer")
    assert unsure.in_scope and "process-engineer-default" in unsure.notes


def test_at_most_three_disciplines_and_all_from_the_taxonomy():
    titles = [title for title, _ in LEADS] + [
        "Senior Staff Power Electronics Control Firmware Engineer",
        "Battery Software & Controls Integration Engineer, Energy Storage",
        "Manager of Electrical, Instrumentation, and Controls Manufacturing",
    ]
    for title in titles:
        disciplines = classify(title).disciplines
        assert 1 <= len(disciplines) <= MAX_DISCIPLINES, title
        assert set(disciplines) <= TAXONOMY_IDS, title


def test_every_rule_names_only_taxonomy_ids():
    for _, disciplines, _, _ in RULES:
        assert all(d.startswith("?") or d in TAXONOMY_IDS for d in disciplines)


def test_department_decides_when_the_title_names_nothing():
    decision = classify("Senior Engineer", department="Engineering / Mechanical Design Engineering")
    assert decision.in_scope and decision.disciplines == ["mechanical"] and decision.evidence == "department"


def test_text_decides_last_and_is_marked_low_confidence():
    text = ("You will design schematics and PCBAs in Altium, review circuits, choose connectors and "
            "debug boards with oscilloscopes.")
    decision = classify("Engineering Technician", text=text)
    assert decision.in_scope and decision.disciplines[0] == "electrical"
    assert decision.evidence == "text" and decision.confidence == "low"


def test_title_wins_over_department_and_text():
    decision = classify("Senior Firmware Engineer", department="Mechanical Engineering",
                        text="SolidWorks, GD&T, sheet metal, machining drawings.")
    assert decision.disciplines == ["firmware"] and decision.evidence == "title"


def test_taxonomy_gaps_are_kept_but_marked():
    for title in ("Plasma Physicist", "Optical Engineer", "Reservoir Engineer", "Civil Engineer"):
        decision = classify(title)
        assert decision.in_scope and decision.confidence == "low", title
        assert any(note.startswith("taxonomy-gap") for note in decision.notes), title
