# Claude Code Integration

Last updated: 2026-04-15

## Vision

Make the document library a first-class tool in Claude Code sessions. When working on academic projects, Claude can search the corpus, retrieve specific documents, get RAG-generated answers, and surface relevant literature — all through structured MCP tool calls rather than ad-hoc shell commands.

This is also the first external client of the Library API. The tool surface defined here (search, show, ask, list) is the same surface the daemon will later expose over a socket for Neovim and other clients. Building the MCP server first validates that API surface with a real consumer before committing to the daemon's architecture.

## Current State

No MCP server or Claude Code-specific integration exists. The Library API (`core/library.py`) exposes all needed operations. CLI commands have `--json` output modes. The library is usable via shell commands in Claude Code sessions today, but with poor ergonomics (untyped output, cold-start latency on every invocation, no session state).

## Near-Term (next to build)

### MCP Server

An MCP server exposing library operations as structured tools. Claude Code discovers and connects to it automatically via `.mcp.json` at the project root.

**Technical approach:**
- FastMCP framework (part of the `mcp` SDK, v1.27.0+) — decorators + type hints auto-generate tool schemas
- stdio transport (JSON-RPC 2.0) — Claude Code manages the subprocess lifecycle
- In-process Library instance — models (embedding, cross-encoder) loaded once at startup, shared across tool calls
- Long-lived process — acceptable cold start (~5-10s) since Claude Code keeps the server up for the session duration

**Tools to expose (read/query operations):**
- `search_library` — hybrid/vector/FTS search with limit, mode, doc scope, reranking toggle
- `ask_library` — RAG question-answering with model selection, doc scope, mode
- `show_document` — full document details (metadata, status, embedding info) by UUID or @citekey
- `list_documents` — paginated document listing with optional status filter
- `get_document_text` — extracted markdown content for a specific document (useful for Claude to read a paper directly)

**Tools to defer (write operations):**
- add, delete, update, reextract, embed — these are management operations better handled via CLI. Exposing them as MCP tools adds complexity (confirmation flows, error handling) without clear value for research workflows.

**Configuration (`.mcp.json` at project root):**
```json
{
  "mcpServers": {
    "local-library": {
      "command": "uv",
      "args": [
        "--directory",
        "/Users/strophios/development/local-library",
        "run",
        "local-library-mcp"
      ]
    }
  }
}
```

**Key design decisions to make:**
- Return format: structured JSON vs. formatted markdown? Claude works well with both, but markdown is more readable in conversation output. Could offer both via a `format` parameter.
- Session state: should the server track recently accessed documents or search results across tool calls? Useful for "show me more about that third result" style interactions, but adds complexity.
- Error handling: MCP tools should return error strings (not raise exceptions) for graceful degradation. How verbose should error messages be?
- `ask_library` and the LLM layer: this tool calls our RAG pipeline which calls an LLM. When Claude Code *is* Claude, there's an interesting recursion — Claude calling a tool that calls Claude. This works fine technically (the RAG pipeline uses a separate API call via LiteLLM), but we should consider whether Claude Code could skip the inner LLM call and do the answer synthesis itself from the retrieved context. That would be a `get_context` tool (retrieval only, no LLM generation) as an alternative to `ask_library`.
- stdout discipline: stdio transport means all stdout is protocol traffic. All logging must go to stderr or to file. Library code that prints to stdout would break the protocol.

**What we already know works:**
- Library class is instantiable and holds all needed state
- `--json` output modes exist for search and ask commands (validates the output shapes)
- The retriever protocol, RAG interface, and document storage are all tested at scale (1,216 docs)

### Research Skills (layer on top of MCP)

After the MCP server works, Claude Code skills can encode research workflows:
- "When the user mentions academic literature, search the library first"
- "When citing a claim, verify it against the corpus"
- "When starting a literature review, list relevant documents and summarize key arguments"

These are essentially CLAUDE.md instructions or Claude Code skills that reference the MCP tools. Low effort, high leverage, but depend on having the MCP server working first.

## Longer-Term Ideas

### Context-Aware Research Agent
A custom Claude Code agent specialized for literature research. Has access to MCP tools plus knowledge of how to conduct systematic searches, cross-reference findings, and build literature reviews. More structured than ad-hoc tool use.

### Daemon Migration
When the library daemon is built (for Neovim), the MCP server becomes a thin client:
- Swaps from in-process `Library()` to daemon socket calls
- Gains shared model lifecycle (lower memory if multiple clients)
- No change to tool interfaces or Claude Code configuration

### Write Operations
If experience shows that adding documents or managing metadata from within Claude Code sessions is valuable, selectively expose write operations with appropriate confirmation flows.

## Dependencies

**Provides to other areas:**
- Validates the Library API surface that the daemon will expose
- Tool schemas become the canonical operation definitions shared across clients

**Needs from other areas:**
- Full corpus import (done) — library search is only useful with content
- RAG Pipeline Improvements — search/answer quality affects tool usefulness
- Extraction Resilience — FAILED documents with no metadata are confusing in tool results

**Independent of:**
- Web Content Ingestion (but ingested web content appears in MCP search results)
- Note Management (but notes could become MCP resources later)
- Neovim Citation Workflow (shared API surface, but no direct dependency)

## References

- MCP Python SDK: `mcp` package v1.27.0+ on PyPI
- FastMCP framework: `mcp.server.fastmcp` module (decorator-based tool definitions)
- Claude Code MCP docs: https://code.claude.com/docs/en/mcp
- MCP specification: https://modelcontextprotocol.io/docs/learn/architecture
- `roadmap.md` — positions MCP server as first external client validating daemon API
- `docs/feature-areas/neovim-citation-workflow/README.md` — daemon design decisions (shared infrastructure)
