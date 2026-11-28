"""One full refresh of the board's data, start to finish, for the daily schedule.

    uv run python -m tools.refresh              # collect, tag, validate, publish, shared build
    uv run python -m tools.refresh --skip-collect   # reuse today's data/jobs.raw.json

Steps, each a separate process, stopping at the first that fails:
  1. collect   pipeline.collect (about 3 hours; network)
  2. tag       pipeline.tag
  3. validate  tools.validate on the raw and tagged files
  4. publish   pipeline.publish, the local board with pay grades
  5. shared    pipeline.publish into data/state/shared-build/, the copy for the shared artifact (grades included, decision 27)

Every step's output goes to data/state/logs/refresh-<date>.log, unbuffered, so the
log shows progress as it happens. The result, with the board's counts, is written to
data/state/refresh-latest.json, which the 11:00 publishing task reads (HANDOVER.md
section 4). A lock file stops two refreshes (or a refresh and a hand-run collection
started through this script) from writing the same files at once; a lock older than
LOCK_STALE_HOURS is taken to be left over from a run that died.

Exit status: 0 when every step passed, 1 when a step failed, 2 when another refresh
holds the lock.

Scheduling it daily at 05:00 on Windows (PowerShell, as the signed-in user, no admin;
set up 2026-11-27 at 08:00, moved to 05:00 on 2026-11-28; see HANDOVER.md section 4):

    $uv = (Get-Command uv).Source
    $action = New-ScheduledTaskAction -Execute $uv -Argument "run python -m tools.refresh" -WorkingDirectory "C:\\HiPot"
    $trigger = New-ScheduledTaskTrigger -Daily -At 5:00AM
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
        -ExecutionTimeLimit (New-TimeSpan -Hours 8) -MultipleInstances IgnoreNew
    Register-ScheduledTask -TaskName "HiPot daily refresh" -Action $action -Trigger $trigger -Settings $settings
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from pipeline.io import ROOT

STATE = ROOT / "data" / "state"
LOGS = STATE / "logs"
LOCK = STATE / "refresh.lock"
STATUS = STATE / "refresh-latest.json"
SHARED = STATE / "shared-build"
LOCK_STALE_HOURS = 8

STEPS = [
    ("collect", ["-m", "pipeline.collect"]),
    ("tag", ["-m", "pipeline.tag"]),
    ("validate", ["-m", "tools.validate", "--raw", "data/jobs.raw.json", "--jobs", "data/jobs.json"]),
    ("publish", ["-m", "pipeline.publish"]),
    # Pay grades are public since 2026-11-27 (decision 27); the shared build is the same as the local one,
    # written outside site/ so the published files come from one finished run.
    ("shared", ["-m", "pipeline.publish", "--out", str(SHARED / "board.json")]),
]


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def take_lock(lock: Path = LOCK, clock=time.time) -> bool:
    """Create the lock file; False when a fresh one already exists."""
    lock.parent.mkdir(parents=True, exist_ok=True)
    if lock.exists() and clock() - lock.stat().st_mtime < LOCK_STALE_HOURS * 3600:
        return False
    lock.write_text(now(), encoding="utf-8")
    return True


def board_counts(path: Path) -> dict:
    try:
        board = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {"roles": len(board.get("roles", [])),
            "companies_hiring": len({role["co"] for role in board.get("roles", [])}),
            "generated_at": board.get("generated_at")}


def run(steps, log: Path, runner=subprocess.run) -> dict:
    """Run the steps in order into one log; the result says which passed and where it stopped."""
    result = {"started": now(), "steps": [], "status": "ok", "log": str(log.relative_to(ROOT))}
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as out:
        for name, args in steps:
            out.write(f"\n===== {name} ({now()}) =====\n")
            out.flush()
            began = time.time()
            code = runner([sys.executable, "-u", *args], cwd=ROOT, stdout=out, stderr=subprocess.STDOUT).returncode
            result["steps"].append({"step": name, "exit": code, "minutes": round((time.time() - began) / 60, 1)})
            if code != 0:
                result["status"] = f"failed at {name}"
                break
    result["finished"] = now()
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--skip-collect", action="store_true", help="reuse data/jobs.raw.json from an earlier collection")
    args = parser.parse_args(argv)

    if not take_lock():
        print(f"Another refresh holds {LOCK.relative_to(ROOT)} (started {LOCK.read_text(encoding='utf-8')}).", file=sys.stderr)
        return 2
    try:
        steps = [s for s in STEPS if not (args.skip_collect and s[0] == "collect")]
        log = LOGS / f"refresh-{datetime.now().strftime('%Y-%m-%d')}.log"
        result = run(steps, log)
        if result["status"] == "ok":
            result["board"] = board_counts(SHARED / "board.json")
            result["shared_build"] = str(SHARED.relative_to(ROOT))
        STATUS.write_text(json.dumps(result, indent=1), encoding="utf-8")
        print(json.dumps(result, indent=1))
        return 0 if result["status"] == "ok" else 1
    finally:
        LOCK.unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(main())
