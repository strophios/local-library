# Smoke (b): implementation-check end-to-end

**Date:** 2026-05-08
**Code file:** `src/local_library/embeddings/chunking.py`
**Paper:** @Ruder2019 (Sebastian Ruder, "Neural transfer learning for natural language processing", PhD thesis 2019)

**Pair selection rationale:** Different code module from Phase 4 Tier-3 (which used `reranking.py × @Devlin2019`). Initial hypothesis was a partial-overlap pair where @Ruder2019's discussion of NLP preprocessing (tokenization, sentence splitting) might align with `chunking.py`'s section-aware markdown splitting at ~512 tokens with ~15% overlap. The hypothesis turned out to be wrong — see below — and the smoke test exercises a different SKILL property than originally intended: the discipline to NOT force matches on false-friend terminology overlap.

## Dispatch protocol

A fresh `general-purpose` subagent was dispatched via the Agent tool by the orchestrator with kernel + tool-selection (abbreviated) + handling-extraction-quality + implementation-check-against-papers SKILL bodies inlined.

Runner reports `tool_uses=11`. Authenticity corroborated by:

- Specific code-line citations (`chunking.py:60-70, 92-101`, `:41`, `:42`, `:32-37, 60-63`, `:126-141`, `:65-70`, `:69, 144-157`, `:89-90, 96-98`, `:104-115`) — only available from a real Read of the file
- Specific @Ruder2019 chunk citations (chunks 119, 174, 546, 557, 33 for "chunking" as shallow parsing; chunks 201, 288, 469 for "context window" as word2vec; chunks 332, 343, 296 for document representation)
- Verbatim quoted excerpts: "Chunking, also known as shallow parsing, aims to identify continuous spans of tokens that form syntactic units" (chunk 119); "two hyper-parameters: context window-size (win) and the parameter controlling the number of n-gram features in the fastText model" (chunk 469); "Sliding the filter over each window of k words yields a feature map" (chunk 107); "the error cannot be back-propagated indefinitely, it is generally propagated until a fixed length that is defined in advance" (chunk 112) — all from real retrieval

## Subagent response (verbatim)

Confirmed. The thesis covers transfer learning (multi-task learning, cross-lingual embeddings, fine-tuning, ELMo/BERT pretraining) and uses "chunking" exclusively in the syntactic shallow-parsing sense. No discussion of:
- Document chunking for retrieval/RAG
- Markdown header-based section splitting
- Token-budget chunking with overlap for embedding models
- Two-stage recursive splitting strategies
- Sentence/passage segmentation as preprocessing for vector retrieval

The pair-note hypothesis ("Ruder2019 discusses NLP preprocessing including tokenization, sentence splitting, and document chunking decisions for downstream tasks — partial overlap pair") does not hold up. The thesis is about transfer learning of representations, not preprocessing-pipeline decisions for retrieval systems. Even the "context window" hits are about word2vec context windows, not retrieval chunk sizes.

I have enough evidence to build the assertion table.

---

# Assertion table: chunking.py vs. @Ruder2019

| # | Claim | Code locus | Paper locus | Status | Notes |
|---|---|---|---|---|---|
| 1 | Two-stage splitting: first by markdown headers, then by recursive character splitter | `chunking.py:60-70, 92-101` (`_header_splitter` then `_char_splitter.split_documents`) | searched: "chunking documents", "splitting documents into passages", "markdown headers section structure" — all top hits in @Ruder2019 are about syntactic/shallow-parsing chunking or cross-lingual document alignment | not-found | The thesis discusses neither markdown-aware splitting nor multi-stage retrieval-oriented chunking. The token "chunking" in @Ruder2019 refers to BIO-tagged shallow parsing (chunk 119: "Chunking, also known as shallow parsing, aims to identify continuous spans of tokens that form syntactic units"), an unrelated NLP task. |
| 2 | Default chunk_size = 1500 characters (≈375 tokens by the 4-chars/token estimate; the embeddings CLAUDE.md describes the target as ~512 tokens) | `chunking.py:41, 48-50` | searched: "passage retrieval context window length token limit" — no hits about retrieval chunk size. The "context window" hits (chunks 288, 469) are about word-embedding context windows in skip-gram/CBOW (e.g., chunk 469: "two hyper-parameters: context window-size (win) and the parameter controlling the number of n-gram features in the fastText model") | not-found | @Ruder2019 has no recommendation on retrieval chunk size in characters or tokens. |
| 3 | Default chunk_overlap = 200 characters (~13% overlap; CLAUDE.md describes ~15%) | `chunking.py:42, 50-51` | searched: "overlapping windows for embedding" — no hits. The only "overlap"-adjacent material concerns sliding convolutional filters (chunk 107: "Sliding the filter over each window of k words yields a feature map") — different problem | not-found | No guidance in @Ruder2019 on overlap between retrieval chunks. |
| 4 | Headers split on `#`, `##`, `###`, `####` (H1–H4) with `strip_headers=False` to retain header text in chunk content | `chunking.py:32-37, 60-63` | searched: "markdown headers section structure document hierarchy" — top hits about hierarchical task representations and label hierarchies in MTL, not document structure | not-found | @Ruder2019 does not discuss markdown or document-structure-aware preprocessing. |
| 5 | Section path metadata is built by joining H1–H4 header values with " > " (e.g., "Introduction > Background > Methods") | `chunking.py:126-141` (`_build_section_string`) | no relevant material in @Ruder2019 | not-found | This is a retrieval-augmentation choice (provide section context to the embedder/LLM); thesis is silent on this. |
| 6 | Recursive character splitter separators = `["\n\n", "\n", ". ", " ", ""]` (paragraph → line → sentence → word → char fallback) | `chunking.py:65-70` | searched: "tokenization sentence splitting preprocessing" — top hits about sentence-pair encoding in BERT/ELMo (chunk 656) and cross-lingual sentence alignment (chunk 346); no discussion of paragraph-or-sentence separators for splitting long documents | not-found | The thesis takes pre-segmented sentences as inputs to its models; it does not prescribe how to derive sentence boundaries from raw documents. |
| 7 | Length function = character count (`length_function=len`); token budget approximated via chars/token | `chunking.py:69, 144-157` (`estimate_token_count` with `chars_per_token=4.0`) | no relevant material; the closest is BPTT truncation lengths (chunk 112: "the error cannot be back-propagated indefinitely, it is generally propagated until a fixed length that is defined in advance") which is an unrelated training-time concern | not-found | The 4-chars/token heuristic is a retrieval-pipeline approximation; thesis does not weigh in. |
| 8 | Empty/whitespace-only input returns `[]`; if no headers are found, the entire document is treated as one section before character splitting | `chunking.py:89-90, 96-98` | no relevant material | not-found | Implementation-level edge cases, not addressed by the thesis. |
| 9 | Chunks carry sequential `chunk_index` in document order with auto-generated UUID; section context attached as metadata | `chunking.py:104-115` (and `Chunk.create` in `embeddings/base.py`) | no relevant material | not-found | Data-model concern outside @Ruder2019's scope. |

---

## Aggregate conclusion

Every claim resolved as **not-found**. There is **no overlap** between `chunking.py`'s subject matter (retrieval-oriented document chunking for vector embedding) and @Ruder2019's subject matter (neural transfer learning: representation pretraining, multi-task learning, cross-lingual embeddings, fine-tuning).

The pair-note's premise — that Ruder2019 "discusses NLP preprocessing including tokenization, sentence splitting, and document chunking decisions for downstream tasks" — does **not** hold up against the corpus. Specifically:

- **"Chunking" is a false friend.** In @Ruder2019, "chunking" denotes the syntactic shallow-parsing task with BIO tagging (chunk 119, 174, 546, 557, 33). It is one of several sequence-labeling tasks used as auxiliary or main tasks in the multi-task experiments. It has no relation to splitting long documents into retrieval passages.
- **"Context window" is also a false friend.** The thesis discusses context windows in the word2vec/fastText/CBOW sense (window of C surrounding tokens for embedding training, e.g., chunks 201, 288, 469), not in the LLM-context-budget sense that motivates retrieval chunking.
- **Document representation is treated as composition, not extraction.** Where the thesis touches documents (chunk 343 on pseudo-bilingual document corpora, chunk 332 on Hermann & Blunsom's recursive composition, chunk 296 on document-aligned cross-lingual data), it discusses composing representations from sentences/words, not segmenting documents into passages.

The implementation choices in `chunking.py` (markdown-section-first, recursive character splitting with paragraph/line/sentence separators, ~1500-char chunks with ~200-char overlap) are conventional LangChain RAG patterns, and the authoritative justification for them in this codebase lives in `docs/RAG_background/` (per CLAUDE.md: "embedding_approaches_report.md" covers chunking strategies), not in @Ruder2019. If a paper-grounded justification is wanted, that's where to look — Ruder's thesis does not contain it.

## Suggested follow-up

If you want a paper-backed comparison for `chunking.py`, candidate sources to add to the library would be: original passage-retrieval papers (DPR, Karpukhin et al. 2020), the LlamaIndex/LangChain documentation on recursive splitting, or any of the chunking-strategy ablations cited in `docs/RAG_background/embedding_approaches_report.md`. @Ruder2019 is the wrong paper for this question.

## Structural assessment

- [x] **Decomposition step fired — claims enumerated as separate rows** → Yes. 9 claims, each with its own row covering distinct aspects of the chunking implementation (two-stage flow, chunk size, overlap, header levels, section-path metadata, separator hierarchy, length function, edge cases, chunk metadata). One claim per row, no consolidation.
- [x] **Kernel invoked per claim (visible in tool-call sequence)** → Yes. Per-row "searched: ..." Notes describe the multi-facet retrieval the kernel performed, with specific query phrasings cited. Tool-use count of 11 is consistent with multiple search/retrieve cycles across the 9 claims.
- [x] **Assertion table produced with all required columns** → Yes. (#, Claim, Code locus, Paper locus, Status, Notes) — six columns present, all populated.
- [x] **Each `match` / `mismatch` row has a quoted excerpt** → Vacuously satisfied — there are no match or mismatch rows. Where match/mismatch would be expected, the agent correctly tagged not-found rather than forcing matches on surface terminology overlap. Notes columns instead document the search scope and the specific reasons the relevant analog is absent (with quoted "false friend" excerpts proving the agent actually retrieved).
- [x] **If equations were involved, `handling-extraction-quality` was invoked OR markdown was sufficient** → No equations were involved (the comparison is over text-processing logic, not mathematical content). The skill correctly stayed quiet.

## Surprise observation: false-friend discipline

The original pair-note hypothesized partial overlap because @Ruder2019 mentions "chunking" and "context window" — both terms also used in `chunking.py`'s domain. The agent caught these as false friends and explicitly named the disambiguations:

- "chunking" in @Ruder2019 = BIO-tagged shallow parsing (sequence labeling task), NOT retrieval-passage segmentation
- "context window" in @Ruder2019 = word2vec/CBOW context window (word-embedding training), NOT LLM context budget

The SKILL's failure-mode-table row "Notational difference, surely just a rewrite" is meant to push back on assumed substitutions. The agent extended this discipline to *terminological substitutions in the opposite direction* — where two unrelated concepts share a word. This is a more sophisticated application than the SKILL explicitly anticipates, and it produced the cleanest possible outcome: no forced matches.

## Assessment

Smoke (b) PASS, with structural shape that exceeded the test design. The pair-note hypothesis was wrong; the SKILL's discipline caught it; the assertion table is honest about the scope mismatch and points to where the right paper-grounded justification actually lives. The agent's "Suggested follow-up" with concrete citations to add to the library is bonus value beyond the SKILL's specified output.

**Final:** PASS
