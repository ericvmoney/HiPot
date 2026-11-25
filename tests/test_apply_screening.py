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


from tools.apply_screening import parent_is_large  # noqa: E402


def test_parent_counts_only_when_large():
    assert parent_is_large("Volkswagen Group 682,724 (2024 average)")
    assert not parent_is_large("EQT AB 1,160 (2021, Wikipedia infobox)")
    assert not parent_is_large("not found; American Securities is a PE firm")
    assert not parent_is_large(None)
    nexamp = company(founded=2007, stage="late")
    fill_missing(nexamp, {"id": "x", "parent": "Mitsubishi Corporation", "parent_headcount": "63,037 consolidated"})
    assert startup_test(nexamp)[0] == "out"
    solv = company(founded=2008, stage="public", ipo_year=2026)
    fill_missing(solv, {"id": "x", "parent": "American Securities (private equity)", "parent_headcount": "not found"})
    assert solv["parent"] is None and startup_test(solv)[0] == "in"


def test_share_sales_by_public_companies_are_not_growth_funding():
    sale = {"date": "2026-09", "type": "at-the-market offering", "source": "s"}
    assert startup_test(company(founded=1992, stage="public", last_raise=sale))[0] == "out"
    private = {"date": "2023-06", "type": "growth equity (follow-on minority investment)", "source": "s"}
    assert startup_test(company(founded=2001, stage="late", last_raise=private))[0] == "in"


def test_founded_fifteen_years_ago_still_counts():
    assert startup_test(company(founded=2011, stage="public"))[0] == "in"
    assert startup_test(company(founded=2010, stage="public"))[0] == "out"


from tools.apply_screening import apply_probe  # noqa: E402


def test_probe_fills_careers_page_and_unknown_board_only():
    found = {"company_id": "x", "careers_url": "https://example.com/careers", "outcome": "ats-found",
             "ats": [{"type": "paylocity", "board": "abc", "readable": True}]}
    unknown = {"id": "x", "careers_url": None, "ats": {"type": "unknown", "board": None}, "read": "manual", "notes": None}
    apply_probe(unknown, found)
    assert unknown["ats"] == {"type": "paylocity", "board": "abc"} and unknown["read"] == "auto"
    assert unknown["careers_url"] == "https://example.com/careers"
    again = copy.deepcopy(unknown)
    apply_probe(again, found)
    assert again == unknown
    known = {"id": "x", "careers_url": None, "ats": {"type": "greenhouse", "board": "x"}, "read": "auto", "notes": None}
    apply_probe(known, found)
    assert known["ats"] == {"type": "greenhouse", "board": "x"}       # a known board is never replaced


from tools.apply_screening import listing_year  # noqa: E402


def test_listing_year_from_the_scouts_wording():
    assert listing_year("97 employees; listed via SPAC in 2022, under five years.") == 2022
    assert listing_year("listed 2022 or 2023 (sources differ)") == 2022     # the stricter reading
    assert listing_year("Large public company.") is None
    assert listing_year("founded 2011; raised a Series B in 2024") is None  # a raise is not a listing
