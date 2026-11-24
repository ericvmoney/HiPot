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
