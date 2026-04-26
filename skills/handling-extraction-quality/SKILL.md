---
name: handling-extraction-quality
description: >-
  Use when the user asks about an equation, formula, derivation, loss
  function, algorithm, figure, table, or other visually-formatted
  technical content from a library document — Marker's PDF extraction
  often degrades on math and visual content. Default flow: retrieve
  the markdown, inspect for garbling cues (raw `$$...$$`, unprocessed
  `\sum`/`\int`/`\frac`, empty `$...$`, empty `<!-- image -->`, broken
  tables, single-character subscript collapse like `QWQ i`); if cues
  fire or `show_document` reports `**Status:** needs_review`, escalate
  to the PDF via `Read` at the path from `show_document`. Provenance
  is mandatory either way: cite chunk index for markdown-sourced
  content, page number for PDF-sourced content. Do not ask the user
  to retype.
allowed-tools:
  - mcp__local-library__search_library
  - mcp__local-library__show_document
  - mcp__local-library__list_documents
  - mcp__local-library__get_document_text
  - Read
---

# Handling extraction quality

## Core principle

Extracted markdown is the default source for library content; the PDF is the fallback when extraction has degraded. The decisive failure mode this skill guards against is NOT "didn't read the PDF" — it's silently passing training-derived clean LaTeX off as document content without disclosure. Provenance is the iron law; PDF escalation is the mechanism, not the goal.

## Iron law — provenance disclosure is mandatory

Every answer about an equation, formula, derivation, figure, or table must say where its content came from:

- **From extracted markdown**: cite the chunk index (e.g., "from chunk 14 of the markdown"). The user can verify with `get_document_text @<citekey>` ranged on that chunk.
- **From the PDF**: cite the page number (e.g., "page 4 of the PDF"). The user can open the PDF themselves at that page.

Without provenance, a clean-looking answer is indistinguishable from confabulation. The user must be able to audit you.

A second, related rule: **do not ask the user to retype the equation or describe the figure when the PDF is on disk.** If markdown is degraded, you read the PDF.

## Recognition cues — markdown is degraded when you see

- Raw `$$...$$` blocks rendered as LaTeX source (Marker LaTeX fallback didn't process it)
- Unprocessed math commands: `\sum`, `\int`, `\alpha`, `\frac{...}{...}` scattered in prose
- Empty math delimiters: `$$` followed by whitespace only, or `$...$` with no content
- Empty image comments: `<!-- image -->` with no description
- Broken markdown tables: missing pipes, uneven cell counts, misaligned columns
- Single-character subscript patterns: `QWQ i`, `KW K i`, `V WV i` (subscript collapse where the original is `QW^Q_i`)
- `**Status:** needs_review` in `show_document` output (low-confidence extraction or pdftext fallback — treat content as unreliable regardless of further inspection)

## Procedure for math / figure / table prompts

Trigger: the user asks about an equation, formula, derivation, loss function, algorithm, figure, table, or other visually-formatted content from a library document.

1. `show_document @<citekey>`. Note the `**Status:**` field and capture the `**Original path:**` field — that's the literal filesystem path to the PDF, kept in scratch for possible escalation.
2. **If `**Status:** needs_review`**: skip directly to step 5 (PDF escalation). The system is telling you the extraction is unreliable.
3. Otherwise, `get_document_text @<citekey>` (chunk-ranged when you can guess the relevant section; full-doc for short docs).
4. **Inspect the retrieved markdown for the recognition cues above.** If any cue fires in the section relevant to the user's question, escalate to step 5. If the markdown is clean for what you need, the markdown is the source — proceed to step 6 with chunk-index provenance.
5. **PDF escalation**: `Read(file_path="<original-path>", pages="<range>")`. Start narrow (e.g., `pages: "1-3"` to orient, then widen). The PDF is now the source — proceed to step 6 with page-number provenance.
6. **Cite provenance** in your answer. Markdown source: chunk index. PDF source: page number. Either way, the user must be able to find what you cited.

## Rationalization table

| Excuse | Reality |
|--------|---------|
| "The markdown looks fine, I'll just use it and not bother saying so" | Provenance is mandatory. Cite the chunk index — it's a 5-token addition that lets the user audit. |
| "I'll silently clean up the garbled subscripts; the user won't notice" | They'll notice when they cross-check and it doesn't match. Either escalate to PDF, or quote the garbled markdown verbatim and flag it. |
| "The user can probably tell me what the equation is" | They shouldn't have to. The PDF is on disk. Read it. |
| "Marker is usually accurate, I'll trust it this time without checking" | The recognition cues are cheap to check. Check before trusting. |
| "I can reconstruct the equation from the garbled chunks + training knowledge" | Reconstruction without disclosure is a lie of omission. The user will see clean LaTeX and assume it came from the document. |
| "The PDF is long; reading will consume context" | Use `pages:` to scope. Read Section 3 only, not the whole document. |
| "Citing chunk index or page number is fussy" | The fussiness is the point — it makes your answer auditable. The grounding-against-library kernel relies on this. |

## Red flags — stop

- About to present an equation, figure description, or table content without saying whether it came from markdown chunk N or PDF page N
- About to type "could you tell me the equation" or "could you clarify the table" to the user
- About to paraphrase an equation or table you cannot clearly see in the markdown
- `show_document` reported `**Status:** needs_review` and you're proceeding without escalating to PDF
- About to silently render garbled extraction (`\n(1)`, `QWQ i`, broken `<!-- image -->`) into clean canonical output without flagging the source as degraded or escalating to PDF
- About to skip the markdown inspection step and jump straight to PDF Read for a math prompt — that's overcorrection; check the markdown first, escalate only if cues fire (or `Status: needs_review`)
