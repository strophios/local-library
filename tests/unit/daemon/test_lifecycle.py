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
def daemon_env(short_tmp_path: Path) -> dict[str, str]:
    """Return env for spawning a daemon with all state isolated to short_tmp_path.

    Uses short_tmp_path (not tmp_path) to keep AF_UNIX socket path under
    Darwin's ~104-char sun_path limit.

    Sets both XDG_DATA_HOME (for Linux parity) and LOCAL_LIBRARY_DATA_DIR
    (the operative override on Darwin, where platformdirs ignores XDG_DATA_HOME).
    """
    env = os.environ.copy()
    env["XDG_DATA_HOME"] = str(short_tmp_path / "data")
    env["LOCAL_LIBRARY_DATA_DIR"] = str(short_tmp_path / "data" / "local-library")
    env["PYTHONUNBUFFERED"] = "1"
    # Skip model warmup. Lifecycle tests only exercise transport + signal
    # handling, not search; loading ~250 MB of embedder + reranker would
    # gate SIGTERM responsiveness on warmup completion (asyncio signal
    # handlers fire on the loop thread but the loop is parked awaiting
    # the executor task during _construct_library).
    env["LOCAL_LIBRARY_DAEMON_SKIP_WARMUP"] = "1"
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
        [
            sys.executable,
            "-c",
            "from local_library import config; print(config.get_data_dir())",
        ],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    return Path(probe.stdout.strip())


def test_daemon_responds_to_ping_and_shuts_down(
    daemon_env: dict[str, str], short_tmp_path: Path
) -> None:
    data_dir = _data_dir(daemon_env)
    # Verify isolation: data_dir under short_tmp_path, not ~/Library/Application Support
    assert str(data_dir).startswith(str(short_tmp_path))
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

        # JSON-RPC ping roundtrip.
        import json as _json

        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.connect(str(socket_path))
            client.sendall(b'{"jsonrpc":"2.0","id":1,"method":"ping"}\n')
            data = b""
            while not data.endswith(b"\n"):
                chunk = client.recv(4096)
                if not chunk:
                    break
                data += chunk
            response = _json.loads(data)
            assert response["jsonrpc"] == "2.0"
            assert response["id"] == 1
            assert response["result"]["ok"] is True
            assert response["result"]["daemon_pid"] == proc.pid
            assert response["result"]["library_version"]

        proc.send_signal(signal.SIGTERM)
        proc.wait(timeout=10)
        assert proc.returncode == 0
        assert not socket_path.exists(), "daemon did not unlink socket on shutdown"
        assert not pid_path.exists(), "daemon did not remove PID file on shutdown"
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)


def test_shutdown_completes_with_held_client_connection(
    daemon_env: dict[str, str], short_tmp_path: Path
) -> None:
    """Daemon must shut down on SIGTERM even when a client holds an open socket.

    Regression: the Neovim plugin maintains a long-lived JSON-RPC channel
    for the lifetime of nvim. Without forced client close on shutdown,
    `Server.wait_closed()` blocks on the active connection and the daemon
    never exits. Pre-fix, SIGTERM was effectively ignored — only SIGKILL
    worked, which is why `LocalLibraryDaemon stop` failed in the plugin.
    """
    data_dir = _data_dir(daemon_env)
    assert str(data_dir).startswith(str(short_tmp_path))
    socket_path = data_dir / "daemon.sock"

    proc = subprocess.Popen(
        [sys.executable, "-m", "local_library.daemon.server"],
        env=daemon_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    held: socket.socket | None = None
    try:
        _wait_for_socket(socket_path)

        # Open and HOLD a connection. Issue a ping first so the connection is
        # actually fully established server-side (accept() ran, the
        # protocol_handler coroutine started). Then keep the socket open
        # while we send SIGTERM.
        held = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        held.connect(str(socket_path))
        held.sendall(b'{"jsonrpc":"2.0","id":1,"method":"ping"}\n')
        # Drain the response so we know the server is engaged.
        data = b""
        held.settimeout(60.0)  # generous: covers warmup
        while not data.endswith(b"\n"):
            chunk = held.recv(4096)
            if not chunk:
                break
            data += chunk

        # Now SIGTERM with the connection still open.
        proc.send_signal(signal.SIGTERM)
        # 5s budget: well below the CLI's 10s `daemon stop` window. If the
        # daemon takes longer, the user-facing CLI reports a stop failure.
        proc.wait(timeout=5)
        assert proc.returncode == 0
        assert not socket_path.exists(), "daemon did not unlink socket on shutdown"
    finally:
        if held is not None:
            try:
                held.close()
            except OSError:
                pass
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)


def test_double_start_is_rejected(daemon_env: dict[str, str], short_tmp_path: Path) -> None:
    data_dir = _data_dir(daemon_env)
    # Verify isolation: data_dir under short_tmp_path, not ~/Library/Application Support
    assert str(data_dir).startswith(str(short_tmp_path))
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
