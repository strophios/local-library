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
from dataclasses import dataclass
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

_RENDER_DPI = 150


# --- Artifact configuration dataclasses ---
# Frozen for immutability and hashability (needed for cache invalidation).
# Parameter ranges (not fixed values) enable per-page variation via RNG sampling.


@dataclass(frozen=True)
class BlurConfig:
    """Gaussian blur parameters."""

    radius_range: tuple[float, float]


@dataclass(frozen=True)
class RotationConfig:
    """Page rotation/skew parameters in degrees."""

    angle_range: tuple[float, float]


@dataclass(frozen=True)
class GaussianNoiseConfig:
    """Additive Gaussian noise parameters."""

    sigma_range: tuple[float, float]


@dataclass(frozen=True)
class ContrastConfig:
    """Contrast adjustment parameters (PIL ImageEnhance factor)."""

    factor_range: tuple[float, float]


@dataclass(frozen=True)
class ScannerDustConfig:
    """Scanner dust speck and roller mark parameters."""

    speck_count_range: tuple[int, int]
    speck_size_range: tuple[int, int]
    roller_mark_count_range: tuple[int, int]


@dataclass(frozen=True)
class SpatialVariationConfig:
    """Spatially varying focus/brightness degradation parameters."""

    blur_intensity_range: tuple[float, float]
    brightness_reduction_range: tuple[float, float]
    blob_scale: int


@dataclass(frozen=True)
class OcclusionConfig:
    """Edge-biased occlusion mark parameters."""

    mark_count_range: tuple[int, int]
    mark_opacity_range: tuple[float, float]
    edge_bias: float


@dataclass(frozen=True)
class TierConfig:
    """Complete noise configuration for a single tier.

    None means the artifact is disabled for this tier.
    All fields frozen so the entire config tree is hashable for cache invalidation.
    """

    blur: BlurConfig | None = None
    rotation: RotationConfig | None = None
    gaussian_noise: GaussianNoiseConfig | None = None
    contrast: ContrastConfig | None = None
    scanner_dust: ScannerDustConfig | None = None
    spatial_variation: SpatialVariationConfig | None = None
    occlusion: OcclusionConfig | None = None


# Tier configurations: current T2/T3 values expressed as single-point ranges.
# Phase 5 will widen these to actual ranges for per-page variation.
# Bleed-through deliberately omitted from T3 (design decision).
TIER_CONFIGS: dict[NoiseTier, TierConfig | None] = {
    NoiseTier.CLEAN_EMBEDDED: None,  # Embedded text PDF, no noise pipeline
    NoiseTier.CLEAN_OCR: TierConfig(),  # Image-only PDF, no artifacts
    NoiseTier.MODERATE_SCAN: TierConfig(
        blur=BlurConfig(radius_range=(0.5, 0.5)),
        rotation=RotationConfig(angle_range=(-1.0, 1.0)),
        gaussian_noise=GaussianNoiseConfig(sigma_range=(5.0, 5.0)),
    ),
    NoiseTier.DEGRADED: TierConfig(
        blur=BlurConfig(radius_range=(1.5, 1.5)),
        rotation=RotationConfig(angle_range=(-3.0, 3.0)),
        contrast=ContrastConfig(factor_range=(0.7, 0.7)),
        gaussian_noise=GaussianNoiseConfig(sigma_range=(25.0, 25.0)),
    ),
}


def derive_page_seed(tier: NoiseTier, doc_name: str, page_index: int) -> int:
    """Derive a deterministic per-page seed for noise generation.

    Produces unique seeds across pages, documents, and tiers while
    maintaining full determinism. Uses SHA-256 for cross-run stability
    (Python's built-in hash() is randomized by default since 3.3).

    Seed space: tier_seed (0-137) + doc_hash (0-9999) = doc_seed (0-10136),
    page_seed = doc_seed * 1000 + page_index. Max value ~10.1M, well within
    numpy RandomState's uint32 range.

    Args:
        tier: Noise tier (determines base seed via _TIER_SEEDS).
        doc_name: Document identifier (e.g., source filename stem).
        page_index: Zero-based page index within the document.

    Returns:
        Integer seed for numpy.random.RandomState.

    Raises:
        KeyError: If tier has no seed (e.g., CLEAN_EMBEDDED).
    """
    tier_seed = _TIER_SEEDS[tier]
    doc_hash = int(hashlib.sha256(doc_name.encode()).hexdigest(), 16) % 10_000
    doc_seed = tier_seed + doc_hash
    return doc_seed * 1000 + page_index


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
            img.save(bio, format="JPEG", quality=85)
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
