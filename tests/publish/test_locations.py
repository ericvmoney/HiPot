"""Location data for the board: only used metros ship, and every US role carries its state."""
from __future__ import annotations

import pytest

from pipeline.io import ROOT, load_json, load_yaml
from pipeline.publish import build_board
from pipeline.publish.states import US_STATES, state_from_text, states_for
from tests.publish.test_publish import company, job, jobs_file, registry

TAXONOMY = load_yaml(ROOT / "taxonomy.yml")
JOBS = load_json(ROOT / "data" / "seed" / "jobs.json")
REGISTRY = load_yaml(ROOT / "companies.yml")


@pytest.mark.parametrize("text,expected", [
    ("Mountain View, CA", "CA"),
    ("Berthoud, Colorado", "CO"),
    ("San Jose, California, United States", "CA"),
    ("Denver, CO - US", "CO"),
    ("Palo Alto, California (hybrid)", "CA"),
    ("Washington, DC", "DC"),                 # the city part never counts as a state
    ("Colorado", "CO"),                       # a whole text that is a state name
    ("Remote - Texas", "TX"),
    ("Kansas City, MO", "MO"),
    ("Weirton, West Virginia", "WV"),
    ("US remote", None),
    ("Remote (remote)", None),
    ("Palo Alto", None),
    ("Boston or Remote", None),
    ("Bengaluru, in", None),                  # lower-case codes never match
    ("Toronto, ON", None),
    ("Washington", "WA"),
])
def test_state_from_text(text, expected):
    assert state_from_text(text) == expected


def test_states_for_prefers_the_structured_field_and_skips_other_countries():
    places = [
        {"text": "Weirton", "city": "Weirton", "state": "WV", "country": "US"},
        {"text": "Monterrey, Nuevo Leon", "country": "MX"},
        {"text": "Toronto, ON", "state": "ON", "country": "CA"},
        {"text": "Charlotte, NC"},
        {"text": "Weirton, WV"},
    ]
    assert states_for(places) == ["wv", "nc"]


def test_only_metros_used_by_roles_ship_with_their_taxonomy_labels():
    assert len(TAXONOMY["metros"]) > 200
    labels = {entry["id"]: entry["label"] for entry in TAXONOMY["metros"]}
    for include_unlisted in (False, True):
        board = build_board(JOBS, REGISTRY, TAXONOMY, include_unlisted=include_unlisted)
        used = {metro for role in board["roles"] for metro in role.get("metros", [])}
        shipped = board["taxonomy"]["metros"]
        assert {entry["id"] for entry in shipped} == used
        assert all(entry == {"id": entry["id"], "label": labels[entry["id"]]} for entry in shipped)
        order = [entry["id"] for entry in TAXONOMY["metros"] if entry["id"] in used]
        assert [entry["id"] for entry in shipped] == order


def test_a_role_outside_every_metro_is_still_found_by_state():
    reg = registry([company("alpha", "core", "in")])
    rural = job("a1", "alpha", locations=[{"text": "Weirton, WV", "city": "Weirton", "state": "WV", "country": "US"}])
    abroad = job("a2", "alpha", locations=[{"text": "Bengaluru", "country": "IN"}])
    board = build_board(jobs_file([rural, abroad]), reg, TAXONOMY)
    by_id = {role["id"]: role for role in board["roles"]}
    assert by_id["a1"]["st"] == ["wv"] and "metros" not in by_id["a1"]
    assert "st" not in by_id["a2"]
    assert board["taxonomy"]["states"] == [{"id": "wv", "label": "West Virginia"}]
    assert board["taxonomy"]["metros"] == []


def test_every_state_used_has_a_label_and_every_label_is_used():
    board = build_board(JOBS, REGISTRY, TAXONOMY, include_unlisted=True)
    used = {state for role in board["roles"] for state in role.get("st", [])}
    assert {entry["id"] for entry in board["taxonomy"]["states"]} == used
    assert all(entry["label"] == US_STATES[entry["id"].upper()] for entry in board["taxonomy"]["states"])
    # The seed has no structured state, so this exercises the text rule: nearly every role should get one.
    with_state = sum(1 for role in board["roles"] if role.get("st"))
    assert with_state > 0.85 * len(board["roles"])
