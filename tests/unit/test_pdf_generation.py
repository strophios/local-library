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
    ContrastConfig,
    GaussianNoiseConfig,
    NoiseTier,
    OcclusionConfig,
    RotationConfig,
    ScannerDustConfig,
    SpatialVariationConfig,
    TierConfig,
    apply_blur,
    apply_contrast,
    apply_gaussian_noise,
    apply_noise_pipeline,
    apply_occlusion,
    apply_rotation,
    apply_scanner_dust,
    apply_spatial_variation,
    content_hash,
    create_image_pdf,
    derive_page_seed,
    generate_all_tiers,
    generate_clean_pdf,
    generation_hash,
    generation_params_hash,
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
    """Test noise application to PIL Images (via pipeline)."""

    @staticmethod
    def _make_white_image() -> Image.Image:
        return Image.new("RGB", (200, 200), (255, 255, 255))

    def test_tier_clean_embedded_raises_value_error(self):
        img = self._make_white_image()
        with pytest.raises(ValueError, match="CLEAN_EMBEDDED is embedded text"):
            apply_noise_pipeline(img, NoiseTier.CLEAN_EMBEDDED, "doc", 0)

    def test_tier_clean_ocr_no_visible_noise(self):
        img = self._make_white_image()
        result = apply_noise_pipeline(img, NoiseTier.CLEAN_OCR, "doc", 0)
        np.testing.assert_array_equal(np.array(result), np.array(img))

    def test_tier_moderate_applies_transforms(self):
        img = self._make_white_image()
        result = apply_noise_pipeline(img, NoiseTier.MODERATE_SCAN, "doc", 0)
        assert result.size[0] > 0
        assert result.size[1] > 0
        assert not np.array_equal(np.array(result), np.array(img))

    def test_tier_degraded_applies_heavy_transforms(self):
        img = self._make_white_image()
        result = apply_noise_pipeline(img, NoiseTier.DEGRADED, "doc", 0)
        assert result.size[0] > 0
        assert not np.array_equal(np.array(result), np.array(img))

    def test_deterministic_with_same_inputs(self):
        img = self._make_white_image()
        result1 = apply_noise_pipeline(img, NoiseTier.MODERATE_SCAN, "doc", 0)
        result2 = apply_noise_pipeline(img, NoiseTier.MODERATE_SCAN, "doc", 0)
        np.testing.assert_array_equal(np.array(result1), np.array(result2))

    def test_different_pages_produce_different_output(self):
        img = self._make_white_image()
        result1 = apply_noise_pipeline(img, NoiseTier.MODERATE_SCAN, "doc", 0)
        result2 = apply_noise_pipeline(img, NoiseTier.MODERATE_SCAN, "doc", 1)
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

    def test_uses_generation_hash_file(self, sample_source: Path, tmp_path: Path):
        """Should write .generation_hash, not .content_hash."""
        generate_all_tiers(sample_source, tmp_path)
        assert (tmp_path / ".generation_hash").exists()
        assert not (tmp_path / ".content_hash").exists()

    def test_cache_miss_on_stale_hash(self, sample_source: Path, tmp_path: Path):
        """Stale hash (simulating param change) should trigger regeneration."""
        generate_all_tiers(sample_source, tmp_path)
        hash_file = tmp_path / ".generation_hash"
        hash_file.write_text("stale_hash_from_old_params")
        generate_all_tiers(sample_source, tmp_path)
        assert hash_file.read_text().strip() != "stale_hash_from_old_params"

    def test_old_content_hash_file_ignored(self, sample_source: Path, tmp_path: Path):
        """Old .content_hash files should not produce cache hits."""
        generate_all_tiers(sample_source, tmp_path)
        gen_hash = tmp_path / ".generation_hash"
        gen_hash.unlink()
        (tmp_path / ".content_hash").write_text("old_content_hash")
        generate_all_tiers(sample_source, tmp_path)
        assert gen_hash.exists()


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

    def test_moderate_scan_has_calibrated_params(self):
        config = TIER_CONFIGS[NoiseTier.MODERATE_SCAN]
        assert config is not None
        assert config.blur.radius_range == (1.0, 2.0)
        assert config.rotation.angle_range == (-3.0, 3.0)
        assert config.gaussian_noise.sigma_range == (8.0, 12.0)
        assert config.contrast.factor_range == (0.85, 0.85)
        assert config.scanner_dust is not None
        assert config.spatial_variation is not None
        assert config.occlusion is None  # Only on T3

    def test_degraded_has_calibrated_params(self):
        config = TIER_CONFIGS[NoiseTier.DEGRADED]
        assert config is not None
        assert config.blur.radius_range == (2.0, 3.0)
        assert config.rotation.angle_range == (-5.0, 5.0)
        assert config.gaussian_noise.sigma_range == (12.0, 18.0)
        assert config.contrast.factor_range == (0.6, 0.75)
        assert config.scanner_dust is not None
        assert config.spatial_variation is not None
        assert config.occlusion is not None
        assert config.occlusion.mark_count_range == (1, 2)

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


class TestIndividualArtifacts:
    """Test individual artifact functions with config + rng signature."""

    @staticmethod
    def _make_white_image() -> Image.Image:
        return Image.new("RGB", (200, 200), (255, 255, 255))

    def test_apply_blur_modifies_image(self):
        img = self._make_white_image()
        arr = np.array(img)
        arr[100, :, :] = 0  # Black horizontal line
        img = Image.fromarray(arr)
        rng = np.random.RandomState(42)
        result = apply_blur(img, BlurConfig(radius_range=(2.0, 2.0)), rng)
        result_arr = np.array(result)
        assert result_arr[99, 100, 0] < 255  # Blur spread to adjacent row

    def test_apply_rotation_changes_dimensions(self):
        img = self._make_white_image()
        rng = np.random.RandomState(42)
        result = apply_rotation(img, RotationConfig(angle_range=(5.0, 5.0)), rng)
        assert result.size != img.size

    def test_apply_contrast_reduces_range(self):
        img = self._make_white_image()
        arr = np.array(img)
        arr[:100, :, :] = 0  # Half black, half white
        img = Image.fromarray(arr)
        rng = np.random.RandomState(42)
        result = apply_contrast(img, ContrastConfig(factor_range=(0.5, 0.5)), rng)
        result_arr = np.array(result)
        assert result_arr[50, 100, 0] > 0  # Was pure black, now lighter
        assert result_arr[150, 100, 0] < 255  # Was pure white, now darker

    def test_apply_gaussian_noise_adds_variation(self):
        img = self._make_white_image()
        rng = np.random.RandomState(42)
        result = apply_gaussian_noise(img, GaussianNoiseConfig(sigma_range=(20.0, 20.0)), rng)
        result_arr = np.array(result)
        assert result_arr.std() > 0

    def test_artifact_determinism(self):
        """Same config + seed produces identical output."""
        img = self._make_white_image()
        config = GaussianNoiseConfig(sigma_range=(10.0, 10.0))
        result1 = apply_gaussian_noise(img, config, np.random.RandomState(42))
        result2 = apply_gaussian_noise(img, config, np.random.RandomState(42))
        np.testing.assert_array_equal(np.array(result1), np.array(result2))

    def test_range_sampling_varies_with_rng(self):
        """When range has width, different rng states produce different results."""
        img = self._make_white_image()
        arr = np.array(img)
        arr[100:150, 100:150, :] = 0  # Black square (blur target)
        img = Image.fromarray(arr)
        config = BlurConfig(radius_range=(0.5, 3.0))
        result1 = apply_blur(img, config, np.random.RandomState(1))
        result2 = apply_blur(img, config, np.random.RandomState(2))
        # Different blur radii should produce visibly different blurs
        assert not np.array_equal(np.array(result1), np.array(result2))


class TestApplyNoisePipeline:
    """Test config-driven noise pipeline that replaces apply_noise()."""

    @staticmethod
    def _make_white_image() -> Image.Image:
        return Image.new("RGB", (200, 200), (255, 255, 255))

    def test_clean_embedded_raises_value_error(self):
        img = self._make_white_image()
        with pytest.raises(ValueError, match="CLEAN_EMBEDDED"):
            apply_noise_pipeline(img, NoiseTier.CLEAN_EMBEDDED, "doc", 0)

    def test_clean_ocr_returns_unmodified_copy(self):
        img = self._make_white_image()
        result = apply_noise_pipeline(img, NoiseTier.CLEAN_OCR, "doc", 0)
        np.testing.assert_array_equal(np.array(result), np.array(img))
        assert result is not img  # Must be a copy

    def test_moderate_scan_modifies_image(self):
        img = self._make_white_image()
        result = apply_noise_pipeline(img, NoiseTier.MODERATE_SCAN, "doc", 0)
        assert not np.array_equal(np.array(result), np.array(img))

    def test_degraded_modifies_image(self):
        img = self._make_white_image()
        result = apply_noise_pipeline(img, NoiseTier.DEGRADED, "doc", 0)
        assert not np.array_equal(np.array(result), np.array(img))

    def test_deterministic_same_inputs(self):
        img = self._make_white_image()
        result1 = apply_noise_pipeline(img, NoiseTier.MODERATE_SCAN, "doc", 0)
        result2 = apply_noise_pipeline(img, NoiseTier.MODERATE_SCAN, "doc", 0)
        np.testing.assert_array_equal(np.array(result1), np.array(result2))

    def test_different_pages_produce_different_output(self):
        """Per-page seed derivation produces per-page variation."""
        img = self._make_white_image()
        result0 = apply_noise_pipeline(img, NoiseTier.MODERATE_SCAN, "doc", 0)
        result1 = apply_noise_pipeline(img, NoiseTier.MODERATE_SCAN, "doc", 1)
        assert not np.array_equal(np.array(result0), np.array(result1))

    def test_different_documents_produce_different_output(self):
        img = self._make_white_image()
        result_a = apply_noise_pipeline(img, NoiseTier.MODERATE_SCAN, "doc_a", 0)
        result_b = apply_noise_pipeline(img, NoiseTier.MODERATE_SCAN, "doc_b", 0)
        assert not np.array_equal(np.array(result_a), np.array(result_b))


class TestApplyScannerDust:
    """Test scanner dust speck and roller mark artifact."""

    @staticmethod
    def _make_white_image() -> Image.Image:
        return Image.new("RGB", (400, 400), (255, 255, 255))

    def test_adds_dark_specks(self):
        img = self._make_white_image()
        config = ScannerDustConfig(
            speck_count_range=(20, 20),
            speck_size_range=(2, 5),
            roller_mark_count_range=(0, 0),
        )
        result = apply_scanner_dust(img, config, np.random.RandomState(42))
        result_arr = np.array(result)
        assert result_arr.min() < 200

    def test_adds_roller_marks(self):
        img = self._make_white_image()
        config = ScannerDustConfig(
            speck_count_range=(0, 0),
            speck_size_range=(2, 2),
            roller_mark_count_range=(3, 3),
        )
        result = apply_scanner_dust(img, config, np.random.RandomState(42))
        assert not np.array_equal(np.array(result), np.array(img))

    def test_deterministic(self):
        img = self._make_white_image()
        config = ScannerDustConfig(
            speck_count_range=(10, 10),
            speck_size_range=(2, 5),
            roller_mark_count_range=(1, 1),
        )
        r1 = apply_scanner_dust(img, config, np.random.RandomState(42))
        r2 = apply_scanner_dust(img, config, np.random.RandomState(42))
        np.testing.assert_array_equal(np.array(r1), np.array(r2))

    def test_zero_counts_returns_unmodified(self):
        img = self._make_white_image()
        config = ScannerDustConfig(
            speck_count_range=(0, 0),
            speck_size_range=(2, 2),
            roller_mark_count_range=(0, 0),
        )
        result = apply_scanner_dust(img, config, np.random.RandomState(42))
        np.testing.assert_array_equal(np.array(result), np.array(img))


class TestApplySpatialVariation:
    """Test spatially varying focus/brightness degradation."""

    @staticmethod
    def _make_white_image() -> Image.Image:
        return Image.new("RGB", (400, 400), (255, 255, 255))

    def test_modifies_image(self):
        img = self._make_white_image()
        config = SpatialVariationConfig(
            blur_intensity_range=(3.0, 3.0),
            brightness_reduction_range=(0.3, 0.3),
            blob_scale=50,
        )
        result = apply_spatial_variation(img, config, np.random.RandomState(42))
        result_arr = np.array(result)
        assert result_arr.min() < 250

    def test_spatial_non_uniformity(self):
        """Different regions should have different degradation levels."""
        img = self._make_white_image()
        config = SpatialVariationConfig(
            blur_intensity_range=(3.0, 3.0),
            brightness_reduction_range=(0.4, 0.4),
            blob_scale=50,
        )
        result = apply_spatial_variation(img, config, np.random.RandomState(42))
        result_arr = np.array(result)
        top_half_mean = result_arr[:200].mean()
        bottom_half_mean = result_arr[200:].mean()
        assert top_half_mean != bottom_half_mean

    def test_deterministic(self):
        img = self._make_white_image()
        config = SpatialVariationConfig(
            blur_intensity_range=(2.0, 2.0),
            brightness_reduction_range=(0.2, 0.2),
            blob_scale=50,
        )
        r1 = apply_spatial_variation(img, config, np.random.RandomState(42))
        r2 = apply_spatial_variation(img, config, np.random.RandomState(42))
        np.testing.assert_array_equal(np.array(r1), np.array(r2))


class TestApplyOcclusion:
    """Test edge-biased occlusion marks."""

    @staticmethod
    def _make_white_image() -> Image.Image:
        return Image.new("RGB", (400, 400), (255, 255, 255))

    def test_adds_dark_marks(self):
        img = self._make_white_image()
        config = OcclusionConfig(
            mark_count_range=(3, 3),
            mark_opacity_range=(0.5, 0.8),
            edge_bias=0.7,
        )
        result = apply_occlusion(img, config, np.random.RandomState(42))
        result_arr = np.array(result)
        assert result_arr.min() < 200

    def test_returns_rgb_not_rgba(self):
        """Output should be converted back to RGB from internal RGBA."""
        img = self._make_white_image()
        config = OcclusionConfig(
            mark_count_range=(1, 1),
            mark_opacity_range=(0.5, 0.5),
            edge_bias=0.5,
        )
        result = apply_occlusion(img, config, np.random.RandomState(42))
        assert result.mode == "RGB"

    def test_deterministic(self):
        img = self._make_white_image()
        config = OcclusionConfig(
            mark_count_range=(2, 2),
            mark_opacity_range=(0.4, 0.6),
            edge_bias=0.8,
        )
        r1 = apply_occlusion(img, config, np.random.RandomState(42))
        r2 = apply_occlusion(img, config, np.random.RandomState(42))
        np.testing.assert_array_equal(np.array(r1), np.array(r2))

    def test_zero_marks_returns_unmodified(self):
        img = self._make_white_image()
        config = OcclusionConfig(
            mark_count_range=(0, 0),
            mark_opacity_range=(0.5, 0.5),
            edge_bias=0.5,
        )
        result = apply_occlusion(img, config, np.random.RandomState(42))
        np.testing.assert_array_equal(np.array(result), np.array(img))


class TestCacheHashFunctions:
    """Test generation parameter and combined hash functions."""

    def test_params_hash_deterministic(self):
        h1 = generation_params_hash()
        h2 = generation_params_hash()
        assert h1 == h2

    def test_params_hash_changes_with_config(self):
        h1 = generation_params_hash(TIER_CONFIGS)
        modified = dict(TIER_CONFIGS)
        modified[NoiseTier.MODERATE_SCAN] = TierConfig(
            blur=BlurConfig(radius_range=(9.0, 9.0)),
        )
        h2 = generation_params_hash(modified)
        assert h1 != h2

    def test_generation_hash_deterministic(self, tmp_path: Path):
        f = tmp_path / "test.md"
        f.write_text("test content")
        assert generation_hash(f) == generation_hash(f)

    def test_generation_hash_changes_with_source(self, tmp_path: Path):
        f1 = tmp_path / "a.md"
        f2 = tmp_path / "b.md"
        f1.write_text("content one")
        f2.write_text("content two")
        assert generation_hash(f1) != generation_hash(f2)

    def test_generation_hash_changes_with_params(self, tmp_path: Path):
        f = tmp_path / "test.md"
        f.write_text("same content")
        h1 = generation_hash(f, TIER_CONFIGS)
        modified = dict(TIER_CONFIGS)
        modified[NoiseTier.MODERATE_SCAN] = TierConfig(
            blur=BlurConfig(radius_range=(9.0, 9.0)),
        )
        h2 = generation_hash(f, modified)
        assert h1 != h2
