# pattern: Imperative Shell
"""PDF generation pipeline for synthetic extraction quality tests.

Generates 4 noise tiers from annotated source markdown:
  T0 (CLEAN_EMBEDDED): pandoc/pdflatex with embedded text
  T1 (CLEAN_OCR): T0 rendered to images, re-composited as image-only PDF
  T2 (MODERATE_SCAN): blur, rotation, noise, contrast reduction, scanner dust,
    spatial variation
  T3 (DEGRADED): heavy blur, rotation, noise, contrast reduction, scanner dust,
    spatial variation, occlusion

Noise application is deterministic via numpy.random.RandomState (frozen
algorithm, guaranteed same output across numpy versions given same seed).
PDFs are cached via combined content + parameter hash to skip regeneration
when neither source content nor generation parameters have changed.
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
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

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


# Tier configurations with calibrated parameter ranges.
# Iteratively tuned: T2 is light degradation (legible with minor artifacts),
# T3 is moderate degradation (legible but noticeably worse). Rotation uses
# nearest-neighbor resampling (bilinear at >1° triggers surya encoder segfault).
TIER_CONFIGS: dict[NoiseTier, TierConfig | None] = {
    NoiseTier.CLEAN_EMBEDDED: None,  # Embedded text PDF, no noise pipeline
    NoiseTier.CLEAN_OCR: TierConfig(),  # Image-only PDF, no artifacts
    NoiseTier.MODERATE_SCAN: TierConfig(
        blur=BlurConfig(radius_range=(0.2, 0.5)),
        # rotation disabled: surya segfaults on rotated images regardless
        # of resampling method. Re-enable if surya/marker fix is released.
        gaussian_noise=GaussianNoiseConfig(sigma_range=(2.0, 4.0)),
        contrast=ContrastConfig(factor_range=(0.9, 0.9)),
        scanner_dust=ScannerDustConfig(
            speck_count_range=(2, 5),
            speck_size_range=(1, 3),
            roller_mark_count_range=(0, 1),
        ),
        spatial_variation=SpatialVariationConfig(
            blur_intensity_range=(0.2, 0.5),
            brightness_reduction_range=(0.03, 0.08),
            blob_scale=120,
        ),
    ),
    NoiseTier.DEGRADED: TierConfig(
        blur=BlurConfig(radius_range=(0.3, 1.0)),
        gaussian_noise=GaussianNoiseConfig(sigma_range=(3.0, 7.0)),
        contrast=ContrastConfig(factor_range=(0.85, 0.85)),
        scanner_dust=ScannerDustConfig(
            speck_count_range=(3, 10),
            speck_size_range=(2, 4),
            roller_mark_count_range=(0, 2),
        ),
        spatial_variation=SpatialVariationConfig(
            blur_intensity_range=(0.3, 0.8),
            brightness_reduction_range=(0.05, 0.15),
            blob_scale=100,
        ),
        occlusion=OcclusionConfig(
            mark_count_range=(1, 2),
            mark_opacity_range=(0.1, 0.25),
            edge_bias=0.7,
        ),
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


def generation_params_hash(
    configs: dict[NoiseTier, TierConfig | None] | None = None,
) -> str:
    """Compute SHA-256 hash of tier configuration parameters.

    Captures every field value across all tiers. Changes to parameter
    ranges, new artifacts enabled, or artifacts removed all change the hash.

    Args:
        configs: Tier configs to hash. Defaults to module-level TIER_CONFIGS.

    Returns:
        Hex digest of SHA-256 hash.
    """
    if configs is None:
        configs = TIER_CONFIGS
    h = hashlib.sha256()
    h.update(repr(configs).encode())
    return h.hexdigest()


def generation_hash(
    source_path: Path,
    configs: dict[NoiseTier, TierConfig | None] | None = None,
) -> str:
    """Compute combined content + parameter hash for cache invalidation.

    Both source content and generation parameters must match for a cache hit.
    Parameter changes (range adjustments, new artifacts) automatically
    invalidate the cache.

    Args:
        source_path: Path to source markdown file.
        configs: Tier configs to hash. Defaults to module-level TIER_CONFIGS.

    Returns:
        Hex digest of combined SHA-256 hash.
    """
    c_hash = content_hash(source_path)
    p_hash = generation_params_hash(configs)
    combined = hashlib.sha256()
    combined.update((c_hash + p_hash).encode())
    return combined.hexdigest()


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


# --- Individual artifact functions ---
# Each follows the signature: (image, config, rng) -> image
# Applied in fixed order by the pipeline orchestrator.


def apply_blur(img: Image.Image, config: BlurConfig, rng: np.random.RandomState) -> Image.Image:
    """Apply Gaussian blur with radius sampled from config range."""
    lo, hi = config.radius_range
    radius = float(rng.uniform(lo, hi)) if lo != hi else lo
    return img.filter(ImageFilter.GaussianBlur(radius=radius))


def apply_rotation(
    img: Image.Image, config: RotationConfig, rng: np.random.RandomState
) -> Image.Image:
    """Apply page rotation/skew with angle sampled from config range."""
    lo, hi = config.angle_range
    angle = float(rng.uniform(lo, hi))
    return img.rotate(
        angle,
        fillcolor=(255, 255, 255),
        expand=False,
        resample=Image.Resampling.NEAREST,
    )


def apply_contrast(
    img: Image.Image, config: ContrastConfig, rng: np.random.RandomState
) -> Image.Image:
    """Apply contrast adjustment with factor sampled from config range."""
    lo, hi = config.factor_range
    factor = float(rng.uniform(lo, hi)) if lo != hi else lo
    enhancer = ImageEnhance.Contrast(img)
    return enhancer.enhance(factor)


def apply_gaussian_noise(
    img: Image.Image, config: GaussianNoiseConfig, rng: np.random.RandomState
) -> Image.Image:
    """Apply additive Gaussian noise with sigma sampled from config range."""
    lo, hi = config.sigma_range
    sigma = float(rng.uniform(lo, hi)) if lo != hi else lo
    arr = np.array(img, dtype=np.float32)
    noise = rng.normal(0, sigma, arr.shape)
    arr = np.clip(arr + noise, 0, 255)
    return Image.fromarray(arr.astype(np.uint8))


def apply_scanner_dust(
    img: Image.Image, config: ScannerDustConfig, rng: np.random.RandomState
) -> Image.Image:
    """Apply scanner dust specks and roller marks.

    Dust specks are small dark filled circles at random positions.
    Roller marks are thin horizontal lines spanning partial page width.
    """
    result = img.copy()
    draw = ImageDraw.Draw(result)
    w, h = result.size

    # Dust specks
    lo, hi = config.speck_count_range
    speck_count = int(rng.randint(lo, hi + 1))
    s_lo, s_hi = config.speck_size_range
    for _ in range(speck_count):
        x = int(rng.randint(0, w))
        y = int(rng.randint(0, h))
        size = int(rng.randint(s_lo, s_hi + 1))
        gray = int(rng.randint(20, 80))
        draw.ellipse([x - size, y - size, x + size, y + size], fill=(gray, gray, gray))

    # Roller marks
    lo, hi = config.roller_mark_count_range
    mark_count = int(rng.randint(lo, hi + 1))
    for _ in range(mark_count):
        y = int(rng.randint(0, h))
        x_start = int(rng.uniform(0, w * 0.3))
        x_end = int(rng.uniform(w * 0.7, w))
        thickness = int(rng.randint(1, 3))
        gray = int(rng.randint(150, 200))
        draw.rectangle([x_start, y, x_end, y + thickness], fill=(gray, gray, gray))

    return result


def apply_spatial_variation(
    img: Image.Image, config: SpatialVariationConfig, rng: np.random.RandomState
) -> Image.Image:
    """Apply spatially varying focus/brightness degradation.

    Generates a smooth blob mask (low-res noise upscaled via bilinear
    interpolation), creates a more-degraded copy of the image, and blends
    original and degraded via the mask. Areas where mask is low get the
    degraded version (softer focus, dimmer).
    """
    w, h = img.size

    # Generate smooth mask via low-res noise upscaled
    grid_w = max(2, w // config.blob_scale)
    grid_h = max(2, h // config.blob_scale)
    low_res = rng.uniform(0.0, 1.0, (grid_h, grid_w)).astype(np.float32)

    # Upscale to full resolution via bilinear interpolation
    mask_img = Image.fromarray((low_res * 255).astype(np.uint8), mode="L")
    mask_img = mask_img.resize((w, h), Image.Resampling.BILINEAR)
    mask = np.array(mask_img, dtype=np.float32) / 255.0

    # Create degraded copy (additional blur + brightness reduction)
    lo_b, hi_b = config.blur_intensity_range
    blur_intensity = float(rng.uniform(lo_b, hi_b)) if lo_b != hi_b else lo_b
    degraded = img.filter(ImageFilter.GaussianBlur(radius=blur_intensity))

    lo_br, hi_br = config.brightness_reduction_range
    reduction = float(rng.uniform(lo_br, hi_br)) if lo_br != hi_br else lo_br
    enhancer = ImageEnhance.Brightness(degraded)
    degraded = enhancer.enhance(1.0 - reduction)

    # Blend: result = original * mask + degraded * (1 - mask)
    arr = np.array(img, dtype=np.float32)
    deg_arr = np.array(degraded, dtype=np.float32)
    mask_3d = mask[:, :, np.newaxis]
    blended = arr * mask_3d + deg_arr * (1.0 - mask_3d)

    return Image.fromarray(np.clip(blended, 0, 255).astype(np.uint8))


def apply_occlusion(
    img: Image.Image, config: OcclusionConfig, rng: np.random.RandomState
) -> Image.Image:
    """Apply edge-biased occlusion marks (photocopy shadows, stains).

    Draws semi-transparent dark shapes via alpha compositing. Marks are
    biased toward page edges/corners (controlled by edge_bias parameter)
    to simulate photocopy artifacts.
    """
    result = img.copy().convert("RGBA")
    w, h = result.size

    lo, hi = config.mark_count_range
    mark_count = int(rng.randint(lo, hi + 1))

    lo_o, hi_o = config.mark_opacity_range

    for _ in range(mark_count):
        opacity = int(rng.uniform(lo_o, hi_o) * 255)
        overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        # Edge-biased positioning
        if float(rng.random()) < config.edge_bias:
            edge = int(rng.randint(0, 4))
            if edge == 0:  # top
                cx = int(rng.uniform(0, w))
                cy = int(rng.uniform(0, h * 0.1))
            elif edge == 1:  # right
                cx = int(rng.uniform(w * 0.9, w))
                cy = int(rng.uniform(0, h))
            elif edge == 2:  # bottom
                cx = int(rng.uniform(0, w))
                cy = int(rng.uniform(h * 0.9, h))
            else:  # left
                cx = int(rng.uniform(0, w * 0.1))
                cy = int(rng.uniform(0, h))
        else:
            cx = int(rng.uniform(0, w))
            cy = int(rng.uniform(0, h))

        mark_w = int(rng.uniform(20, 80))
        mark_h = int(rng.uniform(15, 60))

        if float(rng.random()) < 0.5:
            draw.rectangle(
                [cx - mark_w, cy - mark_h, cx + mark_w, cy + mark_h],
                fill=(30, 30, 30, opacity),
            )
        else:
            draw.ellipse(
                [cx - mark_w, cy - mark_h, cx + mark_w, cy + mark_h],
                fill=(30, 30, 30, opacity),
            )

        result = Image.alpha_composite(result, overlay)

    return result.convert("RGB")


# Fixed application order: blur -> rotation -> contrast -> gaussian_noise
# (-> scanner_dust -> spatial_variation -> occlusion added in Phase 3).
# Order matters: blur before noise ensures noise isn't blurred away.
_ARTIFACT_PIPELINE: list[tuple[str, type]] = [
    ("blur", BlurConfig),
    ("rotation", RotationConfig),
    ("contrast", ContrastConfig),
    ("gaussian_noise", GaussianNoiseConfig),
    ("scanner_dust", ScannerDustConfig),
    ("spatial_variation", SpatialVariationConfig),
    ("occlusion", OcclusionConfig),
]


def apply_noise_pipeline(
    img: Image.Image,
    tier: NoiseTier,
    doc_name: str,
    page_index: int,
) -> Image.Image:
    """Apply noise artifacts to a page image via config-driven pipeline.

    Replaces the former apply_noise() function. Uses TierConfig to determine
    which artifacts to apply and derives per-page seeds for natural variation.

    Args:
        img: Source PIL Image (clean rendered page).
        tier: Noise tier determining which artifacts are enabled.
        doc_name: Document name for seed derivation.
        page_index: Zero-based page index for seed derivation.

    Returns:
        Transformed PIL Image.

    Raises:
        ValueError: If tier is CLEAN_EMBEDDED (embedded text, not image-based).
    """
    config = TIER_CONFIGS[tier]

    if config is None:
        raise ValueError(
            "CLEAN_EMBEDDED is embedded text, not image-based. "
            "Noise cannot be applied to this tier."
        )

    result = img.copy()

    # Check if any artifacts are enabled
    has_artifacts = any(getattr(config, attr) is not None for attr, _ in _ARTIFACT_PIPELINE)
    if not has_artifacts:
        return result

    # Derive per-page seed and create RNG
    seed = derive_page_seed(tier, doc_name, page_index)
    rng = np.random.RandomState(seed)

    # Apply artifacts in fixed order
    artifact_funcs = {
        "blur": apply_blur,
        "rotation": apply_rotation,
        "contrast": apply_contrast,
        "gaussian_noise": apply_gaussian_noise,
        "scanner_dust": apply_scanner_dust,
        "spatial_variation": apply_spatial_variation,
        "occlusion": apply_occlusion,
    }

    for attr, _ in _ARTIFACT_PIPELINE:
        artifact_config = getattr(config, attr)
        if artifact_config is not None:
            result = artifact_funcs[attr](result, artifact_config, rng)

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
            # Convert to grayscale to match real scanned PDF characteristics.
            # Noise artifacts are applied in RGB (some use color), but final
            # output is grayscale since real academic scans are grayscale.
            img.convert("L").save(bio, format="JPEG", quality=85)
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

    Checks combined content + parameter hash to skip regeneration when
    neither source nor generation parameters have changed.
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
    hash_file = output_dir / ".generation_hash"
    current_hash = generation_hash(source_md)

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
    doc_name = source_md.stem

    for tier in [NoiseTier.CLEAN_OCR, NoiseTier.MODERATE_SCAN, NoiseTier.DEGRADED]:
        tier_images = [
            apply_noise_pipeline(img, tier, doc_name, page_idx)
            for page_idx, img in enumerate(page_images)
        ]
        tier_path = output_dir / f"{tier.value}.pdf"
        create_image_pdf(tier_images, tier_path)
        results[tier] = tier_path

    # Write cache hash
    hash_file.write_text(current_hash)

    return results
