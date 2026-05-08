"""Tests for JSON-RPC 2.0 protocol parsing and envelope construction."""

import json

import pytest

from local_library.daemon import protocol


def test_parse_valid_request() -> None:
    raw = '{"jsonrpc":"2.0","id":1,"method":"ping","params":{}}'
    req = protocol.parse_request(raw)
    assert req.id == 1
    assert req.method == "ping"
    assert req.params == {}
    assert req.is_notification is False


def test_parse_valid_request_without_params() -> None:
    raw = '{"jsonrpc":"2.0","id":"abc","method":"ping"}'
    req = protocol.parse_request(raw)
    assert req.id == "abc"
    assert req.method == "ping"
    assert req.params == {}  # absent params => empty dict


def test_parse_notification_has_no_id() -> None:
    raw = '{"jsonrpc":"2.0","method":"ping"}'
    req = protocol.parse_request(raw)
    assert req.id is None
    assert req.is_notification is True


def test_parse_notification_with_null_id_is_not_a_notification() -> None:
    """id:null is a request with unknown id, not a notification (spec §4.1)."""
    raw = '{"jsonrpc":"2.0","id":null,"method":"ping"}'
    req = protocol.parse_request(raw)
    assert req.id is None
    assert req.is_notification is False


def test_parse_malformed_json_raises_parse_error() -> None:
    with pytest.raises(protocol.ParseError) as exc_info:
        protocol.parse_request("not { valid json")
    assert exc_info.value.code == protocol.PARSE_ERROR


def test_parse_non_object_root_raises_invalid_request() -> None:
    with pytest.raises(protocol.InvalidRequest):
        protocol.parse_request("[1, 2, 3]")


def test_parse_batch_raises_invalid_request() -> None:
    """MVP explicitly rejects batch requests (spec permits via 'SHOULD')."""
    raw = '[{"jsonrpc":"2.0","id":1,"method":"ping"}]'
    with pytest.raises(protocol.InvalidRequest):
        protocol.parse_request(raw)


def test_parse_missing_jsonrpc_field_raises_invalid_request() -> None:
    with pytest.raises(protocol.InvalidRequest):
        protocol.parse_request('{"id":1,"method":"ping"}')


def test_parse_wrong_jsonrpc_version_raises_invalid_request() -> None:
    with pytest.raises(protocol.InvalidRequest):
        protocol.parse_request('{"jsonrpc":"1.0","id":1,"method":"ping"}')


def test_parse_missing_method_raises_invalid_request() -> None:
    with pytest.raises(protocol.InvalidRequest):
        protocol.parse_request('{"jsonrpc":"2.0","id":1}')


def test_parse_non_string_method_raises_invalid_request() -> None:
    with pytest.raises(protocol.InvalidRequest):
        protocol.parse_request('{"jsonrpc":"2.0","id":1,"method":42}')


def test_parse_non_object_params_raises_invalid_request() -> None:
    """We only support by-name params (dict), not by-position (list)."""
    with pytest.raises(protocol.InvalidRequest):
        protocol.parse_request('{"jsonrpc":"2.0","id":1,"method":"ping","params":[1,2]}')


def test_build_success_response_roundtrips() -> None:
    line = protocol.build_success_response(request_id=1, result={"ok": True})
    assert line.endswith("\n")
    body = json.loads(line)
    assert body == {"jsonrpc": "2.0", "id": 1, "result": {"ok": True}}


def test_build_success_response_preserves_string_id() -> None:
    line = protocol.build_success_response(request_id="req-7", result=42)
    body = json.loads(line)
    assert body["id"] == "req-7"


def test_build_error_response_with_null_id() -> None:
    """Parse errors use id=null per spec §5."""
    line = protocol.build_error_response(
        request_id=None, code=protocol.PARSE_ERROR, message="Parse error"
    )
    body = json.loads(line)
    assert body == {
        "jsonrpc": "2.0",
        "id": None,
        "error": {"code": -32700, "message": "Parse error"},
    }


def test_build_error_response_includes_data_when_provided() -> None:
    line = protocol.build_error_response(
        request_id=5,
        code=-32000,
        message="not found",
        data={"error_code": "NOT_FOUND", "details": {"identifier": "@xyz"}},
    )
    body = json.loads(line)
    assert body["error"]["data"] == {
        "error_code": "NOT_FOUND",
        "details": {"identifier": "@xyz"},
    }


def test_build_error_response_omits_data_when_absent() -> None:
    line = protocol.build_error_response(request_id=1, code=-32601, message="nope")
    body = json.loads(line)
    assert "data" not in body["error"]


def test_wire_output_contains_no_embedded_newlines() -> None:
    """Compact serialization is safe to split on 0x0A. Verify that even a
    result containing internal newlines produces a single-line wire message."""
    result = {"text": "line1\nline2\nline3"}
    line = protocol.build_success_response(request_id=1, result=result)
    # Exactly one newline — the terminator.
    assert line.count("\n") == 1
    assert line.endswith("\n")
    # Roundtrip.
    body = json.loads(line)
    assert body["result"]["text"] == "line1\nline2\nline3"
