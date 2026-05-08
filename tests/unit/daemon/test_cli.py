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
