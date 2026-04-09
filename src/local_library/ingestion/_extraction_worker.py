"""Marker extraction worker subprocess.

Runs as a standalone process that loads Marker models once and processes
PDF files in a loop via stdin/stdout JSON protocol. Isolates Marker from
the parent process so that segfaults (e.g., surya MPS crashes) don't kill
the entire application.

Protocol:
  - Parent sends one JSON object per line to stdin:
    {"file_path": "/path/to/file.pdf"}
  - Worker responds with one JSON object per line to stdout:
    {"status": "ok", "text": "...", "metadata": {...}}
    {"status": "error", "error_type": "...", "message": "..."}
  - Worker sends "ready" on stdout after models are loaded:
    {"status": "ready"}
"""

# pattern: Imperative Shell

import json
import sys


def main() -> None:
    """Run the extraction worker loop."""
    import os

    # Parse CLI args for configuration
    llm_enabled = "--llm" in sys.argv
    gemini_key = os.environ.get("GEMINI_API_KEY", "")

    # Load Marker models (expensive, done once)
    try:
        from marker.config.parser import ConfigParser
        from marker.converters.pdf import PdfConverter
        from marker.models import create_model_dict
        from marker.output import text_from_rendered

        config: dict = {}

        if llm_enabled and gemini_key:
            config.update(
                {
                    "use_llm": True,
                    "gemini_api_key": gemini_key,
                    "llm_service": "marker.services.gemini.GoogleGeminiService",
                    "redo_inline_math": True,
                    "disable_image_extraction": True,
                }
            )

        config_parser = ConfigParser(config)
        converter = PdfConverter(
            config=config_parser.generate_config_dict(),
            artifact_dict=create_model_dict(),
        )
    except Exception as e:
        _send({"status": "error", "error_type": "load_failed", "message": str(e)})
        sys.exit(1)

    # Signal readiness
    _send({"status": "ready"})

    # Process files from stdin
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            request = json.loads(line)
        except json.JSONDecodeError as e:
            _send({"status": "error", "error_type": "protocol", "message": str(e)})
            continue

        file_path = request.get("file_path")
        if not file_path:
            _send({"status": "error", "error_type": "protocol", "message": "missing file_path"})
            continue

        try:
            rendered = converter(file_path)
            text, _, _ = text_from_rendered(rendered)

            # Extract Marker metadata (page_stats with extraction methods)
            marker_metadata = (
                rendered.metadata
                if hasattr(rendered, "metadata") and isinstance(rendered.metadata, dict)
                else {}
            )

            if not text or not text.strip():
                _send(
                    {
                        "status": "error",
                        "error_type": "empty_output",
                        "message": "extraction produced empty output",
                    }
                )
            else:
                _send({"status": "ok", "text": text, "metadata": marker_metadata})

        except Exception as e:
            _send(
                {
                    "status": "error",
                    "error_type": "extraction_failed",
                    "message": str(e),
                }
            )


def _send(obj: dict) -> None:
    """Write a JSON response to stdout and flush."""
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
