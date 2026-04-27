---
name: drafting-with-grounded-sources
description: >-
  Use when drafting prose that DEFENDS or DEVELOPS specific claims
  using cited evidence from the local library — claims the user has
  stated explicitly, or claims they want help articulating with
  grounded support. Covers decomposition into grounded propositions,
  per-claim invocation of the grounding-against-library kernel, and
  structured output with prose + auditable per-proposition appendix.
  NOT for topic exploration ("summarize what the literature says
  about X", "overview of approaches to Y", "tour what these papers
  cover") — use the using-local-library-mcp orientation skill for
  those, which produces well-quoted grounded prose without
  claim-decomposition. Fires on phrasings like "defend the claim
  that...", "develop the argument that...", "extend this thesis with
  evidence from...", "make the case that...", "write a paragraph
  supporting [proposition] using @<citekey>", "draft a section
  arguing [position] from @<citekey> and @<other>".
allowed-tools:
  - mcp__local-library__search_library
  - mcp__local-library__show_document
  - mcp__local-library__list_documents
  - mcp__local-library__get_document_text
  - Read
---

# Drafting with grounded sources

## When to invoke

- Defending a specific claim with paragraph-level evidence from the library
- Developing or extending a thesis statement with cited support from one or more sources
- Editorial pass on a draft section with flagged unsourced claims
- Engaging with a paper's argument by drawing out its specific commitments and supporting them with quotes
- Explaining a methodology or finding attributed to a specific paper, where the explanation is itself a defended claim
- Building a research note that synthesizes claims from 3 or more sources, where the user has supplied the claims to defend

### When NOT to invoke (use `using-local-library-mcp` instead)

- "Give an overview of approaches to X"
- "Summarize what the literature says about Y"
- "Tour what these sources contain on Z"
- "Explain [topic] drawing on @A and @B" (when no specific claim is named)
- General exploration where the user wants to *discover* what's in the corpus, not *defend* a position
- Literature summaries whose goal is breadth-of-coverage rather than support-for-an-argument

The orientation skill produces well-quoted multi-source prose with inline `@citekeys` and chunk references. It does this without requiring claim-decomposition — appropriate when the user has questions, not theses.

## Iron law

- **Quote into scratch before paraphrasing.** Cannot quote = not grounded = not citable.
- **One proposition, one grounding pass.** "A and B" needs A grounded and B grounded separately.

## Procedure

### Step 1 — Determine input shape and decompose

This SKILL drafts prose that **defends specific claims** with cited evidence. The audit-trail appendix earns its keep only when discrete claims anchor the prose. Three input shapes to handle differently:

**Shape A — claims supplied** (e.g., "defend the claim that X using @A and @B"; "develop the argument that Y, drawing on @A"; "extend this thesis: [thesis] with evidence from @A").

List the supplied propositions. Each becomes one row in the grounding-summary appendix. Proceed to Step 2.

Worked example: "Vaswani et al. 2017 introduced the Transformer architecture, which replaced recurrence with attention and reduced sequential compute" decomposes to:

1. @Vaswani2017 introduced the Transformer architecture.
2. @Vaswani2017's Transformer replaced recurrence with attention.
3. @Vaswani2017 claims this reduces sequential compute.

**Shape B — claims implicit, structure is argument-shaped** (e.g., "extend this argument with evidence from the library", "draft a section arguing [position] from these sources", "make the case for X using @A").

The prompt asks for argument-defense but doesn't fully specify the propositions. **Surface 2–4 inferred propositions for user review BEFORE invoking the kernel:**

> Your prompt asks me to argue for [implied position] drawing on @A and @B but doesn't fully specify the propositions. Based on the argument structure, I'd decompose into:
>
> 1. [inferred proposition 1]
> 2. [inferred proposition 2]
> 3. [inferred proposition 3]
>
> Confirm, refine, or replace before I ground them.

Wait for user response before proceeding. Inferred propositions reflect training-derived priors about the sources, not user intent — surfacing them keeps the user in the authorship loop.

**Shape C — topic exploration, no argument structure** (e.g., "give an overview of approaches to X", "summarize what these papers say about Y", "explain [topic] drawing on @A and @B" without a stated claim, "tour the literature on Z").

This SKILL is the wrong tool. Return control with:

> This prompt looks like exploration ("[the trigger phrase]") rather than argument-defense. drafting-with-grounded-sources is for the latter; its audit-trail appendix earns its keep only when prose defends discrete claims. Two paths:
>
> 1. If you have specific claims in mind, supply them (1–3 propositions) and I'll ground them via this SKILL.
> 2. If you want a tour of what these sources contain on the topic, the `using-local-library-mcp` orientation skill produces well-quoted multi-source prose without requiring claim-decomposition.
>
> Which do you want?

Wait for user response. Do not silently treat exploration as argument-defense — that produces a paragraph grounded against propositions you invented from training memory, with hidden authorship.

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
| "The user gave me a topic and citekeys, so I'll synthesize a paragraph from those sources" | If the prompt is exploration (overview / summary / tour) rather than argument-defense, this SKILL is the wrong tool. Redirect to `using-local-library-mcp`. The audit-trail appendix earns its keep only when prose defends discrete claims. |
| "The user gave me an argument-shaped prompt without claims; I'll just decompose into propositions I expect the papers to make" | Inferred propositions reflect training-derived priors about the sources, not user intent. Surface them for review before grounding so the user can confirm or refine. |

## Red flags — stop

- About to add inline citekey without a corresponding grounding-summary entry
- About to skip decomposition because the section "is short"
- About to keep a not-found proposition by fudging the wording
- About to consolidate two propositions into one citation
- About to draft prose before the scratch buffer is populated
- About to draft an "overview of [topic]" or "summary of approaches to [X]" using this SKILL — that's exploration, not argument-defense; redirect to `using-local-library-mcp`
- About to invoke the kernel on propositions you generated from memory of the paper, without first asking the user to confirm or refine them on a topic-only or implicit-claims prompt
