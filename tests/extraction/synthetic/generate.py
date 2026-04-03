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

    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as tmp:
        tmp.write(stripped)
        tmp_path = tmp.name

    try:
        output_pdf.parent.mkdir(parents=True, exist_ok=True)
        pypandoc.convert_file(
            tmp_path,
            "pdf",
            outputfile=str(output_pdf),
            extra_args=[
                "--pdf-engine=xelatex",
                "--standalone",
                "--variable=geometry:margin=1in",
            ],
        )
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def render_pages_to_images(pdf_path: Path, dpi: int = _RENDER_DPI) -> list[Image.Image]:
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

    Raises:
        ValueError: If tier is CLEAN_EMBEDDED (embedded text, not image-based).
    """
    if tier == NoiseTier.CLEAN_EMBEDDED:
        raise ValueError(
            "CLEAN_EMBEDDED is embedded text, not image-based. "
            "Noise cannot be applied to this tier."
        )

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


def create_image_pdf(
    images: list[Image.Image],
    output_pdf: Path,
    page_width: float = 612,
    page_height: float = 792,
) -> None:
    """Create a PDF from a list of PIL Images (one per page).

    Used to create image-only PDFs (no embedded text layer) for T1-T3.
    Pages are set to standard dimensions (default US Letter) with images
    scaled to fit, rather than using pixel dimensions as page size.

    Args:
        images: List of PIL Images, one per page.
        output_pdf: Path to write the output PDF.
        page_width: Page width in PDF points (72 pts/inch). Default 612 (8.5").
        page_height: Page height in PDF points. Default 792 (11").
    """
    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open()

    try:
        for img in images:
            page = doc.new_page(width=page_width, height=page_height)
            bio = io.BytesIO()
            img.save(bio, format="PNG")
            bio.seek(0)
            page.insert_image(pymupdf.Rect(0, 0, page_width, page_height), stream=bio)
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
