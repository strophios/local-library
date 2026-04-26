---
name: using-local-library-mcp
description: Use when citekeys (`@Name2023`, bare `Name2023`), paper/book/chapter references, phrasing like "what does X argue", "from my library", "cite this", or any request that could plausibly be grounded in the user's local research corpus — reaches for `mcp__local-library__*` tools before answering from training, and treats `@citekey` as a library handle rather than a topic label.
allowed-tools:
  - mcp__local-library__search_library
  - mcp__local-library__show_document
  - mcp__local-library__list_documents
  - mcp__local-library__get_document_text
  - Read
---

# Using local-library MCP

## Core principle

When a citekey or library-adjacent cue appears, the local library is the authoritative source. Reach for MCP tools before answering from training — the specific document in the user's corpus supersedes general knowledge of the author or work.

## Triggers — reach for library tools when you see

- **Explicit citekeys**: `@Name2023`, `Name2023`, `Name et al. 2023`
- **Argument questions**: "What does X argue / say / claim about ...", "What is X's position on ..."
- **Library references**: "In my library", "from my notes", "my corpus", "this document"
- **Citation requests**: "Cite this", "ground this", "source for this", "evidence from"
- **Named works**: Any paper, book, chapter, or author name when plausible as a library item (distinguishing ambiguous names from general topics)

## Tool disambiguation

| Intent | Tool |
|--------|------|
| Get metadata for a known citekey | `show_document @Name2023` |
| Search by topic across the corpus | `search_library "topic phrase"` |
| Browse or filter the corpus | `list_documents` (supports `--status`, `--year`, `--author-contains`, etc.) |
| Read a document's extracted text | `get_document_text @Name2023` (note: >50 chunks triggers preview mode; follow up with range calls) |

## Procedure — unmarked citekey in conversation

1. User mentions `@Name2023` (or unmarked but plausible citekey).
2. Call `show_document @Name2023` first.
3. If response starts with `Error: No document found matching...`, use the `Did you mean @...?` suggestion.
4. If response starts with `⚠ USER-FACING ERROR:`, surface the infrastructure problem — do not silently fall back to training.
5. For engagement with the argument, pull evidence via `get_document_text @Name2023` or targeted `search_library` calls before writing.

## Reading the tool output

- **`search_library`**: Starts with `### Results (N chunks from M documents)`; each result shows `@citekey | score: X | *Title*`, `Section:`, and `Chunk index` labels for follow-up.
- **`show_document`**: Markdown fields: `**Title:**`, `**Authors:**`, `**Date:**`, `**Status:**`, `**Embedding status:**`, `**Chunks:**`, `**Original path:**` (filesystem path for PDF fallback).
- **`get_document_text`**: Short doc (≤50 chunks) = full text in code block; long doc without range = preview + `### Sections` outline; long doc with range = `Chunks S–E of N` label.

## Rationalization table — excuses to reject

| Excuse | Reality |
|--------|---------|
| "I know this author from training; I can just summarize" | The library has their *specific document*. One `show_document` call is cheaper than being wrong about what *this* version says. |
| "The citekey is just a label; the real question is topical" | If the user wrote a citekey, they mean *that* document, not a general topic. |
| "`search_library` returned nothing, so the library doesn't have it" | Try `show_document @<citekey>` directly. Search can miss via embedding or exact-match issues; metadata lookup is authoritative. |
| "Listing all documents would be tedious" | `list_documents` supports filters (year, author, title, citekey prefix). Use them. |
| "I see the citekey but I recognize the work — I'll answer from memory" | Training knowledge is a guess. The document is on disk and one call away. Answer from the disk. |
| "The user probably knows their own paper — I don't need to verify" | Do verify. The user asked you to engage with their corpus, not with your assumptions about it. |

## Red flags — stop

- Writing engagement with `@Name2023` without invoking a library tool
- Paraphrasing what the author "argues" without quoted evidence from `get_document_text`
- Asserting specific numerics (BLEU scores, dataset sizes, year counts, etc.) without confirming them in the source
- Treating `Error: No document found...` as a reason to proceed from training instead of offering the fuzzy-match suggestion
- Treating `⚠ USER-FACING ERROR:` as a signal to silently fall back to memory
