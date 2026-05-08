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


def test_get_data_dir_uses_override_when_env_var_set(monkeypatch) -> None:
    monkeypatch.setenv("LOCAL_LIBRARY_DATA_DIR", "/tmp/xyz")
    assert config.get_data_dir() == Path("/tmp/xyz")


def test_get_data_dir_falls_back_to_platformdirs_when_env_var_unset(
    monkeypatch,
) -> None:
    monkeypatch.delenv("LOCAL_LIBRARY_DATA_DIR", raising=False)
    data_dir = config.get_data_dir()
    # Verify it's not using the override path (would be /tmp or similar test path)
    assert not str(data_dir).startswith("/tmp/")
    # Verify it returns the platformdirs default
    assert "local-library" in str(data_dir)
