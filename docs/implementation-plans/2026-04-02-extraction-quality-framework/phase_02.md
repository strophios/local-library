## Phase 2: PDF Generation Pipeline

**Goal:** Produce 4 noise tiers from annotated source markdown via pandoc/pdflatex + Pillow.

---

<!-- START_TASK_1 -->
### Task 1: Add PDF generation dependencies

**Files:**
- Modify: `pyproject.toml:25-30` (add pymupdf and pypandoc-binary to dev deps)

**Step 1: Update dev dependencies**

In `pyproject.toml`, update the dev optional dependencies (after Phase 1 has added rapidfuzz):

```toml
[project.optional-dependencies]
dev = [
    "numpy>=1.24.0",
    "pillow>=10.0.0",
    "pymupdf>=1.25.0",
    "pypandoc-binary>=1.14",
    "pytest>=8.0.0",
    "pytest-cov>=4.0.0",
    "rapidfuzz>=3.0.0",
    "ruff>=0.8.0",
]
```

Note: numpy and Pillow are available as transitive dependencies (via sentence-transformers and marker-pdf), but are listed explicitly since test code imports them directly. This prevents breakage if upstream dependencies change.

**Step 2: Install and verify**

Run: `uv sync --extra dev`
Expected: pymupdf and pypandoc-binary install successfully

Run: `uv run python -c "import pymupdf; print(pymupdf.__version__)"`
Expected: Prints version number

Run: `uv run python -c "import pypandoc; print(pypandoc.get_pandoc_version())"`
Expected: Prints pandoc version number

**Step 3: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore: add pymupdf and pypandoc-binary dev dependencies for PDF generation"
```
<!-- END_TASK_1 -->

---

<!-- START_SUBCOMPONENT_A (tasks 2-3) -->

<!-- START_TASK_2 -->
### Task 2: Write PDF generation tests

**Files:**
- Create: `tests/unit/test_pdf_generation.py`

**Step 1: Write failing tests**

These tests verify the generation pipeline: annotation stripping → pandoc/pdflatex → noise tiers.
Tests involving `generate_clean_pdf` require pdflatex installed — verify with `which pdflatex` before running.

```python
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
    margins with pdflatex (roughly 3000+ characters).
    """
    md = tmp_path / "multi_page.md"
    paragraphs = []
    for i in range(8):
        paragraphs.append(
            f"This is paragraph {i + 1} of the multi-page test document. "
            "It contains enough text to contribute to filling a full page "
            "when combined with the other paragraphs in this document. "
            "The purpose is to verify that the PDF generation pipeline "
            "correctly handles documents that span multiple pages, which "
            "is the common case for real academic papers."
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
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_pdf_generation.py -v`
Expected: ImportError — `tests.extraction.synthetic.generate` does not exist

<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Implement PDF generation module

**Files:**
- Create: `tests/extraction/synthetic/generate.py`

**Step 1: Implement the module**

```python
# pattern: Imperative Shell
"""PDF generation pipeline for synthetic extraction quality tests.

Generates 4 noise tiers from annotated source markdown:
  T0 (CLEAN_EMBEDDED): pandoc/pdflatex with embedded text
  T1 (CLEAN_OCR): T0 rendered to images, re-composited as image-only PDF
  T2 (MODERATE_SCAN): T1 + slight blur, rotation, faint noise
  T3 (DEGRADED): T1 + heavy noise, skew, contrast reduction, bleed-through

Noise application is deterministic via numpy.random.RandomState (frozen
algorithm, guaranteed same output across numpy versions given same seed).
PDFs are cached via content hash to skip regeneration when source unchanged.
"""
from __future__ import annotations

import enum
import hashlib
import io
import logging
import tempfile
from pathlib import Path

import numpy as np
import pymupdf
from PIL import Image, ImageEnhance, ImageFilter

from tests.extraction.synthetic.annotations import strip_annotations

logger = logging.getLogger(__name__)


class NoiseTier(enum.Enum):
    """Noise degradation tiers for synthetic PDFs."""

    CLEAN_EMBEDDED = "T0_clean"
    CLEAN_OCR = "T1_ocr_needed"
    MODERATE_SCAN = "T2_moderate_scan"
    DEGRADED = "T3_degraded"


# Default seeds per tier for reproducibility
_TIER_SEEDS: dict[NoiseTier, int] = {
    NoiseTier.CLEAN_OCR: 0,
    NoiseTier.MODERATE_SCAN: 42,
    NoiseTier.DEGRADED: 137,
}

_RENDER_DPI = 300


def content_hash(file_path: Path) -> str:
    """Compute SHA-256 hash of file contents for cache invalidation.

    Args:
        file_path: Path to file.

    Returns:
        Hex digest of SHA-256 hash.
    """
    h = hashlib.sha256()
    h.update(file_path.read_bytes())
    return h.hexdigest()


def generate_clean_pdf(source_md: Path, output_pdf: Path) -> None:
    """Generate T0 clean PDF from annotated source markdown via pandoc/pdflatex.

    Strips annotation comments before conversion so they don't appear in output.

    Args:
        source_md: Path to annotated source markdown.
        output_pdf: Path to write the generated PDF.

    Raises:
        RuntimeError: If pandoc/pdflatex conversion fails.
    """
    import pypandoc

    text = source_md.read_text(encoding="utf-8")
    stripped = strip_annotations(text)

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", delete=False, encoding="utf-8"
    ) as tmp:
        tmp.write(stripped)
        tmp_path = tmp.name

    try:
        output_pdf.parent.mkdir(parents=True, exist_ok=True)
        pypandoc.convert_file(
            tmp_path,
            "pdf",
            outputfile=str(output_pdf),
            extra_args=[
                "--pdf-engine=pdflatex",
                "--standalone",
                "--variable=geometry:margin=1in",
            ],
        )
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def render_pages_to_images(
    pdf_path: Path, dpi: int = _RENDER_DPI
) -> list[Image.Image]:
    """Render each page of a PDF to a PIL Image at the specified DPI.

    Args:
        pdf_path: Path to the PDF file.
        dpi: Resolution for rendering. Default 300.

    Returns:
        List of PIL Images, one per page.
    """
    doc = pymupdf.open(str(pdf_path))
    images: list[Image.Image] = []

    try:
        for page in doc:
            pix = page.get_pixmap(dpi=dpi)
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            images.append(img)
    finally:
        doc.close()

    return images


def apply_noise(
    img: Image.Image,
    tier: NoiseTier,
    seed: int | None = None,
) -> Image.Image:
    """Apply noise transforms to a page image based on the noise tier.

    Uses numpy.random.RandomState for deterministic output across
    numpy versions (frozen Mersenne Twister algorithm).

    Args:
        img: Source PIL Image (clean rendered page).
        tier: Noise tier determining transform intensity.
        seed: Random seed for reproducibility. If None, uses tier default.

    Returns:
        Transformed PIL Image.
    """
    if tier == NoiseTier.CLEAN_OCR:
        return img.copy()

    rng_seed = seed if seed is not None else _TIER_SEEDS.get(tier, 0)
    rng = np.random.RandomState(rng_seed)

    result = img.copy()

    if tier == NoiseTier.MODERATE_SCAN:
        # Slight Gaussian blur (simulates slightly soft scan)
        result = result.filter(ImageFilter.GaussianBlur(radius=0.5))
        # Slight rotation (±1°)
        angle = float(rng.uniform(-1.0, 1.0))
        result = result.rotate(
            angle,
            fillcolor=(255, 255, 255),
            expand=True,
            resample=Image.Resampling.BILINEAR,
        )
        # Faint background noise
        arr = np.array(result, dtype=np.float32)
        noise = rng.normal(0, 5, arr.shape)
        arr = np.clip(arr + noise, 0, 255)
        result = Image.fromarray(arr.astype(np.uint8))

    elif tier == NoiseTier.DEGRADED:
        # Heavy blur
        result = result.filter(ImageFilter.GaussianBlur(radius=1.5))
        # Significant skew (±3°)
        angle = float(rng.uniform(-3.0, 3.0))
        result = result.rotate(
            angle,
            fillcolor=(255, 255, 255),
            expand=True,
            resample=Image.Resampling.BILINEAR,
        )
        # Reduce contrast
        enhancer = ImageEnhance.Contrast(result)
        result = enhancer.enhance(0.7)
        # Heavy noise
        arr = np.array(result, dtype=np.float32)
        noise = rng.normal(0, 25, arr.shape)
        arr = np.clip(arr + noise, 0, 255)
        # Simulated bleed-through (faint reversed overlay)
        flipped = np.fliplr(arr)
        inverted = 255.0 - flipped
        arr = np.clip(arr + 0.08 * inverted, 0, 255)
        result = Image.fromarray(arr.astype(np.uint8))

    return result


def create_image_pdf(images: list[Image.Image], output_pdf: Path) -> None:
    """Create a PDF from a list of PIL Images (one per page).

    Used to create image-only PDFs (no embedded text layer) for T1-T3.

    Args:
        images: List of PIL Images, one per page.
        output_pdf: Path to write the output PDF.
    """
    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open()

    try:
        for img in images:
            width, height = img.size
            page = doc.new_page(width=width, height=height)
            bio = io.BytesIO()
            img.save(bio, format="PNG")
            bio.seek(0)
            page.insert_image(pymupdf.Rect(0, 0, width, height), stream=bio)
        doc.save(str(output_pdf))
    finally:
        doc.close()


def generate_all_tiers(
    source_md: Path,
    output_dir: Path,
) -> dict[NoiseTier, Path]:
    """Generate all 4 noise tier PDFs from a single source markdown.

    Checks content hash to skip regeneration when source hasn't changed.
    Produces:
      output_dir/T0_clean.pdf
      output_dir/T1_ocr_needed.pdf
      output_dir/T2_moderate_scan.pdf
      output_dir/T3_degraded.pdf

    Args:
        source_md: Path to annotated source markdown.
        output_dir: Directory for output PDFs.

    Returns:
        Dict mapping NoiseTier to output PDF path.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    hash_file = output_dir / ".content_hash"
    current_hash = content_hash(source_md)

    # Check cache
    if hash_file.exists() and hash_file.read_text().strip() == current_hash:
        existing = {}
        for tier in NoiseTier:
            pdf_path = output_dir / f"{tier.value}.pdf"
            if pdf_path.exists():
                existing[tier] = pdf_path
        if len(existing) == len(NoiseTier):
            logger.info("Cache hit for %s, skipping regeneration", source_md.name)
            return existing

    # Generate T0 (clean embedded)
    t0_path = output_dir / f"{NoiseTier.CLEAN_EMBEDDED.value}.pdf"
    generate_clean_pdf(source_md, t0_path)

    # Render T0 pages to images for T1-T3
    page_images = render_pages_to_images(t0_path)

    results: dict[NoiseTier, Path] = {NoiseTier.CLEAN_EMBEDDED: t0_path}

    for tier in [NoiseTier.CLEAN_OCR, NoiseTier.MODERATE_SCAN, NoiseTier.DEGRADED]:
        tier_images = [apply_noise(img, tier) for img in page_images]
        tier_path = output_dir / f"{tier.value}.pdf"
        create_image_pdf(tier_images, tier_path)
        results[tier] = tier_path

    # Write cache hash
    hash_file.write_text(current_hash)

    return results
```

**Step 2: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_pdf_generation.py -v`
Expected: All tests pass (requires pdflatex installed; verify with `which pdflatex`)

**Step 3: Commit**

```bash
git add tests/extraction/synthetic/generate.py tests/unit/test_pdf_generation.py
git commit -m "feat: add PDF generation pipeline with 4 noise tiers"
```

<!-- END_TASK_3 -->
<!-- END_SUBCOMPONENT_A -->
