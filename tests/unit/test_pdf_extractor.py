"""Unit tests for PDF extractor module."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from local_library.core.errors import ErrorCode, ExtractionError, QualityError
from local_library.core.models import ExtractionResult
from local_library.ingestion.base import ContentExtractor
from local_library.ingestion.pdf import PdfExtractor, _WorkerCrashed


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
