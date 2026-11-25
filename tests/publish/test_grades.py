"""Pay-vs-market grades: a role's published midpoint against comparable published ranges."""
from __future__ import annotations

from pipeline.io import ROOT, load_json, load_yaml
from pipeline.publish import build_board
from pipeline.publish.__main__ import main
from pipeline.publish.grades import grades
from tests.publish.test_pay_bands import paid
from tests.publish.test_publish import company, job, jobs_file, registry

TAXONOMY = load_yaml(ROOT / "taxonomy.yml")
REG = registry([company("alpha", "core", "in"), company("beta", "out", "in")])


def roles_with_mids(mids, prefix="a", **extra):
    """Senior mechanical roles in Denver whose midpoints are the given figures (range ±10,000)."""
    return [paid(f"{prefix}{n}", "alpha", mid - 10000, mid + 10000, **extra) for n, mid in enumerate(mids)]


def graded(jobs):
    board = build_board(jobs_file(jobs), REG, TAXONOMY)
    return {role["id"]: role.get("grade") for role in board["roles"]}


def test_above_at_and_below_against_the_median_of_the_others():
    jobs = roles_with_mids([100000] * 5) + [paid("hi", "alpha", 105000, 125000),   # mid 115,000: 15% above
                                            paid("eq", "alpha", 100000, 120000),   # mid 110,000: 10% above, still "at"
                                            paid("lo", "alpha", 75000, 95000)]     # mid 85,000: 15% below
    found = graded(jobs)
    # Each graded role is compared with the 7 others; their median midpoint is 100,000 in every case here.
    assert found["hi"] == {"v": "above", "g": "d-mechanical", "m": "denver", "n": 7, "med": 100000, "pct": 15}
    assert found["eq"]["v"] == "at" and found["eq"]["pct"] == 10
    assert found["lo"] == {"v": "below", "g": "d-mechanical", "m": "denver", "n": 7, "med": 100000, "pct": -15}
    assert found["a0"]["v"] == "at"


def test_falls_back_to_all_us_when_the_market_is_thin():
    boston = {"metros": ["boston"], "locations": [{"text": "Boston, MA", "state": "MA", "country": "US"}]}
    jobs = roles_with_mids([100000] * 3) + roles_with_mids([100000] * 3, prefix="b", **boston)
    found = graded(jobs)
    # Denver has 2 others, so the comparison uses the same group and level across all US: 5 others.
    assert found["a0"]["m"] == "us" and found["a0"]["n"] == 5


def test_no_grade_with_fewer_than_five_comparable_postings():
    # Five roles: each has only four others to compare with, so none is graded. Six: five others each.
    assert all(grade is None for grade in graded(roles_with_mids([100000] * 5)).values())
    assert all(grade is not None for grade in graded(roles_with_mids([100000] * 6)).values())


def test_yearly_and_hourly_never_compare_with_each_other():
    jobs = roles_with_mids([100000] * 5) + [paid("h", "alpha", 30, 40, period="hour")]
    assert graded(jobs)["h"] is None


def test_other_levels_and_groups_are_not_comparable():
    jobs = roles_with_mids([100000] * 5) + [paid("staff", "alpha", 190000, 210000, level="staff"),
                                            paid("elec", "alpha", 190000, 210000, disciplines=["electrical"])]
    found = graded(jobs)
    assert found["staff"] is None and found["elec"] is None


def test_unlisted_companies_never_move_a_grade():
    jobs = roles_with_mids([100000] * 6) + [paid(f"z{n}", "beta", 400000, 500000) for n in range(10)]
    found = graded(jobs)
    assert found["a0"]["n"] == 5 and found["a0"]["med"] == 100000
    assert not any(key.startswith("z") for key in found)


def test_roles_without_usable_pay_get_no_grade():
    jobs = roles_with_mids([100000] * 6) + [job("nopay", "alpha"), paid("cad", "alpha", 90000, 110000)]
    jobs[-1]["pay"]["currency"] = "CAD"
    found = graded(jobs)
    assert found["nopay"] is None and found["cad"] is None


def test_grades_can_be_switched_off():
    board = build_board(jobs_file(roles_with_mids([100000] * 6)), REG, TAXONOMY, grades=False)
    assert board["grades"] is False
    assert "grades" not in board["taxonomy"]
    assert not any("grade" in role for role in board["roles"])
    on = build_board(jobs_file(roles_with_mids([100000] * 6)), REG, TAXONOMY)
    assert on["grades"] is True and [g["id"] for g in on["taxonomy"]["grades"]] == ["above", "at", "below"]


def test_command_line_flag(tmp_path, capsys):
    seed = str(ROOT / "data" / "seed" / "jobs.json")
    out = tmp_path / "board.json"
    assert main(["--jobs", seed, "--out", str(out)]) == 0
    assert load_json(out)["grades"] is True and "pay grades:" in capsys.readouterr().out
    assert main(["--jobs", seed, "--out", str(out), "--no-grades"]) == 0
    assert load_json(out)["grades"] is False and "pay grades: off" in capsys.readouterr().out


def test_grades_function_matches_the_board():
    jobs = roles_with_mids([90000, 95000, 100000, 105000, 110000, 140000])
    direct = grades(jobs)
    assert direct["a5"]["v"] == "above" and direct["a5"]["med"] == 100000
