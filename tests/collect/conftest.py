from __future__ import annotations

import pytest
from collect_helpers import FakeFetcher


@pytest.fixture(autouse=True)
def keep_real_state_untouched(tmp_path, monkeypatch):
    """Tests that call main() write their run history and careers state here,
    never to data/state/."""
    from pipeline.collect import careers, run
    monkeypatch.setattr(run, "DEFAULT_RUNS", tmp_path / "runs.json")
    monkeypatch.setattr(careers, "STATE_PATH", tmp_path / "careers.json")


@pytest.fixture
def fetcher() -> FakeFetcher:
    return FakeFetcher()
