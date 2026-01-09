# LLM Query Interface Design for RAG Systems

A comprehensive analysis of frameworks, patterns, and architectural decisions for building an LLM-agnostic query interface in a personal knowledge management system.

---

## Table of Contents

1. [Framework Landscape and Philosophy](#framework-landscape-and-philosophy)
2. [Deep Dive: Major Framework Options](#deep-dive-major-framework-options)
3. [RAG Query Patterns](#rag-query-patterns)
4. [Context Assembly Strategies](#context-assembly-strategies)
5. [LLM Abstraction Layer Design](#llm-abstraction-layer-design)
6. [Build vs Buy Analysis](#build-vs-buy-analysis)
7. [Recommendations](#recommendations)
8. [Common Pitfalls and Lock-in Risks](#common-pitfalls-and-lock-in-risks)

---

## Framework Landscape and Philosophy

The 2025 LLM framework ecosystem has stratified into distinct tiers based on abstraction level and intended use case:

### Tier 1: Model Gateways (Unified API Layer)
- **LiteLLM**, **aisuite**, **AbstractCore**
- Philosophy: Standardize LLM communication, abstract provider differences
- Value: Provider-agnostic calls, model routing, fallbacks
- Overhead: Minimal (~3-5ms latency added)

### Tier 2: RAG/Retrieval Frameworks
- **LlamaIndex**, **Haystack**
- Philosophy: Optimize the retrieval-to-generation pipeline
- Value: Indexing, chunking, query engines, production-ready pipelines
- Overhead: Moderate (~5-6ms)

### Tier 3: Orchestration Frameworks
- **LangChain**, **LangGraph**
- Philosophy: Flexible composition of LLM-powered workflows
- Value: Rapid prototyping, agent orchestration, tool integration
- Overhead: Higher (~10-14ms)

### Tier 4: Optimization Frameworks
- **DSPy**
- Philosophy: Program (don't prompt) LLMs; optimize systematically
- Value: Automatic prompt optimization, reproducibility
- Overhead: Lowest (~3.5ms)

### Key Insight

These tiers are **complementary, not competitive**. A production system might use:
- LiteLLM as the provider gateway
- LlamaIndex for retrieval logic
- DSPy signatures for prompt optimization
- Custom FastAPI for the application layer

The question isn't "which framework" but "which combination at what abstraction level."

---

## Deep Dive: Major Framework Options

### LlamaIndex

**Philosophy**: RAG-first framework optimized for connecting LLMs to data.

**Strengths**:
- Best-in-class indexing and chunking strategies
- 35% retrieval accuracy improvement over baseline in benchmarks
- 0.8s average query time vs 1.2s for LangChain
- CitationQueryEngine for inline source attribution
- Over 300 integration packages

**Custom LLM Integration**:
```python
from llama_index.core.llms import CustomLLM, CompletionResponse, LLMMetadata

class MyLLM(CustomLLM):
    context_window: int = 8192
    num_output: int = 1024
    model_name: str = "my-model"

    @property
    def metadata(self) -> LLMMetadata:
        return LLMMetadata(
            context_window=self.context_window,
            num_output=self.num_output,
            model_name=self.model_name,
        )

    def complete(self, prompt: str, **kwargs) -> CompletionResponse:
        # Your implementation here
        return CompletionResponse(text=response_text)

    def stream_complete(self, prompt: str, **kwargs):
        # Streaming implementation
        yield CompletionResponse(text=token, delta=token)
```

**For This Project**: Strong candidate for the retrieval layer. The CitationQueryEngine directly addresses the need for source attribution in academic document RAG.

---

### Haystack

**Philosophy**: Production-first, typed pipeline architecture with DAG-based component composition.

**Strengths**:
- Used by Apple and Meta in production
- Type-validated component connections (catches errors at pipeline construction)
- Native async pipeline support for high-throughput deployment
- Clean separation between indexing and querying pipelines
- Hayhooks for RESTful API deployment

**Custom Component Pattern**:
```python
from haystack import component
from haystack.dataclasses import ChatMessage

@component
class CustomGenerator:
    def __init__(self, model_name: str):
        self.model_name = model_name

    @component.output_types(replies=list[ChatMessage])
    def run(self, messages: list[ChatMessage]) -> dict:
        # Your LLM call here
        return {"replies": [ChatMessage.from_assistant(response)]}
```

**Pipeline Composition**:
```python
from haystack import Pipeline

pipeline = Pipeline()
pipeline.add_component("retriever", my_retriever)
pipeline.add_component("generator", CustomGenerator(model_name="claude-sonnet-4-5"))
pipeline.connect("retriever.documents", "generator.documents")
```

**For This Project**: Excellent choice if you want production-ready infrastructure with strong typing. The component model integrates cleanly with a larger system architecture.

---

### LangChain

**Philosophy**: Maximum flexibility and rapid prototyping through composable chains.

**Strengths**:
- Largest ecosystem and community
- Fastest path to a working prototype
- Extensive tool/agent support
- Good documentation and examples

**Weaknesses**:
- Highest overhead (~10ms latency)
- Highest token usage (~2.4k in benchmarks)
- Abstraction leakage in complex use cases
- Rapid API changes (migration burden)

**For This Project**: Useful for initial prototyping but not recommended for the core interface. The overhead and token usage are concerning for a system prioritizing efficiency.

---

### DSPy

**Philosophy**: Replace prompt engineering with programming. Signatures define I/O; optimizers tune prompts automatically.

**Strengths**:
- Lowest overhead (~3.5ms)
- Prompt optimization can improve F1 from 57% to 77%
- Reproducible, testable prompt development
- Clean separation of logic from prompt details

**Signature-Based Approach**:
```python
import dspy

class RAGAnswer(dspy.Signature):
    """Answer questions based on retrieved context."""
    context: str = dspy.InputField(desc="relevant passages")
    question: str = dspy.InputField()
    answer: str = dspy.OutputField(desc="concise answer with citations")

class RAGModule(dspy.Module):
    def __init__(self):
        self.generate = dspy.ChainOfThought(RAGAnswer)

    def forward(self, question, context):
        return self.generate(question=question, context=context)
```

**For This Project**: Compelling for the generation step. The signature-based approach provides clean interfaces that integrate well with typed systems. Consider using DSPy for prompt management while using other tools for retrieval.

---

### LiteLLM

**Philosophy**: Universal LLM gateway—one API for 100+ providers.

**Strengths**:
- OpenAI-compatible API for all providers
- Built-in fallbacks, load balancing, rate limiting
- Cost tracking and usage monitoring
- Self-hostable proxy server

**Basic Usage**:
```python
from litellm import completion

# Claude
response = completion(
    model="claude-sonnet-4-5",
    messages=[{"role": "user", "content": "Hello"}]
)

# OpenAI
response = completion(
    model="gpt-4.1",
    messages=[{"role": "user", "content": "Hello"}]
)

# Ollama (local)
response = completion(
    model="ollama/llama3",
    messages=[{"role": "user", "content": "Hello"}]
)
```

**Production Considerations**: Reports of performance degradation at scale—"54x slower p99 latency" in some benchmarks compared to specialized alternatives. For a personal knowledge management system, this is unlikely to be an issue.

**For This Project**: Strong candidate for the provider abstraction layer. Provides the LLM-agnostic requirement with minimal code.

---

## RAG Query Patterns

### Multi-Query Retrieval

**Problem**: User queries are often ambiguous or could be phrased multiple ways. Single-query retrieval misses relevant documents due to vocabulary mismatch.

**Solution**: Generate multiple query variations and combine results.

```python
def multi_query_retrieve(original_query: str, retriever, llm) -> list[Document]:
    """Generate query variations and combine results."""

    # Generate variations
    expansion_prompt = f"""Generate 3 alternative phrasings of this query
    that might retrieve different relevant documents:
    Query: {original_query}

    Return as a JSON list of strings."""

    variations = llm.generate(expansion_prompt)
    all_queries = [original_query] + json.loads(variations)

    # Retrieve for each
    all_docs = []
    for query in all_queries:
        docs = retriever.retrieve(query)
        all_docs.extend(docs)

    # Deduplicate and re-rank (reciprocal rank fusion)
    return reciprocal_rank_fusion(all_docs)
```

**Frameworks**:
- Haystack: `QueryExpander` component
- LlamaIndex: `SubQuestionQueryEngine`
- Research: DMQR-RAG, RAG-Fusion, RQ-RAG

---

### Context Compression

**Problem**: Retrieved chunks often contain redundant or irrelevant information, wasting token budget.

**Solution**: Compress or filter context before generation.

```python
def compress_context(chunks: list[str], query: str, budget: int) -> str:
    """Compress retrieved chunks to fit token budget."""

    # Score relevance of each sentence
    scored_sentences = []
    for chunk in chunks:
        for sentence in split_sentences(chunk):
            score = semantic_similarity(sentence, query)
            scored_sentences.append((sentence, score))

    # Greedy selection with redundancy penalty (AdaGReS-style)
    selected = []
    current_tokens = 0

    for sentence, score in sorted(scored_sentences, key=lambda x: -x[1]):
        # Penalize if too similar to already-selected
        redundancy_penalty = max(
            semantic_similarity(sentence, s) for s in selected
        ) if selected else 0

        adjusted_score = score - (0.5 * redundancy_penalty)

        sentence_tokens = count_tokens(sentence)
        if current_tokens + sentence_tokens <= budget and adjusted_score > 0.3:
            selected.append(sentence)
            current_tokens += sentence_tokens

    return " ".join(selected)
```

**Key Techniques**:
- Semantic chunking over static splitting (85% lower token consumption reported)
- Redundancy-aware selection (AdaGReS framework)
- LLM-based summarization for very long contexts
- Embedding-based filtering with similarity thresholds

---

### Citation Generation

**Problem**: RAG responses need verifiable source attribution for credibility.

**Two Approaches**:

1. **Chunk-level attribution**: Tag each chunk with metadata, instruct LLM to cite by ID.

```python
def format_context_with_citations(chunks: list[Document]) -> str:
    """Format chunks with citation markers."""
    formatted = []
    for i, chunk in enumerate(chunks):
        citation_id = f"[{i+1}]"
        source_info = f"{chunk.metadata['title']}, p.{chunk.metadata['page']}"
        formatted.append(f"{citation_id} {chunk.text}\nSource: {source_info}")
    return "\n\n".join(formatted)

# In prompt:
# "When citing sources, use the [N] markers provided."
```

2. **Sentence-level attribution** (Anthropic-style): Map output sentences back to source sentences.

```python
def generate_with_citations(query: str, chunks: list[Document], llm) -> str:
    """Generate response with inline citations."""

    # Prepare source mapping
    source_sentences = {}
    for chunk in chunks:
        for i, sentence in enumerate(split_sentences(chunk.text)):
            key = f"{chunk.id}:{i}"
            source_sentences[key] = {
                "text": sentence,
                "source": chunk.metadata
            }

    prompt = f"""Answer this question using ONLY the provided sources.
    For each claim, include a citation in the format [source_id:sentence_num].

    Sources:
    {format_sources(source_sentences)}

    Question: {query}
    """

    return llm.generate(prompt)
```

**Framework Support**:
- LlamaIndex: `CitationQueryEngine`
- Custom: Store bounding boxes, page numbers, paragraph IDs in vector DB metadata

---

## Context Assembly Strategies

### Token Budget Management

Different models have different context limits. A robust system must handle this dynamically.

**Current Model Context Windows (2025)**:

| Model | Context Window | Max Output |
|-------|----------------|------------|
| Claude Sonnet 4.5 | 200k (1M beta) | 8k |
| GPT-4.1 | 1M | 32k |
| Llama 3 (local) | 8k-128k | varies |

**Budget Allocation Strategy**:
```python
@dataclass
class TokenBudget:
    total: int
    system_prompt: int
    conversation_history: int
    retrieved_context: int
    generation_reserve: int

    @classmethod
    def for_model(cls, model: str, query_complexity: str = "medium"):
        limits = MODEL_LIMITS[model]
        total = limits["context_window"]

        # Reserve output tokens
        generation = min(limits["max_output"], total // 4)
        remaining = total - generation

        # Allocate remaining
        system = min(2000, remaining // 10)
        remaining -= system

        # Split between history and context based on complexity
        history_ratio = {"simple": 0.2, "medium": 0.3, "complex": 0.4}[query_complexity]
        history = int(remaining * history_ratio)
        context = remaining - history

        return cls(
            total=total,
            system_prompt=system,
            conversation_history=history,
            retrieved_context=context,
            generation_reserve=generation
        )
```

### Dynamic Context Assembly

```python
class ContextAssembler:
    """Assemble context within token budget."""

    def __init__(self, tokenizer):
        self.tokenizer = tokenizer

    def assemble(
        self,
        system_prompt: str,
        history: list[Message],
        retrieved: list[Document],
        budget: TokenBudget
    ) -> list[Message]:
        """Assemble messages within budget constraints."""

        messages = []
        remaining = budget.total - budget.generation_reserve

        # 1. System prompt (required)
        system_tokens = self.count(system_prompt)
        if system_tokens > budget.system_prompt:
            system_prompt = self.truncate(system_prompt, budget.system_prompt)
        messages.append({"role": "system", "content": system_prompt})
        remaining -= self.count(system_prompt)

        # 2. Conversation history (recent messages prioritized)
        history_budget = min(budget.conversation_history, remaining // 2)
        history_tokens = 0
        included_history = []

        for msg in reversed(history):
            msg_tokens = self.count(msg.content)
            if history_tokens + msg_tokens <= history_budget:
                included_history.insert(0, msg)
                history_tokens += msg_tokens
            else:
                break

        messages.extend(included_history)
        remaining -= history_tokens

        # 3. Retrieved context (relevance-ranked, deduplicated)
        context_budget = min(budget.retrieved_context, remaining)
        context_text = self.compress_and_format(retrieved, context_budget)

        # Inject as system context or user message depending on model
        messages.append({
            "role": "user",
            "content": f"Context:\n{context_text}\n\nQuestion: {query}"
        })

        return messages

    def compress_and_format(self, docs: list[Document], budget: int) -> str:
        """Apply compression strategies to fit budget."""

        # Sort by relevance score
        docs = sorted(docs, key=lambda d: d.score, reverse=True)

        selected = []
        current_tokens = 0

        for doc in docs:
            doc_tokens = self.count(doc.text)

            if current_tokens + doc_tokens <= budget:
                selected.append(doc)
                current_tokens += doc_tokens
            elif budget - current_tokens > 100:
                # Partial inclusion of high-value doc
                truncated = self.truncate(doc.text, budget - current_tokens)
                doc.text = truncated
                selected.append(doc)
                break

        return self.format_with_citations(selected)
```

### Semantic Chunking vs Fixed Chunking

Fixed-size chunking (500 tokens, 1000 tokens) is easy but breaks semantic units. For academic documents with clear structure, semantic chunking significantly improves retrieval:

```python
def semantic_chunk(document: str, embedder) -> list[str]:
    """Chunk by semantic boundaries."""

    # Split into sentences
    sentences = split_sentences(document)

    # Compute embeddings
    embeddings = embedder.embed(sentences)

    # Find breakpoints where similarity drops
    chunks = []
    current_chunk = [sentences[0]]

    for i in range(1, len(sentences)):
        similarity = cosine_similarity(embeddings[i-1], embeddings[i])

        if similarity < 0.7:  # Threshold for topic shift
            chunks.append(" ".join(current_chunk))
            current_chunk = [sentences[i]]
        else:
            current_chunk.append(sentences[i])

    chunks.append(" ".join(current_chunk))
    return chunks
```

---

## LLM Abstraction Layer Design

For a system requiring Claude, OpenAI, and Ollama support, the abstraction layer is critical.

### Option 1: Use LiteLLM Directly

**Pros**: Minimal code, handles 100+ providers, OpenAI-compatible API
**Cons**: External dependency, potential scaling issues, black-box behavior

```python
from litellm import completion

class LLMProvider:
    def __init__(self, default_model: str = "claude-sonnet-4-5"):
        self.default_model = default_model

    def complete(
        self,
        messages: list[dict],
        model: str = None,
        **kwargs
    ) -> str:
        response = completion(
            model=model or self.default_model,
            messages=messages,
            **kwargs
        )
        return response.choices[0].message.content
```

### Option 2: Thin Custom Abstraction

**Pros**: Full control, minimal dependencies, clear behavior
**Cons**: More code to maintain, must implement each provider

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Generator

@dataclass
class LLMResponse:
    content: str
    model: str
    usage: dict
    raw_response: any = None

class LLMProvider(ABC):
    """Abstract base for LLM providers."""

    @property
    @abstractmethod
    def context_window(self) -> int:
        """Maximum context window in tokens."""
        pass

    @property
    @abstractmethod
    def max_output(self) -> int:
        """Maximum output tokens."""
        pass

    @abstractmethod
    def complete(
        self,
        messages: list[dict],
        max_tokens: int = None,
        temperature: float = 0.7,
        **kwargs
    ) -> LLMResponse:
        """Generate a completion."""
        pass

    @abstractmethod
    def stream(
        self,
        messages: list[dict],
        **kwargs
    ) -> Generator[str, None, None]:
        """Stream a completion."""
        pass


class ClaudeProvider(LLMProvider):
    """Anthropic Claude implementation."""

    MODEL_SPECS = {
        "claude-sonnet-4-5": {"context": 200000, "output": 8192},
        "claude-opus-4-5": {"context": 200000, "output": 8192},
    }

    def __init__(self, model: str = "claude-sonnet-4-5", api_key: str = None):
        import anthropic
        self.model = model
        self.client = anthropic.Anthropic(api_key=api_key)
        self._specs = self.MODEL_SPECS.get(model, {"context": 200000, "output": 8192})

    @property
    def context_window(self) -> int:
        return self._specs["context"]

    @property
    def max_output(self) -> int:
        return self._specs["output"]

    def complete(self, messages: list[dict], max_tokens: int = None, **kwargs) -> LLMResponse:
        # Extract system message if present
        system = None
        user_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system = msg["content"]
            else:
                user_messages.append(msg)

        response = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens or self.max_output,
            system=system,
            messages=user_messages,
            **kwargs
        )

        return LLMResponse(
            content=response.content[0].text,
            model=self.model,
            usage={
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens
            },
            raw_response=response
        )

    def stream(self, messages: list[dict], **kwargs) -> Generator[str, None, None]:
        system = None
        user_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system = msg["content"]
            else:
                user_messages.append(msg)

        with self.client.messages.stream(
            model=self.model,
            max_tokens=kwargs.get("max_tokens", self.max_output),
            system=system,
            messages=user_messages,
        ) as stream:
            for text in stream.text_stream:
                yield text


class OllamaProvider(LLMProvider):
    """Local Ollama implementation."""

    def __init__(self, model: str = "llama3", base_url: str = "http://127.0.0.1:11434"):
        import ollama
        self.model = model
        self.base_url = base_url
        self.client = ollama.Client(host=base_url)

        # Query model for specs (Ollama provides this)
        try:
            info = self.client.show(model)
            self._context = info.get("parameters", {}).get("num_ctx", 8192)
        except:
            self._context = 8192

    @property
    def context_window(self) -> int:
        return self._context

    @property
    def max_output(self) -> int:
        return self._context // 2  # Conservative default

    def complete(self, messages: list[dict], **kwargs) -> LLMResponse:
        response = self.client.chat(
            model=self.model,
            messages=messages,
            **kwargs
        )

        return LLMResponse(
            content=response["message"]["content"],
            model=self.model,
            usage={
                "input_tokens": response.get("prompt_eval_count", 0),
                "output_tokens": response.get("eval_count", 0)
            },
            raw_response=response
        )

    def stream(self, messages: list[dict], **kwargs) -> Generator[str, None, None]:
        for chunk in self.client.chat(
            model=self.model,
            messages=messages,
            stream=True,
            **kwargs
        ):
            yield chunk["message"]["content"]


class LLMRouter:
    """Route requests to appropriate provider."""

    def __init__(self):
        self.providers: dict[str, LLMProvider] = {}
        self.default_provider: str = None

    def register(self, name: str, provider: LLMProvider, default: bool = False):
        self.providers[name] = provider
        if default or self.default_provider is None:
            self.default_provider = name

    def get(self, name: str = None) -> LLMProvider:
        return self.providers[name or self.default_provider]

    def complete(self, messages: list[dict], provider: str = None, **kwargs) -> LLMResponse:
        return self.get(provider).complete(messages, **kwargs)
```

### Option 3: Hybrid (LiteLLM + Custom Extensions)

Use LiteLLM for the API normalization but wrap it in your own interface:

```python
from litellm import completion, get_model_info

class UnifiedLLM:
    """Unified interface with LiteLLM backend."""

    def __init__(self, default_model: str = "claude-sonnet-4-5"):
        self.default_model = default_model
        self._model_cache = {}

    def get_context_window(self, model: str = None) -> int:
        """Get context window for model."""
        model = model or self.default_model
        if model not in self._model_cache:
            try:
                info = get_model_info(model)
                self._model_cache[model] = info
            except:
                self._model_cache[model] = {"max_tokens": 8192}
        return self._model_cache[model].get("max_tokens", 8192)

    def complete(
        self,
        messages: list[dict],
        model: str = None,
        budget: TokenBudget = None,
        **kwargs
    ) -> LLMResponse:
        model = model or self.default_model

        # Apply budget constraints if provided
        if budget:
            kwargs["max_tokens"] = min(
                kwargs.get("max_tokens", budget.generation_reserve),
                budget.generation_reserve
            )

        response = completion(model=model, messages=messages, **kwargs)

        return LLMResponse(
            content=response.choices[0].message.content,
            model=model,
            usage={
                "input_tokens": response.usage.prompt_tokens,
                "output_tokens": response.usage.completion_tokens
            },
            raw_response=response
        )
```

### Recommendation

For this project, **Option 3 (Hybrid)** is the best balance:
- LiteLLM handles provider complexity
- Custom wrapper provides project-specific interfaces
- Easy to swap out LiteLLM later if needed
- Clean integration with the rest of the system

---

## Build vs Buy Analysis

### What "Build" Actually Means

For the LLM query interface, "building" doesn't mean implementing everything from scratch. It means:

1. **Thin provider abstraction** (~200 lines): Wrap LiteLLM or implement 2-3 providers directly
2. **Token budget management** (~150 lines): Model-aware context allocation
3. **Context assembly** (~300 lines): Combine retrieval, history, system prompt
4. **Citation formatting** (~100 lines): Prepare context with source markers

**Total custom code**: ~750 lines for the core interface.

### What Frameworks Provide

| Capability | Build Cost | Framework Alternative |
|------------|------------|----------------------|
| Provider abstraction | Low | LiteLLM (drop-in) |
| Retrieval | High | LlamaIndex, Haystack |
| Indexing/chunking | High | LlamaIndex |
| Query expansion | Medium | Haystack QueryExpander |
| Prompt optimization | High | DSPy |
| Citation tracking | Medium | LlamaIndex CitationQueryEngine |
| Pipeline orchestration | Medium | Haystack pipelines |
| Async/streaming | Medium | All frameworks support |

### Cost-Benefit Summary

**Build** when:
- You need precise control over behavior
- The abstraction is thin and stable
- Framework would add unnecessary complexity
- Integration with existing code is non-trivial

**Buy** when:
- The problem is well-solved by frameworks
- You'd be reimplementing substantial logic
- The framework's abstraction matches your needs
- Active maintenance matters (security, API changes)

### For This Project

| Component | Recommendation | Rationale |
|-----------|---------------|-----------|
| LLM provider abstraction | LiteLLM + thin wrapper | Minimal code, handles complexity |
| Retrieval/indexing | LlamaIndex or Haystack | Significant complexity, well-solved |
| Token management | Build | Project-specific requirements |
| Context assembly | Build | Core to your architecture |
| Citation tracking | LlamaIndex or build | Depends on complexity needs |
| Query expansion | Build or Haystack | Simple enough to build |

---

## Recommendations

### Path 1: Easiest Path

**Stack**: LlamaIndex + LiteLLM

**Implementation**:
```python
from llama_index.core import VectorStoreIndex, Settings
from llama_index.llms.litellm import LiteLLM
from llama_index.embeddings.ollama import OllamaEmbedding

# Configure LLM (works with Claude, OpenAI, Ollama)
Settings.llm = LiteLLM(model="claude-sonnet-4-5")
Settings.embed_model = OllamaEmbedding(model_name="nomic-embed-text")

# Build index from your documents
index = VectorStoreIndex.from_documents(documents)

# Create citation-aware query engine
from llama_index.core.query_engine import CitationQueryEngine
query_engine = CitationQueryEngine.from_args(index, citation_chunk_size=512)

# Query
response = query_engine.query("What are the key findings on X?")
print(response.response)
print(response.source_nodes)  # Citations
```

**Pros**:
- Working system in <100 lines
- Citation tracking included
- Provider-agnostic via LiteLLM
- Good documentation

**Cons**:
- Less control over internals
- May need customization for academic metadata
- LlamaIndex updates can break code

**Time to working prototype**: 1-2 days

---

### Path 2: Best Quality/Flexibility

**Stack**: Haystack pipelines + Custom LLM wrapper + DSPy for generation

**Architecture**:
```
┌─────────────────────────────────────────────────────────────┐
│                     Query Interface                          │
├─────────────────────────────────────────────────────────────┤
│  ┌───────────────┐  ┌───────────────┐  ┌─────────────────┐  │
│  │ Query         │  │ Retrieval     │  │ Response        │  │
│  │ Processing    │──▶ Pipeline      │──▶ Generation      │  │
│  │ (Haystack)    │  │ (Haystack)    │  │ (DSPy)          │  │
│  └───────────────┘  └───────────────┘  └─────────────────┘  │
├─────────────────────────────────────────────────────────────┤
│                   LLM Abstraction Layer                      │
│  ┌─────────────────────────────────────────────────────────┐│
│  │              Custom Wrapper + LiteLLM                   ││
│  │  ┌─────────┐  ┌─────────┐  ┌─────────┐                  ││
│  │  │ Claude  │  │ OpenAI  │  │ Ollama  │                  ││
│  │  └─────────┘  └─────────┘  └─────────┘                  ││
│  └─────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
```

**Implementation sketch**:
```python
# Haystack for retrieval pipeline
from haystack import Pipeline
from haystack.components.retrievers import InMemoryEmbeddingRetriever
from haystack.components.embedders import SentenceTransformersTextEmbedder

retrieval_pipeline = Pipeline()
retrieval_pipeline.add_component("embedder", SentenceTransformersTextEmbedder())
retrieval_pipeline.add_component("retriever", InMemoryEmbeddingRetriever(document_store))
retrieval_pipeline.connect("embedder.embedding", "retriever.query_embedding")

# DSPy for generation
import dspy

class CitedAnswer(dspy.Signature):
    """Answer with inline citations."""
    context: str = dspy.InputField(desc="retrieved passages with [N] markers")
    question: str = dspy.InputField()
    answer: str = dspy.OutputField(desc="answer with [N] citations inline")

class RAGModule(dspy.Module):
    def __init__(self):
        self.generate = dspy.ChainOfThought(CitedAnswer)

    def forward(self, question: str, context: str):
        return self.generate(question=question, context=context)

# Combine in your interface
class QueryInterface:
    def __init__(self, retrieval_pipeline, generator, llm_router):
        self.retrieval = retrieval_pipeline
        self.generator = generator
        self.llm = llm_router

    def query(self, question: str, model: str = None) -> QueryResult:
        # 1. Retrieve
        docs = self.retrieval.run({"embedder": {"text": question}})

        # 2. Format with citations
        context = self.format_context(docs["retriever"]["documents"])

        # 3. Generate
        dspy.configure(lm=self.llm.get_dspy_adapter(model))
        result = self.generator(question=question, context=context)

        return QueryResult(
            answer=result.answer,
            sources=self.extract_citations(result.answer, docs)
        )
```

**Pros**:
- Maximum control and flexibility
- Best performance (typed pipelines, optimized prompts)
- Clean separation of concerns
- DSPy enables systematic prompt improvement

**Cons**:
- More code and complexity
- Steeper learning curve
- Multiple dependencies to manage

**Time to working prototype**: 1-2 weeks

---

### Path 3: Optimal ROI (Recommended for This Project)

**Stack**: Custom abstraction + LiteLLM + LlamaIndex retrieval components

**Philosophy**: Build the integration layer, use frameworks for heavy lifting.

**Architecture**:
```python
# llm_interface.py - Your abstraction layer

from dataclasses import dataclass
from typing import Protocol, Generator
import litellm

@dataclass
class QueryResult:
    answer: str
    sources: list[dict]
    usage: dict

class Retriever(Protocol):
    def retrieve(self, query: str, k: int = 5) -> list[Document]: ...

class RAGInterface:
    """Clean interface for RAG queries."""

    def __init__(
        self,
        retriever: Retriever,
        default_model: str = "claude-sonnet-4-5",
        system_prompt: str = None
    ):
        self.retriever = retriever
        self.default_model = default_model
        self.system_prompt = system_prompt or DEFAULT_RAG_PROMPT
        self.budget_manager = TokenBudgetManager()

    def query(
        self,
        question: str,
        model: str = None,
        k: int = 5,
        include_citations: bool = True
    ) -> QueryResult:
        model = model or self.default_model

        # 1. Retrieve relevant documents
        docs = self.retriever.retrieve(question, k=k)

        # 2. Compute budget and assemble context
        budget = self.budget_manager.compute(model)
        context = self.assemble_context(docs, budget, include_citations)

        # 3. Generate response
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {question}"}
        ]

        response = litellm.completion(
            model=model,
            messages=messages,
            max_tokens=budget.generation_reserve
        )

        answer = response.choices[0].message.content

        # 4. Extract and verify citations
        sources = self.extract_citations(answer, docs) if include_citations else []

        return QueryResult(
            answer=answer,
            sources=sources,
            usage={
                "input_tokens": response.usage.prompt_tokens,
                "output_tokens": response.usage.completion_tokens,
                "model": model
            }
        )

    def stream_query(
        self,
        question: str,
        model: str = None,
        k: int = 5
    ) -> Generator[str, None, None]:
        """Streaming version for interactive use."""
        model = model or self.default_model
        docs = self.retriever.retrieve(question, k=k)
        budget = self.budget_manager.compute(model)
        context = self.assemble_context(docs, budget, include_citations=True)

        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {question}"}
        ]

        for chunk in litellm.completion(
            model=model,
            messages=messages,
            max_tokens=budget.generation_reserve,
            stream=True
        ):
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
```

**Using LlamaIndex for retrieval only**:
```python
from llama_index.core import VectorStoreIndex
from llama_index.embeddings.ollama import OllamaEmbedding

class LlamaIndexRetriever:
    """Wrap LlamaIndex for retrieval only."""

    def __init__(self, index: VectorStoreIndex):
        self.index = index
        self.retriever = index.as_retriever(similarity_top_k=10)

    def retrieve(self, query: str, k: int = 5) -> list[Document]:
        nodes = self.retriever.retrieve(query)[:k]
        return [
            Document(
                id=node.node_id,
                text=node.text,
                score=node.score,
                metadata=node.metadata
            )
            for node in nodes
        ]

# Compose
from llama_index.core import VectorStoreIndex, StorageContext

index = VectorStoreIndex.from_documents(documents)
retriever = LlamaIndexRetriever(index)
rag = RAGInterface(retriever=retriever, default_model="claude-sonnet-4-5")

# Use
result = rag.query("What are the main arguments in Smith 2023?")
```

**Pros**:
- Clean interface that fits your architecture
- LlamaIndex handles complex retrieval/indexing
- LiteLLM handles provider abstraction
- Full control over context assembly and citation
- Easy to extend or replace components
- Testable (mock retriever, mock LLM)

**Cons**:
- Some custom code to maintain (~500 lines)
- Must track LlamaIndex API changes

**Time to working prototype**: 3-5 days
**Time to production-ready**: 2-3 weeks

---

## Common Pitfalls and Lock-in Risks

### Framework Lock-in

**Risk**: Deep integration with a framework makes switching costly.

**Mitigation**:
- Use frameworks for specific components, not end-to-end orchestration
- Define your own interfaces; wrap framework classes
- Avoid framework-specific patterns in business logic

**Example** (bad):
```python
# Tight coupling to LlamaIndex
from llama_index.core.query_engine import CitationQueryEngine

def answer_question(question):
    return query_engine.query(question)  # LlamaIndex object returned
```

**Example** (good):
```python
# Your interface, LlamaIndex as implementation detail
def answer_question(question: str) -> QueryResult:
    response = query_engine.query(question)
    return QueryResult(
        answer=response.response,
        sources=[format_source(n) for n in response.source_nodes]
    )
```

---

### Provider Lock-in

**Risk**: Code assumes specific provider features (Claude's XML tags, OpenAI's function calling).

**Mitigation**:
- Stick to common denominator features when possible
- Abstract provider-specific features behind conditional logic
- Test with multiple providers regularly

```python
def format_for_model(context: str, model: str) -> str:
    """Apply model-specific formatting."""
    if "claude" in model:
        # Claude handles XML well
        return f"<context>\n{context}\n</context>"
    else:
        # Generic markdown
        return f"## Context\n\n{context}"
```

---

### Prompt Brittleness

**Risk**: Prompts that work for one model fail on others.

**Mitigation**:
- Use DSPy signatures for critical prompts (auto-optimizes per model)
- Test prompts across models before deployment
- Keep prompts simple; complex instructions amplify model differences

---

### Version Churn

**Risk**: Framework updates break your code (LangChain is notorious for this).

**Mitigation**:
- Pin versions in requirements
- Wrap framework calls in your own functions
- Prefer stable frameworks (Haystack > LangChain for stability)
- Have integration tests that catch breakage

---

### Token Estimation Errors

**Risk**: Underestimate tokens, exceed context window, get truncated responses.

**Mitigation**:
- Use actual tokenizers, not character-based estimates
- Build in safety margins (10-20% buffer)
- Handle truncation gracefully

```python
import tiktoken

class TokenCounter:
    def __init__(self, model: str):
        # Map to tokenizer (simplified)
        if "claude" in model:
            self.encoder = tiktoken.get_encoding("cl100k_base")  # Approximation
        else:
            self.encoder = tiktoken.encoding_for_model(model)

    def count(self, text: str) -> int:
        return len(self.encoder.encode(text))

    def truncate(self, text: str, max_tokens: int) -> str:
        tokens = self.encoder.encode(text)
        if len(tokens) <= max_tokens:
            return text
        return self.encoder.decode(tokens[:max_tokens])
```

---

### Citation Hallucination

**Risk**: LLM generates plausible-looking but incorrect citations.

**Mitigation**:
- Validate citations against actual source chunks
- Use structured output (JSON) for citations
- Post-process to verify cited text exists in sources

```python
def validate_citations(answer: str, sources: dict[str, str]) -> str:
    """Remove invalid citations from answer."""
    import re

    def check_citation(match):
        cite_id = match.group(1)
        if cite_id in sources:
            return match.group(0)
        else:
            return ""  # Remove invalid citation

    return re.sub(r'\[(\d+)\]', check_citation, answer)
```

---

### Over-Engineering Early

**Risk**: Building complex infrastructure before understanding actual needs.

**Mitigation**:
- Start with Path 1 (easiest), refactor to Path 3 as needs clarify
- Build only what you need now
- Measure before optimizing (token usage, latency, retrieval quality)

---

## Summary

For a personal knowledge management system with LLM-agnostic requirements:

1. **Start with LiteLLM** for provider abstraction—it's effectively free and handles the complexity.

2. **Use LlamaIndex for retrieval** unless you have specific requirements that favor Haystack's typed pipelines.

3. **Build your own context assembly** because it's central to your system and straightforward.

4. **Define clean interfaces** between components so you can swap implementations later.

5. **Test with multiple models** from the start to catch provider-specific assumptions early.

The optimal path (Path 3) balances control with leverage: you own the interfaces and integration logic, while frameworks handle the complex, well-solved problems like vector indexing and embedding management.

---

## Sources

- [Claude Context Windows Documentation](https://docs.claude.com/en/docs/build-with-claude/context-windows)
- [LlamaIndex Custom LLM Documentation](https://docs.llamaindex.ai/en/stable/module_guides/models/llms/usage_custom/)
- [Haystack GitHub Repository](https://github.com/deepset-ai/haystack)
- [LiteLLM Documentation](https://docs.litellm.ai/docs/providers/ollama)
- [OpenAI GPT-4.1 Model Documentation](https://platform.openai.com/docs/models/gpt-4.1)
- [Ollama Embedding Models Blog](https://ollama.com/blog/embedding-models)
- [AdaGReS: Token-Budgeted RAG (arXiv)](https://arxiv.org/abs/2512.25052)
- [Haystack Query Expansion](https://haystack.deepset.ai/blog/query-expansion)
- [RAG Citation Implementation - Tensorlake](https://www.tensorlake.ai/blog/rag-citations)
- [LlamaIndex Citation Query Engine](https://developers.llamaindex.ai/python/examples/workflow/citation_query_engine/)
- [aisuite PyPI](https://pypi.org/project/aisuite/)
- [Two Sigma: Guide to LLM Abstractions](https://www.twosigma.com/articles/a-guide-to-large-language-model-abstractions/)
- [Context Engineering for AI Agents - Mem0](https://mem0.ai/blog/context-engineering-ai-agents-guide)
