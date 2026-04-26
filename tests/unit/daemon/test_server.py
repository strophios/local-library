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
            handler_task = asyncio.create_task(server.echo_handler(child_reader, child_writer))
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
    monkeypatch: pytest.MonkeyPatch, short_tmp_path
) -> None:
    """If the activation env var is set, the server wraps the inherited FD."""
    inherited = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    inherited.bind(str(short_tmp_path / "inherited.sock"))
    inherited.listen(1)
    monkeypatch.setenv("LAUNCH_ACTIVATE_SOCKET_FD", str(inherited.fileno()))
    try:
        sock = server.acquire_listening_socket(fallback_path=short_tmp_path / "fallback.sock")
        assert sock.fileno() != inherited.fileno()  # dup'd
        assert not (short_tmp_path / "fallback.sock").exists()
        sock.close()
    finally:
        inherited.close()


def test_startup_binds_fallback_when_no_activation(
    monkeypatch: pytest.MonkeyPatch, short_tmp_path
) -> None:
    monkeypatch.delenv("LAUNCH_ACTIVATE_SOCKET_FD", raising=False)
    path = short_tmp_path / "daemon.sock"
    sock = server.acquire_listening_socket(fallback_path=path)
    try:
        assert path.is_socket()
    finally:
        sock.close()
        path.unlink(missing_ok=True)
