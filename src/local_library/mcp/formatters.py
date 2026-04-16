"""Markdown formatters for MCP tool responses."""

# pattern: Functional Core

from local_library.embeddings.base import SearchResult


def format_search_results(results: list[SearchResult], query: str) -> str:
    """Format search results as markdown.

    Produces numbered results with citekeys, scores, section headers,
    chunk indices, and blockquoted text excerpts.

    Args:
        results: Search results sorted by score descending
        query: Original search query (used in empty results message)

    Returns:
        Markdown-formatted results string
    """
    if not results:
        return format_empty_results(query)

    # Count unique documents for header
    doc_ids = {r.chunk.doc_id for r in results}

    lines = [
        f"### Results ({len(results)} chunks from {len(doc_ids)} documents)",
        "",
    ]

    for i, r in enumerate(results, start=1):
        # Source identifier: prefer @citekey, fall back to title, then UUID prefix
        if r.doc_citekey:
            source = f"**@{r.doc_citekey}**"
        elif r.doc_title:
            source = f"**{r.doc_title}**"
        else:
            source = f"**{str(r.chunk.doc_id)[:8]}**"

        # Title in italics when citekey is the primary identifier
        title_part = f" | *{r.doc_title}*" if r.doc_citekey and r.doc_title else ""

        lines.append(f"{i}. {source} | score: {r.score:.3f}{title_part}")

        # Section header
        if r.chunk.section:
            lines.append(f"   Section: {r.chunk.section}")

        # Chunk index (labeled for follow-up get_document_text calls)
        lines.append(f"   Chunk {r.chunk.chunk_index}")

        # Chunk text as blockquote, truncated to ~300 chars
        text = r.chunk.text.strip()
        if len(text) > 300:
            text = text[:297] + "..."

        for text_line in text.split("\n"):
            lines.append(f"   > {text_line}")

        lines.append("")  # Blank line between results

    return "\n".join(lines)


def format_user_error(message: str) -> str:
    """Format a user-facing error with the standard prefix.

    User-facing errors indicate infrastructure problems that Claude should
    report to the user rather than attempting to work around.

    Args:
        message: Error description

    Returns:
        Prefixed error string
    """
    return f"\u26a0 USER-FACING ERROR: {message}"


def format_tool_error(message: str) -> str:
    """Format a tool-level error.

    Tool-level errors are things Claude can handle or work around,
    like document-not-found with fuzzy match suggestions.

    Args:
        message: Error description

    Returns:
        Prefixed error string
    """
    return f"Error: {message}"


def format_empty_results(query: str) -> str:
    """Format a helpful message when search returns no results.

    Args:
        query: The original search query

    Returns:
        Suggestion string for improving the search
    """
    return (
        f'No results found for "{query}". '
        "Try different search terms, broader keywords, "
        'or use mode="fts" for exact keyword matching.'
    )
