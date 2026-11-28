"""Company categories (decision 23): the publish step carries them, the board opens on clean tech, and the
category filter round-trips through the address. The rules run in V8 from `<script id="board-filters">`."""
from __future__ import annotations

import json

import pytest

from pipeline.io import ROOT, load_json, load_yaml
from pipeline.publish import build_board, build_pay
from pipeline.publish.pagejs import PageScripts
from tests.publish.test_page import PAGE, SCRIPT, STYLE
from tests.publish.test_publish import company, job, jobs_file, registry
from tools.validate import schema_errors, schema_registry

TAXONOMY = load_yaml(ROOT / "taxonomy.yml")
PAY = {"min": 150000, "max": 190000, "currency": "USD", "period": "year", "basis": "feed"}


def mixed_board(**options):
    reg = registry([
        company("sunco", "core", "in"),
        company("botco", "out", "in", categories=["autonomy-robotics"]),
        company("dualco", "enabling", "in", categories=["defense"]),
        company("plainco", "out", "in"),   # out, no category: not listed
    ])
    jobs = [job(f"{cid}-{n}", cid, metros=["denver"], locations=[{"text": "Denver, CO"}], pay=PAY)
            for cid in ("sunco", "botco", "dualco", "plainco") for n in range(3)]
    return jobs_file(jobs), reg


# --- The publish step ---------------------------------------------------------------------------

def test_publish_carries_each_companys_categories_and_counts_roles_per_category():
    board = build_board(*mixed_board(), TAXONOMY)
    cats = {cid: record.get("cats") for cid, record in board["companies"].items()}
    assert cats == {"sunco": ["clean-tech"], "botco": ["autonomy-robotics"], "dualco": ["clean-tech", "defense"]}
    assert board["counts"]["categories"] == {entry["id"]: {"clean-tech": 6, "autonomy-robotics": 3, "defense": 3}.get(entry["id"], 0)
                                             for entry in TAXONOMY["categories"]}
    assert board["counts"]["left_out_company"] == 3                       # plainco: out and no category
    labels = board["taxonomy"]["categories"]
    assert [entry["id"] for entry in labels] == [entry["id"] for entry in TAXONOMY["categories"]]
    assert [entry for entry in labels if entry.get("default")] == [{"id": "clean-tech", "label": "Clean tech", "default": True}]
    assert schema_errors(board, load_json(ROOT / "pipeline" / "publish" / "board.schema.json"), schema_registry()[0]) == []


def test_a_development_build_marks_an_uncategorized_company_without_categories():
    board = build_board(*mixed_board(), TAXONOMY, include_unlisted=True)
    assert "cats" not in board["companies"]["plainco"] and board["companies"]["plainco"]["unlisted"] is True


def test_the_pay_page_follows_the_boards_default_clean_tech():
    pay = build_pay(*mixed_board(), TAXONOMY)
    assert pay["categories"] == ["clean-tech"]
    assert pay["counts"]["postings"] == 6                                  # sunco and dualco, not botco
    dev = build_pay(*mixed_board(), TAXONOMY, include_unlisted=True)
    assert dev["categories"] == [] and dev["counts"]["postings"] == 12
    assert schema_errors(pay, load_json(ROOT / "pipeline" / "publish" / "pay.schema.json"), schema_registry()[0]) == []
    assert 'id="cat-note" hidden' in (ROOT / "site" / "pay.html").read_text(encoding="utf-8")


# --- The board's filter rules, in V8 --------------------------------------------------------------

KNOWN = ["clean-tech", "autonomy-robotics", "aerospace-space", "defense"]
DEFAULT = ["clean-tech"]


@pytest.fixture(scope="module")
def js():
    with PageScripts("board-filters") as scripts:
        yield scripts


def test_the_default_is_clean_tech_only(js):
    assert js.call("BoardFilters.defaults", TAXONOMY["categories"]) == ["clean-tech"]
    assert js.call("BoardFilters.fromTokens", [""], DEFAULT, KNOWN) == ["clean-tech"]                  # empty address
    assert js.call("BoardFilters.fromTokens", ["f-engineering", "q-test"], DEFAULT, KNOWN) == ["clean-tech"]
    assert js.call("BoardFilters.isDefault", ["clean-tech"], DEFAULT, KNOWN)
    assert not js.call("BoardFilters.isDefault", [], DEFAULT, KNOWN)
    assert not js.call("BoardFilters.isDefault", ["clean-tech", "defense"], DEFAULT, KNOWN)


def test_a_role_shows_when_its_company_is_in_any_checked_category(js):
    of = lambda cats: js.call("BoardFilters.companyCategories", {"cats": cats} if cats is not None else {})
    assert of(["clean-tech", "defense"]) == ["clean-tech", "defense"] and of(None) == ["*none"] and of([]) == ["*none"]
    passes = lambda cats, chosen: js.call("BoardFilters.passes", of(cats), chosen)
    assert passes(["clean-tech"], ["clean-tech"]) and not passes(["autonomy-robotics"], ["clean-tech"])
    assert passes(["clean-tech", "defense"], ["defense"])                  # any one category is enough
    assert passes(["autonomy-robotics"], ["clean-tech", "autonomy-robotics"])
    assert passes(["autonomy-robotics"], []) and passes(None, [])          # nothing ticked: every category
    assert not passes(None, ["clean-tech"]) and passes(None, ["*none"])


@pytest.mark.parametrize("chosen,tokens", [
    (["clean-tech"], []),                                   # the default says nothing: a clean address
    ([], ["cat-all"]),                                      # every category
    (["autonomy-robotics"], ["cat-autonomy-robotics"]),
    (["defense", "clean-tech"], ["cat-clean-tech", "cat-defense"]),   # in the board's order
    (["*none", "clean-tech"], ["cat-clean-tech", "cat-none"]),
])
def test_the_address_round_trip(js, chosen, tokens):
    known = KNOWN + ["*none"]
    assert js.call("BoardFilters.tokens", chosen, DEFAULT, known) == tokens
    back = js.call("BoardFilters.fromTokens", ["f-engineering"] + tokens + ["sort-pay"], DEFAULT, known)
    assert sorted(back) == sorted(chosen)


def test_unknown_categories_in_the_address_fall_back_to_the_default(js):
    assert js.call("BoardFilters.fromTokens", ["cat-made-up"], DEFAULT, KNOWN) == ["clean-tech"]
    assert js.call("BoardFilters.fromTokens", ["cat-made-up", "cat-defense"], DEFAULT, KNOWN) == ["defense"]
    # A board with no clean-tech roles has no default to open on: every category shows.
    assert js.call("BoardFilters.fromTokens", [], DEFAULT, ["defense"]) == []


# --- The board page -------------------------------------------------------------------------------

def test_the_page_wires_the_category_facet():
    assert "{ key: 'cat', title: 'Category', tax: 'categories', none: 'No category', open: true }," in SCRIPT
    assert "cat: BoardFilters.companyCategories(company)," in SCRIPT
    assert "if (!BoardFilters.passes(role.facets[FACETS[f].key], chosen))" in SCRIPT
    assert "defaultCats = BoardFilters.defaults(data.taxonomy.categories);" in SCRIPT
    assert "next.cat = new Set(BoardFilters.fromTokens(all, defaultCats, catIds()));" in SCRIPT
    assert "tokens.push.apply(tokens, BoardFilters.tokens(state.cat, defaultCats, catIds()));" in SCRIPT
    # The default is not counted as an active filter and gets no chip.
    assert "facet.key === 'cat' && isDefaultCats(state.cat) ? 0 : state[facet.key].size" in SCRIPT
    # A company outside clean tech is tagged with its category instead of a tier; clean tech needs no tag.
    badge = SCRIPT[SCRIPT.index("function tierBadge(company)"):SCRIPT.index("function whereText(role)")]
    assert "var adjacent = !known && company.cats && company.cats.length && labels.categories;" in badge
    assert "class: 'tier tier-cat'" in badge and ".tier-cat { color: var(--blue); }" in STYLE
    assert "The board opens on clean tech." in PAGE


def test_the_filter_block_is_pure():
    from pipeline.publish.pagejs import script_block
    code = script_block("board-filters")
    for needle in ("fetch(", "Storage", "document.", "window.", "location."):
        assert needle not in code, needle


def test_the_header_figures_follow_the_category_choice():
    header = SCRIPT[SCRIPT.index("function renderHeader()"):SCRIPT.index("  function update() {")]
    assert "if (!BoardFilters.passes(role.facets.cat, state.cat)) return;" in header
    for stat in ("s-roles", "s-cos", "s-new", "s-places"):
        assert f"$('{stat}').textContent" in header, stat
    assert "' in all categories'" in header and 'id="s-scope"' in PAGE
    assert "renderHeader();" in SCRIPT[SCRIPT.index("  function update() {"):]
    static = SCRIPT[SCRIPT.index("function renderStatic()"):SCRIPT.index("function wireControls()")]
    assert "$('s-roles')" not in static and "$('s-cos')" not in static
