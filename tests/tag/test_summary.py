"""The summary starts at the role, not at the company's "about us" paragraph.

Synthetic postings, modelled on the layouts the feeds use; no posting is copied.
"""
from __future__ import annotations

from pipeline.tag.summary import MAX_LENGTH, summarise

BLURB = ("Acme Storage is a leading developer of long-duration batteries, founded in 2015 and headquartered in "
         "Denver. With 900 employees in 12 countries, we are accelerating the path to a cleaner grid.")
EEO = "Acme Storage is an equal opportunity employer and considers applicants without regard to race or religion."


def test_starts_under_a_role_heading_after_the_company_paragraph():
    text = f"{BLURB}\nTHE ROLE\nYou will own the thermal design of our pack enclosure.\n{EEO}"
    assert summarise(text).startswith("You will own the thermal design")


def test_starts_at_the_first_sentence_about_the_role_without_a_heading():
    text = (f"{BLURB}\nWe celebrate different perspectives and foster an inclusive culture.\n"
            "As a Mechanical Engineer at Acme, you will design enclosures and cooling for our battery packs.")
    assert summarise(text, "Mechanical Engineer").startswith("As a Mechanical Engineer at Acme, you will")


def test_a_sentence_naming_the_title_counts_as_about_the_role():
    text = (f"{BLURB}\nAnalytical Laboratory Technician\n"
            "The Analytical Lab Technician performs routine chemical analysis in support of production quality.")
    summary = summarise(text, "Analytical Laboratory Technician")
    assert summary.startswith("The Analytical Lab Technician performs")


def test_a_label_and_text_on_one_line():
    text = f"{BLURB}\nJob Summary: A highly motivated Accountant I is sought to support manufacturing operations."
    assert summarise(text, "Accountant I").startswith("A highly motivated Accountant I is sought")


def test_a_generic_heading_followed_by_the_company_paragraph_is_passed_over():
    text = ("Job Description Summary\n"
            "Acme Storage is accelerating the path to a cleaner grid, helping our customers keep the lights on.\n"
            "What you’ll do\n"
            "Troubleshoot and repair mechanical, electrical and electronic equipment across the facility.\n"
            "Perform preventive maintenance on production equipment\n")
    summary = summarise(text, "Maintenance Technician")
    assert summary.startswith("Troubleshoot and repair")
    # List items without a full stop are joined with a semicolon.
    assert "facility. Perform preventive maintenance" in summary or "; Perform" in summary


def test_company_sections_are_never_the_start_even_when_they_speak_to_the_reader():
    text = ("About Us\nAt Acme Storage, you will love working with people who care.\n"
            "Why we come to work:\nYou’ll enjoy the satisfaction of being part of a team making a change.\n"
            "Essential Responsibilities:\nLead commercial activities across assigned customer accounts.")
    assert summarise(text, "Key Account Manager").startswith("Lead commercial activities")


def test_where_and_how_the_job_is_done_is_not_the_start():
    text = ("Work arrangement: Please note that this role is based in Missouri or within commuting distance.\n"
            "Responsibilities\nBuild and maintain relationships with utility customers in the region.")
    assert summarise(text, "Account Manager").startswith("Build and maintain relationships")


def test_without_anything_role_like_the_company_paragraph_is_still_skipped():
    text = f"{BLURB}\nDesign test fixtures for cells and modules, and keep the lab running smoothly."
    assert summarise(text, "Engineer").startswith("Design test fixtures")


def test_falls_back_to_the_top_when_the_whole_posting_is_about_the_company():
    summary = summarise(BLURB)
    assert summary.startswith("Acme Storage is a leading developer")


def test_keeps_the_employers_own_characters_and_length():
    text = f"{BLURB}\nWhat you’ll do\nYou’ll design power stages. " + "You will test them. " * 60
    summary = summarise(text, "Power Electronics Engineer")
    assert summary.startswith("You’ll design power stages.")
    assert len(summary) <= MAX_LENGTH


def test_the_role_sentence_leads_so_a_200_character_cut_shows_it():
    text = (f"{BLURB}\nOur values guide everything we do.\nAbout the Role\n"
            "You will lead bring-up of new inverter boards and own their validation plans.\n"
            "Responsibilities\nWrite test plans\nRun HALT\n{EEO}")
    assert "You will lead bring-up of new inverter boards" in summarise(text, "Hardware Engineer")[:200]
    assert "equal opportunity" not in summarise(text, "Hardware Engineer")
