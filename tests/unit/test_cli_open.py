"""Unit tests for open command."""

import os
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from local_library.cli.main import app
from local_library.cli.open import find_editor
from local_library.core.models import DocumentStatus

runner = CliRunner()


@pytest.fixture
def mock_library_open():
    """Provide a mock Library for open command testing."""
    with patch("local_library.cli.open.Library") as mock_lib_cls:
        mock_lib = MagicMock()
        mock_lib_cls.return_value.__enter__ = MagicMock(return_value=mock_lib)
        mock_lib_cls.return_value.__exit__ = MagicMock(return_value=False)
        yield mock_lib


class TestFindEditor:
    """Tests for editor detection logic."""

    def test_find_editor_nvim(self) -> None:
        """Should prefer nvim if available."""
        with patch("shutil.which") as mock_which:
            mock_which.side_effect = lambda x: f"/usr/bin/{x}" if x == "nvim" else None
            editor = find_editor()
            assert editor == "/usr/bin/nvim"

    def test_find_editor_vim_fallback(self) -> None:
        """Should fall back to vim if nvim not available."""
        with patch("shutil.which") as mock_which:
            mock_which.side_effect = lambda x: "/usr/bin/vim" if x == "vim" else None
            editor = find_editor()
            assert editor == "/usr/bin/vim"

    def test_find_editor_env_fallback(self) -> None:
        """Should use $EDITOR if nvim/vim not available."""
        with (
            patch("shutil.which", return_value=None),
            patch.dict(os.environ, {"EDITOR": "/usr/bin/nano"}),
        ):
            editor = find_editor()
            assert editor == "/usr/bin/nano"

    def test_find_editor_none(self) -> None:
        """Should return None if no editor found."""
        with (
            patch("shutil.which", return_value=None),
            patch.dict(os.environ, {}, clear=True),
        ):
            # Remove EDITOR if present
            os.environ.pop("EDITOR", None)
            editor = find_editor()
            assert editor is None


class TestOpenCommand:
    """Tests for open command."""

    def test_open_markdown_default(self, mock_library_open: MagicMock) -> None:
        """open command should open markdown by default."""
        mock_doc = MagicMock()
        mock_doc.id = "12345678-1234-1234-1234-123456789abc"
        mock_doc.extracted_path = "/path/to/doc.md"
        mock_doc.storage_path = "/path/to/doc.pdf"
        mock_doc.status = DocumentStatus.READY

        mock_library_open.get.return_value = mock_doc

        with (
            patch("local_library.cli.open.find_editor", return_value="/usr/bin/nvim"),
            patch("local_library.cli.open.subprocess.run") as mock_run,
        ):
            result = runner.invoke(app, ["open", "12345678"])

            assert result.exit_code == 0
            mock_run.assert_called_once()
            call_args = mock_run.call_args[0][0]
            assert "/usr/bin/nvim" in call_args
            assert "/path/to/doc.md" in call_args

    def test_open_pdf_flag(self, mock_library_open: MagicMock) -> None:
        """open --pdf should open PDF in system viewer."""
        mock_doc = MagicMock()
        mock_doc.id = "12345678-1234-1234-1234-123456789abc"
        mock_doc.extracted_path = "/path/to/doc.md"
        mock_doc.storage_path = "/path/to/doc.pdf"
        mock_doc.status = DocumentStatus.READY

        mock_library_open.get.return_value = mock_doc

        with patch("local_library.cli.open.subprocess.Popen") as mock_popen:
            result = runner.invoke(app, ["open", "--pdf", "12345678"])

            assert result.exit_code == 0
            mock_popen.assert_called_once()
            call_args = mock_popen.call_args[0][0]
            assert "open" in call_args
            assert "/path/to/doc.pdf" in call_args

    def test_open_both_flag(self, mock_library_open: MagicMock) -> None:
        """open --both should open PDF then markdown."""
        mock_doc = MagicMock()
        mock_doc.id = "12345678-1234-1234-1234-123456789abc"
        mock_doc.extracted_path = "/path/to/doc.md"
        mock_doc.storage_path = "/path/to/doc.pdf"
        mock_doc.status = DocumentStatus.READY

        mock_library_open.get.return_value = mock_doc

        with (
            patch("local_library.cli.open.find_editor", return_value="/usr/bin/nvim"),
            patch("local_library.cli.open.subprocess.Popen") as mock_popen,
            patch("local_library.cli.open.subprocess.run") as mock_run,
        ):
            result = runner.invoke(app, ["open", "--both", "12345678"])

            assert result.exit_code == 0
            # PDF opened first (non-blocking)
            mock_popen.assert_called_once()
            # Markdown opened second (blocking)
            mock_run.assert_called_once()

    def test_open_citekey_lookup(self, mock_library_open: MagicMock) -> None:
        """open @citekey should use citekey lookup."""
        mock_doc = MagicMock()
        mock_doc.id = "12345678-1234-1234-1234-123456789abc"
        mock_doc.extracted_path = "/path/to/doc.md"
        mock_doc.storage_path = "/path/to/doc.pdf"
        mock_doc.status = DocumentStatus.READY

        mock_library_open.get_by_citekey.return_value = mock_doc
        mock_library_open.get_all_citekeys.return_value = ["Smith2023"]

        with (
            patch("local_library.cli.open.find_editor", return_value="/usr/bin/nvim"),
            patch("local_library.cli.open.subprocess.run"),
        ):
            result = runner.invoke(app, ["open", "@Smith2023"])

            assert result.exit_code == 0
            mock_library_open.get_by_citekey.assert_called_once_with("Smith2023")

    def test_open_no_extracted_path(self, mock_library_open: MagicMock) -> None:
        """open should error if no markdown available."""
        mock_doc = MagicMock()
        mock_doc.id = "12345678-1234-1234-1234-123456789abc"
        mock_doc.extracted_path = None
        mock_doc.storage_path = "/path/to/doc.pdf"
        mock_doc.status = DocumentStatus.PENDING

        mock_library_open.get.return_value = mock_doc

        result = runner.invoke(app, ["open", "12345678"])

        assert result.exit_code == 1
        assert "no extracted markdown" in result.output.lower()

    def test_open_no_editor_found(self, mock_library_open: MagicMock) -> None:
        """open should error if no editor found."""
        mock_doc = MagicMock()
        mock_doc.id = "12345678-1234-1234-1234-123456789abc"
        mock_doc.extracted_path = "/path/to/doc.md"
        mock_doc.storage_path = "/path/to/doc.pdf"
        mock_doc.status = DocumentStatus.READY

        mock_library_open.get.return_value = mock_doc

        with patch("local_library.cli.open.find_editor", return_value=None):
            result = runner.invoke(app, ["open", "12345678"])

            assert result.exit_code == 1
            assert "no editor found" in result.output.lower()
