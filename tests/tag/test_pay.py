"""Pay found in the posting text. Synthetic text, modelled on the shapes the
real feeds use; no posting is copied."""
from __future__ import annotations

import pytest

from pipeline.tag.pay import pay_from_text, plausible


def pay(text):
    return pay_from_text(text)


def year(low, high, currency="USD"):
    return {"min": low, "max": high, "currency": currency, "period": "year", "basis": "posting-text"}


def hour(low, high, currency="USD"):
    return {"min": low, "max": high, "currency": currency, "period": "hour", "basis": "posting-text"}


@pytest.mark.parametrize("text,expected", [
    ("Salary range: $160,000 to $195,000.", year(160000, 195000)),
    ("The base pay range for this role is $120,000 - $150,000 per year.", year(120000, 150000)),
    ("Salary Range: $142,000 USD - $170,000 USD\nSalary Basis: Annual", year(142000, 170000)),
    ("Compensation: $120k-$150k base.", year(120000, 150000)),
    ("Base salary: $120-150k depending on experience.", year(120000, 150000)),
    ("Base salary: $180,000–$205,000 annually.", year(180000, 205000)),
    ("Initial base salary range = $140,000.00 - $170,000.00", year(140000, 170000)),
    ("Pay range: USD 95,000 - 120,000", year(95000, 120000)),
    ("The salary range for this role in Canada is CA$110,000 - CA$135,000.", year(110000, 135000, "CAD")),
])
def test_annual_ranges(text, expected):
    assert pay(text) == expected


@pytest.mark.parametrize("text,expected", [
    ("Salary Range: $35-41/hr\nSalary Basis: Hourly", hour(35, 41)),
    ("The pay for this position ranges from $45.00 to $60.00 per hour, depending on experience.", hour(45, 60)),
    ("Initial Base Hourly Rate Range: $26.00 - $34.00", hour(26, 34)),
    ("The salary range, $30.00 to $35.00, reflects the target new hire hourly rate.", hour(30, 35)),
    ("We are targeting an hourly pay between $40/hr - $55/hr.", hour(40, 55)),
    ("Hourly rate: $28.50 - $32.25", hour(29, 32)),     # rounded half up to whole dollars
])
def test_hourly_ranges(text, expected):
    assert pay(text) == expected


def test_single_hourly_figures():
    assert pay("This position offers an hourly pay rate of $21.00 per hour.") == hour(21, 21)
    assert pay("Benefits\n- Pay: $23\n- Advance your career") == hour(23, 23)
    # Several stated figures (by degree, by location): lowest to highest stated.
    assert pay("Hourly pay during the internship:\nUndergraduate intern: $25/hr\nMasters intern: $30/hr\n"
               "PhD intern: $35/hr") == hour(25, 35)
    # Without any word saying these are pay, a bare list of rates is not read.
    assert pay("Undergraduate intern: $25/hr\nMasters intern: $30/hr") is None


def test_several_ranges_by_location_take_the_widest():
    text = ("San Jose, CA - $172,800 - $216,000 per year\n"
            "Arlington, TX - $138,200 - $172,800 per year\n"
            "Remote - $120,000 - $175,000 per year")
    assert pay(text) == year(120000, 175000)


def test_widest_range_wins_over_a_target_band_inside_it():
    text = "Base salary: $180,000–$205,000 annually, with a target range of approximately $190,000–$195,000."
    assert pay(text) == year(180000, 205000)


def test_hourly_list_under_a_benefits_heading():
    text = "Benefits\n- Wireman: $32/hr - $37hr.\n- Journeyman: $37/hr - $39/hr.\n- Advance your career"
    assert pay(text) == hour(32, 37)


# Cases that must return nothing.
@pytest.mark.parametrize("text", [
    "",
    "We offer a competitive salary and great benefits.",
    "Annual bonus of $10,000 - $20,000 based on performance.",
    "Sign-on bonus: $5,000 - $10,000.",
    "Relocation assistance of $5,000 to $15,000 is available.",
    "Equity grant valued at $50,000 - $80,000.",
    "We have raised over $900M so far from incredible investors.",
    "With over $160 million in funding and partnerships across critical industries.",
    "Our customers save $2,000 - $5,000 per year on energy bills.",
    "Projects range from $1 million to $10 million.",
    "Reimbursement for home internet, up to AUD $85 per month.",
    "A stipend of $3,000 - $4,000 per month for housing.",
    "401(k) match up to $6,000 per year.",
    "Tuition reimbursement up to $5,250 per year.",
    "Salary: starting from $120,000.",                  # a floor, not a range
    "Pay: up to $45 per hour.",                         # a ceiling
    "The salary range estimate is $130,000,000-$160,000 USD.",   # malformed: low above high
    "We are targeting a base pay between $160,00.00 - $235,000.00.",  # malformed figure
    "Compensation: 120,000 - 150,000",                  # no currency stated
    "The range for this role is $5 - $6.",              # too small for an hourly rate
    "Work 4-10 hours per week, 2 - 3 days a week.",
])
def test_returns_nothing(text):
    assert pay(text) is None


def test_feed_pay_plausibility():
    assert plausible({"min": 120000, "max": 150000, "currency": "USD", "period": "year", "basis": "feed"})
    assert plausible({"min": 25, "max": 35, "currency": "USD", "period": "hour", "basis": "feed"})
    # Hourly figures labelled annual, as one feed delivered them.
    assert not plausible({"min": 23, "max": 25, "currency": "USD", "period": "year", "basis": "feed"})
    assert not plausible(None)
