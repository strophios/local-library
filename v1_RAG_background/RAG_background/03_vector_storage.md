# Vector Database and Embedding Storage for RAG

## Executive Summary

For your academic knowledge management system at 50k-500k vector scale on M1 Mac:

| Solution | Best For | Memory | Performance |
|----------|----------|--------|-------------|
| **LanceDB** | Best overall balance | Low (~150MB) | Fast (~3ms queries) |
| **Chroma** | Best developer experience | Moderate (~400MB) | Fast (~5ms queries) |
| **sqlite-vss** | Simplest integration | Low (~100MB) | Moderate (~50ms queries) |

**Recommendation**: Start with **LanceDB** if you want best performance, or **sqlite-vss** if you prioritize single-file simplicity and can accept slower queries.

---

## Detailed Analysis

### LanceDB

**What it is**: Columnar vector database using the Lance format, designed for ML workloads.

| Aspect | Assessment |
|--------|------------|
| Performance at 100k-500k vectors | Excellent |
| Memory footprint | Low (memory-mapped) |
| Filtering | SQL-like syntax |
| M1 Mac compatibility | Excellent |
| Python bindings | Good |
| Persistence | Native (directory-based) |
| Maintenance | Active development |

**Strengths**:
- Memory-mapped architecture keeps footprint low
- Native versioning for backup/rollback
- Works well with DuckDB for unified queries
- Actively maintained

**Concerns raised in review**:
- Memory claims need clarification: "150MB" may exclude vector data itself
- Verify on your actual embedding dimensions

```python
import lancedb
from lancedb.pydantic import LanceModel, Vector

class ChunkModel(LanceModel):
    id: str
    text: str
    document_id: str
    section_title: str
    embedding: Vector(1024)  # BGE-large dimensions

db = lancedb.connect("./data/vectors")
table = db.create_table("chunks", schema=ChunkModel)

# Insert
table.add([
    ChunkModel(
        id="chunk_001",
        text="...",
        document_id="doc_123",
        section_title="Introduction",
        embedding=embedding_vector
    )
])

# Query with filter
results = table.search(query_embedding).where("document_id = 'doc_123'").limit(10)
```

### Chroma

**What it is**: Open-source embedding database with focus on developer experience.

| Aspect | Assessment |
|--------|------------|
| Performance at 100k-500k vectors | Very good |
| Memory footprint | Moderate (~400MB at 100k) |
| Filtering | Good metadata filtering |
| M1 Mac compatibility | Excellent |
| Python bindings | Excellent (cleanest API) |
| Persistence | Directory-based |
| Maintenance | Active |

**Strengths**:
- Cleanest Python API
- Good documentation
- Built-in document/metadata management
- Easy to get started

```python
import chromadb

client = chromadb.PersistentClient(path="./chroma_db")
collection = client.get_or_create_collection("chunks")

# Insert
collection.add(
    ids=["chunk_001"],
    documents=["chunk text..."],
    metadatas=[{"document_id": "doc_123", "section": "Introduction"}],
    embeddings=[embedding_vector]
)

# Query with filter
results = collection.query(
    query_embeddings=[query_embedding],
    n_results=10,
    where={"document_id": "doc_123"}
)
```

### sqlite-vss

**What it is**: SQLite extension for vector similarity search.

| Aspect | Assessment |
|--------|------------|
| Performance at 100k vectors | Good (~50ms queries) |
| Performance at 200k+ vectors | Degrades without HNSW |
| Memory footprint | Low |
| Filtering | Native SQL |
| Integration | Single file with main DB |
| Maintenance | Active |

**Strengths**:
- Single database file (simpler backup/restore)
- Native SQL filtering
- Transactional consistency with metadata
- Fits your existing SQLite architecture

**Weaknesses**:
- Slower queries than alternatives
- Performance degrades above ~200k vectors without HNSW indexing
- Less featureful API

**Important clarification**: Modern sqlite-vss supports HNSW indexing. With proper configuration, it handles 200k+ vectors acceptably. The real ceiling is system RAM, not database format.

```sql
-- Schema
CREATE VIRTUAL TABLE chunks_vss USING vss0(
    embedding(1024)  -- BGE-large dimensions
);

CREATE TABLE chunks (
    id TEXT PRIMARY KEY,
    text TEXT,
    document_id TEXT,
    section_title TEXT,
    rowid INTEGER
);

-- Query
SELECT c.* FROM chunks c
JOIN chunks_vss v ON c.rowid = v.rowid
WHERE vss_search(v.embedding, :query_embedding)
LIMIT 10;
```

---

## Indexing Strategies

### At Your Scale (100k-500k vectors)

| Strategy | When to Use | Memory Impact |
|----------|-------------|---------------|
| **Flat** | <50k vectors, need exact results | O(n * d) |
| **HNSW** | 50k+ vectors, prioritize speed | O(n * (d + M)) |
| **IVF** | 100k+ vectors, can trade accuracy | Lower than HNSW |

**Recommendation**: Use HNSW for best query performance. At your scale, memory is manageable.

### HNSW Configuration

```python
# Recommended for 100k-500k vectors
hnsw_config = {
    "M": 16,               # Edges per node (16-64 typical)
    "ef_construction": 200, # Build quality (higher = better graph)
    "ef_search": 100,       # Query quality (tune based on latency needs)
    "metric": "cosine"      # For normalized embeddings
}
```

**Memory estimate**:
- 100k vectors × 1024 dimensions × 4 bytes = ~400 MB (vectors alone)
- HNSW overhead: ~10-20% additional
- Total: ~450-500 MB at 100k vectors

---

## Search Implementation

### Pure Vector Search

```python
def vector_search(query_embedding: list[float], k: int = 20) -> list[dict]:
    """Basic semantic search."""
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=k,
        include=["documents", "metadatas", "distances"]
    )
    return [
        {
            "text": doc,
            "metadata": meta,
            "score": 1 - dist  # Convert distance to similarity
        }
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0]
        )
    ]
```

### Hybrid Search (Vector + BM25)

Combining semantic and keyword search often improves results, especially for:
- Queries with rare technical terms
- Exact phrase matching
- Domain-specific vocabulary

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

### MMR (Maximal Marginal Relevance)

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

### Cross-Encoder Re-ranking

For highest quality, re-rank top candidates with a cross-encoder:

```python
from sentence_transformers import CrossEncoder

class ReRanker:
    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"):
        self.model = CrossEncoder(model_name)

    def rerank(self, query: str, candidates: list[dict], k: int = 10) -> list[dict]:
        pairs = [(query, c["text"]) for c in candidates]
        scores = self.model.predict(pairs)

        ranked = sorted(zip(candidates, scores), key=lambda x: x[1], reverse=True)
        return [doc for doc, _ in ranked[:k]]
```

---

## Schema Design

Keep metadata in SQLite (source of truth), vectors in vector store:

```sql
-- SQLite schema
CREATE TABLE documents (
    id TEXT PRIMARY KEY,
    citekey TEXT UNIQUE,
    title TEXT,
    authors TEXT,  -- JSON array
    pub_date TEXT,
    tags TEXT,     -- JSON array
    csl_json TEXT,
    content_path TEXT,
    content_hash TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE chunks (
    id TEXT PRIMARY KEY,
    document_id TEXT REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index INTEGER,
    text TEXT,
    section_title TEXT,
    char_start INTEGER,
    char_end INTEGER,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX idx_chunks_document ON chunks(document_id);

-- Sync tracking
CREATE TABLE embedding_sync (
    chunk_id TEXT PRIMARY KEY REFERENCES chunks(id),
    content_hash TEXT,
    synced_at TEXT
);
```

### Sync Strategy

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

---

## Recommendations

### For Your Use Case

Given:
- ~50k-500k vectors eventually
- Local-first on M1 Mac
- SQLite for metadata
- Python implementation

**Option A: LanceDB (Recommended if performance matters)**
- Best query performance
- Low memory footprint
- Good filtering
- Active development

**Option B: sqlite-vss (Recommended for simplicity)**
- Single file with metadata
- Native SQL filtering
- Simpler backup/restore
- Accept ~50ms query latency

**Option C: Chroma (Recommended for rapid development)**
- Cleanest API
- Best documentation
- Good enough performance

### Performance Expectations on M1

| Solution | Query (100k vectors) | Memory |
|----------|----------------------|--------|
| sqlite-vss | ~50ms | ~100MB |
| Chroma | ~5ms | ~400MB |
| LanceDB | ~3ms | ~150MB |

*Note: These are approximate. Actual performance depends on embedding dimensions, query complexity, and filtering.*

---

## Implementation Checklist

```
[ ] Choose vector store (recommend LanceDB or sqlite-vss)
[ ] Set up schema (SQLite tables + vector index)
[ ] Implement EmbeddingSync class
[ ] Test insert/query performance on sample data
[ ] Implement backup/restore strategy
[ ] Add hybrid search (optional but recommended)
[ ] Test at target scale (100k vectors)
```

---

## Alternatives Not Selected

- **Qdrant**: Good option if you need more sophisticated filtering; heavier than LanceDB
- **Milvus**: Overkill for personal use; better for team/production
- **FAISS**: No metadata filtering; requires custom wrapper
- **Pinecone/Weaviate Cloud**: Unnecessary cost and latency for local system
