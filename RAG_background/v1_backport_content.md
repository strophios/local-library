# v1 RAG Research: Backport Content

This document captures useful content from the v1 RAG research reports (`docs/archive/v1_RAG_background/RAG_background/`) that should be integrated into the current implementation. The v1 research was conducted with limited web search capabilities, which led to some outdated or incorrect information (e.g., sqlite-vss instead of sqlite-vec, misattributed MTEB scores). However, several elements remain valuable.

---

## 1. Evaluation Framework

**Source**: `docs/archive/v1_RAG_background/RAG_background/00_final_summary.md`

**Why integrate**: The current v2 reports lack a detailed evaluation framework with concrete metrics and targets. This is essential for validating RAG quality before and after implementation.

**Where to integrate**: Create a new `RAG_background/evaluation_framework.md` or add as a section to `00_final_summary_report.md`.

### Test Set Design

Create **50-100 stratified queries** covering:

| Category | Example Queries | Count |
|----------|----------------|-------|
| **Factual lookup** | "What learning rate did BERT use?" | 15-20 |
| **Conceptual** | "How does attention relate to memory?" | 15-20 |
| **Comparative** | "How does GPT differ from BERT?" | 10-15 |
| **Methodology** | "What evaluation metrics are used for NER?" | 10-15 |
| **Adversarial** | Questions NOT answerable from corpus | 10-15 |

**Adversarial queries are critical** — they test whether the system correctly says "I don't know" vs. hallucinating.

### Quality Targets

For personal academic use, these thresholds are "good enough":

| Metric | Target | Notes |
|--------|--------|-------|
| Precision@5 | ≥ 60% | At least 3 of top 5 results relevant |
| Recall@10 | ≥ 70% | Find most relevant documents |
| MRR | ≥ 0.5 | Relevant doc typically in top 2 |
| "I don't know" accuracy | ≥ 80% | On adversarial queries |
| End-to-end latency | < 3 seconds | Query to answer |

If you're below these targets, investigate:
- Chunk size (too large = diluted relevance, too small = fragmented context)
- Embedding model mismatch (nomic-embed-text prefixes)
- Vector store configuration

### Latency Targets

| Operation | Target | Notes |
|-----------|--------|-------|
| Embedding query | < 50ms | Single query embedding |
| Vector search | < 100ms | sqlite-vec at 100k vectors |
| LLM generation | < 2s | Claude Haiku |
| Total query | < 3s | User-acceptable for interactive use |
| Citation autocomplete | < 150ms | For smooth Neovim experience |

### Evaluation Code

```python
def evaluate_retrieval(test_set: list[dict], retriever, k: int = 10) -> dict:
    metrics = {"precision@k": [], "recall@k": [], "mrr": [], "idk_correct": []}

    for query in test_set:
        results = retriever.search(query["text"], k=k)
        retrieved_citekeys = [r.metadata["citekey"] for r in results]

        if query.get("unanswerable"):
            # Adversarial query — should return low confidence or empty
            is_correct = len(results) == 0 or results[0].score < 0.3
            metrics["idk_correct"].append(1 if is_correct else 0)
            continue

        relevant = set(query["relevant_docs"])
        retrieved = set(retrieved_citekeys[:k])

        precision = len(relevant & retrieved) / k
        recall = len(relevant & retrieved) / len(relevant) if relevant else 0

        # MRR
        mrr = 0
        for i, citekey in enumerate(retrieved_citekeys):
            if citekey in relevant:
                mrr = 1 / (i + 1)
                break

        metrics["precision@k"].append(precision)
        metrics["recall@k"].append(recall)
        metrics["mrr"].append(mrr)

    return {
        "precision@k": sum(metrics["precision@k"]) / len(metrics["precision@k"]),
        "recall@k": sum(metrics["recall@k"]) / len(metrics["recall@k"]),
        "mrr": sum(metrics["mrr"]) / len(metrics["mrr"]),
        "idk_accuracy": sum(metrics["idk_correct"]) / len(metrics["idk_correct"]) if metrics["idk_correct"] else None
    }
```

---

## 2. Risk Assessment Table

**Source**: `docs/archive/v1_RAG_background/RAG_background/00_final_summary.md`

**Why integrate**: Comprehensive risk analysis with mitigations. The v2 reports have a shorter risk section; this provides more actionable detail.

**Where to integrate**: Add to `00_final_summary_report.md` Section 8 (Risks and Mitigations) or as appendix.

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| PDF extraction failures | Medium | Low | PyMuPDF fallback; flag for manual review |
| Retrieval quality below targets | Medium | High | Tune chunk size; evaluate early; add hybrid search |
| Citation verification unreliable | High | Medium | Treat as review aid only; validate on test set first |
| Embedding model obsolescence | Medium | Medium | Keep original markdown; budget for re-embedding |
| Dependency breaking changes | Medium | Medium | Pin versions; test updates in isolation |
| Zotero schema changes | Low | High | Abstract Zotero access; monitor Zotero releases |
| Processing time exceeds estimates | Medium | Low | Checkpoint frequently; process overnight |
| M1 thermal throttling | Medium | Low | Process in batches with cooling breaks |
| LLM API pricing changes | Low | Low | Can fall back to local models |
| False confidence from citations | High | High | Train user skepticism; always verify important claims |

**The highest-impact risk is false confidence**: The system can return authoritative-looking answers with correct citekeys that don't actually support the claims. Always verify important citations manually. Consider citation triage (once operational) as a way to flag suspicious outputs.

---

## 3. Batch Processing with Thermal Management

**Source**: `docs/archive/v1_RAG_background/RAG_background/00_final_summary.md`

**Why integrate**: Practical code for processing large PDF corpora on M1 with checkpointing and thermal throttling management.

**Where to integrate**: Create a new `RAG_background/batch_processing.md` or add to `pdf_extraction_tools_report.md`.

### Processing Time Estimates

For 1400 academic PDFs on M1 Pro:

| Stage | Time | Notes |
|-------|------|-------|
| PDF extraction (Marker) | 40-80 hours | ~2-4 min/paper; varies by complexity |
| Embedding (nomic-embed-text) | 1-2 hours | ~250ms/batch of 32 chunks |
| Total | 45-85 hours | Run in overnight batches |

**What drives the variance**:
- Scanned vs. native PDFs (scanned = 2-3x slower)
- Document length (20-page papers vs. 200-page dissertations)
- Thermal throttling under sustained load (M1 Pro will throttle after ~30 min continuous)

**Recommended duty cycle**: Process for 2-3 hours, rest for 30 minutes. Or run overnight batches of ~100 documents.

### Expected Failure Rate

| Category | % of Corpus | Outcome |
|----------|-------------|---------|
| Native PDFs, standard layout | ~70% | Clean extraction |
| Native PDFs, complex layout | ~15% | Minor issues, usable |
| Scanned PDFs | ~10% | OCR quality varies |
| Problem documents | ~5% | Require manual review or PyMuPDF fallback |

For 1400 documents, expect ~70 to require some attention.

### Processing Pipeline with Checkpointing

```python
import hashlib
from pathlib import Path
import time

BATCH_SIZE = 50  # Smaller batches for thermal management
CHECKPOINT_FILE = Path("./processing_checkpoint.json")

def process_library(items: list[dict]):
    processed = load_checkpoint()
    failures = []

    for batch_num, batch in enumerate(chunked(items, BATCH_SIZE)):
        print(f"Batch {batch_num + 1}/{len(items) // BATCH_SIZE}")

        for item in batch:
            if item["id"] in processed:
                continue

            try:
                # Extract
                markdown = marker_extract(item["pdf_path"])
                content_hash = hashlib.sha256(markdown.encode()).hexdigest()[:16]

                # Chunk
                chunks = chunker.chunk_document(markdown, item["id"])

                # Embed (batch for efficiency)
                embeddings = embedder.encode([c.text for c in chunks])

                # Store
                store_document(item, markdown, content_hash, chunks, embeddings)
                processed.add(item["id"])

            except Exception as e:
                failures.append({"id": item["id"], "error": str(e)})
                log_failure(item["id"], e)

        # Checkpoint after each batch
        save_checkpoint(processed)
        print(f"  Completed. {len(failures)} failures so far.")

        # Thermal management pause
        if batch_num % 3 == 2:
            print("  Cooling pause (5 min)...")
            time.sleep(300)

    return failures
```

### Recovery from Interruption

```python
# Resume from checkpoint
processed = load_checkpoint()
remaining = [item for item in all_items if item["id"] not in processed]
process_library(remaining)
```

---

## 4. HyDE (Hypothetical Document Embeddings)

**Source**: `docs/archive/v1_RAG_background/RAG_background/04_llm_querying.md`

**Why integrate**: Clear explanation of when to use HyDE and implementation. The v2 reports mention HyDE but lack this practical guidance.

**Where to integrate**: Add to `llm_query_interface_report.md` or create implementation patterns document.

### What HyDE Is

HyDE improves retrieval for conceptual queries by:
1. Generating a hypothetical answer using the LLM
2. Embedding that hypothetical answer instead of the raw query
3. Searching for documents similar to the hypothetical

The hypothetical document often has better vocabulary overlap with actual documents than the original question.

### When to Use HyDE

**Good for**:
- Broad/conceptual questions ("How do embeddings relate to semantic similarity?")
- When basic retrieval returns poor results
- Questions where user vocabulary differs from document vocabulary

**Not for**:
- Specific factual queries ("What does the BLIP model do?")
- Queries with rare technical terms (use keyword search instead)

### Implementation

```python
def hyde_retrieve(self, question: str, k: int = 5) -> list:
    """Generate hypothetical answer, then use it for retrieval."""

    # Generate hypothetical document
    hyde_prompt = f"""Write a short paragraph that would appear in an academic paper
answering this question. Write as if excerpting from a real paper.

Question: {question}

Hypothetical excerpt:"""

    hypothetical = self.llm.generate(hyde_prompt)

    # Use hypothetical for retrieval (better embedding match)
    return self.retriever.search(hypothetical, k=k)
```

**Important**: Use a capable LLM (Claude/GPT-4) for HyDE generation, not local models. Quality of the hypothetical document matters.

---

## 5. Conversation Context Handling

**Source**: `docs/archive/v1_RAG_background/RAG_background/04_llm_querying.md`

**Why integrate**: This is described as "a significant gap in many RAG implementations" in v1. The v2 reports don't cover this at all.

**Where to integrate**: Add to `llm_query_interface_report.md` Section 4 (Context Assembly Pattern) or new section.

### The Problem

Follow-up questions often reference context from earlier in the conversation:
- "What did they find?" (who is "they"?)
- "Compare that to the other approach" (which approaches?)

Without conversation context, these queries retrieve irrelevant documents.

### Solution: Query Contextualization

Rewrite follow-up questions as standalone queries before retrieval:

```python
class ConversationalRAG:
    def __init__(self, retriever, llm):
        self.retriever = retriever
        self.llm = llm
        self.history = []  # List of {"query": str, "response": str, "sources": list}

    def query(self, question: str) -> str:
        # Contextualize query if follow-up
        standalone_q = self.contextualize_query(question)

        # Retrieve and generate
        chunks = self.retriever.search(standalone_q)
        response = self.generate_with_history(question, chunks)

        # Store history
        self.history.append({
            "query": question,
            "response": response,
            "sources": [c.metadata.get("citekey") for c in chunks]
        })

        return response

    def contextualize_query(self, question: str) -> str:
        """Rewrite follow-up question as standalone."""
        if not self.history:
            return question

        # Last 3 turns for context
        history_text = "\n".join([
            f"User: {h['query']}\nAssistant: {h['response'][:200]}..."
            for h in self.history[-3:]
        ])

        prompt = f"""Given this conversation, rewrite the follow-up question
as a standalone question.

Conversation:
{history_text}

Follow-up: {question}

Standalone question:"""

        return self.llm.generate(prompt).strip()

    def generate_with_history(self, question: str, chunks: list) -> str:
        context = self.format_context(chunks)

        # Include relevant history
        history_context = ""
        if self.history:
            history_context = "\n\nPrevious discussion:\n" + "\n".join([
                f"Q: {h['query']}\nA: {h['response'][:300]}..."
                for h in self.history[-2:]
            ])

        prompt = f"""Context from academic sources:

{context}
{history_context}

---

Question: {question}

Answer:"""

        return self.llm.generate(prompt, system=self.SYSTEM_PROMPT)
```

### Preserving Citation Trails

For academic use, conversation history should preserve which sources were cited:

```python
from dataclasses import dataclass
from datetime import datetime

@dataclass
class ConversationTurn:
    query: str
    response: str
    sources: list[str]  # Citekeys
    timestamp: datetime

# Store in database for persistence
```

---

## 6. MarkdownChunker Implementation

**Source**: `docs/archive/v1_RAG_background/RAG_background/02_embeddings_and_chunking.md`

**Why integrate**: Complete, well-documented chunker that handles academic markdown structure. The v2 reports use LangChain's generic RecursiveCharacterTextSplitter example but don't show markdown-aware chunking.

**Where to integrate**: Add to `embedding_approaches_report.md` or create `chunking_implementation.md`.

### Academic-Specific Considerations

1. **Keep LaTeX blocks atomic**: Never split inside `$$...$$` or `$...$`
2. **Keep code blocks atomic**: Never split inside ```...```
3. **Preserve section metadata**: Store section title with each chunk
4. **Handle citations**: Keep inline citations with their context

### Implementation

```python
from dataclasses import dataclass
import re
import tiktoken

@dataclass
class Chunk:
    text: str
    metadata: dict
    token_count: int
    section_title: str | None = None
    document_id: str | None = None

class MarkdownChunker:
    def __init__(
        self,
        chunk_size: int = 450,
        chunk_overlap: int = 75,
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.tokenizer = tiktoken.encoding_for_model("gpt-4")

    def count_tokens(self, text: str) -> int:
        return len(self.tokenizer.encode(text))

    def chunk_document(self, markdown: str, doc_id: str) -> list[Chunk]:
        sections = self._extract_sections(markdown)
        all_chunks = []

        for section in sections:
            chunks = self._chunk_section(
                section["content"],
                section_title=section["title"],
                document_id=doc_id
            )
            all_chunks.extend(chunks)

        return all_chunks

    def _extract_sections(self, markdown: str) -> list[dict]:
        """Split markdown by headers."""
        pattern = r'^(#{1,4})\s+(.+)$'
        sections = []
        current = {"level": 0, "title": "Document", "content": ""}

        for line in markdown.split('\n'):
            match = re.match(pattern, line)
            if match:
                if current["content"].strip():
                    sections.append(current)
                level = len(match.group(1))
                title = match.group(2)
                current = {"level": level, "title": title, "content": ""}
            else:
                current["content"] += line + "\n"

        if current["content"].strip():
            sections.append(current)

        return sections

    def _chunk_section(
        self,
        text: str,
        section_title: str,
        document_id: str
    ) -> list[Chunk]:
        """Chunk a single section."""
        if self.count_tokens(text) <= self.chunk_size:
            return [Chunk(
                text=text.strip(),
                metadata={"section": section_title},
                token_count=self.count_tokens(text),
                section_title=section_title,
                document_id=document_id
            )]

        # Split by paragraphs first
        paragraphs = text.split('\n\n')
        return self._merge_chunks(paragraphs, section_title, document_id)

    def _merge_chunks(
        self,
        parts: list[str],
        section_title: str,
        document_id: str
    ) -> list[Chunk]:
        """Merge small parts into chunks."""
        chunks = []
        current = ""

        for part in parts:
            test = current + ("\n\n" if current else "") + part
            if self.count_tokens(test) <= self.chunk_size:
                current = test
            else:
                if current:
                    chunks.append(Chunk(
                        text=current.strip(),
                        metadata={"section": section_title},
                        token_count=self.count_tokens(current),
                        section_title=section_title,
                        document_id=document_id
                    ))
                # Overlap: keep last portion
                overlap = self._get_overlap(current)
                current = (overlap + "\n\n" + part) if overlap else part

        if current:
            chunks.append(Chunk(
                text=current.strip(),
                metadata={"section": section_title},
                token_count=self.count_tokens(current),
                section_title=section_title,
                document_id=document_id
            ))

        return chunks

    def _get_overlap(self, text: str) -> str:
        """Get last N tokens for overlap."""
        tokens = self.tokenizer.encode(text)
        if len(tokens) <= self.chunk_overlap:
            return text
        overlap_tokens = tokens[-self.chunk_overlap:]
        return self.tokenizer.decode(overlap_tokens)
```

---

## 7. HybridSearcher and MMR Reranking

**Source**: `docs/archive/v1_RAG_background/RAG_background/03_vector_storage.md`

**Why integrate**: The v2 reports show RRF hybrid search but don't include MMR for diversity. This is important when chunks from a single document dominate results.

**Where to integrate**: Add to `vector_storage_report.md` after the hybrid search section.

### HybridSearcher (with BM25)

```python
from rank_bm25 import BM25Okapi
import numpy as np

class HybridSearcher:
    def __init__(self, vector_store, documents: list[dict]):
        self.vector_store = vector_store
        self.documents = documents

        # Build BM25 index
        tokenized = [doc["text"].lower().split() for doc in documents]
        self.bm25 = BM25Okapi(tokenized)

    def search(
        self,
        query: str,
        query_embedding: list[float],
        k: int = 20,
        alpha: float = 0.5  # Weight: 0=keyword only, 1=vector only
    ) -> list[dict]:
        # Vector search
        vector_results = self.vector_store.query(
            query_embeddings=[query_embedding],
            n_results=k * 2
        )

        # BM25 search
        tokenized_query = query.lower().split()
        bm25_scores = self.bm25.get_scores(tokenized_query)
        bm25_top = np.argsort(bm25_scores)[-k*2:][::-1]

        # Reciprocal Rank Fusion
        scores = {}
        k_rrf = 60

        for rank, doc_id in enumerate(vector_results["ids"][0]):
            scores[doc_id] = scores.get(doc_id, 0) + alpha / (k_rrf + rank)

        for rank, idx in enumerate(bm25_top):
            doc_id = self.documents[idx]["id"]
            scores[doc_id] = scores.get(doc_id, 0) + (1 - alpha) / (k_rrf + rank)

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:k]
        return [{"id": doc_id, "score": score} for doc_id, score in ranked]
```

**Guidance on weighting**: Start with `alpha=0.7` (70% vector, 30% BM25). Tune based on your queries:
- More technical queries → increase BM25 weight
- More conceptual queries → increase vector weight

### MMR (Maximal Marginal Relevance) Reranking

Use when chunks from the same document dominate results:

```python
def mmr_rerank(
    query_embedding: np.ndarray,
    candidates: list[dict],
    k: int = 10,
    lambda_param: float = 0.7  # 1.0=relevance, 0.0=diversity
) -> list[dict]:
    """Re-rank for diversity."""
    selected = []
    remaining = list(range(len(candidates)))

    while len(selected) < k and remaining:
        best_idx = None
        best_score = -float('inf')

        for idx in remaining:
            relevance = cosine_sim(query_embedding, candidates[idx]["embedding"])
            diversity = max(
                cosine_sim(candidates[idx]["embedding"], candidates[s]["embedding"])
                for s in selected
            ) if selected else 0

            score = lambda_param * relevance - (1 - lambda_param) * diversity
            if score > best_score:
                best_score = score
                best_idx = idx

        selected.append(best_idx)
        remaining.remove(best_idx)

    return [candidates[i] for i in selected]
```

---

## 8. EmbeddingSync Class

**Source**: `docs/archive/v1_RAG_background/RAG_background/03_vector_storage.md`

**Why integrate**: Handles incremental re-embedding when documents change. Not covered in v2 reports.

**Where to integrate**: Add to `vector_storage_report.md` or `embedding_approaches_report.md`.

```python
import hashlib

class EmbeddingSync:
    def __init__(self, sqlite_conn, vector_store, embedder):
        self.db = sqlite_conn
        self.vectors = vector_store
        self.embedder = embedder

    def content_hash(self, text: str) -> str:
        return hashlib.sha256(text.encode()).hexdigest()[:16]

    def sync_document(self, document_id: str):
        """Sync embeddings for a document."""
        chunks = self.db.execute('''
            SELECT c.id, c.text, s.content_hash
            FROM chunks c
            LEFT JOIN embedding_sync s ON s.chunk_id = c.id
            WHERE c.document_id = ?
        ''', (document_id,)).fetchall()

        to_update = []
        for chunk in chunks:
            current_hash = self.content_hash(chunk['text'])
            if chunk['content_hash'] != current_hash:
                to_update.append(chunk)

        if to_update:
            texts = [c['text'] for c in to_update]
            embeddings = self.embedder.encode(texts)

            self.vectors.upsert(
                ids=[c['id'] for c in to_update],
                embeddings=embeddings,
                documents=texts
            )

            for chunk in to_update:
                self.db.execute('''
                    INSERT OR REPLACE INTO embedding_sync
                    (chunk_id, content_hash, synced_at)
                    VALUES (?, ?, datetime('now'))
                ''', (chunk['id'], self.content_hash(chunk['text'])))

        self.db.commit()
```

### Required Schema

```sql
CREATE TABLE embedding_sync (
    chunk_id TEXT PRIMARY KEY REFERENCES chunks(id),
    content_hash TEXT,
    synced_at TEXT
);
```

---

## Summary: Integration Priorities

| Content | Priority | Integration Target | Effort |
|---------|----------|-------------------|--------|
| **Evaluation Framework** | High | New doc or Section 7 of summary | 1-2 hours |
| **Risk Assessment Table** | Medium | Section 8 of summary | 30 min |
| **Batch Processing** | High | pdf_extraction or new doc | 1 hour |
| **HyDE Guidance** | Medium | llm_query_interface | 30 min |
| **Conversation Context** | High | llm_query_interface | 1 hour |
| **MarkdownChunker** | High | embedding_approaches | 1 hour |
| **HybridSearcher + MMR** | Medium | vector_storage | 30 min |
| **EmbeddingSync** | Medium | vector_storage or embedding | 30 min |

**Recommended order**: Evaluation Framework → MarkdownChunker → Conversation Context → Batch Processing → (rest as needed)
