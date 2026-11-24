"""Static checks on the candidate pay page (site/pay.html). What was checked in a browser is in the A4 report."""
from __future__ import annotations

import re

from pipeline.io import ROOT
from pipeline.publish import PAY_VERSION

PAGE = (ROOT / "site" / "pay.html").read_text(encoding="utf-8")
BOARD = (ROOT / "site" / "index.html").read_text(encoding="utf-8")
SCRIPT = PAGE[PAGE.index("<script>"):PAGE.index("</script>")]
STYLE = PAGE[PAGE.index("<style>"):PAGE.index("</style>")]


def test_title_and_links_between_the_two_pages_are_relative():
    assert "<title>HiPot Pay Ranges</title>" in PAGE[:8000]
    assert '<a href="index.html">' in PAGE
    assert '<a href="pay.html">' in BOARD


def test_data_is_one_relative_fetch_and_nothing_else_leaves_the_page():
    assert "var DATA_URL = 'data/pay.json';" in SCRIPT and SCRIPT.count("fetch(") == 1
    assert PAGE.count("<script") == 1 and "<script src" not in PAGE
    for needle in ("<img", "<iframe", "@import", "url(", "document.cookie", "localStorage", "sendBeacon", "XMLHttpRequest"):
        assert needle not in PAGE, needle
    addresses = re.findall(r"""["'](?:https?:)?//[^"']+["']""", PAGE)
    assert all("fonts.googleapis.com" in a or "fonts.gstatic.com" in a for a in addresses)


def test_data_values_never_become_markup():
    for needle in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "new Function"):
        assert needle not in SCRIPT, needle


def test_theme_tokens_follow_the_hosting_contract():
    assert '@media (prefers-color-scheme: dark) {\n  :root:not([data-theme="light"]) {' in STYLE
    assert ':root[data-theme="dark"] {' in STYLE
    tokens = lambda block: dict(re.findall(r"(--[a-z-]+):\s*([^;]+);", block))
    light = STYLE[STYLE.index(":root {"):STYLE.index("@media (prefers-color-scheme: dark)")]
    media = STYLE[STYLE.index("@media (prefers-color-scheme: dark)"):STYLE.index(':root[data-theme="dark"]')]
    forced = STYLE[STYLE.index(':root[data-theme="dark"]'):STYLE.index("*, *::before")]
    assert tokens(media) == tokens(forced) and set(tokens(media)) <= set(tokens(light))
    assert "--gutter-l: max(16px, env(safe-area-inset-left, 0px));" in STYLE


def test_table_scrolls_inside_its_own_box():
    assert ".bwrap { overflow-x: auto;" in STYLE
    assert ".page > *, .main > * { min-width: 0; }" in STYLE


def test_government_wage_place_is_marked_and_empty():
    assert "GOVERNMENT WAGE COLUMN (planned, not built)" in PAGE
    assert "function govWage(group, level, market) { return null; }" in SCRIPT


def test_page_and_publish_step_agree_on_the_data_version():
    assert f"var PAY_VERSION = {PAY_VERSION};" in SCRIPT
