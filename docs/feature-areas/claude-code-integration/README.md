# Claude Code Integration

Last updated: 2026-05-11

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

`.mcp.json` at the project root (plugin form, since the plugin shipped — uses `${CLAUDE_PLUGIN_ROOT}` so the file is portable across installs):
```json
{
  "mcpServers": {
    "local-library": {
      "command": "uv",
      "args": [
        "--directory",
        "${CLAUDE_PLUGIN_ROOT}",
        "run",
        "local-library-mcp"
      ]
    }
  }
}
```

Claude Code substitutes `${CLAUDE_PLUGIN_ROOT}` at plugin-install time with the absolute path to the installed plugin's working tree. Pre-plugin, this field was a hardcoded user-specific path; the migration happened as part of the plugin work (see `## Plugin` below).

### What we validated

- FastMCP framework (mcp SDK v1.27.0+) handles tool schema generation cleanly via decorators and type hints.
- Cold start (~2-5s for the embedder on first search) is acceptable for long-lived Claude Code sessions. Subsequent calls are fast.
- The Library API's read surface (search, show, list, chunk access) maps directly to MCP tools without wrapper complexity. New public methods were added to Library for chunk access (`get_chunks_for_document`, etc.) so the MCP layer doesn't need private-API access.

## Plugin

**Shipped (merged `66ac046`).** The repo ships as a Claude Code plugin (in-repo, no separate package): six skills bundled with the MCP server config. With the plugin installed, a citekey dropped in conversation prompts a library lookup automatically, and grounded writing/checking is the path of least resistance.

End-user install, full per-skill descriptions, test-drive scenarios, configuration, and troubleshooting are in [`skills/README.md`](../../../skills/README.md). This section captures the design history and rationale.

### Three-layer skill architecture

Skills are organized in three layers, each addressing a different aspect of the "make Claude reach for the library by default" problem:

- **Orientation (always-apply)**: cue-driven skills that fire before training-derived answers. `using-local-library-mcp` catches citekey patterns and library-grounding phrasings; `handling-extraction-quality` catches math/figure/table requests and falls back to the PDF when extracted markdown shows genuine garbling cues. The extraction-quality skill's calibration is non-obvious and worth carrying forward to any similar skills: well-formed LaTeX is the *success* case, not garbling — only malformed LaTeX (subscript collapse like `QWQ i`, escape-sequence remnants like `\n(1)`, empty math delimiters, broken tables, `Status: needs_review`) triggers PDF fallback. This was refined post-shipping in a 2026-04-26 fix.
- **Kernel**: `grounding-against-library` is the atomic per-assertion retrieve → quote → synthesize → report cycle. Procedural skills cross-invoke it per claim. Scope guardrail: returns control to its invoking skill on broad inputs rather than attempting one-pass synthesis, which forces composing skills to handle decomposition. The kernel's `references/tool-selection.md` also documents the `no_rerank` inversion footgun (`False` = reranking ON; `True` = OFF).
- **Procedural composition**: `drafting-with-grounded-sources`, `implementation-check-against-papers`, `verifying-claims-against-library` each decompose complex requests and orchestrate the kernel per claim. Output shapes are distinctive and audit-able by design (prose + grounding-summary appendix, assertion table, claim table).

Why this split? Plugins can't ship a user-global `CLAUDE.md`, so orientation skills must be always-apply to catch citekeys and extraction problems automatically. The kernel is deliberately atomic so composing skills can decompose; without this scope guardrail, the kernel would bias toward "one chunk answers the whole question," short-changing multi-source synthesis. The procedural skills exist to handle the request shapes (drafting, code-check, claim-check) that benefit from explicit per-claim grounding plus an audit-able output format.

**Known scope gap.** The procedural skills are claim-shaped — they assume specific claims to defend, verify, or check. Topic exploration / summary / cross-source synthesis requests ("tell me what my library says about X", "tour these papers") fall through to ad hoc `using-local-library-mcp` behavior. A dedicated exploration/synthesis skill is a likely next addition; see *Longer-Term Ideas > Plugin v0.2.0 follow-ups* below.

### Design and implementation artifacts

- `docs/design-plans/2026-04-24-local-library-claude-code-plugin.md` — design document
- `docs/implementation-plans/2026-04-24-local-library-claude-code-plugin/` — six-phase implementation plan
- `tests/skills/` — RED baselines (Phase 1), GREEN/Tier-3 verifications (Phases 2–4), install-and-permissions audit (Phase 5), smoke transcripts + DoD audit (Phase 6)
- `skills/README.md` — end-user install, full skill descriptions, test-drive scenarios, configuration, troubleshooting

The plugin's runtime assets (`.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `.mcp.json`, the six `skills/<name>/SKILL.md` files, `grounding-against-library/references/tool-selection.md`) are catalogued in `skills/README.md § Where the plugin's pieces live`.

## Near-Term (next to build)

### Write-operation tools (if warranted)

The current tool set is deliberately read-only. If real use surfaces a pattern where `add`, `reextract`, or metadata updates from within Claude Code sessions prove valuable, expose them selectively. Each write tool needs confirmation semantics and careful error handling, so add them one at a time based on demonstrated demand rather than speculative coverage.

## Longer-Term Ideas

### Plugin v0.2.0 follow-ups

Captured in `tests/skills/phase6/test-drive-writeup.md` from the plugin's test-drive write-up:
- **Citekey rendering normalization** — procedural skills that consume kernel reports occasionally render citekeys with stray underscores (`@Vaswani_2017` for `@Vaswani2017`). Normalize at the procedural-skill boundary before user-facing output.
- **Pandoc-citeproc-compatible citation formatting** — investigation: would `[@citekey, p. N]` syntax (matching pandoc-citeproc) be more useful than the current inline `(@citekey)` form? Counter-argument: chunk indices are not page numbers, and forcing the user to manually translate maintains friction that prevents accidental misrepresentation.
- **`literature-synthesis` skill** — cross-source synthesis at the literature-review level, beyond the per-paragraph drafting scope of `drafting-with-grounded-sources`.
- **Subagent wrappers for procedural skills** — heavyweight grounding work happens in a fresh-context subagent rather than the user's main session, to avoid context bloat on long drafts.
- **Neovim REPL integration** — the original headline use case the plugin is meant to support: citekey workflows in editor.

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

- `skills/README.md` — end-user plugin interface doc (install, full skill descriptions, test-drive scenarios, configuration)
- `src/local_library/mcp/CLAUDE.md` — implementation contracts and conventions
- `docs/design-plans/2026-04-15-mcp-server.md` — original MCP server design
- `docs/implementation-plans/2026-04-15-mcp-server/` — phased implementation plan
- MCP Python SDK: `mcp` package v1.27.0+ on PyPI
- FastMCP framework: `mcp.server.fastmcp` module (decorator-based tool definitions)
- Claude Code MCP docs: https://code.claude.com/docs/en/mcp
- MCP specification: https://modelcontextprotocol.io/docs/learn/architecture
- `docs/feature-areas/neovim-citation-workflow/README.md` — daemon design decisions (shared infrastructure)
