"""Keeping board.json small (size report, 2026-11-28): summaries cut to 200 characters at a sentence or a
word, `seen` only when a role has no posted date, and `emp` only when it is not full-time."""
from __future__ import annotations

import pytest

from pipeline.io import ROOT, load_yaml
from pipeline.publish import build_board
from pipeline.publish.build import SUMMARY_CHARS, shorten
from tests.publish.test_publish import board_errors, company, job, jobs_file, registry

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
    assert len(roles["posted"]["summary"]) <= SUMMARY_CHARS and roles["posted"]["summary"].endswith(".")
    assert board_errors(board) == []
