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
