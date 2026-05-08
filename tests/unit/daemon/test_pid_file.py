"""Tests for PID file lifecycle and double-start detection."""

import os
from pathlib import Path

import pytest

from local_library.daemon import pid_file


def _unused_pid() -> int:
    """Return a PID that is guaranteed not to be in use.

    On macOS and Linux, PID 1 is init and always present; we pick a large
    value unlikely to be in use and verify it's dead before returning.
    """
    candidate = 999_999
    try:
        os.kill(candidate, 0)
    except ProcessLookupError:
        return candidate
    raise RuntimeError("unexpected: PID 999999 is alive")


def test_acquire_writes_current_pid(tmp_path: Path) -> None:
    path = tmp_path / "daemon.pid"
    lock = pid_file.acquire(path)
    try:
        assert path.read_text().strip() == str(os.getpid())
    finally:
        pid_file.release(lock)


def test_release_removes_file(tmp_path: Path) -> None:
    path = tmp_path / "daemon.pid"
    lock = pid_file.acquire(path)
    pid_file.release(lock)
    assert not path.exists()


def test_double_acquire_raises(tmp_path: Path) -> None:
    path = tmp_path / "daemon.pid"
    lock = pid_file.acquire(path)
    try:
        with pytest.raises(pid_file.AlreadyRunningError):
            pid_file.acquire(path)
    finally:
        pid_file.release(lock)


def test_stale_pid_is_reclaimed(tmp_path: Path) -> None:
    path = tmp_path / "daemon.pid"
    stale = _unused_pid()
    path.write_text(str(stale))
    # No lock held on the file — simulates a crashed prior daemon.
    lock = pid_file.acquire(path)
    try:
        assert path.read_text().strip() == str(os.getpid())
    finally:
        pid_file.release(lock)


def test_is_process_alive_true_for_self() -> None:
    assert pid_file.is_process_alive(os.getpid()) is True


def test_is_process_alive_false_for_unused() -> None:
    assert pid_file.is_process_alive(_unused_pid()) is False


def test_read_pid_returns_none_when_missing(tmp_path: Path) -> None:
    assert pid_file.read_pid(tmp_path / "missing.pid") is None


def test_read_pid_returns_none_when_malformed(tmp_path: Path) -> None:
    path = tmp_path / "daemon.pid"
    path.write_text("not-a-pid\n")
    assert pid_file.read_pid(path) is None


def test_read_pid_returns_integer(tmp_path: Path) -> None:
    path = tmp_path / "daemon.pid"
    path.write_text("12345\n")
    assert pid_file.read_pid(path) == 12345
