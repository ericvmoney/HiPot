"""Polite HTTP access to public job-board feeds.

The rules, which have no exceptions:

  * one request at a time (the collector is single-threaded), and at least
    MIN_INTERVAL seconds between two requests to the same host;
  * a timeout on every request;
  * a generic User-Agent that names neither the project nor a person;
  * HTTP 403 or 429 means the host refused us: raise Blocked and let the caller
    move on. A block is never retried and never worked around.

A transport failure or a 5xx answer is retried once after a pause. That is the
only retry there is.
"""
from __future__ import annotations

import json
import time
from typing import Any, Callable
from urllib.parse import urlsplit

import httpx

USER_AGENT = "job-feed-reader/0.1 (python-httpx)"
MIN_INTERVAL = 1.0
TIMEOUT = 30.0
RETRY_WAIT = 5.0
BLOCK_STATUSES = (403, 429)


class FetchError(Exception):
    """The request failed or the answer could not be used."""


class Blocked(FetchError):
    """The host refused the request (HTTP 403 or 429)."""


class Fetcher:
    """Fetches JSON, spacing requests to each host."""

    def __init__(
        self,
        client: httpx.Client | None = None,
        min_interval: float = MIN_INTERVAL,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._client = client or httpx.Client(
            timeout=TIMEOUT,
            follow_redirects=False,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        )
        self._min_interval = min_interval
        self._clock = clock
        self._sleep = sleep
        self._last: dict[str, float] = {}
        self.requests = 0

    def close(self) -> None:
        self._client.close()

    def _wait_for(self, host: str) -> None:
        last = self._last.get(host)
        if last is not None:
            remaining = self._min_interval - (self._clock() - last)
            if remaining > 0:
                self._sleep(remaining)

    def _get(self, url: str, params: dict | None) -> httpx.Response:
        host = urlsplit(url).netloc.lower()
        self._wait_for(host)
        try:
            return self._client.get(url, params=params)
        finally:
            # Counted from the end of the request, so a slow answer still
            # leaves a full interval before the next one.
            self._last[host] = self._clock()
            self.requests += 1

    def get_json(self, url: str, params: dict | None = None) -> Any:
        """GET a URL and return its parsed JSON body."""
        response = None
        for attempt in (1, 2):
            try:
                response = self._get(url, params)
            except httpx.TimeoutException as error:
                failure = f"timed out after {TIMEOUT:g}s ({type(error).__name__})"
            except httpx.HTTPError as error:
                failure = f"request failed ({type(error).__name__}: {error})"
            else:
                if response.status_code in BLOCK_STATUSES:
                    raise Blocked(f"HTTP {response.status_code} from {urlsplit(url).netloc}")
                if response.status_code < 500:
                    break
                failure = f"HTTP {response.status_code}"
            if attempt == 2:
                raise FetchError(failure)
            self._sleep(RETRY_WAIT)

        if response.status_code == 404:
            raise FetchError("HTTP 404: no board at this address (wrong or retired board token)")
        if response.status_code != 200:
            raise FetchError(f"HTTP {response.status_code}")
        try:
            return response.json()
        except ValueError as error:
            raise FetchError(f"answer was not JSON ({error})") from error


def record_name(url: str) -> str:
    """File name for a saved answer: host and path, made safe for a file system."""
    parts = urlsplit(url)
    safe = "".join(ch if ch.isalnum() or ch in "-." else "_" for ch in parts.netloc + parts.path)
    return safe.strip("_") + ".json"


class RecordingFetcher(Fetcher):
    """A Fetcher that also saves every answer under a directory.

    The saved files are raw feed answers for building test fixtures and for
    re-running the collector offline with ReplayFetcher. The directory used by
    the command line, data/fixtures-live/, is ignored by git.
    """

    def __init__(self, directory, **kwargs) -> None:
        super().__init__(**kwargs)
        self._directory = directory
        directory.mkdir(parents=True, exist_ok=True)

    def get_json(self, url: str, params: dict | None = None) -> Any:
        data = super().get_json(url, params)
        with open(self._directory / record_name(url), "w", encoding="utf-8", newline="\n") as handle:
            json.dump(data, handle, ensure_ascii=False)
        return data


class ReplayFetcher:
    """Answers from files saved by RecordingFetcher. Makes no network request."""

    def __init__(self, directory) -> None:
        self._directory = directory
        self.requests = 0

    def close(self) -> None:
        pass

    def get_json(self, url: str, params: dict | None = None) -> Any:
        path = self._directory / record_name(url)
        if not path.exists():
            raise FetchError(f"no saved answer for {url}")
        self.requests += 1
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
