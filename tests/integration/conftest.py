"""Fixtures for integration tests."""

# pattern: Imperative Shell

from pathlib import Path

import pytest

from local_library.core import Library


@pytest.fixture
def integration_library(temp_dir: Path) -> Library:
    """Provide a Library instance for integration testing.

    Uses temporary directories for all storage to ensure test isolation.
    Text extraction is disabled by default for compatibility with existing tests
    that use minimal mock text. Tests that want text extraction can pass
    text_extraction_enabled=True when creating a Library.
    """
    return Library(
        db_path=temp_dir / "test.db",
        storage_dir=temp_dir / "storage",
        extracted_dir=temp_dir / "extracted",
        text_extraction_enabled=False,
    )


@pytest.fixture
def integration_library_with_text_extraction(temp_dir: Path) -> Library:
    """Provide a Library instance with text extraction enabled.

    Used for tests that specifically test text extraction functionality.
    """
    return Library(
        db_path=temp_dir / "test.db",
        storage_dir=temp_dir / "storage",
        extracted_dir=temp_dir / "extracted",
        text_extraction_enabled=True,
    )


@pytest.fixture
def sample_pdf_content() -> bytes:
    """Provide minimal valid PDF content for testing.

    This is a minimal PDF that Marker can parse, though extraction
    may produce minimal output.
    """
    # Minimal valid PDF structure
    return b"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R >>
endobj
4 0 obj
<< /Length 44 >>
stream
BT
/F1 12 Tf
100 700 Td
(Hello World) Tj
ET
endstream
endobj
xref
0 5
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
0000000214 00000 n
trailer
<< /Size 5 /Root 1 0 R >>
startxref
306
%%EOF"""


@pytest.fixture
def sample_pdf(temp_dir: Path, sample_pdf_content: bytes) -> Path:
    """Create a sample PDF file for testing."""
    pdf_path = temp_dir / "sample.pdf"
    pdf_path.write_bytes(sample_pdf_content)
    return pdf_path


@pytest.fixture
def multiple_pdfs(temp_dir: Path, sample_pdf_content: bytes) -> list[Path]:
    """Create multiple PDF files with different content."""
    pdfs = []
    for i in range(3):
        # Modify content slightly to get different hashes
        content = sample_pdf_content + f"\n% Document {i}".encode()
        pdf_path = temp_dir / f"doc{i}.pdf"
        pdf_path.write_bytes(content)
        pdfs.append(pdf_path)
    return pdfs
