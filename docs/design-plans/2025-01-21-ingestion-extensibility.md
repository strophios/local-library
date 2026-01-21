# Ingestion Layer Extensibility Design

## Summary

This design refactors the ingestion layer to support multiple content types (PDFs, EPUBs, web articles, etc.) through a registry-based dispatch mechanism. Currently, `Library` is hardcoded to use a single `FileAcquirer` and `PdfExtractor`, which means adding support for new content types requires modifications to Library's internals. The new architecture introduces handler lists that are injected at construction time, allowing Library to iterate through registered acquirers and extractors, dispatching to the first handler that reports it can process the given input.

The refactoring introduces two key capabilities: (1) FileAcquirer becomes content-agnostic, accepting any local file path and detecting MIME type dynamically rather than enforcing a hardcoded PDF extension check, and (2) Library validates that an extractor exists for the acquired content before proceeding, failing early with a clear error if no handler matches. This approach preserves acquired files even when extraction fails, enabling re-processing once the appropriate extractor is added. Future content type support (web URLs, EPUBs, etc.) will require only implementing the `ContentAcquirer` or `ContentExtractor` protocol and registering the handler—no changes to Library's dispatch logic needed.

## Definition of Done

The ingestion layer is refactored to support multiple content types (PDF, EPUB, web, etc.) through a dispatch mechanism that routes inputs to the appropriate acquirer and extractor.

**Primary deliverables:**
1. **Dispatch mechanism** for routing to the correct acquirer and extractor based on input characteristics
2. **Decoupled FileAcquirer** that handles any local file (removing the PDF-specific extension check)
3. **Dynamic MIME type** handling in FileAcquirer instead of hardcoded `"application/pdf"`
4. **Library refactored** to use dispatch rather than hardcoded single implementations
5. **Pipeline validation** that confirms a viable extractor exists for the content type before or immediately after acquisition—fail early with a clear error if no extractor can handle the acquired content

**Success criteria:**
- Adding a new acquirer (e.g., `UrlAcquirer`) or extractor (e.g., `EpubExtractor`) requires only: (a) implementing the protocol, and (b) registering with the dispatch mechanism
- No changes to `Library.add()` logic needed when adding new content types
- Existing tests continue to pass (with appropriate updates for new architecture)
- New dispatch mechanism is testable (can mock/inject handlers)

**Out of scope:**
- Implementing actual new content types (web, EPUB, etc.)
- Changes to storage, CLI, or other layers

## Glossary

- **Acquirer**: Component responsible for obtaining content from a source (local file, URL, etc.) and copying it to temporary storage. Implements `ContentAcquirer` protocol.
- **Extractor**: Component that converts acquired content (PDF, EPUB, web page) into structured markdown. Implements `ContentExtractor` protocol.
- **Dispatch**: The process of selecting the correct handler (acquirer or extractor) for a given input by iterating through registered handlers and calling their `can_handle()` method.
- **Protocol**: Python's structural typing mechanism (via `typing.Protocol`) that defines an interface without requiring inheritance. Marked `@runtime_checkable` to allow `isinstance()` checks.
- **Registry-based dispatch**: A pattern where handlers are registered in a list, and the system iterates through them to find the first that can process the input, rather than using hardcoded logic or complex routing tables.
- **Dependency injection**: Passing dependencies (here, handler lists) into a component's constructor rather than hardcoding them internally. Makes testing easier by allowing mock handlers to be injected.
- **MIME type**: Standard format identifier (e.g., `application/pdf`, `text/html`) used to indicate the nature and format of a file.
- **AcquisitionResult**: Return type from acquirers containing the temporary file path, content hash, and MIME type of acquired content.
- **ErrorCode**: Enum-based error classification system in `errors.py` that provides structured error codes for different failure modes.
- **Duck typing**: Programming style where an object's suitability is determined by the presence of methods/properties rather than explicit inheritance. Python protocols enable static type checking of duck-typed code.

## Architecture

Registry-based dispatch with iteration. Library holds lists of registered handlers and iterates through them calling `can_handle()` until one returns `True`.

**Current state:**
```
Library
  ├── _acquirer: FileAcquirer (hardcoded)
  └── _extractor: PdfExtractor (hardcoded)
```

**New state:**
```
Library
  ├── _acquirers: list[ContentAcquirer]  (registered at init)
  └── _extractors: list[ContentExtractor] (registered at init)
```

**Data flow in `Library.add()`:**
1. **Find acquirer:** Iterate `_acquirers`, call `can_handle(source)`, use first that returns `True`
2. **Acquire:** Copy/download content to temp, compute hash, return `AcquisitionResult`
3. **Find extractor:** Iterate `_extractors`, call `can_handle(acquired_path)`, use first that returns `True`
4. **Validate:** If no extractor found, fail with clear error (file preserved with FAILED status)
5. **Extract:** Convert to markdown, validate quality

**Key design decisions:**
- Dispatch logic lives in Library; "can I handle this?" logic stays in each handler
- Validation happens after acquisition (allows content type detection from actual file)
- Failed records preserve acquired files (enables re-processing when extractor added later)
- Handler lists are injected at construction (explicit, testable, backward-compatible defaults)

**Handler registration contract:**

```python
class Library:
    def __init__(
        self,
        db_path: Path | None = None,
        storage_dir: Path | None = None,
        extracted_dir: Path | None = None,
        acquirers: list[ContentAcquirer] | None = None,
        extractors: list[ContentExtractor] | None = None,
    ) -> None:
        self._acquirers = acquirers if acquirers is not None else [FileAcquirer()]
        self._extractors = extractors if extractors is not None else [PdfExtractor(lazy_load=True)]
```

**Dispatch helper contracts:**

```python
def _find_acquirer(self, source: str) -> ContentAcquirer:
    """Find acquirer that can handle this source.

    Raises:
        AcquisitionError with ACQUISITION_UNSUPPORTED_SOURCE if no handler matches
    """
    ...

def _find_extractor(self, file_path: Path) -> ContentExtractor:
    """Find extractor that can handle this file.

    Raises:
        ExtractionError with EXTRACTION_UNSUPPORTED_FORMAT if no handler matches
    """
    ...
```

## Existing Patterns

Investigation found the protocol-based design in `src/local_library/ingestion/base.py` is well-suited for this change. Both `ContentAcquirer` and `ContentExtractor` already define `can_handle()` methods—the missing piece was the dispatch mechanism.

**Patterns followed:**
- `@runtime_checkable` protocols for duck typing (existing pattern in `base.py`)
- Dependency injection via constructor parameters (matches existing `db_path`, `storage_dir` pattern in Library)
- Error hierarchy with `ErrorCode` enum (existing pattern in `errors.py`)

**Pattern introduced:**
- Registry-with-iteration dispatch (new, but fits naturally with existing `can_handle()` methods)

**Divergence from current code:**
- `FileAcquirer.SUPPORTED_EXTENSIONS` removed (was conflating source type with content type)
- `FileAcquirer.validate()` no longer checks extension (that's the extractor's job)
- `FileAcquirer.acquire()` no longer hardcodes MIME type

## Implementation Phases

### Phase 1: Add New Error Codes

**Goal:** Extend error hierarchy for dispatch failures

**Components:**
- `src/local_library/core/errors.py` — add `ACQUISITION_UNSUPPORTED_SOURCE` and `EXTRACTION_UNSUPPORTED_FORMAT` to `ErrorCode` enum

**Dependencies:** None

**Done when:** New error codes exist and can be imported

### Phase 2: Add Dispatch Methods to Library

**Goal:** Implement handler dispatch without changing existing behavior

**Components:**
- `src/local_library/core/library.py` — add `_find_acquirer()` and `_find_extractor()` private methods
- Tests in `tests/unit/test_library.py` — test dispatch returns correct handler, raises on no match

**Dependencies:** Phase 1 (error codes)

**Done when:** Dispatch methods work correctly, existing tests still pass (methods not yet used in `add()`)

### Phase 3: Refactor Library Constructor for Handler Injection

**Goal:** Allow handler lists to be injected while maintaining backward compatibility

**Components:**
- `src/local_library/core/library.py` — add `acquirers` and `extractors` parameters to `__init__()`, default to current single-handler behavior
- Update `_acquirer` and `_extractor` to `_acquirers` and `_extractors` (lists)
- Tests in `tests/unit/test_library.py` — test injection works, test defaults work

**Dependencies:** Phase 2 (dispatch methods exist)

**Done when:** Library accepts handler lists, defaults produce identical behavior to current implementation

### Phase 4: Decouple FileAcquirer from PDF

**Goal:** FileAcquirer handles any local file, not just PDFs

**Components:**
- `src/local_library/ingestion/file.py` — remove `SUPPORTED_EXTENSIONS`, update `can_handle()` to check for local path (not URL), remove extension check from `validate()`, add `_detect_mime_type()` for dynamic MIME type
- Tests in `tests/unit/test_ingestion.py` — test accepts any extension, test rejects URLs, test MIME detection

**Dependencies:** None (can run in parallel with Phases 1-3)

**Done when:** FileAcquirer handles any local file path regardless of extension

### Phase 5: Wire Dispatch into Library.add()

**Goal:** Replace hardcoded handler usage with dispatch

**Components:**
- `src/local_library/core/library.py` — update `add()` to use `_find_acquirer()` and `_find_extractor()`
- Handle "no extractor" case by marking record FAILED (file preserved)
- Tests in `tests/unit/test_library.py` and `tests/integration/` — test dispatch is used, test no-extractor failure path

**Dependencies:** Phases 2, 3, 4

**Done when:** `Library.add()` uses dispatch, all existing tests pass, new failure path tested

### Phase 6: Update Existing Tests

**Goal:** Ensure test suite works with new architecture

**Components:**
- `tests/unit/test_library.py` — update any tests that patch `library._extractor` to use `library._extractors[0]` or inject mocks
- `tests/integration/` — verify integration tests pass without modification (should work via defaults)

**Dependencies:** Phase 5

**Done when:** Full test suite passes, no deprecation warnings

## Additional Considerations

**Acquired files preserved on extractor failure:** When no extractor can handle acquired content, the file remains in storage with FAILED status. This enables:
- Adding an extractor later and re-processing via a future "retry" command
- Manual inspection of unsupported files
- Clear audit trail of what was attempted

**Handler order matters:** First handler that returns `True` from `can_handle()` wins. For most cases this is irrelevant (handlers are disjoint), but future handlers should be registered with this in mind.

**No content type detection beyond extension:** Per clarification, we use file extension for routing. If future needs require inspecting file contents (e.g., magic bytes), the `can_handle()` method can be enhanced without changing the dispatch mechanism.
