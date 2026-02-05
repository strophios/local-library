"""Unit tests for embed CLI command."""

from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from local_library.cli.main import app
from local_library.core.vec_extension import is_vec_available

runner = CliRunner()


class TestEmbedCommandHelp:
    """Tests for embed command help and arguments."""

    def test_embed_help(self) -> None:
        """embed --help should show usage information."""
        result = runner.invoke(app, ["embed", "--help"])

        assert result.exit_code == 0
        assert "Compute and store embeddings" in result.output
        assert "--pending" in result.output
        assert "--all" in result.output
        assert "--force" in result.output
        assert "--dry-run" in result.output

    def test_embed_no_args_fails(self) -> None:
        """embed without args should fail with helpful error."""
        with patch("local_library.cli.embed.is_vec_available", return_value=True):
            result = runner.invoke(app, ["embed"])

        assert result.exit_code == 1
        assert "must specify identifier, --pending, or --all" in result.output

    def test_embed_identifier_with_pending_fails(self) -> None:
        """embed with both identifier and --pending should fail."""
        with patch("local_library.cli.embed.is_vec_available", return_value=True):
            result = runner.invoke(app, ["embed", "abc123", "--pending"])

        assert result.exit_code == 1
        assert "cannot specify identifier with --pending or --all" in result.output


@pytest.mark.skipif(not is_vec_available(), reason="sqlite-vec not available")
class TestEmbedCommandExecution:
    """Tests for embed command execution."""

    def test_embed_single_document_dry_run(self) -> None:
        """embed --dry-run should show what would be embedded."""
        with patch("local_library.cli.embed.Library") as MockLibrary:
            mock_lib = MagicMock()
            mock_lib.__enter__ = MagicMock(return_value=mock_lib)
            mock_lib.__exit__ = MagicMock(return_value=False)
            mock_doc = MagicMock()
            mock_doc.id = "test-id-123"
            mock_doc.citekey = None
            mock_doc.embedding_status.value = "pending"
            mock_lib.get.return_value = mock_doc
            MockLibrary.return_value = mock_lib

            with patch("local_library.cli.embed.resolve_identifier", return_value=mock_doc):
                result = runner.invoke(app, ["embed", "test-id", "--dry-run"])

        assert result.exit_code == 0
        assert "dry run" in result.output

    def test_embed_pending_dry_run(self) -> None:
        """embed --pending --dry-run should show count."""
        with patch("local_library.cli.embed.Library") as MockLibrary:
            mock_lib = MagicMock()
            mock_lib.__enter__ = MagicMock(return_value=mock_lib)
            mock_lib.__exit__ = MagicMock(return_value=False)
            mock_lib.conn = MagicMock()
            MockLibrary.return_value = mock_lib

            with patch(
                "local_library.embeddings.storage.get_documents_needing_embedding",
                return_value=[],
            ):
                result = runner.invoke(app, ["embed", "--pending", "--dry-run"])

        assert result.exit_code == 0
        assert "would embed 0 documents" in result.output


class TestEmbedVecUnavailable:
    """Tests for when sqlite-vec is not available."""

    def test_embed_without_vec_fails(self) -> None:
        """embed should fail gracefully when sqlite-vec unavailable."""
        with patch("local_library.cli.embed.is_vec_available", return_value=False):
            result = runner.invoke(app, ["embed", "--pending"])

        assert result.exit_code == 1
        assert "sqlite-vec extension not available" in result.output


class TestAddSkipEmbed:
    """Tests for --skip-embed flag on add command."""

    def test_add_has_skip_embed_flag(self) -> None:
        """add --help should show --skip-embed option."""
        result = runner.invoke(app, ["add", "--help"])

        assert result.exit_code == 0
        assert "--skip-embed" in result.output


class TestZoteroImportSkipEmbed:
    """Tests for --skip-embed flag on zotero import command."""

    def test_zotero_import_has_skip_embed_flag(self) -> None:
        """zotero import --help should show --skip-embed option."""
        result = runner.invoke(app, ["zotero", "import", "--help"])

        assert result.exit_code == 0
        assert "--skip-embed" in result.output
