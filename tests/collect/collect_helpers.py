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
