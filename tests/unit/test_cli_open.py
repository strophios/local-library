"""Unit tests for open command."""

import os
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from local_library.cli.main import app
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
        from local_library.cli.open import find_editor

        with patch("shutil.which") as mock_which:
            mock_which.side_effect = lambda x: f"/usr/bin/{x}" if x == "nvim" else None
            editor = find_editor()
            assert editor == "/usr/bin/nvim"

    def test_find_editor_vim_fallback(self) -> None:
        """Should fall back to vim if nvim not available."""
        from local_library.cli.open import find_editor

        with patch("shutil.which") as mock_which:
            mock_which.side_effect = lambda x: "/usr/bin/vim" if x == "vim" else None
            editor = find_editor()
            assert editor == "/usr/bin/vim"

    def test_find_editor_env_fallback(self) -> None:
        """Should use $EDITOR if nvim/vim not available."""
        from local_library.cli.open import find_editor

        with (
            patch("shutil.which", return_value=None),
            patch.dict(os.environ, {"EDITOR": "/usr/bin/nano"}),
        ):
            editor = find_editor()
            assert editor == "/usr/bin/nano"

    def test_find_editor_none(self) -> None:
        """Should return None if no editor found."""
        from local_library.cli.open import find_editor

        with (
            patch("shutil.which", return_value=None),
            patch.dict(os.environ, {}, clear=True),
        ):
            # Remove EDITOR if present
            os.environ.pop("EDITOR", None)
            editor = find_editor()
            assert editor is None
