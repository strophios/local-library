"""Markdown formatters for MCP tool responses."""

# pattern: Functional Core

from local_library.core.models import Document
from local_library.embeddings.base import Chunk, SearchResult


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


def format_document(doc: Document, chunk_count: int) -> str:
    """Format document metadata as markdown.

    Shows citekey, title, authors, date, status, embedding status,
    chunk count, CSL-JSON metadata fields, and original path.

    Args:
        doc: Document to format
        chunk_count: Number of chunks for this document

    Returns:
        Markdown-formatted document metadata
    """
    # Header: prefer @citekey, fall back to title or UUID
    if doc.citekey:
        header = f"## @{doc.citekey}"
    elif doc.title:
        header = f"## {doc.title}"
    else:
        header = f"## Document {doc.id}"

    lines = [header, ""]

    if doc.title:
        lines.append(f"**Title:** {doc.title}")
    if doc.authors:
        lines.append(f"**Authors:** {doc.authors}")
    if doc.issued_date:
        lines.append(f"**Date:** {doc.issued_date}")

    lines.append(f"**Status:** {doc.status.value}")
    lines.append(f"**Embedding status:** {doc.embedding_status.value}")
    lines.append(f"**Chunks:** {chunk_count}")

    # CSL-JSON metadata fields (if available)
    if doc.csl_json:
        lines.append("")
        lines.append("### Metadata")
        csl_fields = [
            ("type", "Type"),
            ("publisher", "Publisher"),
            ("container-title", "Journal/Book"),
            ("volume", "Volume"),
            ("issue", "Issue"),
            ("page", "Pages"),
            ("DOI", "DOI"),
            ("URL", "URL"),
            ("ISBN", "ISBN"),
            ("ISSN", "ISSN"),
            ("abstract", "Abstract"),
        ]
        for key, label in csl_fields:
            if key in doc.csl_json and doc.csl_json[key]:
                value = doc.csl_json[key]
                if isinstance(value, str) and len(value) > 300:
                    value = value[:297] + "..."
                lines.append(f"- **{label}:** {value}")

    lines.append("")
    lines.append(f"**Original path:** {doc.original_path}")

    return "\n".join(lines)


def format_document_list(docs: list[Document], total: int) -> str:
    """Format document listing as markdown table.

    Args:
        docs: Documents to display (already sliced to limit)
        total: Total number of documents (for "showing X of Y" header)

    Returns:
        Markdown table string
    """
    if not docs:
        return "No documents in the library."

    showing = len(docs)
    if showing < total:
        header = f"### Documents (showing {showing} of {total:,})"
    else:
        header = f"### Documents ({total:,} total)"

    lines = [
        header,
        "",
        "| Citekey | Title | Authors | Status | Embeddings |",
        "|---------|-------|---------|--------|------------|",
    ]

    for doc in docs:
        citekey = f"@{doc.citekey}" if doc.citekey else ""
        title = doc.title or ""
        if len(title) > 40:
            title = title[:37] + "..."
        authors = doc.authors or ""
        if len(authors) > 25:
            authors = authors[:22] + "..."

        lines.append(
            f"| {citekey} | {title} | {authors} "
            f"| {doc.status.value} | {doc.embedding_status.value} |"
        )

    return "\n".join(lines)


def format_document_text(
    doc: Document,
    text: str | None,
    chunks: list[Chunk] | None,
    total_chunks: int,
    start_chunk: int | None = None,
    end_chunk: int | None = None,
) -> str:
    """Format document text content as markdown.

    Three modes:
    - Short doc (text provided): returns full extracted markdown
    - Long doc with range (chunks provided, start/end set): chunk subset
    - Long doc preview (chunks provided, no range): header + first chunks + instructions

    Args:
        doc: Document metadata
        text: Full extracted markdown (for short docs)
        chunks: Chunk objects (for long docs)
        total_chunks: Total number of chunks in document
        start_chunk: Start of requested range (if range mode)
        end_chunk: End of requested range (if range mode)

    Returns:
        Markdown-formatted document text
    """
    # Document identification header
    if doc.citekey:
        doc_header = f"## @{doc.citekey}"
    elif doc.title:
        doc_header = f"## {doc.title}"
    else:
        doc_header = f"## Document {doc.id}"

    # Short document: return full text
    if text is not None:
        lines = [doc_header, f"*{total_chunks} chunks*", "", text]
        return "\n".join(lines)

    # Long document with chunk range
    if chunks and (start_chunk is not None or end_chunk is not None):
        s = start_chunk if start_chunk is not None else 0
        e = end_chunk if end_chunk is not None else chunks[-1].chunk_index
        lines = [doc_header, f"*Chunks {s}\u2013{e} of {total_chunks} total*", ""]
        for chunk in chunks:
            if chunk.section:
                lines.append(f"### {chunk.section}")
            lines.append(f"*[Chunk {chunk.chunk_index}]*")
            lines.append("")
            lines.append(chunk.text)
            lines.append("")
        return "\n".join(lines)

    # Long document preview (no range specified)
    if chunks:
        sections = []
        seen = set()
        for chunk in chunks:
            if chunk.section and chunk.section not in seen:
                sections.append(chunk.section)
                seen.add(chunk.section)

        lines = [doc_header, f"*{total_chunks} chunks total*", ""]
        if sections:
            lines.append("### Sections")
            for section in sections:
                lines.append(f"- {section}")
            lines.append("")
        lines.append(f"### Preview (first {len(chunks)} chunks)")
        lines.append("")
        for chunk in chunks:
            if chunk.section:
                lines.append(f"**{chunk.section}**")
            lines.append(f"*[Chunk {chunk.chunk_index}]*")
            lines.append("")
            lines.append(chunk.text)
            lines.append("")
        lines.append("---")
        lines.append(
            f"Document has {total_chunks} chunks. To read a specific section, "
            f"call `get_document_text` with `start_chunk` and `end_chunk` parameters "
            f"(0-based, inclusive). Example: start_chunk=20, end_chunk=40"
        )
        return "\n".join(lines)

    # Fallback: no text or chunks available
    return f"{doc_header}\n\nNo text content available for this document."
