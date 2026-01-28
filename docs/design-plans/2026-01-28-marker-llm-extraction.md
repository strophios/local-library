# Marker LLM-Enhanced Extraction Design

## Summary

Add `--llm-extract` flag to the `add` command enabling Marker's LLM-enhanced PDF extraction for better handling of tables, math, and images. Implement early API key validation for both `--llm` and `--llm-extract` flags with graceful fallback. Pass API key via Marker's config dict to avoid environment variable manipulation.

## Definition of Done

**Primary Deliverables:**
1. **New `--llm-extract` flag** on `add` command that enables Marker's LLM-enhanced PDF extraction (tables, cross-page merging, inline math, form fields)
2. **Early API key validation** for both `--llm` and `--llm-extract` flags - warn at command start if key is missing, then fall back to non-LLM behavior
3. **Image description integration** - when `--llm-extract` is active, images in PDFs are replaced with LLM-generated text descriptions (better for downstream RAG)

**Success Criteria:**
- Running `local-library add document.pdf --llm-extract` produces higher-quality markdown for complex tables and math
- Missing `GEMINI_API_KEY` produces a visible warning before extraction begins, then continues without LLM
- Test PDFs (NIST2023.pdf, Massachusetts2024.pdf for tables; Hu2018.pdf, Dhingra2022.pdf for math) show improved extraction quality

**Out of Scope:**
- Changing the LLM provider (staying with Gemini Flash)
- Re-extracting existing documents in the library
- Adding LLM extraction to other commands besides `add`

## Glossary

- **Marker**: Neural PDF extraction library that converts PDFs to markdown
- **LLM-enhanced extraction**: Marker mode using Gemini to improve table, math, and image handling
- **GEMINI_API_KEY**: Environment variable for Google's Gemini API authentication
- **RAG**: Retrieval-Augmented Generation - downstream use case where text descriptions are more useful than images

## Architecture

### Component Changes

**1. PdfExtractor** (`src/local_library/ingestion/pdf.py`)

Extended constructor to accept LLM configuration:

```python
def __init__(
    self,
    lazy_load: bool = True,
    llm_enabled: bool = False,
) -> None:
```

When `llm_enabled=True` and `GEMINI_API_KEY` is available, configures Marker's PdfConverter with:
- `use_llm: True`
- `gemini_api_key: <from GEMINI_API_KEY env var>`
- `redo_inline_math: True` (always enabled with LLM)
- `disable_image_extraction: True` (replaces images with descriptions)

**2. Library** (`src/local_library/core/library.py`)

New constructor parameters to pass PDF extraction config:

```python
def __init__(
    self,
    # ... existing params ...
    pdf_llm_enabled: bool = False,
) -> None:
```

Passes config to PdfExtractor when creating default extractors.

**3. CLI add command** (`src/local_library/cli/add.py`)

New flag:
```python
llm_extract: Annotated[bool, typer.Option("--llm-extract", ...)] = False
```

Early validation before Library instantiation - checks `GEMINI_API_KEY` for both `--llm` and `--llm-extract` flags, warns and disables if missing.

### Data Flow

```
CLI (--llm-extract flag)
    ↓
Early validation: check_api_key_available("GEMINI_API_KEY")
    ├─ Missing → warn, set llm_extract=False
    └─ Present → continue
    ↓
Library(pdf_llm_enabled=llm_extract)
    ↓
PdfExtractor(llm_enabled=pdf_llm_enabled)
    ↓
_ensure_models_loaded():
    - Read GEMINI_API_KEY from environment
    - Build config dict with gemini_api_key, use_llm, etc.
    - Pass config to PdfConverter
    ↓
PdfConverter extracts with LLM enhancement
```

### API Key Handling

Marker internally expects `GOOGLE_API_KEY` environment variable, but we use `GEMINI_API_KEY`. Rather than manipulating environment variables, we pass the key directly via Marker's config dict:

```python
config["gemini_api_key"] = os.environ.get("GEMINI_API_KEY")
```

This avoids side effects and gives us explicit control.

## Existing Patterns Followed

1. **Constructor parameter injection**: Mirrors `text_extraction_llm_enabled` pattern in Library
2. **Lazy loading**: PdfExtractor already uses lazy loading for Marker models
3. **Early CLI validation**: Similar to existing validation patterns, but adds warning before extraction
4. **Graceful degradation**: Matches existing `--llm` behavior where missing keys fall back silently

## Implementation Phases

### Phase 1: PdfExtractor LLM Support

**Tasks:**
1. Add `llm_enabled` parameter to PdfExtractor constructor
2. Modify `_ensure_models_loaded()` to build config dict when LLM enabled
3. Pass config to PdfConverter with `use_llm`, `gemini_api_key`, `redo_inline_math`, `disable_image_extraction`
4. Add tests for LLM-enabled extraction (mocked Marker)

### Phase 2: Library Configuration Passthrough

**Tasks:**
1. Add `pdf_llm_enabled` parameter to Library constructor
2. Pass to PdfExtractor when creating default extractors
3. Update Library tests

### Phase 3: CLI Integration and Validation

**Tasks:**
1. Add `--llm-extract` flag to add command
2. Add `check_api_key_available()` helper function
3. Add early validation for both `--llm-extract` and `--llm` flags with warning output
4. Pass `pdf_llm_enabled` to Library
5. Add CLI tests for new flag and validation behavior

### Phase 4: Documentation and Manual Testing

**Tasks:**
1. Update CLI help text
2. Update CLAUDE.md files if contracts changed
3. Manual testing with test PDFs (NIST2023.pdf, Massachusetts2024.pdf, Hu2018.pdf, Dhingra2022.pdf)

## Additional Considerations

### Marker Configuration Options

| Option | Value | Purpose |
|--------|-------|---------|
| `use_llm` | `True` | Enable LLM-enhanced extraction |
| `gemini_api_key` | from env | API authentication |
| `redo_inline_math` | `True` | Better LaTeX math extraction |
| `disable_image_extraction` | `True` | Replace images with LLM descriptions |

### Not Configured (Using Marker Defaults)

- `llm_service`: Defaults to Gemini (what we want)
- Model selection: Defaults to `gemini-2.0-flash` (matches our existing pattern)

### Testing Strategy

- Unit tests with mocked Marker to verify config dict construction
- Integration tests (manual) with real PDFs to verify quality improvement
- CLI tests for flag parsing and validation behavior

### Future Extensions

If needed later:
- `--llm-extract-model` flag to override Gemini model
- Support for other LLM providers (Claude, OpenAI, Ollama)
- Per-document LLM extraction settings
