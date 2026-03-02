# Phase 2: Refactor text_extraction.py

**Goal:** Unify LLM call sites under the shared LLMClient abstraction.

**Done when:** LLMExtractor uses LLMClient.complete() instead of litellm.completion() directly, tests mock LLMClient at the right boundary, all tests pass.

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Refactor LLMExtractor and TextMetadataExtractor to use LLMClient

**Files:**
- Modify: `src/local_library/ingestion/text_extraction.py`

**Step 1: Add TYPE_CHECKING import**

At line 22, change:
```python
from typing import Any
```
to:
```python
from typing import TYPE_CHECKING, Any
```

After line 26 (`from local_library.core.models import FieldExtraction, TextExtractionResult`), add:
```python

if TYPE_CHECKING:
    from local_library.llm.base import LLMClient
```

**Step 2: Replace LLMExtractor class**

Replace lines 1153-1176 (class docstring and `__init__`):
```python
class LLMExtractor:
    """LLM-based metadata extraction fallback.

    Uses LiteLLM for provider-agnostic LLM access. Called when heuristic
    confidence is below threshold.

    Uses structured output (response_format) for guaranteed valid JSON.
    The LLM extracts all fields in a single call for cost efficiency and
    to leverage cross-field context.
    """

    def __init__(
        self,
        enabled: bool = False,
        model: str = _LLM_DEFAULT_MODEL,
    ) -> None:
        """Initialize the LLM extractor.

        Args:
            enabled: Whether LLM fallback is enabled
            model: LiteLLM model identifier (e.g., "gemini/gemini-2.0-flash")
        """
        self.enabled = enabled
        self.model = model
```

with:
```python
class LLMExtractor:
    """LLM-based metadata extraction fallback.

    Uses LLMClient for provider-agnostic LLM access. Called when heuristic
    confidence is below threshold.

    Uses structured output (response_format) for guaranteed valid JSON.
    The LLM extracts all fields in a single call for cost efficiency and
    to leverage cross-field context.
    """

    def __init__(
        self,
        llm_client: LLMClient | None = None,
    ) -> None:
        """Initialize the LLM extractor.

        Args:
            llm_client: Pre-configured LLMClient instance. If None,
                       LLM extraction is disabled.
        """
        self._llm_client = llm_client

    @property
    def enabled(self) -> bool:
        """Whether LLM extraction is available."""
        return self._llm_client is not None
```

**Step 3: Replace extract() body (lines 1194-1223)**

Replace:
```python
        if not self.enabled:
            return None

        try:
            import litellm

            # Truncate text if too long
            text = markdown_text[:_LLM_MAX_TEXT_LENGTH]
            if len(markdown_text) > _LLM_MAX_TEXT_LENGTH:
                text += "\n[... text truncated ...]"

            # Build prompt
            system_prompt = self._build_system_prompt()
            user_prompt = self._build_user_prompt(text, heuristic_candidates)

            # Call LLM with structured output
            response = litellm.completion(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format=MetadataExtractionResponse,
                temperature=0.1,  # Low temperature for consistency
                max_tokens=500,
            )

            # Parse structured response
            content = response.choices[0].message.content
            return self._parse_response(content)
```

with:
```python
        if self._llm_client is None:
            return None

        try:
            # Truncate text if too long
            text = markdown_text[:_LLM_MAX_TEXT_LENGTH]
            if len(markdown_text) > _LLM_MAX_TEXT_LENGTH:
                text += "\n[... text truncated ...]"

            # Build prompt
            system_prompt = self._build_system_prompt()
            user_prompt = self._build_user_prompt(text, heuristic_candidates)

            # Call LLM with structured output via LLMClient
            content = self._llm_client.complete(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.1,
                max_tokens=500,
                response_format=MetadataExtractionResponse,
            )

            return self._parse_response(content)
```

Note: the `except Exception` block at lines 1225-1228 remains unchanged.

**Step 4: Replace TextMetadataExtractor.__init__ (lines 1306-1321)**

Replace:
```python
    def __init__(
        self,
        confidence_threshold: float = _DEFAULT_CONFIDENCE_THRESHOLD,
        llm_enabled: bool = False,
        llm_model: str = _LLM_DEFAULT_MODEL,
    ) -> None:
        """Initialize the extractor.

        Args:
            confidence_threshold: Minimum confidence (0.0-1.0) for fields.
                                 Default is 0.7 (70%).
            llm_enabled: Whether to enable LLM fallback. Default is False.
            llm_model: LiteLLM model identifier. Default is "gpt-4o-mini".
        """
        self.confidence_threshold = confidence_threshold
        self._llm_extractor = LLMExtractor(enabled=llm_enabled, model=llm_model)
```

with:
```python
    def __init__(
        self,
        confidence_threshold: float = _DEFAULT_CONFIDENCE_THRESHOLD,
        llm_client: LLMClient | None = None,
    ) -> None:
        """Initialize the extractor.

        Args:
            confidence_threshold: Minimum confidence (0.0-1.0) for fields.
                                 Default is 0.7 (70%).
            llm_client: Pre-configured LLMClient for LLM fallback.
                       If None, LLM fallback is disabled.
        """
        self.confidence_threshold = confidence_threshold
        self._llm_extractor = LLMExtractor(llm_client=llm_client)
```

**Step 5: Update TextMetadataExtractor class docstring attributes section**

In the docstring around lines 1299-1303, replace:
```python
    Attributes:
        confidence_threshold: Minimum confidence for a field to be considered
                             reliable. Fields below this trigger needs_review.
        llm_enabled: Whether to use LLM fallback for low-confidence extractions.
        llm_model: LiteLLM model identifier for fallback.
```

with:
```python
    Attributes:
        confidence_threshold: Minimum confidence for a field to be considered
                             reliable. Fields below this trigger needs_review.
```

**Step 6: Verify linting**

Run: `uv run ruff check src/local_library/ingestion/text_extraction.py`
Expected: No errors
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Update tests to mock LLMClient directly

**Files:**
- Modify: `tests/unit/test_text_extraction.py` (lines 909-1179)

**Step 1: Replace TestLLMExtraction class (lines 909-1049)**

Replace the entire class with:
```python
class TestLLMExtraction:
    """Tests for LLM-based metadata extraction fallback."""

    def test_llm_extractor_parses_json_response(self) -> None:
        """LLMExtractor should parse JSON response correctly."""
        from unittest.mock import MagicMock

        from local_library.ingestion.text_extraction import LLMExtractor

        mock_client = MagicMock()
        mock_client.complete.return_value = (
            '{"title": "Test Title", "authors": ["John Smith"], '
            '"year": "2023", "type": "article-journal"}'
        )

        extractor = LLMExtractor(llm_client=mock_client)
        result = extractor.extract("Some document text")

        assert result is not None
        assert result["title"] == "Test Title"
        assert result["authors"] == ["John Smith"]
        assert result["year"] == "2023"
        assert result["type"] == "article-journal"

    def test_llm_extractor_handles_invalid_json(self) -> None:
        """LLMExtractor should return None for invalid JSON."""
        from unittest.mock import MagicMock

        from local_library.ingestion.text_extraction import LLMExtractor

        mock_client = MagicMock()
        mock_client.complete.return_value = "not valid json"

        extractor = LLMExtractor(llm_client=mock_client)
        result = extractor.extract("Some document text")

        assert result is None

    def test_llm_extractor_handles_api_error(self) -> None:
        """LLMExtractor should return None on API error."""
        from unittest.mock import MagicMock

        from local_library.ingestion.text_extraction import LLMExtractor

        mock_client = MagicMock()
        mock_client.complete.side_effect = Exception("API error")

        extractor = LLMExtractor(llm_client=mock_client)
        result = extractor.extract("Some document text")

        assert result is None

    def test_llm_extractor_disabled_returns_none(self) -> None:
        """LLMExtractor without client should return None immediately."""
        from local_library.ingestion.text_extraction import LLMExtractor

        extractor = LLMExtractor()  # No client = disabled
        result = extractor.extract("Some document text")

        assert result is None

    def test_llm_extractor_truncates_long_text(self) -> None:
        """LLMExtractor should truncate very long documents."""
        from unittest.mock import MagicMock

        from local_library.ingestion.text_extraction import LLMExtractor

        mock_client = MagicMock()
        mock_client.complete.return_value = (
            '{"title": "Test", "authors": [], "year": null, "type": "article-journal"}'
        )

        extractor = LLMExtractor(llm_client=mock_client)

        # Very long text
        long_text = "word " * 10000
        extractor.extract(long_text)

        # Should have called with truncated text
        call_args = mock_client.complete.call_args
        messages = call_args.kwargs["messages"]
        user_content = messages[1]["content"]
        # Should be truncated to reasonable length
        assert len(user_content) < len(long_text)

    def test_llm_extractor_prompt_includes_heuristic_candidates(self) -> None:
        """LLMExtractor prompt should include heuristic candidates when provided."""
        from unittest.mock import MagicMock

        from local_library.ingestion.text_extraction import LLMExtractor

        mock_client = MagicMock()
        mock_client.complete.return_value = (
            '{"title": "Better Title", '
            '"authors": ["Smith, John"], '
            '"year": "2023", "type": "article-journal"}'
        )

        candidates = {
            "title": "Candidate Title",
            "authors": ["Smith, John"],
            "year": "2023",
        }

        extractor = LLMExtractor(llm_client=mock_client)
        extractor.extract("Document text", heuristic_candidates=candidates)

        # Prompt should mention candidates
        call_args = mock_client.complete.call_args
        messages = call_args.kwargs["messages"]
        user_content = messages[1]["content"]
        assert "Candidate Title" in user_content

    def test_llm_extractor_forwards_response_format(self) -> None:
        """LLMExtractor should forward response_format kwarg to LLMClient."""
        from unittest.mock import MagicMock

        from local_library.ingestion.text_extraction import LLMExtractor

        mock_client = MagicMock()
        mock_client.complete.return_value = (
            '{"title": "Test", "authors": [], "year": null, "type": "article-journal"}'
        )

        extractor = LLMExtractor(llm_client=mock_client)
        extractor.extract("Some text")

        call_args = mock_client.complete.call_args
        assert "response_format" in call_args.kwargs
```

**Step 2: Replace TestTextMetadataExtractorWithLLM class (lines 1051-1179)**

Replace the entire class with:
```python
class TestTextMetadataExtractorWithLLM:
    """Tests for TextMetadataExtractor with LLM fallback."""

    def test_extractor_uses_llm_when_low_confidence(self) -> None:
        """Extractor should call LLM when heuristic confidence is low."""
        from unittest.mock import MagicMock

        from local_library.ingestion.text_extraction import TextMetadataExtractor

        # Text with unclear metadata
        text = """Some vague document

        Without clear title or author patterns.
        """

        mock_client = MagicMock()
        mock_client.complete.return_value = (
            '{"title": "LLM Title", '
            '"authors": ["LLM Author"], '
            '"year": "2023", "type": "article-journal"}'
        )

        extractor = TextMetadataExtractor(
            confidence_threshold=0.9,  # High threshold to trigger fallback
            llm_client=mock_client,
        )
        result = extractor.extract(text)

        # Should have LLM-enhanced values
        # Note: confidence is preserved from heuristics
        assert result.title.source == "llm" or result.title.value is not None

    def test_extractor_skips_llm_when_confident(self) -> None:
        """Extractor should skip LLM when heuristic confidence is high."""
        from unittest.mock import MagicMock

        from local_library.ingestion.text_extraction import TextMetadataExtractor

        # Well-structured document
        text = """# Machine Learning Applications

        John Smith, Jane Doe

        Published: 2023

        Journal of Computer Science

        Abstract...
        """

        mock_client = MagicMock()
        extractor = TextMetadataExtractor(
            confidence_threshold=0.3,  # Low threshold
            llm_client=mock_client,
        )
        result = extractor.extract(text)

        # Should not have called LLM
        if not result.needs_review:
            mock_client.complete.assert_not_called()

    def test_extractor_graceful_degradation_without_llm(self) -> None:
        """Extractor should work without LLM (graceful degradation)."""
        from local_library.ingestion.text_extraction import TextMetadataExtractor

        text = """Some Document

        John Smith
        2023
        """

        # No LLM client = disabled
        extractor = TextMetadataExtractor(confidence_threshold=0.7)
        result = extractor.extract(text)

        # Should still produce results
        assert result.title.value is not None
        # All sources should be heuristic
        assert result.title.source == "heuristic"

    def test_extractor_preserves_heuristic_confidence_after_llm(self) -> None:
        """After LLM fallback, heuristic confidence should be preserved."""
        from unittest.mock import MagicMock

        from local_library.ingestion.text_extraction import TextMetadataExtractor

        text = """Unclear document title

        Maybe an author name here
        """

        mock_client = MagicMock()
        mock_client.complete.return_value = (
            '{"title": "Actual Title", '
            '"authors": ["Real Author"], '
            '"year": "2023", "type": "article-journal"}'
        )

        extractor = TextMetadataExtractor(
            confidence_threshold=0.8,
            llm_client=mock_client,
        )
        result = extractor.extract(text)

        # Confidence should still be from heuristics (not boosted by LLM)
        # This ensures needs_review is still triggered appropriately
        if result.title.source == "llm":
            # Confidence preserved from heuristics
            assert result.needs_review is True  # Still needs review
```

**Step 3: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_text_extraction.py -v`
Expected: ALL tests pass
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 3-4) -->
<!-- START_TASK_3 -->
### Task 3: Update Library to create and thread LLMClient

**Files:**
- Modify: `src/local_library/core/library.py:144-153`

**Step 1: Update Library's TextMetadataExtractor construction**

Replace lines 144-153:
```python
        # Initialize text metadata extractor
        self._text_extractor = (
            TextMetadataExtractor(
                confidence_threshold=text_extraction_confidence_threshold,
                llm_enabled=text_extraction_llm_enabled,
                llm_model=text_extraction_llm_model,
            )
            if text_extraction_enabled
            else None
        )
```

with:
```python
        # Initialize text metadata extractor
        # Create LLMClient at Library level for explicit dependency ownership
        text_llm_client = None
        if text_extraction_llm_enabled:
            from local_library.llm.litellm_client import LiteLLMClient

            text_llm_client = LiteLLMClient(model=text_extraction_llm_model)

        self._text_extractor = (
            TextMetadataExtractor(
                confidence_threshold=text_extraction_confidence_threshold,
                llm_client=text_llm_client,
            )
            if text_extraction_enabled
            else None
        )
```

**Step 2: Verify linting**

Run: `uv run ruff check src/local_library/core/library.py`
Expected: No errors
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Verify full test suite and commit

**Step 1: Run full test suite**

Run: `uv run pytest -x -q`
Expected: All tests pass

**Step 2: Verify LLMExtractor no longer imports litellm**

Run: `uv run python -c "import ast, sys; tree = ast.parse(open('src/local_library/ingestion/text_extraction.py').read()); imports = [n.names[0].name for n in ast.walk(tree) if isinstance(n, ast.Import)]; sys.exit(1 if 'litellm' in imports else 0)"`
Expected: Exit code 0

**Step 3: Commit**

```bash
git add src/local_library/ingestion/text_extraction.py src/local_library/core/library.py tests/unit/test_text_extraction.py
git commit -m "refactor(ingestion): use LLMClient abstraction in LLMExtractor

Replace direct litellm.completion() call with LLMClient.complete().
LLMExtractor now accepts LLMClient via constructor injection only.
Library creates LiteLLMClient and threads to TextMetadataExtractor.

Tests updated to mock LLMClient directly instead of litellm internals."
```
<!-- END_TASK_4 -->
<!-- END_SUBCOMPONENT_B -->
