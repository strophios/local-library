---
name: implementation-check-against-papers
description: >-
  Use when comparing code or implementation against method
  descriptions in one or more source papers — covers decomposition
  of code into checkable claims (algorithm shape, hyperparameters,
  loss/objective terms, normalization, initialization, edge cases),
  per-claim grounding via the grounding-against-library kernel,
  math-verification fallback to the PDF via the
  handling-extraction-quality skill, and an assertion-table output
  mapping each code claim to its paper locus and a status
  (match / mismatch / partial / not-found). Multi-source. Also
  fires on phrasings like "compare this code/file against
  @<citekey>", "does this implementation match the paper", "audit
  my implementation of <method>", "verify that this code follows
  @<citekey>", "check whether the hyperparameters match", "does
  this loss function match what's in @<citekey>".
allowed-tools:
  - mcp__local-library__search_library
  - mcp__local-library__show_document
  - mcp__local-library__list_documents
  - mcp__local-library__get_document_text
  - Read
---

# Implementation check against papers

## When to invoke

- Reviewing code that claims to implement a method described in a paper
- Verifying that a refactor preserved fidelity to the original method
- Auditing a `# follows X et al. (YEAR)` comment in code
- Comparing a model's hyperparameter set against the paper's stated values
- Checking whether the implementation's algorithm shape matches the paper's pseudocode
- Investigating a suspected divergence between code and paper before filing a bug

## Iron law

- **One claim per row. No consolidation.** "Algorithm matches" is not a claim. Decompose into specific, individually-checkable assertions.
- **Notational differences are verified, not assumed.** When the code uses different variable names than the paper, confirm the substitution; do not assume "just rewriting." Subscripts and signs flip more often than expected.
- **Math against PDF, not markdown.** For equations or symbol-level details, invoke `handling-extraction-quality` to read the PDF directly. Marker's extracted markdown is unreliable for tightly-spaced subscripts, summation indices, and mathematical operators.

## Procedure

### Step 1 — Decompose the code into checkable claims

Read the target code. List one claim per checkable assertion, organized by area:

- **Algorithm shape**: control flow, loop structure, ordering of operations
- **Hyperparameters**: specific numeric values (learning rate, dropout, batch size, num heads, etc.)
- **Loss / objective terms**: which components are summed, regularization, weighting
- **Normalization / activation**: where softmax / layer-norm / sigmoid / ReLU appear; scale factors like `1/√d_k`
- **Initialization / scheduling**: warmup steps, decay schedule, init distributions
- **Edge cases**: empty inputs, mask handling, padding semantics

Each bullet becomes one row in the assertion table. Resist the urge to consolidate — if two claims would have different statuses, they need separate rows.

### Step 2 — Ground each claim against the paper(s)

For each claim, invoke the `grounding-against-library` kernel with the assertion phrased as: "Paper @<citekey> specifies that <claim>." Capture per-source evidence with chunk indices.

For equation/symbol claims where the kernel's retrieved markdown shows garbling cues (subscript collapse, escape-sequence remnants, empty math delimiters — see `handling-extraction-quality` recognition cues), cross-invoke `handling-extraction-quality`: extract the `**Original path:**` from `show_document`, `Read` the PDF with a `pages:` range covering the relevant section, and quote the equation from the PDF with the page number as provenance.

### Step 3 — Build the assertion table

Aggregate the per-claim grounding results into a table. Required columns and example shape:

```
| # | Claim | Code locus | Paper locus | Status | Notes |
|---|-------|-----------|-------------|--------|-------|
| 1 | softmax over time dim before value projection | reranking.py:128 | @Vaswani2017 §3.2.1 (chunk 14) | match | quote: "we apply a softmax function to obtain the weights on the values" |
| 2 | learning rate warmup over 4000 steps | train.py:62 | @Vaswani2017 §5.3 (chunk 31) | mismatch | code uses warmup_steps=8000; paper says "warmup_steps = 4000" |
| 3 | mask out padded positions in attention | reranking.py:142 | @Vaswani2017 §3.2.3 (chunk 18) | partial | paper masks only future positions in decoder; code's mask scope is broader (all padding tokens in encoder too) |
| 4 | dropout layer after attention output | reranking.py:155 | searched §3, §5; no equivalent | not-found | searched chunks 12-22 and 30-35 with `doc_id="@Vaswani2017"`; no mention of post-attention dropout — paper's only dropout reference is to residual connections (§5.4) |
```

**Status values** (use exactly these strings):
- `match` — paper directly specifies the same thing the code does, with a verbatim quoted excerpt.
- `mismatch` — paper specifies a different value/structure than the code; quote the divergent specifications from both.
- `partial` — paper specifies something related but not identical (different scope, qualified, conditional); explain the gap in Notes.
- `not-found` — searched the paper (with `doc_id="@<citekey>"` retries on the named document) and the claim's analog is not present.

## Output format

- **Assertion table**: rows = checkable claims; columns = (#, Claim, Code locus, Paper locus, Status, Notes)
- **Paper locus** = `@<citekey> §<section> (chunk <N>)` for prose-level claims; `@<citekey> p.<page>` for math/figure-level claims read from the PDF
- **Notes** = quoted evidence (for `match`), divergent specifications (for `mismatch`), gap description (for `partial`), or search-scope description (for `not-found`)

If `handling-extraction-quality` was invoked for any row, the Notes field for that row should explicitly state "from PDF page N" rather than chunk index, and the quoted excerpt is from the PDF reading.

## Failure-mode table

| Excuse | Reality |
|--------|---------|
| "Loose correspondence is good enough at this granularity" | Loose correspondence hides bugs. One claim per row, even if the rows look similar. |
| "Math markdown is garbled but I can guess from the surrounding prose" | Cross-invoke `handling-extraction-quality`. Don't reconstruct from training — that's how false-`match` rows get written. |
| "Notational difference, surely just a rewrite" | Verify substitutions. The paper might use `Q, K, V` while the code uses `query, key, value` — fine. But subscripts (`W^Q_i` vs `W_Q_i`) and signs (`-` vs `+` in a residual) flip more often than expected. |
| "Couldn't find it in §3, must not be in the paper" | Don't tag `not-found` after searching one section. Use `search_library(query, doc_id="@<citekey>")` to retry across chunks; or fetch the section outline via `get_document_text` first to locate the right area. |
| "Multiple claims map to the same paper section; I'll merge the rows" | No. One claim per row. Two claims that share a paper locus can have different statuses (one `match`, one `partial`). |
| "I'll mark `match` if the code looks roughly aligned with the paper's intent" | `match` requires a quoted excerpt that supports the *specific* claim. Without the quote, the right tag is `partial`. |
| "The Notes column is optional — I'll leave it blank for `match` rows" | Notes is required for every row. For `match`, the quote is the audit trail. Without it, the row isn't independently verifiable. |

## Red flags — stop

- About to write `match` without a quoted excerpt in the Notes column
- About to read mathematical symbols off the Marker-extracted markdown without checking the PDF when you spotted garbling cues
- About to skip a code claim because "it's just an implementation detail" — implementation details are exactly where divergence hides
- About to consolidate two rows whose Status values would differ
- About to tag `not-found` without having searched the full paper (use the section outline from `get_document_text` to verify scope)
- About to invoke this skill on a single line of code without decomposing the surrounding code-locus into its component claims
