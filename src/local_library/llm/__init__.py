"""Shared LLM abstraction layer."""

from local_library.llm.base import LLMClient
from local_library.llm.litellm_client import LiteLLMClient

__all__ = ["LLMClient", "LiteLLMClient"]
