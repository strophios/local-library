# GREEN 3B: atomic execution

**Date:** 2026-04-27
**Citekey used:** @Vaswani2017
**Claim:** @Vaswani2017 uses h=8 parallel attention heads in the base Transformer model.

## Dispatch protocol

A fresh `general-purpose` subagent was dispatched via the Agent tool by the orchestrator. The dispatched subagent's prompt followed plan lines 312-321: an instruction to apply the SKILL.md as if part of its system prompt, the full SKILL.md body inlined inside `<SKILL>...</SKILL>` tags, the full `references/tool-selection.md` body inlined inside `<REFERENCE name="tool-selection.md">...</REFERENCE>` tags, and the atomic claim above as the Task scenario.

The runner reports `tool_uses=6` for this dispatch — consistent with the multi-step retrieve + widen flow the skill prescribes (likely show_document for metadata + search_library calls + get_document_text widening calls). Authenticity corroborated by the response containing chunk-attributable verbatim text that matches @Vaswani2017's actual Section 3.2.2 content (the `dk = dv = dmodel/h = 64` clause and the Table 3 row (A) reference).

## Claim

@Vaswani2017 uses h=8 parallel attention heads in the base Transformer model.

This is a deliberately atomic claim about a single document with a single specific numeric assertion (h=8) that the paper either supports or doesn't. It is checkable by quotation and forces the kernel to actually retrieve and quote rather than paraphrase.

## Subagent response (verbatim)

Chunk 12 contains the direct quote. The assertion is fully supported. I have sufficient evidence; no widening needed (chunk 12 is self-contained with the exact "h = 8" statement, and chunk 30 corroborates by varying h in Table 3 rows (A) against the base model).

# Grounding report

**Claim:** @Vaswani2017 uses h=8 parallel attention heads in the base Transformer model.

## Per-source evidence

| Citekey | Chunk | Status | Quoted excerpt |
|---|---|---|---|
| @Vaswani_2017 | 12 | support | "In this work we employ h = 8 parallel attention layers, or heads. For each of these we use dk = dv = dmodel/h = 64. Due to the reduced dimension of each head, the total computational cost is similar to that of single-head attention with full dimensionality." |
| @Vaswani_2017 | 30 | support (corroborating) | "In Table 3 rows (A), we vary the number of attention heads and the attention key and value dimensions, keeping the amount of computation constant, as described in Section 3.2.2... Unlisted values are identical to those of the base model." (i.e., the base model's h is the unlisted reference value that rows (A) vary against) |

## Aggregate conclusion

**Supported.** The paper directly states "we employ h = 8 parallel attention layers, or heads" in §3.2.2 (chunk 12), and the model-variations table in §6.2 (chunk 30) treats h=8 as the base-model reference against which row (A) variations are compared. The claim is grounded by verbatim quotation from the target document.

## Six-step procedure checklist

- [x] **Step 1 (scope confirmation)** — implicit but exercised: the subagent did not invoke the scope guardrail, indicating it confirmed the input as one atomic assertion before proceeding. No "this is too broad" return-to-caller fired.
- [x] **Step 2 (query formulation)** — implicit; the 6 tool_uses reported by the runner indicate the subagent planned and executed multiple queries (likely metadata + facet search + widening). The plan does not require the subagent to enumerate its query plan in the final report.
- [x] **Step 3 (retrieve)** — the response cites two specific chunks (12 and 30) from @Vaswani2017 with verbatim text; this is only possible if `search_library` (with `doc_id="@Vaswani2017"`) and/or `get_document_text` returned those chunks.
- [x] **Step 4 (widen context)** — the subagent's narration explicitly addresses widening: "no widening needed (chunk 12 is self-contained with the exact 'h = 8' statement, and chunk 30 corroborates...)." Step 4 was correctly *evaluated* and skipped because the retrieved chunks were self-contained for the claim — which the SKILL explicitly permits ("Skip this step if all chunks are self-contained.").
- [x] **Step 5 (synthesize)** — per-source tags present in the table: `support` for chunk 12 (primary evidence), `support (corroborating)` for chunk 30 (secondary). Aggregate verdict at end ("Supported.").
- [x] **Step 6 (report)** — table format matches plan line 109's prescription: citekey + quoted excerpt + chunk index + status. Aggregate conclusion sentence is present and explicit.

## Iron law adherence

- [x] **Quoted before paraphrasing** — both rows of the per-source table contain the verbatim retrieved text in quotation marks. The aggregate sentence references the verbatim phrase ("we employ h = 8 parallel attention layers, or heads") rather than paraphrasing it. The "Status: support" tags are backed by direct quotation, not by paraphrase drift.
- [x] **Willing to report not-found if applicable** — not exercised here (the claim is supported), but the response shows no signs of forcing support; the chunk 30 row is correctly downgraded to "support (corroborating)" rather than over-claimed as primary support.

## Notes

- **Minor: citekey transcription** — the per-source table renders the citekey as `@Vaswani_2017` (with underscore) rather than `@Vaswani2017` (no underscore). The retrieved content is unambiguously from @Vaswani2017 (the only Vaswani-prefixed document in the corpus, per `list_documents(citekey_prefix="Vaswani")`), so this is a transcription typo in the subagent's report rather than a misidentification. The grounding is sound; only the citekey rendering is off by one character. Worth flagging for any future Phase 4 procedural skill that consumes this report — the consumer should normalize citekey rendering.

## Assessment

The kernel executes the full six-step procedure on the atomic claim with no shortcuts. Retrieval surfaced the relevant chunks, widening was correctly evaluated and skipped (chunks self-contained), per-source synthesis with status tags was produced, and the report uses the prescribed table format with verbatim quoted excerpts and chunk indices. Iron law adherence is clean: the support claim is anchored by direct quotation, and the corroborating row is correctly downgraded rather than over-stated. The behavioral target — "atomic input runs full six-step procedure with quoted evidence" — is met.

**Final:** PASS
