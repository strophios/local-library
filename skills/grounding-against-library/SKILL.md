---
name: grounding-against-library
description: Use when grounding exactly ONE target assertion against library evidence — retrieves via MCP tools, widens context as needed, synthesizes across all retrieved evidence with per-source tagging (support/contradict/partial/not-found), and reports with per-source citations and quoted evidence. Also use for verification prompts like "verify the claim that...", "is it true that @<citekey> claims X", "check whether @<citekey> says Y", "ground this assertion...". Callers must decompose broad requests into atomic assertions and invoke this skill per-assertion; the kernel returns control if the target is too broad.
allowed-tools:
  - mcp__local-library__search_library
  - mcp__local-library__show_document
  - mcp__local-library__list_documents
  - mcp__local-library__get_document_text
  - Read
---

# Grounding against library

## Scope guardrail — READ FIRST

This skill grounds ONE target assertion. Your caller — a composing skill or user instruction — is responsible for decomposition.

If the input is broad ("explain how X handles Y", "summarize what the literature says about Z", "compare A and B across these dimensions"), STOP and return control to the caller with:

> This request covers multiple assertions. Please decompose into atomic claims and invoke this skill once per claim.
>
> Example decomposition for "[original request]":
> 1. Does @<citekey> claim that [specific assertion A]?
> 2. Is @<other-citekey> theory of [specific assertion B] consistent with [specific assertion C]?
> 3. [Additional atomic assertions as needed]

Do NOT attempt a partial answer. Do NOT fold multiple claims into one grounding pass.

## Core principle

Grounding produces per-source evidence and an aggregate judgment. A single chunk that "looks relevant" is not grounding; it is a hint. Quote before you paraphrase. Not-found is a valid result.

## Iron law

- **Quote before you paraphrase.** If you cannot quote the supporting text, you have not grounded the claim.
- **Not-found is a valid result.** Reporting "no evidence for this claim in the corpus" is better than confabulating support.

## Six-step procedure

### Step 1 — Confirm one scope

Verify the input is ONE assertion. If it is composite, return control per the scope guardrail.

### Step 2 — Formulate query or queries

A single assertion may need multiple facet queries. Plan them before calling tools. Example for "Vaswani2017 claims multi-head attention reduces compute compared to single-head":
- `search_library(query="multi-head attention computational cost", doc_id="@Vaswani2017", limit=10)`
- `search_library(query="single-head attention complexity", doc_id="@Vaswani2017", limit=10)`

If the assertion is unscoped (not about a named document), issue corpus-wide queries (omit `doc_id`).

### Step 3 — Retrieve

Call the planned queries. Multiple documents surfacing is a feature, not a problem to collapse. Capture the document citekey and chunk indices for each result.

### Step 4 — Widen context

If a chunk appears truncated at a boundary that matters for the claim, call `get_document_text(doc_id="@Name2023", start_chunk=N, end_chunk=M)`. Indices are 0-based inclusive. Reuse the chunk indices from search results. Skip this step if all chunks are self-contained.

### Step 5 — Synthesize

Per-source tagging for each document that surfaced:
- **support**: Quoted evidence that directly affirms the claim.
- **contradict**: Evidence that directly contradicts the claim.
- **partial**: Evidence that is relevant but does not fully resolve the claim (qualified, tangential, context-dependent).
- **not-found**: Deliberate search scoping (e.g., doc_id="@SpecificAuthor") returned no results after Step 3 and Step 4.

Then aggregate: Does the evidence across all sources support, contradict, partially support, or remain silent on the claim?

### Step 6 — Report

Produce a table with per-source rows:
- Citekey (formatted as @Author_Year)
- Quoted excerpt (verbatim from retrieved text)
- Chunk index (as labeled in search results or from get_document_text call)
- Status (support / contradict / partial / not-found)

Then aggregate conclusion: one sentence summarizing the combined evidence.

## Rationalization table

| Excuse | Reality |
|--------|---------|
| "Top chunk matched the keyword; I don't need to read more" | Keyword match ≠ semantic support. Quote the support or mark partial. |
| "One strong hit is dispositive" | Other documents may contradict or qualify. Continue searching. |
| "I can paraphrase from the chunk; quotation is pedantic" | Paraphrase drift is where false grounding enters. Quote first. |
| "The second document didn't surface, so it's not relevant" | If named in the claim (e.g., @Smith2023), retry with `doc_id="@Smith2023"` before concluding not-found. |
| "The claim is obviously true; I'll skip the quote" | If obvious, quoting is trivial. |
| "Not-found feels like failure — I'll try harder to extract support" | Not-found is a result. Forcing support is confabulation. |
| "I summarized both papers from their abstracts without retrieving chunks" | Abstracts are not full documents. Retrieve and quote from the corpus. |
| "The comparison is clear, so I'll synthesize into a table without per-source tags" | Comparison-table synthesis obscures which evidence supports which claim. Tag per-source first. |
| "I checked one chunk and it was relevant, so the document supports the claim" | One chunk is a signal. Continue searching for contradictions or qualifications. |
| "I referenced chunk indices parenthetically in the text" | Per-claim chunk attribution is required. Use the table format. |

## Red flags — stop

- About to produce an answer without a quoted excerpt
- About to collapse multiple documents' evidence into one summary without per-source breakdown
- About to tag `support` based on keyword overlap without semantic coherence
- About to skip Step 1 because input "sounds specific enough"
- About to report "the corpus shows..." without per-source status rows
- About to skip widening context when a chunk ends mid-sentence at a claim boundary
- About to report "not-found" for a named document without having called search_library with `doc_id="@Name"`

## See also

- `references/tool-selection.md` — scenario → tool matrix, mode selection, reranking inversion, chunk index semantics.
