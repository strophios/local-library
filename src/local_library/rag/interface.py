"""RAG query interface - context assembly, prompt construction, and orchestration.

Context assembly and prompt construction are pure functions (Functional Core).
RAGInterface orchestrates the full pipeline (Imperative Shell, added in Phase 4).
"""

# pattern: Functional Core

from __future__ import annotations

from local_library.embeddings.base import SearchResult

_SYSTEM_PROMPT = """\
You are a research assistant answering questions based on a personal document library. \
You have been given relevant excerpts from the library below.

Instructions:
- Answer the question using ONLY the provided context.
- Cite sources using citekey references in the format [@citekey] (e.g., [@Smith2023]).
- If the provided context does not contain enough information to answer the question, \
say so clearly rather than speculating.
- Be concise and direct.\
"""

_CONTEXT_SEPARATOR = "\n\n---\n\n"


def assemble_context(search_results: list[SearchResult]) -> str:
    """Format retrieved search results into an attributed context string.

    Each chunk is prefixed with its citekey and section header (when available).
    Chunks are separated by horizontal rules.

    Args:
        search_results: Retrieved chunks with metadata, in relevance order.

    Returns:
        Formatted context string ready for inclusion in a prompt.
        Empty string if no results provided.
    """
    if not search_results:
        return ""

    blocks: list[str] = []
    for result in search_results:
        header = _format_chunk_header(result)
        blocks.append(f"{header} {result.chunk.text}")

    return _CONTEXT_SEPARATOR.join(blocks)


def _format_chunk_header(result: SearchResult) -> str:
    """Build the attribution header for a single chunk.

    Format: [@citekey, §Section] or [@citekey] or [unknown source, §Section] or
    [unknown source].

    Args:
        result: A single search result.

    Returns:
        Formatted attribution header string.
    """
    citekey_part = f"@{result.doc_citekey}" if result.doc_citekey else "unknown source"
    section_part = f", §{result.chunk.section}" if result.chunk.section else ""
    return f"[{citekey_part}{section_part}]"


def build_messages(context: str, question: str) -> list[dict[str, str]]:
    """Construct the message list for the LLM call.

    Uses context-first, question-last ordering: the question sits in the
    high-attention position at the end of the prompt.

    Args:
        context: Formatted context string from assemble_context().
        question: The user's natural language question.

    Returns:
        List of message dicts with 'role' and 'content' keys.
    """
    if context:
        user_content = f"Context:\n{context}\n\nQuestion: {question}"
    else:
        user_content = f"Question: {question}"

    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]
