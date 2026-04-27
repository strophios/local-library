---
name: drafting-with-grounded-sources
description: >-
  Use when writing or editing text (drafts, essays, research notes,
  explanations) that should be grounded in specific source documents
  from the local library — covers decomposition into grounded
  propositions, per-claim invocation of the grounding-against-library
  kernel, and structured output with prose + audit-trail appendix.
  Recommends section-by-section invocation on large drafts. Also
  fires on phrasings like "draft with citations", "expand this with
  sources", "explain/summarize @<citekey> for an essay", "write a
  paragraph drawing from these papers", "synthesize sources into a
  section".
allowed-tools:
  - mcp__local-library__search_library
  - mcp__local-library__show_document
  - mcp__local-library__list_documents
  - mcp__local-library__get_document_text
  - Read
---

# Drafting with grounded sources

## When to invoke

- Writing a 2-paragraph response about a paper's argument and its implications
- Building a research note that synthesizes claims from 3 or more sources
- Editorial pass on a draft section with flagged unsourced claims
- Expanding a thesis statement with paragraph-level evidence from the library
- Explaining a methodology or finding attributed to a specific paper
- Creating a literature summary that engages each source's specific positions, not generic background

## Iron law

- **Quote into scratch before paraphrasing.** Cannot quote = not grounded = not citable.
- **One proposition, one grounding pass.** "A and B" needs A grounded and B grounded separately.

## Procedure

### Step 1 — Decompose before writing

List propositions before producing prose. Example: "Vaswani et al. 2017 introduced the Transformer architecture, which replaced recurrence with attention and reduced sequential compute" decomposes to:

1. @Vaswani2017 introduced the Transformer architecture.
2. @Vaswani2017's Transformer replaced recurrence with attention.
3. @Vaswani2017 claims this reduces sequential compute.

Each bullet becomes one row in the grounding-summary appendix.

### Step 2 — Ground each proposition

Per proposition: invoke `grounding-against-library` (six-step procedure). Capture per-source quoted evidence into a scratch buffer.

If the kernel returns not-found for a proposition: drop it OR rewrite to match what the corpus supports. Do not paraphrase past not-found.

### Step 3 — Write the prose

Draft from the scratch buffer. Inline `@citekeys` at every claim. Paraphrase from quoted excerpts, never from memory.

### Step 4 — Build the grounding-summary appendix

At the end of the draft:

```
## Grounding summary

- Proposition 1: <verbatim>
  - Source: @Citekey1 (Chunk N)
  - Quote: "..."
  - Status: support

- Proposition 2: <verbatim>
  - Source: @Citekey2 (Chunk M)
  - Quote: "..."
  - Status: partial — caveat noted in prose
```

The appendix scales with draft size. For long drafts, invoke section-by-section to keep the appendix manageable.

## Output format

- Draft prose with inline `@citekeys` at every claim
- Grounding-summary appendix at end (one entry per proposition, with source citekey, chunk index, quoted excerpt, status)

## Failure-mode table

| Excuse | Reality |
|--------|---------|
| "I'll cite this from memory; the paper definitely says it" | Memory is where false grounding enters. Quote first; cite from quote. |
| "Top result was thematically related; that's enough to cite" | Citation-shopping. The chunk must support the *specific* claim. |
| "`mentions` / `discusses` / `argues` mean the same thing" | They don't. Match the verb to the quote. |
| "I'll add the citekey at the end and figure out the chunk later" | Citations decay. Capture the chunk index when you capture the quote. |
| "This proposition's a connector — it doesn't need grounding" | Connectors quietly assert relationships. Ground them or mark as synthesis. |

## Red flags — stop

- About to add inline citekey without a corresponding grounding-summary entry
- About to skip decomposition because the section "is short"
- About to keep a not-found proposition by fudging the wording
- About to consolidate two propositions into one citation
- About to draft prose before the scratch buffer is populated
