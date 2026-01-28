"""PDF extraction implementation using Marker."""

# pattern: Imperative Shell

import os
from pathlib import Path
from typing import Any

from local_library.core.errors import ErrorCode, ExtractionError, QualityError
from local_library.core.models import ExtractionResult


class PdfExtractor:
    """Extractor for PDF files using Marker neural extraction.

    Marker converts PDFs to markdown with good formatting preservation.
    Models are loaded once at instantiation and reused for all extractions.
    """

    # Supported file extensions
    SUPPORTED_EXTENSIONS = {".pdf"}

    # Quality thresholds
    DEFAULT_MIN_LENGTH = 100
    DEFAULT_MIN_PRINTABLE_RATIO = 0.8

    def __init__(self, lazy_load: bool = True, llm_enabled: bool = False) -> None:
        """Initialize the PDF extractor.

        Args:
            lazy_load: If True, defer model loading until first extraction.
                       If False, load models immediately.
            llm_enabled: If True, enable Marker's LLM-enhanced extraction for
                         better table, math, and image handling. Requires
                         GEMINI_API_KEY environment variable.
        """
        self._converter: Any = None
        self._lazy_load = lazy_load
        self._llm_enabled = llm_enabled

        if not lazy_load:
            self._ensure_models_loaded()

    def _ensure_models_loaded(self) -> None:
        """Load Marker models if not already loaded.

        When llm_enabled is True and GEMINI_API_KEY is available, configures
        Marker for LLM-enhanced extraction with:
        - use_llm: True
        - redo_inline_math: True (better LaTeX extraction)
        - disable_image_extraction: True (images become text descriptions)
        """
        if self._converter is not None:
            return

        try:
            from marker.config.parser import ConfigParser
            from marker.converters.pdf import PdfConverter
            from marker.models import create_model_dict

            config: dict[str, Any] = {}

            if self._llm_enabled:
                # Check for API key - Marker expects GOOGLE_API_KEY
                gemini_key = os.environ.get("GEMINI_API_KEY")
                if gemini_key:
                    # Set GOOGLE_API_KEY for Marker's Gemini service
                    os.environ["GOOGLE_API_KEY"] = gemini_key
                    config.update({
                        "use_llm": True,
                        "llm_service": "marker.services.gemini.GoogleGeminiService",
                        "redo_inline_math": True,
                        "disable_image_extraction": True,
                    })

            # Use ConfigParser to generate proper config dict
            config_parser = ConfigParser(config)
            self._converter = PdfConverter(
                config=config_parser.generate_config_dict(),
                artifact_dict=create_model_dict(),
            )
        except ImportError as e:
            raise ExtractionError(
                f"marker-pdf not installed or import failed: {e}",
                ErrorCode.EXTRACTION_MARKER_CRASH,
            ) from e
        except Exception as e:
            raise ExtractionError(
                f"failed to load Marker models: {e}",
                ErrorCode.EXTRACTION_MARKER_CRASH,
            ) from e

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

        Args:
            file_path: Path to the PDF file

        Returns:
            ExtractionResult with extracted markdown text

        Raises:
            ExtractionError: If extraction fails
        """
        if not file_path.exists():
            raise ExtractionError(
                f"file not found: {file_path}",
                ErrorCode.EXTRACTION_MARKER_CRASH,
                details={"path": str(file_path)},
            )

        self._ensure_models_loaded()

        try:
            from marker.output import text_from_rendered

            # Run extraction
            rendered = self._converter(str(file_path))
            text, metadata, images = text_from_rendered(rendered)

        except Exception as e:
            raise ExtractionError(
                f"marker extraction failed: {e}",
                ErrorCode.EXTRACTION_MARKER_CRASH,
                details={"path": str(file_path)},
            ) from e

        if not text or not text.strip():
            raise ExtractionError(
                "extraction produced empty output",
                ErrorCode.EXTRACTION_EMPTY_OUTPUT,
                details={"path": str(file_path)},
            )

        # Build result with quality metrics
        result = ExtractionResult.from_text(
            text=text,
            metadata=metadata if isinstance(metadata, dict) else {},
        )

        # Store images as bytes if available
        if images:
            result = ExtractionResult(
                text=result.text,
                metadata=result.metadata,
                images=[img if isinstance(img, bytes) else b"" for img in images],
                page_count=len(images) if images else 0,
                character_count=result.character_count,
                printable_ratio=result.printable_ratio,
            )

        return result

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
