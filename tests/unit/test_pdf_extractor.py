"""Unit tests for PDF extractor module."""

import os
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from local_library.core.errors import ErrorCode, ExtractionError, QualityError
from local_library.core.models import ExtractionResult
from local_library.ingestion.base import ContentExtractor
from local_library.ingestion.pdf import PdfExtractor


class TestPdfExtractor:
    """Tests for PdfExtractor class."""

    @pytest.fixture
    def extractor(self) -> PdfExtractor:
        """Provide a PdfExtractor with lazy loading."""
        return PdfExtractor(lazy_load=True)

    @pytest.fixture
    def sample_pdf(self, temp_dir: Path) -> Path:
        """Create a sample PDF file for testing."""
        pdf_path = temp_dir / "sample.pdf"
        pdf_path.write_bytes(b"%PDF-1.4 test content")
        return pdf_path

    # --- can_handle tests ---

    def test_can_handle_pdf_file(self, extractor: PdfExtractor, sample_pdf: Path) -> None:
        """can_handle should return True for PDF files."""
        assert extractor.can_handle(sample_pdf) is True

    def test_can_handle_uppercase_extension(self, extractor: PdfExtractor, temp_dir: Path) -> None:
        """can_handle should handle uppercase extensions."""
        pdf_path = temp_dir / "sample.PDF"
        pdf_path.write_bytes(b"%PDF-1.4")

        assert extractor.can_handle(pdf_path) is True

    def test_cannot_handle_non_pdf(self, extractor: PdfExtractor, temp_dir: Path) -> None:
        """can_handle should return False for non-PDF files."""
        txt_path = temp_dir / "sample.txt"
        txt_path.write_text("test")

        assert extractor.can_handle(txt_path) is False

    # --- extract tests (mocked) ---

    def test_extract_returns_extraction_result(
        self, extractor: PdfExtractor, sample_pdf: Path
    ) -> None:
        """extract should return ExtractionResult with text."""
        mock_converter = MagicMock()
        mock_rendered = MagicMock()
        mock_converter.return_value = mock_rendered

        with patch("marker.converters.pdf.PdfConverter", return_value=mock_converter):
            with patch("marker.models.create_model_dict", return_value={}):
                with patch(
                    "marker.output.text_from_rendered",
                    return_value=("Extracted markdown content", {"title": "Test"}, []),
                ):
                    # Need to reload the extractor to use mocked imports
                    extractor._converter = mock_converter
                    result = extractor.extract(sample_pdf)

        assert isinstance(result, ExtractionResult)
        assert "Extracted markdown content" in result.text

    def test_extract_raises_for_nonexistent_file(
        self, extractor: PdfExtractor, temp_dir: Path
    ) -> None:
        """extract should raise ExtractionError for nonexistent file."""
        nonexistent = temp_dir / "nonexistent.pdf"

        with pytest.raises(ExtractionError) as exc_info:
            extractor.extract(nonexistent)

        assert exc_info.value.code == ErrorCode.EXTRACTION_MARKER_CRASH

    def test_extract_raises_for_empty_output(
        self, extractor: PdfExtractor, sample_pdf: Path
    ) -> None:
        """extract should raise ExtractionError for empty extraction."""
        mock_converter = MagicMock()
        mock_converter.return_value = MagicMock()

        with patch(
            "marker.output.text_from_rendered",
            return_value=("", {}, []),
        ):
            extractor._converter = mock_converter

            with pytest.raises(ExtractionError) as exc_info:
                extractor.extract(sample_pdf)

            assert exc_info.value.code == ErrorCode.EXTRACTION_EMPTY_OUTPUT

    # --- extract_and_validate tests ---

    def test_extract_and_validate_passes_for_good_content(
        self, extractor: PdfExtractor, sample_pdf: Path
    ) -> None:
        """extract_and_validate should pass for content meeting thresholds."""
        mock_converter = MagicMock()
        mock_converter.return_value = MagicMock()

        good_content = "x" * 200  # Well above min_length

        with patch(
            "marker.output.text_from_rendered",
            return_value=(good_content, {}, []),
        ):
            extractor._converter = mock_converter
            result = extractor.extract_and_validate(sample_pdf)

        assert result.character_count >= 100

    def test_extract_and_validate_raises_for_short_content(
        self, extractor: PdfExtractor, sample_pdf: Path
    ) -> None:
        """extract_and_validate should raise QualityError for short content."""
        mock_converter = MagicMock()
        mock_converter.return_value = MagicMock()

        short_content = "short"  # Below min_length

        with patch(
            "marker.output.text_from_rendered",
            return_value=(short_content, {}, []),
        ):
            extractor._converter = mock_converter

            with pytest.raises(QualityError) as exc_info:
                extractor.extract_and_validate(sample_pdf)

            assert exc_info.value.code == ErrorCode.QUALITY_TOO_SHORT

    def test_extract_and_validate_raises_for_low_printable(
        self, extractor: PdfExtractor, sample_pdf: Path
    ) -> None:
        """extract_and_validate should raise QualityError for garbled output."""
        mock_converter = MagicMock()
        mock_converter.return_value = MagicMock()

        # Content with many non-printable characters
        garbled_content = "Hello" + "\x00" * 200

        with patch(
            "marker.output.text_from_rendered",
            return_value=(garbled_content, {}, []),
        ):
            extractor._converter = mock_converter

            with pytest.raises(QualityError) as exc_info:
                extractor.extract_and_validate(sample_pdf)

            assert exc_info.value.code == ErrorCode.QUALITY_LOW_PRINTABLE

    def test_extract_and_validate_uses_custom_thresholds(
        self, extractor: PdfExtractor, sample_pdf: Path
    ) -> None:
        """extract_and_validate should respect custom thresholds."""
        mock_converter = MagicMock()
        mock_converter.return_value = MagicMock()

        content = "x" * 50  # Would fail default min_length=100

        with patch(
            "marker.output.text_from_rendered",
            return_value=(content, {}, []),
        ):
            extractor._converter = mock_converter

            # Should pass with custom lower threshold
            result = extractor.extract_and_validate(
                sample_pdf, min_length=10, min_printable_ratio=0.5
            )

            assert result.character_count == 50


class TestProtocolConformance:
    """Tests that PdfExtractor conforms to ContentExtractor protocol."""

    def test_pdf_extractor_conforms_to_protocol(self) -> None:
        """PdfExtractor should satisfy ContentExtractor protocol."""
        extractor = PdfExtractor(lazy_load=True)

        # runtime_checkable allows isinstance checks
        assert isinstance(extractor, ContentExtractor)


class TestLLMConfiguration:
    """Tests for PdfExtractor LLM-enhanced extraction configuration."""

    @pytest.fixture
    def sample_pdf(self, temp_dir: Path) -> Path:
        """Create a sample PDF file for testing."""
        pdf_path = temp_dir / "sample.pdf"
        pdf_path.write_bytes(b"%PDF-1.4 test content")
        return pdf_path

    def test_llm_enabled_default_false(self) -> None:
        """PdfExtractor should default to llm_enabled=False."""
        extractor = PdfExtractor(lazy_load=True)
        assert extractor._llm_enabled is False

    def test_llm_enabled_can_be_set_true(self) -> None:
        """PdfExtractor should accept llm_enabled=True."""
        extractor = PdfExtractor(lazy_load=True, llm_enabled=True)
        assert extractor._llm_enabled is True

    def test_llm_config_passed_to_converter_when_enabled(
        self, sample_pdf: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When llm_enabled=True and API key present, LLM config should be passed to Marker."""
        # Set the API key
        monkeypatch.setenv("GEMINI_API_KEY", "test-api-key")

        # Track what config was passed to ConfigParser
        captured_config: dict[str, Any] = {}

        mock_config_parser = MagicMock()
        mock_config_parser.generate_config_dict.return_value = {"mocked": True}

        def capture_config(config: dict[str, Any]) -> MagicMock:
            captured_config.update(config)
            return mock_config_parser

        mock_converter = MagicMock()
        mock_converter.return_value = MagicMock()

        with patch("marker.config.parser.ConfigParser", side_effect=capture_config):
            with patch("marker.converters.pdf.PdfConverter", return_value=mock_converter):
                with patch("marker.models.create_model_dict", return_value={}):
                    extractor = PdfExtractor(lazy_load=True, llm_enabled=True)
                    extractor._ensure_models_loaded()

        # Verify LLM config was included
        assert captured_config.get("use_llm") is True
        assert captured_config.get("llm_service") == "marker.services.gemini.GoogleGeminiService"
        assert captured_config.get("redo_inline_math") is True
        assert captured_config.get("disable_image_extraction") is True

    def test_llm_config_not_passed_when_disabled(
        self, sample_pdf: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When llm_enabled=False, LLM config should not be passed to Marker."""
        # Set API key to prove it's not about the key
        monkeypatch.setenv("GEMINI_API_KEY", "test-api-key")

        captured_config: dict[str, Any] = {}

        mock_config_parser = MagicMock()
        mock_config_parser.generate_config_dict.return_value = {"mocked": True}

        def capture_config(config: dict[str, Any]) -> MagicMock:
            captured_config.update(config)
            return mock_config_parser

        mock_converter = MagicMock()

        with patch("marker.config.parser.ConfigParser", side_effect=capture_config):
            with patch("marker.converters.pdf.PdfConverter", return_value=mock_converter):
                with patch("marker.models.create_model_dict", return_value={}):
                    extractor = PdfExtractor(lazy_load=True, llm_enabled=False)
                    extractor._ensure_models_loaded()

        # Verify LLM config was NOT included
        assert "use_llm" not in captured_config

    def test_llm_config_not_passed_when_no_api_key(
        self, sample_pdf: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When llm_enabled=True but no API key, LLM config should not be passed."""
        # Ensure no API key
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

        captured_config: dict[str, Any] = {}

        mock_config_parser = MagicMock()
        mock_config_parser.generate_config_dict.return_value = {"mocked": True}

        def capture_config(config: dict[str, Any]) -> MagicMock:
            captured_config.update(config)
            return mock_config_parser

        mock_converter = MagicMock()

        with patch("marker.config.parser.ConfigParser", side_effect=capture_config):
            with patch("marker.converters.pdf.PdfConverter", return_value=mock_converter):
                with patch("marker.models.create_model_dict", return_value={}):
                    extractor = PdfExtractor(lazy_load=True, llm_enabled=True)
                    extractor._ensure_models_loaded()

        # Verify LLM config was NOT included (graceful fallback)
        assert "use_llm" not in captured_config

    def test_google_api_key_set_from_gemini_key(
        self, sample_pdf: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When llm_enabled=True, GOOGLE_API_KEY should be set from GEMINI_API_KEY."""
        monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
        # Ensure GOOGLE_API_KEY is not set initially
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

        mock_config_parser = MagicMock()
        mock_config_parser.generate_config_dict.return_value = {}
        mock_converter = MagicMock()

        with patch("marker.config.parser.ConfigParser", return_value=mock_config_parser):
            with patch("marker.converters.pdf.PdfConverter", return_value=mock_converter):
                with patch("marker.models.create_model_dict", return_value={}):
                    extractor = PdfExtractor(lazy_load=True, llm_enabled=True)
                    extractor._ensure_models_loaded()

        # Verify GOOGLE_API_KEY was set
        assert os.environ.get("GOOGLE_API_KEY") == "test-gemini-key"
