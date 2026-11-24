"""The Rippling reader against two trimmed real postings (recorded 2026-11-24)."""
from __future__ import annotations

import copy

import pytest
from collect_helpers import FIXTURES, FakeFetcher

from pipeline.collect import fetch, rippling
from pipeline.collect.fetch import Blocked, FetchError
from pipeline.io import load_json

LIST = "https://api.rippling.com/platform/api/ats/v1/board/aptera/jobs"
FIRST = "f056cda4-2893-414b-8eb9-14f7dcb790cf"
SECOND = "b166d73d-8607-4708-8b32-a5f53b115f7b"


def test_asks_for_the_list_then_each_posting(fetcher):
    rippling.read("aptera", fetcher)
    assert fetcher.calls == [(LIST, None), (f"{LIST}/{FIRST}", None), (f"{LIST}/{SECOND}", None)]


def test_fields(fetcher):
    drafts = {made["posting_id"]: made for made in rippling.read("aptera", fetcher)}
    made = drafts[FIRST]
    assert made["title"] == "Sr DRE, Electrical Systems Packaging"
    assert made["url"] == f"https://ats.rippling.com/aptera/jobs/{FIRST}"
    assert made["locations"] == [{"text": "Carlsbad, CA", "city": "Carlsbad", "state": "CA", "country": "US"}]
    assert made["workplace"] is None                   # no workplace field; the location rules decide
    assert made["employment"] == "full-time"           # from the code SALARIED_FT
    assert made["pay"] is None                         # payRangeDetails is empty on this board
    assert made["posted_date"] == "2026-09-21"         # createdOn, in the board's own time zone
    assert made["department"] == "R+D"
    text = made["description_text"]
    assert text.startswith("Aptera Motors") and "<" not in text and "&amp;" not in text
    assert drafts[SECOND]["department"] == "1410 Engineering"


def test_a_posting_listed_once_per_location_is_read_once():
    listing = load_json(FIXTURES / "rippling_aptera.json")
    second_place = copy.deepcopy(listing[0])
    second_place["workLocation"] = {"label": "Remote (United States)", "id": "Remote (United States)"}
    fetcher = FakeFetcher(extra={LIST: listing + [second_place]},
                          failures={f"{LIST}/{FIRST}": FetchError("HTTP 500")})
    drafts = rippling.read("aptera", fetcher)
    assert [made["posting_id"] for made in drafts] == [FIRST, SECOND]
    assert [url for url, _ in fetcher.calls].count(f"{LIST}/{FIRST}") == 1
    # The detail failed, so the list's locations are used, both of them.
    assert [location["text"] for location in drafts[0]["locations"]] == ["Carlsbad, CA", "Remote (United States)"]


def test_a_failed_detail_keeps_the_posting_from_the_list():
    fetcher = FakeFetcher(failures={f"{LIST}/{FIRST}": FetchError("timed out after 30s (ReadTimeout)")})
    made = rippling.read("aptera", fetcher)[0]
    assert made["title"] == "Sr DRE, Electrical Systems Packaging"
    assert made["department"] == "R+D" and made["locations"][0]["city"] == "Carlsbad"
    assert made["description_text"] == "" and made["posted_date"] is None and made["employment"] == "unknown"


def test_a_refused_detail_blocks_the_company():
    fetcher = FakeFetcher(failures={f"{LIST}/{FIRST}": Blocked("HTTP 429 from api.rippling.com")})
    with pytest.raises(Blocked):
        rippling.read("aptera", fetcher)
    assert len(fetcher.calls) == 2                     # nothing asked after the refusal


def test_an_answer_that_is_not_a_list_is_an_error():
    with pytest.raises(ValueError, match="expected a list"):
        rippling.read("aptera", FakeFetcher(extra={LIST: {"error_code": "RESOURCE_NOT_FOUND"}}))


@pytest.mark.parametrize("kind,expected", [
    ({"label": "SALARIED_FT", "id": "Salaried, full-time"}, "full-time"),
    ({"label": "HOURLY_FT", "id": "Hourly, full-time"}, "full-time"),
    ({"label": "HOURLY_PT", "id": "Hourly, part-time"}, "part-time"),
    ({"label": "INTERN", "id": "Intern"}, "intern"),
    ({"label": "TEMP", "id": "Temporary"}, "contract"),
    ({"label": "CONTRACTOR", "id": "Contractor"}, "contract"),
    ({"label": "", "id": "Full time"}, "full-time"),
    (None, "unknown"),
])
def test_employment_codes(kind, expected):
    assert rippling.employment(kind) == expected


def test_pay_from_pay_range_details():
    # Shape as third-party write-ups report it; this board publishes none.
    ranges = [
        {"location": "Carlsbad, CA", "currency": "USD", "frequency": "MONTH", "rangeStart": 9000, "rangeEnd": 11000},
        {"location": "Carlsbad, CA", "currency": "USD", "frequency": "YEAR", "rangeStart": 150000, "rangeEnd": 190000, "isRemote": False},
    ]
    assert rippling.pay(ranges) == {"min": 150000, "max": 190000, "currency": "USD", "period": "year", "basis": "feed"}
    assert rippling.pay([{"currency": "USD", "frequency": "HOUR", "rangeStart": 28, "rangeEnd": 34}])["period"] == "hour"
    assert rippling.pay([]) is None and rippling.pay(None) is None


def test_the_rippling_host_is_asked_at_most_every_six_seconds():
    import httpx

    class Clock:
        now, sleeps = 0.0, []

        def __call__(self):
            return self.now

        def sleep(self, seconds):
            self.sleeps.append(seconds)
            self.now += seconds

    clock = Clock()
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=[])))
    fetcher = fetch.Fetcher(client=client, clock=clock, sleep=clock.sleep)
    fetcher.get_json(LIST)
    fetcher.get_json(f"{LIST}/{FIRST}")
    fetcher.get_json("https://api.lever.co/v0/postings/lightship")
    fetcher.get_json("https://api.lever.co/v0/postings/other")
    assert clock.sleeps == [6.0, 1.0]
