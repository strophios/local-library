# PDF to Markdown Conversion for Academic RAG Systems

## Executive Summary

For a personal knowledge management system processing ~1400+ academic PDFs on an M1 Pro MacBook, we recommend a **tiered approach**:

1. **Primary processor**: Marker (best quality/performance balance for most PDFs)
2. **Academic metadata extraction**: GROBID (for structured bibliographic data) — *optional, adds external service dependency*
3. **Fallback for problem documents**: PyMuPDF direct extraction

**Critical caveat**: The system already has CSL-JSON from Zotero for existing items; evaluate whether GROBID adds value beyond CrossRef lookup before committing to that dependency.

---

## Tool-by-Tool Analysis

### Marker (VikParuchuri/marker)
**What it is**: Deep learning-based PDF to markdown converter optimized for books and academic papers.

| Aspect | Assessment |
|--------|------------|
| Multi-column layouts | Excellent |
| Equations | Good (converts to LaTeX) |
| Tables | Good |
| Scanned PDFs | Good (built-in OCR) |
| M1 Pro Performance | 1-3 min per 20-page paper |
| Memory | 4-8GB typical |

**Strengths**:
- Preserves document structure (headings, lists, tables)
- Runs well on Apple Silicon with MPS acceleration
- Active development
- Designed specifically for books and papers

**Weaknesses**:
- Headers/footers not always perfectly filtered
- Occasional equation rendering issues with complex notation
- Output optimized for readability, not necessarily for RAG chunking

**Rating**: ★★★★☆ (Best overall for academic PDFs)

### GROBID
**What it is**: Machine learning library for extracting and restructuring scholarly documents into TEI XML.

| Aspect | Assessment |
|--------|------------|
| Metadata extraction | Best-in-class |
| Citation parsing | Excellent |
| Section identification | Excellent |
| Self-sufficient | No (requires service) |

**Strengths**:
- Best for academic metadata (title, authors, affiliations, abstract)
- Excellent citation/reference parsing
- Can identify sections semantically

**Weaknesses**:
- Outputs TEI XML (requires conversion to markdown)
- Runs as external Java service (Docker recommended)
- Adds operational complexity
- Limited OCR support

**Consideration**: Since you already have Zotero CSL-JSON, GROBID's primary benefit is for documents *not* from Zotero. Evaluate whether CrossRef lookup (already planned) provides sufficient metadata before adding this dependency.

**Rating**: ★★★★☆ (Best for metadata, but adds complexity)

### Docling (IBM)
| Aspect | Assessment |
|--------|------------|
| Table extraction | Excellent (best-in-class) |
| Multi-column | Good |
| Academic focus | Moderate |

**When to use**: Documents with complex tables that Marker struggles with.

**Rating**: ★★★☆☆

### Nougat (Meta)
| Aspect | Assessment |
|--------|------------|
| Equation rendering | Excellent (best-in-class) |
| Speed | Very slow (~30-60 sec/page) |
| M1 Support | Limited (CPU fallback) |

**When to use**: Equation-heavy papers where Marker fails; batch process overnight.

**Rating**: ★★★☆☆

### PyMuPDF
| Aspect | Assessment |
|--------|------------|
| Speed | Excellent (milliseconds/page) |
| Memory | Very low (<100MB) |
| Semantic understanding | None |

**When to use**: Fallback when ML-based tools fail; structural analysis of PDFs.

**Rating**: ★★☆☆☆ (Fast but requires custom post-processing)

---

## Performance Estimates for 1400 Documents

| Tool | Total Time | Notes |
|------|------------|-------|
| Marker | 40-100 hours | Realistic for M1 Pro; run in batches |
| PyMuPDF only | ~5 minutes | Poor quality output |
| GROBID (metadata) | 10-20 hours | Metadata extraction only |

**Important**: These are estimates. Actual performance varies significantly by:
- PDF type (native vs. scanned)
- Document complexity
- Thermal throttling under sustained load

---

## RAG-Specific Considerations

**The critical insight from review**: Readable markdown ≠ RAG-optimized output.

For RAG systems, what matters is:
1. **Semantic boundary preservation**: Does output maintain section/paragraph breaks?
2. **Chunk quality**: Will chunks be semantically coherent?
3. **Metadata for filtering**: Can chunks be associated with section type (methods, results, etc.)?

**Marker's output** is optimized for human readability, which correlates with but doesn't guarantee good chunking. Test with your actual RAG pipeline before committing.

### Recommended Validation Process

Before batch-processing 1400 documents:

1. **Sample stratified test set**: 50 PDFs across:
   - Native PDFs (text-based)
   - Scanned PDFs
   - Multi-column layouts
   - Equation-heavy
   - Table-heavy

2. **Measure**:
   - Extraction time per document
   - Markdown structure quality (manual review)
   - Chunk quality for RAG (test retrieval)

3. **Define fallback strategy**:
   - Marker fails → PyMuPDF with heuristic section detection
   - PyMuPDF fails → Flag for manual review

---

## Recommendations

### Easiest Path
**Marker alone** with PyMuPDF fallback.

```python
from marker.convert import convert_single_pdf
from marker.models import load_all_models

models = load_all_models()

def process_pdf(pdf_path: str) -> tuple[str, dict]:
    try:
        text, images, meta = convert_single_pdf(
            pdf_path, models, langs=["en"]
        )
        return text, {"status": "success", "tool": "marker"}
    except Exception as e:
        # Fallback to PyMuPDF
        text = pymupdf_extract(pdf_path)
        return text, {"status": "fallback", "tool": "pymupdf", "error": str(e)}
```

### Highest Quality (If You Need It)
**Marker for body text + GROBID for metadata** — but only if:
- You're ingesting many documents NOT from Zotero
- CrossRef lookup doesn't provide adequate metadata
- You're willing to run a GROBID service

### Recommended for Your Use Case
**Marker as primary** with:
1. PyMuPDF fallback for failures
2. Hash-based deduplication before processing
3. Quality flags in database (to revisit problematic extractions)
4. Defer GROBID until you've evaluated CrossRef adequacy

---

## Implementation Checklist

```
[ ] Install marker-pdf and dependencies
[ ] Test on 10 representative PDFs from Zotero library
[ ] Implement fallback to PyMuPDF
[ ] Add content hash computation for deduplication
[ ] Create quality flag field in database schema
[ ] Batch process in chunks (100 docs/batch) with checkpointing
[ ] Review and address failed extractions
```

---

## Open Questions

1. **Reference section handling**: Exclude from embeddings? Parse separately?
2. **Figure/table handling**: Store as separate artifacts? Include alt-text in chunks?
3. **Incremental updates**: How to detect Zotero PDF updates and re-extract?
