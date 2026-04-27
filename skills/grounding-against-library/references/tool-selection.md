# Tool selection for grounding

This reference complements `SKILL.md`. It maps common grounding scenarios to MCP tool calls. For exhaustive parameter documentation, see `src/local_library/mcp/CLAUDE.md`.

## Identifiers

All four tools accept `doc_id: str` as `@citekey` (preferred, e.g., `@Smith2023`) or UUID (full or partial). Fuzzy match on misses produces a "Did you mean @...?" suggestion — use it. Always use @citekey when known because it is human-readable and stable across library resets.

## Scenario → tool matrix

| Scenario | Start with | Follow-up | Notes |
|---|---|---|---|
| Known citekey; metadata only | `show_document(doc_id="@C")` | — | Check `**Status:** needs_review` — if flagged, cross-invoke `handling-extraction-quality` kernel (Phase 4). |
| Known citekey; full text (short doc) | `get_document_text(doc_id="@C")` | — | Returns full text if total chunks < 50 (SHORT_DOC_THRESHOLD). |
| Known citekey; long doc (no range) | `get_document_text(doc_id="@C")` | — | Returns preview of first 20 chunks (PREVIEW_CHUNK_COUNT) + section outline + instructions for range requests. |
| Known citekey; long doc with range | `get_document_text(doc_id="@C", start_chunk=N, end_chunk=M)` | — | Indices are 0-based, inclusive. Returns the slice [N, M]. Reuse the indices labeled in search results. |
| Known citekey + topic | `search_library(query="...", doc_id="@C", limit=10)` | `get_document_text(doc_id="@C", start_chunk=N, end_chunk=M)` | Doc-scoped search via `doc_id` parameter. Returns ranked chunks within that document. |
| Topic across corpus | `search_library(query="...", limit=10)` | `show_document` for metadata; `get_document_text` for context. | `mode="hybrid"` + reranking on (defaults). Returns results from all documents. |
| Multi-facet assertion | Multiple `search_library` calls | Combine results in synthesis (Step 5 of procedure) | 2–4 queries per assertion is normal. Each query should target one aspect. |
| Citekey misspelled / unknown | `show_document(doc_id="@Guess")` | Use "Did you mean @...?" suggestion | Call the suggested citekey. Don't guess twice. |
| Narrow by metadata (year, author) | `list_documents(year=2023, author_contains="Smith", limit=20)` | `show_document` on the hit | Filters combine with AND semantics. `limit` is pagination only; no offset. |
| Retrieve all docs matching a filter | `list_documents(status="ready", citekey_prefix="Angrist", limit=100)` | As above | `status` one of "ready", "failed", "needs_review", "pending". `citekey_prefix` is case-insensitive prefix match. |

## Mode selection

`search_library` has three modes (default is `mode="hybrid"`):

- **`mode="hybrid"`** (default, recommended): RRF (Reciprocal Rank Fusion) of vector + FTS. Captures both semantic and keyword signals. Use unless you have a specific reason to use single mode.
- **`mode="vector"`**: Pure semantic similarity. Best for conceptual/topic queries. Slower for exact-string matches.
- **`mode="fts"`**: Pure keyword (BM25 via FTS5). Best for named entities, acronyms, exact phrases. Falls back when vector unavailable.

## Reranking inversion — CRITICAL FOOTGUN

The parameter `no_rerank: bool = False` is **inverted internally**.

- Default `no_rerank=False` means reranking is **ON** (enabled).
- Setting `no_rerank=True` **disables** reranking.

The internal code (`server.py:99`) does `rerank=not no_rerank`, so the parameter name is negation of the behavior. This is a footgun: passing `no_rerank=True` thinking you are enabling reranking will in fact disable it. Use `no_rerank=False` (the default) to keep reranking enabled. Only set `no_rerank=True` if you specifically want to disable reranking and understand the consequence (lower result quality).

## Chunk indices

`start_chunk` and `end_chunk` parameters in `get_document_text()` are:

- **0-based** (first chunk is chunk 0)
- **inclusive** on both ends

So `start_chunk=3, end_chunk=7` returns five chunks: [3, 4, 5, 6, 7].

When search results label chunks (e.g., "Chunk 42" in the search output), reuse those indices for `get_document_text` range calls.

## Short-doc vs long-doc behavior

- **< 50 chunks**: `get_document_text(doc_id="@C")` returns full text regardless of range parameters.
- **≥ 50 chunks, no range**: Returns preview (first 20 chunks) + markdown section outline + instructions for requesting specific ranges.
- **≥ 50 chunks, with range**: Returns the requested slice [start_chunk, end_chunk].

Always use ranges for long documents to avoid overwhelming context.

## What this reference is NOT

- **Not a parameter dictionary**: See `src/local_library/mcp/CLAUDE.md` for exhaustive tool contracts.
- **Not an argument for when to ground**: See `SKILL.md` for scope and iron law.
- **Not a troubleshooting guide**: If tools error (identifier miss, invalid ranges), the tool output includes suggestions.
