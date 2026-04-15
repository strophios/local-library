"""Unit tests for Zotero CLI progress callback."""

import io

from rich.console import Console

from local_library.cli.zotero import _make_console_progress_callback


class TestConsoleProgressCallback:
    """Tests for _make_console_progress_callback."""

    def test_precheck_event_prints(self) -> None:
        """Callback should handle precheck_complete event without error."""
        output = io.StringIO()
        console = Console(file=output, no_color=True)
        callback = _make_console_progress_callback(console)

        callback(
            "pre-check done",
            0.0,
            {
                "event": "precheck_complete",
                "file_name": "test.pdf",
                "page_count": 10,
                "has_text": True,
                "timeout": 900,
            },
        )

        assert "10 pages" in output.getvalue()

    def test_progress_event_prints(self) -> None:
        """Callback should handle extraction_progress event without error."""
        output = io.StringIO()
        console = Console(file=output, no_color=True)
        callback = _make_console_progress_callback(console)

        callback(
            "extracting...",
            90.0,
            {
                "event": "extraction_progress",
                "file_name": "test.pdf",
                "device": "mps",
                "elapsed": 90.0,
            },
        )

        assert "1m 30s" in output.getvalue()

    def test_fallback_event_prints(self) -> None:
        """Callback should handle extraction_fallback event without error."""
        output = io.StringIO()
        console = Console(file=output, no_color=True)
        callback = _make_console_progress_callback(console)

        callback(
            "fallback",
            0.0,
            {
                "event": "extraction_fallback",
                "file_name": "test.pdf",
            },
        )

        assert "fallback" in output.getvalue()

    def test_completion_event_prints(self) -> None:
        """Callback should handle extraction_complete event without error."""
        output = io.StringIO()
        console = Console(file=output, no_color=True)
        callback = _make_console_progress_callback(console)

        callback(
            "extracted",
            150.0,
            {
                "event": "extraction_complete",
                "file_name": "test.pdf",
                "device": "mps",
                "duration": 150.0,
            },
        )

        assert "2m 30s" in output.getvalue()
