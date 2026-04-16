"""Tests for the CLI list command filter flags."""

from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from local_library.cli.main import app

runner = CliRunner()


@pytest.fixture
def mock_library_for_list():
    """Provide a mock Library for list CLI testing."""
    with patch("local_library.cli.list.Library") as mock_cls:
        mock_lib = MagicMock()
        mock_lib.list.return_value = []
        mock_cls.return_value.__enter__ = MagicMock(return_value=mock_lib)
        mock_cls.return_value.__exit__ = MagicMock(return_value=False)
        yield mock_lib


class TestCliListFilters:
    def test_year_flag(self, mock_library_for_list) -> None:
        result = runner.invoke(app, ["list", "--year", "2023"])
        assert result.exit_code == 0
        _, kwargs = mock_library_for_list.list.call_args
        assert kwargs.get("year") == 2023

    def test_year_missing_flag(self, mock_library_for_list) -> None:
        result = runner.invoke(app, ["list", "--year-missing"])
        assert result.exit_code == 0
        _, kwargs = mock_library_for_list.list.call_args
        assert kwargs.get("year_missing") is True

    def test_year_and_year_missing_mutually_exclusive(self, mock_library_for_list) -> None:
        result = runner.invoke(app, ["list", "--year", "2023", "--year-missing"])
        assert result.exit_code == 2
        assert "--year and --year-missing are mutually exclusive" in result.output

    def test_author_contains_flag(self, mock_library_for_list) -> None:
        result = runner.invoke(app, ["list", "--author-contains", "Zippel"])
        assert result.exit_code == 0
        _, kwargs = mock_library_for_list.list.call_args
        assert kwargs.get("author_contains") == "Zippel"

    def test_title_contains_flag(self, mock_library_for_list) -> None:
        result = runner.invoke(app, ["list", "--title-contains", "Methods"])
        assert result.exit_code == 0
        _, kwargs = mock_library_for_list.list.call_args
        assert kwargs.get("title_contains") == "Methods"

    def test_citekey_prefix_flag(self, mock_library_for_list) -> None:
        result = runner.invoke(app, ["list", "--citekey-prefix", "Bourdieu"])
        assert result.exit_code == 0
        _, kwargs = mock_library_for_list.list.call_args
        assert kwargs.get("citekey_prefix") == "Bourdieu"

    def test_help_mentions_new_flags(self, mock_library_for_list) -> None:
        result = runner.invoke(app, ["list", "--help"])
        assert result.exit_code == 0
        # Just check that flag names appear in help output
        assert "--year" in result.output
        assert "--author-contains" in result.output
        assert "--title-contains" in result.output
        assert "--citekey-prefix" in result.output
