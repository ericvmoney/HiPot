"""Static checks on the board page: the rules it must keep that can be read from its source.

These do not run the page. What was checked in a real browser is recorded in the A4 report.
"""
from __future__ import annotations

import re

from pipeline.io import ROOT
from pipeline.publish import BOARD_VERSION

PAGE = (ROOT / "site" / "index.html").read_text(encoding="utf-8")
SCRIPT = PAGE[PAGE.index("<script>"):PAGE.index("</script>", PAGE.index("<script>"))]   # the page script, after the ranking block
STYLE = PAGE[PAGE.index("<style>"):PAGE.index("</style>")]


def test_title_is_a_short_name_near_the_top():
    assert "<title>HiPot Jobs</title>" in PAGE[:8000]


GOOGLE_FONTS = ("https://fonts.googleapis.com/css2?family=Inter+Tight:wght@400;500;600;700"
                "&amp;family=JetBrains+Mono:wght@400;500&amp;display=swap")


YAML_LIB = "https://cdnjs.cloudflare.com/ajax/libs/js-yaml/4.1.0/js-yaml.min.js"


def test_page_loads_nothing_from_another_origin_except_its_fonts_and_the_yaml_reader():
    # No external scripts, images or frames: the page's scripts and styles are inline. The one exception
    # is js-yaml, pinned on cdnjs and loaded only when a visitor opens a persona file.
    assert PAGE.count("<script") == 3 and '<script id="hipot-rank">' in PAGE and '<script id="my-roles">' in PAGE
    assert "<script src" not in PAGE
    assert f"var YAML_LIB = '{YAML_LIB}';" in SCRIPT and "tag.src = YAML_LIB;" in SCRIPT
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
    assert sorted(addresses) == sorted(['"https://fonts.googleapis.com"', '"https://fonts.gstatic.com"', f'"{GOOGLE_FONTS}"', f"'{YAML_LIB}'"])
    # Every font has a system fallback.
    assert '--sans: "Inter Tight", system-ui,' in STYLE and '--mono: "JetBrains Mono", ui-monospace,' in STYLE


def test_data_is_fetched_once_by_a_relative_address():
    assert "var DATA_URL = 'data/board.json';" in SCRIPT
    assert SCRIPT.count("fetch(") == 1 and "fetch(DATA_URL)" in SCRIPT


def test_no_cookies_storage_tracking_or_other_network_calls():
    # sessionStorage holds the persona for the tab only (test_ranking.py); localStorage holds My Roles under
    # one key (test_my_roles.py). Nothing else is kept, and nothing is sent.
    for needle in ("document.cookie", "indexedDB", "sendBeacon",
                   "XMLHttpRequest", "WebSocket", "EventSource", "navigator.userAgent", "gtag", "analytics"):
        assert needle not in PAGE, needle


def test_data_values_never_become_markup():
    for needle in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "new Function"):
        assert needle not in SCRIPT, needle
    # Links leave the site only through outLink(), which refuses anything that is not https.
    assert "function isHttps(url) { return typeof url === 'string' && /^https:\\/\\//i.test(url); }" in SCRIPT
    # Two href: outLink(), and the link that saves an exported My Roles file from a blob: address.
    assert SCRIPT.count("href:") == 2 and "el('a', { href: url, download: 'my-roles.yml' })" in SCRIPT
    assert "var url = window.URL.createObjectURL(new Blob([text], { type: 'text/yaml' }));" in SCRIPT
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
    # No colour literal outside the token blocks, apart from the dialog backdrop and two shadows (card menu, bars).
    rest = STYLE[STYLE.index("*, *::before"):]
    assert re.findall(r"#[0-9a-fA-F]{3,8}\b", rest) == []
    assert sorted(re.findall(r"rgba?\([^)]*\)", rest)) == ["rgb(0 0 0 / 0.25)", "rgb(0 0 0 / 0.3)", "rgb(0 0 0 / 0.45)"]


def test_side_gutter_and_its_promise_go_together():
    assert '<meta name="claude:viewport-fit-sides" content="cover">' in PAGE
    assert "--gutter-l: max(16px, env(safe-area-inset-left, 0px));" in STYLE
    assert "--gutter-r: max(16px, env(safe-area-inset-right, 0px));" in STYLE
    assert "padding-left: var(--gutter-l);" in STYLE and "padding-right: var(--gutter-r);" in STYLE


def test_persona_hook_ranks_and_the_board_never_reads_a_resume():
    assert "function rankRolesForPersona(rolesInOrder, candidatePersona)" in SCRIPT
    assert "rankRolesForPersona(sortRoles(shownRoles), persona)" in SCRIPT
    # The file inputs take a persona and a My Roles file; resumes are read only on the persona page.
    assert PAGE.count('type="file"') == 2 and 'id="persona-file"' in PAGE and 'id="mine-file"' in PAGE
    assert 'accept=".yml,.yaml,.txt,.json,' in PAGE and ".pdf" not in PAGE and ".docx" not in PAGE


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
    # Metro areas by role count; states A to Z by name.
    assert "if (a.kind === 'state') return a.label.localeCompare(b.label, 'en');" in SCRIPT
    assert "return (b.total - a.total) || a.label.localeCompare(b.label, 'en');" in SCRIPT
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
    # The card's ⋯ button sits above the stretched link too.
    assert ".role-more {\n  position: absolute; top: 6px; right: 6px; z-index: 2;" in STYLE


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


def test_pay_vs_market_tag_and_filter():
    # The filter exists only when the data carries grades (publish --grades, the default).
    assert "{ key: 'g', title: 'Pay vs market', tax: 'grades', none: 'No grade', open: false }" in SCRIPT
    assert "FACETS = FACETS.filter(function (facet) { return Array.isArray(data.taxonomy[facet.tax]); });" in SCRIPT
    # The tag says what it compared, for sighted and screen-reader users, and that it is not an estimate.
    assert "title: said" in SCRIPT and "class: 'sr-only', text: labels.grades[role.grade.v] + '. ' + said" in SCRIPT
    assert "published ranges, not a salary estimate.';" in SCRIPT
    # It sits above the card's stretched link so its tooltip can show.
    assert ".grade { position: relative; z-index: 1;" in STYLE
    assert '<p id="grade-note" hidden>' in PAGE and "$('grade-note').hidden = !board.grades;" in SCRIPT


def test_company_type_filter_and_tag():
    # Decision 14: Startup and Established, both shown by default, kept in the address like the others.
    assert "{ key: 'ct', title: 'Company type', tax: 'company_types', open: true }" in SCRIPT
    assert "ct: [company.type || 'unchecked']," in SCRIPT
    assert "el('span', { class: 'tier tier-type', text: labels.company_types[company.type] || company.type })" in SCRIPT
    assert "Startups and established companies are both listed, and labelled." in PAGE
    assert "fewer than 4,000 people" in PAGE and "fewer than 1,000 people" not in PAGE


def test_new_tag_filter_and_header_stat():
    # Decision 15: a "New" tag, a "New" filter kept in the address (n-new), and the count in the header.
    assert "{ key: 'n', title: 'New', tax: 'fresh', open: true }" in SCRIPT
    assert "n: role.new ? ['new'] : []," in SCRIPT
    assert "if (role.new) tags.appendChild(el('li', { class: 'tag-new', text: 'New' }));" in SCRIPT
    assert '<b id="s-new">0</b>' in PAGE
    # A filter group with nothing to offer is hidden rather than shown empty.
    assert "facet.details.hidden = facet.options.every(function (option) { return option.total === 0; });" in SCRIPT
