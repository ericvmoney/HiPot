"""The scope decision: which roles are left out of jobs.json, and why."""
from __future__ import annotations

import pytest

from pipeline.tag.rules import classify


@pytest.mark.parametrize("title,reason", [
    ("Account Executive, Utilities", "sales"),
    ("Territory Sales Manager - Southwest", "sales"),
    ("Business Development Analyst, Energy Storage", "sales"),
    ("Senior Technical Recruiter", "recruiting"),
    ("Talent Acquisition Business Partner", "recruiting"),
    ("Senior Accountant", "finance-accounting"),
    ("FP&A Manager", "finance-accounting"),
    ("Plant Controller", "finance-accounting"),
    ("General Counsel", "legal"),
    ("Corporate Paralegal", "legal"),
    ("Senior Channel Marketing Manager", "marketing-communications"),
    ("Head of Communications", "marketing-communications"),
    ("Senior HR Business Partner", "people-hr"),
    ("Payroll Specialist", "people-hr"),
    ("Vice President of People", "people-hr"),
    ("Material Planner", "supply-chain"),
    ("Staff Global Supply Manager, Stamped Metals", "supply-chain"),
    ("Warehouse Associate", "supply-chain"),
    ("Network Administrator", "it"),
    ("Executive Assistant (C-Suite)", "admin"),
    ("General Application", "general-application"),
    ("Don't see the job you're looking for?", "general-application"),
    ("Technical Writer (6 Month Contract)", "documentation-training"),
    ("UX Product Designer", "design-ux"),
])
def test_out_of_scope_titles(title, reason):
    decision = classify(title)
    assert not decision.in_scope
    assert decision.reason == reason


@pytest.mark.parametrize("title", [
    "Senior Software Engineer, Backend",
    "Staff DevOps Engineer",
    "Data Scientist",
    "Machine Learning Engineer",
    "Site Reliability Engineer",
    "Full Stack Software Engineer, Growth",
])
def test_software_with_no_hardware_tie_is_left_out(title):
    decision = classify(title)
    assert not decision.in_scope and decision.reason == "software-no-hardware-tie"


@pytest.mark.parametrize("title,department,text", [
    ("Senior Software Engineer, Fleet Telemetry", None, None),
    ("Software Engineer - Site Controller, Energy Storage", None, None),
    ("Data Scientist, Battery Analytics", None, None),
    ("Staff Software Engineer, Factory Automation", None, None),
    ("Software Engineer", "Firmware and Controls", None),
    ("Software Engineer", None, "You will write telemetry ingestion for our device fleet, talk Modbus to inverters "
                                "and build test automation for the HIL rigs."),
])
def test_software_tied_to_hardware_is_kept(title, department, text):
    decision = classify(title, department, text)
    assert decision.in_scope and "software" in decision.disciplines


def test_supplier_engineering_is_kept_but_supplier_management_is_not():
    assert classify("Senior Supplier Quality Engineer").in_scope
    assert classify("Supplier Industrialization Engineer - Wire Harnessing").in_scope
    assert not classify("Specialist, Supplier Management").in_scope


def test_sales_and_solutions_engineers_are_kept_as_field_with_low_confidence():
    for title in ("Sales Engineer", "Senior Solutions Engineer"):
        decision = classify(title)
        assert decision.in_scope and decision.disciplines == ["field"] and decision.confidence == "low"


def test_an_engineer_whose_title_names_a_discipline_first_stays_in():
    decision = classify("Deployment Engineer (Logistics & Distribution)")
    assert decision.in_scope
    assert any(note.startswith("out-word-in-title") for note in decision.notes)


def test_out_of_scope_department_decides_an_unplaced_title():
    decision = classify("Specialist", department="Finance")
    assert not decision.in_scope and decision.reason == "finance-accounting"
    assert decision.evidence == "department"


def test_broad_title_in_a_non_hardware_department_is_left_out():
    decision = classify("Compliance Director", department="Legal & Policy")
    assert not decision.in_scope and "department-veto" in decision.notes
    # The same title in an engineering department stays.
    assert classify("Compliance Director", department="Hardware Engineering").in_scope


def test_unplaced_engineering_titles_are_counted_separately():
    decision = classify("Senior Engineer")
    assert not decision.in_scope and decision.reason == "unplaced-engineering-title"
    assert decision.confidence == "low"


def test_technicians_are_kept_unless_asked_otherwise():
    assert classify("Battery Lab Technician").in_scope
    assert classify("Journeyman Electrician (Austin)").in_scope
    dropped = classify("Battery Lab Technician", keep_technicians=False)
    assert not dropped.in_scope and dropped.reason == "technician"


def test_production_operators_are_left_out_and_marked_as_a_judgement():
    decision = classify("Production Associate (2nd Shift)")
    assert not decision.in_scope and decision.reason == "operator-production"
    assert decision.confidence == "medium"
