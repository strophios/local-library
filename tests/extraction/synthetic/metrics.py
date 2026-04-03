# pattern: Functional Core
"""Extraction quality metrics: Character Error Rate and Word Error Rate.

Follows the metric function pattern from tests/eval/retrieval_eval.py:
pure functions with NumPy-style docstrings, no I/O.
"""

from __future__ import annotations

import re

from rapidfuzz.distance import Levenshtein

_MARKDOWN_FORMATTING = re.compile(
    r"(?:"
    r"\*{1,3}|"  # bold/italic markers
    r"_{1,3}|"  # underscore bold/italic
    r"#{1,6}\s|"  # heading markers
    r"`{1,3}|"  # code markers
    r"~~"  # strikethrough
    r")"
)
_WHITESPACE = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    """Normalize text for metric comparison.

    Strips markdown formatting, collapses whitespace, lowercases.
    Used before CER/WER computation so formatting differences
    don't count as errors.

    Args:
        text: Raw markdown text.

    Returns:
        Normalized plain text.
    """
    result = _MARKDOWN_FORMATTING.sub("", text)
    result = _WHITESPACE.sub(" ", result)
    return result.strip().lower()


def character_error_rate(reference: str, hypothesis: str) -> float:
    """Compute Character Error Rate between reference and hypothesis.

    CER = edit_distance(ref, hyp) / len(ref)

    Both strings are normalized before comparison. Formatting differences
    (markdown markers, whitespace, case) are not counted as errors.

    Args:
        reference: Ground truth text (source markdown content).
        hypothesis: Extracted text to evaluate.

    Returns:
        CER in [0, inf). 0.0 means perfect match.
        Returns 0.0 if reference is empty.
    """
    ref = normalize_text(reference)
    hyp = normalize_text(hypothesis)

    if not ref:
        return 0.0

    distance = Levenshtein.distance(ref, hyp)
    return distance / len(ref)


def word_error_rate(reference: str, hypothesis: str) -> float:
    """Compute Word Error Rate between reference and hypothesis.

    WER = edit_distance(ref_words, hyp_words) / len(ref_words)

    Both strings are normalized before comparison. Word-level edit
    distance captures merge/split errors common in OCR output.

    Args:
        reference: Ground truth text (source markdown content).
        hypothesis: Extracted text to evaluate.

    Returns:
        WER in [0, inf). 0.0 means perfect match.
        Returns 0.0 if reference is empty.
    """
    ref = normalize_text(reference)
    hyp = normalize_text(hypothesis)

    ref_words = ref.split()
    hyp_words = hyp.split()

    if not ref_words:
        return 0.0

    distance = Levenshtein.distance(ref_words, hyp_words)
    return distance / len(ref_words)
