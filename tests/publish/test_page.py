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


GOOGLE_FONTS = ("https://fonts.googleapis.com/css2?family=Inter+Tight:wght@400;500;600;700"
                "&amp;family=JetBrains+Mono:wght@400;500&amp;display=swap")


def test_page_loads_nothing_from_another_origin_except_its_fonts():
    # No external scripts, images or frames: script and styles are inline.
    assert PAGE.count("<script") == 1 and "<script src" not in PAGE
    for needle in ("<img", "<iframe", "<object", "<embed", "@import", "url("):
        assert needle not in PAGE, needle
    # The one stylesheet is Google Fonts, the only stylesheet host artifact hosting allows.
    links = re.findall(r"<link [^>]*>", PAGE)
    assert links == [
        '<link rel="preconnect" href="https://fonts.googleapis.com">',
        '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>',
        f'<link rel="stylesheet" href="{GOOGLE_FONTS}">',
    ]
    # Apart from those, no address is written in the source; role links come from the data.
    addresses = re.findall(r"""["'](?:https?:)?//[^"']+["']""", PAGE)
    assert sorted(addresses) == sorted(['"https://fonts.googleapis.com"', '"https://fonts.gstatic.com"', f'"{GOOGLE_FONTS}"'])
    # Every font has a system fallback.
    assert '--sans: "Inter Tight", system-ui,' in STYLE and '--mono: "JetBrains Mono", ui-monospace,' in STYLE


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
    assert "tags.appendChild(el('li', { class: 'tag-fn', 'data-fn': role.fn, text: labels.functions[role.fn] || role.fn }));" in SCRIPT


def test_role_type_hues_live_in_the_stylesheet():
    # Each listed function gets one of the six category hues; the ids sit in CSS, not in the script.
    hues = dict(re.findall(r'\.tag-fn\[data-fn="([a-z-]+)"\][^{]*\{ color: var\(--([a-z]+)\)', STYLE))
    pairs = re.findall(r'\.tag-fn\[data-fn="([a-z-]+)"\], \.tag-fn\[data-fn="([a-z-]+)"\] \{ color: var\(--([a-z]+)\)', STYLE)
    for first, second, hue in pairs:
        hues[first] = hues[second] = hue
    assert hues == {
        "engineering": "olive", "technician": "rust", "trades": "rust", "science": "blue", "field-operations": "blue",
        "production": "ochre", "supply-chain": "ochre", "quality-compliance": "violet", "ehs": "violet",
        "project-program": "rose", "product": "rose",
    }


def test_location_filter_lists_every_place_in_a_searchable_scrolling_list():
    # Every metro area and state with roles is listed, by role count, in a scrolling box with a search.
    assert "LOCATION_SHORT_LIST" not in SCRIPT and "moreButton" not in SCRIPT
    assert "facet.scroller = el('div', { class: 'loc-list'" in SCRIPT
    assert re.search(r"\.loc-list \{[^}]*max-height: 320px; overflow-y: auto;", STYLE)
    assert "id: 'f-m-find', type: 'search'" in SCRIPT
    assert "(b.total - a.total)" in SCRIPT
    # States are location options in their own right, kept in the address as 'state-xx'.
    assert "if (id.indexOf(STATE_PREFIX) === 0) return 'state-' + id.slice(STATE_PREFIX.length);" in SCRIPT
    assert "states.forEach(function (code) { places.push(STATE_PREFIX + code); });" in SCRIPT
    # Long Census labels wrap rather than push the page wider.
    assert ".opt-label { flex: 1; min-width: 0; overflow-wrap: anywhere; }" in STYLE


def test_whole_card_opens_the_posting_through_one_stretched_link():
    # One real link per card (the title), stretched over the card; nothing interactive inside the link.
    assert '.role h3 a::after { content: ""; position: absolute; inset: 0;' in STYLE
    assert re.search(r"\.role \{\s*position: relative;", STYLE)
    # The company button and "From the posting" sit above the stretched link and keep their own actions.
    assert ".role .co-btn, .role .summary { position: relative; z-index: 1; }" in STYLE
    # Keyboard focus on the title outlines the whole card.
    assert ".role h3 a:focus-visible::after { outline: 2px solid var(--accent); outline-offset: 2px; }" in STYLE
    assert SCRIPT.count("href:") == 1


def test_listed_role_types_sentence_follows_the_taxonomy():
    assert "entry.listed === false" in SCRIPT
    assert "'Every role type is listed, from '" in SCRIPT
    assert "Corporate roles are not listed" not in PAGE


def test_no_newline_inside_a_script_string():
    # A raw line break inside quotes stops the whole script; it slipped in once through an edit tool.
    for quote in ("'", '"'):
        assert not re.search(quote + r"[^" + quote + r"\n]*\n[^" + quote + r"\n]*" + quote + r"\)", SCRIPT)


def test_filter_state_has_a_set_for_every_filter_group():
    assert "FACETS.forEach(function (facet) { fresh[facet.key] = new Set(); });" in SCRIPT
    assert SCRIPT.count("emptyState()") >= 2


def test_page_and_publish_step_agree_on_the_data_version():
    assert f"var BOARD_VERSION = {BOARD_VERSION};" in SCRIPT
