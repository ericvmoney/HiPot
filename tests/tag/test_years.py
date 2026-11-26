"""Years of experience asked, the level they suggest, and how it reaches the board."""
from __future__ import annotations

import copy
import json

import pytest
from jsonschema import Draft202012Validator

from pipeline.io import ROOT, load_json
from pipeline.publish.build import _role_record
from pipeline.tag.tagger import tag_job
from pipeline.tag.years import INFERRED_LEVELS, calibrate, experience_years, level_from_years

EXAMPLE = load_json(ROOT / "schema" / "examples" / "raw-jobs.example.json")["jobs"][0]


def years(text):
    found = experience_years(text)
    return found.years if found else None


@pytest.mark.parametrize("text,expected", [
    ("5+ years of experience in power electronics.", 5),
    ("3-5 years of experience in manufacturing.", 3),
    ("3 to 5 years of relevant experience.", 3),
    ("Minimum of 4 years in a manufacturing environment.", 4),
    ("At least three (3) years of hands-on experience.", 3),
    ("Experience: 7+ years designing switch-mode converters.", 7),
    ("0-2 years of professional experience.", 0),
    ("We are looking for someone with 5+ years of experience in firmware.", 5),
    ("Minimum 2 yrs experience with PLCs.", 2),
    ("Requires 6 years of progressive experience in procurement.", 6),
])
def test_figures_tied_to_experience(text, expected):
    assert years(text) == expected


@pytest.mark.parametrize("text", [
    "",
    "We have been building batteries for 20 years.",
    "A general contractor celebrating over 30 years of experience as design-build experts.",
    "Backed by over 23 years of experience in solar.",
    "With 25 years of trusted execution, we deliver reliable energy.",
    "Our inverters carry a 10-year warranty.",
    "The modules have a 25 years service life.",
    "Applicants must be 18 years of age or older.",
    "Applicants must be at least 21 years old.",
    "A 1-month paid sabbatical every 5 years.",
    "Reach full production within 2 years.",
    "Completed 4 years of college coursework.",
    "Founded 12 years ago in Boston.",
    "Over the next 5 years we will deploy 10 GW.",
])
def test_figures_not_about_experience_are_ignored(text):
    assert years(text) is None


def test_required_wins_over_preferred():
    assert years("5+ years of experience in firmware. Ideally 8+ years of experience.") == 5
    text = ("Requirements\n- 3+ years of experience in test engineering\n"
            "Preferred Qualifications\n- 10+ years of experience in battery validation")
    found = experience_years(text)
    assert found.years == 3 and not found.preferred_only


def test_preferred_figures_are_used_when_nothing_is_required():
    found = experience_years("Preferred: 4+ years of experience in thermal design.")
    assert found.years == 4 and found.preferred_only


def test_the_largest_required_minimum_counts():
    # The headline requirement, not a narrower secondary one.
    assert years("10+ years of fire protection engineering experience with at least 2 years of energy "
                 "infrastructure experience.") == 10
    assert years("5+ years of purchasing experience. 2+ years of experience leading teams.") == 5


def test_advanced_degree_alternatives_are_set_aside():
    text = ("Bachelor's in Chemical Engineering with 10+ years of R&D experience, or a Master's with 8+ years, "
            "or a PhD with 4+ years.")
    assert years(text) == 10


@pytest.mark.parametrize("value,level", [
    (0, "entry"), (1, "entry"), (2, "mid"), (3, "mid"), (4, "senior"), (6, "senior"),
    (7, "staff"), (10, "staff"), (11, "principal"), (20, "principal"),
])
def test_mapping(value, level):
    assert level_from_years(value) == level


def test_mapping_never_gives_manager_director_or_executive():
    assert {level_from_years(n) for n in range(0, 31)} == set(INFERRED_LEVELS)


def _raw(title, text, **changes):
    raw = copy.deepcopy(EXAMPLE)
    raw.update(title=title, description_text=text, **changes)
    return raw


def test_title_level_is_never_overridden():
    for title, stated in (("Senior Mechanical Engineer", "senior"), ("Engineering Manager", "manager"),
                          ("Director of Hardware", "director"), ("Staff Firmware Engineer", "staff")):
        job, record = tag_job(_raw(title, "1+ years of experience required."))
        assert job["level"] == stated and job["tagging"]["level_by"] == "rule", title
        assert job["experience_years"] == 1


def test_level_is_inferred_only_when_the_title_states_none():
    job, record = tag_job(_raw("Mechanical Engineer", "5+ years of experience in mechanical design."))
    assert job["level"] == "senior" and job["tagging"]["level_by"] == "years" and job["experience_years"] == 5
    assert record["level_by"] == "years"
    # No years stated: no level, and nothing is invented.
    job, _ = tag_job(_raw("Mechanical Engineer", "Design enclosures."))
    assert job["level"] is None and job["tagging"]["level_by"] == "rule" and "experience_years" not in job


def test_internships_are_never_levelled_from_years():
    job, _ = tag_job(_raw("Mechanical Engineering Intern", "1+ years of experience in CAD."))
    assert job["level"] == "intern" and job["tagging"]["level_by"] == "rule"
    job, _ = tag_job(_raw("Hardware Engineering", "2+ years of experience with test.", employment="intern"))
    assert job["level"] is None


def test_board_record_marks_inferred_levels():
    schema = json.loads((ROOT / "pipeline" / "publish" / "board.schema.json").read_text(encoding="utf-8"))
    # One role checked against the board's role schema, with the board's shared definitions.
    role_schema = {**schema["properties"]["roles"]["items"], "$defs": schema["$defs"]}
    validator = Draft202012Validator(role_schema)

    inferred, _ = tag_job(_raw("Mechanical Engineer", "5+ years of experience in mechanical design."))
    record = _role_record(inferred)
    assert record["level"] == "senior" and record["lvb"] == "years" and record["yrs"] == 5
    assert list(validator.iter_errors(record)) == []

    stated, _ = tag_job(_raw("Senior Mechanical Engineer", "3+ years of experience."))
    record = _role_record(stated)
    assert record["level"] == "senior" and "lvb" not in record and record["yrs"] == 3

    nothing, _ = tag_job(_raw("Mechanical Engineer", "Design enclosures."))
    record = _role_record(nothing)
    assert "level" not in record and "lvb" not in record and "yrs" not in record


def test_calibration_counts_agreement_with_title_levels():
    jobs = [_raw("Senior Mechanical Engineer", "5+ years of experience."),
            _raw("Staff Mechanical Engineer", "5+ years of experience."),
            _raw("Mechanical Engineer", "5+ years of experience.")]          # no title level: not counted
    result = calibrate(jobs)
    assert result["roles"] == 2 and result["exact"] == 1 and result["within_one"] == 2
