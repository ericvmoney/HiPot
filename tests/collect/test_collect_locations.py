"""Location, metro and workplace rules, including agreement with the old hub's tags."""
from __future__ import annotations

import pytest

from pipeline.collect.locations import (
    decide_workplace, is_remote_only, metro_for, metros_for, parse_location, split_locations,
    structured_location, workplace_from_text, workplace_from_title,
)
from pipeline.io import ROOT, load_json, load_yaml

SEED = load_json(ROOT / "data" / "seed" / "jobs.json")["jobs"]


def parsed(text: str) -> dict:
    found = parse_location(text)
    assert found.pop("text") == text.strip()
    return found


@pytest.mark.parametrize("text,expected", [
    ("Berkeley, CA", {"city": "Berkeley", "state": "CA", "country": "US"}),
    ("San Jose, CA ", {"city": "San Jose", "state": "CA", "country": "US"}),
    ("Pratt, Kansas", {"city": "Pratt", "state": "KS", "country": "US"}),
    ("Denver, CO - US", {"city": "Denver", "state": "CO", "country": "US"}),
    ("San Mateo, California, United States", {"city": "San Mateo", "state": "CA", "country": "US"}),
    ("South San Francisco, California, USA", {"city": "South San Francisco", "state": "CA", "country": "US"}),
    ("Mountain View, California (HQ)", {"city": "Mountain View", "state": "CA", "country": "US"}),
    ("Berkeley, CA (hybrid)", {"city": "Berkeley", "state": "CA", "country": "US"}),
    ("South San Francisco - Onsite", {"city": "South San Francisco", "state": "CA", "country": "US"}),
    ("Menlo Park Hybrid", {"city": "Menlo Park", "state": "CA", "country": "US"}),
    ("Fremont Office", {"city": "Fremont", "state": "CA", "country": "US"}),
    ("US-CA-Campbell-254", {"city": "Campbell", "state": "CA", "country": "US"}),
    ("San Jose CA", {"city": "San Jose", "state": "CA", "country": "US"}),
    ("14902 Grant Street, #120, Thornton CO 80023", {"city": "Thornton", "state": "CO", "country": "US"}),
    ("Washington, DC", {"city": "Washington", "state": "DC", "country": "US"}),
    ("St. Landry, LA", {"city": "St. Landry", "state": "LA", "country": "US"}),
    ("Boston", {"city": "Boston", "state": "MA", "country": "US"}),
    ("Palo Alto", {"city": "Palo Alto", "state": "CA", "country": "US"}),
    # A state or a country alone
    ("California", {"state": "CA", "country": "US"}),
    ("United States", {"country": "US"}),
    ("San Francisco Bay Area, California, United States", {"state": "CA", "country": "US"}),
    # Remote entries name no place
    ("Remote", {}),
    ("Remote, USA", {"country": "US"}),
    ("USA - Remote", {"country": "US"}),
    ("US remote (Michigan)", {"state": "MI", "country": "US"}),
    ("Remote - Colorado", {"state": "CO", "country": "US"}),
    # Outside the US
    ("Toronto, ON, Canada", {"city": "Toronto", "state": "ON", "country": "CA"}),
    ("Berlin, Germany", {"city": "Berlin", "country": "DE"}),
    ("London, England, United Kingdom", {"city": "London", "country": "GB"}),
    ("Greater Toronto Area, ON, Canada", {}),
    # Not confident: text only
    ("Cambridge", {}),          # Massachusetts or England
    ("Golden", {}),
    ("Madrid", {}),
    ("486 S. Pierce Ave, Suite E", {}),
    ("Region: TOLA", {}),
])
def test_parse_location(text, expected):
    assert parsed(text) == expected


@pytest.mark.parametrize("text,expected", [
    ("Berkeley, CA", ["Berkeley, CA"]),
    ("Carlsbad, CA; Remote", ["Carlsbad, CA", "Remote"]),
    ("Golden, CO, Houston, TX, Oakland, CA", ["Golden, CO", "Houston, TX", "Oakland, CA"]),
    ("Emeryville, or Santa Clara, California", ["Emeryville", "Santa Clara, California"]),
    ("Boston or Remote", ["Boston", "Remote"]),
    ("Denver, CO / Remote", ["Denver, CO", "Remote"]),
    ("Carson City, NV; San Francisco, California, United States",
     ["Carson City, NV", "San Francisco, California, United States"]),
    ("Remote; remote", ["Remote"]),
    ("", []),
    (None, []),
])
def test_split_locations(text, expected):
    assert split_locations(text) == expected


@pytest.mark.parametrize("text,metro", [
    ("Sunnyvale, CA", "sf-bay-area"),
    ("Palo Alto", "sf-bay-area"),                       # a bare city from BARE_CITIES
    ("Fremont Office", "sf-bay-area"),
    ("San Francisco Bay Area, California, United States", "sf-bay-area"),   # a region the lookup knows
    ("Carlsbad, CA", "san-diego"),
    ("Thornton, CO", "denver"),
    ("Worcester, MA", "boston"),
    ("Weirton, WV", "pittsburgh-pa"),
    ("Long Island, NY", "new-york-ny"),
    ("Austin, TX", "austin-tx"),
    # The same city name in another state is that state's metro, not the old hub's
    ("Richmond, VA", "richmond-va"),
    ("Newark, NJ", "new-york-ny"),
    ("Henderson, NV", "las-vegas-nv"),
    ("Aurora, IL", "chicago-il"),
    # Outside the US, or no place at all
    ("Brisbane, Australia", None),
    ("Cambridge, UK", None),
    ("San Jose, Costa Rica", None),
    ("Toronto, ON, Canada", None),
    ("Remote", None),
    ("Remote, USA", None),
    ("Remote - Colorado", None),                        # a state alone is not a metro
    ("California", None),
    ("Cambridge", None),                                # no state: not guessed
    ("Region: TOLA", None),
])
def test_metro_for(text, metro):
    assert metro_for(parse_location(text)) == metro


def test_every_metro_is_a_taxonomy_id():
    known = {entry["id"] for entry in load_yaml(ROOT / "taxonomy.yml")["metros"]}
    found = set()
    for job in SEED:
        found |= set(metros_for([parse_location(piece) for piece in split_locations(_seed_text(job))]))
    assert found and found <= known


def test_metros_for_several_places():
    locations = [parse_location(piece) for piece in split_locations("Golden, CO, Houston, TX, Oakland, CA")]
    assert metros_for(locations) == ["denver", "houston-tx", "sf-bay-area"]


def _seed_text(job: dict) -> str:
    return "; ".join(location["text"] for location in job["locations"])


OLD_HUB_METROS = {"sf-bay-area", "san-diego", "denver", "boston"}

# Seed rows where the shared Census lookup and the old hub's four regions part
# ways, with the metros the collector now gives. Everything else must agree.
KNOWN_DIFFERENCES = {
    # Census draws these as their own areas; the old hub filed them under Denver or the Bay Area.
    "Fort Collins, CO": ["fort-collins-co"],
    "Fort Collins, CO; Windsor, CO": ["fort-collins-co"],
    "Loveland, CO": ["fort-collins-co"],
    "Berthoud, Colorado": ["fort-collins-co"],   # hand-mapped to Larimer County
    "Petaluma, CA": ["santa-rosa-ca"],
    # Henderson CO and Franklin MA were pinned here as unmapped until the
    # supervisor added them to the place lookup; they now agree with the old hub.
    # The old hub cut these strings short ("Cali", "United State"), so the second place cannot be read.
    "Reno, Nevada, United States; Sunnyvale, Californ": ["reno-nv"],
    "Reno, Nevada, United States; San Francisco, Cali": ["reno-nv"],
    "Carson City, NV; San Francisco, California, Unit": ["reno-nv"],
    "McCarran, NV; San Francisco, California, United": ["reno-nv"],
    "San Francisco Bay Area, California, United State": [],
}


def test_metros_agree_with_the_old_hub_apart_from_known_differences():
    """The old hub's region tags, restricted to its four metros, still hold everywhere else."""
    seen = set()
    for job in SEED:
        text = _seed_text(job)
        metros = metros_for([parse_location(piece) for piece in split_locations(text)])
        if text in KNOWN_DIFFERENCES:
            seen.add(text)
            assert metros == KNOWN_DIFFERENCES[text], text
        else:
            assert sorted(set(metros) & OLD_HUB_METROS) == job["metros"], text
    assert seen == set(KNOWN_DIFFERENCES)


def test_remote_agrees_with_the_old_hub_except_where_its_text_was_cut_short():
    # Three seed rows cannot agree: two had their location text truncated before
    # the word "remote", and one hand-entered row says "(remote)" while its tag
    # does not.
    disagreements = [
        _seed_text(job) for job in SEED
        if (workplace_from_text(_seed_text(job)) == "remote") != (job["workplace"] == "remote")
        and workplace_from_text(_seed_text(job)) != "hybrid"
    ]
    assert sorted(set(disagreements)) == [
        "Boston, Massachusetts, United States; Las Vegas",
        "Littleton, CO; San Diego, CA; Franklin, MA (remote)",
    ]
    assert len(disagreements) == 3


@pytest.mark.parametrize("text,expected", [
    ("Remote", "remote"),
    ("US remote", "remote"),
    ("Carlsbad, CA; Remote (Remote, US)", "remote"),
    ("San Jose CA or possible remote considered", "remote"),
    ("Berkeley, CA (hybrid)", "hybrid"),
    ("Remote / Hybrid", "hybrid"),
    ("South San Francisco - Onsite", "onsite"),
    ("Berkeley, CA", "unknown"),
    ("Not remote; Denver, CO", "unknown"),
    ("", "unknown"),
])
def test_workplace_from_text(text, expected):
    assert workplace_from_text(text) == expected


@pytest.mark.parametrize("title,expected", [
    ("Senior Firmware Engineer (Remote)", "remote"),
    ("Field Service Technician - Remote", "remote"),
    ("Account Executive, Remote - US", "remote"),
    ("Controls Engineer (Hybrid)", "hybrid"),
    ("Remote Operations Center Engineer", "unknown"),
    ("Remote Sensing Scientist", "unknown"),
    ("Senior Controls Engineer", "unknown"),
])
def test_workplace_from_title(title, expected):
    assert workplace_from_title(title) == expected


def test_a_feed_field_wins_over_the_location_text():
    assert decide_workplace("onsite", ["Remote"], "Engineer (Remote)") == "onsite"
    assert decide_workplace(None, ["Remote, USA"], "Engineer") == "remote"
    assert decide_workplace(None, ["Austin, TX"], "Engineer (Remote)") == "remote"
    assert decide_workplace(None, ["Austin, TX"], "Engineer") == "unknown"
    assert decide_workplace("sometimes", ["Austin, TX"], "Engineer") == "unknown"


def test_structured_location_prefers_feed_fields_and_fills_gaps_from_text():
    assert structured_location("Palo Alto", "Palo Alto", "California", "United States") == {
        "text": "Palo Alto", "city": "Palo Alto", "state": "CA", "country": "US"}
    # The feed gave only a country; the text supplies the city and state.
    assert structured_location("San Antonio, TX", None, None, "United States") == {
        "text": "San Antonio, TX", "city": "San Antonio", "state": "TX", "country": "US"}
    assert structured_location("Remote (USA)", None, None, "USA") == {"text": "Remote (USA)", "country": "US"}
    assert structured_location("Toronto", "Toronto", "Ontario", "Canada") == {
        "text": "Toronto", "city": "Toronto", "state": "ON", "country": "CA"}
    # Text and feed disagree on the country: nothing is taken from the text.
    assert structured_location("London, UK", None, None, "United States") == {"text": "London, UK", "country": "US"}


def test_is_remote_only():
    assert is_remote_only(parse_location("Remote, USA"))
    assert not is_remote_only(parse_location("Remote - Colorado"))
    assert not is_remote_only(parse_location("Austin, TX"))


# Remote places as boards wrote them in the live runs of 2026-11-24/25 (Workday,
# iCIMS, Ashby and others). Each says which country the remote work is in, so
# the board can tell US-remote from remote elsewhere.
@pytest.mark.parametrize("text,expected", [
    ("United Kingdom - Remote", {"country": "GB"}),          # Canadian Solar, Workday
    ("England - Remote", {"country": "GB"}),
    ("Wales, UK - Remote", {"country": "GB"}),
    ("Canada - Remote", {"country": "CA"}),
    ("CA Remote - Ontario", {"state": "ON", "country": "CA"}),
    ("Germany - Remote", {"country": "DE"}),
    ("Remote - India", {"country": "IN"}),
    ("US - Remote", {"country": "US"}),
    ("Remote (United States)", {"country": "US"}),
    ("Remote, USA", {"country": "US"}),
    ("Remote - IN", {"state": "IN", "country": "US"}),       # SOLV Energy: Indiana, not India
    ("Remote - CA", {"state": "CA", "country": "US"}),
    ("US-CA-Remote", {"state": "CA", "country": "US"}),      # iCIMS
    ("Home Office (MT)", {"state": "MT", "country": "US"}),
    ("Remote", {}),                                          # no country given: left unknown
])
def test_remote_places_carry_their_country(text, expected):
    found = parse_location(text)
    assert {key: value for key, value in found.items() if key != "text"} == expected


@pytest.mark.parametrize("text,expected", [
    ("Germany - Hamburg", {"city": "Hamburg", "country": "DE"}),      # was read as Spain
    ("United Kingdom - London", {"city": "London", "country": "GB"}),
    ("United Kingdom - Northern Ireland", {"country": "GB"}),
])
def test_workday_country_dash_place(text, expected):
    found = parse_location(text)
    assert {key: value for key, value in found.items() if key != "text"} == expected
