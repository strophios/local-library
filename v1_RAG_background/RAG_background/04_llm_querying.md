# LLM Querying for RAG Systems

## Executive Summary

For your academic knowledge management system:

- **Architecture**: Custom minimal implementation (~100-200 lines)
- **Query strategy**: Start with basic retrieve-then-generate; add HyDE for conceptual queries
- **LLM choice**: Local (Ollama) for development, Claude/GPT-4 for quality queries
- **Key insight**: Citation discipline in prompts is critical — enforce grounding in sources

---

## Query Pipeline Architecture

### Basic Retrieve-Then-Generate

The foundation. Get this working first before adding complexity.

```
Query → Embed → Vector Search → Format Context → Generate Response
```

```python
class MinimalRAG:
    SYSTEM_PROMPT = """You are a research assistant. Answer based ONLY on the provided context.
Cite sources using [citekey]. If the context doesn't contain the answer, say so."""

    def __init__(self, retriever, llm):
        self.retriever = retriever
        self.llm = llm

    def query(self, question: str, k: int = 5) -> str:
        # Retrieve
        chunks = self.retriever.search(question, k=k)

        # Format context
        context = self.format_context(chunks)

        # Generate
        prompt = f"""Context from academic sources:

{context}

---

Question: {question}

Provide a clear answer based on the sources above. Cite with [citekey] format."""

        return self.llm.generate(prompt, system=self.SYSTEM_PROMPT)

    def format_context(self, chunks: list) -> str:
        formatted = []
        for chunk in chunks:
            meta = chunk.metadata
            header = f"[{meta.get('citekey', 'unknown')}]"
            if meta.get('authors'):
                header += f" {meta['authors'][0]} et al."
            if meta.get('year'):
                header += f" ({meta['year']})"
            formatted.append(f"{header}\n{chunk.text}")
        return "\n\n---\n\n".join(formatted)
```

### HyDE (Hypothetical Document Embeddings)

Good for conceptual queries where the question doesn't directly match document vocabulary.

**When to use**:
- Broad/conceptual questions ("How do embeddings relate to semantic similarity?")
- When basic retrieval returns poor results

**When NOT to use**:
- Specific factual queries ("What does the BLIP model do?")
- Queries with rare technical terms (use keyword search instead)

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

### Multi-Query Retrieval

For complex questions with multiple parts:

```python
def multi_query_retrieve(self, question: str, k_per: int = 3) -> list:
    """Break question into sub-queries, search each."""

    decompose_prompt = f"""Break this question into 2-3 simpler search queries:
{question}

Queries (one per line):"""

    sub_queries = self.llm.generate(decompose_prompt).strip().split('\n')

    all_chunks = {}
    for query in [question] + sub_queries:
        for chunk in self.retriever.search(query.strip(), k=k_per):
            all_chunks[chunk.id] = chunk  # Deduplicate

    return list(all_chunks.values())
```

---

## Context Assembly

### Formatting for Academic RAG

```python
def format_context(self, chunks: list[Chunk]) -> str:
    """Format chunks with citekeys and clear boundaries."""
    formatted = []

    for chunk in chunks:
        meta = chunk.metadata

        # Build header with citation info
        parts = [f"[{meta.get('citekey', 'unknown')}]"]
        if meta.get('authors'):
            # First author et al.
            first = meta['authors'][0]
            name = first.get('family', first.get('literal', 'Unknown'))
            parts.append(f"{name} et al.")
        if meta.get('year'):
            parts.append(f"({meta['year']})")
        if meta.get('section_title'):
            parts.append(f"— {meta['section_title']}")

        header = " ".join(parts)
        formatted.append(f"{header}\n{chunk.text}")

    return "\n\n---\n\n".join(formatted)
```

### Context Window Management

For long contexts or many chunks:

```python
def assemble_context(
    self,
    chunks: list[Chunk],
    max_tokens: int = 6000,  # Leave room for prompt + response
    tokenizer = None
) -> str:
    """Assemble context within token budget."""
    if tokenizer is None:
        tokenizer = tiktoken.encoding_for_model("gpt-4")

    formatted_chunks = []
    total_tokens = 0

    for chunk in chunks:
        formatted = self.format_single_chunk(chunk)
        chunk_tokens = len(tokenizer.encode(formatted))

        if total_tokens + chunk_tokens > max_tokens:
            break

        formatted_chunks.append(formatted)
        total_tokens += chunk_tokens

    return "\n\n---\n\n".join(formatted_chunks)
```

---

## Prompt Engineering for Academic RAG

### System Prompt (Recommended)

```python
SYSTEM_PROMPT = """You are a research assistant helping answer questions about academic literature.

Guidelines:
1. Answer based ONLY on the provided context. Do not use prior knowledge.
2. Cite sources using their citekeys in brackets, e.g., [smith2023].
3. If multiple sources support a claim, cite all of them.
4. If the context doesn't contain enough information, say so clearly.
5. Distinguish between what sources claim vs. what you're inferring.
6. Use hedging language when appropriate ("suggests", "indicates", "appears to").
"""
```

### Handling "I Don't Know"

Explicitly prompt for acknowledgment of uncertainty:

```python
QUERY_TEMPLATE = """Context from academic sources:

{context}

---

Question: {question}

Instructions:
- If the context contains relevant information, provide a clear answer citing sources.
- If the context is partially relevant, answer what you can and note what's missing.
- If the context doesn't address the question, respond: "The provided sources don't contain information about [topic]. Consider searching for [suggested terms]."

Answer:"""
```

---

## Framework vs. Custom Implementation

### When Custom Implementation Wins

- **Your scale**: ~100-200 lines of code is manageable
- **Your needs**: Citekey formatting, academic metadata, specific prompt structure
- **Your constraints**: Local-first, single-user, specific domain

### When to Consider Frameworks

- If you need sophisticated conversation management
- If you're building for multiple users
- If you need observability/debugging tools out of the box

### Minimal Framework Layer (If Desired)

If you want *some* abstraction without full LangChain overhead:

```python
# Use LangChain's RunnableSequence for composability
from langchain_core.runnables import RunnableSequence, RunnableLambda

retrieve = RunnableLambda(lambda q: retriever.search(q))
format_ctx = RunnableLambda(format_context)
generate = RunnableLambda(lambda ctx: llm.generate(build_prompt(ctx)))

chain = retrieve | format_ctx | generate
result = chain.invoke("What is attention?")
```

---

## LLM Model Recommendations

### For Development/Iteration

| Model | Speed | Quality | Notes |
|-------|-------|---------|-------|
| Llama 3.2 8B | Fast | Good | Via Ollama; good for testing |
| Phi-3.5 mini | Very fast | Moderate | Quick iteration |
| Mistral 7B | Fast | Good | Alternative to Llama |

```bash
ollama pull llama3.2:8b
ollama pull phi3.5:mini
```

### For Quality Queries

| Model | Quality | Cost | Notes |
|-------|---------|------|-------|
| Claude 3.5 Sonnet | Excellent | ~$3/1M tokens | Best reasoning |
| GPT-4o | Excellent | ~$5/1M tokens | Strong overall |
| GPT-4o mini | Good | ~$0.15/1M tokens | Cost-effective |
| Claude 3.5 Haiku | Good | ~$0.25/1M tokens | Fast, cheap |

### Recommendation

```python
# Development
llm = OllamaLLM(model="llama3.2:8b")

# Quality queries
llm = ClaudeLLM(model="claude-3-5-sonnet-20241022")

# Bulk processing
llm = ClaudeLLM(model="claude-3-5-haiku-20241022")  # Or local
```

### LLM Abstraction

```python
from abc import ABC, abstractmethod

class LLM(ABC):
    @abstractmethod
    def generate(self, prompt: str, system: str = None) -> str:
        pass

class OllamaLLM(LLM):
    def __init__(self, model: str = "llama3.2:8b"):
        self.model = model
        self.base_url = "http://localhost:11434"

    def generate(self, prompt: str, system: str = None) -> str:
        import requests
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        response = requests.post(
            f"{self.base_url}/api/chat",
            json={"model": self.model, "messages": messages, "stream": False}
        )
        return response.json()["message"]["content"]

class ClaudeLLM(LLM):
    def __init__(self, model: str = "claude-3-5-sonnet-20241022"):
        import anthropic
        self.client = anthropic.Anthropic()
        self.model = model

    def generate(self, prompt: str, system: str = None) -> str:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=system or "",
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content[0].text
```

---

## Conversation Context Handling

**This is a significant gap in many RAG implementations.**

### Basic Conversation History

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
@dataclass
class ConversationTurn:
    query: str
    response: str
    sources: list[str]  # Citekeys
    timestamp: datetime

# Store in database for persistence
```

---

## Implementation Phases

### Phase 1: Foundation (1-2 days)

1. Basic MinimalRAG class
2. Simple retrieve-then-generate
3. Local LLM for testing (Ollama)
4. Citation prompting

**Success criteria**: Can answer questions about your documents with citations.

### Phase 2: Quality (1 week)

1. Add HyDE for conceptual queries
2. Implement conversation context
3. API LLM integration (Claude)
4. Evaluation on test queries

**Success criteria**: Improved retrieval quality; multi-turn conversations work.

### Phase 3: Advanced (If Needed)

1. Query expansion for vocabulary mismatch
2. Multi-query for complex questions
3. Agentic tool use for exploration
4. Streaming for interactive use

**Transition criteria**:
- Phase 1 → 2: When retrieval precision drops below 70% on test queries
- Phase 2 → 3: Only if building sophisticated features (contradiction detection, etc.)

---

## Complete Starter Implementation

```python
"""Academic RAG System - Minimal but complete."""

from dataclasses import dataclass
from typing import Optional
from abc import ABC, abstractmethod

@dataclass
class Chunk:
    id: str
    text: str
    document_id: str
    metadata: dict

class AcademicRAG:
    SYSTEM_PROMPT = """You are a research assistant. Answer based ONLY on the provided context.
Cite sources using [citekey]. If the context doesn't contain the answer, say so."""

    def __init__(self, retriever, llm):
        self.retriever = retriever
        self.llm = llm

    def query(
        self,
        question: str,
        k: int = 5,
        use_hyde: bool = False
    ) -> dict:
        # Retrieval
        if use_hyde:
            chunks = self._hyde_retrieve(question, k)
            strategy = "hyde"
        else:
            chunks = self.retriever.search(question, k)
            strategy = "basic"

        # Generation
        context = self._format_context(chunks)
        response = self._generate(question, context)

        return {
            "answer": response,
            "sources": [c.metadata.get("citekey") for c in chunks],
            "strategy": strategy
        }

    def _format_context(self, chunks: list[Chunk]) -> str:
        formatted = []
        for chunk in chunks:
            meta = chunk.metadata
            header = f"[{meta.get('citekey', 'unknown')}]"
            formatted.append(f"{header}\n{chunk.text}")
        return "\n\n---\n\n".join(formatted)

    def _generate(self, question: str, context: str) -> str:
        prompt = f"""Context from academic sources:

{context}

---

Question: {question}

Answer (cite sources with [citekey]):"""

        return self.llm.generate(prompt, system=self.SYSTEM_PROMPT)

    def _hyde_retrieve(self, question: str, k: int) -> list[Chunk]:
        hypothetical = self.llm.generate(
            f"Write a paragraph from an academic paper answering: {question}"
        )
        return self.retriever.search(hypothetical, k=k)
```

---

## Implementation Checklist

```
[ ] Implement MinimalRAG class
[ ] Test with local LLM (Ollama)
[ ] Add citation formatting
[ ] Integrate API LLM (Claude)
[ ] Add HyDE for conceptual queries
[ ] Implement conversation history
[ ] Create evaluation test set (20+ queries)
[ ] Measure retrieval quality
[ ] Tune prompts based on results
```
