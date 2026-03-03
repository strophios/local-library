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
            result = client.complete([{"role": "user", "content": "Say hello"}])

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
            tokens = list(client.stream([{"role": "user", "content": "test"}]))

        assert tokens == ["Hello", ", ", "world", "!"]

    def test_stream_skips_none_content(self) -> None:
        """stream() should skip chunks with None content."""
        from local_library.llm.litellm_client import LiteLLMClient

        chunks = _make_stream_chunks(["Hello", None, "", " world"])

        with patch("litellm.completion", return_value=iter(chunks)):
            client = LiteLLMClient(model="test/model")
            tokens = list(client.stream([{"role": "user", "content": "test"}]))

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
        mock_litellm.completion.side_effect = mock_litellm.RateLimitError("too many requests")

        with patch.dict("sys.modules", {"litellm": mock_litellm}):
            client = LiteLLMClient(model="test/model")
            with pytest.raises(LLMError) as exc_info:
                client.complete([{"role": "user", "content": "test"}])

        assert exc_info.value.code == ErrorCode.LLM_RATE_LIMITED

    def test_not_found_maps_to_model_not_found(self) -> None:
        """NotFoundError should map to LLM_MODEL_NOT_FOUND."""
        from local_library.llm.litellm_client import LiteLLMClient

        mock_litellm = _make_mock_litellm()
        mock_litellm.completion.side_effect = mock_litellm.NotFoundError("model not found")

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

        with patch("litellm.completion", side_effect=RuntimeError("stream failed")):
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
