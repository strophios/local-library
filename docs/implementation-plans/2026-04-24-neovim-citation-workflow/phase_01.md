# Neovim Citation Workflow Implementation Plan — Phase 1: Daemon Scaffolding

**Goal:** Stand up a runnable Python daemon process with a CLI (`start`/`stop`/`status`/`restart`/`run`), PID-file-guarded single-instance enforcement, asyncio Unix-socket echo server, and an FD-inheritance shim that forward-compats launchd socket activation — without any JSON-RPC semantics yet.

**Architecture:** A new `src/local_library/daemon/` package (`pid_file.py`, `socket_activation.py`, `server.py`) plus `src/local_library/cli/daemon.py` for the Typer subcommand group. The asyncio event loop owns the listening socket, signal handlers, and a Phase-1-only echo handler that Phase 2 replaces with the JSON-RPC dispatch loop. Lifecycle scaffolding — PID lock, socket unlink on shutdown, SIGTERM/SIGINT routing — is stable for the rest of the daemon's life.

**Tech Stack:** Python 3.10+, asyncio, `psutil` (new dep), `fcntl` (stdlib), Typer (existing), `platformdirs` (existing via `config.py`).

**Scope:** 1 of 7 phases from `docs/design-plans/2026-04-24-neovim-citation-workflow.md`.

**Codebase verified:** 2026-04-24.

**Known platform constraint (Darwin AF_UNIX):** Darwin's `AF_UNIX` socket `sun_path` field is limited to ~104 bytes. pytest's default `tmp_path` fixture creates nested temporary directories under `/private/var/folders/.../pytest-of-<user>/pytest-<version>/test_<name>/<N>/`, and appending a socket filename (e.g., `daemon.sock`) often exceeds this limit, causing `OSError: AF_UNIX path too long` on any test that calls `socket.bind(str(path))` or `asyncio.start_unix_server(..., path=str(path))` against `tmp_path`. The established workaround is the `short_tmp_path` fixture in `tests/unit/daemon/conftest.py`, which uses `tempfile.mkdtemp(prefix="ll-d-")` to create a directory in `/tmp` with a short path. This constraint affects Task 5 (asyncio echo server tests), Task 7 (end-to-end lifecycle integration test), and Phase 3 Task 5 (end-to-end socket test for search and get_document). The constraint was discovered during Phase 1 Task 4 (commit `a26044d` introduced an overly broad `--basetemp` workaround; commit `6735b47` corrected it with the scoped fixture). Future tasks that bind sockets to `tmp_path` should import and use `short_tmp_path` from `tests/unit/daemon/conftest.py`.

**Executor skills:** Invoke `ed3d-house-style:coding-effectively` (required; pulls in FCIS + defense-in-depth), `astral:uv`, `astral:ruff`, `ed3d-plan-and-execute:test-driven-development` for the functionality tasks, and `ed3d-plan-and-execute:verification-before-completion` before marking any task done.

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->

<!-- START_TASK_1 -->
## Task 1: Add daemon dependencies and config path helpers

**Type:** Infrastructure + small functional addition (config helpers + tests).

**Files:**
- Modify: `pyproject.toml` (add `psutil` dep; add `local-library-daemon` script entry)
- Modify: `src/local_library/config.py` (append three path helpers + update `ensure_directories`)
- Create: `tests/unit/test_config_daemon_paths.py`

### Step 1: Add `psutil` dependency and daemon entry point

Append to `pyproject.toml` `[project]` `dependencies = [...]` list — locate the existing `platformdirs` entry and add `psutil>=5.9.0` immediately after (alphabetical order preserved).

Under `[project.scripts]`, add a new line after `local-library-mcp`:

```toml
local-library-daemon = "local_library.daemon.server:main"
```

### Step 2: Run `uv sync` to verify dependency resolution

```bash
uv sync --extra dev
```

Expected: new `psutil` install logged; no errors. Do **not** yet try to invoke `local-library-daemon` — the target module doesn't exist.

### Step 3: Add config path helpers

Append to `src/local_library/config.py` after the existing `get_*` helpers but before `ensure_directories`:

```python
def get_daemon_pid_path() -> Path:
    """Path to the daemon PID file (data dir)."""
    return get_data_dir() / "daemon.pid"


def get_socket_path() -> Path:
    """Path to the daemon's Unix domain socket (data dir)."""
    return get_data_dir() / "daemon.sock"


def get_daemon_log_dir() -> Path:
    """Directory for daemon log files (data dir / logs)."""
    return get_data_dir() / "logs"
```

Then update the existing `ensure_directories` body to include:

```python
    get_daemon_log_dir().mkdir(parents=True, exist_ok=True)
```

(Alongside the existing `mkdir` calls. The socket path's parent is already ensured via `get_data_dir()`, and the PID file's parent is likewise the data dir.)

### Step 4: Write tests

Create `tests/unit/test_config_daemon_paths.py`:

```python
"""Unit tests for daemon-related config path helpers."""

from pathlib import Path

from local_library import config


def test_get_daemon_pid_path_under_data_dir() -> None:
    pid_path = config.get_daemon_pid_path()
    assert isinstance(pid_path, Path)
    assert pid_path.parent == config.get_data_dir()
    assert pid_path.name == "daemon.pid"


def test_get_socket_path_under_data_dir() -> None:
    sock_path = config.get_socket_path()
    assert sock_path.parent == config.get_data_dir()
    assert sock_path.name == "daemon.sock"


def test_get_daemon_log_dir_under_data_dir() -> None:
    log_dir = config.get_daemon_log_dir()
    assert log_dir.parent == config.get_data_dir()
    assert log_dir.name == "logs"


def test_ensure_directories_creates_log_dir(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(config, "get_data_dir", lambda: tmp_path)
    config.ensure_directories()
    assert (tmp_path / "logs").is_dir()
```

### Step 5: Run tests

```bash
uv run pytest tests/unit/test_config_daemon_paths.py -v
```

Expected: all 4 tests pass.

### Step 6: Lint + format

```bash
uv run ruff check src/local_library/config.py tests/unit/test_config_daemon_paths.py
uv run ruff format src/local_library/config.py tests/unit/test_config_daemon_paths.py
```

### Step 7: Commit

```bash
git add pyproject.toml uv.lock src/local_library/config.py tests/unit/test_config_daemon_paths.py
git commit -m "feat(daemon): add config paths and psutil dep for daemon scaffolding

Adds get_daemon_pid_path, get_socket_path, get_daemon_log_dir to config.py;
registers psutil dependency and local-library-daemon script entry."
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
## Task 2: Create daemon package skeleton

**Type:** Infrastructure.

**Files:**
- Create: `src/local_library/daemon/__init__.py`
- Create: `src/local_library/daemon/CLAUDE.md` (seed — completed in Phase 7)
- Create: `tests/unit/daemon/__init__.py`

### Step 1: Create package `__init__.py`

`src/local_library/daemon/__init__.py`:

```python
"""Long-running daemon wrapping the Library orchestrator as a socket service.

Exposes a Unix-domain-socket JSON-RPC 2.0 server over the existing Library,
keeping the embedder and sqlite-vec connection warm in memory for sub-500 ms
warm search latency.
"""

# pattern: Imperative Shell (asyncio, sockets, Library lifecycle)
```

### Step 2: Create seed CLAUDE.md

`src/local_library/daemon/CLAUDE.md`:

```markdown
# Daemon Domain

Last verified: 2026-04-24

## Purpose

Long-running process that wraps the `Library` orchestrator as a Unix-domain-socket
service, keeping the embedding model and sqlite-vec connection warm so downstream
clients (Neovim plugin today; future MCP v2) see sub-500 ms warm search latency.

This seed is updated per phase; Phase 7 marks it complete.

## Contracts

- **Exposes:** Unix-domain-socket endpoint at `config.get_socket_path()`, serving
  line-delimited JSON-RPC 2.0 (protocol specified in Phase 2).
- **Guarantees (Phase 1 only):** A single-instance daemon process can be started,
  stopped, and queried for status via the `local-library daemon <subcommand>` CLI.
  The socket echoes bytes during Phase 1; JSON-RPC semantics arrive in Phase 2.
- **Expects:** The existing `Library` orchestrator (wired in Phase 3).

## Dependencies

- **Uses:** `asyncio` (event loop), `psutil` (resident memory for status),
  `fcntl` (PID file locking), `platformdirs` via `config.py`.
- **Used by:** `cli/daemon.py` (process management commands), Phase 4+ Neovim plugin.
- **Boundary:** Read-only library access service. Does not touch bibliography
  files, project state, or editor context — those belong to the plugin.

## Key Decisions

- **Single event loop + single `Library` instance + single sqlite-vec connection.**
  Blocking model inference (Phase 3) will be wrapped in `run_in_executor`;
  sqlite-vec calls stay on the loop thread (see Phase 3 CLAUDE.md additions).
- **CLI-managed process lifecycle for MVP.** launchd socket-activation is
  scaffolded (env-var-based FD inheritance hook in Phase 1) but not wired.
- **Python 3.10 compatibility.** Socket cleanup is manual (no `cleanup_socket=True`).

## Invariants

- PID file is exclusive-locked for the lifetime of the process; if the lock
  cannot be acquired at startup, a live peer is assumed and startup refuses.
- On clean shutdown (SIGTERM/SIGINT): server closed → socket file unlinked →
  PID file unlocked and removed → process exits 0.

## Key Files

- `server.py` — asyncio server + main() entry point + signal handling
- `pid_file.py` — atomic PID write + stale-detection + fcntl lock
- `socket_activation.py` — launchd FD-inheritance shim (env-var-based stub)
- (Phase 2+) `protocol.py`, `dispatcher.py`, `errors.py` — JSON-RPC layer

## Gotchas

- On Python <3.13, `asyncio.start_unix_server` does not unlink the socket file
  when the server closes; shutdown code must do it explicitly.
- Never use `os.umask` in daemon code (changes global process state); set
  socket file perms via `os.chmod(path, 0o600)` post-bind instead.
```

### Step 3: Create tests package marker

`tests/unit/daemon/__init__.py`: empty file.

### Step 4: Verify package imports

```bash
uv run python -c "import local_library.daemon; print(local_library.daemon.__doc__.splitlines()[0])"
```

Expected output: `Long-running daemon wrapping the Library orchestrator as a socket service.`

### Step 5: Commit

```bash
git add src/local_library/daemon/__init__.py src/local_library/daemon/CLAUDE.md tests/unit/daemon/__init__.py
git commit -m "feat(daemon): add package skeleton and CLAUDE.md seed"
```
<!-- END_TASK_2 -->

<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 3-5) -->

<!-- START_TASK_3 -->
## Task 3: PID file module (TDD)

**Type:** Functionality. Uses the TDD cycle from `ed3d-plan-and-execute:test-driven-development`.

**Files:**
- Create: `tests/unit/daemon/test_pid_file.py`
- Create: `src/local_library/daemon/pid_file.py`

### Step 1: Write failing tests

`tests/unit/daemon/test_pid_file.py`:

```python
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
```

### Step 2: Run tests, confirm they fail

```bash
uv run pytest tests/unit/daemon/test_pid_file.py -v
```

Expected: ImportError for `local_library.daemon.pid_file` on every test.

### Step 3: Implement `pid_file.py`

`src/local_library/daemon/pid_file.py`:

```python
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
```

### Step 4: Run tests, confirm they pass

```bash
uv run pytest tests/unit/daemon/test_pid_file.py -v
```

Expected: 9 tests pass.

### Step 5: Lint + format

```bash
uv run ruff check src/local_library/daemon/pid_file.py tests/unit/daemon/test_pid_file.py
uv run ruff format src/local_library/daemon/pid_file.py tests/unit/daemon/test_pid_file.py
```

### Step 6: Commit

```bash
git add src/local_library/daemon/pid_file.py tests/unit/daemon/test_pid_file.py
git commit -m "feat(daemon): atomic PID file with flock-guarded single-instance check

Introduces pid_file.acquire/release with AlreadyRunningError on live peer,
stale-PID reclamation, and atomic write via tempfile + os.replace. Doubles
fcntl.flock(LOCK_EX|LOCK_NB) as belt-and-suspenders against PID reuse races."
```
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
## Task 4: Socket activation shim (TDD)

**Type:** Functionality.

**Files:**
- Create: `tests/unit/daemon/test_socket_activation.py`
- Create: `src/local_library/daemon/socket_activation.py`

### Step 1: Write failing tests

`tests/unit/daemon/test_socket_activation.py`:

```python
"""Tests for the launchd FD-inheritance shim."""

import socket

import pytest

from local_library.daemon import socket_activation


def test_returns_none_when_env_var_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(socket_activation.ACTIVATION_ENV_VAR, raising=False)
    assert socket_activation.inherited_socket() is None


def test_returns_none_when_env_var_malformed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(socket_activation.ACTIVATION_ENV_VAR, "not-an-int")
    assert socket_activation.inherited_socket() is None


def test_returns_socket_when_env_var_points_at_valid_fd(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent, child = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        monkeypatch.setenv(socket_activation.ACTIVATION_ENV_VAR, str(child.fileno()))
        inherited = socket_activation.inherited_socket()
        assert inherited is not None
        assert inherited.family == socket.AF_UNIX
        inherited.close()
    finally:
        parent.close()
        child.close()


def test_returns_none_when_fd_invalid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(socket_activation.ACTIVATION_ENV_VAR, "999999")
    assert socket_activation.inherited_socket() is None


def test_bind_listen_unlinks_stale_file(tmp_path) -> None:
    path = tmp_path / "daemon.sock"
    path.touch()  # pre-existing stale file
    sock = socket_activation.bind_listen(path)
    try:
        assert path.is_socket()
        assert (path.stat().st_mode & 0o777) == 0o600
    finally:
        sock.close()
        path.unlink(missing_ok=True)


def test_bind_listen_creates_parent(tmp_path) -> None:
    path = tmp_path / "subdir" / "daemon.sock"
    sock = socket_activation.bind_listen(path)
    try:
        assert path.is_socket()
    finally:
        sock.close()
        path.unlink(missing_ok=True)
```

### Step 2: Run tests, confirm they fail

```bash
uv run pytest tests/unit/daemon/test_socket_activation.py -v
```

Expected: ImportError.

### Step 3: Implement `socket_activation.py`

`src/local_library/daemon/socket_activation.py`:

```python
"""Socket acquisition: launchd FD inheritance with manual-bind fallback.

# pattern: Imperative Shell (socket I/O, env inspection)

When the daemon runs under a future launchd LaunchAgent, launchd will
pre-bind the socket and hand us a file descriptor. For Phase 1 there is no
launchd wiring; the shim still exists as the single code path for acquiring
the listening socket, so the launchd upgrade is a packaging change — not a
code change.

The shim supports two activation modes:

1. **Env-var FD inheritance** (Phase 1, testable today): caller — typically
   a wrapper script or a future test harness — pre-binds a socket and passes
   the integer FD in the `LAUNCH_ACTIVATE_SOCKET_FD` environment variable.

2. **Native launchd `launch_activate_socket`** (TODO — activated when we
   migrate to a LaunchAgent plist with a `Sockets` key). The real API lives
   in `<launch.h>` and requires a ctypes binding against libc. See
   docs/concepts/daemons.md §2 for the full launchd migration recipe.

If neither activation path produces a socket, `bind_listen()` binds one
manually at the configured path, unlinks any stale socket file, and chmods
to 0600.
"""

from __future__ import annotations

import os
import socket
from pathlib import Path

ACTIVATION_ENV_VAR = "LAUNCH_ACTIVATE_SOCKET_FD"
"""Name of the env var carrying a pre-bound, listening Unix-socket FD.

This name mirrors Apple's `launch_activate_socket` API while being explicit
about the mechanism (FD inheritance via env var). Under a future launchd
migration, a short ctypes wrapper around `launch_activate_socket` will
supersede this env var — callers won't need to change."""


def inherited_socket() -> socket.socket | None:
    """Return a socket built from an inherited FD, or None if not activated.

    Returns None when:
    - The env var is unset.
    - The env var value is not a decimal integer.
    - The FD is not open (os.fstat raises OSError).
    """
    raw = os.environ.get(ACTIVATION_ENV_VAR)
    if raw is None:
        return None
    try:
        fd = int(raw)
    except ValueError:
        return None
    try:
        os.fstat(fd)
    except OSError:
        return None
    # dup() so that the caller owns a socket object whose close() is safe;
    # the original FD remains owned by the parent.
    return socket.socket(fileno=os.dup(fd))


def bind_listen(path: Path, backlog: int = 128) -> socket.socket:
    """Bind a new Unix-domain listening socket at `path`.

    Removes any pre-existing socket file (stale from a prior crash) before
    binding. Sets 0600 permissions on the socket file — only the daemon's
    user can connect. Returns the listening socket (caller must close).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.bind(str(path))
    os.chmod(path, 0o600)
    sock.listen(backlog)
    return sock
```

### Step 4: Run tests, confirm they pass

```bash
uv run pytest tests/unit/daemon/test_socket_activation.py -v
```

Expected: 6 tests pass.

### Step 5: Lint + format

```bash
uv run ruff check src/local_library/daemon/socket_activation.py tests/unit/daemon/test_socket_activation.py
uv run ruff format src/local_library/daemon/socket_activation.py tests/unit/daemon/test_socket_activation.py
```

### Step 6: Commit

```bash
git add src/local_library/daemon/socket_activation.py tests/unit/daemon/test_socket_activation.py
git commit -m "feat(daemon): socket activation shim with manual-bind fallback

Adds inherited_socket() for env-var FD inheritance (launchd forward-compat
stub) and bind_listen() for the manual-bind path with stale-socket cleanup
and 0600 permissions."
```
<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
## Task 5: asyncio echo server + signal handling

**Type:** Functionality. Tests drive server internals via pure-function calls and a real socket-pair handler exercise; end-to-end lifecycle is covered in Task 7.

**Files:**
- Create: `tests/unit/daemon/test_server.py`
- Create: `src/local_library/daemon/server.py`

### Step 1: Write failing tests

`tests/unit/daemon/test_server.py`:

```python
"""Unit tests for daemon server internals (pure-function layer).

End-to-end lifecycle is verified via subprocess in tests/unit/daemon/test_lifecycle.py.
"""

import asyncio
import socket

import pytest

from local_library.daemon import server


def test_version_string_is_nonempty() -> None:
    v = server.library_version()
    assert isinstance(v, str)
    assert len(v) > 0


def test_resident_bytes_reports_positive_integer() -> None:
    rss = server.resident_bytes()
    assert isinstance(rss, int)
    assert rss > 0


def test_echo_handler_roundtrip_via_socketpair() -> None:
    """Drive the echo handler over a real UDS socket pair."""
    parent, child = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        async def run() -> bytes:
            reader, writer = await asyncio.open_unix_connection(sock=parent)
            child_reader, child_writer = await asyncio.open_connection(sock=child)
            handler_task = asyncio.create_task(
                server.echo_handler(child_reader, child_writer)
            )
            writer.write(b"hello\n")
            await writer.drain()
            data = await reader.readline()
            writer.close()
            await writer.wait_closed()
            await asyncio.wait_for(handler_task, timeout=1.0)
            return data

        data = asyncio.run(run())
        assert data == b"hello\n"
    finally:
        parent.close()
        child.close()


def test_startup_uses_inherited_socket_when_present(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """If the activation env var is set, the server wraps the inherited FD."""
    inherited = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    inherited.bind(str(tmp_path / "inherited.sock"))
    inherited.listen(1)
    monkeypatch.setenv("LAUNCH_ACTIVATE_SOCKET_FD", str(inherited.fileno()))
    try:
        sock = server.acquire_listening_socket(fallback_path=tmp_path / "fallback.sock")
        assert sock.fileno() != inherited.fileno()  # dup'd
        assert not (tmp_path / "fallback.sock").exists()
        sock.close()
    finally:
        inherited.close()


def test_startup_binds_fallback_when_no_activation(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.delenv("LAUNCH_ACTIVATE_SOCKET_FD", raising=False)
    path = tmp_path / "daemon.sock"
    sock = server.acquire_listening_socket(fallback_path=path)
    try:
        assert path.is_socket()
    finally:
        sock.close()
        path.unlink(missing_ok=True)
```

### Step 2: Run tests, confirm they fail

```bash
uv run pytest tests/unit/daemon/test_server.py -v
```

Expected: ImportError for `local_library.daemon.server`.

### Step 3: Implement `server.py`

`src/local_library/daemon/server.py`:

```python
"""Daemon asyncio server: echo loop (Phase 1), JSON-RPC dispatch arrives in Phase 2.

# pattern: Imperative Shell

Owns the event loop, the listening socket (from socket_activation), the PID
file lock (from pid_file), and SIGTERM/SIGINT handling.

Phase 1 protocol is a literal echo: the server reads bytes from each client
and writes them back unchanged. Phase 2 replaces `echo_handler` with the
JSON-RPC dispatch loop; the lifecycle scaffolding stays intact.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import socket
import sys
import time
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import psutil

from local_library import config
from local_library.daemon import pid_file, socket_activation

_START_TIME = time.monotonic()
_LOGGER = logging.getLogger("local_library.daemon")


def library_version() -> str:
    """Return the installed local-library distribution version."""
    try:
        return version("local-library")
    except PackageNotFoundError:
        return "0.0.0+unknown"


def resident_bytes() -> int:
    """Return the current process's resident set size in bytes."""
    return int(psutil.Process().memory_info().rss)


def uptime_seconds() -> float:
    """Return seconds since the daemon main() entered its serving loop."""
    return time.monotonic() - _START_TIME


def acquire_listening_socket(fallback_path: Path) -> socket.socket:
    """Return a listening UDS socket: inherited from launchd if available,
    else bound manually at `fallback_path`.
    """
    inherited = socket_activation.inherited_socket()
    if inherited is not None:
        _LOGGER.info("acquired inherited socket from launchd FD")
        return inherited
    _LOGGER.info("binding new socket at %s", fallback_path)
    return socket_activation.bind_listen(fallback_path)


async def echo_handler(
    reader: asyncio.StreamReader, writer: asyncio.StreamWriter
) -> None:
    """Phase 1 handler: echo bytes until EOF, then close cleanly.

    Phase 2 replaces this with the JSON-RPC dispatch loop.
    """
    try:
        while True:
            chunk = await reader.read(4096)
            if not chunk:
                break
            writer.write(chunk)
            await writer.drain()
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:  # noqa: BLE001 — best-effort shutdown
            pass


async def _serve(listening: socket.socket, stop_event: asyncio.Event) -> None:
    server_obj = await asyncio.start_unix_server(echo_handler, sock=listening)
    async with server_obj:
        await stop_event.wait()
        server_obj.close()
        await server_obj.wait_closed()


def _install_signal_handlers(
    loop: asyncio.AbstractEventLoop, stop_event: asyncio.Event
) -> None:
    def _stop(_sig: int) -> None:
        _LOGGER.info("received signal %s, initiating shutdown", _sig)
        stop_event.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _stop, sig)


def _configure_logging() -> None:
    log_dir = config.get_daemon_log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=[
            logging.FileHandler(log_dir / "daemon.log", mode="a"),
            logging.StreamHandler(sys.stderr),
        ],
    )


def main() -> int:
    """Foreground entry point for the daemon process.

    Invoked by the `local-library-daemon` script entry and by
    `local-library daemon run`. Returns process exit code.
    """
    global _START_TIME  # noqa: PLW0603 — uptime anchors at serve start
    _configure_logging()
    _LOGGER.info(
        "daemon starting (pid=%s, version=%s)", os.getpid(), library_version()
    )

    config.ensure_directories()

    try:
        lock = pid_file.acquire(config.get_daemon_pid_path())
    except pid_file.AlreadyRunningError as exc:
        _LOGGER.error("refusing to start: %s", exc)
        return 1

    listening = acquire_listening_socket(config.get_socket_path())
    _START_TIME = time.monotonic()

    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        stop_event = asyncio.Event()
        _install_signal_handlers(loop, stop_event)
        _LOGGER.info("daemon ready at %s", config.get_socket_path())
        loop.run_until_complete(_serve(listening, stop_event))
        _LOGGER.info("daemon shut down cleanly")
        return 0
    finally:
        try:
            listening.close()
        except OSError:
            pass
        try:
            config.get_socket_path().unlink()
        except FileNotFoundError:
            pass
        pid_file.release(lock)
        loop.close()


if __name__ == "__main__":
    sys.exit(main())
```

### Step 4: Run tests

```bash
uv run pytest tests/unit/daemon/test_server.py -v
```

Expected: 5 tests pass.

### Step 5: Lint + format

```bash
uv run ruff check src/local_library/daemon/server.py tests/unit/daemon/test_server.py
uv run ruff format src/local_library/daemon/server.py tests/unit/daemon/test_server.py
```

### Step 6: Commit

```bash
git add src/local_library/daemon/server.py tests/unit/daemon/test_server.py
git commit -m "feat(daemon): asyncio UDS echo server with signal-driven shutdown

Phase 1 handler is a literal byte echo; Phase 2 replaces it with the
JSON-RPC dispatch loop. Lifecycle scaffolding — PID file lock, socket
activation, SIGTERM/SIGINT handling, clean socket + PID cleanup — is
stable for the rest of the daemon's lifetime."
```
<!-- END_TASK_5 -->

<!-- END_SUBCOMPONENT_B -->

<!-- START_SUBCOMPONENT_C (tasks 6-7) -->

<!-- START_TASK_6 -->
## Task 6: CLI subcommand group + main.py wiring

**Type:** Infrastructure with a small functionality component (status reporting).

**Files:**
- Create: `src/local_library/cli/daemon.py`
- Modify: `src/local_library/cli/main.py` (add_typer call + import)
- Create: `tests/unit/daemon/test_cli.py`

### Step 1: Create `cli/daemon.py`

`src/local_library/cli/daemon.py`:

```python
"""CLI subcommands for daemon process lifecycle management.

# pattern: Imperative Shell

`run` is foreground (the launchd / test-harness entry).
`start` spawns a detached background process running the daemon module.
`stop` sends SIGTERM to the PID and waits for release of the PID file.
`status` reports pid, uptime, resident memory (reads live data via psutil).
`restart` is stop-then-start.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time

import psutil
import typer
from rich.console import Console
from rich.table import Table

from local_library import config
from local_library.daemon import pid_file
from local_library.daemon import server as daemon_server

app = typer.Typer(
    name="daemon",
    help="Manage the long-running local-library daemon.",
    add_completion=False,
)

_console = Console()


def _resolve_running_pid() -> int | None:
    """Return the PID of a running daemon, or None if not running."""
    pid = pid_file.read_pid(config.get_daemon_pid_path())
    if pid is None:
        return None
    if not pid_file.is_process_alive(pid):
        return None
    return pid


@app.command()
def run() -> None:
    """Run the daemon in the foreground (does not return until SIGTERM)."""
    raise typer.Exit(code=daemon_server.main())


@app.command()
def start() -> None:
    """Start the daemon as a detached background process."""
    if _resolve_running_pid() is not None:
        _console.print("[yellow]daemon already running[/yellow]")
        raise typer.Exit(code=0)

    config.ensure_directories()
    log_path = config.get_daemon_log_dir() / "daemon.out"

    # Use the python module form to avoid depending on the script-entry path
    # being on PATH at the exact moment `start` runs.
    cmd = [sys.executable, "-m", "local_library.daemon.server"]

    stdout = open(log_path, "ab")
    proc = subprocess.Popen(
        cmd,
        stdout=stdout,
        stderr=subprocess.STDOUT,
        start_new_session=True,  # detach: new process group, no controlling TTY
        close_fds=True,
    )

    # Poll briefly for the PID file to appear as confirmation.
    deadline = time.monotonic() + 5.0
    pid_path = config.get_daemon_pid_path()
    while time.monotonic() < deadline:
        if pid_path.exists() and pid_file.read_pid(pid_path) == proc.pid:
            _console.print(f"[green]daemon started[/green] (pid={proc.pid})")
            return
        if proc.poll() is not None:
            _console.print(
                f"[red]daemon exited during startup[/red] "
                f"(exit={proc.returncode}, see {log_path})"
            )
            raise typer.Exit(code=1)
        time.sleep(0.1)

    _console.print(
        "[red]daemon did not report ready within 5s[/red] "
        f"(pid={proc.pid}, see {log_path})"
    )
    raise typer.Exit(code=1)


@app.command()
def stop() -> None:
    """Stop the running daemon (SIGTERM + wait for PID file removal)."""
    pid = _resolve_running_pid()
    if pid is None:
        _console.print("[yellow]daemon not running[/yellow]")
        raise typer.Exit(code=0)

    os.kill(pid, signal.SIGTERM)

    deadline = time.monotonic() + 10.0
    pid_path = config.get_daemon_pid_path()
    while time.monotonic() < deadline:
        if not pid_path.exists():
            _console.print(f"[green]daemon stopped[/green] (pid={pid})")
            return
        if not pid_file.is_process_alive(pid):
            _console.print(
                f"[green]daemon stopped[/green] (pid={pid}, stale PID file left)"
            )
            return
        time.sleep(0.1)

    _console.print(f"[red]daemon did not stop within 10s[/red] (pid={pid})")
    raise typer.Exit(code=1)


@app.command()
def restart() -> None:
    """Stop the daemon (if running) and start a fresh instance."""
    if _resolve_running_pid() is not None:
        stop()
    start()


@app.command()
def status() -> None:
    """Report daemon liveness, pid, uptime, and resident memory."""
    pid = _resolve_running_pid()
    if pid is None:
        _console.print("[red]daemon not running[/red]")
        raise typer.Exit(code=1)

    proc = psutil.Process(pid)
    rss = proc.memory_info().rss
    uptime = time.time() - proc.create_time()

    table = Table(show_header=False, box=None)
    table.add_row("pid", str(pid))
    table.add_row("socket", str(config.get_socket_path()))
    table.add_row("uptime", f"{uptime:.1f}s")
    table.add_row("resident", f"{rss / (1024 * 1024):.1f} MiB")
    _console.print(table)
```

### Step 2: Wire into `cli/main.py`

Modify `src/local_library/cli/main.py`. In the import block, add alongside the other `as *_cmd` imports:

```python
from local_library.cli import daemon as daemon_cmd
```

Find the existing `app.add_typer(zotero_cmd.app, name="zotero")` line and add, directly below it:

```python
app.add_typer(daemon_cmd.app, name="daemon")
```

### Step 3: Write CLI smoke tests

`tests/unit/daemon/test_cli.py`:

```python
"""Smoke tests for the daemon CLI wiring (no live daemon required)."""

from typer.testing import CliRunner

from local_library.cli.main import app

runner = CliRunner()


def test_daemon_subcommand_registered() -> None:
    result = runner.invoke(app, ["daemon", "--help"])
    assert result.exit_code == 0
    assert "start" in result.stdout
    assert "stop" in result.stdout
    assert "status" in result.stdout
    assert "restart" in result.stdout
    assert "run" in result.stdout


def test_status_reports_not_running_when_no_daemon(monkeypatch, tmp_path) -> None:
    from local_library import config

    monkeypatch.setattr(config, "get_data_dir", lambda: tmp_path)
    result = runner.invoke(app, ["daemon", "status"])
    assert result.exit_code == 1
    assert "not running" in result.stdout.lower()


def test_stop_reports_not_running_when_no_daemon(monkeypatch, tmp_path) -> None:
    from local_library import config

    monkeypatch.setattr(config, "get_data_dir", lambda: tmp_path)
    result = runner.invoke(app, ["daemon", "stop"])
    assert result.exit_code == 0
    assert "not running" in result.stdout.lower()
```

### Step 4: Run tests

```bash
uv run pytest tests/unit/daemon/test_cli.py -v
```

Expected: 3 tests pass.

### Step 5: Operational verification

```bash
uv run local-library daemon --help
```

Expected: help text lists `start`, `stop`, `status`, `restart`, `run`.

```bash
uv run local-library daemon status
```

Expected: exits with code 1, prints "daemon not running".

### Step 6: Lint + format

```bash
uv run ruff check src/local_library/cli/daemon.py src/local_library/cli/main.py tests/unit/daemon/test_cli.py
uv run ruff format src/local_library/cli/daemon.py src/local_library/cli/main.py tests/unit/daemon/test_cli.py
```

### Step 7: Commit

```bash
git add src/local_library/cli/daemon.py src/local_library/cli/main.py tests/unit/daemon/test_cli.py
git commit -m "feat(daemon): CLI subcommand group (start/stop/status/restart/run)

Wires the daemon lifecycle behind 'local-library daemon <cmd>'. 'start'
spawns a detached process, 'stop' sends SIGTERM and waits, 'status' reports
pid/uptime/resident-memory, 'run' is the foreground entry point."
```
<!-- END_TASK_6 -->

<!-- START_TASK_7 -->
## Task 7: End-to-end lifecycle integration test

**Type:** Functionality / Verification.

**Files:**
- Create: `tests/unit/daemon/test_lifecycle.py`

### Step 1: Write the test

`tests/unit/daemon/test_lifecycle.py`:

```python
"""End-to-end daemon lifecycle: spawn, echo over UDS, SIGTERM, clean exit.

Spawns the daemon as a real subprocess using a per-test data dir (via the
XDG_DATA_HOME env var that platformdirs honors). Goal: exercise real signal
delivery, real socket unlink, real PID file lock release — none of which
can be faithfully tested in-process.
"""

import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest


@pytest.fixture
def daemon_env(tmp_path: Path) -> dict[str, str]:
    """Return env for spawning a daemon with all state isolated to tmp_path."""
    env = os.environ.copy()
    env["XDG_DATA_HOME"] = str(tmp_path / "data")
    env["PYTHONUNBUFFERED"] = "1"
    return env


def _wait_for_socket(path: Path, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.is_socket():
            return
        time.sleep(0.05)
    raise AssertionError(f"daemon did not create socket {path} within {timeout}s")


def _data_dir(env: dict[str, str]) -> Path:
    """Compute the same data dir the daemon will resolve in-child."""
    probe = subprocess.run(
        [sys.executable, "-c",
         "from local_library import config; print(config.get_data_dir())"],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    return Path(probe.stdout.strip())


def test_daemon_starts_echoes_and_shuts_down(daemon_env: dict[str, str]) -> None:
    data_dir = _data_dir(daemon_env)
    socket_path = data_dir / "daemon.sock"
    pid_path = data_dir / "daemon.pid"

    proc = subprocess.Popen(
        [sys.executable, "-m", "local_library.daemon.server"],
        env=daemon_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    try:
        _wait_for_socket(socket_path)
        assert pid_path.exists()
        assert int(pid_path.read_text().strip()) == proc.pid

        # Echo roundtrip.
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.connect(str(socket_path))
            client.sendall(b"ping\n")
            data = b""
            while not data.endswith(b"\n"):
                chunk = client.recv(4096)
                if not chunk:
                    break
                data += chunk
            assert data == b"ping\n"

        proc.send_signal(signal.SIGTERM)
        proc.wait(timeout=10)
        assert proc.returncode == 0
        assert not socket_path.exists(), "daemon did not unlink socket on shutdown"
        assert not pid_path.exists(), "daemon did not remove PID file on shutdown"
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)


def test_double_start_is_rejected(daemon_env: dict[str, str]) -> None:
    data_dir = _data_dir(daemon_env)
    socket_path = data_dir / "daemon.sock"

    first = subprocess.Popen(
        [sys.executable, "-m", "local_library.daemon.server"],
        env=daemon_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    try:
        _wait_for_socket(socket_path)

        second = subprocess.run(
            [sys.executable, "-m", "local_library.daemon.server"],
            env=daemon_env,
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert second.returncode == 1
        combined = (second.stdout + second.stderr).lower()
        assert "already running" in combined
    finally:
        first.send_signal(signal.SIGTERM)
        first.wait(timeout=10)
```

**Note on `XDG_DATA_HOME`:** `platformdirs.user_data_dir` honors `XDG_DATA_HOME` when explicitly set. If this redirection proves flaky under macOS in practice, the fallback is to add a `LOCAL_LIBRARY_DATA_DIR` override in `config.py` gated on that env var's presence; re-run the tests then.

### Step 2: Run the tests

```bash
uv run pytest tests/unit/daemon/test_lifecycle.py -v
```

Expected: 2 tests pass. Each test spawns a real subprocess, so expect ~5–15s total.

### Step 3: Verify all Phase 1 "Done when" criteria

Manual verification (not a committed test step):

```bash
uv run local-library daemon start
ls ~/Library/Application\ Support/local-library/daemon.sock  # socket exists
nc -U ~/Library/Application\ Support/local-library/daemon.sock <<< "hello"
# expect echo of "hello"
uv run local-library daemon status
# expect table with pid, socket, uptime, resident
uv run local-library daemon stop
# expect "daemon stopped (pid=N)"
ls ~/Library/Application\ Support/local-library/daemon.sock 2>&1
# expect: No such file or directory
```

### Step 4: Lint + format

```bash
uv run ruff check tests/unit/daemon/test_lifecycle.py
uv run ruff format tests/unit/daemon/test_lifecycle.py
```

### Step 5: Commit

```bash
git add tests/unit/daemon/test_lifecycle.py
git commit -m "test(daemon): end-to-end lifecycle (spawn, echo, SIGTERM, cleanup)

Verifies real signal delivery, real socket unlink, real PID file lock
release, and double-start rejection via subprocess-based tests."
```
<!-- END_TASK_7 -->

<!-- END_SUBCOMPONENT_C -->

<!-- START_TASK_8 -->
## Task 8: Concepts doc chapters 1–2 + close Phase 1

**Type:** Documentation.

**Files:**
- Create: `docs/concepts/daemons.md`

### Step 1: Author the doc

Create `docs/concepts/daemons.md`:

```markdown
# Daemons, IPC, and RPC — a working reference

Last verified: 2026-04-24

This document is a standalone teaching reference for the concepts that shape
the local-library daemon. It is written in lockstep with the implementation
phases: each chapter is grounded in specific design decisions made in this
project, cross-referenced into `docs/design-plans/2026-04-24-neovim-citation-workflow.md`.

## Chapter 1 — What is a daemon?

A **daemon** is a long-running process that provides services to other
processes without being tied to a user's interactive session. The defining
properties:

1. **Lifetime decoupled from a TTY.** A daemon survives logout, terminal
   close, and SSH disconnect. Mechanically, this means the daemon runs in
   its own session (`setsid`) and has no controlling terminal.
2. **Stable endpoint.** A daemon publishes a well-known address — a socket
   path, TCP port, D-Bus name — that other processes know how to reach.
3. **Idle-tolerant.** A daemon spends most of its time blocked waiting for
   requests, not computing. Its value is amortized model-load cost, not
   throughput.
4. **Single-instance per endpoint.** Two daemons cannot own the same socket
   path simultaneously; some coordination (PID file, systemd socket, launchd
   LaunchAgent) ensures only one is live at a time.

In the local-library architecture, the daemon exists to avoid paying
cold-start costs repeatedly: the embedding model (~200 MB) and sqlite-vec
connection initialize once, then serve many small queries over the lifetime
of a Neovim session.

### Why a daemon for local-library specifically?

Two alternatives were considered and rejected:

- **CLI-per-query.** Shelling out to `local-library search` from the editor
  pays ~3–8 s cold-start on every invocation (embedder + reranker load).
  Unusable for a claim-driven search workflow that fires on every `<leader>c`.
- **Editor plugin with in-process Python.** Requires embedding a Python
  interpreter in Neovim (pynvim), which composes poorly with the editor's
  Lua event loop and would couple the retrieval engine to the Neovim
  lifecycle. Non-starter once we want a future MCP server v2 to share the
  same warm state.

The daemon is the architecturally smallest change that resolves both: warm
state, editor-agnostic. See design doc §"High-level shape" and §"Process model".

## Chapter 2 — Process supervision and service management

A daemon that can start is not a daemon that will stay running. **Service
management** covers the questions: who launches the daemon on boot or on
demand? Who restarts it after a crash? Who routes its logs?

### The three common answers

1. **User-managed (CLI-driven).** The user runs `my-daemon start` and
   `my-daemon stop`. The program is responsible for its own lifecycle:
   forking, PID file, signal handling. Simple; no OS coupling. Poor for
   always-on services because the user has to remember to start it.
2. **System supervisor.** systemd on Linux, launchd on macOS, SMF on
   illumos. The supervisor owns process lifecycle: starts on boot, restarts
   on crash, aggregates logs. The daemon ships a unit file / plist and lets
   the supervisor manage it. Requires learning the supervisor's conventions
   but eliminates a class of lifecycle bugs.
3. **Socket activation.** The supervisor pre-binds the listening socket
   itself and hands the daemon an inherited FD on start. This lets the
   daemon be started on-demand (first client connect) and shut down after
   idle, without losing requests in the handoff.

### local-library's choice: CLI-managed with launchd forward-compat

For MVP, local-library's daemon is user-managed: `local-library daemon start`,
`stop`, `status`. This matches the developer's workflow (start the daemon in
the morning, stop it when the machine shuts down) and avoids forcing launchd
configuration on users who don't want system-level service integration.

However, the daemon is structured so that a future move to launchd
socket-activation is a packaging change — not a code change. Specifically:

- `socket_activation.inherited_socket()` checks for a pre-bound FD (Phase 1
  via the `LAUNCH_ACTIVATE_SOCKET_FD` env var; future via ctypes wrapper
  around Apple's `launch_activate_socket`). If present, the server wraps it
  as the listening socket and skips the manual bind.
- `main()` is a plain function; no double-fork, no demonization. Under
  launchd, the process stays in the foreground and launchd takes care of
  TTY detachment.
- Logging goes to `config.get_daemon_log_dir()/daemon.log`. Under launchd,
  the plist's `StandardOutPath` / `StandardErrorPath` can redirect cleanly.

### The pieces that stay the daemon's problem

Even with socket activation, the daemon still owns:

- **Single-instance enforcement.** The PID file + `fcntl.flock` combo
  (see `daemon/pid_file.py`) ensures that only one daemon process writes
  to the sqlite-vec database at a time. sqlite-vec's single-threaded access
  requirement makes this non-optional; launchd's socket activation does
  not substitute for it, because a buggy start script could still launch
  two processes.
- **Signal-driven cleanup.** SIGTERM is the supervisor's "please shut down"
  request. The daemon must close the server, unlink the socket, release
  the PID lock, and exit 0 within the supervisor's grace period (launchd
  default: 20 s). See `daemon/server.py` `_install_signal_handlers`.

### Cross-references

- Design doc §"Process model" — the CLI-managed-with-launchd-compat decision
- Design doc §"Patterns this design deliberately does not follow" —
  rejection of double-fork / PEP 3143 daemonization
- `src/local_library/daemon/pid_file.py` — PID file + flock implementation
- `src/local_library/daemon/socket_activation.py` — FD-inheritance shim

*Chapters 3–8 are written in Phases 2–7.*
```

### Step 2: Verify chapter count

```bash
grep -c '^## Chapter' docs/concepts/daemons.md
```

Expected: `2`.

### Step 3: Commit

```bash
git add docs/concepts/daemons.md
git commit -m "docs(concepts): add chapters 1-2 of the daemons concepts doc

Chapter 1: what a daemon is and why local-library has one.
Chapter 2: process supervision, service management, and the CLI-managed-
with-launchd-forward-compat decision. Cross-references the design doc
and the Phase 1 implementation files."
```

### Step 4: Run the full Phase 1 test set

```bash
uv run pytest tests/unit/daemon/ tests/unit/test_config_daemon_paths.py -v
```

Expected: 29 tests pass (4 config + 9 pid_file + 6 socket_activation + 5 server + 3 cli + 2 lifecycle).

### Step 5: Phase close verification

- ✓ `uv run local-library daemon start` spawns daemon, writes PID, binds socket — Task 7 manual verification.
- ✓ `uv run local-library daemon status` reports pid, uptime, resident — Task 6.
- ✓ `uv run local-library daemon stop` terminates cleanly — Task 6.
- ✓ `uv run local-library daemon run` stays foreground — Task 6 `run` command.
- ✓ Unit tests cover PID lifecycle, signal handling, double-start detection — Tasks 3 + 7.

Confirm `git status` is clean before moving to Phase 2.
<!-- END_TASK_8 -->
