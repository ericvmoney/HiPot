"""tools/apply_screening.py: rulings and fixes must be safe to apply again."""
from __future__ import annotations

import copy

from tools.apply_screening import STARTUP_IN_BY_RULE, fill_missing, rule_reason


def test_rule_reason_is_not_appended_twice():
    once = rule_reason("No headcount found; founded 2021.", "no figure")
    assert once.endswith(STARTUP_IN_BY_RULE["no figure"])
    assert rule_reason(once, "no figure") == once


def test_rule_reason_drops_the_scouts_placeholder():
    reason = rule_reason("132 people (Dealroom); founded 2013. Older than 10 years: owner to decide.", "age")
    assert "owner to decide" not in reason and reason.endswith(STARTUP_IN_BY_RULE["age"])


def test_fill_missing_never_overwrites_and_is_repeatable():
    company = {"id": "x", "hq": "Boulder, CO", "founded": None, "stage": None, "headcount": None, "notes": None}
    fix = {"id": "x", "hq": {"value": "Denver, CO"}, "founded": {"value": 2019}, "stage": {"value": "seed"},
           "headcount": {"value": 40, "as_of": "undated", "source": "Example profile"}}
    fill_missing(company, fix)
    assert company["hq"] == "Boulder, CO"                 # existing value kept
    assert company["founded"] == 2019 and company["stage"] == "seed"
    assert company["headcount"]["value"] == 40 and len(company["headcount"]["as_of"]) == 10
    again = copy.deepcopy(company)
    fill_missing(again, fix)
    assert again == company


from tools.apply_screening import startup_test  # noqa: E402


def company(**fields):
    base = {"id": "x", "stage": "series-b", "founded": 2020, "headcount": None, "parent": None,
            "last_raise": None, "ipo_year": None}
    base.update(fields)
    return base


def test_startup_test_cap_and_tolerance():
    assert startup_test(company(headcount={"value": 3900, "as_of": "2026-01-01", "source": "s"}))[0] == "in"
    assert startup_test(company(headcount={"value": 4800, "as_of": "2026-01-01", "source": "s"}))[0] == "in"
    assert startup_test(company(headcount={"value": 5200, "as_of": "2026-01-01", "source": "s"}))[0] == "out"


def test_startup_test_independence():
    assert startup_test(company(parent="Alphabet"))[0] == "out"
    # A subsidiary label without a known owner does not exclude on its own.
    assert startup_test(company(stage="subsidiary"))[0] == "in"


def test_startup_test_growth_signs():
    assert startup_test(company(founded=2015))[0] == "in"                         # founded within 15 years
    old = dict(founded=1990, stage="public")
    assert startup_test(company(**old))[0] == "out"
    assert startup_test(company(**old, ipo_year=2024))[0] == "in"                  # public under 5 years
    assert startup_test(company(**old, last_raise={"date": "2025-03", "type": "Series F", "source": "s"}))[0] == "in"
    assert startup_test(company(founded=1990, stage="late"))[0] == "in"            # venture-backed, round unchecked
    assert startup_test(company(founded=1990, stage=None))[0] == "out"
    assert startup_test(company(founded=None))[0] == "in"
