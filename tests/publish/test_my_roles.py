"""My Roles and great matches (decision 18). The pure blocks of site/index.html (`<script id="my-roles">`
and HiPotRank.great in `<script id="hipot-rank">`) run in V8; the rest are checks on the page's source.
All data here is synthetic."""
from __future__ import annotations

import re

import pytest

from pipeline.publish.pagejs import PageScripts, script_block
from tests.publish.test_page import PAGE, SCRIPT, STYLE

TODAY = "2026-11-25"


def role(rid, title="Controls Engineer", **fields):
    base = {"id": rid, "title": title, "url": "https://jobs.example.com/" + rid,
            "pay": {"min": 150000, "max": 190000, "cur": "USD", "per": "year"}}
    base.update(fields)
    return base


@pytest.fixture(scope="module")
def js():
    with PageScripts("hipot-rank", "my-roles") as scripts:
        yield scripts


def snap(js, rid, title="Controls Engineer"):
    return js.call("MyRoles.snapshot", role(rid, title), "Example Co", "Denver, CO · Hybrid", TODAY)


def add(js, entries, rid, status="applied", on=TODAY, title="Controls Engineer"):
    return js.call("MyRoles.add", entries, snap(js, rid, title), status, on)


# --- The pure block ----------------------------------------------------------------------------------

def test_adding_a_role_keeps_a_snapshot_its_status_history_and_applied_date(js):
    entries = add(js, [], "a")
    assert entries == [{
        "id": "a", "title": "Controls Engineer", "company": "Example Co", "place": "Denver, CO · Hybrid",
        "pay": {"min": 150000, "max": 190000, "cur": "USD", "per": "year"}, "url": "https://jobs.example.com/a",
        "status": "applied", "history": [{"status": "applied", "on": TODAY}], "applied_on": TODAY,
        "notes": "", "added_on": TODAY, "last_listed": TODAY,
    }]
    saved = add(js, [], "b", "saved")
    assert saved[0]["applied_on"] is None and saved[0]["status"] == "saved"


def test_statuses_are_the_nine_in_order(js):
    labels = [s["label"] for s in js.eval("MyRoles.STATUSES")]
    assert labels == ["Saved", "Applied", "Recruiter screen", "Interviewing", "Offer", "Accepted", "Rejected", "Withdrawn", "No response"]


def test_a_status_change_is_dated_and_sets_the_applied_date_once(js):
    entries = add(js, [], "a", "saved", "2026-11-20")
    entries = js.call("MyRoles.setStatus", entries, "a", "applied", "2026-11-21")
    entries = js.call("MyRoles.setStatus", entries, "a", "interviewing", "2026-11-24")
    entries = js.call("MyRoles.setStatus", entries, "a", "interviewing", "2026-11-25")   # no change, no new line
    e = entries[0]
    assert e["history"] == [{"status": "saved", "on": "2026-11-20"}, {"status": "applied", "on": "2026-11-21"},
                            {"status": "interviewing", "on": "2026-11-24"}]
    assert e["applied_on"] == "2026-11-21" and js.call("MyRoles.daysSince", e, TODAY) == 1
    # Marking a role already in the list changes its status, never duplicates it.
    again = add(js, entries, "a", "offer")
    assert len(again) == 1 and again[0]["status"] == "offer"
    with pytest.raises(Exception):
        js.call("MyRoles.setStatus", entries, "a", "hired", TODAY)


def test_lists_are_never_changed_in_place(js):
    assert js.eval("""(function () {
      var one = MyRoles.add([], MyRoles.snapshot({ id: 'a', title: 't', url: 'https://x.example' }, 'c', 'p', '2026-11-25'), 'applied', '2026-11-25');
      var copy = JSON.stringify(one);
      MyRoles.setStatus(one, 'a', 'offer', '2026-11-26'); MyRoles.setNotes(one, 'a', 'n'); MyRoles.move(one, 'a', 1); MyRoles.remove(one, 'a');
      return JSON.stringify(one) === copy;
    })()""")


def test_the_candidates_own_order(js):
    entries = []
    for rid in "abcd":
        entries = add(js, entries, rid)
    ids = lambda xs: "".join(e["id"] for e in xs)
    assert ids(js.call("MyRoles.move", entries, "c", -1)) == "acbd"
    assert ids(js.call("MyRoles.move", entries, "a", -1)) == "abcd"      # already first
    assert ids(js.call("MyRoles.move", entries, "d", 1)) == "abcd"       # already last
    assert ids(js.call("MyRoles.moveTo", entries, "d", 0)) == "dabc"
    assert ids(js.call("MyRoles.moveTo", entries, "a", 99)) == "bcda"
    assert ids(js.call("MyRoles.remove", entries, "b")) == "acd"
    # Other orders are views only.
    entries = js.call("MyRoles.setStatus", entries, "c", "saved", TODAY)
    assert ids(js.call("MyRoles.sorted", entries, "status")) == "cabd" and ids(entries) == "abcd"


def test_notes_and_applied_date(js):
    entries = add(js, [], "a")
    entries = js.call("MyRoles.setNotes", entries, "a", "x" * 6000)
    entries = js.call("MyRoles.setAppliedOn", entries, "a", "2026-11-02")
    assert len(entries[0]["notes"]) == 5000 and entries[0]["applied_on"] == "2026-11-02"
    assert js.call("MyRoles.setAppliedOn", entries, "a", "next week")[0]["applied_on"] is None


def test_last_listed_is_kept_when_the_posting_leaves_the_board(js):
    entries = add(js, add(js, [], "a", on="2026-11-01"), "b", on="2026-11-01")
    entries = [dict(e, last_listed="2026-11-01") for e in entries]
    marked = js.call("MyRoles.markListed", entries, {"a": True}, "2026-11-25")
    assert {e["id"]: e["last_listed"] for e in marked} == {"a": "2026-11-25", "b": "2026-11-01"}
    # Nothing to record: the same list comes back, so the page writes nothing.
    assert js.eval("(function () { var l = MyRoles.add([], MyRoles.snapshot({ id: 'a', title: 't' }, 'c', 'p', '2026-11-25'), 'applied', '2026-11-25');"
                   " return MyRoles.markListed(l, { a: true }, '2026-11-25') === l; })()")


def test_storage_round_trip_and_what_is_dropped(js):
    entries = add(js, [], "a")
    text = js.call("MyRoles.serialize", entries)
    assert js.call("MyRoles.parse", text) == entries and js.call("MyRoles.parse", None) == []
    odd = {"my_roles_version": 0, "roles": [
        {"id": "x", "title": "T", "url": "javascript:alert(1)", "status": "hired", "secret": "dropped",
         "history": [{"status": "bogus", "on": "2026-11-01"}, {"status": "applied", "on": "not a date"}], "added_on": "2026-11-01"},
        {"id": "x", "title": "duplicate"}]}
    cleaned = js.call("MyRoles.fromData", odd)
    assert len(cleaned) == 1 and cleaned[0]["url"] == "" and cleaned[0]["status"] == "saved" and "secret" not in cleaned[0]
    assert cleaned[0]["history"] == [{"status": "saved", "on": "2026-11-01"}]
    for bad in ({}, {"my_roles_version": 1, "roles": []}, {"my_roles_version": 0, "roles": [{"title": "no id"}]}, "text"):
        with pytest.raises(Exception):
            js.call("MyRoles.fromData", bad)


def test_export_and_import_merge_by_role_and_by_latest_change(js):
    mine = add(js, add(js, [], "a", on="2026-11-20"), "b", on="2026-11-20")
    exported = js.call("MyRoles.exportData", mine, TODAY)
    assert exported["my_roles_version"] == 0 and exported["exported_on"] == TODAY and len(exported["roles"]) == 2
    # Elsewhere: a moved to Offer later, b unchanged, c new. Here: b moved to Rejected after the export.
    other = js.call("MyRoles.setStatus", js.call("MyRoles.fromData", exported), "a", "offer", "2026-11-24")
    other = add(js, other, "c", on="2026-11-22")
    here = js.call("MyRoles.setStatus", mine, "b", "rejected", "2026-11-25")
    out = js.call("MyRoles.importData", js.call("MyRoles.exportData", other, TODAY), here)
    assert (out["added"], out["updated"], out["kept"]) == (1, 1, 1)
    assert [(e["id"], e["status"]) for e in out["list"]] == [("a", "offer"), ("b", "rejected"), ("c", "applied")]


def test_great_matches_are_the_top_two_percent_at_most_thirty_scoring_seventy(js):
    def scored(scores):
        return [{"id": str(i), "match": {"score": s, "excluded": None, "fit": {"great": True}}} for i, s in enumerate(scores)]
    assert js.call("HiPotRank.great", scored([90] * 1000)) == [str(i) for i in range(20)]     # 2% of 1,000
    assert len(js.call("HiPotRank.great", scored([90] * 5000))) == 30                         # at most 30
    assert js.call("HiPotRank.great", scored([65] * 1000)) == []                              # none reach 70
    assert js.call("HiPotRank.great", scored([50, 80, 75])) == ["1"]                          # a small list: its best one
    # Any order in, the best come out; excluded roles never count.
    mixed = scored([71, 95, 60] * 100)
    mixed[1]["match"]["excluded"] = "a company you left out"
    great = js.call("HiPotRank.great", mixed)
    assert len(great) == 5 and "1" not in great and all(int(i) % 3 == 1 for i in great)   # 2% of the 299 left
    # A high score outside the candidate's background is never a great match.
    outside = scored([95, 90, 80])
    outside[0]["match"]["fit"]["great"] = False
    assert js.call("HiPotRank.great", outside) == ["1"]


PERSONA = {
    "persona_version": 0, "disciplines": ["controls", "firmware"], "domains": ["energy-storage", "ev"],
    "locations": {"metros": ["denver"], "remote": True}, "preferences": {"sectors": ["grid", "fission"]},
}


@pytest.mark.parametrize("disc,sectors,great,why", [
    (["controls"], ["energy-storage"], True, "main discipline, known sector"),
    (["firmware", "controls"], ["wind", "grid"], False, "a sector the persona prefers but does not know"),
    (["field", "mechanical", "controls"], ["energy-storage"], False, "controls only as a side tag"),
    (["field"], ["energy-storage"], False, "a discipline next to the persona's, not one of them"),
    (["test"], ["ev"], False, "nearby discipline only"),
    ([], ["ev"], False, "no discipline on the role"),
])
def test_a_great_match_is_squarely_in_the_candidates_background(js, disc, sectors, great, why):
    # Owner feedback 2026-11-27: a sales engineer, balance-of-plant work and gas-turbine plant controls
    # were flagged as great matches for a controls and firmware engineer.
    role = {"fn": "engineering", "level": None, "disc": disc, "metros": ["denver"], "loc": ["Denver, CO"], "wp": "onsite", "pay": None}
    company = {"id": "x", "name": "X", "sectors": sectors, "stage": None}
    match = js.call("HiPotRank.match", role, company, js.call("HiPotRank.normalize", PERSONA), {})
    assert match["fit"]["great"] is great, why
    # A persona with no domains falls back to its preferred sectors.
    no_domains = dict(PERSONA, domains=[], preferences={"sectors": ["energy-storage"]})
    known = js.call("HiPotRank.match", dict(role, disc=["controls"]), dict(company, sectors=["energy-storage"]),
                    js.call("HiPotRank.normalize", no_domains), {})
    assert known["fit"]["great"] is True


# --- The board page --------------------------------------------------------------------------------

def strip_comments(code):
    return re.sub(r"/\*.*?\*/", "", re.sub(r"//[^\n]*", "", code), flags=re.S)


def test_my_roles_uses_one_storage_key_and_every_access_is_wrapped():
    code = strip_comments(SCRIPT)
    assert "var KEY = 'hipot-my-roles';" in script_block("my-roles")
    assert set(re.findall(r"localStorage\.(\w+)\((\w+)", code)) == {("getItem", "MINE_KEY"), ("setItem", "MINE_KEY")}
    assert code.count("localStorage") == 2
    for line in code.splitlines():
        if "localStorage." in line:
            assert line.strip().startswith("try {") or "try {" in code[code.rindex("try {", 0, code.index(line)):code.index(line)], line
    # The pure blocks touch no storage at all.
    for block in ("hipot-rank", "my-roles"):
        assert "Storage." not in strip_comments(script_block(block))
    # Blocked storage: the tab still works and says so; a visitor with no My Roles gets nothing written.
    assert "My Roles lasts only while this tab is open. Export to keep a copy." in SCRIPT
    assert "Kept in this browser only; export to keep a copy." in PAGE
    assert "setMine(listed, { render: false, save: listed !== mine });" in SCRIPT


def test_nothing_about_my_roles_or_great_matches_is_in_the_address():
    encode = SCRIPT[SCRIPT.index("function encodeState()"):SCRIPT.index("function decodeState(")]
    decode = SCRIPT[SCRIPT.index("function decodeState("):SCRIPT.index("function writeHash()")]
    for needle in ("mine", "Mine", "hideMine", "great"):
        assert needle not in encode and needle not in decode, needle
    assert "persona" not in encode   # decode only checks that a persona is loaded before accepting sort-match
    assert "hideMine: false, great: false" in SCRIPT


def test_a_card_in_my_roles_carries_both_the_tag_and_the_border():
    node = SCRIPT[SCRIPT.index("function roleNode(role, grouped)"):SCRIPT.index("function companyHeading(role)")]
    assert "var entry = mineById[role.id];" in node
    assert "if (entry) tags.appendChild(el('li', { class: 'tag-mine' }" in node and "MyRoles.label(entry.status)" in node
    assert "el('li', { class: 'role' + (entry ? ' role-mine' : '')" in node
    assert ".role.role-mine { border-color: var(--mine);" in STYLE
    assert "--mine: #2B55A0;" in STYLE and STYLE.count("--mine: #8FB4F5;") == 2   # light, and both dark blocks
    # A great match: badge, accent edge, and the why line as the badge's tooltip.
    assert "el('li', { class: 'tag-great', title: role.match.why, text: 'Great match' })" in node
    assert ".role.role-great { box-shadow: inset 5px 0 0 var(--accent);" in STYLE


def test_the_card_menu_repeats_what_it_replaces_and_has_a_keyboard_route():
    for needle in ("'Open posting in a new tab'", "'Copy posting link'", "'Mark as applied'", "'Save for later'",
                   "'Remove from My Roles'", "if (event.shiftKey) return;", "'aria-haspopup': 'menu'", "LONG_PRESS_MS = 550"):
        assert needle in SCRIPT, needle
    assert "window.open(role.url, '_blank', 'noopener,noreferrer');" in SCRIPT and "if (!isHttps(role.url)) return;" in SCRIPT
    assert '<div class="menu" id="card-menu" role="menu"' in PAGE
    assert ".role:hover .role-more, .role:focus-within .role-more" in STYLE


def test_the_applied_bar_asks_within_thirty_minutes_and_never_blocks():
    assert "APPLY_WINDOW_MS = 30 * 60 * 1000" in SCRIPT
    assert "window.addEventListener('focus', onReturn);" in SCRIPT and "document.addEventListener('visibilitychange', onReturn);" in SCRIPT
    bar = PAGE[PAGE.index('<div class="apply-bar" id="apply-bar"'):PAGE.index("</div>", PAGE.index('id="apply-bar"'))]
    assert 'role="region"' in bar and "dialog" not in bar and "aria-modal" not in bar
    on_return = SCRIPT[SCRIPT.index("function onReturn()"):SCRIPT.index("function hideApplyBar()")]
    assert ".focus()" not in on_return


def test_great_matches_need_a_persona_and_store_nothing():
    update = SCRIPT[SCRIPT.index("  function update() {"):SCRIPT.index("  function clearAll() {")]
    assert "greatIds = persona ? new Set(HiPotRank.great(shownRoles)) : null;" in update
    assert "if (!persona) state.great = false;" in update
    assert "Storage" not in update
