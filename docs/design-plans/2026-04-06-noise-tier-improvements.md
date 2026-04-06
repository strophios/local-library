# Noise Tier Improvements Design

## Summary

The extraction quality framework in `tests/extraction/synthetic/` measures how well the Marker PDF extraction pipeline preserves content fidelity across simulated document degradation levels. Documents are processed through four "noise tiers" — clean (T0), lightly degraded (T1), moderately degraded (T2), and heavily degraded (T3) — by rendering source markdown to PDF and synthetically applying degradation artifacts before running them through the extraction pipeline. The resulting CER/WER metrics show how much extraction quality degrades as document condition worsens.

This design improves the noise generation layer at the bottom of that pipeline. The current approach applies a fixed set of degradation parameters per tier, producing pages within a document that look nearly identical to each other, and T2/T3 tiers that don't yet reflect the realistic artifact mix of actual scanned academic documents. The redesign replaces hardcoded per-tier function branches with a config-driven architecture: each artifact type is an independent function parameterized by ranges rather than fixed values, a deterministic per-page seed scheme samples from those ranges so pages within a document vary naturally, and the fixture cache now invalidates automatically when either source content or generation parameters change. Three new artifact types are added — scanner dust and roller marks, spatially varying focus/brightness, and edge-biased occlusion marks — and T2/T3 parameter values are recalibrated with bleed-through removed from T3.

## Definition of Done

**Deliverables:**
- Redesigned noise generation in `generate.py` with per-page/per-document seed variation as the foundation
- Three new artifact types: scanner dust/roller marks, spatially varying quality, local occlusion
- Recalibrated T2 (moderately harder) and T3 (significantly harder, no bleed-through)
- Generation parameter hashing for intelligent fixture cache invalidation (compare param hash + content hash before regenerating)
- New baseline established covering all 4 tiers
- (Stretch goal) Geometric distortion via opencv displacement fields

**Success criteria:**
- Pages within a document visibly differ from each other (per-page variation works)
- Results are deterministic (same seeds → same output across runs)
- Cache correctly regenerates when generation params or source content change, and skips when neither has changed
- Existing framework (runner, alignment, metrics, validators) works without modification against new PDFs
- Baseline JSON updated with results from all 4 tiers

**Out of scope:**
- Changes to the extraction pipeline itself (Marker, cleanup)
- New source documents or expanded validators
- DPI changes
- Any other framework improvements beyond noise tiers

## Glossary

- **Noise tier**: A named degradation level applied to a source document during PDF generation. Four tiers: T0 (clean, no noise), T1 (light), T2 (moderate scan), T3 (degraded photocopy). Used to benchmark extraction quality across a range of document conditions.
- **CER / WER**: Character Error Rate and Word Error Rate. Edit-distance-based metrics (via rapidfuzz) that measure how much extracted text deviates from the expected content. Lower is better.
- **Marker**: The primary PDF text extraction library used by the system. The extraction quality framework measures Marker's fidelity under degradation.
- **Pillow (PIL)**: Python Imaging Library fork used for raster image operations — blur, contrast adjustment, drawing shapes. All core artifact types use Pillow.
- **numpy `RandomState`**: A legacy numpy random number generator class using the Mersenne Twister algorithm. Chosen here because its output is stable across numpy versions, which is important for deterministic test fixtures.
- **Frozen dataclass**: A Python `dataclass` with `frozen=True`, making instances immutable and therefore hashable. Used here so the entire config tree can be hashed for cache invalidation.
- **Fixture cache**: The cached set of generated PDFs stored on disk so the benchmark doesn't re-render documents on every run. Cache validity is checked via a stored hash.
- **`cv2.remap` / OpenCV**: `cv2` is the Python interface to OpenCV, a computer vision library. `remap` applies a displacement field to warp pixel positions, enabling geometric distortions like page curl or warping. Relevant only to the stretch goal.
- **Displacement field**: A per-pixel vector map describing how to remap each output pixel to a source location. Used with `cv2.remap` to simulate page warping. Relevant only to the stretch goal.
- **Bilinear interpolation**: A resampling method used during image upscaling. Here, small random noise arrays are upscaled via bilinear interpolation to produce smooth, spatially coherent blob masks for the spatial variation artifact.
- **Alpha compositing**: Blending a semi-transparent layer onto an image using an alpha (opacity) channel. Used in the occlusion artifact to paint dark marks without fully obscuring the underlying content.
- **Pandoc / XeLaTeX**: Document conversion tools used in T0 to render source markdown to PDF without any degradation. Not modified by this design.

## Architecture

### Config-Driven Noise Pipeline

Replace the current monolithic `apply_noise()` function (tier-specific if/elif branches) with a config-driven pipeline. Tier definitions become data (frozen dataclasses) rather than code branches.

**Artifact config dataclasses** — each frozen, each representing one degradation type with parameter *ranges* (not fixed values). The pipeline samples from ranges using per-page RNG, producing natural variation.

Individual configs:
- `BlurConfig(radius_range)` — uniform Gaussian blur
- `RotationConfig(angle_range)` — page skew in degrees
- `GaussianNoiseConfig(sigma_range)` — additive per-pixel noise
- `ContrastConfig(factor_range)` — PIL ImageEnhance factor (<1.0 = reduced)
- `ScannerDustConfig(speck_count_range, speck_size_range, roller_mark_count_range)` — physical scanner defects
- `SpatialVariationConfig(blur_intensity_range, brightness_reduction_range, blob_scale)` — localized degradation via smooth mask blending
- `OcclusionConfig(mark_count_range, mark_opacity_range, edge_bias)` — dark marks biased toward edges/corners

`TierConfig` composes these — `None` means the artifact is disabled for that tier. All frozen, so the entire config tree is hashable.

**Pipeline application order** is fixed: blur → rotation → contrast → gaussian noise → scanner dust → spatial variation → occlusion. Order matters: blur before noise ensures noise isn't blurred away; spatial variation after noise ensures fade is visible.

### Seed Derivation

Per-page and per-document variation while maintaining full determinism:

- **Document seed**: `doc_seed = tier_seed + hash(doc_name) % 10_000`
- **Page seed**: `page_seed = doc_seed * 1000 + page_index`
- Each page gets its own `numpy.random.RandomState(page_seed)` passed to the artifact pipeline

Tier seeds remain well-separated (0, 42, 137). The `* 1000` multiplier supports up to 1000 pages per document (our corpus is 3-8 pages). T0 and T1 are unchanged — T0 uses pandoc/xelatex with no noise, T1 renders to images and re-composites with no modification.

### Artifact Implementations

Each artifact is an independent function: `(image, config, rng) -> image`.

**Existing operations** (refactored from `apply_noise()` branches):
- Blur, rotation, contrast, gaussian noise — same Pillow/numpy operations, now with ranges instead of fixed values

**New operations:**
- **Scanner dust**: Pillow `ImageDraw`. Dust specks are small filled circles (2-5px) at random positions. Roller marks are thin horizontal lines (1-2px height, partial page width). Counts sampled from config ranges per page.
- **Spatial variation**: Generate a smooth mask (low-resolution random noise upscaled via bilinear interpolation to produce large soft blobs), create a more-degraded copy of the current image (additional blur + brightness reduction), blend via `result = image * mask + degraded * (1 - mask)`. The `blob_scale` parameter controls low-res grid size.
- **Occlusion**: Semi-transparent dark shapes via `ImageDraw` with alpha compositing. Dark rectangles near edges/corners (photocopy shadows), irregular ellipses at random positions (stains). `edge_bias` controls clustering toward edges.

**Stretch goal — Geometric distortion**: `cv2.remap` with sinusoidal/parabolic displacement fields. Adds `opencv-python-headless` (~46 MB) as dev dependency. Same function signature pattern, added to tier configs only if pursued.

### Cache Invalidation

Combine source content hash with generation parameter hash. Both must match for cache hit.

- **Content hash**: SHA-256 of source markdown (same as current)
- **Params hash**: SHA-256 of `repr(TIER_CONFIGS)` — captures every field value across all tiers
- **Combined hash**: `sha256(content_hash + params_hash)` stored in `.generation_hash` file (replaces `.content_hash`)

Parameter changes (range adjustments, new artifacts enabled, artifacts removed) automatically invalidate the cache. Internal code changes to artifact *functions* are not detected — manual fixture clearing is needed for those, which is acceptable for a test framework.

### Tier Definitions

Recalibrated from `tmp_plan.md`, with gaussian noise reduced to account for new artifact types contributing overall difficulty:

**T2 (MODERATE_SCAN)** — decent-quality scan:
- Blur: radius 1.0–2.0
- Rotation: ±2–3°
- Noise: sigma 8–12 (reduced from planned 10–15)
- Contrast: 0.85
- Scanner dust: light (few specks, maybe one roller mark)
- Spatial variation: mild

**T3 (DEGRADED)** — poor-quality photocopy, no bleed-through:
- Blur: radius 2.0–3.0
- Rotation: ±3–5°
- Noise: sigma 12–18 (reduced from planned 20–30)
- Contrast: 0.6–0.75
- Scanner dust: moderate
- Spatial variation: moderate
- Occlusion: 1–2 small marks per page

These values are starting points. The config-driven approach makes recalibration trivial after reviewing benchmark results.

## Existing Patterns

The design extends patterns already established in `tests/extraction/synthetic/generate.py`:

- **Pillow + numpy image stack**: All existing noise operations use PIL `ImageFilter`, `ImageEnhance`, and numpy array operations. New artifacts follow the same stack (no new image libraries for core artifacts).
- **Deterministic RNG via `numpy.random.RandomState`**: Frozen Mersenne Twister algorithm guarantees same output across numpy versions. The redesign keeps this approach, extending it with per-page seed derivation.
- **`NoiseTier` enum**: Four tiers with string values used as filenames. Unchanged.
- **Content-hash caching**: Cache check in `generate_all_tiers()` skips regeneration when source hasn't changed. Extended to include parameter hashing, same location and flow.

**New pattern introduced:** Frozen dataclass configuration hierarchy. This diverges from the current approach of hardcoded values in function branches. Justified by: the parameter space is growing from ~8 values across 2 tiers to ~30+ values across 2 tiers with per-artifact structure. Data-as-configuration makes tier definitions reviewable, hashable, and separately testable.

## Implementation Phases

### Phase 1: Config Dataclass Hierarchy and Seed Derivation

**Goal:** Establish the data model for tier configuration and the per-page seed derivation scheme.

**Components:**
- Artifact config dataclasses in `tests/extraction/synthetic/generate.py` — `BlurConfig`, `RotationConfig`, `GaussianNoiseConfig`, `ContrastConfig`, `ScannerDustConfig`, `SpatialVariationConfig`, `OcclusionConfig`, `TierConfig`
- `TIER_CONFIGS` dict mapping `NoiseTier` to `TierConfig` — initial values matching current T2/T3 behavior (existing params expressed as ranges)
- Seed derivation function producing per-page `RandomState` from tier seed, doc name, and page index

**Dependencies:** None (first phase)

**Done when:** Config dataclasses instantiate correctly, `TIER_CONFIGS` is defined, seed derivation produces deterministic per-page seeds that differ across pages and documents

### Phase 2: Pipeline Orchestrator and Artifact Refactor

**Goal:** Replace the monolithic `apply_noise()` with a config-driven pipeline that applies artifacts in fixed order, and refactor existing noise operations (blur, rotation, contrast, gaussian noise) into independent artifact functions.

**Components:**
- Individual artifact functions in `tests/extraction/synthetic/generate.py` — `apply_blur`, `apply_rotation`, `apply_contrast`, `apply_gaussian_noise`, each with `(image, config, rng) -> image` signature
- Pipeline orchestrator replacing `apply_noise()` — looks up `TierConfig`, derives per-page seed, applies enabled artifacts in order
- Updated `generate_all_tiers()` — passes doc_name and page_index through to the pipeline

**Dependencies:** Phase 1 (config dataclasses and seed derivation)

**Done when:** Benchmark runs successfully with the refactored pipeline. T2/T3 output will differ from previous baseline (per-page seeds change the output), but degradation type and approximate quality levels are preserved. Existing tests pass.

### Phase 3: New Artifact Implementations

**Goal:** Implement the three new artifact types: scanner dust, spatially varying quality, and local occlusion.

**Components:**
- `apply_scanner_dust` function — Pillow `ImageDraw` for dust specks and roller marks
- `apply_spatial_variation` function — numpy mask generation (low-res noise upscaled), degraded copy creation, mask-based blending
- `apply_occlusion` function — Pillow `ImageDraw` with alpha compositing for edge-biased dark marks

**Dependencies:** Phase 2 (pipeline orchestrator to plug into)

**Done when:** Each artifact function produces visible, deterministic effects when tested in isolation. Functions integrate into the pipeline without breaking existing artifacts.

### Phase 4: Cache Invalidation Upgrade

**Goal:** Replace content-only hash caching with combined content + generation parameter hashing.

**Components:**
- Parameter hash computation from `TIER_CONFIGS` repr in `tests/extraction/synthetic/generate.py`
- Combined hash logic in `generate_all_tiers()` — computes `sha256(content_hash + params_hash)`, writes `.generation_hash`
- Backward compatibility: ignore stale `.content_hash` files (treat as cache miss)

**Dependencies:** Phase 1 (config dataclasses must exist to hash)

**Done when:** Cache hits when neither source nor params change. Cache misses and regenerates when either changes. Old `.content_hash` files don't cause errors.

### Phase 5: Tier Recalibration and Baseline Establishment

**Goal:** Set final T2/T3 parameter values with new artifacts enabled, run full benchmark, establish new baseline covering all 4 tiers.

**Components:**
- Updated `TIER_CONFIGS` values in `tests/extraction/synthetic/generate.py` — T2 and T3 with new artifacts enabled at calibrated intensities, bleed-through removed from T3
- New `baseline.json` in `tests/extraction/synthetic/results/` — full results for T0, T1, T2, T3 across all 6 source documents
- Fixture regeneration (delete cached PDFs, run benchmark)

**Dependencies:** Phases 2, 3, 4 (all artifacts implemented, cache invalidation working)

**Done when:** Benchmark produces results for all 4 tiers. T0 > T1 > T2 > T3 in quality (monotonic degradation). Results are committed as the new regression baseline.

## Additional Considerations

**Stretch goal — Geometric distortion (Phase 6 if pursued):** Would add `opencv-python-headless` as dev dependency, implement `apply_geometric_distortion` function using `cv2.remap` with displacement fields, add `GeometricDistortionConfig` to the config hierarchy, and enable on T3. Parameter tuning for realistic-looking distortion is the main risk. Decision to pursue deferred until after Phase 5 baseline is established and reviewed.

**Noise parameter tuning is iterative.** The config values in this design are starting points based on the rough plan. After Phase 5 produces a baseline, reviewing the actual CER/WER numbers and visually inspecting generated PDFs may suggest adjustments. The config-driven architecture makes this trivial — change a value, cache auto-invalidates, re-run benchmark.
