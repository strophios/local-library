# Citation Tooling for Academic RAG Workflows

## Executive Summary

This report examines citation-specific tooling built on top of a RAG system for academic knowledge management. The analysis covers five use cases: citation suggestion, real-time autocomplete in Neovim, citation verification, contradiction detection, and bibliography integration.

| Feature | Complexity | Feasibility | Priority |
|---------|------------|-------------|----------|
| Citation Suggestion | Low | Straightforward | 1 |
| Neovim Autocomplete | Medium | Straightforward | 2 |
| HTTP API / CLI | Low | Straightforward | 3 |
| MCP Server | Low | Straightforward | 4 |
| Citation Verification | Medium-High | Needs Validation | 5 |
| Contradiction Detection | High | Research-Grade | 6 |

**Key insight**: Citation suggestion is immediately achievable with standard RAG infrastructure. Verification and contradiction detection require NLI models that may not transfer well to academic text—validate before trusting.

---

## 1. Lessons from Existing Tools

### 1.1 Semantic Scholar

Semantic Scholar provides a production-grade reference for academic paper discovery:

- **Scale**: 225M+ papers with SPECTER2 embeddings available via API
- **Citation Classification**: Background / Methods / Results categories using the [SciCite model](https://medium.com/ai2-blog/citation-intent-classification-bd2bd47559de)
- **"Highly Influential" Detection**: Identifies citations where the cited work significantly impacted methodology or results
- **Rate Limits**: 1 request/second free tier; 10 requests/second with API key

**What to borrow**:
- SPECTER2 embeddings are purpose-built for scientific documents. Consider using them for papers where you can retrieve embeddings via API (DOI lookup), reducing local computation.
- The background/methods/results classification is more nuanced than "supporting/contrasting" and may be more useful for academic workflows.

**Limitations**:
- API-only access means latency (~200-500ms) and rate limits
- Limited to indexed papers—your personal library may have items not in their corpus

### 1.2 scite.ai

scite.ai provides "Smart Citations" with supporting/mentioning/contrasting classification:

- **Training Data**: 40,000+ manually classified citation contexts
- **Scale**: 1.5B+ citation statements analyzed
- **Extraction**: Uses [GROBID](https://github.com/kermitt2/grobid) for PDF structure extraction, then custom deep learning for intent classification
- **Architecture**: GROBID uses BidLSTM-CRF with layout features for document structure, then a separate model classifies citation intent

**What to borrow**:
- The three-category classification (supporting/mentioning/contrasting) maps well to user needs
- GROBID integration is already planned for the RAG system—citation context extraction can piggyback on this

**Limitations**:
- Proprietary; no public model weights
- Classification quality degrades on non-indexed papers

### 1.3 Elicit

Elicit demonstrates a sophisticated multi-stage retrieval architecture:

- **Stage 1**: Custom embedding-based semantic search over 138M papers (Semantic Scholar + PubMed + OpenAlex)
- **Stage 2**: Top 1,000 candidates reranked by LLM for relevance to specific research question
- **Stage 3**: Custom screening questions for further filtering
- **Process-Based Architecture**: Supervised on reasoning process, not just outcomes
- **Accuracy Claims**: 94-99% on data extraction for empirical research

**What to borrow**:
- The two-stage architecture (embedding retrieval → LLM reranking) is practical for local systems
- Sentence-level citation (specific passages, not just documents) improves precision
- "Process-based" supervision via [ICE](https://github.com/oughtinc/ice) is open-source and worth examining

**Limitations**:
- Scale and compute resources far exceed a personal system
- Optimized for empirical research; performance on theoretical/philosophical work is less certain

### 1.4 Consensus

Consensus targets research question answering:

- **Hybrid Search**: Semantic embeddings + BM25 keyword matching
- **Scale**: 220M papers
- **"Consensus Meter"**: Visualizes Yes/No/Mixed for binary research questions
- **GPT-5 Scholar Agent**: Uses advanced LLM for synthesis

**What to borrow**:
- Hybrid search (vector + BM25) consistently outperforms either alone—implement this
- The "consensus meter" concept could be adapted for contradiction detection (though accuracy claims need scrutiny)

### 1.5 Connected Papers and ResearchRabbit

These tools focus on citation network analysis:

- **Bibliographic Coupling**: Papers that cite similar references are likely related
- **Co-citation**: Papers frequently cited together cluster topically
- **Connected Papers**: Analyzes ~50K papers per graph, builds similarity graphs

**What to borrow**:
- For a personal library, citation network features are secondary to semantic search
- However, "papers cited by this paper" and "papers citing this paper" can inform relevance without embeddings

---

## 2. Citation Suggestion Architecture

### 2.1 Query Formulation

Given a sentence or paragraph containing a claim, find papers in your library that could support it.

```python
from dataclasses import dataclass
from typing import Optional

@dataclass
class CitationSuggestion:
    citekey: str
    title: str
    authors_short: str        # "Smith et al."
    year: Optional[int]
    similarity_score: float   # 0.0-1.0, from embedding search
    excerpt: str              # Best matching chunk
    chunk_location: str       # e.g., "Section 3.2, p.7"

    def to_pandoc(self) -> str:
        return f"[@{self.citekey}]"

    def to_latex(self) -> str:
        return f"\\cite{{{self.citekey}}}"

    def to_org(self) -> str:
        return f"[cite:@{self.citekey}]"


class CitationSuggester:
    def __init__(self, embedder, vector_store, document_store):
        self.embedder = embedder
        self.vectors = vector_store
        self.docs = document_store

    def suggest(
        self,
        text: str,
        k: int = 5,
        threshold: float = 0.45,
        mode: str = "default",
        recency_weight: float = 0.0,  # Optional recency bias
    ) -> list[CitationSuggestion]:
        """
        Suggest citations for a text passage.

        Args:
            text: The claim or passage needing citations
            k: Maximum number of suggestions
            threshold: Minimum similarity score (0.0-1.0)
            mode: "strict" (0.65), "default" (0.45), "broad" (0.30)
            recency_weight: Optional weight for newer papers (0.0-0.5)
        """
        thresholds = {"strict": 0.65, "default": 0.45, "broad": 0.30}
        threshold = thresholds.get(mode, threshold)

        # Embed query
        query_embedding = self.embedder.encode(text)

        # Search with over-fetch for deduplication
        results = self.vectors.search(
            query_embedding,
            k=k * 3,
            threshold=threshold,
        )

        # Deduplicate by document, keeping best chunk per document
        seen_docs = {}
        for result in results:
            doc_id = result.metadata["document_id"]
            if doc_id not in seen_docs or result.score > seen_docs[doc_id].score:
                seen_docs[doc_id] = result

        # Sort by score (optionally with recency boost)
        ranked = sorted(seen_docs.values(), key=lambda r: self._rank_score(r, recency_weight), reverse=True)

        # Build suggestions
        suggestions = []
        for result in ranked[:k]:
            doc = self.docs.get(result.metadata["document_id"])
            suggestions.append(CitationSuggestion(
                citekey=doc.citekey,
                title=doc.title,
                authors_short=self._format_authors(doc.csl_json.get("author", [])),
                year=doc.csl_json.get("issued", {}).get("date-parts", [[None]])[0][0],
                similarity_score=result.score,
                excerpt=result.text[:400] + ("..." if len(result.text) > 400 else ""),
                chunk_location=result.metadata.get("section", "Unknown"),
            ))

        return suggestions

    def _format_authors(self, authors: list) -> str:
        if not authors:
            return "Unknown"
        first = authors[0].get("family", authors[0].get("literal", "Unknown"))
        if len(authors) > 2:
            return f"{first} et al."
        elif len(authors) == 2:
            second = authors[1].get("family", "")
            return f"{first} & {second}"
        return first

    def _rank_score(self, result, recency_weight: float) -> float:
        base_score = result.score
        if recency_weight > 0:
            year = result.metadata.get("year", 2000)
            current_year = 2026
            age_factor = max(0, 1 - (current_year - year) / 30)  # Decay over 30 years
            return base_score + recency_weight * age_factor
        return base_score
```

### 2.2 Threshold Calibration

The right threshold depends on your library and use case. Start with defaults and calibrate:

| Mode | Threshold | Expected Behavior |
|------|-----------|-------------------|
| Strict | 0.65 | High confidence; 2-3 results typical |
| Default | 0.45 | Balanced; 4-6 results typical |
| Broad | 0.30 | Discovery mode; 8-10 results, lower precision |

**Calibration procedure**:
1. Take 20 sentences from your own writing with known citations
2. Run suggestion on each, record where the "correct" citation appears in ranking
3. Adjust threshold until correct citation appears in top-k for 80%+ of queries

### 2.3 Two-Stage Reranking (Optional Enhancement)

For higher precision, add LLM-based reranking after embedding retrieval:

```python
def suggest_with_rerank(
    self,
    text: str,
    k: int = 5,
    rerank_k: int = 15,
) -> list[CitationSuggestion]:
    """Two-stage: embedding retrieval → LLM reranking."""

    # Stage 1: Get candidates via embedding
    candidates = self.suggest(text, k=rerank_k, mode="broad")

    if len(candidates) <= k:
        return candidates

    # Stage 2: LLM reranking
    prompt = f"""Given this claim that needs a citation:
"{text}"

Rank these papers by how well they could support the claim (best first):
{self._format_candidates(candidates)}

Return only the numbers of the top {k} papers, comma-separated."""

    response = self.llm.complete(prompt)
    ranked_indices = self._parse_ranking(response.text, k)

    return [candidates[i] for i in ranked_indices if i < len(candidates)]
```

**Cost/benefit**: LLM reranking adds 200-500ms latency and ~$0.001-0.01 per query (Claude Haiku). Worth it for batch operations; skip for real-time autocomplete.

---

## 3. Real-Time Neovim Autocomplete

### 3.1 Latency Requirements

For acceptable autocomplete UX:
- **Target**: <200ms p50, <400ms p99
- **Breakdown**: Daemon overhead (~10ms) + embedding (~30-50ms) + vector search (~20-50ms) + response formatting (~10ms) = ~70-120ms realistic baseline

### 3.2 Architecture

The recommended architecture uses a persistent background daemon communicating via Unix socket:

```
Neovim                          Citation Daemon
┌──────────────┐                ┌─────────────────────┐
│  nvim-cmp    │  Unix Socket   │  Python Process     │
│  source      │◄──────────────►│  /tmp/cite.sock     │
│              │   JSON-RPC     │                     │
│  Trigger: [@ │                │  - BGE model loaded │
│              │                │  - Vector index     │
└──────────────┘                │    memory-mapped    │
                                │  - Query cache      │
                                └─────────────────────┘
```

**Why Unix socket over HTTP?**
- ~10x lower latency (no TCP handshake overhead)
- No port conflicts
- Simpler process lifecycle management

### 3.3 Protocol Design

Request (JSON over Unix socket):
```json
{
    "id": 1,
    "method": "suggest",
    "params": {
        "context": "Neural networks have shown remarkable capabilities in...",
        "cursor_line": "This reduces training time significantly [@",
        "trigger": "[@",
        "limit": 10,
        "mode": "default"
    }
}
```

Response:
```json
{
    "id": 1,
    "result": {
        "items": [
            {
                "citekey": "hinton2012dropout",
                "label": "hinton2012dropout - Dropout: A Simple Way... (2012)",
                "insert_text": "hinton2012dropout",
                "score": 0.72,
                "documentation": "**Hinton et al. (2012)**\n\n> ...dropout prevents complex co-adaptations..."
            }
        ],
        "timing_ms": 85
    }
}
```

### 3.4 Daemon Implementation

```python
#!/usr/bin/env python3
"""Citation suggestion daemon with Unix socket interface."""

import asyncio
import json
import os
from pathlib import Path

from sentence_transformers import SentenceTransformer

SOCKET_PATH = os.environ.get("CITATION_SOCKET", "/tmp/citation-daemon.sock")

class CitationDaemon:
    def __init__(self, suggester):
        self.suggester = suggester
        self.query_cache = {}  # LRU cache for recent queries

    async def handle_client(self, reader, writer):
        try:
            data = await reader.read(4096)
            if not data:
                return

            request = json.loads(data.decode())
            response = await self.process_request(request)

            writer.write(json.dumps(response).encode())
            await writer.drain()
        except Exception as e:
            error_response = {"id": request.get("id"), "error": str(e)}
            writer.write(json.dumps(error_response).encode())
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    async def process_request(self, request):
        method = request.get("method")
        params = request.get("params", {})

        if method == "suggest":
            return await self.handle_suggest(request["id"], params)
        elif method == "health":
            return {"id": request["id"], "result": {"status": "ok"}}
        else:
            return {"id": request["id"], "error": f"Unknown method: {method}"}

    async def handle_suggest(self, request_id, params):
        import time
        start = time.perf_counter()

        # Build context from cursor_line + surrounding context
        context = params.get("context", "")
        cursor_line = params.get("cursor_line", "")

        # Extract text before trigger (the claim needing citation)
        trigger = params.get("trigger", "[@")
        if trigger in cursor_line:
            claim = cursor_line.split(trigger)[0].strip()
        else:
            claim = cursor_line.strip()

        # Use broader context if claim is too short
        if len(claim.split()) < 5:
            claim = context[-500:] if len(context) > 500 else context

        # Check cache
        cache_key = claim[:200]
        if cache_key in self.query_cache:
            items = self.query_cache[cache_key]
        else:
            # Run suggestion (synchronously in thread pool for now)
            suggestions = await asyncio.to_thread(
                self.suggester.suggest,
                claim,
                k=params.get("limit", 10),
                mode=params.get("mode", "default"),
            )

            items = [
                {
                    "citekey": s.citekey,
                    "label": f"{s.citekey} - {s.title[:50]}... ({s.year})",
                    "insert_text": s.citekey,
                    "score": s.similarity_score,
                    "documentation": f"**{s.authors_short} ({s.year})**\n\n> {s.excerpt}",
                }
                for s in suggestions
            ]

            # Cache recent queries (simple LRU)
            if len(self.query_cache) > 100:
                self.query_cache.pop(next(iter(self.query_cache)))
            self.query_cache[cache_key] = items

        elapsed_ms = (time.perf_counter() - start) * 1000

        return {
            "id": request_id,
            "result": {"items": items, "timing_ms": round(elapsed_ms, 1)}
        }

    async def run(self):
        # Clean up stale socket
        socket_path = Path(SOCKET_PATH)
        if socket_path.exists():
            socket_path.unlink()

        server = await asyncio.start_unix_server(
            self.handle_client, path=SOCKET_PATH
        )

        print(f"Citation daemon listening on {SOCKET_PATH}")
        async with server:
            await server.serve_forever()


if __name__ == "__main__":
    # Initialize (do this once at startup)
    from citation_tools import CitationSuggester, load_resources
    embedder, vector_store, doc_store = load_resources()
    suggester = CitationSuggester(embedder, vector_store, doc_store)

    daemon = CitationDaemon(suggester)
    asyncio.run(daemon.run())
```

### 3.5 nvim-cmp Source (Lua)

```lua
-- lua/cmp_citation/init.lua
local source = {}

source.new = function()
    local self = setmetatable({}, { __index = source })
    -- Use XDG_RUNTIME_DIR if available, otherwise /tmp
    local runtime_dir = vim.fn.getenv("XDG_RUNTIME_DIR")
    if runtime_dir == vim.NIL then
        runtime_dir = "/tmp"
    end
    self.socket_path = runtime_dir .. "/citation-daemon.sock"
    return self
end

source.get_keyword_pattern = function()
    -- Match text after [@ or \cite{
    return [[\%(\[@\|\\cite{\)\zs\k*]]
end

source.get_trigger_characters = function()
    return { '@', '{' }
end

source.is_available = function(self)
    -- Check if daemon socket exists
    return vim.fn.filereadable(self.socket_path) == 1
end

source.complete = function(self, params, callback)
    local line = params.context.cursor_before_line

    -- Only trigger on citation patterns
    if not (line:match("%[@[%w_:-]*$") or line:match("\\cite{[%w_:-]*$")) then
        callback({ items = {}, isIncomplete = false })
        return
    end

    -- Get context (surrounding lines)
    local cursor = params.context.cursor
    local buf = vim.api.nvim_get_current_buf()
    local start_line = math.max(0, cursor.row - 5)
    local lines = vim.api.nvim_buf_get_lines(buf, start_line, cursor.row + 1, false)
    local context = table.concat(lines, "\n")

    -- Build request
    local request = vim.fn.json_encode({
        id = os.time(),
        method = "suggest",
        params = {
            context = context,
            cursor_line = line,
            trigger = line:match("\\cite{") and "\\cite{" or "[@",
            limit = 10,
            mode = "default"
        }
    })

    -- Async socket communication using libuv
    local uv = vim.uv or vim.loop
    local client = uv.new_pipe(false)

    client:connect(self.socket_path, function(err)
        if err then
            vim.schedule(function()
                callback({ items = {}, isIncomplete = true })
            end)
            return
        end

        client:write(request)

        client:read_start(function(read_err, data)
            client:close()

            if read_err or not data then
                vim.schedule(function()
                    callback({ items = {}, isIncomplete = true })
                end)
                return
            end

            local ok, response = pcall(vim.fn.json_decode, data)
            if not ok or not response.result then
                vim.schedule(function()
                    callback({ items = {}, isIncomplete = true })
                end)
                return
            end

            -- Convert to nvim-cmp items
            local items = {}
            for _, item in ipairs(response.result.items or {}) do
                table.insert(items, {
                    label = item.label,
                    insertText = item.insert_text,
                    detail = string.format("Score: %.2f", item.score),
                    documentation = {
                        kind = "markdown",
                        value = item.documentation or ""
                    },
                    kind = require("cmp").lsp.CompletionItemKind.Reference
                })
            end

            vim.schedule(function()
                callback({ items = items, isIncomplete = false })
            end)
        end)
    end)
end

return source
```

### 3.6 Setup in Neovim Config

```lua
-- In your nvim-cmp setup
local cmp = require('cmp')

-- Register the citation source
cmp.register_source('citation', require('cmp_citation').new())

cmp.setup({
    sources = cmp.config.sources({
        { name = 'nvim_lsp' },
        { name = 'citation', keyword_length = 0 },  -- Trigger immediately on [@
        { name = 'buffer' },
    }),
})

-- Filetype-specific: prioritize citations in markdown/tex
cmp.setup.filetype({'markdown', 'tex', 'org'}, {
    sources = cmp.config.sources({
        { name = 'citation', priority = 100 },
        { name = 'nvim_lsp' },
        { name = 'buffer' },
    }),
})
```

### 3.7 Performance Optimizations

To achieve <150ms latency consistently:

1. **Keep embedding model in memory**: The daemon loads the model once at startup, not per-request
2. **Memory-map vector index**: sqlite-vss and LanceDB both support memory-mapping
3. **Query embedding cache**: Cache recent query embeddings (they're the slowest part)
4. **Limit context window**: Don't send entire buffer; last 5 lines is usually sufficient
5. **Pre-filter by recency** (optional): If library is >100k chunks, filter to last 5 years first

---

## 4. Citation Verification and Contradiction Detection

### 4.1 The NLI Problem

Citation verification ("does this paper support this claim?") and contradiction detection ("does anything in my library contradict this claim?") require Natural Language Inference (NLI) models.

**The core challenge**: Standard NLI models are trained on crowdsourced data (SNLI, MultiNLI) that differs substantially from academic text:

| Dataset | Domain | Size | Best Model Accuracy |
|---------|--------|------|---------------------|
| SNLI | General (captions) | 570K pairs | ~92% |
| MultiNLI | General (varied) | 433K pairs | ~90% |
| [SciNLI](https://arxiv.org/abs/2203.06728) | NLP/CL papers | 107K pairs | 78% (XLNet) |
| [MSciNLI](https://arxiv.org/abs/2404.08066) | 5 scientific domains | 132K pairs | 77% (PLMs), 52% (LLMs) |

**Key finding**: Even the best models achieve only ~77-78% accuracy on scientific text, compared to 90%+ on general NLI. LLMs perform worse than fine-tuned PLMs on this task.

### 4.2 NLI Model Options

**Recommended for initial experiments**: [cross-encoder/nli-deberta-v3-base](https://huggingface.co/cross-encoder/nli-deberta-v3-base)

- 90.04% accuracy on MultiNLI (general text)
- ~400ms inference on M1 Pro (acceptable for batch, not real-time)
- Apache 2.0 license

**For scientific text specifically**: Consider fine-tuning on SciNLI or MSciNLI before production use.

```python
from transformers import pipeline

class NLIClassifier:
    def __init__(self, model_name: str = "cross-encoder/nli-deberta-v3-base"):
        self.pipeline = pipeline(
            "text-classification",
            model=model_name,
            device="mps",  # Use Metal on M1
        )

    def classify(self, premise: str, hypothesis: str) -> tuple[str, float]:
        """
        Classify entailment relationship.

        Returns:
            (label, confidence) where label is one of:
            - ENTAILMENT: premise supports hypothesis
            - NEUTRAL: no clear relationship
            - CONTRADICTION: premise contradicts hypothesis
        """
        # Cross-encoder format
        result = self.pipeline(
            f"{premise}</s></s>{hypothesis}",
            top_k=1,
        )[0]
        return result["label"], result["score"]
```

### 4.3 Citation Verification Pipeline

```python
from dataclasses import dataclass
from enum import Enum
import re

class SupportLevel(Enum):
    STRONG = "strong"           # High confidence entailment
    MODERATE = "moderate"       # Medium confidence entailment
    WEAK = "weak"               # Low similarity, neutral NLI
    UNSUPPORTED = "unsupported" # Very low similarity
    CONTRADICTED = "contradicted"
    MISSING = "missing"         # Citekey not in library

@dataclass
class VerificationResult:
    citekey: str
    claim: str
    support_level: SupportLevel
    nli_label: str
    nli_confidence: float
    similarity_score: float
    best_evidence: str | None
    notes: str | None


class CitationVerifier:
    """Verify that citations support their claims."""

    # Patterns for extracting citations
    CITATION_PATTERNS = [
        r'\[@([a-zA-Z0-9_:-]+(?:,\s*[a-zA-Z0-9_:-]+)*)\]',  # Pandoc: [@smith2020]
        r'\\cite\{([^}]+)\}',                                # LaTeX: \cite{smith2020}
        r'\[cite:@([a-zA-Z0-9_:-]+)\]',                      # Org: [cite:@smith2020]
    ]

    def __init__(self, embedder, vector_store, document_store, nli_model):
        self.embedder = embedder
        self.vectors = vector_store
        self.docs = document_store
        self.nli = nli_model

    def verify_document(self, text: str) -> list[VerificationResult]:
        """Extract and verify all citations in a document."""
        pairs = self._extract_claim_citation_pairs(text)
        return [self._verify_pair(claim, citekey) for claim, citekey in pairs]

    def _extract_claim_citation_pairs(self, text: str) -> list[tuple[str, str]]:
        """Extract (claim_sentence, citekey) pairs from text."""
        pairs = []

        for pattern in self.CITATION_PATTERNS:
            for match in re.finditer(pattern, text):
                # Get the sentence containing the citation
                start = max(0, text.rfind('.', 0, match.start()) + 1)
                end = text.find('.', match.end())
                if end == -1:
                    end = len(text)

                sentence = text[start:end].strip()

                # Handle multiple citekeys: [@smith2020, jones2021]
                citekeys = [k.strip() for k in match.group(1).split(',')]
                for citekey in citekeys:
                    pairs.append((sentence, citekey))

        return pairs

    def _verify_pair(self, claim: str, citekey: str) -> VerificationResult:
        """Verify a single claim-citation pair."""

        # Get document
        doc = self.docs.get_by_citekey(citekey)
        if not doc:
            return VerificationResult(
                citekey=citekey,
                claim=claim,
                support_level=SupportLevel.MISSING,
                nli_label="N/A",
                nli_confidence=0.0,
                similarity_score=0.0,
                best_evidence=None,
                notes="Citekey not found in library"
            )

        # Find best matching chunks in the cited document
        claim_embedding = self.embedder.encode(claim)
        chunks = self.vectors.search(
            claim_embedding,
            k=5,
            filter={"document_id": doc.id}
        )

        if not chunks:
            return VerificationResult(
                citekey=citekey,
                claim=claim,
                support_level=SupportLevel.UNSUPPORTED,
                nli_label="N/A",
                nli_confidence=0.0,
                similarity_score=0.0,
                best_evidence=None,
                notes="No matching content found in cited document"
            )

        # Run NLI on best matching chunk
        best_chunk = chunks[0]
        nli_label, nli_confidence = self.nli.classify(best_chunk.text, claim)

        # Classify support level
        support_level = self._classify_support(
            nli_label, nli_confidence, best_chunk.score
        )

        return VerificationResult(
            citekey=citekey,
            claim=claim,
            support_level=support_level,
            nli_label=nli_label,
            nli_confidence=nli_confidence,
            similarity_score=best_chunk.score,
            best_evidence=best_chunk.text[:500],
            notes=f"Section: {best_chunk.metadata.get('section', 'Unknown')}"
        )

    def _classify_support(
        self, nli_label: str, nli_conf: float, similarity: float
    ) -> SupportLevel:
        """
        Combine NLI and similarity signals to classify support.

        Conservative approach: high thresholds to avoid false confidence.
        """
        if nli_label == "ENTAILMENT":
            if nli_conf > 0.7 and similarity > 0.5:
                return SupportLevel.STRONG
            elif nli_conf > 0.5:
                return SupportLevel.MODERATE
            else:
                return SupportLevel.WEAK

        elif nli_label == "CONTRADICTION":
            if nli_conf > 0.7:
                return SupportLevel.CONTRADICTED
            else:
                # Low-confidence contradiction could be nuance, not error
                return SupportLevel.WEAK

        else:  # NEUTRAL
            if similarity > 0.5:
                return SupportLevel.WEAK  # Related but not entailing
            else:
                return SupportLevel.UNSUPPORTED
```

### 4.4 Contradiction Detection

```python
class ContradictionDetector:
    """Find papers in library that contradict claims."""

    def __init__(self, embedder, vector_store, nli_model, llm=None):
        self.embedder = embedder
        self.vectors = vector_store
        self.nli = nli_model
        self.llm = llm  # Optional, for claim extraction

    def find_contradictions(
        self,
        claim: str,
        similarity_threshold: float = 0.35,  # Lower to catch more candidates
        contradiction_threshold: float = 0.7,  # High to reduce false positives
        limit: int = 5
    ) -> list[dict]:
        """
        Find passages in library that contradict a claim.

        Two-stage process:
        1. Embedding search finds topically similar passages
        2. NLI filters for actual contradictions
        """
        # Stage 1: Semantic similarity search
        claim_embedding = self.embedder.encode(claim)
        candidates = self.vectors.search(
            claim_embedding,
            k=50,  # Over-fetch for NLI filtering
            threshold=similarity_threshold
        )

        # Stage 2: NLI classification
        contradictions = []
        for chunk in candidates:
            label, confidence = self.nli.classify(chunk.text, claim)

            if label == "CONTRADICTION" and confidence > contradiction_threshold:
                contradictions.append({
                    "claim": claim,
                    "contradicting_text": chunk.text,
                    "citekey": chunk.metadata.get("citekey"),
                    "document_title": chunk.metadata.get("title"),
                    "section": chunk.metadata.get("section"),
                    "confidence": confidence,
                    "similarity": chunk.score,
                })

        # Sort by confidence
        contradictions.sort(key=lambda x: x["confidence"], reverse=True)
        return contradictions[:limit]

    def extract_claims_from_document(self, text: str) -> list[str]:
        """
        Extract verifiable claims from a document.

        Heuristic approach: look for sentences with claim indicators.
        """
        claim_indicators = [
            r'\b(show|demonstrate|find|found|reveal|indicate|suggest)\b',
            r'\b(argue|conclude|establish|prove|confirm)\b',
            r'\b(significant|important|novel|contrary|unlike)\b',
            r'\b(therefore|thus|hence|consequently|as a result)\b',
        ]

        sentences = re.split(r'(?<=[.!?])\s+', text)
        claims = []

        for sentence in sentences:
            sentence = sentence.strip()

            # Skip short sentences and questions
            if len(sentence.split()) < 8 or sentence.endswith('?'):
                continue

            # Check for claim indicators
            for pattern in claim_indicators:
                if re.search(pattern, sentence, re.IGNORECASE):
                    claims.append(sentence)
                    break

        return claims

    def scan_document_for_contradictions(
        self, text: str, max_claims: int = 20
    ) -> list[dict]:
        """
        Scan a document for claims that may be contradicted by library content.
        """
        claims = self.extract_claims_from_document(text)[:max_claims]

        all_contradictions = []
        for claim in claims:
            contradictions = self.find_contradictions(claim, limit=3)
            all_contradictions.extend(contradictions)

        # Deduplicate by citekey
        seen = set()
        unique = []
        for c in all_contradictions:
            key = (c["citekey"], c["claim"][:50])
            if key not in seen:
                seen.add(key)
                unique.append(c)

        return sorted(unique, key=lambda x: x["confidence"], reverse=True)
```

### 4.5 Critical Caveats for Verification/Contradiction

**Do not trust these systems without validation.**

1. **Academic language is hard for NLI**:
   - Hedging ("may suggest", "could potentially")
   - Technical jargon with domain-specific meanings
   - Implicit assumptions and background knowledge
   - SciNLI/MSciNLI show 77-78% accuracy vs 90%+ on general text

2. **Many false positives**:
   - Scope differences: "X works for A" vs "X doesn't work for B" is not contradiction
   - Nuanced disagreement vs. full contradiction
   - Different experimental conditions

3. **Many false negatives**:
   - Paraphrasing: academic writing heavily paraphrases; embedding similarity may be low
   - Indirect support: methodology citations are legitimate but score as "weak"

4. **Recommendation**: Use as a **review aid**, not an automated gate:
   - Flag results for human review
   - Never auto-reject based on these signals
   - Build a validation set (50+ claim-citation pairs with human labels) before trusting

---

## 5. CSL-JSON and Citekey Integration

### 5.1 Citekey Generation

BetterBibTeX-style citekeys are human-readable and stable:

```python
import re
import unicodedata

def generate_citekey(csl_json: dict) -> str:
    """
    Generate BetterBibTeX-style citekey from CSL-JSON.

    Format: authorYEARfirstword
    Examples: smith2020attention, hinton2012dropout
    """
    # Extract first author family name
    authors = csl_json.get("author", [])
    if authors:
        author = authors[0].get("family", authors[0].get("literal", "unknown"))
    else:
        author = "unknown"

    # Normalize author name
    author = unicodedata.normalize("NFD", author)
    author = author.encode("ascii", "ignore").decode()  # Remove diacritics
    author = re.sub(r"[^a-zA-Z]", "", author).lower()

    # Extract year
    issued = csl_json.get("issued", {})
    date_parts = issued.get("date-parts", [[None]])
    year = date_parts[0][0] if date_parts and date_parts[0] else "nodate"

    # Extract first significant word from title
    title = csl_json.get("title", "untitled")
    words = re.findall(r"[a-zA-Z]+", title.lower())
    stopwords = {"a", "an", "the", "of", "in", "on", "for", "to", "and", "or"}
    first_word = next((w for w in words if w not in stopwords), "untitled")

    return f"{author}{year}{first_word}"


def ensure_unique_citekey(citekey: str, existing: set[str]) -> str:
    """Append suffix if citekey already exists."""
    if citekey not in existing:
        return citekey

    suffix = 'a'
    while f"{citekey}{suffix}" in existing:
        suffix = chr(ord(suffix) + 1)

    return f"{citekey}{suffix}"
```

### 5.2 CSL-JSON Formatting for Display

```python
def format_citation_short(csl_json: dict) -> str:
    """Format as 'Smith et al. (2020)'."""
    authors = csl_json.get("author", [])

    if not authors:
        author_str = "Unknown"
    elif len(authors) == 1:
        author_str = authors[0].get("family", "Unknown")
    elif len(authors) == 2:
        author_str = f"{authors[0].get('family', '')} & {authors[1].get('family', '')}"
    else:
        author_str = f"{authors[0].get('family', '')} et al."

    # Year
    issued = csl_json.get("issued", {})
    date_parts = issued.get("date-parts", [[None]])
    year = date_parts[0][0] if date_parts and date_parts[0] else "n.d."

    return f"{author_str} ({year})"


def format_citation_full(csl_json: dict, style: str = "apa") -> str:
    """
    Format full citation using citeproc-py.

    Requires: pip install citeproc-py
    """
    from citeproc import CitationStylesStyle, CitationStylesBibliography
    from citeproc import formatter, Citation, CitationItem
    from citeproc.source.json import CiteProcJSON

    # Load style
    style_path = f"/path/to/csl-styles/{style}.csl"
    bib_style = CitationStylesStyle(style_path)

    # Create bibliography
    bib_source = CiteProcJSON([csl_json])
    bibliography = CitationStylesBibliography(bib_style, bib_source, formatter.plain)

    # Generate
    citation = Citation([CitationItem(csl_json.get("id", "item1"))])
    bibliography.register(citation)

    return str(bibliography.bibliography()[0])
```

### 5.3 Pandoc and LaTeX Output

```python
@dataclass
class FormattedCitation:
    citekey: str

    def to_pandoc(self) -> str:
        """[@citekey]"""
        return f"[@{self.citekey}]"

    def to_pandoc_suppress_author(self) -> str:
        """[-@citekey] for '(2020)' without author"""
        return f"[-@{self.citekey}]"

    def to_pandoc_locator(self, page: str) -> str:
        """[@citekey, p. 42]"""
        return f"[@{self.citekey}, p. {page}]"

    def to_latex(self) -> str:
        """\cite{citekey}"""
        return f"\\cite{{{self.citekey}}}"

    def to_latex_parencite(self) -> str:
        """\parencite{citekey} (biblatex)"""
        return f"\\parencite{{{self.citekey}}}"

    def to_org(self) -> str:
        """[cite:@citekey] (org-cite)"""
        return f"[cite:@{self.citekey}]"
```

---

## 6. API Design

### 6.1 HTTP API (FastAPI)

```python
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional

app = FastAPI(title="Citation Tools API", version="1.0.0")

class SuggestRequest(BaseModel):
    text: str
    limit: int = 5
    mode: str = "default"
    format: str = "json"  # json, pandoc, latex

class VerifyRequest(BaseModel):
    document_path: Optional[str] = None
    document_text: Optional[str] = None

class ContradictionRequest(BaseModel):
    claim: str
    limit: int = 5


@app.post("/suggest")
async def suggest_citations(request: SuggestRequest):
    """Suggest citations for a text passage."""
    suggestions = suggester.suggest(
        text=request.text,
        k=request.limit,
        mode=request.mode
    )

    if request.format == "pandoc":
        return {"citations": [s.to_pandoc() for s in suggestions]}
    elif request.format == "latex":
        return {"citations": [s.to_latex() for s in suggestions]}
    else:
        return {"suggestions": [s.__dict__ for s in suggestions]}


@app.post("/verify")
async def verify_citations(request: VerifyRequest, background_tasks: BackgroundTasks):
    """
    Verify citations in a document (async for large documents).

    Returns a job ID; poll /verify/{job_id} for results.
    """
    if not request.document_path and not request.document_text:
        raise HTTPException(400, "Provide document_path or document_text")

    text = request.document_text
    if request.document_path:
        with open(request.document_path) as f:
            text = f.read()

    job_id = create_job_id()
    background_tasks.add_task(run_verification, job_id, text)

    return {"job_id": job_id, "status": "processing"}


@app.get("/verify/{job_id}")
async def get_verification_status(job_id: str):
    """Get verification job status and results."""
    job = get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job


@app.post("/contradictions")
async def find_contradictions(request: ContradictionRequest):
    """Find papers that contradict a claim."""
    contradictions = detector.find_contradictions(
        claim=request.claim,
        limit=request.limit
    )
    return {"contradictions": contradictions}


@app.get("/health")
async def health():
    return {"status": "ok", "model_loaded": True}
```

### 6.2 CLI (Typer)

```python
#!/usr/bin/env python3
"""Citation workflow CLI."""

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
import json

app = typer.Typer(help="Citation workflow tools")
console = Console()


@app.command()
def suggest(
    text: str = typer.Argument(..., help="Text to find citations for"),
    limit: int = typer.Option(5, "-n", "--limit", help="Max results"),
    mode: str = typer.Option("default", "-m", "--mode",
                             help="strict/default/broad"),
    format: str = typer.Option("table", "-f", "--format",
                               help="table/json/pandoc/latex"),
):
    """Suggest citations for a text passage."""
    suggestions = suggester.suggest(text, k=limit, mode=mode)

    if format == "json":
        console.print_json(data=[s.__dict__ for s in suggestions])
    elif format == "pandoc":
        for s in suggestions:
            console.print(s.to_pandoc())
    elif format == "latex":
        for s in suggestions:
            console.print(s.to_latex())
    else:
        table = Table(title="Citation Suggestions", show_lines=True)
        table.add_column("Citekey", style="cyan", no_wrap=True)
        table.add_column("Reference", max_width=40)
        table.add_column("Score", justify="right", style="green")
        table.add_column("Excerpt", max_width=50)

        for s in suggestions:
            table.add_row(
                s.citekey,
                f"{s.authors_short} ({s.year})\n{s.title[:40]}...",
                f"{s.similarity_score:.2f}",
                s.excerpt[:100] + "..."
            )

        console.print(table)


@app.command()
def verify(
    document: str = typer.Argument(..., help="Path to document"),
    format: str = typer.Option("table", "-f", "--format"),
    only_problems: bool = typer.Option(False, "--problems",
                                        help="Only show weak/unsupported"),
):
    """Verify citations in a document."""
    with console.status("Verifying citations..."):
        with open(document) as f:
            results = verifier.verify_document(f.read())

    if only_problems:
        results = [r for r in results if r.support_level not in
                   {SupportLevel.STRONG, SupportLevel.MODERATE}]

    if format == "json":
        console.print_json(data=[r.__dict__ for r in results])
    else:
        for r in results:
            color = {
                SupportLevel.STRONG: "green",
                SupportLevel.MODERATE: "yellow",
                SupportLevel.WEAK: "orange3",
                SupportLevel.UNSUPPORTED: "red",
                SupportLevel.CONTRADICTED: "red bold",
                SupportLevel.MISSING: "dim",
            }.get(r.support_level, "white")

            console.print(Panel(
                f"[bold]{r.citekey}[/bold]\n\n"
                f"Claim: {r.claim[:100]}...\n\n"
                f"Support: [{color}]{r.support_level.value}[/{color}] "
                f"(NLI: {r.nli_label} @ {r.nli_confidence:.2f})\n\n"
                f"Evidence: {r.best_evidence[:200] if r.best_evidence else 'N/A'}...",
                title=r.support_level.value.upper(),
            ))


@app.command()
def contradictions(
    claim: str = typer.Argument(..., help="Claim to check"),
    limit: int = typer.Option(5, "-n", "--limit"),
):
    """Find papers that contradict a claim."""
    with console.status("Searching for contradictions..."):
        results = detector.find_contradictions(claim, limit=limit)

    if not results:
        console.print("[green]No contradictions found.[/green]")
        return

    console.print(f"[yellow]Found {len(results)} potential contradictions:[/yellow]\n")

    for i, r in enumerate(results, 1):
        console.print(Panel(
            f"[bold cyan]{r['citekey']}[/bold cyan]\n\n"
            f"Confidence: {r['confidence']:.2f}\n\n"
            f"Text: {r['contradicting_text'][:300]}...",
            title=f"Contradiction {i}",
        ))


if __name__ == "__main__":
    app()
```

### 6.3 MCP Server

For LLM agent access (e.g., Claude):

```python
from mcp import Server, Tool

server = Server("citation-tools")


@server.tool()
async def suggest_citations(text: str, limit: int = 5) -> list[dict]:
    """
    Find papers in the library that could support a claim.

    Args:
        text: The claim or passage needing citations
        limit: Maximum number of suggestions (default 5)

    Returns:
        List of citation suggestions with citekeys, scores, and excerpts
    """
    suggestions = suggester.suggest(text, k=limit)
    return [
        {
            "citekey": s.citekey,
            "reference": f"{s.authors_short} ({s.year})",
            "title": s.title,
            "score": s.similarity_score,
            "excerpt": s.excerpt,
            "pandoc": s.to_pandoc(),
        }
        for s in suggestions
    ]


@server.tool()
async def verify_citation(claim: str, citekey: str) -> dict:
    """
    Check if a specific citation supports a claim.

    Args:
        claim: The claim being made
        citekey: The citekey of the cited paper

    Returns:
        Verification result with support level and evidence
    """
    result = verifier._verify_pair(claim, citekey)
    return {
        "support_level": result.support_level.value,
        "nli_label": result.nli_label,
        "nli_confidence": result.nli_confidence,
        "similarity": result.similarity_score,
        "evidence": result.best_evidence,
        "notes": result.notes,
    }


@server.tool()
async def find_contradicting_sources(claim: str, limit: int = 3) -> list[dict]:
    """
    Find papers in the library that might contradict a claim.

    Args:
        claim: The claim to check for contradictions
        limit: Maximum contradictions to return (default 3)

    Returns:
        List of potentially contradicting sources with confidence scores
    """
    contradictions = detector.find_contradictions(claim, limit=limit)
    return contradictions


@server.tool()
async def lookup_paper(citekey: str) -> dict | None:
    """
    Look up a paper by citekey.

    Args:
        citekey: The citekey to look up

    Returns:
        Paper metadata (CSL-JSON) or None if not found
    """
    doc = document_store.get_by_citekey(citekey)
    if not doc:
        return None
    return {
        "citekey": doc.citekey,
        "csl_json": doc.csl_json,
        "short_citation": format_citation_short(doc.csl_json),
    }
```

---

## 7. Implementation Feasibility Assessment

### 7.1 Straightforward to Build (Weeks)

| Feature | Effort | Dependencies |
|---------|--------|--------------|
| **Citation Suggestion** | 2-3 days | Existing RAG infrastructure |
| **CLI** | 1 day | typer, rich |
| **HTTP API** | 1 day | FastAPI |
| **MCP Server** | 1 day | mcp library |
| **Neovim daemon** | 2-3 days | asyncio, socket knowledge |
| **nvim-cmp source** | 1-2 days | Lua, nvim-cmp API |
| **Citekey generation** | Few hours | Pure Python |

**Total for MVP (suggestion + CLI + Neovim)**: ~1-2 weeks

### 7.2 Requires Significant Validation (Weeks to Months)

| Feature | Challenge | Effort |
|---------|-----------|--------|
| **Citation Verification** | NLI accuracy on academic text unknown | 2-4 weeks to validate |
| **Contradiction Detection** | High false positive rate expected | 2-4 weeks to validate |
| **Claim Extraction** | Heuristics work poorly; LLM needed | 1-2 weeks |

**Validation approach**:
1. Build test set: 50-100 claim-citation pairs with human labels
2. Run verification system, compute accuracy
3. Only proceed if accuracy > 75% on your test set
4. Consider fine-tuning on SciNLI/MSciNLI if accuracy is poor

### 7.3 Probably Out of Scope (Months+)

| Feature | Why Out of Scope |
|---------|------------------|
| **Training custom NLI for your domain** | Requires labeled data, ML expertise, compute |
| **Citation intent classification (background/methods/results)** | Needs training data; use Semantic Scholar API instead |
| **Cross-document reasoning** | Research-grade problem; current systems don't do this well |
| **Automated bibliography generation** | citeproc-py handles this; building custom is unnecessary |

---

## 8. Recommendations

### 8.1 Easiest Path (MVP Citation Features) — 1-2 Weeks

Build citation suggestion with CLI and Neovim integration. Skip verification.

**What you get**:
- Type `[@` in Neovim, get relevant papers from your library
- CLI for batch citation suggestions
- Low risk, immediate value

**Stack**:
```
Citation Suggester (Python)
├── Uses existing embeddings + vector store
├── Threshold-based filtering (0.45 default)
└── Output: citekeys, scores, excerpts

Daemon (Unix socket)
├── Keeps model loaded
├── Simple JSON protocol
└── ~100ms latency

nvim-cmp source (Lua)
├── Triggers on [@
├── Async socket client
└── Formats for completion menu
```

**Skip**: Verification, contradiction detection (validate later)

### 8.2 Best Quality (Full Academic Workflow) — 6-10 Weeks

If you need verification and contradiction detection, invest in validation first.

**Phase 1** (Weeks 1-2): MVP from above

**Phase 2** (Weeks 3-4): Verification validation
- Build test set: 100 claim-citation pairs from your own papers
- Human-label support levels
- Run verification system, measure accuracy
- If accuracy < 75%, stop here or fine-tune

**Phase 3** (Weeks 5-6): Contradiction detection
- Only proceed if verification accuracy is acceptable
- Extract claims from manuscript → find contradictions
- High false positive rate expected; tune thresholds

**Phase 4** (Weeks 7-8): Integration polish
- Two-stage reranking (embedding → LLM)
- SPECTER2 integration for papers with DOIs
- Full API surface

**Risks**:
- NLI accuracy may be unacceptable on academic text
- Contradiction detection may have too many false positives to be useful
- Timeline may expand to 10-12 weeks

### 8.3 Optimal ROI

**Recommendation**: Start with MVP, add verification only if needed.

Citation suggestion alone solves the most common use case: "I need a citation here, what do I have?" This is 80% of the value for 20% of the effort.

Verification and contradiction detection sound valuable but:
- Require significant validation work
- May not work well on your documents
- False positives erode trust

**If you do proceed with verification**:
1. Build the validation test set first (1-2 days)
2. Evaluate baseline accuracy
3. Make an informed decision based on actual numbers

---

## 9. Open Research Questions

### 9.1 NLI for Academic Text

**Question**: How well do standard NLI models (trained on SNLI/MultiNLI) perform on academic text?

**Known data**:
- SciNLI/MSciNLI show 77-78% accuracy vs 90%+ on general text
- LLMs perform worse than fine-tuned PLMs on scientific NLI
- Domain shift significantly degrades performance

**What's needed**:
- Validation on *your* documents specifically
- Consider fine-tuning on SciNLI if accuracy is poor
- May need domain-specific model (no good off-the-shelf options)

### 9.2 Claim Extraction

**Question**: How to reliably extract verifiable claims from academic text?

**Options**:
1. **Heuristics**: Look for claim indicators ("we show", "results demonstrate")
   - Fast, no API cost
   - Misses implicit claims, false positives on hedged statements
2. **LLM extraction**: "Extract claims from this paragraph"
   - Better recall
   - Slow (~1s per paragraph), API costs

**Open issue**: No good benchmark for claim extraction in academic text

### 9.3 Handling Nuanced Disagreement

**Question**: How to distinguish full contradiction from nuanced disagreement?

**Example**:
- Claim: "Transformers outperform RNNs on NLP tasks"
- Source 1: "RNNs remain competitive on low-resource tasks" — not a contradiction
- Source 2: "Transformers fail to generalize on our benchmark" — partial contradiction?
- Source 3: "The attention mechanism provides no benefit over averaging" — strong contradiction

Current NLI models treat all three similarly. This may require:
- Multi-turn LLM reasoning
- Scope-aware entailment
- Domain-specific fine-tuning

### 9.4 User Feedback Loop

**Question**: How to improve suggestions based on which citations users actually use?

**Sketch**:
```python
# Track which suggestions user accepts
if user_selects(suggestion):
    feedback_store.record(
        query=original_query,
        selected_citekey=suggestion.citekey,
        alternatives=[s.citekey for s in other_suggestions]
    )

# Periodically retrain or adjust
# - Weight documents by selection frequency
# - Fine-tune embedding model on (query, selected_doc) pairs
# - Adjust threshold based on acceptance rate
```

**Challenge**: Requires enough usage data to be meaningful (~100+ selections)

---

## 10. Implementation Checklist

```
Phase 1: MVP (1-2 weeks)
[ ] Citation Suggestion
    [ ] CitationSuggester class
    [ ] Threshold calibration on 20 sample queries
    [ ] CSL-JSON integration for author/year formatting

[ ] CLI
    [ ] suggest command with table/json/pandoc output
    [ ] Test on real manuscript

[ ] Neovim Integration
    [ ] Citation daemon (Unix socket, JSON protocol)
    [ ] nvim-cmp source (Lua)
    [ ] Measure latency (<200ms p50)
    [ ] Test in actual writing session

Phase 2: Validation (2-4 weeks, if proceeding)
[ ] Verification Validation
    [ ] Build test set: 100 claim-citation pairs
    [ ] Human-label support levels
    [ ] Run CitationVerifier
    [ ] Compute accuracy metrics
    [ ] Decision: proceed or stop

[ ] If proceeding:
    [ ] Tune thresholds based on validation
    [ ] Add to CLI (verify command)
    [ ] Add to API

Phase 3: Full Stack (2-4 weeks, if proceeding)
[ ] Contradiction Detection
    [ ] ContradictionDetector class
    [ ] Validate on test claims
    [ ] Tune false positive rate

[ ] HTTP API
    [ ] FastAPI endpoints
    [ ] Background job processing for large docs

[ ] MCP Server
    [ ] Tool definitions
    [ ] Test with Claude

[ ] Integration Polish
    [ ] Two-stage reranking
    [ ] SPECTER2 for DOI lookup
    [ ] Citeproc formatting
```

---

## References and Sources

- [SciNLI: A Corpus for Natural Language Inference on Scientific Text](https://arxiv.org/abs/2203.06728) - ACL 2022
- [MSciNLI: A Diverse Benchmark for Scientific Natural Language Inference](https://arxiv.org/abs/2404.08066) - 2024
- [cross-encoder/nli-deberta-v3-base](https://huggingface.co/cross-encoder/nli-deberta-v3-base) - Hugging Face
- [Semantic Scholar API](https://www.semanticscholar.org/product/api)
- [SPECTER2](https://huggingface.co/allenai/specter2) - Scientific document embeddings
- [GROBID](https://github.com/kermitt2/grobid) - PDF structure extraction
- [scite.ai Smart Citations](https://scite.ai/reports/scite-a-smart-citation-index-keppkgL5) - Citation classification
- [Elicit](https://elicit.com/) - Process-based ML for research
- [nvim-cmp](https://github.com/hrsh7th/nvim-cmp) - Neovim completion engine
- [Neovim luv/libuv documentation](https://neovim.io/doc/user/luvref.html)
- [Lost in Inference: Rediscovering NLI for LLMs](https://aclanthology.org/2025.naacl-long.466/) - NAACL 2025
