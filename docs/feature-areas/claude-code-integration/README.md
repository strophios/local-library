# Claude Code Integration

Last updated: 2026-04-16

## Vision

Make the document library a first-class tool in Claude Code sessions. When working on academic projects, Claude can search the corpus, retrieve specific documents, and surface relevant literature — all through structured MCP tool calls rather than ad-hoc shell commands.

This is also the first external client of the Library API. The tool surface defined here is the same surface the daemon will later expose over a socket for Neovim and other clients. Building the MCP server first validates that API surface with a real consumer before committing to the daemon's architecture.

## Current State

**MCP server is built and merged (see commits `fb74a7f..1e0fefb`).** Four read-only tools expose library operations to Claude Code over stdio transport. Claude Code discovers the server via `.mcp.json` at the project root. Tools return markdown; the server loads models once at startup and shares them across tool calls.

Implementation lives under `src/local_library/mcp/` with a domain CLAUDE.md documenting contracts and conventions.

### Tools

- `search_library` — hybrid/vector/FTS search. Returns ranked results with citekeys, scores, section headers, and chunk indices. Supports `limit`, `mode`, `doc` scope, and a reranking toggle.
- `show_document` — document metadata (citekey, title, authors, date, status, chunk count, CSL-JSON fields) by UUID or @citekey.
- `list_documents` — markdown table of documents with optional status filter and pagination.
- `get_document_text` — extracted markdown content. Returns full text for short documents (<50 chunks); for longer documents, returns a preview of the first 20 chunks plus instructions for fetching specific chunk ranges. Chunk indices from `search_library` feed directly into this tool.

### Key design decisions made

- **No `ask_library` tool.** The original plan included a RAG-based answer tool, but building it would mean Claude calling a tool that calls another LLM. Instead, `search_library` returns chunks and Claude synthesizes answers directly. This eliminates latency, avoids context isolation between the inner LLM call and the outer session, and keeps our codebase simpler.
- **Markdown-only returns.** No JSON format option. One output format reduces per-call decision overhead for Claude and keeps tool output readable in conversation.
- **No session state.** Each tool call is stateless. "Show me more about that third result" is handled by Claude re-issuing a tool call with the right identifier, not by the server tracking conversational context.
- **Error convention with two severity levels.** `⚠ USER-FACING ERROR:` prefix signals infrastructure problems (sqlite-vec unavailable, empty corpus) that Claude should surface to the user. Plain `Error:` means tool-level issues (identifier miss, invalid range) that Claude can work around or retry. Tool functions never raise to the MCP protocol.
- **stdout is protocol-only.** All logging goes to stderr. A dedicated audit test (`tests/mcp/test_stdout_discipline.py`) verifies that importing and invoking tools produces zero stdout output. This prevents any accidental `print()` from breaking the JSON-RPC stream.
- **Chunk-based long-doc access.** Documents above 50 chunks return a preview rather than the full text. Chunk indices returned by `search_library` let Claude fetch specific passages on demand instead of loading entire papers.

### Configuration

`.mcp.json` at the project root:
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

### What we validated

- FastMCP framework (mcp SDK v1.27.0+) handles tool schema generation cleanly via decorators and type hints.
- Cold start (~2-5s for the embedder on first search) is acceptable for long-lived Claude Code sessions. Subsequent calls are fast.
- The Library API's read surface (search, show, list, chunk access) maps directly to MCP tools without wrapper complexity. New public methods were added to Library for chunk access (`get_chunks_for_document`, etc.) so the MCP layer doesn't need private-API access.

## Near-Term (next to build)

### Research skills layered on MCP

The server is working; now encode the workflows. Claude Code skills (CLAUDE.md instructions or project-level skills) can reference the MCP tools:

- "When the user mentions a paper or concept from the literature, search `local-library` first before external search."
- "When citing a claim, verify it against the corpus via `search_library` and quote the relevant chunk."
- "When starting a literature review in this project, `list_documents` with relevant status, then `search_library` for the topic."

These are low effort, high value. They don't require code changes — just a few well-placed skill definitions that point at the existing tools.

### Write-operation tools (if warranted)

The current tool set is deliberately read-only. If real use surfaces a pattern where `add`, `reextract`, or metadata updates from within Claude Code sessions prove valuable, expose them selectively. Each write tool needs confirmation semantics and careful error handling, so add them one at a time based on demonstrated demand rather than speculative coverage.

## Longer-Term Ideas

### Context-Aware Research Agent
A custom Claude Code agent specialized for literature research. Has access to MCP tools plus knowledge of how to conduct systematic searches, cross-reference findings, and build literature reviews. More structured than ad-hoc tool use.

### Daemon Migration
When the library daemon is built (for Neovim), the MCP server becomes a thin client:
- Swaps from in-process `Library()` to daemon socket calls
- Gains shared model lifecycle (lower memory if multiple clients)
- No change to tool interfaces or Claude Code configuration

## Dependencies

**Provides to other areas:**
- Validates the Library API surface that the daemon will expose (confirmed with real consumer)
- Tool contracts (markdown-only, stateless, two-tier errors) inform daemon protocol design
- Motivated public Library methods for chunk access that benefit other clients too

**Needs from other areas:**
- Full corpus import (done — 1,216 docs) — library search is only useful with content
- RAG Pipeline Improvements — search quality directly affects tool usefulness
- Extraction Resilience (done) — FAILED documents now retain citekey and filename metadata, so they're identifiable in tool results rather than anonymous errors

**Independent of:**
- Content Ingestion (but ingested web content will appear in MCP search results)
- Note Management (but notes could become MCP resources later)
- Neovim Citation Workflow (shared API surface, but no direct dependency)

## References

- `src/local_library/mcp/CLAUDE.md` — implementation contracts and conventions
- `docs/design-plans/2026-04-15-mcp-server.md` — original design
- `docs/implementation-plans/2026-04-15-mcp-server/` — phased implementation plan
- MCP Python SDK: `mcp` package v1.27.0+ on PyPI
- FastMCP framework: `mcp.server.fastmcp` module (decorator-based tool definitions)
- Claude Code MCP docs: https://code.claude.com/docs/en/mcp
- MCP specification: https://modelcontextprotocol.io/docs/learn/architecture
- `docs/feature-areas/neovim-citation-workflow/README.md` — daemon design decisions (shared infrastructure)
