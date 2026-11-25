"""Government wage slice for the pay page: the right occupation and statistic, only what is needed, never in grades."""
from __future__ import annotations

from jsonschema import Draft202012Validator, FormatChecker

from pipeline.io import ROOT, load_json, load_yaml
from pipeline.publish import build_board, build_pay
from pipeline.publish.wages import occupation_and_statistic, page_wages
from tests.publish.test_pay_bands import paid
from tests.publish.test_publish import company, jobs_file, registry

TAXONOMY = load_yaml(ROOT / "taxonomy.yml")
REFERENCE = load_json(ROOT / "data" / "pay" / "bls-oews-2025.json")
PAY_SCHEMA = load_json(ROOT / "pipeline" / "publish" / "pay.schema.json")
REG = registry([company("alpha", "core", "in")])

FAKE = {
    "source": "BLS OEWS, May 2025",
    "occupations": {"17-2141": "Mechanical engineers", "11-9041": "Engineering managers", "17-3023": "Technicians",
                    "11-3051": "Production managers", "51-2028": "Assemblers"},
    "role_to_occupation": {"mechanical": "17-2141", "technician": "17-3023", "production": "51-2028"},
    "manager_occupation": {"engineering": "11-9041", "production": "11-3051"},
    "level_to_statistic": {"intern": None, "entry": "p25", "senior": "median", "staff": "p75", "manager": "median"},
    "metros": {"denver": {
        "17-2141": {"area": "Denver-Aurora-Centennial, CO", "employment": 4000, "year_p25": 90000, "year_median": 110000,
                    "year_p75": 135000, "year_p90": 160000, "hour_median": 52.9},
        "11-9041": {"area": "Denver-Aurora-Centennial, CO", "employment": 900, "year_median": None, "top_coded": ["year_median"]},
    }},
}


def test_occupation_and_statistic_rules():
    assert occupation_and_statistic(FAKE, "d-mechanical", "senior") == ("17-2141", "median")
    assert occupation_and_statistic(FAKE, "d-mechanical", "staff") == ("17-2141", "p75")
    assert occupation_and_statistic(FAKE, "d-mechanical", "manager") == ("11-9041", "median")   # engineering manager
    assert occupation_and_statistic(FAKE, "f-production", "manager") == ("11-3051", "median")
    assert occupation_and_statistic(FAKE, "f-technician", "manager") == ("17-3023", "median")   # no manager occupation
    assert occupation_and_statistic(FAKE, "d-mechanical", "intern") is None
    assert occupation_and_statistic(FAKE, "d-mechanical", "none") is None


def test_only_metro_figures_the_bands_need_are_shipped():
    bands = [{"per": "year", "g": "d-mechanical", "l": "senior", "m": "denver", "n": 3},
             {"per": "year", "g": "d-mechanical", "l": "senior", "m": "us", "n": 9},
             {"per": "year", "g": "d-mechanical", "l": "intern", "m": "denver", "n": 3}]
    out = page_wages(FAKE, bands, ("us", "remote"))
    assert out["year"] == 2025
    assert out["rules"] == {"d-mechanical|senior": ["17-2141", "median"]}
    assert out["figures"] == {"denver": {"17-2141": {"area": "Denver-Aurora-Centennial, CO", "year_median": 110000}}}
    assert out["occupations"] == {"17-2141": "Mechanical engineers"}


def test_top_coded_values_stay_null_and_flagged():
    bands = [{"per": "year", "g": "d-mechanical", "l": "manager", "m": "denver", "n": 3}]
    figure = page_wages(FAKE, bands, ("us", "remote"))["figures"]["denver"]["11-9041"]
    assert figure == {"area": "Denver-Aurora-Centennial, CO", "year_median": None, "top": ["year_median"]}


def test_real_reference_builds_a_valid_pay_file_and_never_touches_grades():
    jobs = [paid(f"a{n}", "alpha", 90000 + n * 5000, 130000 + n * 5000) for n in range(6)]
    pay = build_pay(jobs_file(jobs), REG, TAXONOMY, wages=REFERENCE)
    errors = [e.message for e in Draft202012Validator(PAY_SCHEMA, format_checker=FormatChecker()).iter_errors(pay)]
    assert errors == []
    figure = pay["gov"]["figures"]["denver"][pay["gov"]["rules"]["d-mechanical|senior"][0]]
    assert "year_median" in figure and figure["area"]
    assert "us" not in pay["gov"]["figures"] and "remote" not in pay["gov"]["figures"]
    # Grades come from posted ranges only: the board is the same with or without the reference.
    board = build_board(jobs_file(jobs), REG, TAXONOMY)
    assert [r.get("grade") for r in board["roles"]] == [r.get("grade") for r in build_board(jobs_file(jobs), REG, TAXONOMY)["roles"]]
    assert "wages" not in build_board.__code__.co_varnames


def test_pay_file_without_a_reference_has_no_gov_block():
    assert "gov" not in build_pay(jobs_file([paid("a1", "alpha", 90000, 110000)]), REG, TAXONOMY)
