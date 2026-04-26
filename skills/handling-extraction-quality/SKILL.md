---
name: handling-extraction-quality
description: Use when the user asks about an equation, formula, derivation, loss function, algorithm, figure, table, or other visually-formatted technical content from a library document — Marker's PDF extraction reliably degrades on math and visual content, so reach for the original PDF via `Read` rather than trusting the extracted markdown for those content types. Also use reactively when extracted markdown shows garbled math (raw `$$...$$`, unprocessed `\sum`/`\int`/`\frac`, empty `$...$`), empty `<!-- image -->` comments, broken markdown tables, single-character subscript collapse like `QWQ i`, or `show_document` reports `**Status:** needs_review`. Procedure: extract `**Original path:**` from `show_document`, then `Read` the PDF with `pages:` to scope.
allowed-tools:
  - mcp__local-library__search_library
  - mcp__local-library__show_document
  - mcp__local-library__list_documents
  - mcp__local-library__get_document_text
  - Read
---

# Handling extraction quality

## Core principle

Extracted markdown is an artifact of the Marker extraction pipeline. The PDF is the source of truth. When the artifact is degraded for what the user is asking about, read the PDF directly instead of projecting clean LaTeX from training or asking the user to provide it again.

## Recognition cues — markdown is garbled when you see

- Raw `$$...$$` blocks rendered as LaTeX source (Marker fallback didn't process it)
- Unprocessed math commands: `\sum`, `\int`, `\alpha`, `\frac{...}{...}` scattered in prose
- Empty math delimiters: `$$` followed by whitespace only, or `$...$` with no content
- Empty image comments: `<!-- image -->` with no description
- Broken markdown tables: missing pipes, uneven cell counts, misaligned columns
- Single-character subscript patterns: `QWQ i`, `KW K i`, `V WV i` (subscript collapse where original is `QW^Q_i`)
- **Status: needs_review** in `show_document` output (pdftext fallback was used — extraction is unreliable)

## Pre-emptive consultation — read the PDF FIRST when the user asks about

- **Equations / formulas**: "What's the main equation", "explain the loss function", "what's the derivation of...", "write out the formula"
- **Algorithms**: "how does the algorithm work", "walk me through the procedure", "explain the training loop"
- **Figures**: "explain Figure N", "what does the diagram show", "describe the architecture diagram"
- **Tables**: "what's in Table N", "compare the results table", "what are the hyperparameters"
- **Math notation**: any prompt mentioning specific dimensions, subscripts, or symbolic notation (`d_k`, `Q`, `K`, `V`, etc.)

For these prompts, do NOT first try `get_document_text` and then react to garbling. Go straight to `show_document` → `Read` on the PDF with a narrow `pages:` range covering the relevant section. Marker's extraction reliably degrades on math and visual content; the markdown is not the source of truth for those content types — the PDF is. This applies even when `show_document` reports `**Status:** ready` (status reflects extraction completion, not extraction fidelity for math).

## Iron law — read the PDF; do not ask the user

This is non-negotiable. The agent must NOT ask the user to retype the equation, describe the figure, or clarify the table when the PDF is on disk. The user already has the document open. Reading the PDF directly is a 2-minute task. Asking them to retype is a 5-minute interruption to their flow. Do the reading.

## Procedure

1. Call `show_document @<citekey>` to retrieve metadata.
2. Extract the value of the `**Original path:**` field — this is the literal filesystem path to the PDF.
3. Call `Read(file_path="<path>", pages="<range>")`. Start narrow (e.g., `pages: "1-3"`) to orient yourself to the document structure; widen the range as needed.
4. Read math, figures, and tables directly from the PDF's rendered content.
5. Cite the PDF page number in your response so the user can verify: "On page 3 of the PDF, the equation is..."

## Rationalization table

| Excuse | Reality |
|--------|---------|
| "The user can probably tell me what the equation is" | They shouldn't have to. The PDF is on disk. Read it. |
| "The markdown is garbled but I can summarize what's readable" | A summary that omits the math is a wrong answer in polite wrapper. |
| "I'll just flag the garbling and ask them to clarify" | Flagging is appropriate only if the PDF is also unreadable. Try first. |
| "Marker is usually accurate, I'll trust it this time" | You already spotted the garbling cues. That's the trigger. Don't override your observation. |
| "The PDF is long; reading will consume context" | Use `pages:` to scope. Read Section 3 only, not the entire document. |
| "I can reconstruct the equation from the garbled chunks + training knowledge" | Reconstruction is worse than retrieval. The user will see clean LaTeX and assume it came from the document, when it came from your training. That's a lie by omission. |

## Red flags — stop

- About to type "could you tell me the equation" or "could you clarify the table" to the user
- About to paraphrase an equation or table you cannot clearly see in the markdown
- About to say "the extracted markdown is unclear on this point" without checking the PDF first
- `show_document` reported `**Status:** needs_review` and you're proceeding as if extraction is reliable
- About to present clean canonical LaTeX/figures without acknowledging that the source text was degraded or noting the page number from the PDF
