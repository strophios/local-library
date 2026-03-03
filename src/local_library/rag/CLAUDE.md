# RAG Domain

Last verified: 2026-03-03

## Purpose

Orchestrates the RAG query pipeline: context assembly from search results, prompt construction, and LLM answer generation. Supports both blocking and streaming paths. Pure functions handle context formatting; RAGInterface coordinates the full pipeline.

## Contracts

- **Exposes**: `RAGInterface` (orchestrator), `RAGStream` (streaming wrapper), `assemble_context()` (pure function), `build_messages()` (pure function)
- **Guarantees**:
  - `assemble_context()` formats SearchResults into attributed context string with citekey headers ([@citekey, section])
  - `build_messages()` constructs system + user message list; context-first, question-last ordering for high-attention position
  - `RAGInterface.query()` returns complete `RAGResponse`; skips LLM call when search_results is empty (pre-LLM gate)
  - `RAGInterface.query_stream()` returns `RAGStream` yielding tokens; skips LLM call when search_results is empty
  - `RAGStream.to_response()` builds `RAGResponse` from accumulated tokens after iteration
  - `RAGStream.context_chunks` available immediately before iteration starts (enables source display during streaming)
  - Pre-LLM gate returns "I don't have any relevant documents to answer this question." without API call
- **Expects**: Pre-retrieved `list[SearchResult]` from a retriever; configured `LLMClient` for generation

## Dependencies

- **Uses**: `core.errors` (RAGError, ErrorCode), `core.models` (RAGResponse), `embeddings.base` (SearchResult), `llm.base` (LLMClient)
- **Used by**: `core.library` (Library.query() and Library.query_stream() delegate to RAGInterface)
- **Boundary**: RAG MUST NOT import from cli, ingestion, or storage

## Key Decisions

- **Pure functions + orchestrator colocated**: `assemble_context()` and `build_messages()` are pure Functional Core functions in the same file as RAGInterface (Imperative Shell). Separation into two files adds complexity without testability benefit
- **Lazy imports via `__getattr__`**: Package `__init__.py` uses lazy loading to prevent circular imports, following the pattern used by embeddings and ingestion modules
- **Pre-LLM gate**: Both query() and query_stream() check for empty search results before calling the LLM, saving latency and cost
- **Context-first prompt**: User message places context before question (question sits at end of prompt in high-attention position)
- **Low temperature for RAG**: Uses temperature=0.3 for generation (lower than default 0.7) to prioritize factual grounding over creative generation
- **RAGStream accumulation**: RAGStream accumulates tokens internally during iteration; `to_response()` assembles the final RAGResponse without re-iteration
- **System prompt instructs citation style**: System prompt requires [@citekey] citation format and instructs "ONLY use provided context"
- **Chunk attribution format**: Each chunk prefixed with `[@citekey, section]` header for source traceability in the context window

## Invariants

- `assemble_context()` returns empty string for empty input (never None)
- `build_messages()` always returns exactly 2 messages: one system, one user
- RAGInterface never calls LLM with empty context (pre-LLM gate catches this)
- RAGStream.to_response() can be called at any point (returns partial answer if iteration incomplete)

## Key Files

- `interface.py` - assemble_context(), build_messages() (pure), RAGInterface (orchestrator), RAGStream (streaming wrapper)

## Gotchas

- `RAGStream.__iter__()` wraps LLM stream errors as `RAGError` with `LLM_GENERATION_FAILED` code
- `RAGInterface.query()` also wraps LLM errors as `RAGError` (not raw `LLMError`)
- The `_CONTEXT_SEPARATOR` between chunks is `\n\n---\n\n` (markdown horizontal rule)
- `assemble_context()` does not deduplicate chunks (caller responsibility to provide clean results)
- `RAGStream` holds a reference to the token iterator; do not iterate the underlying iterator directly after wrapping
