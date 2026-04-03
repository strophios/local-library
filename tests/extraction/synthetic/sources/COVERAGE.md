# Feature Coverage Matrix for Extraction Quality Tests

This matrix documents the planned feature coverage across all synthetic source documents. Each document is designed to exercise 5-8 features in realistic context, and every feature type is covered by at least 2 documents.

| Feature Type | Doc 1: Urban Transit | Doc 2: Climate Stats | Doc 3: NAS Survey | Doc 4: Labor History | Doc 5: Empirical Study | Doc 6: Engineering |
|---|---|---|---|---|---|---|
| heading-h1 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| heading-h2 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| heading-h3 | | | ✓ | | ✓ | |
| heading-h4 | | | ✓ | | | |
| table-simple | ✓ | | | | | |
| table-complex | | | | | ✓ | |
| footnote | ✓ | | | ✓ | | |
| bibliography | ✓ | ✓ | | ✓ | | |
| display-math | | ✓ | | ✓ | ✓ | |
| inline-math | | ✓ | ✓ | | ✓ | |
| blockquote | | | | ✓ | | |
| code-block | | | ✓ | | | ✓ |
| nested-list | | | ✓ | | | |
| dense-prose | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |

## Document Design

### Doc 1: Urban Transit (5-8 features)
Comparative analysis of urban mass transit systems. Features: h1, h2, dense-prose, simple-table, footnote, bibliography.

### Doc 2: Climate Stats (5-8 features)
Statistical analysis of climate modeling data. Features: h1, h2, dense-prose, display-math, inline-math, bibliography.

### Doc 3: NAS Survey (5-8 features)
Neural architecture search methodology overview. Features: h1, h2, h3, h4, dense-prose, code-block, nested-list, inline-math.

### Doc 4: Labor History (5-8 features)
Historical survey of labor movements. Features: h1, h2, dense-prose, footnote, bibliography, blockquote, display-math.

### Doc 5: Empirical Study (5-8 features)
Empirical research study with complex results. Features: h1, h2, h3, dense-prose, display-math, inline-math, complex-table.

### Doc 6: Engineering (5-8 features)
Engineering technical report. Features: h1, h2, dense-prose, code-block.

## Feature Definitions

- **heading-h1**: Top-level document title
- **heading-h2**: Section headings
- **heading-h3**: Subsection headings
- **heading-h4**: Sub-subsection headings
- **table-simple**: Simple 3-column data table
- **table-complex**: Multi-column table with merged cells or complex structure
- **footnote**: Inline footnote or endnote references
- **bibliography**: Bibliography or references section
- **display-math**: Block-level mathematical notation (e.g., equations on their own line)
- **inline-math**: Inline mathematical notation within text
- **blockquote**: Extended quoted text blocks
- **code-block**: Code snippets or algorithm pseudocode
- **nested-list**: Multi-level lists with indentation
- **dense-prose**: Paragraph-level dense academic prose
