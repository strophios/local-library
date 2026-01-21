# Ingestion Domain

Last verified: 2026-01-21

## Purpose

Handles content acquisition (getting files into the system) and extraction (converting to searchable text). Defines protocols for extensibility; implementations handle specific source types.

## Contracts

- **Exposes**: ContentAcquirer protocol, ContentExtractor protocol, FileAcquirer, PdfExtractor
- **Guarantees**:
  - Acquirers copy to temp location (never modify source)
  - AcquisitionResult.content_hash is SHA-256 of acquired content
  - Extractors produce ExtractionResult with quality metrics
  - PdfExtractor validates output (min length, printable ratio)
- **Expects**: Source paths exist and are readable; temp directories provided by caller

## Dependencies

- **Uses**: `core.models` (AcquisitionResult, ExtractionResult), `core.errors` (exception types)
- **Used by**: `core.library` (Library orchestrator)
- **Boundary**: Ingestion MUST NOT import from cli or storage

## Key Decisions

- **Protocol-based extensibility**: ContentAcquirer and ContentExtractor are protocols (not ABCs) for duck typing
- **Lazy Marker loading**: PdfExtractor defers model load until first extraction (saves startup time)
- **Quality validation**: ExtractionResult.validate() checks min length and printable ratio
- **compute_storage_path**: Git-style `ab/cd/hash.ext` layout for content-addressable storage

## Invariants

- Acquirers never modify source files
- content_hash computed AFTER copying to temp (verifies what was copied)
- PdfExtractor raises QualityError on invalid output (never silently succeeds)

## Key Files

- `base.py` - ContentAcquirer, ContentExtractor protocols; compute_storage_path utility
- `file.py` - FileAcquirer (local files), compute_file_hash
- `pdf.py` - PdfExtractor (Marker wrapper with quality validation)

## Gotchas

- PdfExtractor.extract_and_validate() is the preferred method (combines extraction + validation)
- FileAcquirer.acquire() returns resolved absolute path in original_path
- Quality thresholds are configurable but default to min_length=100, min_printable_ratio=0.8
