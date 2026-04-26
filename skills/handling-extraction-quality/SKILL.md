---
name: handling-extraction-quality
description: >-
  Use when the user asks about an equation, formula, derivation, loss
  function, algorithm, figure, table, or other visually-formatted
  technical content from a library document — Marker's PDF extraction
  generally produces correct LaTeX for math, but it can degrade with
  subscript/superscript collapse (`QWQ i` instead of `QW^Q_i`),
  escape-sequence remnants like `\n(1)` at equation tails, empty math
  delimiters, empty `<!-- image -->` markers, broken markdown tables,
  or `show_document` reporting `**Status:** needs_review`. Default
  flow: retrieve the markdown, inspect for those genuine garbling
  cues; if cues fire, escalate to the PDF via `Read` at the path from
  `show_document`. Provenance is mandatory either way: cite chunk
  index for markdown-sourced content, page number for PDF-sourced
  content. Do not ask the user to retype.
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

**Important caveat: well-formed LaTeX in extracted markdown is the success case, not garbling.** Marker is designed to emit LaTeX for math content. Go to the PDF in response to *malformed*, *garbled*, or *erroring* LaTeX (the cues below); well-formed LaTeX (`$$E = mc^2$$`, `$\frac{a}{b}$`, `\sum_{i=1}^n` inside math delimiters, properly-typeset matrices) is trustworthy and is the source.

## Iron law — provenance disclosure is mandatory

Every answer about an equation, formula, derivation, figure, or table must say where its content came from:

- **From extracted markdown**: cite the chunk index (e.g., "from chunk 14 of the markdown"). The user can verify with `get_document_text @<citekey>` ranged on that chunk.
- **From the PDF**: cite the page number (e.g., "page 4 of the PDF"). The user can open the PDF themselves at that page.

Without provenance, a clean-looking answer is indistinguishable from confabulation. The user must be able to audit you.

A second, related rule: **do not ask the user to retype the equation or describe the figure when the PDF is on disk.** If markdown is degraded, you read the PDF.

## Recognition cues — markdown is genuinely garbled when you see

These are the patterns that distinguish degraded extraction from successful LaTeX output. They are *not* LaTeX presence — they are LaTeX (or table, or figure) malformation.

- **Subscript / superscript collapse**: capital letters and digits running together with no `^` or `_` structure — patterns like `QWQ i`, `KW K i`, `V WV i`, `R dmodel×dk`. The originals were `QW^Q_i`, `KW^K_i`, `VW^V_i`, `\mathbb{R}^{d_{\text{model}} \times d_k}`.
- **Escape-sequence remnants**: literal `\n` followed by equation numbers like `\n(1)`, `\n(3)` at equation tails. The `\n` was supposed to be a real newline; it's a literal two-character string instead.
- **Empty math delimiters**: `$$` followed only by whitespace, or `$...$` with no content inside. Marker emitted delimiters but extracted no content.
- **Empty image markers**: `<!-- image -->` with no description. Marker noted an image existed but couldn't extract it. If the user is asking about a figure, this is content loss.
- **Broken markdown tables**: rows with uneven `|` counts, cells visibly running together, headers misaligned with body rows.
- **`**Status:** needs_review`** in `show_document` output (low-confidence extraction or pdftext fallback — treat content as unreliable regardless of further inspection).

What is NOT a garbling cue, despite their LaTeX-looking appearance: well-formed `$$...$$` blocks, `$...$` inline math, properly-rendered LaTeX commands like `\sum`, `\int`, `\frac{a}{b}`, `\mathbb{R}` inside math delimiters. These are Marker's intended output for math content. Treat them as the source.

## Procedure for math / figure / table prompts

Trigger: the user asks about an equation, formula, derivation, loss function, algorithm, figure, table, or other visually-formatted content from a library document.

1. `show_document @<citekey>`. Note the `**Status:**` field and capture the `**Original path:**` field — that's the literal filesystem path to the PDF, kept in scratch for possible escalation.
2. **If `**Status:** needs_review`**: skip directly to step 5 (PDF escalation). The system is telling you the extraction is unreliable.
3. Otherwise, `get_document_text @<citekey>` (chunk-ranged when you can guess the relevant section; full-doc for short docs).
4. **Inspect the retrieved markdown for the genuine garbling cues above.** If any cue fires in the section relevant to the user's question, escalate to step 5. If the markdown is clean (LaTeX well-formed, tables intact, no escape-sequence remnants), the markdown is the source — proceed to step 6 with chunk-index provenance.
5. **PDF escalation**: `Read(file_path="<original-path>", pages="<range>")`. Start narrow (e.g., `pages: "1-3"` to orient, then widen). The PDF is now the source — proceed to step 6 with page-number provenance.
6. **Cite provenance** in your answer. Markdown source: chunk index. PDF source: page number. Either way, the user must be able to find what you cited.

## Rationalization table

| Excuse | Reality |
|--------|---------|
| "I see `$$...$$` or `\sum` in the markdown — that's garbled, escalate to PDF" | Wrong: well-formed `$$...$$` and `\sum` inside math delimiters are Marker's *success* format. Correct LaTeX is the source. Only escalate when the LaTeX is *malformed* (subscript collapse, escape-sequence remnants, empty delimiters). |
| "The markdown looks fine, I'll just use it and not bother saying so" | Provenance is mandatory. Cite the chunk index — it's a 5-token addition that lets the user audit. |
| "I'll silently clean up the garbled subscripts; the user won't notice" | They'll notice when they cross-check and it doesn't match. Either escalate to PDF, or quote the garbled markdown verbatim and flag it. |
| "The user can probably tell me what the equation is" | They shouldn't have to. The PDF is on disk. Read it. |
| "Marker is usually accurate, I'll trust it this time without checking the cues" | The recognition cues are cheap to check. Check before trusting. |
| "I can reconstruct the equation from the garbled chunks + training knowledge" | Reconstruction without disclosure is a lie of omission. The user will see clean LaTeX and assume it came from the document. |
| "The PDF is long; reading will consume context" | Use `pages:` to scope. Read Section 3 only, not the whole document. |
| "Citing chunk index or page number is fussy" | The fussiness is the point — it makes your answer auditable. The grounding-against-library kernel relies on this. |

## Red flags — stop

- About to present an equation, figure description, or table content without saying whether it came from markdown chunk N or PDF page N
- About to escalate to PDF Read just because you saw `$$...$$` or `\sum` (those are success markers, not failures — only malformed LaTeX is the trigger)
- About to type "could you tell me the equation" or "could you clarify the table" to the user
- About to paraphrase an equation or table you cannot clearly see in the markdown
- `show_document` reported `**Status:** needs_review` and you're proceeding without escalating to PDF
- About to silently render garbled extraction (`\n(1)`, `QWQ i`, broken `<!-- image -->`) into clean canonical output without flagging the source as degraded or escalating to PDF
