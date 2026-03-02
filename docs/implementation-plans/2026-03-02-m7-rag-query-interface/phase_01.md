# M7: RAG Query Interface Implementation Plan

**Goal:** Build the query-facing half of the RAG system — LLM abstraction, RAG orchestration, and CLI interface for asking questions grounded in library documents.

**Architecture:** Custom RAGInterface class backed by thin LLMClient protocol wrapping LiteLLM. Two new packages (llm/, rag/) following established Protocol-based patterns. Library orchestrates lazy-init wiring.

**Tech Stack:** Python, LiteLLM, Rich (streaming display), pytest (unittest.mock)

**Scope:** 6 phases from original design (phases 1-6)

**Codebase verified:** 2026-03-02

---

## Phase 1: LLM Abstraction Layer

**Goal:** Shared LLM client protocol and LiteLLM implementation, with error codes.

**Done when:** LiteLLMClient satisfies LLMClient protocol, error mapping covers generation failures / rate limits / model not found, tests pass with mocked litellm.completion.

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Add error codes and exception classes to core/errors.py

**Files:**
- Modify: `src/local_library/core/errors.py:63` (add ErrorCode values) and `:140` (add exception classes)

**Step 1: Add new ErrorCode values**

After line 63 (`EMBEDDING_FTS_QUERY_SYNTAX`), add a new section:

```python
    # RAG / LLM errors
    RAG_NO_CONTEXT = "RAG_NO_CONTEXT"
    LLM_GENERATION_FAILED = "LLM_GENERATION_FAILED"
    LLM_MODEL_NOT_FOUND = "LLM_MODEL_NOT_FOUND"
    LLM_RATE_LIMITED = "LLM_RATE_LIMITED"
```

**Step 2: Add new exception classes**

After line 140 (end of `FTSQueryError`), add:

```python


class LLMError(LocalLibraryError):
    """Error during LLM API interaction."""

    pass


class RAGError(LocalLibraryError):
    """Error during RAG query pipeline."""

    pass
```

**Step 3: Verify**

Run: `uv run ruff check src/local_library/core/errors.py`
Expected: No errors

Run: `uv run python -c "from local_library.core.errors import ErrorCode, LLMError, RAGError; print(ErrorCode.LLM_RATE_LIMITED, LLMError, RAGError)"`
Expected: Prints enum value and class references without error

**Step 4: Commit**

```bash
git add src/local_library/core/errors.py
git commit -m "feat(core): add LLM and RAG error codes and exception classes

Add ErrorCode values: RAG_NO_CONTEXT, LLM_GENERATION_FAILED,
LLM_MODEL_NOT_FOUND, LLM_RATE_LIMITED.

Add exception classes: LLMError, RAGError (both inherit LocalLibraryError)."
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Create llm package with LLMClient protocol

**Files:**
- Create: `src/local_library/llm/__init__.py`
- Create: `src/local_library/llm/base.py`

**Step 1: Create `src/local_library/llm/__init__.py`**

```python
"""Shared LLM abstraction layer."""

from local_library.llm.base import LLMClient

__all__ = ["LLMClient"]
```

Note: `LiteLLMClient` will be added to `__init__.py` exports in Task 4 after implementation.

**Step 2: Create `src/local_library/llm/base.py`**

```python
"""LLMClient protocol — thin abstraction over LLM providers."""

# pattern: Functional Core

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class LLMClient(Protocol):
    """Protocol for LLM API interaction.

    Declares complete() and stream() methods. LiteLLMClient is the
    concrete implementation. Does not handle prompt construction,
    context assembly, or output parsing.
    """

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> str:
        """Call LLM and return complete response text.

        Args:
            messages: List of message dicts with 'role' and 'content' keys
            temperature: Sampling temperature (0.0-2.0)
            max_tokens: Maximum tokens in response
            **kwargs: Additional provider-specific parameters

        Returns:
            Complete response text as string

        Raises:
            LLMError: If the LLM call fails
        """
        ...

    def stream(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> Iterator[str]:
        """Call LLM and yield response tokens as they arrive.

        Args:
            messages: List of message dicts with 'role' and 'content' keys
            temperature: Sampling temperature (0.0-2.0)
            max_tokens: Maximum tokens in response
            **kwargs: Additional provider-specific parameters

        Yields:
            Response text tokens as strings

        Raises:
            LLMError: If the LLM call fails
        """
        ...
```

**Step 3: Verify**

Run: `uv run ruff check src/local_library/llm/`
Expected: No errors

Run: `uv run python -c "from local_library.llm import LLMClient; print(LLMClient)"`
Expected: Prints protocol class reference without error

**Step 4: Commit**

```bash
git add src/local_library/llm/__init__.py src/local_library/llm/base.py
git commit -m "feat(llm): add LLMClient protocol

Runtime-checkable protocol with complete() and stream() methods.
Follows existing Protocol patterns from embeddings and ingestion."
```
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 3-4) -->
<!-- START_TASK_3 -->
### Task 3: Write tests for LiteLLMClient

**Files:**
- Create: `tests/unit/test_llm_client.py`

**Step 1: Write the test file**

```python
"""Tests for the LLM client abstraction layer."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from local_library.core.errors import ErrorCode, LLMError
from local_library.llm.base import LLMClient


def _make_mock_litellm() -> MagicMock:
    """Create a mock litellm module with controllable exception types."""
    mock = MagicMock()
    mock.RateLimitError = type("RateLimitError", (Exception,), {})
    mock.NotFoundError = type("NotFoundError", (Exception,), {})
    mock.AuthenticationError = type("AuthenticationError", (Exception,), {})
    return mock


def _make_completion_response(content: str) -> MagicMock:
    """Create a mock litellm completion response."""
    response = MagicMock()
    response.choices = [MagicMock(message=MagicMock(content=content))]
    return response


def _make_stream_chunks(texts: list[str | None]) -> list[MagicMock]:
    """Create mock streaming chunks from a list of text fragments."""
    chunks = []
    for text in texts:
        chunk = MagicMock()
        chunk.choices = [MagicMock(delta=MagicMock(content=text))]
        chunks.append(chunk)
    return chunks


class TestLLMClientProtocol:
    """Tests for LLMClient protocol satisfaction."""

    def test_litellm_client_satisfies_protocol(self) -> None:
        """LiteLLMClient should be recognized as LLMClient via isinstance."""
        from local_library.llm.litellm_client import LiteLLMClient

        with patch.dict("sys.modules", {"litellm": _make_mock_litellm()}):
            client = LiteLLMClient(model="test/model")
            assert isinstance(client, LLMClient)


class TestLiteLLMClientComplete:
    """Tests for LiteLLMClient.complete()."""

    def test_complete_returns_response_text(self) -> None:
        """complete() should return text content from litellm response."""
        from local_library.llm.litellm_client import LiteLLMClient

        mock_response = _make_completion_response("Hello, world!")

        with patch("litellm.completion", return_value=mock_response):
            client = LiteLLMClient(model="test/model")
            result = client.complete(
                [{"role": "user", "content": "Say hello"}]
            )

        assert result == "Hello, world!"

    def test_complete_passes_parameters(self) -> None:
        """complete() should forward model, temperature, max_tokens to litellm."""
        from local_library.llm.litellm_client import LiteLLMClient

        mock_response = _make_completion_response("response")

        with patch("litellm.completion", return_value=mock_response) as mock_call:
            client = LiteLLMClient(model="gemini/gemini-2.0-flash")
            client.complete(
                [{"role": "user", "content": "test"}],
                temperature=0.3,
                max_tokens=1000,
            )

        mock_call.assert_called_once_with(
            model="gemini/gemini-2.0-flash",
            messages=[{"role": "user", "content": "test"}],
            temperature=0.3,
            max_tokens=1000,
            stream=False,
        )

    def test_complete_raises_on_none_content(self) -> None:
        """complete() should raise LLMError when response content is None."""
        from local_library.llm.litellm_client import LiteLLMClient

        mock_response = _make_completion_response("placeholder")
        mock_response.choices[0].message.content = None

        with patch("litellm.completion", return_value=mock_response):
            client = LiteLLMClient(model="test/model")
            with pytest.raises(LLMError) as exc_info:
                client.complete([{"role": "user", "content": "test"}])

        assert exc_info.value.code == ErrorCode.LLM_GENERATION_FAILED


class TestLiteLLMClientStream:
    """Tests for LiteLLMClient.stream()."""

    def test_stream_yields_tokens(self) -> None:
        """stream() should yield text content from each chunk."""
        from local_library.llm.litellm_client import LiteLLMClient

        chunks = _make_stream_chunks(["Hello", ", ", "world", "!"])

        with patch("litellm.completion", return_value=iter(chunks)):
            client = LiteLLMClient(model="test/model")
            tokens = list(
                client.stream([{"role": "user", "content": "test"}])
            )

        assert tokens == ["Hello", ", ", "world", "!"]

    def test_stream_skips_none_content(self) -> None:
        """stream() should skip chunks with None content."""
        from local_library.llm.litellm_client import LiteLLMClient

        chunks = _make_stream_chunks(["Hello", None, "", " world"])

        with patch("litellm.completion", return_value=iter(chunks)):
            client = LiteLLMClient(model="test/model")
            tokens = list(
                client.stream([{"role": "user", "content": "test"}])
            )

        assert tokens == ["Hello", " world"]

    def test_stream_passes_parameters(self) -> None:
        """stream() should forward parameters with stream=True."""
        from local_library.llm.litellm_client import LiteLLMClient

        with patch("litellm.completion", return_value=iter([])) as mock_call:
            client = LiteLLMClient(model="anthropic/claude-sonnet-4-20250514")
            list(
                client.stream(
                    [{"role": "user", "content": "test"}],
                    temperature=0.5,
                    max_tokens=2000,
                )
            )

        mock_call.assert_called_once_with(
            model="anthropic/claude-sonnet-4-20250514",
            messages=[{"role": "user", "content": "test"}],
            temperature=0.5,
            max_tokens=2000,
            stream=True,
        )


class TestLiteLLMClientErrorMapping:
    """Tests for LiteLLMClient error mapping from litellm exceptions."""

    def test_rate_limit_maps_to_rate_limited(self) -> None:
        """RateLimitError should map to LLM_RATE_LIMITED."""
        from local_library.llm.litellm_client import LiteLLMClient

        mock_litellm = _make_mock_litellm()
        mock_litellm.completion.side_effect = mock_litellm.RateLimitError(
            "too many requests"
        )

        with patch.dict("sys.modules", {"litellm": mock_litellm}):
            client = LiteLLMClient(model="test/model")
            with pytest.raises(LLMError) as exc_info:
                client.complete([{"role": "user", "content": "test"}])

        assert exc_info.value.code == ErrorCode.LLM_RATE_LIMITED

    def test_not_found_maps_to_model_not_found(self) -> None:
        """NotFoundError should map to LLM_MODEL_NOT_FOUND."""
        from local_library.llm.litellm_client import LiteLLMClient

        mock_litellm = _make_mock_litellm()
        mock_litellm.completion.side_effect = mock_litellm.NotFoundError(
            "model not found"
        )

        with patch.dict("sys.modules", {"litellm": mock_litellm}):
            client = LiteLLMClient(model="test/model")
            with pytest.raises(LLMError) as exc_info:
                client.complete([{"role": "user", "content": "test"}])

        assert exc_info.value.code == ErrorCode.LLM_MODEL_NOT_FOUND

    def test_generic_exception_maps_to_generation_failed(self) -> None:
        """Unknown exceptions should map to LLM_GENERATION_FAILED."""
        from local_library.llm.litellm_client import LiteLLMClient

        with patch("litellm.completion", side_effect=RuntimeError("broke")):
            client = LiteLLMClient(model="test/model")
            with pytest.raises(LLMError) as exc_info:
                client.complete([{"role": "user", "content": "test"}])

        assert exc_info.value.code == ErrorCode.LLM_GENERATION_FAILED

    def test_stream_errors_also_mapped(self) -> None:
        """Errors during streaming should also be mapped to LLMError."""
        from local_library.llm.litellm_client import LiteLLMClient

        with patch(
            "litellm.completion", side_effect=RuntimeError("stream failed")
        ):
            client = LiteLLMClient(model="test/model")
            with pytest.raises(LLMError) as exc_info:
                list(client.stream([{"role": "user", "content": "test"}]))

        assert exc_info.value.code == ErrorCode.LLM_GENERATION_FAILED

    def test_llm_error_preserves_cause(self) -> None:
        """Mapped LLMError should chain the original exception."""
        from local_library.llm.litellm_client import LiteLLMClient

        original = RuntimeError("original cause")

        with patch("litellm.completion", side_effect=original):
            client = LiteLLMClient(model="test/model")
            with pytest.raises(LLMError) as exc_info:
                client.complete([{"role": "user", "content": "test"}])

        assert exc_info.value.__cause__ is original
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_llm_client.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'local_library.llm.litellm_client'`
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Implement LiteLLMClient and verify

**Files:**
- Create: `src/local_library/llm/litellm_client.py`
- Modify: `src/local_library/llm/__init__.py` (add LiteLLMClient export)

**Step 1: Create `src/local_library/llm/litellm_client.py`**

```python
"""LiteLLM-backed implementation of the LLMClient protocol."""

# pattern: Imperative Shell

from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import Any

from local_library.core.errors import ErrorCode, LLMError

logger = logging.getLogger(__name__)


class LiteLLMClient:
    """Thin wrapper around litellm.completion().

    Handles lazy import (at construction), error mapping to ErrorCode,
    and response/stream unwrapping. Does not handle prompt construction,
    context assembly, or output parsing.

    Args:
        model: LiteLLM model string (e.g., "gemini/gemini-2.0-flash",
               "anthropic/claude-sonnet-4-20250514")
    """

    def __init__(self, model: str) -> None:
        self.model = model
        try:
            import litellm

            self._litellm = litellm
        except ImportError as e:
            raise LLMError(
                message="litellm is not installed",
                code=ErrorCode.LLM_GENERATION_FAILED,
                details={"error": str(e)},
            ) from e

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> str:
        """Call LLM and return complete response text.

        Args:
            messages: List of message dicts with 'role' and 'content' keys
            temperature: Sampling temperature (0.0-2.0)
            max_tokens: Maximum tokens in response
            **kwargs: Additional provider-specific parameters

        Returns:
            Complete response text as string

        Raises:
            LLMError: If the LLM call fails or returns empty content
        """
        try:
            response = self._litellm.completion(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=False,
                **kwargs,
            )
            content = response.choices[0].message.content
            if content is None:
                raise LLMError(
                    message="LLM returned empty response",
                    code=ErrorCode.LLM_GENERATION_FAILED,
                    details={"model": self.model},
                )
            return content
        except LLMError:
            raise
        except Exception as e:
            raise self._map_error(e) from e

    def stream(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> Iterator[str]:
        """Call LLM and yield response tokens as they arrive.

        Args:
            messages: List of message dicts with 'role' and 'content' keys
            temperature: Sampling temperature (0.0-2.0)
            max_tokens: Maximum tokens in response
            **kwargs: Additional provider-specific parameters

        Yields:
            Response text tokens as strings

        Raises:
            LLMError: If the LLM call fails
        """
        try:
            response = self._litellm.completion(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
                **kwargs,
            )
            for chunk in response:
                content = chunk.choices[0].delta.content
                if content:
                    yield content
        except LLMError:
            raise
        except Exception as e:
            raise self._map_error(e) from e

    def _map_error(self, exc: Exception) -> LLMError:
        """Map litellm/provider exceptions to LLMError with appropriate ErrorCode."""
        if isinstance(exc, self._litellm.RateLimitError):
            return LLMError(
                message=f"rate limited: {exc}",
                code=ErrorCode.LLM_RATE_LIMITED,
                details={"model": self.model},
            )
        if isinstance(exc, self._litellm.NotFoundError):
            return LLMError(
                message=f"model not found: {self.model}",
                code=ErrorCode.LLM_MODEL_NOT_FOUND,
                details={"model": self.model},
            )
        return LLMError(
            message=f"LLM generation failed: {exc}",
            code=ErrorCode.LLM_GENERATION_FAILED,
            details={"model": self.model, "error_type": type(exc).__name__},
        )
```

**Step 2: Update `src/local_library/llm/__init__.py`**

```python
"""Shared LLM abstraction layer."""

from local_library.llm.base import LLMClient
from local_library.llm.litellm_client import LiteLLMClient

__all__ = ["LLMClient", "LiteLLMClient"]
```

**Step 3: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_llm_client.py -v`
Expected: All tests PASS

**Step 4: Run linting**

Run: `uv run ruff check src/local_library/llm/`
Expected: No errors

**Step 5: Run full test suite to check for regressions**

Run: `uv run pytest -x -q`
Expected: All existing tests pass

**Step 6: Commit**

```bash
git add src/local_library/llm/litellm_client.py src/local_library/llm/__init__.py tests/unit/test_llm_client.py
git commit -m "feat(llm): add LiteLLMClient implementation with tests

Wraps litellm.completion() with lazy import at construction, error
mapping (RateLimitError -> LLM_RATE_LIMITED, NotFoundError ->
LLM_MODEL_NOT_FOUND), and response/stream unwrapping.

Satisfies LLMClient protocol. Tests use mocked litellm.completion."
```
<!-- END_TASK_4 -->
<!-- END_SUBCOMPONENT_B -->
