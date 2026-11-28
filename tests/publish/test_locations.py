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


# --- Roles outside every metro area (the owner's metro review, 2026-11-28) ----------------------------

@pytest.mark.parametrize("locations,metros,expected", [
    ([{"text": "Munich", "country": "DE"}], [], "abroad"),
    ([{"text": "Munich", "country": "DE"}, {"text": "Toronto", "country": "CA"}], [], "abroad"),
    ([{"text": "Montrose, CO"}], [], "us"),                       # a rural plant: a state, no metro area
    ([{"text": "Greenville", "country": "US"}], [], "us"),          # in the US, city not placed yet
    ([{"text": "Munich", "country": "DE"}, {"text": "Greenville", "country": "US"}], [], "us"),   # not all abroad
    ([{"text": "Munich"}], [], "unclear"),                          # no country to go by
    ([], [], "unclear"),
    ([{"text": "Denver, CO"}], ["denver"], None),                   # in a metro area
])
def test_place_class(locations, metros, expected):
    from pipeline.publish.states import place_class
    assert place_class({"metros": metros, "locations": locations}) == expected


def test_elsewhere_in_a_state_is_a_state_none_of_the_roles_metro_areas_covers():
    from pipeline.publish.states import elsewhere_states, metro_states
    assert metro_states("New York-Newark-Jersey City, NY-NJ-PA") == ["NY", "NJ", "PA"] and metro_states("Somewhere") == []
    codes = {"denver": ["CO"], "nyc": ["NY", "NJ", "PA"]}
    job = lambda metros, *places: {"metros": metros, "locations": [{"text": p} for p in places]}
    assert elsewhere_states(job([], "Montrose, CO"), codes) == ["co"]
    assert elsewhere_states(job(["denver"], "Denver, CO", "Moses Lake, WA"), codes) == ["wa"]
    assert elsewhere_states(job(["nyc"], "Newark, NJ"), codes) == []          # NJ is in the New York metro area


def test_the_board_and_companies_carry_the_classes():
    reg = registry([company("alpha", "core", "in"), company("beta", "core", "in")])
    jobs = [job("plant", "alpha", locations=[{"text": "Montrose, CO", "state": "CO", "country": "US"}]),
            job("munich", "alpha", locations=[{"text": "Munich", "country": "DE"}], workplace="remote"),
            job("den", "beta", metros=["denver"], locations=[{"text": "Denver, CO"}, {"text": "Moses Lake, WA"}])]
    from pipeline.publish.build import build_all
    built = build_all(jobs_file(jobs), reg, TAXONOMY)
    roles = {role["id"]: role for role in built["board"]["roles"]}
    assert roles["plant"]["nm"] == "us" and roles["plant"]["es"] == ["co"]
    assert roles["munich"]["nm"] == "abroad" and "es" not in roles["munich"]
    assert "nm" not in roles["den"] and roles["den"]["es"] == ["wa"]
    companies = {c["id"]: c for c in built["companies"]["companies"]}
    # A remote role abroad is not "remote" (remote means in the US) but it is outside the US.
    assert companies["alpha"]["out"] == ["abroad", "us"] and "remote" not in companies["alpha"]
    assert companies["alpha"]["es"] == ["co"] and companies["beta"]["es"] == ["wa"] and "out" not in companies["beta"]


def test_the_board_page_offers_the_new_choices_and_their_tokens_round_trip():
    from tests.publish.test_page import SCRIPT
    assert "var away = role.nm === 'abroad' || !!HiPotRank.abroad(role);" in SCRIPT
    assert "if (role.wp === 'remote' && !away) places.push(REMOTE);" in SCRIPT
    assert "{ id: ABROAD, label: 'Outside the US', kind: 'top' }" in SCRIPT
    assert "label: 'Elsewhere in ' + entry.label, kind: 'else'" in SCRIPT
    # Last under its state, after the metro areas.
    prepare = SCRIPT[SCRIPT.index("function prepareLocations(facet)"):SCRIPT.index("// ---- Filter state in the URL fragment")]
    assert prepare.index("group.metros.forEach") < prepare.index("var rest = group.state ? byId[ELSE_PREFIX + group.state.id] : null;")
    # Address tokens: written and read back the same way.
    assert "if (id === ABROAD) return 'abroad';" in SCRIPT and "if (token === 'abroad') { next.m.add(ABROAD); return; }" in SCRIPT
    assert "if (id === UNCLEAR) return 'unclear';" in SCRIPT and "if (token === 'unclear') { next.m.add(UNCLEAR); return; }" in SCRIPT
    assert "if (id.indexOf(ELSE_PREFIX) === 0) return 'else-' + id.slice(ELSE_PREFIX.length);" in SCRIPT
    assert "else if (key === 'else') { if (/^[a-z]{2}$/.test(value) && facetByKey.m.byId[ELSE_PREFIX + value]) next.m.add(ELSE_PREFIX + value); }" in SCRIPT
    companies = (ROOT / "site" / "companies.html").read_text(encoding="utf-8")
    assert "value: 'e-' + group.state.id, text: 'Elsewhere in ' + group.state.label" in companies
    assert "{ value: 'abroad', text: 'Outside the US (' + outCount('abroad') + ')' }" in companies


# --- Metro areas grouped under their state (owner's request, 2026-11-28), run in V8 -------------------

METROS = [
    {"id": "nyc", "label": "New York-Newark-Jersey City, NY-NJ-PA"},
    {"id": "fort-collins-co", "label": "Fort Collins-Loveland, CO"},
    {"id": "denver", "label": "Denver-Aurora-Greeley, CO"},
    {"id": "albany", "label": "Albany-Schenectady-Troy, NY"},
    {"id": "guam", "label": "Hagatna, GU"},                      # a state code not in the list
    {"id": "nolabel", "label": "Somewhere"},                      # no codes at all
]
STATES = [{"id": "ny", "label": "New York"}, {"id": "co", "label": "Colorado"}, {"id": "ct", "label": "Connecticut"},
          {"id": "nj", "label": "New Jersey"}]


@pytest.fixture(scope="module")
def js():
    from pipeline.publish.pagejs import PageScripts
    with PageScripts("board-filters") as scripts:
        yield scripts


def test_metro_areas_are_grouped_under_their_state_a_to_z(js):
    groups = js.call("BoardFilters.metroGroups", METROS, STATES)
    heads = [group["state"]["label"] if group["state"] else None for group in groups]
    assert heads == ["Colorado", "Connecticut", "New Jersey", "New York", None]   # A to Z; unknown states last
    colorado = groups[0]["metros"]
    assert [m["name"] for m in colorado] == ["Denver-Aurora-Greeley", "Fort Collins-Loveland"]   # A to Z within
    assert groups[1]["metros"] == [] and groups[2]["metros"] == []   # a state with no metro area keeps its heading
    new_york = groups[3]["metros"]
    assert [m["id"] for m in new_york] == ["albany", "nyc"]
    assert new_york[1] == {"id": "nyc", "name": "New York-Newark-Jersey City", "also": ["NJ", "PA"]}
    # Listed once, under its first state only.
    every = [m["id"] for group in groups for m in group["metros"]]
    assert sorted(every) == sorted(m["id"] for m in METROS) and len(every) == len(set(every))
    assert {m["id"] for m in groups[4]["metros"]} == {"guam", "nolabel"}


def test_split_metro(js):
    assert js.call("BoardFilters.splitMetro", "Pittsburgh-Weirton-Steubenville, PA-OH-WV") == {
        "name": "Pittsburgh-Weirton-Steubenville", "codes": ["PA", "OH", "WV"]}
    assert js.call("BoardFilters.splitMetro", "Somewhere") == {"name": "Somewhere", "codes": []}


def test_both_pages_use_the_grouping_and_the_address_is_unchanged():
    from tests.publish.test_page import SCRIPT, STYLE
    prepare = SCRIPT[SCRIPT.index("function prepareLocations(facet)"):SCRIPT.index("// ---- Filter state in the URL fragment")]
    assert "BoardFilters.metroGroups(" in prepare and "head.members.push(option);" in prepare
    # Remote and "outside any metro" stay first; states head their metro areas, which are indented.
    assert "var ordered = facet.options.filter(function (o) { return o.kind === 'top'; });" in prepare
    assert ".loc-list .opt-metro { padding-left: 22px; }" in STYLE and "' also ' + option.also.join(', ')" in SCRIPT
    # Search keeps a state's heading above any of its metro areas that match.
    show = SCRIPT[SCRIPT.index("function showLocations(facet)"):SCRIPT.index("function syncControls()")]
    assert "if (!show && option.kind === 'state') show = option.members.some(visible);" in show
    # The address keeps the same tokens: m-<metro>, state-xx.
    assert "if (id.indexOf(STATE_PREFIX) === 0) return 'state-' + id.slice(STATE_PREFIX.length);" in SCRIPT
    companies = (ROOT / "site" / "companies.html").read_text(encoding="utf-8")
    assert "BoardFilters.metroGroups(data.labels.metros, data.labels.states).forEach(function (group) {" in companies
    assert "el('optgroup', { label: group.state ? group.state.label : 'Other metro areas' })" in companies
