"""Shared file helpers for the pipeline and tools."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]


class _Loader(yaml.SafeLoader):
    """SafeLoader that leaves dates as strings.

    The schemas describe dates as strings, so `2026-11-23` must not turn into
    a `datetime.date` on load.
    """


_Loader.yaml_implicit_resolvers = {
    key: [(tag, regexp) for tag, regexp in resolvers if tag != "tag:yaml.org,2002:timestamp"]
    for key, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


def load_yaml(path: Path | str) -> Any:
    with open(path, encoding="utf-8") as handle:
        return yaml.load(handle, Loader=_Loader)


def dump_yaml(data: Any, path: Path | str, header: str = "") -> None:
    body = yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=110)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(header + body)


def load_json(path: Path | str) -> Any:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def dump_json(data: Any, path: Path | str, compact: bool = False) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        if compact:
            json.dump(data, handle, ensure_ascii=False, separators=(",", ":"))
        else:
            json.dump(data, handle, ensure_ascii=False, indent=1)
        handle.write("\n")
