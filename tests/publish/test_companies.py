"""The Companies page (decision 27): companies.json from the publish step, its pay note and read status, the
page's pure rules in V8, and favorite companies on the page and the board. Synthetic data only."""
from __future__ import annotations

import json
import re

import pytest

from pipeline.io import ROOT, load_json, load_yaml
from pipeline.publish.build import build_all
from pipeline.publish.companies import pay_note, read_status
from pipeline.publish.pagejs import PageScripts, script_block
from tests.publish.test_page import SCRIPT as BOARD_SCRIPT
from tests.publish.test_publish import company, job, jobs_file, registry
from tools.validate import schema_errors, schema_registry

TAXONOMY = load_yaml(ROOT / "taxonomy.yml")
PAGE = (ROOT / "site" / "companies.html").read_text(encoding="utf-8")
PAGE_SCRIPT = PAGE[PAGE.index("<script>\n(function"):PAGE.index("</script>", PAGE.index("<script>\n(function"))]
PAY = {"min": 150000, "max": 190000, "currency": "USD", "period": "year", "basis": "feed"}


# --- The pay note and read status ---------------------------------------------------------------

def roles_with(pay_count, total):
    return [job(f"r{n}", "alpha", pay=PAY if n < pay_count else None) for n in range(total)]


@pytest.mark.parametrize("pcts,paid,total,verdict", [
    ([], 0, 0, None),                       # no open roles: no note
    ([], 0, 4, "unlisted"),                 # none publishes pay
    ([5, 30], 3, 4, "few"),                 # pay published, but fewer than 3 graded
    ([12, 25, 9], 3, 3, "above"),           # median 12: more than 10% above
    ([-12, -25, 9], 3, 3, "below"),
    ([-11, 2, 11], 3, 3, "at"),
    ([10, 10, 10], 3, 3, "at"),             # exactly 10% is within the band
])
def test_the_pay_note(pcts, paid, total, verdict):
    roles = roles_with(paid, total)
    graded = {f"r{n}": {"pct": pct} for n, pct in enumerate(pcts)}
    note = pay_note(roles, graded)
    if verdict is None:
        assert note is None
        return
    assert note["v"] == verdict and note["roles"] == total and note["paid"] == paid and note["graded"] == len(pcts)
    assert ("pct" in note) == (verdict in ("above", "at", "below"))


def registry_company(cid, read="auto", ats="greenhouse", board="b"):
    record = company(cid, "core", "in", read=read)
    record["ats"] = {"type": ats, "board": board}
    return record


@pytest.mark.parametrize("read,ats,board,sites,status", [
    ("auto", "greenhouse", "acme", None, "daily"),
    ("auto", "ukg", "acme", None, "weekly"),                 # robots.txt disallows the listing (decision 24)
    ("auto", "adp", "acme", None, "weekly"),
    ("auto", "other", "https://careers.acme.example/jobs", {"acme.example": {"read_at": "x"}}, "weekly"),
    ("auto", "other", "https://careers.acme.example/jobs", {}, "daily"),
    ("manual", "greenhouse", "acme", None, "not-read"),
    ("none", "unknown", None, None, "not-read"),
    ("auto", "greenhouse", None, None, "not-read"),          # no board to read
])
def test_read_status(read, ats, board, sites, status):
    assert read_status(registry_company("acme", read, ats, board), sites) == status


# --- companies.json --------------------------------------------------------------------------------

def built():
    reg = registry([company("alpha", "core", "in", hq="Denver, CO", sectors=["ev"], founded=2019,
                            headcount={"value": 40, "as_of": "2026-11-01", "source": "Company site"}),
                    company("idle", "enabling", "out", hq="Austin, TX"),
                    company("botco", "out", "in", categories=["autonomy-robotics"]),
                    company("plain", "out", "in")])               # out, no category: not listed
    jobs = [job("a1", "alpha", metros=["denver"], locations=[{"text": "Denver, CO"}], pay=PAY, function="technician"),
            job("a2", "alpha", workplace="remote", locations=[{"text": "Remote, US"}]),
            job("b1", "botco"), job("p1", "plain")]
    return build_all(jobs_file(jobs), reg, TAXONOMY)


def test_every_listed_company_is_in_the_file_hiring_or_not():
    out = built()
    data, board = out["companies"], out["board"]
    assert data["generated_at"] == board["generated_at"]
    by_id = {c["id"]: c for c in data["companies"]}
    assert set(by_id) == {"alpha", "idle", "botco"}                  # 'plain' is not listed
    assert data["counts"]["companies"] == 3 and data["counts"]["hiring"] == 2
    alpha, idle = by_id["alpha"], by_id["idle"]
    assert alpha["roles"] == 2 and alpha["metros"] == ["denver"] and alpha["st"] == ["co"] and alpha["remote"] is True
    assert alpha["fns"] == {"engineering": 1, "technician": 1} and alpha["pay"]["v"] == "few"
    assert alpha["hc"] == {"n": 40, "as_of": "2026-11-01", "src": "Company site"} and alpha["founded"] == 2019
    assert idle["roles"] == 0 and "pay" not in idle and "metros" not in idle and idle["hq"] == "Austin, TX"
    assert by_id["botco"]["cats"] == ["autonomy-robotics"] and alpha["cats"] == ["clean-tech"]
    schema = load_json(ROOT / "pipeline" / "publish" / "companies.schema.json")
    assert schema_errors(data, schema, schema_registry()[0]) == []


def test_the_command_writes_companies_json_beside_the_board(tmp_path, capsys):
    from pipeline.publish.__main__ import main
    out = tmp_path / "shared" / "board.json"
    assert main(["--jobs", str(ROOT / "data" / "seed" / "jobs.json"), "--out", str(out)]) == 0
    data = json.loads((tmp_path / "shared" / "companies.json").read_text(encoding="utf-8"))
    assert data["generated_at"] == json.loads(out.read_text(encoding="utf-8"))["generated_at"]
    assert "companies:" in capsys.readouterr().out


# --- The pages' pure blocks, in V8 ------------------------------------------------------------------

@pytest.fixture(scope="module")
def js():
    from py_mini_racer import MiniRacer
    ctx = MiniRacer()
    for block in ("board-filters", "favorites", "company-rules"):
        opening = f'<script id="{block}">'
        start = PAGE.index(opening) + len(opening)
        ctx.eval(PAGE[start:PAGE.index("</script>", start)])

    class Scripts:
        def call(self, name, *args):
            ctx.eval(f"var __args = {json.dumps(args)};")
            return json.loads(ctx.eval(f"JSON.stringify({name}.apply(null, __args))"))
    yield Scripts()
    ctx.close()


def test_the_shared_blocks_are_the_same_on_both_pages():
    for block in ("board-filters", "favorites"):
        opening = f'<script id="{block}">'
        start = PAGE.index(opening) + len(opening)
        assert PAGE[start:PAGE.index("</script>", start)] == script_block(block), block


def test_favorites(js):
    one = js.call("Favorites.toggle", [], "acme", "Acme", "2026-11-28")
    assert one == [{"id": "acme", "name": "Acme", "added_on": "2026-11-28"}]
    assert js.call("Favorites.toggle", one, "acme", "Acme", "2026-11-28") == []            # a second click unstars
    assert js.call("Favorites.parse", js.call("Favorites.serialize", one)) == one
    merged = js.call("Favorites.merge", one, {"favorites_version": 0, "companies": [{"id": "acme"}, {"id": "beta", "name": "Beta"}]})
    assert merged["added"] == 1 and [f["id"] for f in merged["list"]] == ["acme", "beta"]
    assert js.call("Favorites.fromData", [{"id": "Bad Id"}, {"id": "ok"}, {"id": "ok"}]) == [{"id": "ok", "name": "ok", "added_on": None}]
    for bad in ({}, {"favorites_version": 1, "companies": []}, "text"):
        with pytest.raises(Exception):
            js.call("Favorites.fromData", bad)


@pytest.mark.parametrize("note,label,basis", [
    (None, "No open roles", ""),
    ({"v": "unlisted", "roles": 4, "paid": 0, "graded": 0}, "Unlisted salaries", "none of its 4 open roles publishes pay"),
    ({"v": "few", "roles": 5, "paid": 1, "graded": 1}, "Too few to say", "1 role with pay, not enough to compare"),
    ({"v": "at", "roles": 20, "paid": 14, "graded": 12, "pct": 3}, "At market", "14 of 20 roles publish pay; median within 10% of the market"),
    ({"v": "above", "roles": 8, "paid": 8, "graded": 6, "pct": 18}, "Above market", "8 of 8 roles publish pay; median 18% above the market"),
    ({"v": "below", "roles": 3, "paid": 3, "graded": 3, "pct": -14}, "Below market", "3 of 3 roles publish pay; median 14% below the market"),
])
def test_the_pay_note_in_words(js, note, label, basis):
    out = js.call("CompanyRules.payText", note)
    assert out["label"] == label and out["basis"] == basis


COMPANIES = [
    {"id": "sun", "name": "Sunco", "cats": ["clean-tech"], "type": "startup", "stage": "seed", "sectors": ["solar"],
     "metros": ["denver"], "st": ["co"], "roles": 5, "new": 2, "pay": {"v": "at", "pct": 2}, "read": "daily", "hc": {"n": 40}},
    {"id": "bot", "name": "Botco", "cats": ["autonomy-robotics"], "type": "established", "roles": 9, "remote": True,
     "pay": {"v": "above", "pct": 20}, "read": "weekly", "hc": {"n": 900}},
    {"id": "idle", "name": "Idle Power", "cats": ["clean-tech"], "type": "startup", "roles": 0, "read": "not-read"},
]


def ids(js, f, fav=None):
    base = {"q": "", "cats": ["clean-tech"], "place": "", "sector": "", "type": "", "stage": "", "hiring": False,
            "pay": "", "read": "", "fav": False}
    base.update(f)
    return [c["id"] for c in COMPANIES if js.call("CompanyRules.matches", c, base, fav or {})]


def test_filters(js):
    assert ids(js, {}) == ["sun", "idle"]                                  # the default: clean tech only
    assert ids(js, {"cats": []}) == ["sun", "bot", "idle"]                 # nothing ticked: every category
    assert ids(js, {"cats": ["autonomy-robotics"]}) == ["bot"]
    assert ids(js, {"hiring": True}) == ["sun"]
    assert ids(js, {"cats": [], "place": "remote"}) == ["bot"]
    assert ids(js, {"place": "m-denver"}) == ["sun"] and ids(js, {"place": "s-co"}) == ["sun"]
    assert ids(js, {"sector": "solar"}) == ["sun"] and ids(js, {"stage": "seed"}) == ["sun"]
    assert ids(js, {"cats": [], "type": "established"}) == ["bot"]
    assert ids(js, {"cats": [], "pay": "above"}) == ["bot"] and ids(js, {"read": "not-read"}) == ["idle"]
    assert ids(js, {"fav": True}, {"idle": True}) == ["idle"]
    assert ids(js, {"q": "idle POW"}) == ["idle"]


@pytest.mark.parametrize("by,order", [
    ("roles", ["bot", "sun", "idle"]), ("new", ["sun", "bot", "idle"]), ("name", ["bot", "idle", "sun"]),
    ("pay", ["bot", "sun", "idle"]), ("headcount", ["bot", "sun", "idle"]),
])
def test_sort(js, by, order):
    assert [c["id"] for c in js.call("CompanyRules.sort", COMPANIES, by)] == order


# --- The pages -----------------------------------------------------------------------------------

def test_the_companies_page_keeps_one_key_and_talks_only_to_its_own_origin():
    code = re.sub(r"//[^\n]*", "", PAGE_SCRIPT)
    assert set(re.findall(r"localStorage\.(\w+)\((\w+)", code)) == {("getItem", "FAV_KEY"), ("setItem", "FAV_KEY")}
    assert "var KEY = 'hipot-favorite-companies';" in script_block("favorites")
    assert code.count("fetch(") == 2 and "fetch(DATA_URL)" in code and "fetch(LOCAL_API + name, options)" in code
    assert "var DATA_URL = 'data/companies.json';" in code
    api = code[code.index("function localApi("):code.index("function loadYaml()")]
    assert api.index("if (!servedLocally()) return Promise.resolve(null);") < api.index("fetch(")
    for needle in ("sessionStorage", "innerHTML", "document.cookie", "XMLHttpRequest", "sendBeacon"):
        assert needle not in PAGE, needle


def test_the_companies_page_links_to_the_board_filtered_to_the_company():
    # Every category, so an adjacent company's roles are not hidden by the board's clean-tech default.
    assert "el('a', { href: 'index.html#c-' + company.id + '--cat-all'" in PAGE_SCRIPT
    assert '<a href="companies.html">Companies</a>' in (ROOT / "site" / "index.html").read_text(encoding="utf-8")
    assert 'href="companies.html"' in (ROOT / "site" / "pay.html").read_text(encoding="utf-8")


def test_favorites_on_the_board():
    assert "companyButton, ' ', favButton(company, role.id), ' ', tierBadge(company), ' '," in BOARD_SCRIPT
    assert "if (state.favOnly && !favIds[role.co]) continue;" in BOARD_SCRIPT
    assert 'id="f-fav-only"' in (ROOT / "site" / "index.html").read_text(encoding="utf-8")
    # My Roles' export carries them; an import merges them.
    assert "if (withFavorites) data.favorite_companies = Favorites.toData(favs).companies;" in BOARD_SCRIPT
    assert "Favorites.merge(favs, data.favorite_companies)" in BOARD_SCRIPT
    # Never in the address.
    encode = BOARD_SCRIPT[BOARD_SCRIPT.index("function encodeState()"):BOARD_SCRIPT.index("function decodeState(")]
    assert "fav" not in encode.lower()
