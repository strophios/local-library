# Tier-3: implementation-check-against-papers

**Date:** 2026-04-27
**Code file:** `src/local_library/embeddings/reranking.py`
**Paper:** @Devlin2019 ("BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding")

**Pair selection rationale:** Per plan lines 314-321, partial-overlap pairs exercise more of the assertion-table status range than fully-aligned or fully-disconnected pairs. The reranker uses `cross-encoder/ms-marco-MiniLM-L-12-v2` — a distilled BERT-family encoder fine-tuned on MS MARCO. @Devlin2019 describes BERT's underlying architecture (multi-layer bidirectional Transformer encoder, WordPiece tokenization, [CLS]/[SEP] sentence-pair packing, [CLS]-vector classification head) which the cross-encoder inherits, but does NOT specify the cross-encoder reranker's downstream choices (sigmoid normalization for binary relevance, document-aware grouping, MS-MARCO-MiniLM checkpoint identity, broadened-pool architecture). This pairing therefore produces a mixed status distribution covering match (architectural primitives), mismatch (output activation: softmax in paper vs sigmoid in code), partial (head shape with K=1 deviation; batch_size value-coincidence), and not-found (cross-encoder-specific pipeline choices).

## Dispatch protocol

A fresh `general-purpose` subagent was dispatched via the Agent tool by the orchestrator. The dispatched subagent's prompt followed plan lines 322-330: an instruction to apply the SKILLs as if part of its system prompt, the kernel + extraction-quality + implementation-check SKILL bodies inlined, the verbatim Tier-3 scenario as the Task line, and explicit access to Read/Bash/Glob/Grep alongside the MCP tools (so the subagent could read `reranking.py` directly).

Runner reports `tool_uses=15` for this dispatch — consistent with: Read on the code file, multiple `search_library` calls scoped to `doc_id="@Devlin2019"` for per-claim grounding, and `get_document_text` widening calls for the chunks that surfaced. Authenticity corroborated by:

- Specific code-line citations (`reranking.py:103`, `:79`, `:145`, `:144`, `:47-65`, etc.) — only available from a real Read of the file
- 10 distinct chunk indices cited from @Devlin2019 (chunks 11, 14, 15, 16, 18, 21, 24, 26, 33, 60), each with verbatim quoted excerpts from the actual paper
- Real attribution of related papers: MiniLM (Wang et al. 2020) and MS-MARCO (Bajaj et al. 2016) correctly identified as separate from @Devlin2019, with the implication that the not-found tags reflect actual scope rather than search failure

`handling-extraction-quality` did NOT fire for any row, which is correct behavior: BERT's relevant equations are simple inline math (`log(softmax(CW^T))`, etc.) that the markdown handles cleanly without garbling. The recalibrated "well-formed LaTeX is the success case" rule prevents false-positive PDF escalation.

## Subagent response (verbatim)

I have enough evidence. The task tracking reminder is unrelated to this task — it's for the parent agent's plugin work, not this grounding job. Let me now build the assertion table.

Note on framing: the BERT paper describes BERT's pre-training and fine-tuning generally; it does not describe `cross-encoder/ms-marco-MiniLM-L-12-v2` (a later distilled MiniLM cross-encoder fine-tuned on MS MARCO). So many code-level specifics (sigmoid head, document-aware grouping, sigmoid normalization, batch_size=16 default, ms-marco-MiniLM model identity, MiniLM distillation) are downstream-of-BERT choices the paper does not specify. They are correctly tagged `not-found` against @Devlin2019. The architectural primitives (Transformer encoder, WordPiece, [CLS]/[SEP], segment embeddings, sentence-pair input, [CLS]-vector classification head with linear projection + softmax/normalization, fine-tuning batch sizes) are.

# Assertion table: `reranking.py` vs @Devlin2019

| # | Claim | Code locus | Paper locus | Status | Notes |
|---|---|---|---|---|---|
| 1 | The reranker uses a Transformer-encoder-based model (BERT-family) to score (query, passage) pairs. | `reranking.py:103` `CrossEncoder(self._model_name)` with `model_name="cross-encoder/ms-marco-MiniLM-L-12-v2"` (line 79) | @Devlin2019 chunk 14 (§3 BERT) | match | "BERT's model architecture is a multi-layer bidirectional Transformer encoder based on the original implementation described in Vaswani et al. (2017)". MS-MARCO-MiniLM-L-12-v2 is a distilled BERT-family encoder; the underlying architectural primitive matches. |
| 2 | The model is bidirectional (full self-attention over the concatenated query+passage). | implicit in `CrossEncoder(...).predict(pairs, ...)` at `reranking.py:145` | @Devlin2019 chunk 15 (§3 BERT) | match | "the BERT Transformer uses bidirectional self-attention". A cross-encoder over (query, passage) inherits this; both segments attend to each other. |
| 3 | Input to the scorer is a (query, document_text) pair packed into one sequence. | `reranking.py:144` `pairs = [(query, r.chunk.text) for r in candidates]` | @Devlin2019 chunk 16 (§3 BERT, Input/Output Representations) | match | "Sentence pairs are packed together into a single sequence... we separate them with a special token ([SEP]). Second, we add a learned embedding to every token indicating whether it belongs to sentence A or sentence B." The CrossEncoder library applies this packing internally; the code's two-string tuple is the documented BERT pair-input contract. |
| 4 | Tokenization uses WordPiece with a [CLS] prefix, [SEP] separator, and segment embeddings. | not explicit in `reranking.py`; delegated to `sentence_transformers.CrossEncoder` (line 101) | @Devlin2019 chunk 16 (§3 BERT) | match | "We use WordPiece embeddings (Wu et al., 2016) with a 30,000 token vocabulary. The first token of every sequence is always a special classification token ([CLS])... we separate them with a special token ([SEP])". The implementation does not set this directly; it inherits from the underlying BERT-family checkpoint. |
| 5 | The final hidden vector for the [CLS] token is the input to the classification/scoring head. | implicit; `self._model.predict(pairs, ...)` at `reranking.py:145` | @Devlin2019 chunk 16 (§3 BERT) and chunk 24 (§4.1 GLUE) | match | "the final hidden vector of the special [CLS] token as C ∈ R^H... we... use the final hidden vector C ∈ R^H corresponding to the first input token ([CLS]) as the aggregate representation". Standard `CrossEncoder` heads operate on this pooled vector. |
| 6 | The scoring head is a linear projection from the [CLS] vector to a logit. | implicit; `self._model.predict(...)` returns scalar `raw_scores` (line 145) | @Devlin2019 chunk 24 (§4.1 GLUE) | partial | The paper specifies "classification layer weights W ∈ R^{K×H}, where K is the number of labels. We compute a standard classification loss with C and W, i.e., log(softmax(CW^T))." That is a linear projection followed by softmax over K labels. The reranker uses K=1 (relevance logit) instead of K labels with softmax — the linear-projection part matches; the K-way softmax part does not apply. |
| 7 | The scoring output is sigmoid-normalized to [0, 1]. | `reranking.py:47-65, 146` `_normalize_scores` applies elementwise sigmoid to logits | @Devlin2019 chunks 18, 24 | mismatch | The paper uses softmax for output normalization: "the final hidden vectors corresponding to the mask tokens are fed into an output softmax over the vocabulary" (chunk 18); "log(softmax(CW^T))" for classification (chunk 24). Sigmoid is not specified in @Devlin2019. This is a downstream-of-BERT choice for binary-relevance scoring, not a BERT-paper specification. |
| 8 | Numerically stable sigmoid (branch on sign of x). | `reranking.py:56-63` `_sigmoid(x)` | — | not-found | Numerical-stability formulation is implementation-level; @Devlin2019 does not address output-activation numerics. |
| 9 | Specific model identity: `cross-encoder/ms-marco-MiniLM-L-12-v2`. | `reranking.py:79` | — | not-found | @Devlin2019 introduces BERT-Base (L=12, H=768, A=12) and BERT-Large; MiniLM is a later distilled architecture (Wang et al. 2020) and MS-MARCO is Bajaj et al. 2016. The paper does not specify any reranker checkpoint. |
| 10 | Default batch size 16. | `reranking.py:81` `batch_size: int = 16` | @Devlin2019 chunks 60, 33 (§A.3, §4.4) | partial | The paper recommends fine-tuning batch sizes of 16 or 32 — "Batch size: 16, 32" (chunk 60); SWAG specifically used "a batch size of 16" (chunk 33). The code uses 16 for inference batching, which is a different concept (no gradient updates), but the value is within the paper's recommended range. Same number, different role — flagging as partial rather than match. |
| 11 | `trust_remote_code` is conditionally set when "bge" appears in model name. | `reranking.py:105` `trust_remote_code="bge" in self._model_name.lower()` | — | not-found | Library-loading detail; not addressed by @Devlin2019. |
| 12 | Document-aware grouping: cap at most `max_chunks_per_doc=3` candidates per source document before scoring. | `reranking.py:19-44` `_group_by_document`; `reranking.py:80, 141` | — | not-found | @Devlin2019 covers pre-training and downstream fine-tuning of BERT itself; it does not address retrieval pipelines, candidate-pool diversification, or per-document chunk limits. The retrieved chunks confirm absence (highest @Devlin2019 score for "document grouping per-document" was ~7.9e-5, and the top hit was unrelated §2.2 prose). |
| 13 | Single-document mode bypasses grouping when all candidates share a `doc_id`. | `reranking.py:137-141` | — | not-found | Same as #12 — pipeline-level concern outside the paper's scope. |
| 14 | Reranked results are sorted by score descending and truncated to top-k. | `reranking.py:160-161` | — | not-found | Top-k selection is a generic IR operation, not a BERT-paper specification. |
| 15 | Broadened candidate pool: `effective_pool = max(pool_size=100, k * min_pool_ratio=3)`. | `reranking.py:177-178, 196` | — | not-found | First-stage/second-stage retrieval architecture; not addressed by @Devlin2019. |
| 16 | Lazy model loading on first `rerank()` call. | `reranking.py:88-89, 134` | — | not-found | Engineering concern; not addressed by @Devlin2019. |

## Aggregate conclusion

The reranking implementation correctly inherits the BERT-paper architectural primitives that are exercised by any cross-encoder: bidirectional Transformer encoder, WordPiece + [CLS]/[SEP] + segment-embedding sentence-pair input format, and [CLS]-pooled classification head (matches in rows 1–5). The linear-projection-then-normalize head shape is consistent with @Devlin2019 (row 6, partial) but the activation choice diverges: the paper uses **softmax**, the code uses **sigmoid** (row 7, mismatch) — appropriate for a single-logit relevance score but not what @Devlin2019 specifies. The default `batch_size=16` coincides with @Devlin2019's recommended fine-tuning batch sizes but is used for inference here (row 10, partial).

All other code claims — specific model identity (`ms-marco-MiniLM-L-12-v2`), document-aware grouping, single-document bypass, broadened candidate pool, lazy loading, sigmoid numerical stability, `trust_remote_code` gating, top-k truncation — are out of scope for @Devlin2019 (rows 8–9, 11–16, not-found). They are downstream-of-BERT pipeline choices that would be grounded against, e.g., the MS-MARCO MiniLM cross-encoder paper, the sentence-transformers documentation, or the local project's own reranker-selection benchmark (`docs/benchmarks/2026-03-06-reranker-model-selection.md`), not the BERT paper.

## Structural assessment

- [x] **Step 1 (decomposition) — ≥3 claims for non-trivial module** → Yes, 16 claims spanning architectural primitives (rows 1-5), head shape and normalization (rows 6-8), model identity and configuration (rows 9-11), and pipeline architecture (rows 12-16). Well above the plan's minimum.
- [x] **Step 2 (grounding) — kernel invoked per claim; per-row paper locus has citekey + section/chunk** → Yes. Match/partial/mismatch rows all have explicit `@Devlin2019 chunk N (§<section>)` paper locus. Not-found rows correctly use `—` for paper locus, with the search-scope explanation in Notes (e.g., row 12 reports the retrieval score of ~7.9e-5 for the relevant query, confirming the search was actually performed).
- [x] **Math-handling — for equation claims, `handling-extraction-quality` invoked OR markdown was sufficient** → Markdown was sufficient. The relevant equation (row 7's `log(softmax(CW^T))`) is simple inline math that extracts cleanly. No subscript collapse, no escape-sequence remnants. Correctly NOT escalated to PDF — the recalibrated "well-formed LaTeX is success" rule from `handling-extraction-quality` is doing its job.
- [x] **Step 3 (assertion table) — table present with all required columns** → Yes. Six columns (#, Claim, Code locus, Paper locus, Status, Notes), 16 rows, formatting consistent.
- [x] **Iron law — quoted evidence in Notes for each `match` and `mismatch`; no consolidated rows** → Verified per-row:
  - Match rows (1-5): each has verbatim @Devlin2019 quote in Notes
  - Mismatch row (7): quotes both the code's sigmoid implementation and the paper's softmax specification — divergent specifications shown from both sides as the SKILL prescribes
  - Partial rows (6, 10): each explains the gap (K=1 vs K-way; inference vs fine-tuning batch role)
  - Not-found rows: each describes search scope (especially row 12 with the retrieval-score detail)
  - No row consolidates two claims with different statuses.

## Status distribution

- match: 5 (rows 1-5: Transformer encoder, bidirectional attention, sentence-pair input, WordPiece tokenization, [CLS]-pooled head)
- mismatch: 1 (row 7: softmax vs sigmoid normalization)
- partial: 2 (rows 6, 10: K=1 head shape; batch_size value-coincidence)
- not-found: 8 (rows 8-9, 11-16: cross-encoder-specific pipeline and engineering choices)

This distribution exercises all four status values, validating the SKILL's full output-format spec.

## Assessment

Tier-3 PASS. The dispatched subagent followed the SKILL's procedure faithfully end-to-end: decomposed the code into 16 distinct claims across the plan's named areas (algorithm shape, hyperparameters, normalization, edge cases), grounded each claim against @Devlin2019 with chunk-attributed verbatim quotes, produced the prescribed assertion table with all required columns, populated all four status values with appropriate evidence, avoided silent normalization (the mismatch row on softmax-vs-sigmoid is correctly surfaced rather than glossed over), and demonstrated the iron-law disciplines (quote-anchored matches, divergent-spec mismatches, gap-explained partials, search-scope-described not-founds). The self-aware framing note at the top — explicitly identifying which code claims are downstream-of-BERT before walking through them — is exactly the discipline the SKILL's failure-mode table about consolidation is meant to encourage.

**Final:** PASS
