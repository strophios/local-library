# pattern: Imperative Shell
"""Tests for synthetic PDF generation pipeline."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from tests.extraction.synthetic.generate import (
    TIER_CONFIGS,
    BlurConfig,
    NoiseTier,
    RotationConfig,
    TierConfig,
    apply_noise,
    content_hash,
    create_image_pdf,
    derive_page_seed,
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

    def test_strips_annotations_before_conversion(self, sample_source: Path, tmp_path: Path):
        """Annotations should not appear in the generated PDF."""
        output = tmp_path / "output.pdf"
        generate_clean_pdf(sample_source, output)
        assert output.exists()

        # Extract text from PDF to verify annotations are absent
        import pymupdf

        doc = pymupdf.open(str(output))
        try:
            full_text = ""
            for page in doc:
                full_text += page.get_text()
        finally:
            doc.close()

        # Annotation markers should not appear in extracted text
        assert "<!-- feature:" not in full_text, "Generated PDF contains annotation opening markers"
        assert "<!-- /feature -->" not in full_text, (
            "Generated PDF contains annotation closing markers"
        )

    def test_multi_page_produces_multiple_pages(self, multi_page_source: Path, tmp_path: Path):
        output = tmp_path / "multi.pdf"
        generate_clean_pdf(multi_page_source, output)

        import pymupdf

        doc = pymupdf.open(str(output))
        try:
            assert len(doc) >= 2, (
                f"Expected 2+ pages but got {len(doc)}. Multi-page fixture may need more content."
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

    def test_multi_page_renders_all_pages(self, multi_page_source: Path, tmp_path: Path):
        pdf_path = tmp_path / "multi.pdf"
        generate_clean_pdf(multi_page_source, pdf_path)

        images = render_pages_to_images(pdf_path, dpi=150)
        assert len(images) >= 2


class TestApplyNoise:
    """Test noise application to PIL Images."""

    @staticmethod
    def _make_white_image() -> Image.Image:
        return Image.new("RGB", (200, 200), (255, 255, 255))

    def test_tier_clean_embedded_raises_value_error(self):
        img = self._make_white_image()
        with pytest.raises(ValueError, match="CLEAN_EMBEDDED is embedded text"):
            apply_noise(img, NoiseTier.CLEAN_EMBEDDED)

    def test_tier_clean_ocr_no_visible_noise(self):
        img = self._make_white_image()
        result = apply_noise(img, NoiseTier.CLEAN_OCR)
        # Should be unchanged (just image, no noise)
        np.testing.assert_array_equal(np.array(result), np.array(img))

    def test_tier_moderate_applies_blur_and_rotation(self):
        img = self._make_white_image()
        result = apply_noise(img, NoiseTier.MODERATE_SCAN)
        # Rotation with expand=True may change dimensions
        assert result.size[0] > 0
        assert result.size[1] > 0
        # Pixel data should differ due to blur, rotation, and noise
        assert not np.array_equal(np.array(result), np.array(img))

    def test_tier_degraded_applies_heavy_transforms(self):
        img = self._make_white_image()
        result = apply_noise(img, NoiseTier.DEGRADED)
        assert result.size[0] > 0
        # Pixel data should differ due to heavy transforms
        assert not np.array_equal(np.array(result), np.array(img))

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
                assert len(doc) >= 2, f"Tier {tier}: expected 2+ pages, got {len(doc)}"
            finally:
                doc.close()


class TestConfigDataclasses:
    """Test config dataclass properties required for the noise pipeline."""

    def test_blur_config_is_frozen(self):
        config = BlurConfig(radius_range=(0.5, 1.5))
        with pytest.raises(AttributeError):
            config.radius_range = (1.0, 2.0)  # type: ignore[misc]

    def test_tier_config_is_hashable(self):
        config = TierConfig(
            blur=BlurConfig(radius_range=(0.5, 1.5)),
            rotation=RotationConfig(angle_range=(-1.0, 1.0)),
        )
        assert hash(config) is not None
        s = {config}  # set insertion requires hashable
        assert len(s) == 1

    def test_tier_config_defaults_to_all_none(self):
        config = TierConfig()
        assert config.blur is None
        assert config.rotation is None
        assert config.gaussian_noise is None
        assert config.contrast is None
        assert config.scanner_dust is None
        assert config.spatial_variation is None
        assert config.occlusion is None

    def test_equal_configs_have_equal_hashes(self):
        config1 = TierConfig(blur=BlurConfig(radius_range=(0.5, 1.5)))
        config2 = TierConfig(blur=BlurConfig(radius_range=(0.5, 1.5)))
        assert config1 == config2
        assert hash(config1) == hash(config2)

    def test_different_configs_are_unequal(self):
        config1 = TierConfig(blur=BlurConfig(radius_range=(0.5, 1.5)))
        config2 = TierConfig(blur=BlurConfig(radius_range=(1.0, 2.0)))
        assert config1 != config2


class TestTierConfigs:
    """Test TIER_CONFIGS dict structure and current-value preservation."""

    def test_all_tiers_present(self):
        for tier in NoiseTier:
            assert tier in TIER_CONFIGS

    def test_clean_embedded_has_no_config(self):
        assert TIER_CONFIGS[NoiseTier.CLEAN_EMBEDDED] is None

    def test_clean_ocr_has_empty_config(self):
        config = TIER_CONFIGS[NoiseTier.CLEAN_OCR]
        assert isinstance(config, TierConfig)
        assert config.blur is None
        assert config.rotation is None
        assert config.gaussian_noise is None

    def test_moderate_scan_preserves_current_params(self):
        config = TIER_CONFIGS[NoiseTier.MODERATE_SCAN]
        assert config is not None
        assert config.blur.radius_range == (0.5, 0.5)
        assert config.rotation.angle_range == (-1.0, 1.0)
        assert config.gaussian_noise.sigma_range == (5.0, 5.0)
        assert config.contrast is None

    def test_degraded_preserves_current_params(self):
        config = TIER_CONFIGS[NoiseTier.DEGRADED]
        assert config is not None
        assert config.blur.radius_range == (1.5, 1.5)
        assert config.rotation.angle_range == (-3.0, 3.0)
        assert config.contrast.factor_range == (0.7, 0.7)
        assert config.gaussian_noise.sigma_range == (25.0, 25.0)

    def test_entire_config_tree_is_hashable(self):
        """Full config tree must be hashable for cache invalidation via repr()."""
        for tier in NoiseTier:
            config = TIER_CONFIGS[tier]
            if config is not None:
                hash(config)  # Should not raise


class TestDerivePageSeed:
    """Test per-page seed derivation for deterministic per-page variation."""

    def test_deterministic_same_inputs(self):
        seed1 = derive_page_seed(NoiseTier.MODERATE_SCAN, "climate_modeling", 0)
        seed2 = derive_page_seed(NoiseTier.MODERATE_SCAN, "climate_modeling", 0)
        assert seed1 == seed2

    def test_different_pages_different_seeds(self):
        seed0 = derive_page_seed(NoiseTier.MODERATE_SCAN, "climate_modeling", 0)
        seed1 = derive_page_seed(NoiseTier.MODERATE_SCAN, "climate_modeling", 1)
        assert seed0 != seed1

    def test_different_documents_different_seeds(self):
        seed_a = derive_page_seed(NoiseTier.MODERATE_SCAN, "climate_modeling", 0)
        seed_b = derive_page_seed(NoiseTier.MODERATE_SCAN, "neural_architecture", 0)
        assert seed_a != seed_b

    def test_different_tiers_different_seeds(self):
        seed_t2 = derive_page_seed(NoiseTier.MODERATE_SCAN, "climate_modeling", 0)
        seed_t3 = derive_page_seed(NoiseTier.DEGRADED, "climate_modeling", 0)
        assert seed_t2 != seed_t3

    def test_clean_embedded_raises_key_error(self):
        """CLEAN_EMBEDDED has no tier seed -- cannot derive page seeds."""
        with pytest.raises(KeyError):
            derive_page_seed(NoiseTier.CLEAN_EMBEDDED, "doc", 0)

    def test_seeds_produce_different_random_sequences(self):
        """Derived seeds should produce visibly different RandomState output."""
        seed0 = derive_page_seed(NoiseTier.MODERATE_SCAN, "doc", 0)
        seed1 = derive_page_seed(NoiseTier.MODERATE_SCAN, "doc", 1)
        rng0 = np.random.RandomState(seed0)
        rng1 = np.random.RandomState(seed1)
        assert not np.array_equal(rng0.random(10), rng1.random(10))
