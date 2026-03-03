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
