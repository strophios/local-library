# LLM Domain

Last verified: 2026-03-03

## Purpose

Provides a protocol-based abstraction over LLM providers. Decouples LLM consumers (RAG interface, text metadata extraction) from specific provider libraries. LiteLLM is the concrete backend.

## Contracts

- **Exposes**: `LLMClient` protocol (runtime-checkable), `LiteLLMClient` implementation
- **Guarantees**:
  - LLMClient declares `complete()` (blocking) and `stream()` (token iterator) methods
  - LiteLLMClient maps provider exceptions to typed `LLMError` with appropriate `ErrorCode`
  - LiteLLMClient lazily imports litellm at construction time (not at module import)
  - Error mapping: `RateLimitError` -> `LLM_RATE_LIMITED`, `NotFoundError` -> `LLM_MODEL_NOT_FOUND`, other -> `LLM_GENERATION_FAILED`
  - Empty LLM response raises `LLMError` with `LLM_GENERATION_FAILED`
- **Expects**: Valid LiteLLM model string (e.g., "gemini/gemini-2.0-flash", "anthropic/claude-sonnet-4-20250514"); appropriate API key in environment

## Dependencies

- **Uses**: `core.errors` (LLMError, ErrorCode)
- **Used by**: `core.library` (creates LiteLLMClient for RAG and text extraction), `rag.interface` (accepts LLMClient for generation), `ingestion.text_extraction` (accepts LLMClient for fallback extraction)
- **Boundary**: LLM MUST NOT import from cli, rag, ingestion, or embeddings

## Key Decisions

- **Protocol over ABC**: LLMClient is a `@runtime_checkable Protocol` for duck typing, consistent with other protocols in the codebase (Chunker, Embedder, Retriever)
- **Thin wrapper**: LiteLLMClient handles only litellm calling, error mapping, and response unwrapping. No prompt construction, context assembly, or output parsing
- **Lazy litellm import**: litellm imported at LiteLLMClient construction (not module level) to avoid import cost when LLM features unused
- **Error mapping centralized**: `_map_error()` private method maps all litellm/provider exceptions to LLMError with appropriate ErrorCode
- **Functional Core / Imperative Shell split**: `base.py` (protocol) is Functional Core; `litellm_client.py` is Imperative Shell

## Invariants

- LLMClient.complete() always returns a non-empty string (empty response raises LLMError)
- LLMClient.stream() yields string tokens; never yields empty strings
- All failures surface as LLMError (never raw provider exceptions)

## Key Files

- `base.py` - LLMClient protocol with complete() and stream() signatures (Functional Core)
- `litellm_client.py` - LiteLLMClient implementation wrapping litellm.completion() (Imperative Shell)

## Gotchas

- LiteLLMClient constructor raises LLMError if litellm is not installed (not ImportError)
- The `response_format` kwarg is passed through to litellm via `**kwargs` for structured output support (used by text extraction)
- Stream iteration can raise LLMError mid-iteration if the provider connection fails
