"""Static checks on the persona builder (site/persona.html) and the external hosts of every page.

What was checked in a browser (the synthetic resume as text, PDF and DOCX; the example persona
imported and saved again) is in the A4 report.
"""
from __future__ import annotations

import re

import pytest

from pipeline.io import ROOT, load_yaml
from pipeline.publish.build import build_taxonomy_file

SITE = ROOT / "site"
PAGES = {path.name: path.read_text(encoding="utf-8") for path in SITE.glob("*.html")}
PAGE = PAGES["persona.html"]
SCRIPT = PAGE[PAGE.index("<script>"):PAGE.index("</script>")]
TAXONOMY = load_yaml(ROOT / "taxonomy.yml")


@pytest.mark.parametrize("name", sorted(PAGES))
def test_no_page_names_an_external_host_other_than_cdnjs_and_google_fonts(name):
    hosts = set(re.findall(r"https?://([a-z0-9.-]+)", PAGES[name], re.I))
    assert hosts <= {"cdnjs.cloudflare.com", "fonts.googleapis.com", "fonts.gstatic.com"}, hosts


def test_libraries_are_pinned_exact_versions_from_cdnjs():
    urls = re.findall(r"'(https://cdnjs\.cloudflare\.com/ajax/libs/[^']+)'", SCRIPT)
    assert len(urls) == 4
    for url in urls:
        assert re.match(r"https://cdnjs\.cloudflare\.com/ajax/libs/[a-z.-]+/\d+\.\d+\.\d+/[\w.-]+\.js$", url), url


def test_nothing_leaves_the_page_and_nothing_is_stored():
    # One fetch, for the taxonomy, by a relative address; no other way out and no storage.
    assert SCRIPT.count("fetch(") == 1 and "var TAXONOMY_URL = 'data/taxonomy.json';" in SCRIPT
    for needle in ("XMLHttpRequest", "sendBeacon", "WebSocket", "EventSource", "localStorage", "sessionStorage",
                   "indexedDB", "document.cookie", "method: 'POST'", "innerHTML", "outerHTML", "insertAdjacentHTML", "eval("):
        assert needle not in PAGE, needle
    assert "Your resume stays on this page." in PAGE


def test_identity_is_removed_and_blocked():
    for needle in ("var EMAIL = ", "var PHONE = ", "var LINK = ", "var STREET = ", "function findName(", "'[employer]'"):
        assert needle in SCRIPT, needle
    # A file that still holds an email, phone or link cannot be saved.
    assert "errors.push('Remove ' + rule[1] + ': the file must not identify you.');" in SCRIPT
    # Only persona fields are written: the saved object is built field by field from the schema.
    saved = SCRIPT[SCRIPT.index("function forSaving(p)"):SCRIPT.index("function toYaml(p)")]
    keys = set(re.findall(r"out\.([a-z_]+) =", saved))
    assert keys <= {"functions", "disciplines", "level", "domains", "skills", "standards", "locations",
                    "hard_constraints", "preferences", "exclude", "notes"}, keys


def test_years_come_from_role_dates_and_disciplines_are_reviewed():
    assert "function yearsFor(intervals)" in SCRIPT and "Math.round(total * 2) / 2" in SCRIPT
    assert 'id="all-disciplines"' in PAGE and "proposals.disciplines" in SCRIPT
    # The on-device model is optional, off unless the browser reports it available.
    assert "if (state === 'available') $('ai-disciplines').hidden = false;" in SCRIPT
    assert '<button type="button" class="btn btn-small" id="ai-disciplines" hidden>' in PAGE


def test_save_uses_the_downloads_capability_with_an_allowed_extension():
    assert "window.claude.use('downloads')" in SCRIPT
    assert "downloads.save({ filename: 'persona.yml.txt', data: currentYaml })" in SCRIPT
    assert "download: 'persona.yml'" in SCRIPT   # a plain link elsewhere


def test_board_links_to_the_persona_builder():
    assert '<a href="persona.html">Build your persona (draft)</a>' in PAGES["index.html"]


def test_taxonomy_file_for_the_page():
    data = build_taxonomy_file(TAXONOMY)
    assert {entry["id"] for entry in data["disciplines"]} == {entry["id"] for entry in TAXONOMY["disciplines"]}
    assert all("covers" in entry for entry in data["disciplines"])
    assert len(data["metros"]) == len(TAXONOMY["metros"])
    assert set(data) == {"taxonomy_version", "functions", "disciplines", "levels", "sectors", "stages", "metros"}
