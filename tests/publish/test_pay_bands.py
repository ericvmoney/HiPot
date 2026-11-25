"""Pay bands for the candidate pay page: only published pay, yearly and hourly apart, no figures below 3."""
from __future__ import annotations

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from pipeline.io import ROOT, load_json, load_yaml
from pipeline.publish import build_pay, dumps_pay
from pipeline.publish import pay as paybands
from tests.publish.test_publish import company, job, jobs_file, registry

TAXONOMY = load_yaml(ROOT / "taxonomy.yml")
JOBS = load_json(ROOT / "data" / "seed" / "jobs.json")
REGISTRY = load_yaml(ROOT / "companies.yml")
PAY_SCHEMA = load_json(ROOT / "pipeline" / "publish" / "pay.schema.json")


def paid(jid, cid, low, high, period="year", **extra):
    fields = {"pay": {"min": low, "max": high, "currency": "USD", "period": period, "basis": "feed"},
              "locations": [{"text": "Denver, CO", "city": "Denver", "state": "CO", "country": "US"}],
              "metros": ["denver"], "disciplines": ["mechanical"], "level": "senior"}
    fields.update(extra)
    return job(jid, cid, **fields)


def band(pay, period, group, level, market):
    found = [b for b in pay["bands"] if (b["per"], b["g"], b["l"], b["m"]) == (period, group, level, market)]
    assert len(found) <= 1
    return found[0] if found else None


def schema_errors(pay):
    validator = Draft202012Validator(PAY_SCHEMA, format_checker=FormatChecker())
    return [f"{list(e.absolute_path)}: {e.message[:160]}" for e in validator.iter_errors(pay)]


def test_band_is_the_median_low_high_and_midpoint_of_published_ranges():
    reg = registry([company("alpha", "core", "in")])
    jobs = [paid("a1", "alpha", 100000, 140000), paid("a2", "alpha", 120000, 160000), paid("a3", "alpha", 150000, 210000)]
    pay = build_pay(jobs_file(jobs), reg, TAXONOMY)
    for market in ("denver", "us"):
        assert band(pay, "year", "d-mechanical", "senior", market) == {
            "per": "year", "g": "d-mechanical", "l": "senior", "m": market, "n": 3,
            "lo": 120000, "hi": 160000, "mid": 140000,
        }
    assert band(pay, "year", "d-mechanical", "senior", "remote") is None
    assert schema_errors(pay) == []


def test_a_band_below_three_postings_shows_no_figures():
    reg = registry([company("alpha", "core", "in")])
    pay = build_pay(jobs_file([paid("a1", "alpha", 100000, 140000), paid("a2", "alpha", 120000, 160000)]), reg, TAXONOMY)
    found = band(pay, "year", "d-mechanical", "senior", "us")
    assert found == {"per": "year", "g": "d-mechanical", "l": "senior", "m": "us", "n": 2}
    assert schema_errors(pay) == []


def test_hourly_and_yearly_pay_never_mix():
    reg = registry([company("alpha", "core", "in")])
    jobs = [paid(f"y{n}", "alpha", 90000, 110000) for n in range(3)] + \
           [paid(f"h{n}", "alpha", 30, 40, period="hour") for n in range(3)]
    pay = build_pay(jobs_file(jobs), reg, TAXONOMY)
    yearly, hourly = band(pay, "year", "d-mechanical", "senior", "us"), band(pay, "hour", "d-mechanical", "senior", "us")
    assert (yearly["n"], yearly["lo"], yearly["hi"]) == (3, 90000, 110000)
    assert (hourly["n"], hourly["lo"], hourly["hi"]) == (3, 30, 40)
    assert pay["counts"] == {"postings": 6, "year": 3, "hour": 3, "left_out": 0}


def test_an_unlisted_companys_pay_never_enters_a_band():
    reg = registry([company("alpha", "core", "in"), company("beta", "out", "in")])
    jobs = [paid(f"a{n}", "alpha", 100000, 120000) for n in range(3)] + \
           [paid(f"b{n}", "beta", 400000, 500000) for n in range(5)]
    pay = build_pay(jobs_file(jobs), reg, TAXONOMY)
    found = band(pay, "year", "d-mechanical", "senior", "us")
    assert (found["n"], found["hi"]) == (3, 120000)
    assert "500000" not in dumps_pay(pay)
    # The development build includes them, as the board does.
    dev = build_pay(jobs_file(jobs), reg, TAXONOMY, include_unlisted=True)
    assert band(dev, "year", "d-mechanical", "senior", "us")["n"] == 8


def test_an_unlisted_functions_pay_never_enters_a_band(monkeypatch):
    reg = registry([company("alpha", "core", "in")])
    taxonomy = {**TAXONOMY, "functions": [{**f, "listed": f["id"] != "sales-bd"} for f in TAXONOMY["functions"]]}
    jobs = [paid(f"s{n}", "alpha", 100000, 120000, function="sales-bd", disciplines=[]) for n in range(3)]
    pay = build_pay(jobs_file(jobs), reg, taxonomy)
    assert pay["bands"] == [] and pay["counts"]["postings"] == 0


def test_role_group_level_and_market_rules():
    base = job("a1", "alpha", disciplines=["power-electronics", "electrical"])
    assert paybands.role_group(base) == "d-power-electronics"
    assert paybands.role_group({**base, "function": "science"}) == "d-power-electronics"
    assert paybands.role_group({**base, "function": "engineering", "disciplines": []}) == "f-engineering"
    assert paybands.role_group({**base, "function": "technician"}) == "f-technician"   # discipline ignored outside eng/science
    assert paybands.level_key(base) == "none"
    two_metros = {**base, "metros": ["denver", "boston"], "workplace": "remote"}
    assert paybands.markets(two_metros) == ["denver", "boston", "remote", "us"]
    abroad = {**base, "locations": [{"text": "Bengaluru", "country": "IN"}]}
    assert paybands.markets(abroad) == []
    unknown = {**base, "locations": [{"text": "Los Angeles"}]}
    assert paybands.markets(unknown) == ["us"]


@pytest.mark.parametrize("pay,usable", [
    ({"min": 100000, "max": 120000, "currency": "USD", "period": "year", "basis": "feed"}, True),
    ({"min": 0, "max": 120000, "currency": "USD", "period": "year", "basis": "feed"}, False),   # no published low end
    ({"min": 100000, "max": 120000, "currency": "CAD", "period": "year", "basis": "feed"}, False),
    (None, False),
])
def test_only_us_dollar_ranges_with_a_low_end_count(pay, usable):
    assert (paybands.usable_pay(job("a1", "alpha", pay=pay)) is not None) is usable


def test_seed_pay_file_matches_its_schema_and_is_stable():
    first = build_pay(JOBS, REGISTRY, TAXONOMY)
    assert schema_errors(first) == []
    assert dumps_pay(first) == dumps_pay(build_pay(JOBS, REGISTRY, TAXONOMY))
    assert all(("mid" in b) is (b["n"] >= 3) for b in first["bands"])
    labelled = {entry["id"] for entry in first["labels"]["markets"]}
    assert {b["m"] for b in first["bands"]} <= labelled
