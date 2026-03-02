# M7: RAG Query Interface Design

## Summary

M7 builds the query-facing half of the RAG system: given a natural language question, the system retrieves relevant document chunks (via the hybrid retrieval pipeline built in M6), assembles them into a prompt with source attribution, and calls an LLM to generate a grounded answer. The answer streams token-by-token to the terminal, concluding with a sources footer that lists the citekeys of contributing documents. If no relevant context was found, the system says so rather than generating an answer.

The implementation introduces two new packages. The `llm/` package is a thin, protocol-based wrapper around LiteLLM that handles provider abstraction, error mapping, and lazy import — it deliberately does nothing beyond wrapping the API call. The `rag/` package contains `RAGInterface`, which orchestrates the full pipeline: context assembly from retrieved chunks (formatting each with its citekey and section header), prompt construction (system + user messages), and delegating generation to the `LLMClient`. A `RAGStream` wrapper handles the streaming path, accumulating tokens during iteration so that a complete `RAGResponse` can be built once the stream finishes. The design introduces no new architectural patterns — it follows the Protocol-based extensibility, lazy initialization, and frozen dataclass result types already established in the codebase.

## Definition of Done

1. **A CLI `ask` command** that accepts a natural language question and returns an LLM-generated answer grounded in library documents, with inline citekey citations (`[@Smith2023]`)
2. **Context assembly** from retrieved chunks — the system retrieves relevant chunks via the existing hybrid retriever (M6) and assembles them into a prompt with source attribution
3. **LiteLLM-backed LLM calls** supporting at minimum Gemini and Claude, with provider/model configurable at the CLI
4. **"I don't know" handling** — when retrieved context is insufficient, the system says so rather than hallucinating
5. **Latency under 10s** for a typical query (dominated by LLM call time, not retrieval)
6. **Response with citations** — the answer references source documents by citekey, and the user can see which documents contributed

**Out of scope for M7:** Multi-turn conversation, MCP integration, auto-tagging, evaluation expansion beyond the existing 12-query baseline.

**Resolved during brainstorming:** Response streaming is IN scope — the CLI streams LLM tokens as they arrive.

## Glossary

- **RAG (Retrieval-Augmented Generation)**: A pattern where an LLM answer is grounded in retrieved document content rather than generated purely from model weights. The model is given relevant text chunks as context and instructed to cite them.
- **citekey**: A short, human-readable document identifier in BetterBibTeX style (e.g., `Smith2023`). Used throughout the system to reference documents; appears inline in LLM-generated answers as `[@Smith2023]`.
- **chunk**: A segment of extracted document text produced by the chunking pipeline. Each chunk carries metadata including its source document, section header, and position. The unit of retrieval and context assembly.
- **`SearchResult`**: The result type returned by the M6 retrieval system. Wraps a `Chunk` with its relevance score and source document metadata (including citekey).
- **hybrid retrieval / RRF fusion**: The M6 retrieval mode that combines vector similarity search and FTS5 keyword search using Reciprocal Rank Fusion, a score-fusion algorithm that merges ranked lists without requiring normalized scores.
- **FTS5**: SQLite's built-in full-text search extension. Implements BM25 ranking for keyword-based retrieval.
- **LiteLLM**: A Python library that provides a unified interface to LLM APIs (OpenAI, Anthropic/Claude, Google Gemini, etc.), abstracting over provider-specific SDKs.
- **`LLMClient` (protocol)**: The thin abstraction over LiteLLM defined in this milestone. Declares `complete()` and `stream()` methods; `LiteLLMClient` is the concrete implementation.
- **`RAGInterface`**: The class that owns RAG-specific orchestration logic — context assembly, prompt construction, and coordinating the LLM call. Distinct from `Library`, which handles higher-level wiring.
- **`RAGStream`**: A wrapper around the LLM token iterator that accumulates tokens during streaming iteration and exposes `to_response()` to produce a complete `RAGResponse` once iteration finishes.
- **`RAGResponse`**: A frozen dataclass capturing the full result of a query: question, answer, source chunks, model, and retrieval mode.
- **lazy initialization**: The pattern of deferring construction of expensive objects (here: `LiteLLMClient`, `RAGInterface`) until first use, rather than at application startup.
- **Protocol (Python)**: A structural subtyping mechanism from `typing`. A class satisfies a Protocol if it implements the required methods, without needing to explicitly inherit from it. Used here for `LLMClient`, `Retriever`, `Chunker`, etc.
- **`@runtime_checkable`**: A decorator that allows `isinstance()` checks against a Protocol at runtime.
- **frozen dataclass**: A Python `@dataclass(frozen=True)` — an immutable data container. Instances cannot be modified after construction.
- **Rich `Live`**: A component from the Rich terminal library that supports dynamically updating terminal output. Used here to display streaming tokens as they arrive.
- **constructor injection**: Passing a dependency (e.g., `LLMClient`) into a class via its constructor rather than having the class create or import it directly. Makes testing easier and decouples components.
- **greedy packing**: Assembling context chunks in order until some limit is reached, without backtracking or optimizing for token budget.
- **pre-LLM gate**: A short-circuit check before calling the LLM. Here: if retrieval returns zero results, skip the API call entirely and return a "no context" response.

## Architecture

### Approach

Custom `RAGInterface` class backed by a thin `LLMClient` protocol wrapping LiteLLM. LlamaIndex was evaluated via a technical spike and set aside — it adds 50-200MB of dependencies primarily for orchestration glue we can write in ~200 lines, and its `CitationQueryEngine` uses numeric `[1]` markers rather than our citekey format.

The design introduces two new packages:

- **`llm/`** — Shared LLM abstraction. `LLMClient` protocol with `complete()` and `stream()` methods. `LiteLLMClient` concrete implementation wrapping `litellm.completion()`. Thin by design — handles lazy import, error mapping to `ErrorCode`, and response unwrapping. Does not handle prompt construction, output parsing, or token budgeting.

- **`rag/`** — RAG query interface. `RAGInterface` class that orchestrates retrieval → context assembly → prompt construction → LLM generation → response packaging. Owns the RAG-specific logic; depends on `LLMClient` for generation and `Retriever` (from M6) for search.

Additionally, `text_extraction.py` is refactored so that `LLMExtractor` uses `LLMClient` instead of calling `litellm.completion()` directly. This unifies the two LLM call sites under a shared abstraction.

### Package Structure

```
src/local_library/
├── llm/                          # NEW: Shared LLM abstraction
│   ├── __init__.py
│   ├── base.py                   # LLMClient protocol
│   └── litellm_client.py        # LiteLLMClient implementation
├── rag/                          # NEW: RAG query interface
│   ├── __init__.py
│   └── interface.py              # RAGInterface, RAGStream
├── core/
│   ├── models.py                 # + RAGResponse dataclass
│   ├── errors.py                 # + RAGError, LLMError, new ErrorCodes
│   └── library.py                # + query(), query_stream() methods
├── ingestion/
│   └── text_extraction.py        # REFACTORED: LLMExtractor uses LLMClient
└── cli/
    ├── main.py                   # + register ask command
    └── ask.py                    # NEW: ask command
```

### Component Responsibilities

| Component | Responsibility | Does NOT do |
|-----------|---------------|-------------|
| `LLMClient` (protocol) | `complete(messages, *, temperature, max_tokens, **kwargs) → str`, `stream(messages, *, temperature, max_tokens, **kwargs) → Iterator[str]` | Prompt construction, context assembly, output parsing |
| `LiteLLMClient` | Lazy litellm import (at construction time, stored on instance), error mapping to `ErrorCode`, response/stream unwrapping | Anything beyond wrapping `litellm.completion` |
| `RAGInterface` | Context assembly from `SearchResult`s, prompt construction with citekey attribution, orchestrate blocking and streaming generation paths | Retrieval (uses `Retriever`), LLM provider details (uses `LLMClient`) |
| `RAGStream` | Wraps streaming token iterator, accumulates tokens during iteration, builds `RAGResponse` via `to_response()` after iteration completes | Driving the iteration (caller does this) |
| `Library.query()` / `Library.query_stream()` | Orchestration: lazy-init `LLMClient` + `RAGInterface`, wire up retriever, delegate, return result | Implementation details of retrieval or generation |
| `cli/ask.py` | Flag parsing, Library context, Rich streaming display, output formatting (Rich tables + JSON) | Business logic |

### Data Flow

```
CLI ask command
  │
  ▼
Library.query_stream(question, model, mode, limit, doc_ids)
  │
  ├─► Retriever.retrieve(question, k=limit, doc_ids=doc_ids)
  │     │
  │     └─► list[SearchResult]  (from M6, unchanged)
  │
  ├─► RAGInterface.query_stream(question, search_results)
  │     │
  │     ├─► assemble_context(search_results)  →  formatted context string
  │     ├─► build_messages(context, question)  →  [system, user] messages
  │     ├─► LLMClient.stream(messages)         →  Iterator[str]
  │     └─► RAGStream(token_iter, search_results, ...)
  │
  └─► RAGStream  →  yields tokens to CLI for live display
                  →  to_response() after iteration for sources footer / JSON
```

### Contracts

**LLMClient protocol:**

```python
@runtime_checkable
class LLMClient(Protocol):
    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs,
    ) -> str: ...

    def stream(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs,
    ) -> Iterator[str]: ...
```

**RAGResponse dataclass:**

```python
@dataclass(frozen=True)
class RAGResponse:
    question: str
    answer: str
    context_chunks: list[SearchResult]
    model: str
    retrieval_mode: str
```

**RAGStream interface:**

```python
class RAGStream:
    context_chunks: list[SearchResult]    # available immediately

    def __iter__(self) -> Iterator[str]:  # yields answer tokens
        ...                               # accumulates internally

    def to_response(self) -> RAGResponse: # call after iteration completes
        ...
```

**New error codes:**

```python
class ErrorCode(str, Enum):
    # ... existing codes ...
    RAG_NO_CONTEXT = "RAG_NO_CONTEXT"
    LLM_GENERATION_FAILED = "LLM_GENERATION_FAILED"
    LLM_MODEL_NOT_FOUND = "LLM_MODEL_NOT_FOUND"
    LLM_RATE_LIMITED = "LLM_RATE_LIMITED"
```

### Context Assembly

Retrieved chunks are formatted with citekey attribution:

```
[@Smith2023] The key finding was that attention mechanisms...

---

[@Jones2021, §Methods] We employed a mixed-methods approach...
```

Each chunk includes its citekey (from `SearchResult.doc_citekey`) and section header (from `SearchResult.chunk.section`) when available. Chunks separated by `\n\n---\n\n`. Simple greedy packing — no token budget management initially (deferred until a concrete need arises).

### Prompt Construction

Two messages: system + user. Context-first, question-last ordering (conventional RAG pattern; question in high-attention position at end of prompt).

- **System prompt**: Research assistant persona, citekey citation instructions (`[@citekey]` format), instruction to acknowledge when context is insufficient. ~100-150 tokens.
- **User message**: Context block followed by question.

System prompt content should be validated against current best practices during implementation. Prompt ordering (context-first vs. question-first) is a tunable choice that can be tested via the evaluation harness.

### "I Don't Know" Handling

Two layers:

1. **Pre-LLM gate**: If retrieval returns zero results, skip the LLM call entirely. Return a response indicating no relevant documents were found. Saves an API call and latency.
2. **Prompt-level**: System prompt instructs the LLM to acknowledge when provided context doesn't contain relevant information.

Score-threshold-based gating deferred — retrieval scores are not normalized across modes (vector: ~0-1, FTS: varies, hybrid: RRF scores), so a meaningful threshold would need calibration.

### CLI Output

**Default (streaming):**

1. Brief "Searching..." indicator during retrieval
2. Answer streams token-by-token via Rich `Live` display
3. Sources footer after streaming completes:

```
Sources:
  [@Smith2023]  "Efficient Attention Mechanisms in Large Language Models"
  [@Jones2021]  "A Survey of Transformer Optimization Techniques"
```

**JSON (`--json`, implies `--no-stream`):**

```json
{
  "question": "...",
  "answer": "...",
  "model": "gemini/gemini-2.0-flash",
  "retrieval_mode": "hybrid",
  "sources": [
    {"citekey": "Smith2023", "title": "...", "doc_id": "...", "chunks_used": 3}
  ]
}
```

**CLI flags:** `--model` (LLM model), `--mode` (retrieval: hybrid/vector/fts), `--limit` (max context chunks), `--json`, `--no-stream`, `--doc` (scope to document via @citekey or UUID).

## Existing Patterns

Investigation confirmed several established patterns that this design follows:

**Library orchestration with sub-component delegation.** Library owns multi-step workflows (e.g., `add()` coordinates 11 steps across acquirers, extractors, and storage) but delegates work to focused sub-components. `RAGInterface` follows this pattern — Library.query() orchestrates, RAGInterface handles RAG-specific logic.

**Lazy initialization for heavy dependencies.** `NomicEmbedder`, `EmbeddingStorage`, and the sqlite-vec extension are all lazily constructed on first use. `LiteLLMClient` follows the same pattern — constructed on first `query()` call, not at Library construction time. The litellm import happens at `LiteLLMClient` construction (stored on instance), not on every method call.

**Protocol-based extensibility.** `Chunker`, `Embedder`, and `Retriever` are all `@runtime_checkable` Protocol classes with frozen dataclass result types. `LLMClient` follows the same pattern.

**Frozen dataclass result types.** `Chunk`, `ChunkEmbedding`, `SearchResult` are all `@dataclass(frozen=True)`. `RAGResponse` follows this pattern.

**ErrorCode enum with domain-specific exceptions.** `EmbeddingError`, `FTSQueryError` inherit from `LocalLibraryError` with `ErrorCode` enum values. `RAGError` and `LLMError` follow this pattern.

**CLI command structure.** Commands follow: validate preconditions → create Library context manager → delegate to Library → format output (Rich tables + JSON). `ask` command follows this pattern.

**No new patterns introduced.** All architectural choices align with existing codebase conventions.

## Implementation Phases

### Phase 1: LLM Abstraction Layer

**Goal:** Shared LLM client protocol and LiteLLM implementation, with error codes.

**Components:**
- `LLMClient` protocol in `src/local_library/llm/base.py` — `complete()` and `stream()` methods with `temperature` and `max_tokens` as named parameters
- `LiteLLMClient` in `src/local_library/llm/litellm_client.py` — wraps `litellm.completion()` with lazy import at construction, error mapping, response/stream unwrapping
- `LLMError` and `RAGError` exception classes in `src/local_library/core/errors.py` with new `ErrorCode` values

**Dependencies:** None (first phase)

**Done when:** `LiteLLMClient` satisfies `LLMClient` protocol, error mapping covers generation failures / rate limits / model not found, tests pass with mocked `litellm.completion`

### Phase 2: Refactor text_extraction.py

**Goal:** Unify LLM call sites under the shared `LLMClient` abstraction.

**Components:**
- `LLMExtractor` in `src/local_library/ingestion/text_extraction.py` — refactored to accept `LLMClient` via constructor injection instead of calling `litellm.completion()` directly
- `Library` constructor in `src/local_library/core/library.py` — threading of `LLMClient` instance to `TextMetadataExtractor` / `LLMExtractor`

**Dependencies:** Phase 1 (LLMClient protocol and LiteLLMClient)

**Done when:** All existing text_extraction tests pass without modification (regression), `LLMExtractor` no longer imports litellm directly

### Phase 3: RAG Data Models and Context Assembly

**Goal:** Pure-function context assembly and prompt construction, with RAGResponse data model.

**Components:**
- `RAGResponse` dataclass in `src/local_library/core/models.py`
- Context assembly function in `src/local_library/rag/interface.py` — formats `list[SearchResult]` into attributed context string with citekeys and section headers
- Prompt construction function in `src/local_library/rag/interface.py` — builds system + user messages from context and question

**Dependencies:** Phase 1 (error codes)

**Done when:** Context assembly correctly formats chunks with citekeys/sections, handles edge cases (missing citekeys, empty sections), prompt construction produces well-formed message list, all tests pass

### Phase 4: RAGInterface with Streaming

**Goal:** Full RAG orchestration with both blocking and streaming paths.

**Components:**
- `RAGInterface` class in `src/local_library/rag/interface.py` — `query()` (blocking) and `query_stream()` (streaming) methods, wiring context assembly + prompt construction + LLMClient
- `RAGStream` class in `src/local_library/rag/interface.py` — wraps streaming iterator with internal accumulation and `to_response()` method
- Pre-LLM gate: skip LLM call when retrieval returns empty results

**Dependencies:** Phase 1 (LLMClient), Phase 3 (context assembly, prompt construction, RAGResponse)

**Done when:** `query()` returns correct `RAGResponse` with mock LLMClient, `query_stream()` yields tokens and `to_response()` produces correct `RAGResponse`, empty-retrieval path skips LLM and returns appropriate response, all tests pass

### Phase 5: Library Integration

**Goal:** Wire RAGInterface into Library with lazy initialization.

**Components:**
- `Library.query()` and `Library.query_stream()` methods in `src/local_library/core/library.py` — orchestrate retriever + RAGInterface, lazy-init LLMClient and RAGInterface on first call
- Constructor parameters for RAG configuration (`rag_model`, etc.)

**Dependencies:** Phase 2 (refactored LLMClient threading), Phase 4 (RAGInterface)

**Done when:** `Library.query()` produces correct RAGResponse with mock LLMClient, lazy initialization works (LLMClient not created until first query), error handling pipeline surfaces LLMError/RAGError correctly, integration tests pass

### Phase 6: CLI Ask Command

**Goal:** User-facing CLI command with streaming display and JSON output.

**Components:**
- `ask` command in `src/local_library/cli/ask.py` — flags for model, mode, limit, json, no-stream, doc; Rich `Live` streaming display; sources footer; JSON output format
- Command registration in `src/local_library/cli/main.py`
- Graceful Ctrl+C handling during streaming

**Dependencies:** Phase 5 (Library integration)

**Done when:** `local-library ask "question"` streams an answer with source citations, `--json` produces valid JSON output, `--no-stream` works, `--doc @citekey` scopes correctly, `--model` switches provider, error cases display cleanly

## Additional Considerations

**Prompt tuning is deferred to runtime.** The system prompt content should be validated against current best practices during implementation. Prompt ordering and phrasing are tunable parameters, not hardcoded design decisions. The existing 12-query evaluation harness provides a regression baseline for measuring prompt changes.

**Testing gaps noted for future work.** Two testing categories are explicitly deferred: (1) integration tests with real LLM API calls (should follow the `@pytest.mark.extraction` opt-in pattern once established), and (2) visual verification of Rich streaming display rendering (requires manual check). Both should be addressed post-M7.

**Token budget management.** Context assembly uses simple greedy packing for now. If future features (multi-turn conversation, very large retrieval sets) need precise token budgeting, the `LLMClient` protocol can be extended with a `count_tokens()` method and a `TokenBudgetManager` can be extracted — but only when a concrete need arises.
