"""Shared helpers for the collector tests. Nothing here touches the network."""
from __future__ import annotations

from pathlib import Path

from pipeline.collect.fetch import FetchError
from pipeline.io import load_json

FIXTURES = Path(__file__).parent / "fixtures"

# Feed address -> fixture file. The fixtures are real answers recorded on
# 2026-11-24 and trimmed: a few postings per board, descriptions shortened.
ADDRESSES = {
    "https://boards-api.greenhouse.io/v1/boards/antora/jobs": "greenhouse_antora.json",
    "https://boards-api.greenhouse.io/v1/boards/pacificfusion/jobs": "greenhouse_pacificfusion.json",
    "https://boards-api.greenhouse.io/v1/boards/redwoodmaterials/jobs": "greenhouse_redwoodmaterials.json",
    "https://api.lever.co/v0/postings/lightship": "lever_lightship.json",
    "https://api.lever.co/v0/postings/mainspringenergy": "lever_mainspringenergy.json",
    "https://api.ashbyhq.com/posting-api/job-board/Ridealso": "ashby_Ridealso.json",
    "https://api.ashbyhq.com/posting-api/job-board/formenergy": "ashby_formenergy.json",
    "https://api.ashbyhq.com/posting-api/job-board/span": "ashby_span.json",
    "https://api.ashbyhq.com/posting-api/job-board/base-power": "ashby_base-power.json",
    "https://api.rippling.com/platform/api/ats/v1/board/aptera/jobs": "rippling_aptera.json",
    "https://apply.workable.com/api/v1/widget/accounts/anthro": "workable_anthro.json",
    "https://lunaroutpost.bamboohr.com/careers/list": "bamboohr_lunaroutpost_list.json",
    "https://api.smartrecruiters.com/v1/companies/EnPowerInc/postings?limit=100&offset=0": "smartrecruiters_EnPowerInc.json",
    "https://fastned.recruitee.com/api/offers/": "recruitee_fastned.json",
    "https://greenerpowersolutions.recruitee.com/api/offers/": "recruitee_greenerpowersolutions.json",
    "https://zeno-power.breezy.hr/json": "breezy_zeno-power.json",
}
# Feeds that answer in XML or HTML rather than JSON.
TEXT_ADDRESSES = {
    "https://app.jazz.co/feeds/export/jobs/coreshelltech": "jazzhr_coreshelltech.xml",
}
# Readers that make one request per posting ({base}/{posting}): these answers
# are keyed by posting id (a uuid on Rippling). Postings with no recorded detail
# get a 404, which exercises each reader's fallback.
RIPPLING_DETAILS = {
    "https://api.rippling.com/platform/api/ats/v1/board/aptera/jobs": "rippling_aptera_details.json",
    "https://api.smartrecruiters.com/v1/companies/EnPowerInc/postings": "smartrecruiters_EnPowerInc_details.json",
}
# BambooHR asks .../careers/{id}/detail; these answers are keyed by posting id.
# Only one detail was recorded, so the other posting exercises the fallback.
BAMBOOHR_DETAILS = {
    "https://lunaroutpost.bamboohr.com/careers": "bamboohr_lunaroutpost_details.json",
}


class FakeFetcher:
    """Serves fixtures by address and records what was asked for."""

    def __init__(self, extra: dict | None = None, failures: dict | None = None) -> None:
        self.extra = extra or {}
        self.failures = failures or {}
        self.calls: list[tuple[str, dict | None]] = []
        self.requests = 0

    def get_json(self, url: str, params: dict | None = None):
        self.calls.append((url, params))
        self.requests += 1
        if url in self.failures:
            raise self.failures[url]
        if url in self.extra:
            return self.extra[url]
        if url in ADDRESSES:
            return load_json(FIXTURES / ADDRESSES[url])
        if url.endswith("/detail"):
            base, _, posting = url[: -len("/detail")].rpartition("/")
            if base in BAMBOOHR_DETAILS:
                details = load_json(FIXTURES / BAMBOOHR_DETAILS[base])
                if posting in details:
                    return details[posting]
        base, _, uuid = url.rpartition("/")
        if base in RIPPLING_DETAILS:
            details = load_json(FIXTURES / RIPPLING_DETAILS[base])
            if uuid in details:
                return details[uuid]
        raise FetchError(f"HTTP 404: no fixture for {url}")

    def get_text(self, url: str, params: dict | None = None) -> str:
        self.calls.append((url, params))
        self.requests += 1
        if url in self.failures:
            raise self.failures[url]
        if url in self.extra:
            return self.extra[url]
        if url in TEXT_ADDRESSES:
            return (FIXTURES / TEXT_ADDRESSES[url]).read_text(encoding="utf-8")
        raise FetchError(f"HTTP 404: no fixture for {url}")

    def close(self) -> None:
        pass


def company(company_id: str, ats: str, board: str | None, tier: str = "core", status: str = "in") -> dict:
    return {
        "id": company_id, "name": company_id, "ats": {"type": ats, "board": board}, "read": "auto",
        "sectors": [], "stage": None,
        "climate": {"tier": tier, "reason": "test", "basis": "provisional", "approved": False},
        "startup": {"status": status, "reason": None},
    }
