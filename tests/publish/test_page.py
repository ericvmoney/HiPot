"""Static checks on the board page: the rules it must keep that can be read from its source.

These do not run the page. What was checked in a real browser is recorded in the A4 report.
"""
from __future__ import annotations

import re

from pipeline.io import ROOT
from pipeline.publish import BOARD_VERSION

PAGE = (ROOT / "site" / "index.html").read_text(encoding="utf-8")
SCRIPT = PAGE[PAGE.index("<script>"):PAGE.index("</script>")]
STYLE = PAGE[PAGE.index("<style>"):PAGE.index("</style>")]


def test_title_is_a_short_name_near_the_top():
    assert "<title>HiPot Jobs</title>" in PAGE[:8000]


def test_page_loads_nothing_from_another_origin():
    # No external scripts, stylesheets, fonts, images or frames: everything is inline.
    assert PAGE.count("<script") == 1 and "<script src" not in PAGE
    for needle in ("<link", "<img", "<iframe", "<object", "<embed", "@import", "url("):
        assert needle not in PAGE, needle
    # The only addresses written in the source are none at all; role links come from the data.
    assert re.findall(r"""["'](?:https?:)?//[^"']+["']""", PAGE) == []


def test_data_is_fetched_once_by_a_relative_address():
    assert "var DATA_URL = 'data/board.json';" in SCRIPT
    assert SCRIPT.count("fetch(") == 1 and "fetch(DATA_URL)" in SCRIPT


def test_no_cookies_storage_tracking_or_other_network_calls():
    for needle in ("document.cookie", "localStorage", "sessionStorage", "indexedDB", "sendBeacon",
                   "XMLHttpRequest", "WebSocket", "EventSource", "navigator.userAgent", "gtag", "analytics"):
        assert needle not in PAGE, needle


def test_data_values_never_become_markup():
    for needle in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "new Function"):
        assert needle not in SCRIPT, needle
    # Links leave the site only through outLink(), which refuses anything that is not https.
    assert "function isHttps(url) { return typeof url === 'string' && /^https:\\/\\//i.test(url); }" in SCRIPT
    assert SCRIPT.count("href:") == 1
    assert "rel: 'noopener noreferrer'" in SCRIPT and "target: '_blank'" in SCRIPT


def test_theme_tokens_follow_the_hosting_contract():
    assert re.search(r"^:root \{", STYLE, re.M)
    assert '@media (prefers-color-scheme: dark) {\n  :root:not([data-theme="light"]) {' in STYLE
    assert ':root[data-theme="dark"] {' in STYLE
    assert "background: var(--bg);" in STYLE[STYLE.index("body {"):STYLE.index("body {") + 200]
    # Every token set in a dark block is first defined on bare :root, and both dark blocks match.
    light = STYLE[STYLE.index(":root {"):STYLE.index("@media (prefers-color-scheme: dark)")]
    media = STYLE[STYLE.index("@media (prefers-color-scheme: dark)"):STYLE.index(':root[data-theme="dark"]')]
    forced = STYLE[STYLE.index(':root[data-theme="dark"]'):STYLE.index("*, *::before")]
    tokens = lambda block: dict(re.findall(r"(--[a-z-]+):\s*([^;]+);", block))
    assert tokens(media) == tokens(forced)
    assert set(tokens(media)) <= set(tokens(light))
    # No colour literal outside the token blocks, apart from the dialog backdrop.
    rest = STYLE[STYLE.index("*, *::before"):]
    assert re.findall(r"#[0-9a-fA-F]{3,8}\b", rest) == []
    assert re.findall(r"rgba?\([^)]*\)", rest) == ["rgb(0 0 0 / 0.45)"]


def test_side_gutter_and_its_promise_go_together():
    assert '<meta name="claude:viewport-fit-sides" content="cover">' in PAGE
    assert "--gutter-l: max(16px, env(safe-area-inset-left, 0px));" in STYLE
    assert "--gutter-r: max(16px, env(safe-area-inset-right, 0px));" in STYLE
    assert "padding-left: var(--gutter-l);" in STYLE and "padding-right: var(--gutter-r);" in STYLE


def test_persona_hook_exists_and_no_persona_interface_is_built():
    assert "function rankRolesForPersona(rolesInOrder, candidatePersona)" in SCRIPT
    assert "rankRolesForPersona(sortRoles(outcome.matched), persona)" in SCRIPT
    assert 'type="file"' not in PAGE and "resume" not in PAGE.lower()


def test_role_type_is_the_first_filter_and_every_role_shows_its_function():
    facets = SCRIPT[SCRIPT.index("var FACETS = ["):SCRIPT.index("];", SCRIPT.index("var FACETS = ["))]
    keys = re.findall(r"\{ key: '([a-z]+)'", facets)
    assert keys[0] == "f" and "tax: 'functions'" in facets.splitlines()[1]
    assert len(keys) == len(set(keys))
    # Function ids and labels come from the data file, never from a list in the page.
    for function_id in ("engineering", "technician", "sales-bd", "supply-chain"):
        assert f"'{function_id}'" not in SCRIPT
    # The function label leads the tag row, so the row is never empty for a role with no discipline.
    assert "tags.appendChild(el('li', { class: 'tag-fn', text: labels.functions[role.fn] || role.fn }));" in SCRIPT


def test_filter_state_has_a_set_for_every_filter_group():
    assert "FACETS.forEach(function (facet) { fresh[facet.key] = new Set(); });" in SCRIPT
    assert SCRIPT.count("emptyState()") >= 2


def test_page_and_publish_step_agree_on_the_data_version():
    assert f"var BOARD_VERSION = {BOARD_VERSION};" in SCRIPT
