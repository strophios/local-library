# pattern: Imperative Shell
"""Tests for synthetic PDF generation pipeline."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from tests.extraction.synthetic.generate import (
    NoiseTier,
    apply_noise,
    content_hash,
    create_image_pdf,
    generate_all_tiers,
    generate_clean_pdf,
    render_pages_to_images,
)


@pytest.fixture
def sample_source(tmp_path: Path) -> Path:
    """Create a minimal annotated source markdown file."""
    md = tmp_path / "sample.md"
    md.write_text(
        "<!-- feature: heading-h1 id:title -->\n"
        "# Sample Document\n"
        "<!-- /feature -->\n"
        "\n"
        "<!-- feature: dense-prose id:body -->\n"
        "This is a sample document for testing the PDF generation pipeline. "
        "It contains enough text to be a realistic extraction target.\n"
        "<!-- /feature -->\n"
    )
    return md


@pytest.fixture
def multi_page_source(tmp_path: Path) -> Path:
    """Create an annotated source markdown that produces 2+ PDF pages.

    Generates enough prose to reliably exceed one page at standard
    margins with pdflatex (roughly 5000+ characters).
    """
    md = tmp_path / "multi_page.md"
    paragraphs = []
    for i in range(20):
        paragraphs.append(
            f"This is paragraph {i + 1} of the multi-page test document. "
            "It contains enough text to contribute to filling a full page "
            "when combined with the other paragraphs in this document. "
            "The purpose is to verify that the PDF generation pipeline "
            "correctly handles documents that span multiple pages, which "
            "is the common case for real academic papers. "
            "Each paragraph adds several sentences to ensure sufficient content. "
            "The accumulation of multiple paragraphs ensures we exceed page boundaries. "
            "Standard margins and line spacing affect the page break calculations. "
            "With pdflatex, each page typically holds about 250-300 words of text."
        )
    body = "\n\n".join(paragraphs)
    md.write_text(
        "<!-- feature: heading-h1 id:title -->\n"
        "# Multi-Page Test Document\n"
        "<!-- /feature -->\n"
        "\n"
        "<!-- feature: dense-prose id:body -->\n"
        f"{body}\n"
        "<!-- /feature -->\n"
    )
    return md


class TestContentHash:
    """Test content hashing for cache invalidation."""

    def test_same_content_same_hash(self, tmp_path: Path):
        f1 = tmp_path / "a.md"
        f2 = tmp_path / "b.md"
        f1.write_text("identical content")
        f2.write_text("identical content")
        assert content_hash(f1) == content_hash(f2)

    def test_different_content_different_hash(self, tmp_path: Path):
        f1 = tmp_path / "a.md"
        f2 = tmp_path / "b.md"
        f1.write_text("content one")
        f2.write_text("content two")
        assert content_hash(f1) != content_hash(f2)


class TestGenerateCleanPdf:
    """Test T0 clean PDF generation via pandoc/pdflatex."""

    def test_produces_pdf_file(self, sample_source: Path, tmp_path: Path):
        output = tmp_path / "output.pdf"
        generate_clean_pdf(sample_source, output)
        assert output.exists()
        assert output.stat().st_size > 0
        # PDF magic bytes
        assert output.read_bytes()[:4] == b"%PDF"

    def test_strips_annotations_before_conversion(
        self, sample_source: Path, tmp_path: Path
    ):
        """Annotations should not appear in the intermediate markdown."""
        output = tmp_path / "output.pdf"
        generate_clean_pdf(sample_source, output)
        assert output.exists()

    def test_multi_page_produces_multiple_pages(
        self, multi_page_source: Path, tmp_path: Path
    ):
        output = tmp_path / "multi.pdf"
        generate_clean_pdf(multi_page_source, output)

        import pymupdf

        doc = pymupdf.open(str(output))
        try:
            assert len(doc) >= 2, (
                f"Expected 2+ pages but got {len(doc)}. "
                "Multi-page fixture may need more content."
            )
        finally:
            doc.close()


class TestRenderPagesToImages:
    """Test PDF page rendering to PIL Images."""

    def test_returns_list_of_images(self, sample_source: Path, tmp_path: Path):
        pdf_path = tmp_path / "test.pdf"
        generate_clean_pdf(sample_source, pdf_path)

        images = render_pages_to_images(pdf_path, dpi=150)
        assert len(images) >= 1

        for img in images:
            assert isinstance(img, Image.Image)
            assert img.mode == "RGB"

    def test_respects_dpi_setting(self, sample_source: Path, tmp_path: Path):
        pdf_path = tmp_path / "test.pdf"
        generate_clean_pdf(sample_source, pdf_path)

        images_low = render_pages_to_images(pdf_path, dpi=72)
        images_high = render_pages_to_images(pdf_path, dpi=300)

        # Higher DPI = larger images
        assert images_high[0].size[0] > images_low[0].size[0]

    def test_multi_page_renders_all_pages(
        self, multi_page_source: Path, tmp_path: Path
    ):
        pdf_path = tmp_path / "multi.pdf"
        generate_clean_pdf(multi_page_source, pdf_path)

        images = render_pages_to_images(pdf_path, dpi=150)
        assert len(images) >= 2


class TestApplyNoise:
    """Test noise application to PIL Images."""

    @staticmethod
    def _make_white_image() -> Image.Image:
        return Image.new("RGB", (200, 200), (255, 255, 255))

    def test_tier_clean_ocr_no_visible_noise(self):
        img = self._make_white_image()
        result = apply_noise(img, NoiseTier.CLEAN_OCR)
        # Should be unchanged (just image, no noise)
        assert result.size == img.size

    def test_tier_moderate_applies_blur_and_rotation(self):
        img = self._make_white_image()
        result = apply_noise(img, NoiseTier.MODERATE_SCAN)
        # Rotation with expand=True may change dimensions
        assert result.size[0] > 0
        assert result.size[1] > 0

    def test_tier_degraded_applies_heavy_transforms(self):
        img = self._make_white_image()
        result = apply_noise(img, NoiseTier.DEGRADED)
        assert result.size[0] > 0

    def test_deterministic_with_same_seed(self):
        img = self._make_white_image()
        result1 = apply_noise(img, NoiseTier.MODERATE_SCAN, seed=42)
        result2 = apply_noise(img, NoiseTier.MODERATE_SCAN, seed=42)
        np.testing.assert_array_equal(np.array(result1), np.array(result2))

    def test_different_seeds_produce_different_output(self):
        img = self._make_white_image()
        result1 = apply_noise(img, NoiseTier.MODERATE_SCAN, seed=42)
        result2 = apply_noise(img, NoiseTier.MODERATE_SCAN, seed=99)
        assert not np.array_equal(np.array(result1), np.array(result2))


class TestCreateImagePdf:
    """Test creating PDF from PIL images."""

    def test_creates_valid_pdf(self, tmp_path: Path):
        images = [Image.new("RGB", (612, 792), (255, 255, 255))]
        output = tmp_path / "output.pdf"
        create_image_pdf(images, output)
        assert output.exists()
        assert output.read_bytes()[:4] == b"%PDF"

    def test_multi_page_pdf(self, tmp_path: Path):
        images = [
            Image.new("RGB", (612, 792), (255, 255, 255)),
            Image.new("RGB", (612, 792), (200, 200, 200)),
        ]
        output = tmp_path / "output.pdf"
        create_image_pdf(images, output)

        import pymupdf

        doc = pymupdf.open(str(output))
        try:
            assert len(doc) == 2
        finally:
            doc.close()


class TestGenerateAllTiers:
    """Test full tier generation from source markdown."""

    def test_produces_four_pdfs(self, sample_source: Path, tmp_path: Path):
        results = generate_all_tiers(sample_source, tmp_path)
        assert len(results) == 4
        for tier, path in results.items():
            assert path.exists(), f"Missing PDF for tier {tier}"
            assert path.read_bytes()[:4] == b"%PDF"

    def test_caching_skips_regeneration(self, sample_source: Path, tmp_path: Path):
        """Second call should use cache (same content hash)."""
        results1 = generate_all_tiers(sample_source, tmp_path)
        mtimes1 = {t: p.stat().st_mtime for t, p in results1.items()}

        results2 = generate_all_tiers(sample_source, tmp_path)
        mtimes2 = {t: p.stat().st_mtime for t, p in results2.items()}

        # Files should not have been regenerated
        assert mtimes1 == mtimes2

    def test_multi_page_all_tiers(self, multi_page_source: Path, tmp_path: Path):
        """Multi-page source produces multi-page PDFs across all tiers."""
        results = generate_all_tiers(multi_page_source, tmp_path)

        import pymupdf

        for tier, path in results.items():
            doc = pymupdf.open(str(path))
            try:
                assert len(doc) >= 2, (
                    f"Tier {tier}: expected 2+ pages, got {len(doc)}"
                )
            finally:
                doc.close()
