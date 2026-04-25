"""Atomic, lock-guarded PID file management for the daemon.

# pattern: Imperative Shell (file I/O, fcntl locking, signal probing)

Provides a small API that pairs an exclusively-flocked PID file with atomic
writes. Intended usage:

    lock = pid_file.acquire(path)     # raises AlreadyRunningError on live peer
    try:
        ... run daemon ...
    finally:
        pid_file.release(lock)

The returned `PidLock` owns an open file descriptor whose fcntl lock is the
authoritative single-instance guard. Dropping the object releases the lock;
an explicit `release()` also unlinks the file.
"""

from __future__ import annotations

import fcntl
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO


class AlreadyRunningError(RuntimeError):
    """Raised when another daemon instance holds the PID file lock."""

    def __init__(self, path: Path, live_pid: int) -> None:
        super().__init__(f"daemon already running (pid={live_pid}) at {path}")
        self.path = path
        self.live_pid = live_pid


@dataclass
class PidLock:
    """Holds an open, flocked file descriptor for the PID file's lifetime."""

    path: Path
    handle: TextIO


def is_process_alive(pid: int) -> bool:
    """Return True iff a process with this PID is alive.

    Uses signal 0 probe semantics; ESRCH means no such process (dead),
    EPERM means the process exists but we lack permission (treat as alive).
    """
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def read_pid(path: Path) -> int | None:
    """Return the PID stored in `path`, or None if missing or malformed."""
    try:
        raw = path.read_text().strip()
    except FileNotFoundError:
        return None
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def acquire(path: Path) -> PidLock:
    """Open and exclusively flock the PID file, then write our PID atomically.

    Raises AlreadyRunningError if another live process holds the lock.
    Handles stale PID files (crashed prior daemon) by reclaiming the lock.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
    handle: TextIO = os.fdopen(fd, "r+")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        # Another process holds the lock. Read the PID to report it.
        existing = handle.read().strip()
        handle.close()
        try:
            live_pid = int(existing)
        except ValueError:
            live_pid = -1
        raise AlreadyRunningError(path, live_pid) from None

    # Lock acquired. Write our PID atomically (temp + replace) so readers
    # never see a half-written file even under concurrent status polls.
    # Atomic replace creates a new inode; re-open and re-lock the new inode
    # so the lifetime-scoped guard points at the live file.
    _atomic_write_pid(path, os.getpid())
    handle.close()
    fd = os.open(path, os.O_RDWR)
    handle = os.fdopen(fd, "r+")
    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    return PidLock(path=path, handle=handle)


def release(lock: PidLock) -> None:
    """Release the fcntl lock, close the handle, and unlink the PID file."""
    try:
        fcntl.flock(lock.handle.fileno(), fcntl.LOCK_UN)
    except OSError:
        pass
    try:
        lock.handle.close()
    except OSError:
        pass
    try:
        lock.path.unlink()
    except FileNotFoundError:
        pass


def _atomic_write_pid(path: Path, pid: int) -> None:
    """Write `pid` to `path` atomically via temp-file + rename."""
    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".pid-tmp-", dir=parent)
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(f"{pid}\n")
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except (OSError, FileNotFoundError):
            pass
        raise
