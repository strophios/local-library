"""Unit tests for error module."""

import pytest

from local_library.core.errors import (
    AcquisitionError,
    ErrorCode,
    ExtractionError,
    LocalLibraryError,
    LookupError,
    MetadataError,
    QualityError,
    StorageError,
    ZoteroError,
)


class TestErrorCode:
    """Tests for ErrorCode enum."""

    def test_error_code_is_string(self) -> None:
        """ErrorCode values should be strings for JSON serialization."""
        assert isinstance(ErrorCode.ACQUISITION_FILE_NOT_FOUND.value, str)
        assert ErrorCode.ACQUISITION_FILE_NOT_FOUND.value == "ACQUISITION_FILE_NOT_FOUND"

    def test_all_error_codes_have_string_values(self) -> None:
        """All error codes should have matching string values."""
        for code in ErrorCode:
            assert code.value == code.name

    def test_acquisition_unsupported_source_is_string(self) -> None:
        """ACQUISITION_UNSUPPORTED_SOURCE should have string value."""
        assert ErrorCode.ACQUISITION_UNSUPPORTED_SOURCE == "ACQUISITION_UNSUPPORTED_SOURCE"
        assert isinstance(ErrorCode.ACQUISITION_UNSUPPORTED_SOURCE, str)

    def test_extraction_unsupported_format_is_string(self) -> None:
        """EXTRACTION_UNSUPPORTED_FORMAT should have string value."""
        assert ErrorCode.EXTRACTION_UNSUPPORTED_FORMAT == "EXTRACTION_UNSUPPORTED_FORMAT"
        assert isinstance(ErrorCode.EXTRACTION_UNSUPPORTED_FORMAT, str)

    def test_extraction_fallback_error_code(self) -> None:
        """EXTRACTION_FALLBACK should be a valid ErrorCode."""
        assert ErrorCode.EXTRACTION_FALLBACK == "EXTRACTION_FALLBACK"
        assert ErrorCode.EXTRACTION_FALLBACK.value == "EXTRACTION_FALLBACK"


class TestLocalLibraryError:
    """Tests for base exception class."""

    def test_exception_stores_message_and_code(self) -> None:
        """Exception should store message and error code."""
        error = LocalLibraryError("test message", ErrorCode.NOT_FOUND)

        assert error.message == "test message"
        assert error.code == ErrorCode.NOT_FOUND
        assert error.details == {}

    def test_exception_stores_details(self) -> None:
        """Exception should store optional details dict."""
        details = {"path": "/some/path", "size": 1024}
        error = LocalLibraryError("test", ErrorCode.NOT_FOUND, details=details)

        assert error.details == details

    def test_str_format_includes_code(self) -> None:
        """String representation should include error code."""
        error = LocalLibraryError("file missing", ErrorCode.ACQUISITION_FILE_NOT_FOUND)

        assert str(error) == "[ACQUISITION_FILE_NOT_FOUND] file missing"

    def test_exception_is_catchable(self) -> None:
        """Exception should be catchable as LocalLibraryError."""
        with pytest.raises(LocalLibraryError):
            raise LocalLibraryError("test", ErrorCode.NOT_FOUND)


class TestSpecificExceptions:
    """Tests for specific exception subclasses."""

    def test_acquisition_error_inherits_from_base(self) -> None:
        """AcquisitionError should inherit from LocalLibraryError."""
        error = AcquisitionError("file not found", ErrorCode.ACQUISITION_FILE_NOT_FOUND)

        assert isinstance(error, LocalLibraryError)
        assert isinstance(error, AcquisitionError)

    def test_extraction_error_inherits_from_base(self) -> None:
        """ExtractionError should inherit from LocalLibraryError."""
        error = ExtractionError("marker crashed", ErrorCode.EXTRACTION_MARKER_CRASH)

        assert isinstance(error, LocalLibraryError)
        assert isinstance(error, ExtractionError)

    def test_quality_error_inherits_from_base(self) -> None:
        """QualityError should inherit from LocalLibraryError."""
        error = QualityError("output too short", ErrorCode.QUALITY_TOO_SHORT)

        assert isinstance(error, LocalLibraryError)
        assert isinstance(error, QualityError)

    def test_storage_error_inherits_from_base(self) -> None:
        """StorageError should inherit from LocalLibraryError."""
        error = StorageError("database error", ErrorCode.STORAGE_DATABASE_ERROR)

        assert isinstance(error, LocalLibraryError)
        assert isinstance(error, StorageError)

    def test_lookup_error_inherits_from_base(self) -> None:
        """LookupError should inherit from LocalLibraryError."""
        error = LookupError("not found", ErrorCode.NOT_FOUND)

        assert isinstance(error, LocalLibraryError)
        assert isinstance(error, LookupError)

    def test_can_catch_specific_exception(self) -> None:
        """Should be able to catch specific exception types."""
        with pytest.raises(AcquisitionError):
            raise AcquisitionError("test", ErrorCode.ACQUISITION_FILE_NOT_FOUND)

    def test_can_catch_as_base_exception(self) -> None:
        """Should be able to catch specific exceptions as base type."""
        with pytest.raises(LocalLibraryError):
            raise AcquisitionError("test", ErrorCode.ACQUISITION_FILE_NOT_FOUND)


class TestMetadataErrorCodes:
    """Tests for metadata-related error codes."""

    def test_metadata_invalid_schema_is_string(self) -> None:
        """METADATA_INVALID_SCHEMA should have string value."""
        assert ErrorCode.METADATA_INVALID_SCHEMA == "METADATA_INVALID_SCHEMA"
        assert isinstance(ErrorCode.METADATA_INVALID_SCHEMA, str)

    def test_metadata_invalid_type_is_string(self) -> None:
        """METADATA_INVALID_TYPE should have string value."""
        assert ErrorCode.METADATA_INVALID_TYPE == "METADATA_INVALID_TYPE"
        assert isinstance(ErrorCode.METADATA_INVALID_TYPE, str)

    def test_metadata_citekey_invalid_is_string(self) -> None:
        """METADATA_CITEKEY_INVALID should have string value."""
        assert ErrorCode.METADATA_CITEKEY_INVALID == "METADATA_CITEKEY_INVALID"
        assert isinstance(ErrorCode.METADATA_CITEKEY_INVALID, str)


class TestMetadataError:
    """Tests for MetadataError exception class."""

    def test_metadata_error_inherits_from_base(self) -> None:
        """MetadataError should inherit from LocalLibraryError."""
        error = MetadataError("invalid schema", ErrorCode.METADATA_INVALID_SCHEMA)

        assert isinstance(error, LocalLibraryError)
        assert isinstance(error, MetadataError)

    def test_metadata_error_stores_message_and_code(self) -> None:
        """MetadataError should store message and code."""
        error = MetadataError(
            "missing type field",
            ErrorCode.METADATA_INVALID_TYPE,
            details={"field": "type"},
        )

        assert error.message == "missing type field"
        assert error.code == ErrorCode.METADATA_INVALID_TYPE
        assert error.details == {"field": "type"}

    def test_can_catch_metadata_error_as_base(self) -> None:
        """Should be able to catch MetadataError as LocalLibraryError."""
        with pytest.raises(LocalLibraryError):
            raise MetadataError("test", ErrorCode.METADATA_INVALID_SCHEMA)


class TestZoteroErrorCodes:
    """Tests for Zotero-specific error codes."""

    def test_zotero_error_codes_exist(self) -> None:
        """All Zotero error codes should be defined in ErrorCode enum."""
        assert ErrorCode.ZOTERO_DIR_NOT_FOUND.value == "ZOTERO_DIR_NOT_FOUND"
        assert ErrorCode.ZOTERO_DATABASE_NOT_FOUND.value == "ZOTERO_DATABASE_NOT_FOUND"
        assert ErrorCode.ZOTERO_DATABASE_LOCKED.value == "ZOTERO_DATABASE_LOCKED"
        assert ErrorCode.ZOTERO_DATABASE_ERROR.value == "ZOTERO_DATABASE_ERROR"
        assert ErrorCode.ZOTERO_LIBRARY_JSON_NOT_FOUND.value == "ZOTERO_LIBRARY_JSON_NOT_FOUND"
        assert ErrorCode.ZOTERO_LIBRARY_JSON_PARSE_ERROR.value == "ZOTERO_LIBRARY_JSON_PARSE_ERROR"
        assert ErrorCode.ZOTERO_ITEM_NOT_FOUND.value == "ZOTERO_ITEM_NOT_FOUND"
        assert ErrorCode.ZOTERO_CITEKEY_NOT_FOUND.value == "ZOTERO_CITEKEY_NOT_FOUND"
        assert ErrorCode.ZOTERO_ATTACHMENT_MISSING.value == "ZOTERO_ATTACHMENT_MISSING"

    def test_zotero_error_inherits_from_base(self) -> None:
        """ZoteroError should inherit from LocalLibraryError."""
        error = ZoteroError(
            message="zotero directory not found",
            code=ErrorCode.ZOTERO_DIR_NOT_FOUND,
            details={"path": "/nonexistent"},
        )

        assert isinstance(error, LocalLibraryError)
        assert error.code == ErrorCode.ZOTERO_DIR_NOT_FOUND
        assert error.details == {"path": "/nonexistent"}
        assert str(error) == "[ZOTERO_DIR_NOT_FOUND] zotero directory not found"


def test_not_implemented_error_code_exists() -> None:
    from local_library.core.errors import ErrorCode

    assert ErrorCode.NOT_IMPLEMENTED.value == "NOT_IMPLEMENTED"
