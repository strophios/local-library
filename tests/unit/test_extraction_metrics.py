# pattern: Imperative Shell
"""Tests for extraction quality metrics (CER, WER)."""
from __future__ import annotations

from tests.extraction.synthetic.metrics import (
    character_error_rate,
    normalize_text,
    word_error_rate,
)


class TestNormalizeText:
    """Test text normalization for metric computation."""

    def test_strips_markdown_formatting(self):
        assert normalize_text("**bold** and *italic*") == "bold and italic"

    def test_collapses_whitespace(self):
        assert normalize_text("word   word\n\nword") == "word word word"

    def test_lowercases(self):
        assert normalize_text("Hello WORLD") == "hello world"

    def test_strips_heading_markers(self):
        assert normalize_text("## Section Title") == "section title"

    def test_empty_string(self):
        assert normalize_text("") == ""

    def test_preserves_alphanumeric_content(self):
        assert normalize_text("Section 3.2: Results") == "section 3.2: results"


class TestCharacterErrorRate:
    """Test CER computation."""

    def test_identical_strings(self):
        assert character_error_rate("hello world", "hello world") == 0.0

    def test_single_substitution(self):
        # "the" vs "tbe" — 1 char substitution over 3 chars
        cer = character_error_rate("the", "tbe")
        assert abs(cer - 1.0 / 3.0) < 1e-6

    def test_insertion(self):
        # "cat" vs "cart" — 1 insertion over 3 reference chars
        cer = character_error_rate("cat", "cart")
        assert abs(cer - 1.0 / 3.0) < 1e-6

    def test_deletion(self):
        # "cart" vs "cat" — 1 deletion over 4 reference chars
        cer = character_error_rate("cart", "cat")
        assert abs(cer - 1.0 / 4.0) < 1e-6

    def test_empty_reference_returns_zero(self):
        assert character_error_rate("", "") == 0.0

    def test_empty_reference_nonempty_hypothesis(self):
        # Edge case: no reference to compare against
        assert character_error_rate("", "abc") == 0.0

    def test_completely_wrong(self):
        # All characters wrong
        cer = character_error_rate("abc", "xyz")
        assert cer == 1.0

    def test_normalizes_before_comparing(self):
        # Formatting differences shouldn't count as errors
        cer = character_error_rate("**bold text**", "bold text")
        assert cer == 0.0


class TestWordErrorRate:
    """Test WER computation."""

    def test_identical_strings(self):
        assert word_error_rate("hello world", "hello world") == 0.0

    def test_single_word_substitution(self):
        # 1 word wrong out of 3
        wer = word_error_rate("the big cat", "the big dog")
        assert abs(wer - 1.0 / 3.0) < 1e-6

    def test_word_insertion(self):
        # "the cat" vs "the big cat" — 1 insertion over 2 reference words
        wer = word_error_rate("the cat", "the big cat")
        assert abs(wer - 1.0 / 2.0) < 1e-6

    def test_word_merge(self):
        # "of the" vs "ofthe" — 2 reference words become 1 wrong word
        wer = word_error_rate("of the", "ofthe")
        assert wer > 0.0

    def test_empty_reference(self):
        assert word_error_rate("", "") == 0.0

    def test_normalizes_before_comparing(self):
        wer = word_error_rate("## Section Title", "section title")
        assert wer == 0.0
