# PDF Extraction Tools for Academic Document RAG Systems

A comprehensive analysis for implementing PDF extraction in a personal knowledge management system targeting ~1400+ academic PDFs on Apple Silicon hardware.

---

## Table of Contents

1. [Problem Space Overview](#problem-space-overview)
2. [Tool Analysis](#tool-analysis)
   - [Marker](#marker)
   - [MinerU](#mineru)
   - [Nougat](#nougat)
   - [GROBID](#grobid)
   - [Docling](#docling)
   - [olmOCR](#olmocr)
   - [Lower-Level Libraries](#lower-level-libraries)
3. [Comparative Analysis](#comparative-analysis)
4. [Recommendations](#recommendations)
5. [Open Questions and Empirical Benchmarking](#open-questions-and-empirical-benchmarking)

---

## Problem Space Overview

### The Challenge

Academic PDFs present unique extraction challenges that standard OCR and text extraction tools struggle with:

- **Complex layouts**: Multi-column text, figures interleaved with text, sidebars, and marginal notes
- **Mathematical content**: Inline and display equations requiring LaTeX or MathML output
- **Tables**: Both simple and complex (spanning, nested headers, merged cells)
- **Citations and references**: Structured bibliographic data embedded in unstructured text
- **Document structure**: Heading hierarchies, abstract/body/conclusion delineation
- **Visual elements**: Figures, captions, and their relationships to surrounding text
- **Scanned documents**: OCR requirements for older papers or institutional scans

The target output for a RAG system is well-structured markdown that preserves:
1. Semantic structure (headings, paragraphs, lists)
2. Reading order (especially for multi-column layouts)
3. Mathematical expressions (ideally as LaTeX)
4. Table data (preserving relationships)
5. Clean body text (stripped of headers, footers, page numbers)

### Hardware Context

**Target system**: 2021 MacBook Pro with M1 Pro

Key constraints:
- Apple Silicon (ARM64) architecture—not all tools have native support
- Metal Performance Shaders (MPS) available for GPU acceleration in PyTorch
- Unified memory architecture (likely 16GB or 32GB shared between CPU and GPU)
- No NVIDIA CUDA support

This hardware context significantly influences tool selection, as many ML-based extraction tools are optimized primarily for NVIDIA GPUs.

---

## Tool Analysis

### Marker

**Repository**: [github.com/datalab-to/marker](https://github.com/datalab-to/marker)
**License**: GPL-3.0 with commercial restrictions (>$5M revenue)

#### How It Works

Marker is an end-to-end pipeline that converts PDFs to markdown, JSON, or HTML. It combines multiple specialized models:

- **Layout analysis**: Uses LayoutLMv3 or similar transformer models
- **OCR**: Built on Surya OCR for text recognition
- **Post-processing**: Deterministic parsing for tables, equations, and code blocks
- **LLM enhancement**: Optional flag (`--use-llm`) for complex tables/formulas via Gemini or Ollama

The pipeline preserves document structure including sections, paragraphs, lists, footnotes, and logical reading order. It automatically exports images and tables as separate files.

#### M1 Mac Compatibility

**Native MPS support**: Yes. Set `TORCH_DEVICE=mps` in `local.env` for GPU acceleration via Metal Performance Shaders. CPU is the default if not configured.

**Performance on M3 Mac SoC**: ~4.2 sec/page (per Docling technical report benchmarks)
**Performance on x86 CPU**: ~16 sec/page
**Performance with CUDA (L4 GPU)**: ~0.86 sec/page

For ~1400 PDFs at average 15 pages each, M1 processing would take approximately:
- MPS acceleration: ~24 hours (at ~4 sec/page)
- CPU only: ~93 hours

#### Strengths

- **Balanced accuracy and speed**: 10x faster than Nougat with comparable accuracy on most documents
- **Low hallucination risk**: Unlike pure transformer approaches, uses deterministic post-processing
- **Multi-format output**: Markdown, JSON, HTML
- **Active development**: Regular updates, responsive maintainers
- **Good language support**: Best for English and similar Latin-based languages; provisional support for CJK

#### Weaknesses

- **Embedded formula detection**: Struggles with inline equations according to ReADoc benchmark
- **Slower than MinerU on GPU**: When CUDA is available, MinerU significantly outperforms
- **Commercial license restrictions**: May matter for future use cases
- **OCR limitations**: "Works best on digital PDFs that won't require a lot of OCR"

#### Academic PDF Quality

Marker performs well on:
- Standard two-column academic layouts (IEEE, ACM formats)
- Book-structured documents
- Documents with clear heading hierarchies

It struggles with:
- Heavy mathematical content
- Complex nested tables
- Scanned documents requiring significant OCR

**Benchmark scores** (olmOCR-Bench): 76.1 points

---

### MinerU

**Repository**: [github.com/opendatalab/MinerU](https://github.com/opendatalab/MinerU)
**License**: AGPL-3.0
**Developer**: OpenDataLab (Shanghai AI Laboratory)

#### How It Works

MinerU employs a multi-model pipeline with five specialized components:

1. **Layout detection**: 77.6% mAP accuracy
2. **Formula detection**: 87.7% AP50
3. **Table recognition**: Dedicated model for structure extraction
4. **Formula recognition**: 0.968 CDM score, outputs LaTeX
5. **OCR**: PaddleOCR supporting 84+ languages

MinerU 2.5 introduced a hybrid backend architecture for improved flexibility.

#### M1 Mac Compatibility

**MPS support**: Yes, officially supported. The [mcp-mineru project](https://github.com/TINKPA/mcp-mineru) provides MLX-optimized acceleration specifically for Apple Silicon (M1/M2/M3/M4).

**Known issues**:
- Some users report "Illegal hardware instruction" errors on macOS Sonoma with M1
- Docling technical report notes MinerU "did not finish any run" on MacBook Pro M3 Max in their tests

**Performance with MLX acceleration**:
- 50-page document in ~15 seconds (3x faster than CPU)
- GPU usage: 60%, CPU: 25%, Memory: 2.8GB

**Performance benchmarks**:
- x86 CPU: ~3.3 sec/page
- CUDA (L4 GPU): ~0.21 sec/page (fastest among tested tools)

#### Strengths

- **Strongest formula handling**: High accuracy for LaTeX output from equations
- **Best multi-language support**: 84+ languages including CJK
- **Excellent preprocessing**: Removes headers, footers, footnotes, page numbers automatically
- **Consistent reading order**: Best performance on multi-column layouts per OmniDocBench
- **Strong layout segmentation**: Competitive with commercial tools

#### Weaknesses

- **Table recognition**: Falls short compared to other tools per ReADoc benchmark
- **M1 stability**: Reports of crashes and compatibility issues
- **Mixed language accuracy drop**: Performance decreases with Chinese-English mixed content
- **Complex installation**: Multiple model dependencies
- **AGPL license**: Copyleft requirements may affect integration

#### Academic PDF Quality

MinerU excels at:
- Complex reports requiring high fidelity
- Documents with mathematical expressions
- Multi-column academic papers
- Non-English academic documents

**Benchmark scores** (olmOCR-Bench): 75.8 points
**OmniDocBench**: Most consistent reading order prediction among pipeline tools

---

### Nougat

**Repository**: [github.com/facebookresearch/nougat](https://github.com/facebookresearch/nougat)
**License**: MIT (permissive)
**Developer**: Meta AI

#### How It Works

Nougat (Neural Optical Understanding for Academic Documents) takes a fundamentally different approach: a single end-to-end transformer model trained to convert document images directly to markup.

Architecture:
- Based on **DONUT** (Document Understanding Transformer)
- **350M parameters** (base model)
- Trained on arXiv and PubMed Central papers
- Outputs **MultiMarkdown (.mmd)** format

Unlike pipeline tools, Nougat processes documents as images and learns the entire conversion task end-to-end.

#### M1 Mac Compatibility

Nougat can run on M1 Macs via PyTorch MPS, though it's slower than CUDA-accelerated execution. Memory requirements for the 350M parameter model are manageable on 16GB unified memory.

**Installation**: `pip install nougat-ocr`

#### Strengths

- **Best-in-class formula extraction**: 75%+ accuracy on equations vs. GROBID's ~11%
- **Trained specifically for academic documents**: arXiv/PMC training data
- **End-to-end simplicity**: No pipeline configuration
- **MIT license**: Fully permissive
- **Native LaTeX output**: Mathematical expressions in LaTeX format

#### Weaknesses

- **Speed**: ~10x slower than Marker
- **English-only practical use**: Other Latin languages "might work"; CJK will not
- **Generalization issues**: Performance drops on non-arXiv-style documents (ReADoc benchmark shows 81.42 → 74.12 on GitHub docs)
- **Hallucination risk**: End-to-end models can generate plausible but incorrect text
- **Limited to academic PDFs**: Poor performance on invoices, forms, general documents

#### Academic PDF Quality

For arXiv-style papers, Nougat achieves:
- **BLEU score**: >91% for continuous text
- **Text accuracy**: >96%
- **Formula/table accuracy**: ~75%

The model's training on academic documents makes it exceptionally good for papers following standard academic formatting conventions.

---

### GROBID

**Repository**: [github.com/kermitt2/grobid](https://github.com/kermitt2/grobid)
**License**: Apache-2.0
**Production users**: Semantic Scholar, ResearchGate, scite.ai

#### How It Works

GROBID (GeneRation Of BIbliographic Data) is a mature, production-grade system specifically designed for extracting **structured metadata** from academic documents. It uses:

- Conditional Random Fields (CRF) for sequence labeling
- Optional deep learning models via DeLFT integration
- Rule-based post-processing for citation parsing

Output format is **TEI XML** (Text Encoding Initiative), a rich structured format that captures:
- Document sections
- Authors, affiliations, abstracts
- Citations and bibliographic references
- Figures and tables (metadata)

#### M1 Mac Compatibility

**Significant challenges**:

- The full Docker image (`grobid/grobid:0.8.0`) does not run on ARM64—immediately quits with platform mismatch error
- Deep learning models require AVX instructions unavailable on ARM
- The `lfoppiano/grobid:0.8.0` image works but is **CRF-only** (no deep learning)
- macOS Sonoma users report Docker container crashes when processing PDFs

**Workarounds**:
- Use `lfoppiano/grobid:0.8.0` (CRF-only, works on ARM64)
- Third-party ARM64 image: `kurdidev/grobid`
- Native macOS installation (not fully supported)
- Rosetta 2 emulation for x86 images (4-5x performance penalty)

#### Strengths

- **Production-proven**: Used by major academic services at scale
- **Structured output**: TEI XML captures rich document semantics
- **Citation extraction**: Best-in-class bibliographic reference parsing
- **Metadata focus**: Author, affiliation, abstract extraction
- **Mature and stable**: Years of development and community support

#### Weaknesses

- **Formula accuracy**: Only ~11% on mathematical expressions
- **M1 compatibility**: Poor, especially with deep learning models
- **Output format**: TEI XML requires transformation to markdown
- **Processing speed**: 2-5 seconds per page
- **Not optimized for RAG**: Output structure oriented toward bibliographic use cases

#### Academic PDF Quality

GROBID achieves ~90% accuracy on text extraction but its value is in **structured metadata extraction** rather than full-text conversion. For a RAG system, GROBID is better suited as a complementary tool for extracting:
- Citation networks
- Author information
- Abstract/section structure

---

### Docling

**Repository**: [github.com/docling-project/docling](https://github.com/docling-project/docling)
**License**: MIT
**Developer**: IBM Research Zurich / LF AI & Data Foundation

#### How It Works

Docling uses a modular pipeline approach:

- **TableFormer**: 97.9% accuracy on complex table extraction
- **Vision model integration**: Optional VLM enhancement
- **Granite-Docling**: 258M parameter model handling math, code, tables
- **Multi-format support**: PDF, DOCX, PPTX, XLSX, HTML, images, audio

Output formats include markdown and JSON with structured document representation.

#### M1 Mac Compatibility

**MLX acceleration**: Docling supports MLX on Apple Silicon.

**Performance** (per Docling technical report):
- M3 Max SoC: **1.27 sec/page** (fastest among tested tools on Mac)
- x86 CPU: 3.1 sec/page
- CUDA (L4 GPU): 0.49 sec/page

**Known issues**:
- Dependency conflict with mlx-vlm and docling-ibm-models in v2.31
- Transformers version incompatibility (mlx-vlm needs ≥4.51.3, docling-ibm-models needs <4.43.0)
- Formula enrichment (`do_formula_enrichment=True`) may cause CUDA OOM even on 24GB cards

#### Strengths

- **Best table extraction**: 97.9% accuracy on complex tables
- **Fastest on Mac**: 1.27 sec/page on M3 Max
- **MIT license**: Fully permissive
- **Multi-format input**: Not limited to PDFs
- **Foundation backing**: LF AI & Data, IBM Research

#### Weaknesses

- **Dependency conflicts**: Current version has Apple Silicon setup issues
- **Formula handling**: Requires significant VRAM; may struggle on M1
- **Newer tool**: Less community testing than Marker/MinerU
- **VLM integration complexity**: Advanced features require additional setup

#### Academic PDF Quality

Docling and Mistral OCR were both able to "detect, extract, and correctly format equations" in the "Attention Is All You Need" paper benchmark. Strong performance on:
- Tables (best-in-class)
- Clean digital-born PDFs
- Documents with relatively simple layouts

---

### olmOCR

**Repository**: [github.com/allenai/olmocr](https://github.com/allenai/olmocr)
**License**: Apache-2.0
**Developer**: Allen Institute for AI (AI2)

#### How It Works

olmOCR represents the newest generation of OCR tools, built on Vision Language Models:

- **Base model**: Qwen2.5-VL-7B-Instruct (7B parameters)
- **Training data**: olmOCR-mix-1025 dataset with 270,000 PDF pages
- **Coverage**: Academic papers, historical scans, legal documents, handwritten content
- **Output**: Plain text and markdown preserving reading order

olmOCR 2 (October 2025) introduced reinforcement learning training for improved accuracy.

#### M1 Mac Compatibility

**Not recommended for M1 Macs**:
- Requires recent NVIDIA GPU (RTX 4090, L40S, A100, H100)
- Minimum 20GB GPU VRAM
- 30GB free disk space
- No MPS/MLX support documented

This is effectively NVIDIA-only for local deployment.

#### Strengths

- **State-of-the-art accuracy**: 82.4 points on olmOCR-Bench (highest among open-source tools)
- **Diverse document handling**: Academic, legal, historical, handwritten
- **Apache 2.0 license**: Permissive
- **Active development**: Regular 2025 updates
- **Robust OCR**: Handles scanned documents well

#### Weaknesses

- **Hardware requirements**: Impractical for M1 Mac local deployment
- **Large model**: 7B parameters require significant resources
- **Speed**: Slower than pipeline-based approaches
- **New tool**: Less production testing

#### Academic PDF Quality

olmOCR 2 outperforms Marker (76.1) and MinerU (75.8) on olmOCR-Bench, making it the current accuracy leader. Particularly strong on:
- Complex layouts
- Scanned historical documents (82.3% accuracy on historical math scans)
- Mixed text/diagram pages
- Complex tables (84.9% accuracy)

However, the hardware requirements make it unsuitable for the target M1 Mac use case unless using cloud inference.

#### Benchmark Disputes

**Important caveat**: The benchmarking claims between olmOCR and Marker are contested:

- **olmOCR's claim**: Human ELO rankings place olmOCR at 1,800+ Elo vs Marker at 1,600, with olmOCR winning 61.3% of direct comparisons
- **Marker's counter-claim**: When Marker's team tested with 1,107 documents using LLM-as-judge, Marker won 56% of comparisons. They note olmOCR's benchmarks used only 75 samples from ~2,000, filtered on opaque criteria

**Interpretation**: The quality advantage of olmOCR is likely real but narrower than marketing suggests, and concentrated on specific document types (scanned historical documents, complex layouts, handwritten content). For digital-born PDFs with clear text, the difference may be minimal.

#### Speed Comparison

olmOCR is significantly slower than Marker:
- **Marker**: 20-120 pages/second on comparable hardware
- **olmOCR**: 0.4-4 pages/second (with sglang optimization)
- **Ratio**: Marker is 20-100x faster

This speed difference makes olmOCR impractical for processing entire libraries but potentially worthwhile for selective use on problematic documents.

---

### Lower-Level Libraries

For completeness, these libraries are often used as components or for simpler extraction needs:

#### PyMuPDF (fitz)

- **Speed**: ~0.1 sec/page
- **Strength**: Fast text extraction, good table support
- **Weakness**: No ML models; struggles with complex layouts and equations
- **Use case**: Quick extraction from clean digital PDFs; base layer for custom pipelines

#### pdfplumber

- **Strength**: Exceptional table extraction via geometric analysis
- **Weakness**: Slower; no OCR; no structure preservation
- **Use case**: Table-focused extraction from digital PDFs

#### pypdfium2

- **Strength**: Fast, lightweight PDF rendering
- **Weakness**: Basic text extraction only
- **Use case**: PDF rendering, simple text extraction

These tools are insufficient for academic PDF extraction on their own but may be useful as pipeline components.

---

## Comparative Analysis

### Recommendation Matrix

| Tool | M1 Mac Support | Speed (Mac) | Math/Equations | Tables | Academic Quality | License | Installation Complexity |
|------|----------------|-------------|----------------|--------|------------------|---------|------------------------|
| **Marker** | Excellent (MPS) | ~4 sec/page | Fair | Good | High | GPL-3.0* | Low |
| **MinerU** | Partial (issues) | ~5 sec/page | Excellent | Fair | High | AGPL-3.0 | Medium |
| **Nougat** | Good (MPS) | ~40 sec/page | Excellent | Fair | Very High (arXiv) | MIT | Low |
| **GROBID** | Poor | N/A | Poor | Good | Medium (metadata) | Apache-2.0 | Medium |
| **Docling** | Good (MLX)** | ~1.3 sec/page | Good*** | Excellent | High | MIT | Medium |
| **olmOCR** | None | N/A | Excellent | Good | Highest | Apache-2.0 | N/A (requires NVIDIA) |

\* GPL-3.0 with commercial restrictions >$5M revenue
\** Current dependency conflicts may affect M1 setup
\*** Formula enrichment has high memory requirements

### Accuracy Benchmarks

**olmOCR-Bench** (higher is better, max ~100):
1. olmOCR 2: 82.4
2. Marker: 76.1
3. MinerU: 75.8

**ReADoc Benchmark** (arXiv subset):
1. Nougat: 81.42
2. Pipeline tools: Vary by metric

**Table Extraction**:
1. Docling: 97.9%
2. Others: Significantly lower

### Processing Time Estimates for 1400 PDFs

Assuming average 15 pages per document (21,000 total pages):

| Tool | M1 Pro Estimated Time | Notes |
|------|----------------------|-------|
| Docling | ~7.4 hours | Fastest on Mac |
| Marker | ~23 hours | Reliable MPS support |
| MinerU | ~29 hours | If stability issues resolved |
| Nougat | ~233 hours | Impractical without batching |

---

## Recommendations

### 1. Easiest Path to Working System: **Marker**

**Rationale**:
- Best M1 Mac support with straightforward MPS configuration (`TORCH_DEVICE=mps`)
- Simple installation via pip
- Active community and documentation
- Balanced accuracy acceptable for RAG use
- ~24 hours for full corpus processing

**Setup steps**:
```bash
pip install marker-pdf
# Create local.env with TORCH_DEVICE=mps
# Configure INFERENCE_RAM based on unified memory
```

**Tradeoffs**: Sacrifices some equation accuracy for reliability and ease of use.

### 2. Best Quality Regardless of Effort: **Hybrid Pipeline**

**Approach**: Combine multiple tools for best-of-breed extraction:

1. **Primary extraction**: MinerU (if stability resolved) or Marker
2. **Math-heavy papers**: Nougat for papers with significant equations
3. **Metadata extraction**: GROBID for citations and bibliographic data
4. **Table-heavy documents**: Docling for complex tables

**Implementation**:
- Classify documents by content type (math-heavy, table-heavy, standard)
- Route to appropriate tool
- Merge outputs with conflict resolution

**Tradeoffs**: Significant implementation complexity; multiple dependencies; longest development time.

### 3. Optimal ROI for This Use Case: **Docling with Marker Fallback**

**Rationale**:

Given the constraints (1400 academic PDFs, M1 Mac, quality paramount), Docling offers the best balance:

- **Fastest processing**: 1.27 sec/page on M3 Max (likely similar on M1 Pro)
- **Best table handling**: Critical for academic papers with data tables
- **MIT license**: No restrictions
- **Good equation support**: Handles most LaTeX extraction
- **Native MLX acceleration**: Designed for Apple Silicon

**Implementation strategy**:

1. **Primary**: Docling for all PDFs
2. **Fallback**: Marker for documents where Docling fails or produces poor output
3. **Optional**: Nougat for math-heavy papers identified in pass 1

**Estimated timeline**: ~8-10 hours for primary processing, plus review and fallback passes.

**Risk mitigation**: The dependency conflict issue (mlx-vlm vs docling-ibm-models) should be verified before commitment. Check [github.com/docling-project/docling-ibm-models/issues/102](https://github.com/docling-project/docling-ibm-models/issues/102) for resolution status.

### 4. Hybrid Approach for OCR-Heavy Libraries (With Remote GPU Access)

**For users with**: Access to remote NVIDIA GPUs (cloud instances, HPC cluster) AND a significant proportion of scanned/OCR-heavy documents.

**Rationale**: olmOCR's quality advantage is most pronounced on scanned historical documents, complex layouts, and handwritten content. For digital-born PDFs, Marker performs comparably at 20-100x the speed. A hybrid approach captures the best of both.

**Implementation strategy**:

1. **First pass with Marker** (`--use_llm --force_ocr`):
   - Process all PDFs locally on M1 Mac
   - This handles the majority of documents well
   - Produces extraction quality scores/metrics where available

2. **Quality triage**:
   - Review extraction results for quality issues
   - Identify problematic documents: poor OCR, mangled tables, missing equations
   - This subset is likely 10-30% of a typical academic library

3. **Selective olmOCR**:
   - Process only the problematic subset on remote NVIDIA GPU
   - Requires 20GB+ VRAM (RTX 4090, A100, etc.)
   - Higher quality extraction for difficult documents

4. **Ongoing processing**:
   - Use Marker locally for new documents
   - Route to remote olmOCR only when Marker fails

**When to use olmOCR vs Marker**:

| Document Type | Recommendation |
|---------------|----------------|
| Digital-born PDF (LaTeX-generated) | Marker |
| High-quality scan | Marker |
| Scanned historical document | olmOCR |
| Complex multi-column (pre-1990s) | olmOCR |
| Handwritten/typewritten content | olmOCR |
| Heavy mathematical notation (scanned) | olmOCR |
| Complex tables spanning pages | Consider olmOCR |

**Cost/benefit**: The 20-100x speed difference means processing 1,400 PDFs with olmOCR takes hours vs. minutes with Marker. Given the contested quality claims, the extra time is only justified for documents where Marker demonstrably fails.

**Estimated effort**:
- First pass (Marker): ~24 hours on M1 Mac
- Triage: 2-4 hours manual review
- Selective olmOCR: Depends on subset size; ~1-2 hours for 10% of library on A100

---

## Open Questions and Empirical Benchmarking

### Questions to Resolve Before Implementation

1. **Docling M1 stability**: Is the dependency conflict resolved? Test installation on target machine before committing.

2. **MinerU M1 reliability**: Can the "Illegal hardware instruction" errors be worked around? Worth testing given strong formula handling.

3. **Memory pressure**: With 16GB or 32GB unified memory, what's the practical concurrency limit? Test with actual documents.

4. **Equation quality threshold**: What's "good enough" for RAG? May not need perfect LaTeX if semantic search works on approximate representations.

5. **Scanned PDF prevalence**: What fraction of the 1400 PDFs are scanned vs. digital-born? This affects OCR requirements.

### Recommended Empirical Tests

Create a benchmark set of ~20-30 documents representing:
- [ ] Standard two-column IEEE/ACM papers
- [ ] Math-heavy papers (ML theory, physics)
- [ ] Table-heavy papers (empirical studies, surveys)
- [ ] Scanned older papers
- [ ] Multi-language papers (if present in corpus)

For each tool, measure:
1. **Processing time** per page
2. **Memory usage** peak and sustained
3. **Heading hierarchy accuracy** (manual review)
4. **Equation extraction quality** (sample review)
5. **Table preservation** (sample review)
6. **Failure rate** (crashes, timeouts, corrupted output)

### Quality Validation Approach

Since manual review of 1400 PDFs is impractical, consider:

1. **Statistical sampling**: Review 5% of documents (70 papers) across content types
2. **Automated checks**:
   - Output length vs. page count (detect truncation)
   - Presence of expected sections (abstract, references)
   - LaTeX syntax validity for equations
3. **RAG integration testing**: Test retrieval quality on extracted content

---

## Sources

### Primary Tool Documentation
- [Marker GitHub](https://github.com/datalab-to/marker)
- [MinerU GitHub](https://github.com/opendatalab/MinerU)
- [Nougat GitHub](https://github.com/facebookresearch/nougat)
- [GROBID Documentation](https://grobid.readthedocs.io/)
- [Docling GitHub](https://github.com/docling-project/docling)
- [olmOCR GitHub](https://github.com/allenai/olmocr)

### Benchmarks and Comparisons
- [Docling Technical Report](https://arxiv.org/html/2408.09869v4)
- [OmniDocBench](https://arxiv.org/html/2412.07626v2)
- [ReADoc Benchmark](https://arxiv.org/html/2409.05137v1)
- [olmOCR-Bench](https://olmocr.allenai.org/papers/olmocr.pdf)
- [Jimmy Song: Deep Dive into Open Source PDF to Markdown Tools](https://jimmysong.io/blog/pdf-to-markdown-open-source-deep-dive/)

### M1 Mac Compatibility
- [Marker PyPI - MPS Configuration](https://pypi.org/project/marker-pdf/)
- [MinerU MLX MCP Server](https://github.com/TINKPA/mcp-mineru)
- [GROBID Docker ARM64 Issues](https://github.com/kermitt2/grobid/issues/1089)
- [Docling IBM Models Compatibility Issue](https://github.com/docling-project/docling-ibm-models/issues/102)

### Academic Papers
- [Nougat: Neural Optical Understanding for Academic Documents](https://arxiv.org/pdf/2308.13418)
- [olmOCR 2: Unit Test Rewards for Document OCR](https://allenai.org/blog/olmocr-2)
