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


def test_bind_listen_unlinks_stale_file(short_tmp_path) -> None:
    path = short_tmp_path / "daemon.sock"
    path.touch()  # pre-existing stale file
    sock = socket_activation.bind_listen(path)
    try:
        assert path.is_socket()
        assert (path.stat().st_mode & 0o777) == 0o600
    finally:
        sock.close()
        path.unlink(missing_ok=True)


def test_bind_listen_creates_parent(short_tmp_path) -> None:
    path = short_tmp_path / "subdir" / "daemon.sock"
    sock = socket_activation.bind_listen(path)
    try:
        assert path.is_socket()
    finally:
        sock.close()
        path.unlink(missing_ok=True)
