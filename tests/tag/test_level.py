"""Level from the title: every level in taxonomy.yml, and null when none is stated."""
from __future__ import annotations

import json

import pytest

from pipeline.io import ROOT, load_yaml
from pipeline.seed.import_old_hub import level_from_title as seed_level
from pipeline.tag.level import level_from_title

LEVELS = {entry["id"] for entry in load_yaml(ROOT / "taxonomy.yml")["levels"]}

CASES = [
    # intern
    ("Mechanical Engineering Intern", "intern"),
    ("Summer 2027 Internship - Electrical Engineering", "intern"),
    ("Firmware Co-op (Fall 2027)", "intern"),
    ("Winter/Spring 2027 Optical Engineering Fellow", "intern"),
    # entry
    ("Junior Mechanical Engineer", "entry"),
    ("Associate Electrical Engineer", "entry"),
    ("Hardware Engineer I", "entry"),
    ("New Grad Hardware Engineer", "entry"),
    ("Mechanical Engineer (Early Career, Exceptional Talent)", "entry"),
    ("Apprentice Electrician", "entry"),
    # mid
    ("Controls Engineer II", "mid"),
    ("Mechanical Engineer 2", "mid"),
    ("Interconnection Engineer I/II", "mid"),
    # senior
    ("Senior Electrical Engineer", "senior"),
    ("Sr. Mechanical Engineer", "senior"),
    ("Electrical Engineer III", "senior"),
    # staff
    ("Staff Firmware Engineer", "staff"),
    ("Lead Manufacturing Engineer", "staff"),
    ("Mechanical Engineer IV", "staff"),
    ("Electrical Engineer - Level 4", "staff"),
    ("Senior/Staff Controls Engineer", "staff"),
    # principal
    ("Principal Battery Systems Engineer", "principal"),
    ("Chief Systems Architect", "principal"),
    ("Distinguished Engineer", "principal"),
    ("Technical Specialist, Motion Controls Architecture", "principal"),
    ("Senior/Principial Mechanical Engineer", "principal"),
    # manager
    ("Mechanical Engineering Manager", "manager"),
    ("Production Supervisor (2nd Shift)", "manager"),
    ("Group Product Manager", "manager"),
    ("General Site Superintendent", "manager"),
    # director
    ("Director, Electrical Engineering", "director"),
    ("Head of Systems Engineering", "director"),
    ("Head of Systems Engineering (Senior Director)", "director"),
    # executive
    ("VP, Sales", "executive"),
    ("Vice President, Electrical Engineering", "executive"),
    ("Chief Technology Officer", "executive"),
    ("CTO", "executive"),
]


@pytest.mark.parametrize("title,level", CASES)
def test_level(title, level):
    assert level_from_title(title) == level


def test_every_taxonomy_level_is_covered():
    assert {level for _, level in CASES} == LEVELS


@pytest.mark.parametrize("title", [
    "Mechanical Engineer",
    "Product Manager",                       # an individual contributor, not a people manager
    "Senior Product Manager, Hardware".replace("Senior ", ""),
    "Technical Program Manager",
    "I&C Engineer",                          # the I of I&C is not level one
    "V&V Engineer",
    "Model 3 Test Engineer",                 # a number that is not after a role noun
    "Member of Technical Staff, Power Electronics",
    "Chief of Staff",
    "Postdoctoral Fellow, Plasma Physics",
])
def test_no_level_stated(title):
    assert level_from_title(title) is None


def test_product_and_program_managers_take_the_level_their_title_states():
    assert level_from_title("Senior Product Manager") == "senior"
    assert level_from_title("Principal Technical Program Manager") == "principal"
    assert level_from_title("Senior Manager, Product Management") == "manager"


def test_agrees_with_the_seed_levels_except_where_extended():
    """The seed's levels came from the old hub's rule. The new rule may add a
    level the old one could not read, or move 'architecture' out of the
    principal band; it must not disagree anywhere else."""
    jobs = json.loads((ROOT / "data" / "seed" / "jobs.json").read_text(encoding="utf-8"))["jobs"]
    for job in jobs:
        title = job["title"]
        old, new = seed_level(title), level_from_title(title)
        if old == new or old is None:
            continue
        # The old rule read "architecture" as principal; a staff engineer
        # working on an architecture is staff. And it missed a misspelling.
        moved_architecture = "architecture" in title.lower() and old == "principal"
        assert moved_architecture or title == "Senior/Principial Mechanical Engineer", (title, old, new)
