from __future__ import annotations

import pytest
from collect_helpers import FakeFetcher


@pytest.fixture
def fetcher() -> FakeFetcher:
    return FakeFetcher()
