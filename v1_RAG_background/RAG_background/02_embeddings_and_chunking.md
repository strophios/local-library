# Embedding Models and Chunking Strategies for Academic RAG

## Executive Summary

For your academic knowledge management system on M1 Pro:

- **Recommended embedding model**: BGE-large-en-v1.5 (best ROI) or GTE-large-en-v1.5 (if long context needed)
- **Chunking strategy**: Markdown-aware recursive chunking, 400-500 tokens, 50-100 token overlap
- **Key insight**: Use query prefixes for retrieval models — this alone can significantly improve results

---

## Embedding Models

### Tier 1: Best Quality (Recommended)

| Model | Dimensions | Context | MTEB Avg | Notes |
|-------|------------|---------|----------|-------|
| **BGE-large-en-v1.5** | 1024 | 512 | 64.23 | Best overall; strong community |
| **GTE-large-en-v1.5** | 1024 | 8192 | 65.39 | Best for long context |
| **mxbai-embed-large-v1** | 1024 | 512 | 64.68 | Matryoshka support |

**Recommendation**: Start with **BGE-large-en-v1.5**. Upgrade to GTE if you need longer context windows.

### Tier 2: Good Balance

| Model | Dimensions | Context | MTEB Avg | Notes |
|-------|------------|---------|----------|-------|
| **Nomic-embed-text-v1.5** | 768 | 8192 | 62.28 | Apache 2.0, Matryoshka |
| **all-mpnet-base-v2** | 768 | 384 | ~60 | Massive adoption |

### Tier 3: Fast/Lightweight

| Model | Dimensions | Context | Notes |
|-------|------------|---------|-------|
| **all-MiniLM-L6-v2** | 384 | 256 | 5x faster, good for prototyping |

### M1 Pro Performance Estimates

| Model | Single Doc | Batch of 32 | Memory |
|-------|------------|-------------|--------|
| all-MiniLM-L6-v2 | ~3ms | ~50ms | ~100MB |
| all-mpnet-base-v2 | ~8ms | ~120ms | ~450MB |
| BGE-large-en-v1.5 | ~15ms | ~250ms | ~1.3GB |

**For 1400 documents × 10 chunks = 14,000 embeddings**:
- BGE-large: ~3-4 minutes total
- Storage: ~56 MB for vectors

### Critical: Query Prefixes

BGE and similar models perform significantly better with query prefixes:

```python
from FlagEmbedding import FlagModel

model = FlagModel(
    'BAAI/bge-large-en-v1.5',
    query_instruction_for_retrieval="Represent this sentence for searching relevant passages:",
    use_fp16=True
)

# Documents: embed WITHOUT prefix
doc_embeddings = model.encode(chunks)

# Queries: embed WITH instruction prefix
query_embedding = model.encode_queries(["your search query"])
```

---

## Chunking Strategies

### Recommended: Markdown-Aware Recursive Chunking

Split by markdown structure, falling back to paragraph/sentence boundaries:

```python
# Priority order for split points
separators = [
    "\n## ",      # H2 headers (major sections)
    "\n### ",     # H3 headers (subsections)
    "\n#### ",    # H4 headers
    "\n\n",       # Paragraph breaks
    "\n",         # Line breaks
    ". ",         # Sentence boundaries
    " ",          # Word boundaries (last resort)
]
```

### Chunk Size Guidelines

| Use Case | Chunk Size | Overlap | Notes |
|----------|------------|---------|-------|
| Precision queries | 256-512 tokens | 50-100 | Find specific facts |
| Nuanced answers | 512-1024 tokens | 100-200 | More context |
| Full sections | 1024-2048 tokens | 200-400 | Comprehensive |

**For BGE-large (512 context)**: Target 400-450 tokens per chunk with 50-100 overlap.

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

## Storage Considerations

| Model | Dimensions | Storage per Vector | 14,000 chunks |
|-------|------------|--------------------|---------------|
| all-MiniLM-L6-v2 | 384 | 1.5 KB | 21 MB |
| all-mpnet-base-v2 | 768 | 3 KB | 42 MB |
| BGE-large-en-v1.5 | 1024 | 4 KB | 56 MB |

At your scale, storage is not a concern. Prioritize quality over compression.

---

## Recommendations

### Easiest Path (Start Here)

1. **Model**: `all-mpnet-base-v2` (no prefix needed, widely adopted)
2. **Chunking**: LangChain's `RecursiveCharacterTextSplitter` (500 tokens, 100 overlap)
3. **Storage**: Chroma (simple API)

```python
from sentence_transformers import SentenceTransformer
from langchain_text_splitters import RecursiveCharacterTextSplitter

model = SentenceTransformer('all-mpnet-base-v2')
splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=100)

chunks = splitter.split_text(document)
embeddings = model.encode(chunks)
```

**Time to implement**: 1-2 hours

### Best ROI (Recommended)

1. **Model**: `BAAI/bge-large-en-v1.5` with query prefixes
2. **Chunking**: Custom MarkdownChunker (code above)
3. **Storage**: sqlite-vss (fits your existing architecture)

**Time to implement**: 3-5 days

### Highest Quality

1. **Model**: `Alibaba-NLP/gte-large-en-v1.5` (8192 context)
2. **Chunking**: Hierarchical (document → section → paragraph)
3. **Storage**: LanceDB with HNSW indexing
4. **Extras**: Cross-encoder reranker, hybrid search

**Time to implement**: 1-2 weeks

---

## Implementation Checklist

```
[ ] Choose embedding model (recommend BGE-large)
[ ] Implement MarkdownChunker class
[ ] Test chunking on sample documents
[ ] Verify chunk sizes and overlap
[ ] Set up embedding pipeline with FlagEmbedding
[ ] Benchmark embedding speed on M1
[ ] Integrate with vector store
[ ] Test retrieval quality on sample queries
```

---

## Open Questions

1. **Section-level embeddings**: Worth storing document/section embeddings alongside chunks for coarse retrieval?
2. **Reference section**: Exclude from embeddings or chunk separately?
3. **Query expansion**: Worth implementing for technical vocabulary?
