"""CLI integration tests using real Library (with mocked extraction)."""

import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from local_library.cli.main import app
from local_library.core import Library

runner = CliRunner()


class TestCLIIntegration:
    """Integration tests for CLI commands with real Library."""

    @pytest.fixture
    def cli_env(self, temp_dir: Path, sample_pdf: Path):
        """Set up CLI test environment with patched paths."""
        db_path = temp_dir / "test.db"
        storage_dir = temp_dir / "storage"
        extracted_dir = temp_dir / "extracted"

        # Patch Library to use temp paths
        original_init = Library.__init__

        def patched_init(self, **kwargs):
            original_init(
                self,
                db_path=db_path,
                storage_dir=storage_dir,
                extracted_dir=extracted_dir,
            )

        with patch.object(Library, "__init__", patched_init):
            yield {"sample_pdf": sample_pdf, "temp_dir": temp_dir}

    def test_cli_add_list_show_delete(self, cli_env: dict) -> None:
        """CLI should support full workflow."""
        sample_pdf = cli_env["sample_pdf"]

        # Patch extraction in the Library class
        with patch("local_library.core.library.PdfExtractor.extract_and_validate") as mock_extract:
            mock_extract.return_value = MagicMock(text="Extracted content " * 20)

            # ADD
            result = runner.invoke(app, ["add", str(sample_pdf)])
            assert result.exit_code == 0, f"Add failed: {result.output}"
            assert "added" in result.output.lower()

            # Extract doc ID from output using regex for UUID

            uuid_pattern = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
            match = re.search(uuid_pattern, result.output)
            assert match is not None, f"Could not find UUID in: {result.output}"
            doc_id = match.group(0)

            # LIST
            result = runner.invoke(app, ["list"])
            assert result.exit_code == 0
            assert doc_id[:8] in result.output

            # SHOW
            result = runner.invoke(app, ["show", doc_id[:8]])
            assert result.exit_code == 0
            # Check for document ID in output
            assert doc_id[:8] in result.output

            # DELETE
            result = runner.invoke(app, ["delete", "--force", doc_id[:8]])
            assert result.exit_code == 0
            assert "deleted" in result.output or "deleted" in result.output.lower()

            # Verify deletion
            result = runner.invoke(app, ["list"])
            assert result.exit_code == 0
            assert "No documents" in result.output or "no documents" in result.output.lower()

    def test_cli_json_output(self, cli_env: dict) -> None:
        """CLI --json flag should produce valid JSON."""
        sample_pdf = cli_env["sample_pdf"]

        with patch("local_library.core.library.PdfExtractor.extract_and_validate") as mock_extract:
            mock_extract.return_value = MagicMock(text="Extracted content " * 20)

            # ADD with JSON
            result = runner.invoke(app, ["add", "--json", str(sample_pdf)])
            assert result.exit_code == 0

            # Just verify JSON fields are present (Rich formatting may wrap lines)
            assert '"id"' in result.output
            assert '"status"' in result.output
            assert '"is_duplicate"' in result.output

            # Extract UUID to verify it's present
            uuid_pattern = (
                r'"id":\s*"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})"'
            )
            match = re.search(uuid_pattern, result.output)
            assert match is not None, f"Could not find id in JSON output: {result.output}"
            doc_id = match.group(1)

            # LIST with JSON
            result = runner.invoke(app, ["list", "--json"])
            assert result.exit_code == 0

            # Verify JSON structure by checking for expected fields
            assert '"id"' in result.output
            assert '"status"' in result.output
            assert doc_id in result.output

    def test_cli_error_handling(self, cli_env: dict) -> None:
        """CLI should handle errors with proper exit codes."""
        # Show nonexistent document
        result = runner.invoke(app, ["show", "nonexistent"])
        assert result.exit_code == 1
        assert "not found" in result.output.lower()

        # Delete nonexistent document
        result = runner.invoke(app, ["delete", "--force", "nonexistent"])
        assert result.exit_code == 1
        assert "not found" in result.output.lower()

        # Add nonexistent file
        result = runner.invoke(app, ["add", "/nonexistent/file.pdf"])
        assert result.exit_code == 1

    def test_cli_force_mode(self, cli_env: dict) -> None:
        """CLI add --force should create failed record."""
        result = runner.invoke(app, ["add", "--force", "/nonexistent/file.pdf"])
        # Should succeed (creates failed record)
        # Exit code 2 is for extraction failure (which happens after record creation)
        # But for inaccessible files with --force, it creates failed record without extraction
        assert result.exit_code == 0 or "failed" in result.output.lower()

        # List should show the document
        result = runner.invoke(app, ["list"])
        assert "nonexistent" in result.output or "failed" in result.output.lower()


class TestAddWithMetadata:
    """Tests for add command with --metadata flag."""

    @pytest.fixture
    def cli_env_isolated(self, temp_dir: Path) -> dict:
        """Set up isolated CLI test environment for metadata tests."""
        db_path = temp_dir / "metadata_test.db"
        storage_dir = temp_dir / "metadata_storage"
        extracted_dir = temp_dir / "metadata_extracted"

        # Patch Library to use isolated temp paths
        original_init = Library.__init__

        def patched_init(self, **kwargs):
            original_init(
                self,
                db_path=db_path,
                storage_dir=storage_dir,
                extracted_dir=extracted_dir,
            )

        with patch.object(Library, "__init__", patched_init):
            yield {"temp_dir": temp_dir}

    def test_add_with_metadata_file(
        self, cli_env_isolated: dict, temp_dir: Path, sample_pdf_content: bytes
    ) -> None:
        """add --metadata should process metadata file."""
        import json

        # Create unique PDF for this test
        test_pdf = temp_dir / "test_metadata_1.pdf"
        test_pdf.write_bytes(sample_pdf_content + b"\n% metadata test 1")

        # Create metadata file
        metadata = {
            "type": "book",
            "title": "Test Book",
            "author": [{"family": "Author", "given": "Test"}],
            "issued": {"date-parts": [[2023]]},
        }
        metadata_file = temp_dir / "metadata.json"
        metadata_file.write_text(json.dumps(metadata))

        with patch("local_library.core.library.PdfExtractor") as MockExtractor:
            mock_extractor = MagicMock()
            mock_extractor.can_handle.return_value = True
            mock_extractor.extract_and_validate.return_value = MagicMock(
                text="Extracted " * 30
            )
            MockExtractor.return_value = mock_extractor

            result = runner.invoke(
                app,
                ["add", str(test_pdf), "--metadata", str(metadata_file)],
            )

        assert result.exit_code == 0
        assert "added" in result.output or "Author2023Test" in result.output

    def test_add_with_invalid_json_file(
        self, cli_env_isolated: dict, temp_dir: Path, sample_pdf_content: bytes
    ) -> None:
        """add --metadata with invalid JSON should fail."""
        # Create unique PDF for this test
        test_pdf = temp_dir / "test_metadata_2.pdf"
        test_pdf.write_bytes(sample_pdf_content + b"\n% metadata test 2")

        # Create invalid JSON file
        invalid_file = temp_dir / "invalid.json"
        invalid_file.write_text("not valid json {")

        result = runner.invoke(
            app,
            ["add", str(test_pdf), "--metadata", str(invalid_file)],
        )

        assert result.exit_code == 1
        assert "invalid JSON" in result.output or "error" in result.output

    def test_add_with_invalid_metadata_schema(
        self, cli_env_isolated: dict, temp_dir: Path, sample_pdf_content: bytes
    ) -> None:
        """add --metadata with invalid CSL-JSON should fail."""
        import json

        # Create unique PDF for this test
        test_pdf = temp_dir / "test_metadata_3.pdf"
        test_pdf.write_bytes(sample_pdf_content + b"\n% metadata test 3")

        # Create metadata with missing required 'type'
        metadata = {"title": "Missing Type Field"}
        metadata_file = temp_dir / "bad_metadata.json"
        metadata_file.write_text(json.dumps(metadata))

        with patch("local_library.core.library.PdfExtractor") as MockExtractor:
            mock_extractor = MagicMock()
            mock_extractor.can_handle.return_value = True
            mock_extractor.extract_and_validate.return_value = MagicMock(
                text="Extracted " * 30
            )
            MockExtractor.return_value = mock_extractor

            result = runner.invoke(
                app,
                ["add", str(test_pdf), "--metadata", str(metadata_file)],
            )

        assert result.exit_code == 1
        assert "metadata" in result.output.lower() or "error" in result.output.lower()
