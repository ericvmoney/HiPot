"""Keeping board.json small (size report, 2026-11-28): `seen` only when a role has no posted date, `emp`
only when it is not full-time, and the posting summaries in their own file (summaries.json), each distinct
text once, cut to 300 characters at a sentence or a word."""
from __future__ import annotations

import json

import pytest

from pipeline.io import ROOT, load_json, load_yaml
from pipeline.publish import build_board
from pipeline.publish.build import SUMMARY_CHARS, build_outputs, dumps_summaries, shorten
from tests.publish.test_publish import board_errors, company, job, jobs_file, registry
from tools.validate import schema_errors, schema_registry

TAXONOMY = load_yaml(ROOT / "taxonomy.yml")
SENTENCES = ("Build the battery pack test rig for our grid storage product. Work with firmware, controls and quality "
             "engineers on validation plans for every release. Own the data pipeline for every test run, from raw logs "
             "to the weekly report the team reads.")


def test_short_text_is_kept_whole():
    assert shorten("  Own the inverter control loop.  ", 200) == "Own the inverter control loop."
    assert shorten("x" * 200, 200) == "x" * 200


def test_a_long_text_is_cut_at_a_sentence_end_when_one_is_near_the_limit():
    out = shorten(SENTENCES, 200)
    assert out == ("Build the battery pack test rig for our grid storage product. Work with firmware, controls and quality "
                   "engineers on validation plans for every release.")
    # A sentence end earlier than 60% of the limit would lose too much: then the cut is at a word.
    early = "Short opener. " + "then a long clause without any stop " * 10
    assert shorten(early, 200).endswith("…")
    # A sentence ending exactly at the limit is kept as it is.
    text = "a" * 199 + ". Next sentence."
    assert shorten(text, 200) == "a" * 199 + "."


def test_otherwise_at_a_word_with_an_ellipsis():
    text = "Join a team building " + "very " * 60 + "large machines."
    out = shorten(text, 200)
    assert out.endswith("…") and len(out) <= 200 and not out[:-1].endswith(" ")
    assert text.startswith(out[:-1])
    assert shorten("x" * 300, 200) == "x" * 199 + "…"      # no space at all: a hard cut
    assert shorten("word, " * 60, 200).endswith("word…")     # no comma left before the ellipsis


@pytest.mark.parametrize("length", [150, 199, 200, 201, 260, 499, 2000])
def test_never_longer_than_the_limit(length):
    text = ("Lorem ipsum dolor sit amet. " * 100)[:length]
    assert len(shorten(text, SUMMARY_CHARS)) <= SUMMARY_CHARS


def test_the_board_drops_what_the_page_does_not_need():
    reg = registry([company("alpha", "core", "in")])
    jobs = [job("posted", "alpha", posted_date="2026-11-21", employment="full-time", summary=SENTENCES),
            job("unposted", "alpha", employment="contract"),
            job("unknown", "alpha", employment="unknown")]
    board = build_board(jobs_file(jobs), reg, TAXONOMY)
    roles = {role["id"]: role for role in board["roles"]}
    assert roles["posted"]["posted"] == "2026-11-21" and "seen" not in roles["posted"]   # dated by posted
    assert roles["unposted"]["seen"] == "2026-11-20" and "posted" not in roles["unposted"]
    assert "emp" not in roles["posted"] and roles["unposted"]["emp"] == "contract" and "emp" not in roles["unknown"]
    assert "summary" not in roles["posted"] and roles["posted"]["sm"] == 0 and "sm" not in roles["unposted"]
    assert board_errors(board) == []


# --- Summaries in their own file (summaries.json) -------------------------------------------------

BLURB = "Acme makes heat pumps for apartment buildings. " * 10   # a company blurb many roles share


def test_each_distinct_summary_is_stored_once_and_roles_point_to_it():
    reg = registry([company("alpha", "core", "in"), company("beta", "core", "in")])
    jobs = [job("a1", "alpha", summary=BLURB), job("a2", "alpha", summary=BLURB),
            job("a3", "alpha", summary="Own the inverter control loop."), job("b1", "beta", summary=BLURB),
            job("b2", "beta")]
    board, summaries = build_outputs(jobs_file(jobs), reg, TAXONOMY)
    assert summaries["generated_at"] == board["generated_at"] and summaries["summaries_version"] == 0
    assert len(summaries["texts"]) == 2 and SUMMARY_CHARS == 300
    assert all(len(text) <= 300 for text in summaries["texts"])
    texts = {role["id"]: summaries["texts"][role["sm"]] for role in board["roles"] if "sm" in role}
    assert texts["a1"] == texts["a2"] == texts["b1"] == shorten(BLURB, 300)
    assert texts["a3"] == "Own the inverter control loop." and "b2" not in texts
    schema = load_json(ROOT / "pipeline" / "publish" / "summaries.schema.json")
    assert schema_errors(summaries, schema, schema_registry()[0]) == []
    assert json.loads(dumps_summaries(summaries)) == summaries
    assert board == build_board(jobs_file(jobs), reg, TAXONOMY)   # the same board, whichever way it is built


def test_the_command_writes_summaries_beside_the_board(tmp_path, capsys):
    from pipeline.publish.__main__ import main
    out = tmp_path / "shared" / "board.json"
    assert main(["--jobs", str(ROOT / "data" / "seed" / "jobs.json"), "--out", str(out), "--no-grades"]) == 0
    board = json.loads(out.read_text(encoding="utf-8"))
    summaries = json.loads((tmp_path / "shared" / "summaries.json").read_text(encoding="utf-8"))
    assert summaries["generated_at"] == board["generated_at"]
    assert all(0 <= role["sm"] < len(summaries["texts"]) for role in board["roles"] if "sm" in role)
    assert "summaries:" in capsys.readouterr().out


def test_the_page_loads_summaries_only_when_one_is_opened():
    from tests.publish.test_page import SCRIPT
    node = SCRIPT[SCRIPT.index("function summaryNode(role)"):SCRIPT.index("// A company heading")]
    assert "box.addEventListener('toggle'" in node and "if (!box.open || box.dataset.loaded) return;" in node
    assert "loadSummaries().then(" in node and "text.textContent =" in node   # text, never markup
    load = SCRIPT[SCRIPT.index("function loadSummaries()"):SCRIPT.index("function summaryNode(role)")]
    assert "if (data.generated_at !== board.generated_at)" in load   # never another refresh's indexes
    assert "typeof role.sm === 'number' ? summaryNode(role) : null" in SCRIPT
    assert "role.summary" not in SCRIPT
