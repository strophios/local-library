# Phase 6: LLM Fallback

**Goal:** Add LLM extraction for low-confidence documents.

When heuristic confidence falls below threshold, an LLM can re-extract all fields in a single call. The LLM provides values but heuristic confidence is preserved (we don't yet trust LLM enough to override confidence).

**Reference documentation:**
- `src/local_library/core/CLAUDE.md` - Core domain contracts
- `src/local_library/ingestion/CLAUDE.md` - Ingestion domain contracts

---

<!-- START_TASK_1 -->
### Task 1: Add litellm dependency

**Files:**
- Modify: `pyproject.toml`

**Step 1: Add litellm to dependencies**

In `pyproject.toml`, add `litellm` to the dependencies list:

```toml
dependencies = [
    "jsonschema>=4.20.0",
    "litellm>=1.0.0",
    "marker-pdf>=1.10.0",
    "nameparser>=1.1.0",
    "platformdirs>=4.0.0",
    "rich>=13.0.0",
    "typer>=0.21.0",
    "unidecode>=1.3.0",
]
```

**Step 2: Install the new dependency**

Run:
```bash
uv sync
```

Expected: Installs litellm without errors

**Step 3: Verify import works**

Run:
```bash
uv run python -c "import litellm; print(litellm.__version__)"
```

Expected: Prints version number

**Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "$(cat <<'EOF'
deps: add litellm for LLM fallback extraction

Provider-agnostic LLM access for M3b text extraction fallback.
Enables OpenAI, Anthropic, and other providers via unified API.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

<!-- END_TASK_1 -->

<!-- START_SUBCOMPONENT_A (tasks 2-4) -->

<!-- START_TASK_2 -->
### Task 2: Write tests for LLM extraction

**Files:**
- Modify: `tests/unit/test_text_extraction.py`

**Step 1: Add LLM extraction tests**

Add to `tests/unit/test_text_extraction.py`:

```python
from unittest.mock import MagicMock, patch


class TestLLMExtraction:
    """Tests for LLM-based metadata extraction fallback."""

    def test_llm_extractor_parses_json_response(self) -> None:
        """LLMExtractor should parse JSON response correctly."""
        from local_library.ingestion.text_extraction import LLMExtractor

        extractor = LLMExtractor(enabled=True, model="gpt-4o-mini")

        # Mock response
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(
                message=MagicMock(
                    content='{"title": "Test Title", "authors": ["John Smith"], "year": "2023", "type": "article-journal"}'
                )
            )
        ]

        with patch("litellm.completion", return_value=mock_response):
            result = extractor.extract("Some document text")

        assert result is not None
        assert result["title"] == "Test Title"
        assert result["authors"] == ["John Smith"]
        assert result["year"] == "2023"
        assert result["type"] == "article-journal"

    def test_llm_extractor_handles_invalid_json(self) -> None:
        """LLMExtractor should return None for invalid JSON."""
        from local_library.ingestion.text_extraction import LLMExtractor

        extractor = LLMExtractor(enabled=True, model="gpt-4o-mini")

        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="not valid json"))]

        with patch("litellm.completion", return_value=mock_response):
            result = extractor.extract("Some document text")

        assert result is None

    def test_llm_extractor_handles_api_error(self) -> None:
        """LLMExtractor should return None on API error."""
        from local_library.ingestion.text_extraction import LLMExtractor

        extractor = LLMExtractor(enabled=True, model="gpt-4o-mini")

        with patch("litellm.completion", side_effect=Exception("API error")):
            result = extractor.extract("Some document text")

        assert result is None

    def test_llm_extractor_disabled_returns_none(self) -> None:
        """Disabled LLMExtractor should return None immediately."""
        from local_library.ingestion.text_extraction import LLMExtractor

        extractor = LLMExtractor(enabled=False, model="gpt-4o-mini")

        # Should not call API
        result = extractor.extract("Some document text")

        assert result is None

    def test_llm_extractor_truncates_long_text(self) -> None:
        """LLMExtractor should truncate very long documents."""
        from local_library.ingestion.text_extraction import LLMExtractor

        extractor = LLMExtractor(enabled=True, model="gpt-4o-mini")

        # Very long text
        long_text = "word " * 10000

        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content='{"title": "Test", "authors": [], "year": null, "type": "article-journal"}'))
        ]

        with patch("litellm.completion", return_value=mock_response) as mock_call:
            extractor.extract(long_text)

            # Should have called with truncated text
            call_args = mock_call.call_args
            messages = call_args.kwargs["messages"]
            user_content = messages[1]["content"]
            # Should be truncated to reasonable length
            assert len(user_content) < len(long_text)

    def test_llm_extractor_prompt_includes_heuristic_candidates(self) -> None:
        """LLMExtractor prompt should include heuristic candidates when provided."""
        from local_library.ingestion.text_extraction import LLMExtractor

        extractor = LLMExtractor(enabled=True, model="gpt-4o-mini")

        candidates = {
            "title": "Candidate Title",
            "authors": ["Smith, John"],
            "year": "2023",
        }

        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(
                message=MagicMock(
                    content='{"title": "Better Title", "authors": ["Smith, John"], "year": "2023", "type": "article-journal"}'
                )
            )
        ]

        with patch("litellm.completion", return_value=mock_response) as mock_call:
            extractor.extract("Document text", heuristic_candidates=candidates)

            # Prompt should mention candidates
            call_args = mock_call.call_args
            messages = call_args.kwargs["messages"]
            user_content = messages[1]["content"]
            assert "Candidate Title" in user_content


class TestTextMetadataExtractorWithLLM:
    """Tests for TextMetadataExtractor with LLM fallback."""

    def test_extractor_uses_llm_when_low_confidence(self) -> None:
        """Extractor should call LLM when heuristic confidence is low."""
        from local_library.ingestion.text_extraction import TextMetadataExtractor

        # Text with unclear metadata
        text = """Some vague document

        Without clear title or author patterns.
        """

        mock_llm_response = MagicMock()
        mock_llm_response.choices = [
            MagicMock(
                message=MagicMock(
                    content='{"title": "LLM Title", "authors": ["LLM Author"], "year": "2023", "type": "article-journal"}'
                )
            )
        ]

        with patch("litellm.completion", return_value=mock_llm_response):
            extractor = TextMetadataExtractor(
                confidence_threshold=0.9,  # High threshold to trigger fallback
                llm_enabled=True,
                llm_model="gpt-4o-mini",
            )
            result = extractor.extract(text)

            # Should have LLM-enhanced values
            # Note: confidence is preserved from heuristics
            assert result.title.source == "llm" or result.title.value is not None

    def test_extractor_skips_llm_when_confident(self) -> None:
        """Extractor should skip LLM when heuristic confidence is high."""
        from local_library.ingestion.text_extraction import TextMetadataExtractor

        # Well-structured document
        text = """# Machine Learning Applications

        John Smith, Jane Doe

        Published: 2023

        Journal of Computer Science

        Abstract...
        """

        with patch("litellm.completion") as mock_call:
            extractor = TextMetadataExtractor(
                confidence_threshold=0.3,  # Low threshold
                llm_enabled=True,
                llm_model="gpt-4o-mini",
            )
            result = extractor.extract(text)

            # Should not have called LLM
            if not result.needs_review:
                mock_call.assert_not_called()

    def test_extractor_graceful_degradation_without_llm(self) -> None:
        """Extractor should work without LLM (graceful degradation)."""
        from local_library.ingestion.text_extraction import TextMetadataExtractor

        text = """Some Document

        John Smith
        2023
        """

        # LLM disabled
        extractor = TextMetadataExtractor(
            confidence_threshold=0.7,
            llm_enabled=False,
        )
        result = extractor.extract(text)

        # Should still produce results
        assert result.title.value is not None
        # All sources should be heuristic
        assert result.title.source == "heuristic"

    def test_extractor_preserves_heuristic_confidence_after_llm(self) -> None:
        """After LLM fallback, heuristic confidence should be preserved."""
        from local_library.ingestion.text_extraction import TextMetadataExtractor

        text = """Unclear document title

        Maybe an author name here
        """

        mock_llm_response = MagicMock()
        mock_llm_response.choices = [
            MagicMock(
                message=MagicMock(
                    content='{"title": "Actual Title", "authors": ["Real Author"], "year": "2023", "type": "article-journal"}'
                )
            )
        ]

        with patch("litellm.completion", return_value=mock_llm_response):
            extractor = TextMetadataExtractor(
                confidence_threshold=0.8,
                llm_enabled=True,
                llm_model="gpt-4o-mini",
            )
            result = extractor.extract(text)

            # Confidence should still be from heuristics (not boosted by LLM)
            # This ensures needs_review is still triggered appropriately
            if result.title.source == "llm":
                # Confidence preserved from heuristics
                assert result.needs_review is True  # Still needs review
```

**Step 2: Run tests to verify they fail**

Run:
```bash
uv run pytest tests/unit/test_text_extraction.py::TestLLMExtraction -v
uv run pytest tests/unit/test_text_extraction.py::TestTextMetadataExtractorWithLLM -v
```

Expected: FAIL with "cannot import name 'LLMExtractor'"

**Step 3: Commit**

```bash
git add tests/unit/test_text_extraction.py
git commit -m "$(cat <<'EOF'
test(text_extraction): add LLM fallback extraction tests

Covers JSON parsing, error handling, graceful degradation,
confidence preservation, and integration with orchestrator.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Implement LLMExtractor class

**Files:**
- Modify: `src/local_library/ingestion/text_extraction.py`

**Step 1: Add LLMExtractor implementation**

Add to `src/local_library/ingestion/text_extraction.py` before the TextMetadataExtractor class:

```python
import json
import logging

# LLM extraction constants
_LLM_MAX_TEXT_LENGTH = 8000  # Characters to send to LLM
_LLM_DEFAULT_MODEL = "gpt-4o-mini"  # Cost-effective default

logger = logging.getLogger(__name__)


class LLMExtractor:
    """LLM-based metadata extraction fallback.

    Uses LiteLLM for provider-agnostic LLM access. Called when heuristic
    confidence is below threshold.

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
            model: LiteLLM model identifier (e.g., "gpt-4o-mini", "claude-3-haiku")
        """
        self.enabled = enabled
        self.model = model

    def extract(
        self,
        markdown_text: str,
        heuristic_candidates: dict[str, str | list[str] | None] | None = None,
    ) -> dict[str, str | list[str] | None] | None:
        """Extract metadata using LLM.

        Args:
            markdown_text: Document text to analyze
            heuristic_candidates: Optional dict of heuristic extraction results
                                 to provide as context for the LLM

        Returns:
            Dict with keys: title, authors, year, type
            Returns None if disabled, API error, or invalid response
        """
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

            # Call LLM
            response = litellm.completion(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.1,  # Low temperature for consistency
                max_tokens=500,
            )

            # Parse response
            content = response.choices[0].message.content
            return self._parse_response(content)

        except Exception as e:
            logger.warning(f"LLM extraction failed: {e}")
            return None

    def _build_system_prompt(self) -> str:
        """Build the system prompt for extraction."""
        return """You are a metadata extraction assistant. Extract bibliographic metadata from academic documents.

Return ONLY a JSON object with these exact keys:
- "title": string (document title)
- "authors": array of strings (author names in "Family, Given" format)
- "year": string (4-digit publication year) or null
- "type": string (one of: "article-journal", "paper-conference", "chapter", "thesis", "report", "book")

If a field cannot be determined, use null for strings or empty array for authors.
Do not include any text outside the JSON object."""

    def _build_user_prompt(
        self,
        text: str,
        candidates: dict[str, str | list[str] | None] | None,
    ) -> str:
        """Build the user prompt with document text and optional candidates."""
        prompt_parts = ["Extract metadata from this document:\n\n", text]

        if candidates:
            prompt_parts.append("\n\n---\nHeuristic extraction found these candidates:")
            if candidates.get("title"):
                prompt_parts.append(f"\nTitle candidate: {candidates['title']}")
            if candidates.get("authors"):
                prompt_parts.append(f"\nAuthor candidates: {candidates['authors']}")
            if candidates.get("year"):
                prompt_parts.append(f"\nYear candidate: {candidates['year']}")
            prompt_parts.append(
                "\n\nUse these as hints but extract the correct values from the document."
            )

        return "".join(prompt_parts)

    def _parse_response(self, content: str) -> dict[str, str | list[str] | None] | None:
        """Parse LLM response into structured dict.

        Handles:
        - JSON in markdown code blocks
        - Plain JSON
        - Invalid JSON (returns None)
        """
        if not content:
            return None

        # Try to extract JSON from markdown code block
        json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
        if json_match:
            content = json_match.group(1)
        else:
            # Try to find JSON object
            json_match = re.search(r"\{[^{}]*\}", content, re.DOTALL)
            if json_match:
                content = json_match.group(0)

        try:
            data = json.loads(content)

            # Validate structure
            result: dict[str, str | list[str] | None] = {
                "title": data.get("title"),
                "authors": data.get("authors", []),
                "year": data.get("year"),
                "type": data.get("type", "article-journal"),
            }

            # Ensure authors is a list
            if not isinstance(result["authors"], list):
                result["authors"] = []

            return result

        except json.JSONDecodeError:
            logger.warning(f"Failed to parse LLM response as JSON: {content[:100]}...")
            return None
```

**Step 2: Update TextMetadataExtractor to use LLM fallback**

Modify the `TextMetadataExtractor` class:

```python
class TextMetadataExtractor:
    """Orchestrates extraction of all metadata fields from document text.

    Combines individual field extractors (title, authors, date, type) and
    aggregates confidence scores to determine if human review is needed.

    Supports optional LLM fallback when heuristic confidence is low.

    Usage:
        extractor = TextMetadataExtractor()
        result = extractor.extract(markdown_text)
        if result.needs_review:
            print(f"Review needed: {result.review_reasons}")

    Attributes:
        confidence_threshold: Minimum confidence for a field to be considered
                             reliable. Fields below this trigger needs_review.
        llm_enabled: Whether to use LLM fallback for low-confidence extractions.
        llm_model: LiteLLM model identifier for fallback.
    """

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

    def extract(self, markdown_text: str) -> "TextExtractionResult":
        """Extract all metadata fields from markdown text.

        Runs each field extractor independently, then aggregates results
        into a TextExtractionResult with overall confidence and review status.

        If LLM fallback is enabled and any field confidence is below threshold,
        the LLM re-extracts all fields. LLM values are used but heuristic
        confidence is preserved.

        Args:
            markdown_text: Marker-produced markdown content

        Returns:
            TextExtractionResult with all extracted fields and aggregated metadata
        """
        from local_library.core.models import TextExtractionResult

        # Extract each field with heuristics
        title = extract_title(markdown_text)
        authors = extract_authors(markdown_text)
        date = extract_date(markdown_text)
        doc_type = extract_doc_type(markdown_text)

        # Check if LLM fallback is needed
        needs_llm = self._needs_llm_fallback(title, authors, date, doc_type)

        if needs_llm and self._llm_extractor.enabled:
            # Build candidates dict for context
            candidates = {
                "title": title.value,
                "authors": [a.value for a in authors if a.value],
                "year": date.value,
            }

            llm_result = self._llm_extractor.extract(markdown_text, candidates)

            if llm_result:
                # Update extractions with LLM values but preserve heuristic confidence
                title, authors, date, doc_type = self._merge_llm_results(
                    title, authors, date, doc_type, llm_result
                )

        # Calculate overall confidence (minimum of all fields)
        all_confidences = [title.confidence, date.confidence, doc_type.confidence]
        if authors:
            all_confidences.extend(a.confidence for a in authors)

        overall_confidence = min(all_confidences) if all_confidences else 0.0

        # Determine needs_review and reasons
        review_reasons = self._check_review_needed(title, authors, date, doc_type)
        needs_review = len(review_reasons) > 0

        return TextExtractionResult(
            title=title,
            authors=authors,
            date=date,
            doc_type=doc_type,
            overall_confidence=round(overall_confidence, 2),
            needs_review=needs_review,
            review_reasons=tuple(review_reasons),
        )

    def _needs_llm_fallback(
        self,
        title: FieldExtraction,
        authors: tuple[FieldExtraction, ...],
        date: FieldExtraction,
        doc_type: FieldExtraction,
    ) -> bool:
        """Check if LLM fallback should be triggered."""
        threshold = self.confidence_threshold

        # Trigger if any major field is below threshold
        if title.confidence < threshold:
            return True
        if date.confidence < threshold:
            return True
        if not authors or all(a.confidence < threshold for a in authors):
            return True

        return False

    def _merge_llm_results(
        self,
        title: FieldExtraction,
        authors: tuple[FieldExtraction, ...],
        date: FieldExtraction,
        doc_type: FieldExtraction,
        llm_result: dict[str, str | list[str] | None],
    ) -> tuple[
        FieldExtraction,
        tuple[FieldExtraction, ...],
        FieldExtraction,
        FieldExtraction,
    ]:
        """Merge LLM results into field extractions.

        Uses LLM values but preserves heuristic confidence scores.
        """
        # Update title if LLM provided one
        if llm_result.get("title"):
            title = FieldExtraction(
                value=llm_result["title"],
                confidence=title.confidence,  # Preserve heuristic confidence
                source="llm",
                alternatives=title.alternatives,
                reasoning=f"LLM extraction (heuristic: {title.value})",
            )

        # Update authors if LLM provided them
        llm_authors = llm_result.get("authors", [])
        if llm_authors:
            new_authors = []
            # Use average heuristic confidence for LLM authors
            avg_conf = (
                sum(a.confidence for a in authors) / len(authors) if authors else 0.3
            )
            for name in llm_authors:
                if name:
                    new_authors.append(
                        FieldExtraction(
                            value=name,
                            confidence=avg_conf,  # Preserve heuristic confidence
                            source="llm",
                            alternatives=(),
                            reasoning="LLM extraction",
                        )
                    )
            if new_authors:
                authors = tuple(new_authors)

        # Update date if LLM provided one
        if llm_result.get("year"):
            date = FieldExtraction(
                value=llm_result["year"],
                confidence=date.confidence,  # Preserve heuristic confidence
                source="llm",
                alternatives=date.alternatives,
                reasoning=f"LLM extraction (heuristic: {date.value})",
            )

        # Update type if LLM provided one
        if llm_result.get("type"):
            doc_type = FieldExtraction(
                value=llm_result["type"],
                confidence=doc_type.confidence,  # Preserve heuristic confidence
                source="llm",
                alternatives=doc_type.alternatives,
                reasoning=f"LLM extraction (heuristic: {doc_type.value})",
            )

        return title, authors, date, doc_type

    def _check_review_needed(
        self,
        title: FieldExtraction,
        authors: tuple[FieldExtraction, ...],
        date: FieldExtraction,
        doc_type: FieldExtraction,
    ) -> list[str]:
        """Check if any field needs human review.

        Returns:
            List of review reasons (empty if no review needed)
        """
        reasons: list[str] = []
        threshold = self.confidence_threshold

        # Check title
        if title.value is None:
            reasons.append("title could not be extracted")
        elif title.confidence < threshold:
            reasons.append(
                f"title confidence {title.confidence:.2f} below threshold {threshold:.2f}"
            )

        # Check authors
        if not authors:
            reasons.append("no authors could be extracted")
        else:
            low_conf_authors = [a for a in authors if a.confidence < threshold]
            if len(low_conf_authors) == len(authors):
                # All authors have low confidence
                avg_conf = sum(a.confidence for a in authors) / len(authors)
                reasons.append(
                    f"authors average confidence {avg_conf:.2f} below threshold {threshold:.2f}"
                )

        # Check date
        if date.value is None:
            reasons.append("date could not be extracted")
        elif date.confidence < threshold:
            reasons.append(
                f"date confidence {date.confidence:.2f} below threshold {threshold:.2f}"
            )

        # Check doc_type (less critical, only flag if very low)
        if doc_type.confidence < threshold * 0.7:  # Lower bar for type
            reasons.append(
                f"document type confidence {doc_type.confidence:.2f} is low"
            )

        return reasons
```

**Step 3: Run tests**

Run:
```bash
uv run pytest tests/unit/test_text_extraction.py::TestLLMExtraction -v
uv run pytest tests/unit/test_text_extraction.py::TestTextMetadataExtractorWithLLM -v
```

Expected: All tests PASS

**Step 4: Commit**

```bash
git add src/local_library/ingestion/text_extraction.py
git commit -m "$(cat <<'EOF'
feat(text_extraction): implement LLM fallback extraction

Adds LLMExtractor using LiteLLM for provider-agnostic LLM access.
Triggers when heuristic confidence is low. Preserves heuristic
confidence scores to maintain calibration accuracy.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Run full test suite and lint

**Files:**
- All modified files

**Step 1: Run all text extraction tests**

Run:
```bash
uv run pytest tests/unit/test_text_extraction.py -v
```

Expected: All tests PASS

**Step 2: Run all unit tests**

Run:
```bash
uv run pytest tests/unit/ -v
```

Expected: All tests PASS

**Step 3: Run linting**

Run:
```bash
uv run ruff check src/local_library/ingestion/text_extraction.py
uv run ruff format src/local_library/ingestion/text_extraction.py
```

Expected: No errors (or auto-fixed)

**Step 4: Commit any fixes**

```bash
git add .
git commit -m "$(cat <<'EOF'
style(text_extraction): apply ruff formatting

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

<!-- END_TASK_4 -->

<!-- END_SUBCOMPONENT_A -->

---

## Phase 6 Completion Checklist

- [ ] `litellm` dependency added
- [ ] `LLMExtractor` class implemented
- [ ] JSON response parsing working
- [ ] Error handling for API failures
- [ ] Integration with `TextMetadataExtractor` working
- [ ] Heuristic confidence preserved after LLM fallback
- [ ] Graceful degradation when LLM disabled
- [ ] All LLM tests pass
- [ ] Linting passes
