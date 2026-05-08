---
name: verifying-claims-against-library
description: >-
  Use when checking whether the local library supports given textual
  claims — claims with explicit citekeys, claims attributing
  positions to named authors, or claims about what a source "argues"
  / "shows" / "finds" / "concludes". Enumerates each
  citation-bearing claim, invokes the grounding-against-library
  kernel per claim, and reports a claim table with verbatim quoted
  support and a status (match / partial / mismatch / not-found).
  Multi-source. Catches "doesn't contradict" passing as "supports",
  silent qualifier-stripping, and one-chunk-dispositive errors.
  Also fires on phrasings like "verify these claims against my
  library", "fact-check this passage", "are these citations
  warranted", "does my library actually back these claims",
  "is @<citekey> really saying X", "check whether the cited sources
  support this".
allowed-tools:
  - mcp__local-library__search_library
  - mcp__local-library__show_document
  - mcp__local-library__list_documents
  - mcp__local-library__get_document_text
  - Read
---

# Verifying claims against library

## When to invoke

- A user pastes cited prose and asks "does my library support this?"
- An editor pass on a draft asking which citations are warranted
- A fact-check pass on someone else's text against the local corpus
- Reviewing a literature-review section before submission
- Auditing a `[citation]`-marked footnote sweep
- Validating a quote attributed to `@<citekey>` that smells off

## Iron law

- **Quote the support.** A `match` without a verbatim quoted excerpt in the table is rubber-stamping. If you cannot quote, the right tag is `partial` or `not-found`.
- **Caveats in the quote that aren't in the claim = `partial`, not `match`.** "X causes Y in low-income countries" ≠ "X causes Y". A claim that drops a qualifier the source contains is partially supported, not fully supported.
- **"Doesn't contradict" is not "supports".** If the source is silent on the specific claim, the right tag is `not-found`. Silence is not endorsement.

## Procedure

### Step 1 — Enumerate citation-bearing claims

Read the input prose. Each claim that carries a citation (or *should* carry one) becomes one row. A claim that combines two assertions ("X causes Y, and Y causes Z, per @Smith2020") is **two** claims — one row each.

Claims to enumerate:
- Explicit citation: `"...as @Smith2020 argues..."`
- Attributed positions: `"@Smith2020 finds that..."`, `"according to @Smith2020..."`
- Verb-of-attribution claims: `"argues"`, `"shows"`, `"finds"`, `"concludes"`, `"demonstrates"`, `"rejects"`, `"establishes"`
- Implicit attributions: a paragraph clearly drawn from one source, even if the citation is at paragraph end

### Step 2 — Per-claim grounding

For each enumerated claim, invoke the `grounding-against-library` kernel. The assertion passed to the kernel is the verbatim claim with its attributed citekey(s).

Watch for these distinctions when synthesizing:

- **Negation**: "X does not cause Y" requires the quoted excerpt to **explicitly negate**, not merely omit. Source silence on X-causing-Y does not support "X does not cause Y" — that is `not-found`, not `match`.
- **Qualifiers**: "X usually causes Y" / "X causes Y under condition C" — the quote must include the qualifier. If the source's quote contains the qualifier but the claim drops it, status is `partial` (gap toward over-claim).
- **Attribution voice**: `"argues"` is stronger than `"mentions"`; `"rejects"` is opposite of `"endorses"`. Match the verb in the claim to the stance in the quote. A claim that says "Smith argues X" but Smith only "mentions X in passing" is `partial` at best.

### Step 3 — Build the claim table

Aggregate per-claim grounding results into a table:

```
| # | Claim (verbatim) | Cited source | Quoted support | Status | Notes |
|---|------------------|--------------|----------------|--------|-------|
| 1 | "X causes Y in low-income countries" | @Smith2020 | "...we find X causes Y in low-income economies, with no detectable effect in high-income countries..." | match | quote contains the qualifier; claim preserves it |
| 2 | "X causes Y" (qualifier dropped from claim 1's source) | @Smith2020 | "...we find X causes Y in low-income economies, with no detectable effect in high-income countries..." | partial | claim drops the "in low-income countries" qualifier the source explicitly attaches |
| 3 | "Z is invariant under transformation T" | @Jones2021 | <none> | not-found | searched §2-§5 with `doc_id="@Jones2021"`; no claim about T-invariance found |
| 4 | "Both papers agree on policy implications" | @Smith2020, @Jones2021 | <quoted excerpts from both, on the policy implications they each draw> | mismatch | Smith favors policy A on chunk 18; Jones favors policy B on chunk 24; the claim of agreement is contradicted by both sources |
```

**Status values** (use exactly these strings):
- `match` — quoted excerpt directly affirms the claim, including any qualifiers in the claim
- `partial` — source contains relevant evidence but the claim drops a qualifier, overstates the verb of attribution, or aggregates beyond what the source supports
- `mismatch` — source explicitly contradicts the claim (provide the contradicting quote)
- `not-found` — searched the named source(s) thoroughly (with `doc_id="@<citekey>"` retries) and no relevant evidence surfaced; silence ≠ support

For multi-source claims (one row, two cited sources), each source's status is reported in Notes. The row's overall status is the worst of the per-source statuses, unless the overall claim is *only* warranted by both sources jointly (in which case partial-on-either downgrades the row).

## Output format

- **Claim table**: rows = citation-bearing claims; columns = (#, Claim verbatim, Cited source, Quoted support, Status, Notes)
- **Summary line at end**: "Of N claims: <m> match, <p> partial, <x> mismatch, <nf> not-found." This forces a count-the-matches discipline at the end.

If `handling-extraction-quality` was invoked for any row (e.g., a claim about an equation in a source whose math markdown is garbled), the Notes field for that row should explicitly state "from PDF page N" rather than chunk index.

## Failure-mode table

| Excuse | Reality |
|--------|---------|
| "Cited source mentions the topic, that's good enough to call it a match" | Topical overlap is not support. The chunk must support the *specific* claim verbatim, with its qualifiers and verb of attribution. |
| "Couldn't find the support on the first search; close enough — match" | Premature closure. The kernel does multi-facet retrieval; let it. Don't downgrade your own discipline. |
| "The qualifier is implicit; no need to flag the claim as partial" | Implicit qualifiers are how false claims travel. If the source has it and the claim drops it, status is `partial`. |
| "The source doesn't contradict the claim, so it counts as a match" | Silence is `not-found`. "Doesn't contradict" is the floor for support, not support itself. |
| "Two sources cited together; one supports, so the row is match" | Per-source status is required for multi-source claims. The row's overall status reflects the weakest link, not the strongest. |
| "I'll mark `match` if the quote loosely paraphrases the claim's idea" | `match` requires a quote that *contains* the claim's content. Loose paraphrase = `partial`. |
| "The summary line is bookkeeping — I'll skip it" | The summary line is the at-a-glance signal of how cited the prose really is. Without it, the table loses its audit value. |
| "Verb-of-attribution differences (`argues` vs `mentions`) are stylistic, not substantive" | They aren't. `argues` claims a defended position; `mentions` claims a passing reference. A `match` requires the verb in the claim to align with the stance in the quote. |

## Red flags — stop

- About to mark `match` without a verbatim quote in the table's Quoted support column
- About to ignore a qualifier ("usually", "in some cases", "for X populations") that the source contains but the claim drops
- About to merge two distinct claims into one row because they cite the same source
- About to tag `not-found` after one search query (the kernel does multi-facet; let it)
- About to treat "the source discusses the topic" as evidence supporting "the source argues the claim"
- About to omit the summary line at the end of the table
- About to mark `match` on a multi-source row when one of the cited sources is `not-found`
