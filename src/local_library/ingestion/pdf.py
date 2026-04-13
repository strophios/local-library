"""PDF extraction implementation using Marker via worker subprocess.

Extraction runs in a persistent worker subprocess to isolate segfaults
(e.g., surya MPS crashes on specific tensor shapes). If the worker crashes,
it is restarted with TORCH_DEVICE=cpu for the failed document, then
restarted on MPS for subsequent documents.
"""

# pattern: Imperative Shell

import json
import logging
import subprocess
import sys
import threading
import time
from pathlib import Path

from local_library.core.errors import ErrorCode, ExtractionError, QualityError
from local_library.core.models import ExtractionResult

logger = logging.getLogger(__name__)

# Path to the worker script, relative to this module
_WORKER_MODULE = "local_library.ingestion._extraction_worker"

# Timeout for worker readiness signal after startup (seconds)
_WORKER_READY_TIMEOUT = 120

# Default timeout for a single extraction (seconds)
_DEFAULT_EXTRACTION_TIMEOUT = 900  # 15 minutes

# Interval for progress logging during extraction (seconds)
_PROGRESS_LOG_INTERVAL = 30


class PdfExtractor:
    """Extractor for PDF files using Marker neural extraction.

    Runs Marker in a persistent worker subprocess for segfault isolation.
    Models are loaded once per worker lifetime. If the worker crashes
    (e.g., surya segfault on MPS), it is restarted on CPU for the failed
    document, then restarted on MPS for subsequent documents.
    """

    # Supported file extensions
    SUPPORTED_EXTENSIONS = {".pdf"}

    # Quality thresholds
    DEFAULT_MIN_LENGTH = 100
    DEFAULT_MIN_PRINTABLE_RATIO = 0.8

    def __init__(
        self,
        lazy_load: bool = True,
        llm_enabled: bool = False,
        extraction_timeout: int = _DEFAULT_EXTRACTION_TIMEOUT,
    ) -> None:
        """Initialize the PDF extractor.

        Args:
            lazy_load: If True, defer worker startup until first extraction.
                       If False, start worker immediately.
            llm_enabled: If True, enable Marker's LLM-enhanced extraction for
                         better table, math, and image handling. Requires
                         GEMINI_API_KEY environment variable.
            extraction_timeout: Maximum seconds for a single extraction before
                               killing the worker. Default 15 minutes.
        """
        self._llm_enabled = llm_enabled
        self._extraction_timeout = extraction_timeout
        self._worker: subprocess.Popen | None = None
        self._worker_device: str | None = None  # None = auto (MPS/CUDA), "cpu" = forced CPU
        self._last_extraction_info: dict | None = None

        if not lazy_load:
            self._ensure_worker_running()

    def _start_worker(self, device: str | None = None) -> subprocess.Popen:
        """Start a new extraction worker subprocess.

        Args:
            device: Torch device override. None for auto (MPS/CUDA), "cpu" for CPU.

        Returns:
            The started subprocess.

        Raises:
            ExtractionError: If worker fails to start or load models.
        """
        cmd = [sys.executable, "-m", _WORKER_MODULE]
        if self._llm_enabled:
            cmd.append("--llm")

        env = None
        if device is not None:
            import os

            env = os.environ.copy()
            env["TORCH_DEVICE"] = device

        try:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                env=env,
            )
        except OSError as e:
            raise ExtractionError(
                f"failed to start extraction worker: {e}",
                ErrorCode.EXTRACTION_MARKER_CRASH,
            ) from e

        # Wait for readiness signal
        try:
            ready_line = proc.stdout.readline()
            if not ready_line:
                raise ExtractionError(
                    "extraction worker exited during startup (no ready signal)",
                    ErrorCode.EXTRACTION_MARKER_CRASH,
                )
            ready_msg = json.loads(ready_line)
            if ready_msg.get("status") == "error":
                raise ExtractionError(
                    f"extraction worker failed to load models: {ready_msg.get('message', '')}",
                    ErrorCode.EXTRACTION_MARKER_CRASH,
                )
            if ready_msg.get("status") != "ready":
                raise ExtractionError(
                    f"unexpected worker startup message: {ready_line.strip()}",
                    ErrorCode.EXTRACTION_MARKER_CRASH,
                )
        except json.JSONDecodeError as e:
            raise ExtractionError(
                f"worker sent invalid startup message: {ready_line.strip()!r}",
                ErrorCode.EXTRACTION_MARKER_CRASH,
            ) from e

        device_label = device or "auto"
        logger.info("extraction worker started (device=%s, pid=%d)", device_label, proc.pid)
        return proc

    def _ensure_worker_running(self, device: str | None = None) -> None:
        """Ensure a worker is running with the requested device.

        Starts a new worker if none exists or if the device changed.
        """
        if self._worker is not None and self._worker.poll() is None:
            if device == self._worker_device:
                return
            # Device changed — stop current worker
            self._stop_worker()

        self._worker = self._start_worker(device)
        self._worker_device = device

    def _stop_worker(self) -> None:
        """Stop the current worker subprocess if running."""
        if self._worker is None:
            return
        try:
            if self._worker.stdin:
                self._worker.stdin.close()
            self._worker.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self._worker.kill()
            self._worker.wait()
        except Exception:
            pass
        self._worker = None
        self._worker_device = None

    def _send_request(self, file_path: str) -> dict:
        """Send an extraction request to the worker and read the response.

        Uses a reader thread for timeout support and periodic progress logging.

        Args:
            file_path: Absolute path to the PDF file.

        Returns:
            Response dict from worker.

        Raises:
            ExtractionError: If worker crashes, times out, or communication fails.
        """
        if self._worker is None or self._worker.stdin is None or self._worker.stdout is None:
            raise ExtractionError(
                "extraction worker not running",
                ErrorCode.EXTRACTION_MARKER_CRASH,
            )

        request = json.dumps({"file_path": file_path}) + "\n"
        try:
            self._worker.stdin.write(request)
            self._worker.stdin.flush()
        except (BrokenPipeError, OSError) as e:
            raise ExtractionError(
                f"failed to send request to worker: {e}",
                ErrorCode.EXTRACTION_MARKER_CRASH,
                details={"path": file_path},
            ) from e

        # Read response in a thread so we can timeout and log progress
        result_line: list[str | None] = [None]
        read_error: list[Exception | None] = [None]

        def _reader() -> None:
            try:
                result_line[0] = self._worker.stdout.readline()
            except Exception as e:
                read_error[0] = e

        thread = threading.Thread(target=_reader, daemon=True)
        thread.start()

        file_name = Path(file_path).name
        device_label = self._worker_device or "mps"
        start_time = time.monotonic()
        last_log = start_time

        while thread.is_alive():
            thread.join(timeout=_PROGRESS_LOG_INTERVAL)
            if not thread.is_alive():
                break

            elapsed = time.monotonic() - start_time
            now = time.monotonic()

            # Log progress periodically
            if now - last_log >= _PROGRESS_LOG_INTERVAL:
                logger.info(
                    "extracting %s on %s... (%.0fs elapsed)",
                    file_name,
                    device_label,
                    elapsed,
                )
                last_log = now

            # Check timeout
            if elapsed > self._extraction_timeout:
                logger.error(
                    "extraction timed out after %.0fs on %s: %s",
                    elapsed,
                    device_label,
                    file_name,
                )
                self._stop_worker()
                raise ExtractionError(
                    f"extraction timed out after {elapsed:.0f}s: {file_name}",
                    ErrorCode.EXTRACTION_TIMEOUT,
                    details={"path": file_path, "timeout": self._extraction_timeout},
                )

        duration = time.monotonic() - start_time

        if read_error[0] is not None:
            raise ExtractionError(
                f"failed to read worker response: {read_error[0]}",
                ErrorCode.EXTRACTION_MARKER_CRASH,
                details={"path": file_path},
            ) from read_error[0]

        response_line = result_line[0]
        if not response_line:
            # Worker died — stdout closed
            exit_code = self._worker.wait()
            self._worker = None
            raise _WorkerCrashed(exit_code, file_path)

        try:
            response = json.loads(response_line)
        except json.JSONDecodeError as e:
            raise ExtractionError(
                f"worker sent invalid response: {response_line.strip()!r}",
                ErrorCode.EXTRACTION_MARKER_CRASH,
                details={"path": file_path},
            ) from e

        # Track extraction info for metadata
        self._last_extraction_info = {
            "extraction_duration_seconds": round(duration, 1),
            "extraction_device": device_label,
        }

        if duration > 60:
            logger.info(
                "extracted %s on %s in %.0fs",
                file_name,
                device_label,
                duration,
            )

        return response

    def can_handle(self, file_path: Path) -> bool:
        """Check if this extractor can handle the given file.

        Args:
            file_path: Path to the file to check

        Returns:
            True if this extractor can handle the file (PDF)
        """
        return file_path.suffix.lower() in self.SUPPORTED_EXTENSIONS

    def extract(self, file_path: Path) -> ExtractionResult:
        """Extract text content from PDF using Marker.

        Runs extraction in a worker subprocess. If the worker crashes
        (segfault), retries on CPU, then restarts the MPS worker for
        subsequent documents.

        Args:
            file_path: Path to the PDF file

        Returns:
            ExtractionResult with extracted markdown text and extraction
            metadata (duration, device, fallback status)

        Raises:
            ExtractionError: If extraction fails on both MPS and CPU
        """
        if not file_path.exists():
            raise ExtractionError(
                f"file not found: {file_path}",
                ErrorCode.EXTRACTION_MARKER_CRASH,
                details={"path": str(file_path)},
            )

        file_path_str = str(file_path.resolve())
        was_fallback = False

        # Try with current device (MPS/auto)
        try:
            self._ensure_worker_running()
            response = self._send_request(file_path_str)
        except _WorkerCrashed as e:
            logger.warning(
                "extraction worker crashed (exit=%d) on %s, retrying on CPU",
                e.exit_code,
                file_path.name,
            )
            was_fallback = True
            response = self._extract_with_cpu_fallback(file_path_str)

        result = self._handle_response(response, file_path_str)

        # Merge extraction run info into result metadata
        if self._last_extraction_info:
            extraction_info = {**self._last_extraction_info}
            if was_fallback:
                extraction_info["extraction_device"] = "cpu (fallback)"
                extraction_info["extraction_fallback"] = True
            result = ExtractionResult(
                text=result.text,
                metadata={**result.metadata, **extraction_info},
                images=result.images,
                page_count=result.page_count,
                character_count=result.character_count,
                printable_ratio=result.printable_ratio,
            )

        return result

    def _extract_with_cpu_fallback(self, file_path: str) -> dict:
        """Retry extraction on CPU after an MPS crash.

        After CPU extraction succeeds, restarts the worker on MPS for
        subsequent documents.

        Raises:
            ExtractionError: If CPU extraction also fails.
        """
        try:
            self._ensure_worker_running(device="cpu")
            response = self._send_request(file_path)
        except _WorkerCrashed as e:
            raise ExtractionError(
                f"extraction crashed on both MPS and CPU (exit={e.exit_code})",
                ErrorCode.EXTRACTION_MARKER_CRASH,
                details={"path": file_path, "exit_code": e.exit_code},
            ) from None
        except ExtractionError:
            raise

        # CPU succeeded — restart MPS worker for subsequent documents
        self._stop_worker()
        # Don't eagerly restart MPS worker here; let _ensure_worker_running()
        # handle it lazily on the next extract() call
        return response

    def _handle_response(self, response: dict, file_path: str) -> ExtractionResult:
        """Convert worker response dict to ExtractionResult.

        Raises:
            ExtractionError: If worker reported an error.
        """
        status = response.get("status")

        if status == "error":
            error_type = response.get("error_type", "unknown")
            message = response.get("message", "unknown error")

            if error_type == "empty_output":
                raise ExtractionError(
                    "extraction produced empty output",
                    ErrorCode.EXTRACTION_EMPTY_OUTPUT,
                    details={"path": file_path},
                )

            raise ExtractionError(
                f"marker extraction failed: {message}",
                ErrorCode.EXTRACTION_MARKER_CRASH,
                details={"path": file_path, "error_type": error_type},
            )

        if status != "ok":
            raise ExtractionError(
                f"unexpected worker response status: {status}",
                ErrorCode.EXTRACTION_MARKER_CRASH,
                details={"path": file_path},
            )

        text = response.get("text", "")
        metadata = response.get("metadata", {})

        return ExtractionResult.from_text(text=text, metadata=metadata)

    def extract_and_validate(
        self,
        file_path: Path,
        min_length: int | None = None,
        min_printable_ratio: float | None = None,
    ) -> ExtractionResult:
        """Extract text and validate quality.

        Convenience method that combines extraction with quality validation.

        Args:
            file_path: Path to the PDF file
            min_length: Minimum character count (default: 100)
            min_printable_ratio: Minimum printable ratio (default: 0.8)

        Returns:
            ExtractionResult if extraction passes quality checks

        Raises:
            ExtractionError: If extraction fails
            QualityError: If extraction fails quality validation
        """
        min_length = min_length or self.DEFAULT_MIN_LENGTH
        min_printable_ratio = min_printable_ratio or self.DEFAULT_MIN_PRINTABLE_RATIO

        result = self.extract(file_path)

        if result.character_count < min_length:
            raise QualityError(
                f"extracted content too short: {result.character_count} chars (min: {min_length})",
                ErrorCode.QUALITY_TOO_SHORT,
                details={
                    "path": str(file_path),
                    "character_count": result.character_count,
                    "min_length": min_length,
                },
            )

        if result.printable_ratio < min_printable_ratio:
            raise QualityError(
                (
                    f"low printable character ratio: {result.printable_ratio:.2%} "
                    f"(min: {min_printable_ratio:.0%})"
                ),
                ErrorCode.QUALITY_LOW_PRINTABLE,
                details={
                    "path": str(file_path),
                    "printable_ratio": result.printable_ratio,
                    "min_printable_ratio": min_printable_ratio,
                },
            )

        return result

    def close(self) -> None:
        """Stop the worker subprocess and release resources."""
        self._stop_worker()

    def __del__(self) -> None:
        """Ensure worker is stopped on garbage collection."""
        try:
            self._stop_worker()
        except Exception:
            pass


class _WorkerCrashed(Exception):
    """Internal exception for worker subprocess crashes (segfaults etc)."""

    def __init__(self, exit_code: int, file_path: str) -> None:
        self.exit_code = exit_code
        self.file_path = file_path
        super().__init__(f"worker crashed with exit code {exit_code} on {file_path}")
