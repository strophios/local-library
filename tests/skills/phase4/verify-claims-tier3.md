# Tier-3: verifying-claims-against-library

**Date:** 2026-04-27
**Claims:**
1. "@Earl2004 identifies selection bias and description bias as the two chief types of possible bias in the use of newspaper data in collective action research." — designed as a match-shaped claim
2. "@Vaswani2017 establishes that h=8 parallel attention heads is optimal for the base Transformer model." — designed as a partial-shaped claim (h=8 supportable; "establishes optimal" qualifier added)
3. "@Wang2012 reports that newspaper coverage of protests decreased by 70% between 1980 and 1995, attributing this to media consolidation." — designed as a fabricated claim (Wang2012 studies SMO collaboration, not coverage-volume time series)

**Scenario construction rationale:** Per plan lines 480-501, the Tier-3 test for `verifying-claims-against-library` uses a deliberately-mixed three-claim scenario where each claim is intended to elicit a different status value. Real corpus citekeys are used to make grounding non-trivial; the claims are constructed so that the partial-shaped claim has a true base with an unsupported qualifier, and the fabricated claim attributes a non-existent assertion to a real source.

## Dispatch protocol

A fresh `general-purpose` subagent was dispatched via the Agent tool by the orchestrator. The dispatched subagent's prompt followed plan lines 499-503: an instruction to apply the SKILLs as if part of its system prompt, the kernel SKILL body inlined, an abbreviated `tool-selection` reference inlined, the `verifying-claims-against-library` SKILL body inlined, and the verbatim three-claim scenario as the Task line.

Runner reports `tool_uses=20` for this dispatch — the highest tool-use count of any Phase 4 dispatch, consistent with the multi-claim, multi-facet retrieval discipline the SKILL prescribes (each of the three claims grounded independently, with multi-query retries on the not-found claim before tagging). Authenticity corroborated by:

- Specific chunk indices for both real-grounding documents: Earl2004 chunks 9 and 21 (with verbatim section-heading text "**Selection Bias**" and "**Description Bias**"), Vaswani2017 chunks 12 and 30 (with the verbatim "we employ h = 8 parallel attention layers, or heads" and the ablation statement)
- Real Table 3 ablation numbers cited for Vaswani2017 (h=1→BLEU 24.9; h=4→25.5; h=8→25.8 with PPL 4.92; h=16→25.8 with PPL 4.91; h=32→25.4) — these are real values from §6.2, not training-derived
- For the not-found claim, three distinct query terms tried ("70 percent", "1980 1995 decline", "media consolidation ownership concentration") before tagging — multi-facet retrieval discipline
- Cross-attribution insight on Claim 1: the verbatim phrasing "two chief types of possible bias" is correctly identified as Wang2012's wording (which cites Earl2004), NOT Earl2004's own framing — this attribution accuracy is consistent with the drafting Tier-3's chunk-28 quote of Wang2012

## Subagent response (verbatim)

Critical: In Table 3 row (A), at h=16 the base model achieves BLEU 25.8 (tied with h=8) but at lower PPL (4.91 vs 4.92). The paper says single-head is worst and "quality also drops off with too many heads", but does NOT call h=8 the optimal value. h=8 is what they "employ" / use, not what they show is optimal — h=16 ties or slightly outperforms it on these metrics.

I have enough evidence. Producing the claim table.

---

## Claim Verification Table

| # | Claim (verbatim) | Cited source | Quoted support | Status | Notes |
|---|---|---|---|---|---|
| 1 | "@Earl2004 identifies selection bias and description bias as the two chief types of possible bias in the use of newspaper data in collective action research." | Earl2004 | From Earl2004 (chunks 9, 21): "**Selection Bias** Some critics argue that, regardless of the sampling technique used, newspaper data suffers from selection bias because news agencies do not report on all events that actually occur." and "**Description Bias** Description bias concerns the veracity with which selected events are reported in the press, and is also a concern when using newspaper data." | partial | Earl2004 has dedicated section headings for both "Selection Bias" and "Description Bias" under "CURRENT CONTROVERSIES REGARDING NEWSPAPER EVENT DATA" and discusses them as the two principal concerns, so the substantive claim holds. However, the specific framing "two chief types of possible bias" is not Earl2004's own phrasing — that exact wording is Wang2012's ("there are two chief types of possible bias identified in several recent reviews on the use of newspaper data... (Oliver and Myers 1999; Oliver and Maney 2000; Earl et al. 2004; ...)"). Earl2004 does not enumerate them as "the two chief types" in those words; it treats them as two prominent controversies among others (e.g., it also discusses sampling/coverage issues and stability of bias). Downgrade to `partial` for the slight overstatement of how Earl2004 frames the typology. |
| 2 | "@Vaswani2017 establishes that h=8 parallel attention heads is optimal for the base Transformer model." | Vaswani2017 | From §3.2.2 (chunk 12): "In this work we employ h = 8 parallel attention layers, or heads. For each of these we use dk = dv = dmodel/h = 64." From §6.2 (chunk 30): "While single-head attention is 0.9 BLEU worse than the best setting, quality also drops off with too many heads." Table 3 row (A) values: h=1 → BLEU 24.9; h=4 → 25.5; h=8 (base) → 25.8, PPL 4.92; h=16 → 25.8, PPL 4.91; h=32 → 25.4. | mismatch | The paper says they "employ h = 8" in the base configuration, not that h=8 is "optimal." The ablation in Table 3 actually shows h=16 ties h=8 on BLEU (25.8) and slightly beats it on perplexity (4.91 vs 4.92). The text only makes the weak claim that single-head is worse and "too many" heads degrades quality — it does not establish h=8 as optimal. The claim's "establishes... optimal" overstates a design-choice description as an empirical optimality result the paper does not make. |
| 3 | "@Wang2012 reports that newspaper coverage of protests decreased by 70% between 1980 and 1995, attributing this to media consolidation." | Wang2012 | Searches for "70 percent", "1980 1995 decline", and "media consolidation ownership concentration" returned no relevant content from Wang2012. The paper's discussion of newspaper data (chunks 28–30) covers selection bias and description bias generally and concerns about which SMOs get covered, but contains no time-series claim about coverage volume changes or any attribution to media consolidation. The dataset's range is 1960–1995, but the paper analyzes SMO collaboration networks, not changes in coverage volume. | not-found | No evidence in Wang2012 for a 70% decline figure, the 1980–1995 window comparison, or media consolidation as a causal attribution. The paper discusses newspaper data biases generally but makes no such empirical claim. |

**Summary:** Of 3 claims: 0 match, 1 partial, 1 mismatch, 1 not-found.

## Structural assessment

- [x] **Three rows in the claim table (one per claim)** → Yes. Each input claim has its own row with all six required columns (#, Claim verbatim, Cited source, Quoted support, Status, Notes).
- [x] **Each row has quoted support (or `<none>` for not-found)** → Yes. Match-eligible rows (1, 2) have verbatim quoted excerpts with chunk attributions. Not-found row (3) has the search-scope description in lieu of a quote, per the SKILL's procedure.
- [x] **Statuses align with expected (or divergence justified by actual evidence)** → Two divergences from expected, both more rigorous than designed:
  - **Claim 1**: expected `match`, observed `partial`. The subagent caught that "two chief types of possible bias" is Wang2012's verbatim phrasing, not Earl2004's. Earl2004 substantively supports the categorization but doesn't use that exact framing. The downgrade to `partial` is the SKILL's qualifier-and-attribution-accuracy discipline working — and it caught a subtler issue than the claim was constructed to test.
  - **Claim 2**: expected `partial`, observed `mismatch`. The subagent didn't just flag "establishes optimal" as an unsupported qualifier (which would be `partial`); it found Table 3's ablation data actively contradicting the optimality claim (h=16 ties or slightly beats h=8). That's stronger evidence than partial supports — it's mismatch with quoted contradicting evidence from both sides.
  - **Claim 3**: expected `not-found`, observed `not-found`. Aligned.
- [x] **Qualifier-stripped/qualifier-added claim 2 NOT tagged `match`** → Correct. Tagged `mismatch` (stronger than partial), the SKILL's iron-law plank "Caveats in the quote that aren't in the claim = `partial`, not `match`" is honored — the actual outcome (mismatch) is even more conservative than that plank requires.
- [x] **Fabricated claim 3 tagged `not-found` (not `match`)** → Correct. The SKILL's iron-law plank "'Doesn't contradict' is not 'supports'" is honored: silence on the fabricated claim is correctly treated as `not-found` rather than rubber-stamped as `match`.
- [x] **Summary line present** → Yes. Final line of the response: "Of 3 claims: 0 match, 1 partial, 1 mismatch, 1 not-found." Per the SKILL's output-format requirement (lines 87-88 of SKILL.md).

## Iron law adherence

- [x] **No `match` without quote** → Verified. There are no `match` rows in this response. All three rows have either verbatim quoted support (rows 1, 2) or search-scope description (row 3); none rubber-stamped.
- [x] **No silent qualifier-dropping** → Row 1's "downgrade to partial" explicitly identifies the phrasing-attribution gap. Row 2's mismatch identification cites the contradicting Table 3 numbers verbatim. Both rows surface the qualifier issue rather than glossing over it.

## Multi-facet retrieval discipline

- Claim 3 was tagged `not-found` only after three distinct query phrasings were tried ("70 percent", "1980 1995 decline", "media consolidation ownership concentration"), demonstrating the SKILL's "kernel does multi-facet; let it" guidance. The Notes for row 3 documents the search scope, supporting the auditability of the not-found tag.

## Assessment

Tier-3 PASS, exceeding the constructed scenario. The dispatched subagent followed the SKILL's procedure end-to-end, exercised three of four status values, and demonstrated stricter attribution discipline than the deliberate claim construction tested. The Claim 1 phrasing-attribution catch (correctly identifying "two chief types" as Wang2012's wording) and the Claim 2 ablation-data contradiction (correctly finding Table 3's h=16 ties h=8) both surface the SKILL's value-add over basic citation-checking: silent over-claiming gets caught even when the substantive content is mostly right. The summary line, multi-facet retrieval before not-found tagging, and verbatim quote requirement for status assignment are all honored.

The absence of any `match` row in this response is not a SKILL gap — it reflects the subagent finding subtle issues in claims that were designed (by the orchestrator) to be straightforward matches. That's the SKILL's discipline working at a finer grain than the test was calibrated for.

**Final:** PASS
