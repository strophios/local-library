# MCP Server Domain

Last verified: 2026-04-15

## Purpose

Exposes the document library to Claude Code via MCP (Model Context Protocol) tools over stdio transport using the FastMCP framework. Wraps the existing Library API without adding new data models or capabilities. All tools are read-only.

## Contracts

- **Exposes**: MCP tools (search_library; show_document, list_documents, get_document_text planned for Phase 2)
- **Guarantees**:
  - All tools return markdown with consistent, parseable structure
  - Citekeys appear after `@`, scores labeled, chunk indices labeled
  - Error convention: `⚠ USER-FACING ERROR:` prefix for infrastructure errors (Claude should inform user); `Error:` prefix for tool-level errors (Claude can handle or work around)
  - Empty search results are not errors — tool returns suggestions
  - Library instance created once at startup, shared across tool calls
  - Models load lazily on first use (~2-5s one-time for embedder)
  - All logging to stderr; stdout reserved for JSON-RPC protocol
- **Expects**: Library API available; sqlite-vec for search features (graceful error when unavailable)

## Dependencies

- **Uses**: `core.Library` (orchestrator), `core.errors` (LookupError, EmbeddingError, FTSQueryError), `core.vec_extension` (is_vec_available), `cli.utils` (resolve_identifier), `embeddings.base` (SearchResult)
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
- Tool-level errors always include actionable suggestions where possible
- Library instance is never None during tool execution (assert in each tool function)

## Key Files

- `server.py` — FastMCP app, tool definitions, Library lifecycle, logging setup (Imperative Shell)
- `formatters.py` — Markdown rendering functions: format_search_results, format_user_error, format_tool_error, format_empty_results (Functional Core)

## Gotchas

- stdout is reserved for JSON-RPC protocol — never use print() in tool functions; use logger (configured to stderr)
- Library created with `embed_on_add=False` since MCP server is read-only
- `resolve_identifier()` raises LookupError on unknown identifiers — catch in tool functions
- `FTSQueryError` inherits from `EmbeddingError` — catch FTSQueryError before EmbeddingError in exception handlers
- First search call triggers embedder model loading (~2-5s); subsequent calls are fast
- `TOKENIZERS_PARALLELISM` env var set to "false" to suppress HuggingFace warning in forked process
