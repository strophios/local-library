"""Unit tests for PDF extractor module."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pymupdf as fitz_lib
import pytest

from local_library.core.errors import ErrorCode, ExtractionError, QualityError
from local_library.core.models import ExtractionResult
from local_library.ingestion.base import ContentExtractor
from local_library.ingestion.pdf import (
    PdfExtractor,
    PreCheckResult,
    _compute_dynamic_timeout,
    _precheck_pdf,
    _WorkerCrashed,
)


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

    # --- extract tests (mocked at worker boundary) ---

    def test_extract_returns_extraction_result(
        self, extractor: PdfExtractor, sample_pdf: Path
    ) -> None:
        """extract should return ExtractionResult with text from worker."""
        worker_response = {
            "status": "ok",
            "text": "Extracted markdown content",
            "metadata": {"page_stats": []},
        }

        with patch.object(extractor, "_ensure_worker_running"):
            with patch.object(extractor, "_send_request", return_value=worker_response):
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
        worker_response = {
            "status": "error",
            "error_type": "empty_output",
            "message": "extraction produced empty output",
        }

        with patch.object(extractor, "_ensure_worker_running"):
            with patch.object(extractor, "_send_request", return_value=worker_response):
                with pytest.raises(ExtractionError) as exc_info:
                    extractor.extract(sample_pdf)

                assert exc_info.value.code == ErrorCode.EXTRACTION_EMPTY_OUTPUT

    def test_extract_raises_for_worker_error(
        self, extractor: PdfExtractor, sample_pdf: Path
    ) -> None:
        """extract should raise ExtractionError for worker extraction failure."""
        worker_response = {
            "status": "error",
            "error_type": "extraction_failed",
            "message": "marker crash",
        }

        with patch.object(extractor, "_ensure_worker_running"):
            with patch.object(extractor, "_send_request", return_value=worker_response):
                with pytest.raises(ExtractionError) as exc_info:
                    extractor.extract(sample_pdf)

                assert exc_info.value.code == ErrorCode.EXTRACTION_MARKER_CRASH

    # --- CPU fallback tests ---

    def test_extract_retries_on_cpu_after_crash(
        self, extractor: PdfExtractor, sample_pdf: Path
    ) -> None:
        """extract should retry on CPU when MPS worker crashes."""
        cpu_response = {
            "status": "ok",
            "text": "Extracted on CPU",
            "metadata": {},
        }

        # First call crashes, CPU retry succeeds
        with patch.object(extractor, "_ensure_worker_running"):
            with patch.object(
                extractor,
                "_send_request",
                side_effect=[
                    _WorkerCrashed(-11, str(sample_pdf)),
                    cpu_response,
                ],
            ):
                with patch.object(extractor, "_stop_worker"):
                    result = extractor.extract(sample_pdf)

        assert result.text == "Extracted on CPU"

    def test_extract_raises_when_both_mps_and_cpu_crash(
        self, extractor: PdfExtractor, sample_pdf: Path
    ) -> None:
        """extract should raise when both MPS and CPU crash."""
        with patch.object(extractor, "_ensure_worker_running"):
            with patch.object(
                extractor,
                "_send_request",
                side_effect=_WorkerCrashed(-11, str(sample_pdf)),
            ):
                with pytest.raises(ExtractionError) as exc_info:
                    extractor.extract(sample_pdf)

                assert "both MPS and CPU" in str(exc_info.value)

    # --- extract_and_validate tests ---

    def test_extract_and_validate_passes_for_good_content(
        self, extractor: PdfExtractor, sample_pdf: Path
    ) -> None:
        """extract_and_validate should pass for content meeting thresholds."""
        good_content = "x" * 200  # Well above min_length
        worker_response = {"status": "ok", "text": good_content, "metadata": {}}

        with patch.object(extractor, "_ensure_worker_running"):
            with patch.object(extractor, "_send_request", return_value=worker_response):
                result = extractor.extract_and_validate(sample_pdf)

        assert result.character_count >= 100

    def test_extract_and_validate_raises_for_short_content(
        self, extractor: PdfExtractor, sample_pdf: Path
    ) -> None:
        """extract_and_validate should raise QualityError for short content."""
        short_content = "short"  # Below min_length
        worker_response = {"status": "ok", "text": short_content, "metadata": {}}

        with patch.object(extractor, "_ensure_worker_running"):
            with patch.object(extractor, "_send_request", return_value=worker_response):
                with pytest.raises(QualityError) as exc_info:
                    extractor.extract_and_validate(sample_pdf)

                assert exc_info.value.code == ErrorCode.QUALITY_TOO_SHORT

    def test_extract_and_validate_raises_for_low_printable(
        self, extractor: PdfExtractor, sample_pdf: Path
    ) -> None:
        """extract_and_validate should raise QualityError for garbled output."""
        # Content with many non-printable characters
        garbled_content = "Hello" + "\x00" * 200
        worker_response = {"status": "ok", "text": garbled_content, "metadata": {}}

        with patch.object(extractor, "_ensure_worker_running"):
            with patch.object(extractor, "_send_request", return_value=worker_response):
                with pytest.raises(QualityError) as exc_info:
                    extractor.extract_and_validate(sample_pdf)

                assert exc_info.value.code == ErrorCode.QUALITY_LOW_PRINTABLE

    def test_extract_and_validate_uses_custom_thresholds(
        self, extractor: PdfExtractor, sample_pdf: Path
    ) -> None:
        """extract_and_validate should respect custom thresholds."""
        content = "x" * 50  # Would fail default min_length=100
        worker_response = {"status": "ok", "text": content, "metadata": {}}

        with patch.object(extractor, "_ensure_worker_running"):
            with patch.object(extractor, "_send_request", return_value=worker_response):
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
    """Tests for PdfExtractor LLM configuration passed to worker."""

    def test_llm_enabled_default_false(self) -> None:
        """PdfExtractor should default to llm_enabled=False."""
        extractor = PdfExtractor(lazy_load=True)
        assert extractor._llm_enabled is False

    def test_llm_enabled_can_be_set_true(self) -> None:
        """PdfExtractor should accept llm_enabled=True."""
        extractor = PdfExtractor(lazy_load=True, llm_enabled=True)
        assert extractor._llm_enabled is True

    def test_worker_command_includes_llm_flag_when_enabled(self) -> None:
        """Worker command should include --llm flag when llm_enabled=True."""
        extractor = PdfExtractor(lazy_load=True, llm_enabled=True)

        with patch("subprocess.Popen") as mock_popen:
            mock_proc = MagicMock()
            mock_proc.stdout.readline.return_value = '{"status": "ready"}\n'
            mock_proc.poll.return_value = None
            mock_popen.return_value = mock_proc

            extractor._start_worker()

            # Verify --llm flag was in the command
            cmd = mock_popen.call_args[0][0]
            assert "--llm" in cmd

    def test_worker_command_omits_llm_flag_when_disabled(self) -> None:
        """Worker command should not include --llm flag when llm_enabled=False."""
        extractor = PdfExtractor(lazy_load=True, llm_enabled=False)

        with patch("subprocess.Popen") as mock_popen:
            mock_proc = MagicMock()
            mock_proc.stdout.readline.return_value = '{"status": "ready"}\n'
            mock_proc.poll.return_value = None
            mock_popen.return_value = mock_proc

            extractor._start_worker()

            # Verify --llm flag was NOT in the command
            cmd = mock_popen.call_args[0][0]
            assert "--llm" not in cmd

    def test_worker_started_with_cpu_device_env(self) -> None:
        """Worker should receive TORCH_DEVICE=cpu when device='cpu'."""
        extractor = PdfExtractor(lazy_load=True)

        with patch("subprocess.Popen") as mock_popen:
            mock_proc = MagicMock()
            mock_proc.stdout.readline.return_value = '{"status": "ready"}\n'
            mock_proc.poll.return_value = None
            mock_popen.return_value = mock_proc

            extractor._start_worker(device="cpu")

            # Verify TORCH_DEVICE was set in env
            env = mock_popen.call_args[1].get("env", {})
            assert env.get("TORCH_DEVICE") == "cpu"

    def test_worker_started_without_device_env_by_default(self) -> None:
        """Worker should not have TORCH_DEVICE set when device=None (auto)."""
        extractor = PdfExtractor(lazy_load=True)

        with patch("subprocess.Popen") as mock_popen:
            mock_proc = MagicMock()
            mock_proc.stdout.readline.return_value = '{"status": "ready"}\n'
            mock_proc.poll.return_value = None
            mock_popen.return_value = mock_proc

            extractor._start_worker(device=None)

            # Verify env was not overridden (None = inherit)
            env = mock_popen.call_args[1].get("env")
            assert env is None


class TestWorkerLifecycle:
    """Tests for worker subprocess lifecycle management."""

    def test_close_stops_worker(self) -> None:
        """close() should terminate the worker subprocess."""
        extractor = PdfExtractor(lazy_load=True)

        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.stdin = MagicMock()
        extractor._worker = mock_proc

        extractor.close()

        mock_proc.stdin.close.assert_called_once()
        assert extractor._worker is None

    def test_ensure_worker_reuses_running_worker(self) -> None:
        """_ensure_worker_running should reuse an active worker."""
        extractor = PdfExtractor(lazy_load=True)

        mock_proc = MagicMock()
        mock_proc.poll.return_value = None  # Still running
        extractor._worker = mock_proc
        extractor._worker_device = None

        with patch.object(extractor, "_start_worker") as mock_start:
            extractor._ensure_worker_running(device=None)

            mock_start.assert_not_called()

    def test_ensure_worker_restarts_on_device_change(self) -> None:
        """_ensure_worker_running should restart worker if device changes."""
        extractor = PdfExtractor(lazy_load=True)

        mock_proc = MagicMock()
        mock_proc.poll.return_value = None  # Still running
        extractor._worker = mock_proc
        extractor._worker_device = None  # Currently on auto/MPS

        new_proc = MagicMock()
        new_proc.poll.return_value = None

        with patch.object(extractor, "_stop_worker") as mock_stop:
            with patch.object(extractor, "_start_worker", return_value=new_proc):
                extractor._ensure_worker_running(device="cpu")

                mock_stop.assert_called_once()

    def test_ensure_worker_starts_new_if_dead(self) -> None:
        """_ensure_worker_running should start new worker if current is dead."""
        extractor = PdfExtractor(lazy_load=True)

        mock_proc = MagicMock()
        mock_proc.poll.return_value = -11  # Dead (segfault)
        extractor._worker = mock_proc

        new_proc = MagicMock()
        new_proc.poll.return_value = None

        with patch.object(extractor, "_start_worker", return_value=new_proc):
            extractor._ensure_worker_running()

        assert extractor._worker is new_proc


class TestPreCheckTimeoutComputation:
    """Tests for _compute_dynamic_timeout() pure function."""

    # --- Text-extractable documents ---

    def test_text_pdf_short_uses_minimum(self) -> None:
        """Short text PDFs should use the 900s minimum."""
        result = _compute_dynamic_timeout(page_count=10, has_extractable_text=True)
        assert result == 900

    def test_text_pdf_medium_scales_linearly(self) -> None:
        """Medium text PDFs should scale at 5s/page when above minimum."""
        result = _compute_dynamic_timeout(page_count=200, has_extractable_text=True)
        assert result == 1000  # 200 * 5 = 1000 > 900

    def test_text_pdf_long_scales_linearly(self) -> None:
        """Long text PDFs should scale at 5s/page."""
        result = _compute_dynamic_timeout(page_count=500, has_extractable_text=True)
        assert result == 2500  # 500 * 5

    # --- Image-only documents ---

    def test_image_pdf_short_uses_minimum(self) -> None:
        """Short image PDFs should use the 1800s minimum."""
        result = _compute_dynamic_timeout(page_count=10, has_extractable_text=False)
        assert result == 1800

    def test_image_pdf_medium_scales_linearly(self) -> None:
        """Medium image PDFs should scale at 45s/page when above minimum."""
        result = _compute_dynamic_timeout(page_count=50, has_extractable_text=False)
        assert result == 2250  # 50 * 45 = 2250 > 1800

    def test_image_pdf_long_scales_linearly(self) -> None:
        """Long image PDFs should scale at 45s/page."""
        result = _compute_dynamic_timeout(page_count=100, has_extractable_text=False)
        assert result == 4500  # 100 * 45

    # --- Clamping ---

    def test_capped_at_max_timeout(self) -> None:
        """Timeout should be capped at max_timeout."""
        result = _compute_dynamic_timeout(page_count=10000, has_extractable_text=True)
        assert result == 14400  # Default max (4 hours)

    def test_image_pdf_capped_at_max_timeout(self) -> None:
        """Image PDF timeout should be capped at max_timeout."""
        result = _compute_dynamic_timeout(page_count=1000, has_extractable_text=False)
        assert result == 14400  # 1000 * 45 = 45000, capped at 14400

    def test_custom_max_timeout(self) -> None:
        """Custom max_timeout should cap the result."""
        result = _compute_dynamic_timeout(
            page_count=500, has_extractable_text=True, max_timeout=2000
        )
        assert result == 2000  # 500 * 5 = 2500, capped at 2000

    def test_custom_base_timeout_raises_floor(self) -> None:
        """Custom base_timeout should raise the floor above type minimum."""
        result = _compute_dynamic_timeout(
            page_count=10, has_extractable_text=True, base_timeout=3600
        )
        assert result == 3600  # base_timeout > type minimum (900)

    def test_zero_pages_uses_type_minimum(self) -> None:
        """Zero-page PDF should use type-specific minimum."""
        result = _compute_dynamic_timeout(page_count=0, has_extractable_text=True)
        assert result == 900

    def test_zero_pages_image_uses_type_minimum(self) -> None:
        """Zero-page image PDF should use image minimum."""
        result = _compute_dynamic_timeout(page_count=0, has_extractable_text=False)
        assert result == 1800


class TestPreCheckResult:
    """Tests for PreCheckResult dataclass."""

    def test_creates_frozen_dataclass(self) -> None:
        """PreCheckResult should be immutable."""
        result = PreCheckResult(page_count=10, has_extractable_text=True, computed_timeout=900)
        assert result.page_count == 10
        assert result.has_extractable_text is True
        assert result.computed_timeout == 900

        with pytest.raises(AttributeError):
            result.page_count = 20  # type: ignore[misc]


class TestPreCheckPdf:
    """Tests for _precheck_pdf() function using real pymupdf PDFs."""

    @pytest.fixture
    def text_pdf(self, temp_dir: Path) -> Path:
        """Create a valid PDF with extractable text (3 pages)."""
        pdf_path = temp_dir / "text_document.pdf"
        doc = fitz_lib.open()
        for i in range(3):
            page = doc.new_page()
            # Insert enough text to exceed the 100-char threshold per page
            page.insert_text(
                (50, 50),
                f"Page {i + 1}: This is a test document with enough text content "
                "to be detected as having extractable text by the pre-check function. "
                "The quick brown fox jumps over the lazy dog.",
            )
        doc.save(str(pdf_path))
        doc.close()
        return pdf_path

    @pytest.fixture
    def image_only_pdf(self, temp_dir: Path) -> Path:
        """Create a valid PDF with no extractable text (blank pages)."""
        pdf_path = temp_dir / "image_only.pdf"
        doc = fitz_lib.open()
        for _ in range(5):
            doc.new_page()  # Blank pages -- no text
        doc.save(str(pdf_path))
        doc.close()
        return pdf_path

    @pytest.fixture
    def minimal_text_pdf(self, temp_dir: Path) -> Path:
        """Create a PDF with text below the 100-char threshold."""
        pdf_path = temp_dir / "minimal_text.pdf"
        doc = fitz_lib.open()
        page = doc.new_page()
        page.insert_text((50, 50), "Short")  # Well under 100 chars
        doc.save(str(pdf_path))
        doc.close()
        return pdf_path

    def test_text_pdf_detected(self, text_pdf: Path) -> None:
        """Pre-check should detect text-extractable PDFs."""
        result = _precheck_pdf(text_pdf)

        assert result.page_count == 3
        assert result.has_extractable_text is True
        assert result.computed_timeout == 900  # max(900, 3*5=15) = 900

    def test_image_only_pdf_detected(self, image_only_pdf: Path) -> None:
        """Pre-check should detect image-only PDFs."""
        result = _precheck_pdf(image_only_pdf)

        assert result.page_count == 5
        assert result.has_extractable_text is False
        assert result.computed_timeout == 1800  # max(1800, 5*45=225) = 1800

    def test_minimal_text_below_threshold(self, minimal_text_pdf: Path) -> None:
        """Pre-check should treat PDFs with <100 chars as not text-extractable."""
        result = _precheck_pdf(minimal_text_pdf)

        assert result.page_count == 1
        assert result.has_extractable_text is False
        assert result.computed_timeout == 1800  # Treated as image-only

    def test_passes_timeout_parameters(self, text_pdf: Path) -> None:
        """Pre-check should forward base and max timeout to computation."""
        result = _precheck_pdf(text_pdf, base_timeout=3600, max_timeout=7200)

        assert result.computed_timeout == 3600  # base > type minimum


class TestExtractWithPreCheck:
    """Tests for PdfExtractor.extract() with pre-check integration."""

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

    def test_extract_uses_precheck_timeout(self, extractor: PdfExtractor, sample_pdf: Path) -> None:
        """extract() should pass pre-check timeout to _send_request."""
        precheck = PreCheckResult(page_count=200, has_extractable_text=True, computed_timeout=1000)
        worker_response = {
            "status": "ok",
            "text": "Extracted content",
            "metadata": {},
        }

        with patch("local_library.ingestion.pdf._precheck_pdf", return_value=precheck):
            with patch.object(extractor, "_ensure_worker_running"):
                with patch.object(
                    extractor, "_send_request", return_value=worker_response
                ) as mock_send:
                    extractor.extract(sample_pdf)

        # Verify timeout was passed through
        mock_send.assert_called_once()
        _, kwargs = mock_send.call_args
        assert kwargs.get("timeout") == 1000

    def test_extract_falls_back_to_base_timeout_on_precheck_failure(
        self, extractor: PdfExtractor, sample_pdf: Path
    ) -> None:
        """extract() should use base timeout if pre-check fails."""
        worker_response = {
            "status": "ok",
            "text": "Extracted content",
            "metadata": {},
        }

        with patch(
            "local_library.ingestion.pdf._precheck_pdf",
            side_effect=Exception("corrupt PDF"),
        ):
            with patch.object(extractor, "_ensure_worker_running"):
                with patch.object(
                    extractor, "_send_request", return_value=worker_response
                ) as mock_send:
                    extractor.extract(sample_pdf)

        # Should fall back to base timeout (900)
        _, kwargs = mock_send.call_args
        assert kwargs.get("timeout") == 900

    def test_max_extraction_timeout_constructor_parameter(self) -> None:
        """PdfExtractor should accept max_extraction_timeout parameter."""
        extractor = PdfExtractor(
            lazy_load=True, extraction_timeout=1800, max_extraction_timeout=7200
        )
        assert extractor._extraction_timeout == 1800
        assert extractor._max_extraction_timeout == 7200

    def test_precheck_result_in_extraction_metadata(
        self, extractor: PdfExtractor, sample_pdf: Path
    ) -> None:
        """extract() should include pre-check info in result metadata."""
        precheck = PreCheckResult(page_count=42, has_extractable_text=True, computed_timeout=900)
        worker_response = {
            "status": "ok",
            "text": "Extracted content with enough length " * 5,
            "metadata": {"page_stats": []},
        }

        with patch("local_library.ingestion.pdf._precheck_pdf", return_value=precheck):
            with patch.object(extractor, "_ensure_worker_running"):
                with patch.object(extractor, "_send_request", return_value=worker_response):
                    result = extractor.extract(sample_pdf)

        assert result.metadata.get("precheck_page_count") == 42
        assert result.metadata.get("precheck_has_text") is True


class TestSendRequestTimeout:
    """Tests for _send_request timeout parameter."""

    def test_send_request_uses_provided_timeout(self) -> None:
        """_send_request should use explicit timeout over self._extraction_timeout."""
        extractor = PdfExtractor(lazy_load=True, extraction_timeout=900)

        mock_proc = MagicMock()
        mock_proc.stdin = MagicMock()
        mock_proc.stdout = MagicMock()
        mock_proc.stdout.readline.return_value = (
            '{"status": "ok", "text": "test", "metadata": {}}\n'
        )
        mock_proc.poll.return_value = None
        extractor._worker = mock_proc
        extractor._worker_device = None

        # Extraction completes immediately since readline returns right away
        response = extractor._send_request("/fake/path.pdf", timeout=60)
        assert response["status"] == "ok"

    def test_send_request_defaults_to_instance_timeout(self) -> None:
        """_send_request should use self._extraction_timeout when timeout=None."""
        extractor = PdfExtractor(lazy_load=True, extraction_timeout=900)

        mock_proc = MagicMock()
        mock_proc.stdin = MagicMock()
        mock_proc.stdout = MagicMock()
        mock_proc.stdout.readline.return_value = (
            '{"status": "ok", "text": "test", "metadata": {}}\n'
        )
        mock_proc.poll.return_value = None
        extractor._worker = mock_proc
        extractor._worker_device = None

        response = extractor._send_request("/fake/path.pdf")
        assert response["status"] == "ok"
