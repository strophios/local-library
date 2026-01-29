# Marker LLM-Enhanced Extraction Implementation Plan

**Goal:** Add `--llm-extract` flag to enable Marker's LLM-enhanced PDF extraction for better tables, math, and images

**Architecture:** Thread `llm_enabled` config through CLI → Library → PdfExtractor. PdfExtractor configures Marker's PdfConverter with LLM options when enabled. API key validation at CLI layer with graceful fallback.

**Tech Stack:** Marker (marker-pdf), Gemini API (via gemini_api_key config parameter), ConfigParser for Marker config

**Scope:** 4 phases from original design (phases 1-4)

**Codebase verified:** 2026-01-28

---

## Phase 1: PdfExtractor LLM Support

This phase adds the `llm_enabled` parameter to PdfExtractor and modifies `_ensure_models_loaded()` to configure Marker for LLM-enhanced extraction when enabled.

**Key insight:** Marker supports passing `gemini_api_key` directly via config dict, avoiding environment variable manipulation. We read `GEMINI_API_KEY` from the environment and pass it explicitly to Marker's configuration.

**Design clarification:** The design's "Not Configured" section says `llm_service` "defaults to Gemini." We explicitly set `llm_service: "marker.services.gemini.GoogleGeminiService"` for explicitness and to ensure behavior doesn't change if Marker's defaults change. This is defensive but aligns with design intent.

---

<!-- START_SUBCOMPONENT_A (tasks 1-4) -->

<!-- START_TASK_1 -->
### Task 1: Add llm_enabled parameter to PdfExtractor constructor

**Files:**
- Modify: `src/local_library/ingestion/pdf.py:26-37`

**Step 1: Update the constructor signature and instance variable**

Open `src/local_library/ingestion/pdf.py` and modify the `__init__` method to accept `llm_enabled`:

```python
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
```

**Step 2: Verify the change compiles**

Run: `uv run python -c "from local_library.ingestion.pdf import PdfExtractor; PdfExtractor(llm_enabled=True)"`

Expected: No errors (lazy loading means no actual Marker invocation)

**Step 3: Commit**

```bash
git add src/local_library/ingestion/pdf.py
git commit -m "$(cat <<'EOF'
feat(pdf): add llm_enabled parameter to PdfExtractor

Preparation for Marker LLM-enhanced extraction. Parameter stored
but not yet used in _ensure_models_loaded().

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Add os import and implement LLM configuration in _ensure_models_loaded

**Files:**
- Modify: `src/local_library/ingestion/pdf.py:1-10` (imports)
- Modify: `src/local_library/ingestion/pdf.py:39-58` (_ensure_models_loaded method)

**Step 1: Add os import at top of file**

Add `import os` to the imports section:

```python
"""PDF extraction implementation using Marker."""

# pattern: Imperative Shell

import os
from pathlib import Path
from typing import Any
```

**Step 2: Implement LLM configuration in _ensure_models_loaded**

Replace the `_ensure_models_loaded` method with:

```python
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
            gemini_key = os.environ.get("GEMINI_API_KEY")
            if gemini_key:
                # Pass API key directly via config (avoids environment mutation)
                config.update({
                    "use_llm": True,
                    "gemini_api_key": gemini_key,
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
```

**Step 3: Verify the change compiles**

Run: `uv run python -c "from local_library.ingestion.pdf import PdfExtractor; print('OK')"`

Expected: `OK`

**Step 4: Commit**

```bash
git add src/local_library/ingestion/pdf.py
git commit -m "$(cat <<'EOF'
feat(pdf): implement LLM config in _ensure_models_loaded

When llm_enabled=True and GEMINI_API_KEY is set:
- Passes gemini_api_key directly via config dict
- Configures use_llm, llm_service, redo_inline_math, disable_image_extraction
- Uses ConfigParser to generate proper config dict

Without GEMINI_API_KEY, LLM mode silently falls back to standard extraction.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Write tests for PdfExtractor LLM configuration

**Files:**
- Modify: `tests/unit/test_pdf_extractor.py`

**Step 1: Add test class for LLM configuration**

Add the following test class at the end of the file (after `TestProtocolConformance`):

```python
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

    def test_gemini_api_key_passed_in_config(
        self, sample_pdf: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When llm_enabled=True, gemini_api_key should be passed in config dict."""
        monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")

        captured_config: dict[str, Any] = {}

        mock_config_parser = MagicMock()
        mock_config_parser.generate_config_dict.return_value = {}

        def capture_config(config: dict[str, Any]) -> MagicMock:
            captured_config.update(config)
            return mock_config_parser

        mock_converter = MagicMock()

        with patch("marker.config.parser.ConfigParser", side_effect=capture_config):
            with patch("marker.converters.pdf.PdfConverter", return_value=mock_converter):
                with patch("marker.models.create_model_dict", return_value={}):
                    extractor = PdfExtractor(lazy_load=True, llm_enabled=True)
                    extractor._ensure_models_loaded()

        # Verify gemini_api_key was passed in config (not set in environment)
        assert captured_config.get("gemini_api_key") == "test-gemini-key"
```

**Step 2: Add required import for Any type**

At the top of the test file, update imports to include `Any` and `os`:

```python
"""Unit tests for PDF extractor module."""

import os
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
```

**Step 3: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_pdf_extractor.py -v`

Expected: All tests pass, including the new `TestLLMConfiguration` tests

**Step 4: Commit**

```bash
git add tests/unit/test_pdf_extractor.py
git commit -m "$(cat <<'EOF'
test(pdf): add tests for LLM configuration

Tests verify:
- llm_enabled defaults to False
- LLM config passed to Marker when enabled + API key present
- LLM config NOT passed when disabled
- LLM config NOT passed when no API key (graceful fallback)
- gemini_api_key passed via config dict

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Run full test suite and verify no regressions

**Files:**
- None (verification only)

**Step 1: Run ruff check**

Run: `uv run ruff check src/local_library/ingestion/pdf.py tests/unit/test_pdf_extractor.py`

Expected: No linting errors

**Step 2: Run ruff format check**

Run: `uv run ruff format --check src/local_library/ingestion/pdf.py tests/unit/test_pdf_extractor.py`

Expected: No formatting issues (or run `uv run ruff format` to fix)

**Step 3: Run the full unit test suite**

Run: `uv run pytest tests/unit/ -v`

Expected: All tests pass

**Step 4: Commit any formatting fixes if needed**

If ruff format made changes:

```bash
git add -A
git commit -m "$(cat <<'EOF'
style: apply ruff formatting

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

<!-- END_TASK_4 -->

<!-- END_SUBCOMPONENT_A -->

---

## Phase 1 Completion Checklist

- [ ] PdfExtractor accepts `llm_enabled` parameter
- [ ] `_ensure_models_loaded()` configures Marker for LLM when enabled + API key present
- [ ] `gemini_api_key` passed via config dict (avoids environment mutation)
- [ ] Graceful fallback when API key missing (no LLM config, standard extraction)
- [ ] All new tests pass
- [ ] No regressions in existing tests
- [ ] Code passes ruff check and format
