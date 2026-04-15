# MCP Server Design

## Summary

This document describes an MCP (Model Context Protocol) server that exposes the local-library document corpus to Claude Code as a set of callable tools. The server wraps the existing `Library` API — the same one backing the CLI — without adding new data models or capabilities. It runs as a subprocess managed by Claude Code, communicating over stdio using JSON-RPC 2.0, and presents four read-only tools: `search_library` for hybrid/vector/FTS retrieval with optional cross-encoder reranking, `show_document` and `list_documents` for metadata access, and `get_document_text` for fetching extracted markdown content.

The design makes one significant omission deliberately: there is no `ask_library` RAG tool. Claude Code itself is the language model — when it needs an answer grounded in the corpus, it calls `search_library` to retrieve relevant chunks and synthesizes the answer directly, which avoids the latency, cost, and context isolation of a nested LLM call. The server is implemented in a new `mcp/` package following existing project conventions (Functional Core formatters, Imperative Shell server, lazy model loading). Configuration is declared in `.mcp.json` at the project root, and a `pyproject.toml` script entry point makes the server runnable via `uv run local-library-mcp`.

## Definition of Done

- **An MCP server** exposes the document library to Claude Code via 4 read-only tools over stdio transport using the FastMCP framework
- **`search_library`** searches the corpus with configurable mode (hybrid/vector/FTS), document scoping, result limit, and reranking toggle. Returns markdown with ranked results including citekeys, scores, section headers, chunk text, and chunk indices
- **`show_document`** returns document metadata (citekey, title, authors, date, status, embedding status, chunk count) for a given UUID or @citekey
- **`list_documents`** returns a paginated document listing with optional status filter
- **`get_document_text`** returns extracted markdown for a document, with optional chunk-range parameters. Short documents (<50 chunks) return full text; long documents without a range return a header + first ~20 chunks with instructions for requesting specific ranges
- **All tools return markdown** with consistent, parseable structure (citekeys after `@`, scores labeled, chunk indices labeled)
- **Error convention**: infrastructure errors (sqlite-vec unavailable, model load failure, empty corpus) use a `USER-FACING ERROR` prefix signaling Claude should inform the user. Tool-level errors (not found, invalid params, empty results) return actionable suggestions
- **Library instance** created once at server startup, shared across tool calls. Models load lazily on first use
- **Configuration** via `.mcp.json` at project root with `pyproject.toml` script entry point
- **All logging to stderr**; stdout reserved for JSON-RPC protocol

**Out of scope**: write operations (add, delete, update, reextract, embed), `ask_library` RAG tool (Claude Code is the LLM — use `search_library` + Claude's own synthesis), session state across tool calls, streaming responses, daemon integration.

## Glossary

- **MCP (Model Context Protocol)**: An open protocol that lets AI assistants call external tools during a conversation. The "server" here is the provider side — it declares tools and handles calls from the AI client (Claude Code).
- **FastMCP**: A Python framework for building MCP servers with minimal boilerplate. Part of the `mcp` SDK (v1.27.0+). Handles capability negotiation, tool registration, and JSON-RPC dispatch via decorators and type hints.
- **stdio transport**: The communication channel between Claude Code and the MCP server — JSON-RPC 2.0 messages passed over standard input/output of the server subprocess. This is why stdout must be kept free of any non-protocol output.
- **JSON-RPC 2.0**: A lightweight remote procedure call protocol encoded as JSON. FastMCP handles this layer; tool authors deal only with Python functions that return strings.
- **Library**: The central orchestrator class (`core/library.py`) that provides unified access to document storage, retrieval, and embedding operations. The MCP server creates one Library instance at startup and shares it across all tool calls.
- **Retriever / HybridRetriever**: A protocol-based abstraction for document search. `HybridRetriever` fuses results from vector similarity search and FTS5 full-text search using Reciprocal Rank Fusion (RRF). The MCP `search_library` tool delegates to whichever Retriever mode is requested.
- **sqlite-vec**: A SQLite extension that adds vector similarity search. Required for vector and hybrid search modes; its absence is treated as a user-facing error because it substantially degrades search quality.
- **FTS5**: SQLite's built-in full-text search engine. Used alongside sqlite-vec in hybrid search, and as a fallback when sqlite-vec is unavailable.
- **Cross-encoder reranking**: A two-stage retrieval step where an initial broad candidate set is rescored by a model that jointly encodes query and document chunk. Improves ranking quality. Enabled by default; disabled via `no_rerank`.
- **nomic-embed-text-v1.5**: The local embedding model used to convert text to 768-dimensional vectors for similarity search. Loaded lazily on first search call; takes ~2-5 seconds the first time.
- **CSL-JSON**: Citation Style Language JSON — the standard metadata format used by Zotero and citation processors. The system stores bibliographic metadata as CSL-JSON blobs.
- **Citekey**: A short human-readable identifier for a document (e.g., `@Bourdieu1984`), generated in BetterBibTeX style. Used as the primary human-facing identifier across CLI, MCP tools, and search results.
- **Functional Core / Imperative Shell**: An architectural pattern separating pure functions with no side effects (Functional Core — here, `formatters.py`) from code that manages I/O, state, and external dependencies (Imperative Shell — here, `server.py`).
- **Chunk / chunk index**: The unit of retrieval. Extracted markdown is split into overlapping chunks (~512 tokens) for embedding and indexing. A chunk index is its 0-based position within the document's chunk sequence, used to request surrounding context via `get_document_text`.
- **Lazy loading**: Deferring expensive initialization (model loading, extension loading) until the capability is first used rather than at startup. The server boots in ~100ms; the embedder loads on first `search_library` call.
- **`.mcp.json`**: A configuration file at the project root that tells Claude Code how to start and connect to MCP servers. Contains the command to launch the server subprocess.

## Architecture

### Overview

The MCP server is a FastMCP application that wraps the existing Library API. It runs as a long-lived subprocess managed by Claude Code, communicating over stdio (JSON-RPC 2.0). The Library instance is created once at startup; embedding and reranking models load lazily on first use.

### Server Lifecycle

1. Claude Code reads `.mcp.json` and starts the server subprocess
2. Server creates `Library()` instance (~100ms — models not yet loaded)
3. FastMCP handles capability negotiation, declaring 4 tools
4. First search call triggers embedder loading (~2-5s one-time)
5. Subsequent calls are fast (models stay in memory for session duration)
6. Claude Code stops the server when the session ends; `Library.__exit__()` cleans up

### Tool Surface

4 read-only tools, all returning markdown:

| Tool | Library Method | Purpose |
|------|---------------|---------|
| `search_library` | `Retriever.retrieve()` via `Library.get_retriever()` | Search corpus by query. Hybrid/vector/FTS modes, document scoping, reranking toggle. |
| `show_document` | `Library.get()` | Document metadata by UUID or @citekey. |
| `list_documents` | `Library.list()` | Paginated listing with optional status filter. |
| `get_document_text` | `Library.get()` + read `extracted_path`, or chunk-range query from `chunks` table | Extracted markdown content. Full text for short docs, chunk-range for long docs. |

No `ask_library` / RAG tool. Claude Code is the LLM — it calls `search_library` to get relevant chunks and synthesizes the answer itself, which is faster, cheaper, and leverages the full conversation context.

### Tool Contracts

**`search_library(query: str, limit: int = 10, mode: str = "hybrid", doc_id: str | None = None, no_rerank: bool = False) -> str`**

Parameters:
- `query` — search string
- `limit` — max results, default 10, capped at 100
- `mode` — "hybrid" (default), "vector", or "fts"
- `doc_id` — optional UUID or @citekey to scope search to one document
- `no_rerank` — disable cross-encoder reranking

Returns markdown with document-grouped results: citekey, title, score, section header, chunk text excerpt, chunk_index. Chunk indices are labeled to enable follow-up `get_document_text` calls for surrounding context.

**`show_document(doc_id: str) -> str`**

Parameters:
- `doc_id` — UUID (full or partial) or @citekey

Returns markdown with: citekey, title, authors, date, document status, embedding status, chunk count, CSL-JSON metadata fields, original path. On identifier miss, returns fuzzy match suggestions.

**`list_documents(status: str | None = None, limit: int = 20) -> str`**

Parameters:
- `status` — optional filter: "ready", "failed", "needs_review", "pending"
- `limit` — max results, default 20, capped at 100

Returns markdown table with: citekey, title, authors, status, embedding status. Header shows total count ("Showing 20 of 1,216 documents").

**`get_document_text(doc_id: str, start_chunk: int | None = None, end_chunk: int | None = None) -> str`**

Parameters:
- `doc_id` — UUID or @citekey
- `start_chunk` — optional 0-based chunk index to start from
- `end_chunk` — optional chunk index to end at (inclusive)

Behavior:
- Short documents (<50 chunks): returns full extracted markdown regardless of range params
- Long documents with range specified: returns chunks in that range with section headers preserved and chunk indices labeled
- Long documents without range: returns document header (title, total chunks, section outline from chunk section headers) plus first ~20 chunks, with a note explaining how to request specific ranges

### Return Format

All tools return markdown with consistent, parseable structure. No JSON option — one format, always the same, no per-call decision overhead for Claude.

Search results example:
```
### Results (3 chunks from 2 documents)

1. **@Bourdieu1984** | score: 0.997 | *Distinction*
   Section: Chapter 2 — The Social Space and Its Transformations
   Chunk 42 of 1987
   > The social space is constructed in such a way that agents
   > or groups are distributed in it according to their position...

2. **@Fuhse2015** | score: 0.988 | *Social Networks as Communicative Structures*
   Section: Field Theory
   Chunk 8 of 31
   > Bourdieu's field theory provides a relational framework
   > for understanding...
```

### Error Convention

Two error tiers, distinguished by prefix:

**User-facing errors** (infrastructure, data integrity — Claude should inform the user):
```
⚠ USER-FACING ERROR: Vector search unavailable. The sqlite-vec extension
is not loaded. This significantly impacts search quality. Please inform the
user and suggest running `uv run local-library search` from the terminal
to diagnose.
```

Triggers: sqlite-vec unavailable, database not found or corrupt, embedding model failed to load, empty corpus.

**Tool-level errors** (Claude can handle or work around):
```
Error: No document found matching 'xyz'. Did you mean @Smith2023 or @SmithJones2024?
```

Triggers: document not found, ambiguous identifier, invalid parameters, chunk range out of bounds. Empty search results are not errors — the tool returns a helpful suggestion to try different terms.

Tool descriptions include the instruction: "Errors prefixed with 'USER-FACING ERROR' should be reported to the user rather than worked around."

### Module Structure

```
src/local_library/mcp/
├── __init__.py       # Package root (minimal, lazy imports)
├── server.py         # FastMCP app, tool definitions, Library lifecycle, logging setup
└── formatters.py     # Markdown rendering functions (Functional Core)
```

**`server.py`** (Imperative Shell) — Creates the FastMCP app, instantiates Library, defines 4 tool functions. Each tool: validate input → call Library method → catch exceptions → format via `formatters.py` → return markdown string.

**`formatters.py`** (Functional Core) — Pure functions: `format_search_results(list[SearchResult]) -> str`, `format_document(Document) -> str`, `format_document_list(list[Document], total: int) -> str`, `format_document_text(text: str, chunks: list[Chunk], ...) -> str`. Testable independently.

**Entry point** — registered in `pyproject.toml` as `local-library-mcp = "local_library.mcp.server:main"`. The `.mcp.json` config calls `uv run local-library-mcp`.

### stdout Discipline

stdio transport means all stdout is JSON-RPC protocol traffic. At server startup, `main()` configures Python's root logger to stderr and redirects `sys.stdout` to stderr before initializing Library. FastMCP handles the actual stdio protocol on the real stdout file descriptor. Library code, sentence-transformers, and other dependencies that may print to stdout are protected by this redirect.

## Existing Patterns

**Package structure**: The `mcp/` package follows the established pattern of domain packages (`cli/`, `core/`, `embeddings/`, `ingestion/`, `llm/`, `rag/`). Each has `__init__.py` with lazy imports and a domain CLAUDE.md.

**Functional Core / Imperative Shell**: `formatters.py` is Functional Core (pure markdown rendering, no I/O). `server.py` is Imperative Shell (Library instantiation, MCP protocol, I/O). Follows the same split as `cli/` (Imperative Shell commands) vs. `core/models.py` (Functional Core types).

**Lazy model loading**: The server relies on Library's existing lazy loading — `NomicEmbedder` and `CrossEncoderReranker` load on first use, not at init. This matches the pattern in `embeddings/nomic.py` and `embeddings/reranking.py`.

**Identifier resolution**: `resolve_identifier()` in `cli/utils.py` handles UUID/@citekey parsing and fuzzy matching. The MCP tools reuse this logic (imported directly or extracted to a shared utility).

**`--json` output shapes**: The CLI's JSON output formats (`cli/search.py:134-151`, `cli/ask.py:204-227`) informed the markdown return format design. The same fields appear in both, just rendered differently.

**No new domain concepts introduced**. The MCP server consumes existing types (Document, SearchResult, Chunk, Retriever) and produces markdown strings. No new models, no schema changes, no new protocols.

## Implementation Phases

### Phase 1: Server Scaffold + Search Tool

**Goal:** A working MCP server with one tool that Claude Code can discover and call.

**Components:**
- `src/local_library/mcp/__init__.py` — package init with lazy imports
- `src/local_library/mcp/server.py` — FastMCP app, Library lifecycle (init/cleanup), stderr logging setup, stdout redirect, `search_library` tool definition
- `src/local_library/mcp/formatters.py` — `format_search_results()` markdown renderer
- `.mcp.json` at project root — server configuration for Claude Code
- `pyproject.toml` script entry point — `local-library-mcp`
- `src/local_library/mcp/CLAUDE.md` — domain contract documentation

**Dependencies:** None (first phase). Library API and all retrieval infrastructure already exist.

**Done when:** `uv run local-library-mcp` starts the server. Claude Code discovers the `search_library` tool. A search query returns markdown results with citekeys, scores, and chunk text. Formatter has unit tests. Error cases (invalid mode, sqlite-vec unavailable) return appropriate error strings.

### Phase 2: Document Tools

**Goal:** Complete the tool surface with document metadata, listing, and text retrieval.

**Components:**
- `show_document` tool in `server.py` — wraps `Library.get()` with identifier resolution and fuzzy matching
- `list_documents` tool in `server.py` — wraps `Library.list()` with status filtering and pagination
- `get_document_text` tool in `server.py` — reads extracted markdown or chunk-range from database, with defensive cap on long documents
- Corresponding formatters in `formatters.py` — `format_document()`, `format_document_list()`, `format_document_text()`
- Error convention implementation — user-facing error prefix for infrastructure errors, fuzzy match suggestions for identifier misses

**Dependencies:** Phase 1 (server scaffold, FastMCP app, Library lifecycle)

**Done when:** All 4 tools work in Claude Code. `get_document_text` correctly handles short docs (full text), long docs with range (chunk subset), and long docs without range (header + first 20 chunks + instructions). Formatters have unit tests. Error convention tested for both tiers.

### Phase 3: Integration Testing and Polish

**Goal:** Verified end-to-end behavior in Claude Code, documentation, and any fixes from real usage.

**Components:**
- End-to-end testing in Claude Code — verify tool discovery, model loading latency, search quality, document retrieval, error handling
- stdout audit — verify no Library dependencies leak to stdout during real usage
- CLAUDE.md section or skill — instructions for Claude on when and how to use library tools, user-facing error handling convention
- Domain CLAUDE.md for `mcp/` package — contracts, dependencies, invariants

**Dependencies:** Phase 2 (all tools implemented)

**Done when:** All tools work reliably in Claude Code sessions. No stdout corruption observed. CLAUDE.md documents library tool usage. Model loading latency is acceptable (one-time ~5s, subsequent calls fast).

## Additional Considerations

**Daemon migration path:** When the library daemon is built, the MCP server swaps from in-process `Library()` calls to daemon socket calls. The tool interfaces, markdown formatters, and `.mcp.json` config don't change. Only `server.py`'s Library instantiation code changes. This swap should be a single-phase modification, not a rewrite.

**No session state for MVP.** Each tool call is independent. If usage reveals that "show me more about that third result" patterns are common, session state (caching recent search results by query) can be added in `server.py` without changing tool interfaces. Defer until real usage data exists.

**pymupdf dependency.** `get_document_text` reads from already-extracted markdown files, not raw PDFs. No new runtime dependency needed for the MCP server itself.

**Concurrent calls.** Claude Code sends one tool call at a time. No concurrency concerns. If a future MCP client sends concurrent calls, Library's SQLite connection would need serialization, but this is not a current concern.
