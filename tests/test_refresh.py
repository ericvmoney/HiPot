"""The daily refresh: steps in order, a stop at the first failure, and the lock."""
from __future__ import annotations

import os
import subprocess
from types import SimpleNamespace

from tools import refresh


def test_steps_run_in_order_and_stop_at_the_first_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(refresh, "ROOT", tmp_path)
    calls = []

    def runner(args, cwd, stdout, stderr):
        calls.append(args[3] if args[2] == "-m" else args)   # the module name
        assert args[1] == "-u" and stderr is subprocess.STDOUT
        return SimpleNamespace(returncode=1 if args[3] == "pipeline.tag" else 0)

    result = refresh.run(refresh.STEPS, tmp_path / "logs" / "r.log", runner=runner)
    assert calls == ["pipeline.collect", "pipeline.tag"]
    assert result["status"] == "failed at tag" and [s["exit"] for s in result["steps"]] == [0, 1]
    assert "===== collect" in (tmp_path / "logs" / "r.log").read_text(encoding="utf-8")


def test_all_steps_pass(tmp_path, monkeypatch):
    monkeypatch.setattr(refresh, "ROOT", tmp_path)
    result = refresh.run(refresh.STEPS, tmp_path / "r.log", runner=lambda *a, **k: SimpleNamespace(returncode=0))
    assert result["status"] == "ok" and [s["step"] for s in result["steps"]] == ["collect", "tag", "validate", "publish", "shared"]
    # The shared build leaves pay grades out and writes outside site/, which the local board serves.
    shared = dict(refresh.STEPS)["shared"]
    assert "--no-grades" in shared and str(refresh.SHARED / "board.json") in shared


def test_the_lock_keeps_a_second_refresh_out_until_it_goes_stale(tmp_path):
    lock = tmp_path / "state" / "refresh.lock"
    assert refresh.take_lock(lock) is True
    assert refresh.take_lock(lock) is False
    old = lock.stat().st_mtime - (refresh.LOCK_STALE_HOURS * 3600 + 60)
    os.utime(lock, (old, old))
    assert refresh.take_lock(lock) is True       # left over from a run that died


def test_everything_it_writes_is_ignored_by_git():
    # data/state/ is git-ignored: the log, the lock, the status and the shared build never get committed.
    for path in (refresh.LOGS, refresh.LOCK, refresh.STATUS, refresh.SHARED):
        assert path.is_relative_to(refresh.STATE)
    assert "data/state/" in (refresh.ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
