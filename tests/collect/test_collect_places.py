"""Location reading for roles the board put outside every metro area (2026-11-28).

The texts are the shapes found on the boards; the postings are synthetic.
"""
from __future__ import annotations

import pytest

from pipeline.collect import careers, workday
from pipeline.collect.locations import decide_workplace, fill_from_board, metros_for, parse_location, place_at_start


def parsed(text: str) -> dict:
    return {key: value for key, value in parse_location(text).items() if key != "text"}


def us(city: str | None, state: str) -> dict:
    return {**({"city": city} if city else {}), "state": state, "country": "US"}


@pytest.mark.parametrize("text, expected, metro", [
    # The state written without a comma, before or after the city
    ("Wilmington NC USA", us("Wilmington", "NC"), "wilmington-nc"),
    ("OH - Pataskala", us("Pataskala", "OH"), "columbus-oh"),
    ("NJ Edison", us("Edison", "NJ"), "new-york-ny"),
    ("PA Turtle Creek", us("Turtle Creek", "PA"), "pittsburgh-pa"),
    ("Brighton Colorado", us("Brighton", "CO"), "denver"),
    ("San Diego CA Renewable Group", us("San Diego", "CA"), "san-diego"),
    ("Lafayette, IN Manufacturing Facility", us("Lafayette", "IN"), "lafayette-in"),
    # Workday site codes: region and country codes, then a number
    ("Roanoke US VA 3", us("Roanoke", "VA"), "roanoke-va"),
    ("Niskayuna VERNOVA NY US 3", us("Niskayuna", "NY"), "albany-ny"),
    # More than a place in the name: the place the lookup knows
    ("Dynapower South Burlington, VT", us("South Burlington", "VT"), "burlington-vt"),
    ("Santa Fe Springs - Clark St., CA, USA", us("Santa Fe Springs", "CA"), "los-angeles-ca"),
    ("Uptown Charlotte, NC", us("Charlotte", "NC"), "charlotte-nc"),
    ("Milpitas Ames, California", us("Milpitas", "CA"), "sf-bay-area"),
    ("Los Angeles East, California", us("Los Angeles", "CA"), "los-angeles-ca"),
    ("Service Center - Dayton, OH", us("Dayton", "OH"), "dayton-oh"),
    ("Hydrogen Plant, St. Gabriel, LA", us("St. Gabriel", "LA"), "baton-rouge-la"),
    ("This will be an in-person role located in Detroit, MI", us("Detroit", "MI"), "detroit-mi"),
    ("Greater Boston (Woburn, MA) – On-site/Hybrid", us("Woburn", "MA"), "boston"),
    ("Riverside, ca, CA, United States", us("Riverside", "CA"), "los-angeles-ca"),
    # Neighbourhoods and townships added to the place lookup
    ("Research Triangle Park, NC", us("Research Triangle Park", "NC"), "raleigh-nc"),
    ("Charlestown, MA", us("Charlestown", "MA"), "boston"),
    # A place name is never cut where its words belong together
    ("Big Spring, TX", us("Big Spring", "TX"), None),
    ("Garden City, TX", us("Garden City", "TX"), None),
    # A ZIP code alone says nothing more
    ("CA, US, 95131", us(None, "CA"), None),
])
def test_us_places(text, expected, metro):
    assert parsed(text) == expected
    assert metros_for([parse_location(text)]) == ([metro] if metro else [])


@pytest.mark.parametrize("text, expected", [
    ("Charleroi USA", {"country": "US"}),                # no state: left unknown, not guessed
    ("Hyderabad TS IN 26", {"city": "Hyderabad", "country": "IN"}),
    ("Chennai TN IN 5", {"city": "Chennai", "country": "IN"}),
    ("Swansea GB 1", {"city": "Swansea", "country": "GB"}),
    ("CA - Toronto", {}),                                # not California
    ("San Francisco Bay Area, California, United States", us(None, "CA")),   # a region stays a region
])
def test_other_places(text, expected):
    assert parsed(text) == expected


def test_place_at_the_start_of_a_careers_page():
    assert place_at_start("< Back Account Director Apply Now San Francisco, CA, USA Job Type Full Time") == {
        "text": "San Francisco, CA", "city": "San Francisco", "state": "CA", "country": "US"}
    assert place_at_start("De-Ice | Careers | Aerospace Engineer | Boston , Massachusetts About")["city"] == "Boston"
    assert place_at_start("Per F. Peterson, PhD, University of California Berkeley") is None
    assert place_at_start("About us. " + "x" * 400 + " Boston, MA") is None         # too far down to be the posting's place
    assert place_at_start("Moses Lake, WA. Build batteries.") is None              # outside every metro: not taken from text


def test_careers_postings_without_a_place_take_it_from_their_text():
    draft = {"posting_id": "p1", "title": "Engineer", "locations": [],
             "description_text": "Engineer Malden, MA, USA Job Type Full-time"}
    assert careers._unique([draft])[0]["locations"][0]["city"] == "Malden"


def posting(locations: list[str], description: str = "", country: str | None = "US") -> dict:
    found = [parse_location(text) for text in locations]
    if country and len(found) == 1 and "country" not in found[0]:
        found[0]["country"] = country
    return {"locations": found, "description_text": description}


def test_a_board_settles_its_sites_state():
    drafts = [posting(["Greenville"], "Join our team in Greenville, SC."), posting(["Greenville"]),
              posting(["Schenectady", "Greenville"])]
    fill_from_board(drafts)
    assert all(next(l for l in d["locations"] if l["text"] == "Greenville") == {
        "text": "Greenville", "city": "Greenville", "state": "SC", "country": "US"} for d in drafts)
    assert drafts[2]["locations"][0] == {"text": "Schenectady"}          # nothing on the board says where


def test_a_board_that_disagrees_settles_nothing():
    drafts = [posting(["Greenville"], "Greenville, SC"), posting(["Greenville"], "Greenville, NC")]
    fill_from_board(drafts)
    assert all("state" not in d["locations"][0] for d in drafts)


def test_a_board_gives_a_site_its_country():
    drafts = [posting(["Pallavaram"], country="IN"), posting(["Noida", "Pallavaram"]),
              posting(["Stafford"], country="GB"), posting(["Stafford"], "Stafford, VA", country=None)]
    fill_from_board(drafts)
    assert drafts[1]["locations"][1] == {"text": "Pallavaram", "city": "Pallavaram", "country": "IN"}
    assert drafts[3]["locations"][0] == {"text": "Stafford", "city": "Stafford", "country": "GB"}  # not Virginia


def test_workday_country_wins_over_the_text():
    india = {"location": "Chennai, IN", "country": {"descriptor": "India"},
             "jobRequisitionLocation": {"country": {"descriptor": "India", "alpha2Code": "IN"}}}
    assert workday._locations(india, None) == [{"text": "Chennai, IN", "city": "Chennai", "country": "IN"}]
    us_site = {"location": "Greenville", "additionalLocations": ["Bengaluru"], "country": {"descriptor": "United States of America"}}
    assert workday._locations(us_site, None)[0] == {"text": "Greenville", "country": "US"}   # no state invented
    nowhere = {"country": {"descriptor": "Japan"}, "jobRequisitionLocation": {"country": {"alpha2Code": "JP"}}}
    assert workday._locations(nowhere, None) == [{"text": "Japan", "country": "JP"}]


def test_a_list_of_remote_places_is_remote():
    remote = ["Remote - CO", "Remote - CA", "Remote - TX"]
    assert decide_workplace("hybrid", remote, "Engineer") == "remote"
    assert decide_workplace("hybrid", ["Remote - CO"], "Engineer") == "hybrid"     # one entry: the feed decides
    assert decide_workplace("onsite", ["Remote - CO", "Denver, CO"], "Engineer") == "onsite"
