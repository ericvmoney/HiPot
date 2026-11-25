"""New roles (decision 15): first seen in the last 3 business days, Mountain time, never a company's first read."""
from __future__ import annotations

from datetime import date

import pytest

from pipeline.io import ROOT, load_yaml
from pipeline.publish import build_board
from pipeline.publish.fresh import mountain_date, new_role_ids, window_start
from tests.publish.test_publish import company, job, jobs_file, registry

TAXONOMY = load_yaml(ROOT / "taxonomy.yml")


@pytest.mark.parametrize("generated_at,start", [
    ("2026-11-24T18:00:00-07:00", date(2026, 11, 20)),   # Tuesday: Fri, Mon, Tue
    ("2026-11-25T01:56:14Z", date(2026, 11, 20)),        # Tuesday evening in Denver, already Wednesday in UTC
    ("2026-11-28T10:00:00-07:00", date(2026, 11, 25)),   # Saturday: Wed, Thu, Fri
    ("2026-11-23T08:00:00-07:00", date(2026, 11, 19)),   # Monday: Thu, Fri, Mon
    ("2026-11-26T08:00:00-07:00", date(2026, 11, 24)),   # Thursday (US holiday, no calendar): Tue, Wed, Thu
])
def test_window_start_counts_three_weekdays_in_mountain_time(generated_at, start):
    assert window_start(generated_at) == start


def test_mountain_date_follows_daylight_saving():
    assert mountain_date("2026-07-01T05:30:00Z") == date(2026, 6, 30)    # MDT, UTC-6
    assert mountain_date("2026-12-01T06:30:00Z") == date(2026, 11, 30)   # MST, UTC-7


def seen(jid, cid, stamp):
    return job(jid, cid, first_seen=stamp, last_seen="2026-11-24T18:00:00-07:00")


GENERATED = "2026-11-24T18:00:00-07:00"


def test_a_companys_first_read_is_never_new():
    jobs = [seen("a1", "alpha", "2026-11-23T09:00:00-07:00"), seen("a2", "alpha", "2026-11-23T12:00:00-07:00")]
    assert new_role_ids(jobs, GENERATED) == set()           # both within 6 hours of alpha's first read


def test_a_role_posted_after_the_first_read_is_new_inside_the_window():
    jobs = [seen("a1", "alpha", "2026-11-10T09:00:00-07:00"),
            seen("a2", "alpha", "2026-11-20T09:00:00-07:00"),   # Friday: inside
            seen("a3", "alpha", "2026-11-19T09:00:00-07:00"),   # Thursday: outside
            seen("a4", "alpha", "2026-11-24T17:00:00-07:00")]   # today
    assert new_role_ids(jobs, GENERATED) == {"a2", "a4"}


def test_seed_primed_roles_are_never_new_and_set_no_baseline():
    # The old hub knew one Antora role on the 12th; the collector first read the whole board on the 24th.
    jobs = [seen("old", "antora", "2026-11-12T14:00:00-07:00"),
            seen("b1", "antora", "2026-11-24T11:15:00-07:00"), seen("b2", "antora", "2026-11-24T11:16:00-07:00"),
            seen("later", "antora", "2026-11-24T18:45:00-07:00")]
    assert new_role_ids(jobs, "2026-11-24T19:00:00-07:00", seed_ids={"old"}) == {"later"}
    # Without the seed ids, the whole first read would look new.
    assert new_role_ids(jobs, "2026-11-24T19:00:00-07:00") == {"b1", "b2", "later"}


def test_the_board_flags_and_counts_new_roles():
    reg = registry([company("alpha", "core", "in")])
    jobs = [seen("a1", "alpha", "2026-11-10T09:00:00-07:00"), seen("a2", "alpha", "2026-11-23T09:00:00-07:00")]
    board = build_board({**jobs_file(jobs), "generated_at": GENERATED}, reg, TAXONOMY)
    roles = {role["id"]: role for role in board["roles"]}
    assert roles["a2"].get("new") is True and "new" not in roles["a1"]
    assert board["counts"]["new"] == 1 and board["counts"]["new_since"] == "2026-11-20"
    assert board["taxonomy"]["fresh"] == [{"id": "new", "label": "New in the last 3 business days"}]


# --- First read from the collector's run history (data/state/runs.json) -----------------

def runs(*spans):
    """runs(("2026-11-23T09:00:00-07:00", "2026-11-23T09:40:00-07:00", ["alpha"]), ...)"""
    return {"state_version": 0, "runs": [{"started_at": s, "finished_at": f, "read": sorted(read), "partial": []}
                                         for s, f, read in spans]}


def test_history_sets_the_first_read_even_after_its_roles_have_closed():
    # Alpha was first read on the 17th; every role from that read has closed. A role first seen on the 23rd
    # is new with the history, but inference would treat it as the first read.
    history = runs(("2026-11-17T09:00:00-07:00", "2026-11-17T09:30:00-07:00", ["alpha"]),
                   ("2026-11-23T09:00:00-07:00", "2026-11-23T09:30:00-07:00", ["alpha"]))
    jobs = [seen("a1", "alpha", "2026-11-23T09:10:00-07:00")]
    assert new_role_ids(jobs, GENERATED, runs=history) == {"a1"}
    assert new_role_ids(jobs, GENERATED) == set()


def test_history_first_read_ends_at_the_runs_finish():
    # A new company read for the first time on the 24th: what that run found is not new, however long it took.
    history = runs(("2026-11-24T08:00:00-07:00", "2026-11-24T16:00:00-07:00", ["beta"]))
    jobs = [seen("b1", "beta", "2026-11-24T08:05:00-07:00"), seen("b2", "beta", "2026-11-24T15:55:00-07:00"),
            seen("b3", "beta", "2026-11-24T17:30:00-07:00")]
    assert new_role_ids(jobs, GENERATED, runs=history) == {"b3"}


def test_a_company_read_before_the_history_began_keeps_its_inferred_first_read():
    # Gamma was collected on the 10th, before runs.json existed; history starts on the 23rd.
    history = runs(("2026-11-23T09:00:00-07:00", "2026-11-23T09:30:00-07:00", ["gamma"]))
    jobs = [seen("g1", "gamma", "2026-11-10T09:00:00-07:00"), seen("g2", "gamma", "2026-11-23T09:10:00-07:00")]
    assert new_role_ids(jobs, GENERATED, runs=history) == {"g2"}


def test_companies_missing_from_the_history_fall_back_to_inference():
    history = runs(("2026-11-17T09:00:00-07:00", "2026-11-17T09:30:00-07:00", ["alpha"]))
    jobs = [seen("d1", "delta", "2026-11-23T09:00:00-07:00"), seen("d2", "delta", "2026-11-23T12:00:00-07:00"),
            seen("d3", "delta", "2026-11-24T10:00:00-07:00")]
    assert new_role_ids(jobs, GENERATED, runs=history) == {"d3"}


def test_seed_rule_still_applies_with_history():
    history = runs(("2026-11-24T11:00:00-07:00", "2026-11-24T11:30:00-07:00", ["antora"]))
    jobs = [seen("old", "antora", "2026-11-20T14:00:00-07:00"), seen("b1", "antora", "2026-11-24T11:15:00-07:00"),
            seen("later", "antora", "2026-11-24T17:45:00-07:00")]
    assert new_role_ids(jobs, GENERATED, runs=history, seed_ids={"old"}) == {"later"}


def test_the_command_reads_the_run_history(tmp_path, capsys):
    import json
    from pipeline.publish.__main__ import main
    history = tmp_path / "runs.json"
    history.write_text(json.dumps(runs(("2026-11-24T08:00:00-07:00", "2026-11-24T09:00:00-07:00", ["also"]))), encoding="utf-8")
    seed = str(ROOT / "data" / "seed" / "jobs.json")
    assert main(["--jobs", seed, "--out", str(tmp_path / "board.json"), "--runs", str(history)]) == 0
    assert "run history: 1 runs" in capsys.readouterr().out
    assert main(["--jobs", seed, "--out", str(tmp_path / "board.json"), "--runs", str(tmp_path / "none.json")]) == 0
    assert "no run history, first reads inferred" in capsys.readouterr().out
