"""Workplace refinement and the summary excerpt."""
from __future__ import annotations

import pytest

from pipeline.tag.summary import MAX_LENGTH, summarise
from pipeline.tag.workplace import refine_workplace, workplace_from_text, workplace_from_title


@pytest.mark.parametrize("text,expected", [
    ("This is a fully on-site role at our Carson City plant.", "onsite"),
    ("This is an in-person role in Pratt, Kansas.", "onsite"),
    ("This is a hybrid role, requiring in-person work three days a week at our office.", "hybrid"),
    ("This position follows a hybrid schedule, with team members in the office.", "hybrid"),
    ("You will be in the office 3 days per week.", "hybrid"),
    ("This is a remote position open to candidates in the US.", "remote"),
    ("This role is fully remote within the United States.", "remote"),
])
def test_clear_statements(text, expected):
    assert workplace_from_text(text) == expected


@pytest.mark.parametrize("text", [
    "",
    "Design hybrid inverters for residential storage.",
    "Build remote monitoring for our fleet of batteries.",
    "Collaborate with remote team members across three time zones.",
    "On-site team lunches and a stocked kitchen.",
    "Occasional travel for on-site work at customer sites.",
    "Fully remote working or hybrid depending on preference.",
])
def test_unclear_or_unrelated_text_decides_nothing(text):
    assert workplace_from_text(text) is None


def test_negated_remote():
    assert workplace_from_text("This is not a remote position. It is an on-site role in Austin.") == "onsite"


def test_title_markers():
    assert workplace_from_title("Senior Commissioning Engineer (Remote)") == "remote"
    assert workplace_from_title("Controls Engineer - Hybrid") == "hybrid"
    assert workplace_from_title("Senior Mechanical Engineer") is None


def test_collector_value_wins_unless_unknown():
    assert refine_workplace("onsite", "Engineer (Remote)", "This is a remote position.") == "onsite"
    assert refine_workplace("unknown", "Engineer (Remote)", "") == "remote"
    assert refine_workplace("unknown", "Engineer", "Nothing about where.") == "unknown"


def test_summary_starts_at_the_role_and_stays_short():
    text = ("Acme Storage builds batteries for the grid. We are a team of builders.\n"
            "About the Role\n"
            "You will own the thermal design of our pack enclosure. You will run CFD and test it. "
            + "You will work closely with suppliers. " * 30
            + "\nWe are an equal opportunity employer and consider applicants without regard to race.")
    summary = summarise(text)
    assert summary.startswith("You will own the thermal design")
    assert len(summary) <= MAX_LENGTH
    assert "equal opportunity" not in summary


def test_summary_skips_contact_details_and_handles_short_or_empty_text():
    assert summarise("") is None
    assert summarise("Short.") is None
    summary = summarise("Design power stages for our inverter. Questions? Write to jobs@example.com today. "
                        "You will lead bring-up of new boards.")
    assert "@" not in summary


def test_summary_of_one_long_sentence_is_cut_at_a_word():
    summary = summarise("You will " + "design and test power electronics " * 40)
    assert len(summary) <= MAX_LENGTH and summary.endswith("…")
