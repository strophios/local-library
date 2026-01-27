"""Unit tests for update command."""

import json
from datetime import datetime, timezone
from uuid import UUID

import pytest

from local_library.core.models import Document, DocumentStatus


class TestBuildEditableJson:
    """Tests for JSON structure builder."""

    def test_build_editable_json_structure(self) -> None:
        """Should build correct JSON structure for editing."""
        from local_library.cli.update import build_editable_json

        doc = Document(
            id=UUID("12345678-1234-1234-1234-123456789abc"),
            original_path="/path/to/doc.pdf",
            content_hash="abc123",
            storage_path="/storage/ab/c1/abc123.pdf",
            status=DocumentStatus.NEEDS_REVIEW,
            created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
            updated_at=datetime(2025, 1, 2, tzinfo=timezone.utc),
            extracted_path="/extracted/abc123.md",
            citekey="Smith2023",
            csl_json={"type": "article", "title": "Test"},
            title="Test Title",
            authors="John Smith",
            issued_date="2023",
        )

        result = build_editable_json(doc)
        parsed = json.loads(result)

        # Check readonly block
        assert "_readonly" in parsed
        assert parsed["_readonly"]["id"] == "12345678-1234-1234-1234-123456789abc"
        assert parsed["_readonly"]["original_path"] == "/path/to/doc.pdf"

        # Check editable fields
        assert parsed["status"] == "needs_review"
        assert parsed["citekey"] == "Smith2023"
        assert parsed["csl_json"] == {"type": "article", "title": "Test"}

    def test_build_editable_json_null_fields(self) -> None:
        """Should handle null fields gracefully."""
        from local_library.cli.update import build_editable_json

        doc = Document(
            id=UUID("12345678-1234-1234-1234-123456789abc"),
            original_path="/path/to/doc.pdf",
            content_hash="abc123",
            storage_path="/storage/ab/c1/abc123.pdf",
            status=DocumentStatus.PENDING,
            created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
            updated_at=datetime(2025, 1, 2, tzinfo=timezone.utc),
            citekey=None,
            csl_json=None,
        )

        result = build_editable_json(doc)
        parsed = json.loads(result)

        assert parsed["citekey"] is None
        assert parsed["csl_json"] is None
