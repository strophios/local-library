# Claude Code Integration

Last updated: 2026-05-09

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

**Shipped (merged `66ac046`).** The repo also ships as a Claude Code plugin (in-repo, no separate package): six skills bundled with the MCP server config Claude Code needs to talk to your library. With the plugin installed, a citekey dropped in conversation prompts a library lookup automatically, and grounded writing/checking is the path of least resistance.

### Three-layer skill architecture

- **Orientation (always-apply)**:
  - `using-local-library-mcp` — citekey patterns (`@Name2023`), library-grounding cues ("what does X argue", "from my library"), and verification phrasings trigger MCP tool use before training-derived answers. Treats `@citekey` as a library handle rather than a topic label.
  - `handling-extraction-quality` — math/equation/figure/table prompts trigger evaluation of the retrieved markdown for genuine garbling cues (subscript collapse like `QWQ i`, escape-sequence remnants like `\n(1)`, empty math delimiters, broken tables, `Status: needs_review`). Escalates to native `Read` on the PDF when cues fire. Provenance disclosure is mandatory either way: chunk index for markdown, page number for PDF. Well-formed LaTeX (`$$...$$`, `\sum`/`\int`/`\frac` in math delimiters) is the success case, NOT garbling — only malformed LaTeX triggers escalation.
- **Kernel**: `grounding-against-library` — atomic per-assertion retrieve → quote → synthesize → report cycle. Scope guardrail: kernel returns control to its caller on broad inputs, requesting decomposition into atomic assertions. Six-step procedure (confirm scope, formulate query/queries, retrieve, widen context, synthesize per-source tags, report per-source rows + aggregate). The kernel's `references/tool-selection.md` documents tool-call shapes (including the `no_rerank` inversion footgun: `no_rerank: bool = False` means reranking ON; setting True DISABLES reranking).
- **Procedural composition** (cross-invokes the kernel per-claim):
  - `drafting-with-grounded-sources` — three input shapes (claims supplied → proceed; argument-shaped without claims → surface inferred propositions for review; topic-only exploration → return control to using-local-library-mcp). Output: prose with inline `@citekeys` + grounding-summary appendix listing per-proposition citekey/chunk/quote/status.
  - `implementation-check-against-papers` — decompose code into checkable claims (algorithm shape, hyperparameters, loss terms, normalization, edge cases), ground each via the kernel. For equation/symbol claims with garbled markdown, cross-invokes `handling-extraction-quality`. Output: assertion table mapping each claim to its paper locus + status (match/mismatch/partial/not-found).
  - `verifying-claims-against-library` — enumerate citation-bearing claims, per-claim grounding, output claim table with quoted support and a summary line. Catches `doesn't contradict` passing as `supports`, silent qualifier-stripping, and one-chunk-dispositive errors.

### Plugin install

```
/plugin marketplace add <path-or-github-repo>
/plugin install local-library@local-library
```

`<path-or-github-repo>` is a local filesystem path (for development) or a github org/repo. The plugin's `.mcp.json` brings the MCP server with it (no separate registration needed); the six skills auto-discover via Claude Code's plugin loader.

### Where the plugin's pieces live

- `.claude-plugin/plugin.json` — plugin manifest (name, version, keywords)
- `.claude-plugin/marketplace.json` — self-advertising marketplace entry (note: `source: "./"` is required; the bare `"."` form fails marketplace schema validation)
- `.mcp.json` at the repo root — MCP server config (uses `${CLAUDE_PLUGIN_ROOT}`)
- `skills/<skill-name>/SKILL.md` — six SKILL.md files (one per skill above) + `grounding-against-library/references/tool-selection.md`
- `tests/skills/` — RED baselines (Phase 1), GREEN/Tier-3 verifications (Phases 2-4), install-and-permissions audit (Phase 5), smoke transcripts + DoD audit (Phase 6)
- `README.md` § "Claude Code Plugin" — user-facing install/architecture/test-drive docs
- `docs/design-plans/2026-04-24-local-library-claude-code-plugin.md` — design document
- `docs/implementation-plans/2026-04-24-local-library-claude-code-plugin/` — six-phase implementation plan

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

- `src/local_library/mcp/CLAUDE.md` — implementation contracts and conventions
- `docs/design-plans/2026-04-15-mcp-server.md` — original design
- `docs/implementation-plans/2026-04-15-mcp-server/` — phased implementation plan
- MCP Python SDK: `mcp` package v1.27.0+ on PyPI
- FastMCP framework: `mcp.server.fastmcp` module (decorator-based tool definitions)
- Claude Code MCP docs: https://code.claude.com/docs/en/mcp
- MCP specification: https://modelcontextprotocol.io/docs/learn/architecture
- `docs/feature-areas/neovim-citation-workflow/README.md` — daemon design decisions (shared infrastructure)
