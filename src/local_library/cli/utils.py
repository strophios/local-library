"""CLI utility functions."""

# pattern: Mixed (Functional Core utilities + Imperative Shell resolve_identifier)

from typing import TYPE_CHECKING, Protocol

from local_library.core import ErrorCode, LookupError
from local_library.core.models import Document

if TYPE_CHECKING:
    from local_library.core import Library


class LibraryProtocol(Protocol):
    """Protocol for Library methods used by resolve_identifier."""

    def get(self, doc_id: str) -> Document: ...
    def get_by_citekey(self, citekey: str) -> Document | None: ...
    def get_all_citekeys(self) -> list[str]: ...


def levenshtein_distance(s1: str, s2: str) -> int:
    """Calculate Levenshtein (edit) distance between two strings.

    Args:
        s1: First string
        s2: Second string

    Returns:
        Minimum number of single-character edits (insertions, deletions,
        substitutions) to transform s1 into s2
    """
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)

    if len(s2) == 0:
        return len(s1)

    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            # Cost is 0 if characters match, 1 otherwise
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row

    return previous_row[-1]


def suggest_citekeys(
    query: str,
    all_citekeys: list[str],
    max_suggestions: int = 3,
    max_distance: int = 3,
) -> list[str]:
    """Generate citekey suggestions for a failed lookup.

    Prioritizes prefix matches, then falls back to Levenshtein distance.

    Args:
        query: The citekey that wasn't found (without @ prefix)
        all_citekeys: All available citekeys in the library
        max_suggestions: Maximum number of suggestions to return
        max_distance: Maximum Levenshtein distance for fuzzy matches

    Returns:
        List of suggested citekeys, prefix matches first
    """
    if not all_citekeys:
        return []

    # First: prefix matches
    prefix_matches = [ck for ck in all_citekeys if ck.startswith(query)]

    if len(prefix_matches) >= max_suggestions:
        return prefix_matches[:max_suggestions]

    # Second: Levenshtein distance for remaining slots
    remaining_slots = max_suggestions - len(prefix_matches)
    non_prefix = [ck for ck in all_citekeys if ck not in prefix_matches]

    # Calculate distances and filter
    with_distances = [
        (ck, levenshtein_distance(query, ck))
        for ck in non_prefix
    ]
    within_threshold = [
        (ck, dist) for ck, dist in with_distances if dist <= max_distance
    ]
    within_threshold.sort(key=lambda x: x[1])

    fuzzy_matches = [ck for ck, _ in within_threshold[:remaining_slots]]

    return prefix_matches + fuzzy_matches


def resolve_identifier(identifier: str, library: LibraryProtocol) -> Document:
    """Resolve a document identifier (UUID or @citekey) to a Document.

    Args:
        identifier: Either a UUID (full or partial) or @citekey
        library: Library instance for lookups

    Returns:
        The resolved Document

    Raises:
        LookupError: If document not found, with suggestions for citekey misses
    """
    if identifier.startswith("@"):
        # Citekey lookup
        citekey = identifier[1:]  # Strip @ prefix
        doc = library.get_by_citekey(citekey)

        if doc is not None:
            return doc

        # Not found - generate suggestions
        all_citekeys = library.get_all_citekeys()
        suggestions = suggest_citekeys(citekey, all_citekeys)

        raise LookupError(
            f"citekey not found: {citekey}",
            ErrorCode.NOT_FOUND,
            details={"citekey": citekey, "suggestions": suggestions},
        )

    # UUID lookup - delegate to Library.get() which handles partial matching
    return library.get(identifier)
