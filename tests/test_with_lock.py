from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WITH_LOCK = str(ROOT / "tools" / "with_lock.sh")


def run_pair(tmp: Path, locked: bool) -> list[str]:
    """Start two overlapping runs that log their start and end; return the log."""
    log = tmp / "log"
    script = f'echo start >> "{log}"; sleep 0.4; echo end >> "{log}"'
    command = ["sh", WITH_LOCK, str(tmp / "lock"), "sh", "-c", script] if locked else ["sh", "-c", script]
    first = subprocess.Popen(command)
    time.sleep(0.1)
    second = subprocess.Popen(command)
    assert first.wait(timeout=10) == 0 and second.wait(timeout=10) == 0
    return log.read_text().split()


def test_lock_serialises_overlapping_runs(tmp_path: Path) -> None:
    assert run_pair(tmp_path, locked=True) == ["start", "end", "start", "end"]
    assert not (tmp_path / "lock").exists()


def test_bait_runs_without_the_lock_interleave(tmp_path: Path) -> None:
    assert run_pair(tmp_path, locked=False) == ["start", "start", "end", "end"]


def test_exit_status_is_kept_and_lock_released(tmp_path: Path) -> None:
    result = subprocess.run(["sh", WITH_LOCK, str(tmp_path / "lock"), "sh", "-c", "exit 3"], check=False)
    assert result.returncode == 3
    assert not (tmp_path / "lock").exists()


def test_stale_lock_left_by_a_killed_run_is_removed(tmp_path: Path) -> None:
    lock = tmp_path / "lock"
    lock.mkdir()
    two_hours_ago = time.time() - 7200
    os.utime(lock, (two_hours_ago, two_hours_ago))
    env = {**os.environ, "STALE_MINUTES": "1"}
    result = subprocess.run(["sh", WITH_LOCK, str(lock), "true"], env=env, timeout=10, check=False)
    assert result.returncode == 0 and not lock.exists()
