"""Count US-remote roles on companies' own job boards. Used by the A2 company scout for the 'remote' region.

Reads every company with a Greenhouse, Lever, Ashby or Rippling board from companies.yml and from the
scout's proposal files, loads each board's public feed once, and records how many roles are US-remote
(location text says remote or anywhere, or the feed marks the role remote, and no non-US country is
named), how many of those have engineering or technical titles, and a few sample titles.

Polite in the same way as probe_boards.py: one request at a time per host, at least 1.2 s apart
(6 s for Rippling, as the collector does), a generic client name, and a host that answers 401, 403 or
429 is not asked again.

    uv run python data/screening/tools/remote_scan.py out.json [extra proposal files...]
"""
from __future__ import annotations

import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent))
import probe_boards as pb  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
READERS = {"greenhouse", "lever", "ashby", "rippling"}


def companies(paths: list[Path]) -> list[dict]:
    seen, out = set(), []
    for path in paths:
        for c in (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("companies", []):
            ats = c.get("ats") or {}
            if ats.get("type") in READERS and ats.get("board") and c["id"] not in seen:
                seen.add(c["id"])
                out.append({"id": c["id"], "name": c["name"], "system": ats["type"], "token": ats["board"],
                            "hq": c.get("hq"), "file": path.name,
                            "listed": c["climate"]["tier"] in ("core", "enabling") and c["startup"]["status"] == "in"})
    return out


def main() -> int:
    target = Path(sys.argv[1])
    paths = [ROOT / "companies.yml"] + [Path(p) for p in sys.argv[2:]]
    rows = companies(paths)
    done = json.loads(target.read_text(encoding="utf-8")) if target.exists() else {}
    fetcher = pb.Fetcher()
    lock = threading.Lock()
    rippling_lock = threading.Lock()

    def work(row):
        if row["id"] in done:
            return
        if row["system"] == "rippling":
            with rippling_lock:  # 6 s apart on Rippling
                result = pb.probe(fetcher, row["system"], row["token"], row["name"])
                threading.Event().wait(4.8)
        else:
            result = pb.probe(fetcher, row["system"], row["token"], row["name"])
        keep = {k: result.get(k) for k in ("status", "open_roles", "remote_us_roles", "remote_us_engineering",
                                           "remote_titles", "board_name", "sample_locations")}
        with lock:
            done[row["id"]] = {**row, **keep}
            target.write_text(json.dumps(done, indent=1, ensure_ascii=False), encoding="utf-8")
        print(f"{row['id']}: {keep.get('open_roles')} roles, {keep.get('remote_us_roles')} US-remote", flush=True)

    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(work, rows))
    if fetcher.refused:
        done["_refused_hosts"] = fetcher.refused
        target.write_text(json.dumps(done, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"{len(rows)} boards; refused hosts: {fetcher.refused}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
