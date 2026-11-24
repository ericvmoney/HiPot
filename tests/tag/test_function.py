"""Function: every role gets exactly one, from the title, then the department, then the text."""
from __future__ import annotations

import pytest

from pipeline.io import ROOT, load_yaml
from pipeline.tag.function import DEPARTMENT_RULES, TITLE_RULES
from pipeline.tag.rules import classify

FUNCTIONS = {entry["id"] for entry in load_yaml(ROOT / "taxonomy.yml")["functions"]}


def function(title, department=None, text=None):
    return classify(title, department, text).function


@pytest.mark.parametrize("title,expected", [
    # engineering
    ("Senior Mechanical Engineer", "engineering"),
    ("Staff Firmware Engineer", "engineering"),
    ("Senior Software Engineer, Backend", "engineering"),
    ("Senior Data Scientist", "engineering"),
    ("Supplier Quality Engineer", "engineering"),
    ("Sales Engineer", "engineering"),
    ("Director of Mechanical Engineering", "engineering"),
    ("Director, Power Conversion & Energy Storage", "engineering"),
    ("Deployment Engineer (Field Operations)", "engineering"),
    ("Controls Engineer - Warehouse Automation", "engineering"),
    # science
    ("Senior Materials Scientist, R&D", "science"),
    ("Laser Physicist", "science"),
    ("Summer 2027 Internship - Physics", "science"),
    # technician
    ("Battery Lab Technician", "technician"),
    ("Field Service Technician", "technician"),
    ("Engineering Technician, Prototype Shop", "technician"),
    # trades
    ("Journeyman Electrician (Austin)", "trades"),
    ("CNC Machinist", "trades"),
    ("Welder/Fitter", "trades"),
    ("Flight Test Maintenance (A&P)", "trades"),
    # production
    ("Production Associate (2nd Shift)", "production"),
    ("Production Supervisor", "production"),
    ("Assembler", "production"),
    ("Facilities Maintenance Supervisor - Night Shift", "production"),
    # supply chain
    ("Material Planner", "supply-chain"),
    ("Staff Global Supply Manager, Stamped Metals", "supply-chain"),
    ("Warehouse Associate", "supply-chain"),
    ("Last Mile Delivery Driver (Dallas-Fort Worth)", "supply-chain"),
    # quality and compliance
    ("Quality Manager", "quality-compliance"),
    ("Senior Field Quality Inspector", "quality-compliance"),
    ("Document Control Specialist", "quality-compliance"),
    ("Director, Licensing & Regulatory Affairs", "quality-compliance"),
    # ehs
    ("Senior Industrial Hygienist", "ehs"),
    ("Staff EHS Engineer", "ehs"),
    # projects and programs
    ("Technical Program Manager, Battery", "project-program"),
    ("Senior Construction Project Manager", "project-program"),
    ("Project Engineer", "project-program"),
    ("Senior Staff Scheduler", "project-program"),
    ("General Site Superintendent", "project-program"),
    # field and asset operations
    ("Field Service Manager", "field-operations"),
    ("Deployment Operations Associate", "field-operations"),
    ("Senior Manager, Commissioning", "field-operations"),
    # product and design
    ("Senior Product Manager, Hardware", "product"),
    ("UX Product Designer", "product"),
    # sales and business development
    ("Account Executive, Utilities", "sales-bd"),
    ("Territory Sales Manager - Southwest", "sales-bd"),
    ("Member Experience Associate", "sales-bd"),
    # marketing
    ("Senior Channel Marketing Manager", "marketing"),
    ("Director of Grid Policy", "marketing"),
    ("Animator/Motion Designer", "marketing"),
    # finance, legal and strategy
    ("Senior Accountant", "finance-legal"),
    ("General Counsel", "finance-legal"),
    ("Well Permitting Specialist", "finance-legal"),
    ("Corporate Development Director", "finance-legal"),
    # people and administration
    ("Senior Technical Recruiter", "people-admin"),
    ("Senior HR Business Partner", "people-admin"),
    ("Executive Assistant (C-Suite)", "people-admin"),
    # it
    ("Network Administrator", "it"),
    ("NetSuite Administrator", "it"),
    ("Salesforce Developer", "it"),
])
def test_function_from_the_title(title, expected):
    assert function(title) == expected


def test_role_noun_is_read_from_the_head_of_the_title_first():
    assert function("Senior Software Engineer, Frontend (Digital Products - Technician Hub)") == "engineering"
    assert function("Senior Machinist / R&D Specialist") == "trades"


def test_engineer_whose_title_names_a_field_first_is_not_moved_to_a_corporate_function():
    assert function("Senior Software Engineer, Backend (Sales)") == "engineering"
    assert function("Deployment Engineer (Logistics & Distribution)") == "engineering"


@pytest.mark.parametrize("title,department,expected", [
    ("Specialist, Press Shop", "Production", "production"),
    ("Operations Manager (Connecticut)", "Deployments (Operations & Engineering) / Deployment Operations",
     "field-operations"),
    ("Specialist", "Finance", "finance-legal"),
    ("Specialist", "Operations / People / HR", "people-admin"),
    ("Intern, Design", "Design", "product"),
    ("Electrical Supervisor", "Electrical Installers", "trades"),
])
def test_function_from_the_department(title, department, expected):
    decision = classify(title, department)
    assert decision.function == expected
    assert decision.function_evidence in ("department", "title")


def test_software_in_a_corporate_it_department_is_it():
    decision = classify("Senior DevOps Engineer", department="Information Technology")
    assert decision.function == "it" and "it-department" in decision.notes
    # The same title on a product team is engineering.
    assert function("Senior DevOps Engineer", department="Software Engineering") == "engineering"


def test_text_decides_last_and_default_is_marked():
    text = "Requirements: a bachelor's degree in mechanical or electrical engineering and five years of experience."
    decision = classify("Associate II", text=text)
    assert decision.function == "engineering" and decision.function_evidence == "text"
    assert decision.function_confidence == "low"
    unknown = classify("Associate II")
    assert unknown.function_evidence == "default" and "function-default" in unknown.notes


def test_general_applications_are_kept_and_marked():
    decision = classify("General Application")
    assert decision.function == "people-admin" and "general-application" in decision.notes


def test_every_rule_names_a_taxonomy_function():
    assert {rule.function for rule in TITLE_RULES} <= FUNCTIONS
    assert {function for function, _ in DEPARTMENT_RULES} <= FUNCTIONS


def test_every_listed_function_is_reachable_from_a_title_rule():
    listed = {entry["id"] for entry in load_yaml(ROOT / "taxonomy.yml")["functions"] if entry.get("listed")}
    assert listed <= {rule.function for rule in TITLE_RULES}
