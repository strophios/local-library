# MCP Server Domain

Last verified: 2026-04-16

## Purpose

Exposes the document library to Claude Code via MCP (Model Context Protocol) tools over stdio transport using the FastMCP framework. Wraps the existing Library API without adding new data models or capabilities. All tools are read-only.

## Contracts

- **Exposes**: MCP tools
  - `search_library` — semantic/keyword search with scores, chunk indices, and optional reranking
  - `show_document` — document metadata (citekey, title, authors, date, status, chunk count, CSL-JSON fields)
  - `list_documents` — documents as markdown table with optional status, year, author, title, citekey filters and pagination
  - `get_document_text` — extracted markdown: full text for short docs (<50 chunks), chunk subset for ranges, preview with instructions for long docs
- **Guarantees**:
  - All tools return markdown with consistent, parseable structure
  - Citekeys appear after `@`, scores labeled, chunk indices labeled
  - Error convention: `⚠ USER-FACING ERROR:` prefix for infrastructure errors (Claude should inform user); `Error:` prefix for tool-level errors (Claude can handle or work around)
  - Empty search results are not errors — tool returns suggestions
  - Identifier resolution supports both UUID (full/partial) and @citekey with fuzzy match suggestions on miss
  - File reading errors caught and reported (file may have been moved/deleted)
  - Chunk indices validated: must be non-negative, s <= e, s < total_chunks
  - list_documents filters combine with AND semantics; status, year, year_missing, author_contains, title_contains, citekey_prefix parameters are all optional
  - list_documents year and year_missing are mutually exclusive (tool returns error if both provided)
  - list_documents substring filters (author_contains, title_contains) are case-insensitive; wildcard characters (%, _) are matched literally rather than as patterns
  - list_documents citekey_prefix is case-insensitive prefix match
  - Library instance created once at startup, shared across tool calls
  - Models load lazily on first use (~2-5s one-time for embedder)
  - All logging to stderr; stdout reserved for JSON-RPC protocol
- **Expects**: Library API available; sqlite-vec for search features (graceful error when unavailable)

## Dependencies

- **Uses**: `core.Library` (orchestrator), `core.models` (Document, DocumentStatus), `core.errors` (LookupError, EmbeddingError, FTSQueryError), `core.vec_extension` (is_vec_available), `cli.utils` (resolve_identifier), `embeddings.base` (Chunk, SearchResult)
- **Used by**: Claude Code (via MCP protocol over stdio)
- **Boundary**: MCP MUST NOT be imported by core, embeddings, ingestion, or rag. CLI may import from MCP for shared utilities if needed.

## Key Decisions

- **Functional Core / Imperative Shell**: formatters.py is Functional Core (pure markdown rendering, no I/O). server.py is Imperative Shell (Library lifecycle, MCP protocol, I/O)
- **No RAG tool**: Claude Code is the LLM — it uses search_library to retrieve chunks and synthesizes answers directly, avoiding latency and context isolation of nested LLM calls
- **Module-level Library**: Library instance stored as module-level variable in server.py; created in main() before mcp.run(), closed in finally block
- **Markdown-only returns**: No JSON output option — one format reduces per-call decision overhead for Claude
- **Identifier resolution via cli.utils**: Reuses resolve_identifier() from CLI for UUID/@citekey parsing and fuzzy match suggestions
- **Sync tool functions**: Library API is synchronous; FastMCP handles threading for async event loop

## Invariants

- Tool functions never raise exceptions to MCP protocol — all errors caught and returned as formatted strings
- USER-FACING ERROR prefix only for infrastructure problems (sqlite-vec unavailable, model load failure, empty corpus)
- Tool-level errors always include actionable suggestions where possible (identifier miss → fuzzy suggestions; file not found → path shown)
- Library instance is never None during tool execution (assert in each tool function)
- Identifier resolution via resolve_identifier() returns Document or raises LookupError with suggestions
- File reading respects encoding="utf-8" and catches FileNotFoundError with path information
- Chunk range validation: start >= 0, end >= 0, start <= end, start < total_chunks (for a single-chunk request, start == end is valid)

## Key Files

- `server.py` — FastMCP app, tool definitions (search_library, show_document, list_documents, get_document_text), Library lifecycle, logging setup, chunk preview logic (Imperative Shell)
  - `VALID_MODES = ("hybrid", "vector", "fts")` — search modes
  - `VALID_STATUSES = ("ready", "failed", "needs_review", "pending")` — list filters
  - `SHORT_DOC_THRESHOLD = 50` — chunks threshold for full-text vs. preview
  - `PREVIEW_CHUNK_COUNT = 20` — preview chunk count
- `formatters.py` — Markdown rendering functions: format_search_results, format_document, format_document_list, format_document_text, format_user_error, format_tool_error, format_empty_results (Functional Core)

## Gotchas

- stdout is reserved for JSON-RPC protocol — never use print() in tool functions; use logger (configured to stderr)
- Library created with `embed_on_add=False` since MCP server is read-only
- `resolve_identifier()` raises LookupError on unknown identifiers — catch in tool functions and format with suggestions
- `FTSQueryError` inherits from `EmbeddingError` — catch FTSQueryError before EmbeddingError in exception handlers
- First search call triggers embedder model loading (~2-5s); subsequent calls are fast
- `TOKENIZERS_PARALLELISM` env var set to "false" to suppress HuggingFace warning in forked process
- `get_document_text` checks `doc.extracted_path` for existence (may be None for PENDING/FAILED documents)
- File reading via `Path.read_text()` can raise FileNotFoundError if extracted markdown was moved/deleted — catch and report path
- `SHORT_DOC_THRESHOLD = 50` chunks: documents below this return full text, above this use chunk-based access for efficiency
- Preview mode (long doc without range) shows first `PREVIEW_CHUNK_COUNT` chunks + instructions, not all chunks
