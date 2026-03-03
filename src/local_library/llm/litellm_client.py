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
