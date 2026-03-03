"""RAG query interface - context assembly, prompt construction, and orchestration.

Context assembly and prompt construction are pure functions (Functional Core).
RAGInterface orchestrates the full pipeline (Imperative Shell, added in Phase 4).
"""

# pattern: Mixed (unavoidable)
# Reason: Pure functions (assemble_context, build_messages) and Imperative Shell
# (RAGInterface) colocated in same file. Separation into two files adds
# complexity without testability benefit — pure functions are tested directly,
# RAGInterface tested with mocks.

from __future__ import annotations

from collections.abc import Iterator

from local_library.core.errors import ErrorCode, RAGError
from local_library.core.models import RAGResponse
from local_library.embeddings.base import SearchResult
from local_library.llm.base import LLMClient

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


class RAGStream:
    """Streaming wrapper for RAG query responses.

    Wraps a token iterator from the LLM, accumulating tokens during iteration.
    After iteration completes, call to_response() to build the final RAGResponse.

    The context_chunks are available immediately (before iteration starts),
    enabling the caller to display source information while streaming.

    Attributes:
        context_chunks: SearchResults used as context (available immediately).
    """

    def __init__(
        self,
        token_iter: Iterator[str],
        question: str,
        context_chunks: tuple[SearchResult, ...],
        model: str,
        retrieval_mode: str,
    ) -> None:
        """Initialize the streaming wrapper.

        Args:
            token_iter: Iterator yielding answer tokens from LLM.
            question: The original question.
            context_chunks: SearchResults used as context.
            model: Model identifier.
            retrieval_mode: Retrieval mode label.
        """
        self._token_iter = token_iter
        self._question = question
        self.context_chunks = context_chunks
        self._model = model
        self._retrieval_mode = retrieval_mode
        self._accumulated: list[str] = []

    def __iter__(self) -> Iterator[str]:
        """Yield answer tokens, accumulating them internally.

        Raises:
            RAGError: If the token stream fails mid-iteration.
        """
        try:
            for token in self._token_iter:
                self._accumulated.append(token)
                yield token
        except Exception as exc:
            raise RAGError(
                "LLM generation failed during streaming",
                ErrorCode.LLM_GENERATION_FAILED,
            ) from exc

    def to_response(self) -> RAGResponse:
        """Build the complete RAGResponse from accumulated tokens.

        Should be called after iteration completes. If called before
        iteration finishes, builds response from tokens received so far.

        Returns:
            Complete RAGResponse with the accumulated answer.
        """
        return RAGResponse(
            question=self._question,
            answer="".join(self._accumulated),
            context_chunks=self.context_chunks,
            model=self._model,
            retrieval_mode=self._retrieval_mode,
        )


class RAGInterface:
    """Orchestrates the RAG query pipeline.

    Coordinates context assembly, prompt construction, and LLM generation.
    Supports both blocking (query) and streaming (query_stream) paths.

    The pre-LLM gate skips the API call when retrieval returns zero results,
    saving latency and cost.
    """

    def __init__(self, llm_client: LLMClient, model: str) -> None:
        """Initialize the RAG interface.

        Args:
            llm_client: Client for LLM generation.
            model: Model identifier for attribution in RAGResponse.
        """
        self._llm_client = llm_client
        self._model = model

    def query(
        self,
        question: str,
        search_results: list[SearchResult],
        retrieval_mode: str = "hybrid",
    ) -> RAGResponse:
        """Execute a blocking RAG query.

        Assembles context from search results, constructs the prompt, calls the
        LLM, and returns a complete RAGResponse.

        If search_results is empty, returns a no-context response without
        calling the LLM (pre-LLM gate).

        Args:
            question: The user's natural language question.
            search_results: Retrieved chunks from the retriever.
            retrieval_mode: Retrieval mode label for the response.

        Returns:
            Complete RAGResponse with answer and source attribution.

        Raises:
            RAGError: If LLM generation fails.
        """
        context_chunks = tuple(search_results)

        # Pre-LLM gate: skip API call if no context
        if not search_results:
            return RAGResponse(
                question=question,
                answer="I don't have any relevant documents to answer this question.",
                context_chunks=context_chunks,
                model=self._model,
                retrieval_mode=retrieval_mode,
            )

        context = assemble_context(search_results)
        messages = build_messages(context, question)

        try:
            answer = self._llm_client.complete(messages, temperature=0.3)
        except Exception as exc:
            raise RAGError(
                "LLM generation failed",
                ErrorCode.LLM_GENERATION_FAILED,
            ) from exc

        return RAGResponse(
            question=question,
            answer=answer,
            context_chunks=context_chunks,
            model=self._model,
            retrieval_mode=retrieval_mode,
        )

    def query_stream(
        self,
        question: str,
        search_results: list[SearchResult],
        retrieval_mode: str = "hybrid",
    ) -> RAGStream:
        """Execute a streaming RAG query.

        Assembles context and constructs the prompt, then returns a RAGStream
        that yields tokens as they arrive from the LLM.

        If search_results is empty, returns a RAGStream that yields the
        no-context message without calling the LLM.

        Args:
            question: The user's natural language question.
            search_results: Retrieved chunks from the retriever.
            retrieval_mode: Retrieval mode label for the response.

        Returns:
            RAGStream that yields answer tokens and builds RAGResponse.
        """
        context_chunks = tuple(search_results)

        # Pre-LLM gate: skip API call if no context
        if not search_results:
            no_context_msg = "I don't have any relevant documents to answer this question."
            return RAGStream(
                token_iter=iter([no_context_msg]),
                question=question,
                context_chunks=context_chunks,
                model=self._model,
                retrieval_mode=retrieval_mode,
            )

        context = assemble_context(search_results)
        messages = build_messages(context, question)

        token_iter = self._llm_client.stream(messages, temperature=0.3)

        return RAGStream(
            token_iter=token_iter,
            question=question,
            context_chunks=context_chunks,
            model=self._model,
            retrieval_mode=retrieval_mode,
        )
