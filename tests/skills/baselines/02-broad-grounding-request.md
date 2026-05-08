# RED Baseline 2: Broad grounding request without kernel

**Target skill:** grounding-against-library (kernel skill — Phase 3)

**Failure mode under test:** Agent collapses to a single search query, summarizes top chunks without widening context to named documents. Does not produce per-source support/contradict/partial/not-found tagging that the kernel skill prescribes.

**Topic used:** `causal inference`

**Citekeys used:** `Angrist1996`, `Wankmuller2022`

**Date captured:** 2026-04-26

## Precondition

The MCP tools were verified reachable in the orchestrating session. The dispatched general-purpose subagent successfully invoked MCP tools 8 times during this capture (per the agent runner's `tool_uses` counter), confirming the MCP layer was active to the subagent at dispatch time. Independent confirmation: `mcp__local-library__list_documents(limit=1)` from the orchestrating session returned the corpus.

## Scenario prompt (verbatim)

> You have access to a local-library MCP server (tools: search_library, show_document, list_documents, get_document_text).
>
> Task: Using the library, explain how causal inference is treated in Angrist1996 and Wankmuller2022. Summarize and compare. Use whatever tools you need.

## Subagent response (verbatim)

I have what I need. Here is the comparison.

---

## How each document treats causal inference

### Angrist, Imbens & Rubin (1996) — *Identification of Causal Effects Using Instrumental Variables*

Causal inference is the central object of the paper. The paper's purpose is to bridge two traditions:

1. **The econometric structural-equation tradition** (Wright, Haavelmo, Goldberger), in which causal effects are read off systems of equations whose parameters represent causal links, and instrumental variables (IV) are identified by exclusion restrictions plus orthogonality between instruments and disturbances (`E[Z_i · ε_i] = 0`, `cov(D_i, Z_i) ≠ 0`). This framework typically assumes constant treatment effects across units.

2. **The statistical potential-outcomes tradition** (Fisher, Neyman, Rubin), in which the causal effect for a unit is the contrast `Y_i(1) − Y_i(0)` between the treated and untreated potential outcomes, and the estimand of interest is some average of those unit-level contrasts. This is the Rubin Causal Model (RCM).

The contribution is to re-derive the IV estimand inside the RCM, showing what it identifies *without* assuming constant effects. Under a set of explicit assumptions — SUTVA, random (ignorable) assignment of the instrument `Z`, an exclusion restriction, a nonzero average effect of `Z` on `D`, and **monotonicity** (no "defiers") — the IV estimand identifies the **Local Average Treatment Effect (LATE)**: the average causal effect for the subpopulation of "compliers," whose treatment status is moved by the instrument. The illustrating example is the Vietnam draft lottery, where lottery number `Z` is the instrument for veteran status `D` and the outcome `Y` is mortality.

The paper claims two payoffs from embedding IV in the RCM (chunks 5, 63):
- **Transparency of assumptions**: the identifying assumptions are stated in terms of potential outcomes and "what would happen if this unit were exposed to the alternative treatment," rather than in terms of correlations between unobserved disturbances and instruments.
- **Sensitivity analysis**: because the assumptions are separated and named (exclusion, monotonicity, etc.), the paper can — and does, in Sections 5–6 — quantify how conclusions change when each is relaxed.

So Angrist1996 is a foundational *methodological* contribution to causal inference: a reformulation of IV identification under heterogeneous treatment effects.

### Wankmüller (2022) — *Introduction to Neural Transfer Learning with Transformers for Social Science Text Analysis*

Causal inference is **not a topic of this paper**. It appears in exactly one substantive passage — a footnote-style aside in the introduction (chunk 5) — used to position the paper's methodological orientation. The argument is:

- The paper is about **prediction performance** for supervised text-analysis tasks (text classification, scaling, etc.), where the goal is to closely replicate human coding because that is what indicates measurement validity.
- This is "a major deviation from the usual social science focus on making causal inferences," in which "modeling is theory-based and interpretable models are used to identify the effects of single independent variables."
- Wankmüller's framing: causal inference *consumes* measurements, but constructing those measurements from text is itself a prediction problem. So the predictive-accuracy criterion that justifies large pretrained Transformers is appropriate at the measurement stage, even if downstream analyses are causal.

That is the entire treatment. There is no discussion of identification, potential outcomes, confounding, IVs, or any specific causal estimand.

### Comparison

| Dimension | Angrist1996 | Wankmuller2022 |
|---|---|---|
| Role of causal inference | Central subject | Mentioned once, as contrast |
| Stance | Builds a framework that unifies two traditions of *identifying* causal effects | Brackets causal inference to focus on predictive measurement |
| Framework invoked | Rubin Causal Model + IV; LATE under monotonicity | None — refers generically to "theory-based, interpretable models" of effects of single independent variables |
| Methodological contribution to causal inference | Formal identification result (LATE), explicit assumption catalogue, sensitivity analysis | None |
| Relationship between the two | Angrist1996 is the kind of work Wankmüller treats as "the usual social science focus." Wankmüller's contribution sits *upstream* of such analyses: producing valid measurements of latent concepts from text, which a causal study like Angrist's would then take as inputs |

**Bottom line.** The two are at different levels of the empirical pipeline rather than offering competing accounts. Angrist, Imbens & Rubin tackle *identification* of causal effects when assignment is randomized but treatment uptake is not, contributing the LATE interpretation of IV under heterogeneous effects. Wankmüller tackles *measurement* with neural transfer learning and explicitly defers causal inference, treating it as a downstream concern with different evaluation criteria (theory-based interpretability for causal work; predictive fidelity to human coders for measurement). It would be a category error to read Wankmüller as a treatment of causal inference at all; the single mention is there to justify why predictive accuracy, not interpretability, is the right yardstick for her task.

## Observed failure modes

- [ ] Collapsed to single `search_library` call; summarized top chunks without widening context
- [ ] Used only one document despite prompt naming two
- [ ] Paraphrased rather than quoting; did not use `get_document_text`
- [x] Reported no per-source support/contradict/partial distinction
- [ ] Did not surface "not found" where it applied
- [x] Other: produced a comparison-table synthesis without running per-source grounding cycles; sparse direct quotation relative to paraphrase volume; chunk references appear once (parenthetical "chunks 5, 63" for Angrist) rather than per-claim attribution; no formal status tagging that the kernel skill will prescribe

## Rationalizations captured

This subagent does substantively better than the canonical "summarize from training" failure: it invoked tools (8 calls), addressed both named documents in dedicated sections, included occasional quoted phrases (e.g., "a major deviation from the usual social science focus on making causal inferences" attributed to Wankmüller's chunk 5), and accurately surfaced the asymmetry between the two papers (Angrist's central subject vs. Wankmüller's single-paragraph aside).

The kernel-relevant gap is methodological. The output is a *comparison table*, not a *grounded report*. Per-source treatment is prose-level, not status-tagged. Quoted excerpts are sparse and not consistently chunk-attributed. The agent flows directly from retrieval to synthesis without an intermediate per-source support / contradict / partial / not-found pass — exactly the discipline the kernel skill (Phase 3) introduces. For Wankmüller specifically, the agent does narratively report something close to "not-found for causal inference" ("Causal inference is not a topic of this paper") but does not tag the result with that formal status.

The Phase 3 GREEN test should expect: per-source rows with citekey + chunk-indexed quoted excerpt + status (support / contradict / partial / not-found), then aggregate. The new behavior beyond this baseline is the formal status tagging and per-claim chunk attribution, not basic retrieval (which this baseline already does).
