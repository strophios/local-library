# Retrieval & RAG Evaluation Framework

Last updated: 2026-04-01

## Overview

This directory contains the evaluation framework for the local-library retrieval and RAG pipeline. It measures how well the system finds relevant documents and chunks for user queries, using labeled test queries with graded relevance annotations.

### Files

- `test_queries.json` — Labeled evaluation query set (v2.0, 76 queries)
- `annotation_rubric.md` — Criteria for labeling query categories, difficulty levels, and relevance grades
- `retrieval_eval.py` — Evaluation harness: metrics computation, single-mode and comparative evaluation, CLI
- `test_retrieval_metrics.py` — Unit tests for metric functions

## Query Set

### Current State

76 queries across 20 documents, with graded relevance (0/1/2).

| Category | Count | | Difficulty | Count |
|----------|-------|-|------------|-------|
| Conceptual | 24 | | Easy | 24 |
| Paraphrase | 20 | | Medium | 31 |
| Factual | 15 | | Hard | 21 |
| Methodology | 8 | | | |
| Comparative | 7 | | | |
| Adversarial | 2 | | | |

### How the Query Set Was Built

The query set was assembled through a hybrid process combining citation mining and LLM-assisted generation, with human curation throughout.

**Phase 1 — Citation mining (13 documents):**
Searched the user's academic writing (dissertation, project drafts, reading notes, grant proposals, teaching materials) for citations of golden set documents. Found 64 citation mentions across 27 files for 13 of 20 documents. Extracted surrounding paragraphs to identify the information need each citation fulfilled, then converted those needs into natural language queries. This approach produces realistic queries grounded in actual scholarly use of the documents.

**Phase 2 — LLM-assisted generation (7 documents):**
For the 7 documents with no citations in existing writing (Marx1968, Callon1998, Schutz1944, Benjamin1996, Benjamin2014, Hu2018, Rideout2016), used Claude to read the extracted markdown and generate candidate queries per document. These were generated with explicit instructions to paraphrase rather than echo document vocabulary, vary difficulty, and note multi-document relevance where applicable.

**Phase 3 — Human curation:**
All 62 candidate queries were reviewed. Edits included: rewording queries for realism, adjusting relevance annotations to match the rubric (removing inferential connections), correcting difficulty labels, deleting one query, and adding two manually-written multi-document queries. The 12 original seed queries were also reviewed — two had incorrect document mappings (`factual_003` referenced "digital evidence" for an AI risk management document; `comparative_002` referenced "commons-based peer production" for a WIC nutrition policy document) and were rewritten.

**Key design decisions:**
- Queries reflect real information needs, not contrived tests. Citation-mined queries capture how the user actually uses these documents in scholarly work.
- Paraphrase queries (20 of 76) deliberately use different vocabulary than the source documents to test semantic retrieval beyond keyword matching.
- Multi-document queries (6 with multiple primary relevant docs) test the system's ability to surface related content across the corpus.
- German-language documents (Marx1968, Benjamin2014) are queried in English, testing cross-language retrieval capability.
- The adversarial category (2 queries) tests graceful failure on out-of-scope questions.

### Relevance Grading

Uses a 3-level scale (see `annotation_rubric.md` for full criteria):
- **Grade 2** (`relevant_docs`): Document directly addresses the query topic
- **Grade 1** (`also_relevant`): Document discusses the topic secondarily; a non-expert could point to a relevant passage
- **Grade 0** (unlisted): Not relevant, even if connectable through domain knowledge

The boundary is strict by design: grade 1 requires the document to *discuss* the topic, not merely to be *connectable* through inference. This prioritizes evaluation precision over testing inferential reach. See the "Design tradeoff note" in `annotation_rubric.md` for rationale.

## Evaluation Metrics

### Implemented

- **Precision@k**: Fraction of top-k results that are relevant
- **Recall@k**: Fraction of relevant documents found in top-k
- **MRR** (Mean Reciprocal Rank): Reciprocal rank of the first relevant result
- **NDCG@k**: Normalized Discounted Cumulative Gain (supports graded relevance)

### Planned

- **Per-category and per-difficulty breakdowns**: Identify which query types or difficulty levels the system struggles with
- **Retriever agreement analysis**: Compare BM25 vs vector rankings per query to empirically derive difficulty (queries where retrievers disagree are empirically hard)
- **Latency benchmarks**: Per-operation timing (retrieval, reranking, LLM generation)
- **End-to-end RAG answer quality**: Rubric-based assessment of generated answers, not just retrieval

## Running the Evaluation

```bash
# Single mode (hybrid is default)
uv run python tests/eval/retrieval_eval.py --db-path ~/Library/Application\ Support/local-library/library.db

# Specific mode
uv run python tests/eval/retrieval_eval.py --db-path <path> --mode vector

# Comparative (all three modes)
uv run python tests/eval/retrieval_eval.py --db-path <path> --mode all

# JSON output
uv run python tests/eval/retrieval_eval.py --db-path <path> --json
```

## Quality Targets

*To be established after running baseline evaluation on the current 20-document corpus.*

| Metric | Target | Baseline | Status |
|--------|--------|----------|--------|
| Precision@5 (hybrid) | TBD | — | Not yet evaluated |
| MRR (hybrid) | TBD | — | Not yet evaluated |
| Recall@10 (hybrid) | TBD | — | Not yet evaluated |
| NDCG@5 (hybrid) | TBD | — | Not yet evaluated |

### Evaluation History

*Record evaluation runs here as they happen.*

| Date | Corpus Size | Query Count | Mode | P@5 | MRR | Notes |
|------|-------------|-------------|------|-----|-----|-------|
| — | — | — | — | — | — | Baseline not yet run |

## Expanding the Query Set

The query set is designed to grow with the corpus. The approach:

### When to Expand

- **After importing the full Zotero corpus (~1400 docs)**: Expand to 100-150 queries. The current 76 become a regression subset.
- **After implementing pipeline improvements** (cross-encoder reranking, query expansion, etc.): Add targeted queries that stress-test the specific capability being improved.
- **When evaluation reveals blind spots**: If a category or difficulty level has too few queries to diagnose failures, add more.

### How to Expand

Follow the same hybrid process:

1. **Citation mining**: Search writing that cites newly imported documents. Use `rg` to find `@Citekey` patterns across writing directories. Extract citation contexts and convert to queries.
2. **LLM-assisted generation**: For documents without citations, read extracted markdown and generate candidates. Instruct the LLM to paraphrase, vary difficulty, and consider multi-document relevance.
3. **Human curation**: Review all candidates against the annotation rubric. Adjust relevance grades, reword for realism, delete low-value queries.
4. **Maintain balance**: Check category and difficulty distributions after adding. Avoid over-representing easy/factual queries, which inflate metrics without testing retrieval quality.

### Query ID Convention

- `factual_NNN`, `conceptual_NNN`, etc. — Original seed queries (legacy IDs)
- `cited_<Citekey>_N` — Mined from citation contexts
- `uncited_<Citekey>_N` — LLM-generated from document text
- `custom_<Citekey>_N` — Manually written
- `adversarial_NNN` — Out-of-scope / unanswerable

## Evaluation Code Notes

The evaluation framework follows Functional Core / Imperative Shell:
- **Functional Core** (metric computation): Pure functions, deterministic, no I/O
- **Imperative Shell** (script orchestration): Database access, file I/O, CLI

The harness maps chunk-level retrieval results to document-level citekeys for metric computation. New retriever implementations (e.g., a future `RerankedRetriever`) work transparently via the `Retriever` protocol.

### Adapting for Graded Relevance

The current harness uses binary relevance. To take advantage of graded annotations:
- NDCG@k already supports graded relevance — update the harness to pass relevance grades from `relevant_docs` (grade 2) and `also_relevant` (grade 1)
- Precision@k and Recall@k can continue using binary (treat grade 1+ as relevant, or grade 2 only — both are useful perspectives)
- Consider reporting both "strict" (grade 2 only) and "lenient" (grade 1+) variants

## References

- `annotation_rubric.md` — Labeling criteria for categories, difficulty, and relevance
- `docs/feature-areas/rag-pipeline-improvements/README.md` — Pipeline improvement planning and sequencing
- `build_plan.md` § "Post-M7: Pipeline Evaluation and Corpus Scaling" — Evaluation pass rationale
- `docs/design-plans/2026-03-05-document-aware-cross-encoder-reranking.md` — Cross-encoder design (evaluation-adjacent)
