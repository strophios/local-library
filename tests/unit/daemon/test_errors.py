"""Tests for LocalLibraryError → JSON-RPC error envelope translation."""

import json

from local_library.core.errors import (
    EmbeddingError,
    ErrorCode,
    LocalLibraryError,
)
from local_library.core.errors import (
    LookupError as LibLookupError,  # avoid shadowing builtin
)
from local_library.daemon import errors, protocol


def test_local_library_error_maps_to_server_error_code() -> None:
    exc = LibLookupError(
        "document not found",
        ErrorCode.NOT_FOUND,
        details={"identifier": "@xyz"},
    )
    line = errors.translate(request_id=7, exception=exc)
    body = json.loads(line)
    assert body["error"]["code"] == protocol.SERVER_ERROR  # -32000
    assert body["error"]["message"] == "document not found"
    assert body["error"]["data"]["error_code"] == "NOT_FOUND"
    assert body["error"]["data"]["details"] == {"identifier": "@xyz"}


def test_translate_preserves_request_id() -> None:
    exc = EmbeddingError("extension unavailable", ErrorCode.EMBEDDING_EXTENSION_UNAVAILABLE)
    line = errors.translate(request_id="req-3", exception=exc)
    body = json.loads(line)
    assert body["id"] == "req-3"


def test_translate_handles_empty_details() -> None:
    exc = LocalLibraryError("generic", ErrorCode.STORAGE_DATABASE_ERROR)
    line = errors.translate(request_id=1, exception=exc)
    body = json.loads(line)
    assert body["error"]["data"]["details"] == {}


def test_translate_json_rpc_error_uses_its_own_code() -> None:
    """Pass-through: JsonRpcError translates to its own code, not -32000."""
    exc = protocol.MethodNotFound("method 'nope' not registered")
    line = errors.translate(request_id=2, exception=exc)
    body = json.loads(line)
    assert body["error"]["code"] == protocol.METHOD_NOT_FOUND  # -32601
    assert body["error"]["message"] == "method 'nope' not registered"
    assert "data" not in body["error"]


def test_translate_unknown_exception_maps_to_internal_error() -> None:
    """Unexpected exceptions (programming errors) produce -32603 with a redacted message."""
    exc = ValueError("divide by cucumber")
    line = errors.translate(request_id=1, exception=exc)
    body = json.loads(line)
    assert body["error"]["code"] == protocol.INTERNAL_ERROR  # -32603
    # The raw exception message must NOT leak to clients as-is — the envelope
    # uses a generic message. The translator also logs the real exception
    # server-side (verified via log capture in Task 4's integration test).
    assert "cucumber" not in body["error"]["message"].lower()
