"""JSON-RPC 2.0 protocol parsing and response-envelope construction.

# pattern: Functional Core (pure serialization, no I/O)

Responsible for exactly three things:

1. Parse a single wire message (UTF-8 text, one JSON object, newline-terminated
   as delivered by the caller — this module does not handle the newline split
   itself) into a `ParsedRequest` or raise a typed protocol error.
2. Build a success response envelope as a compact, newline-terminated line of
   JSON.
3. Build an error response envelope with optional `data` payload.

Explicitly out of scope:
- Transport/framing (the I/O layer splits the stream on 0x0A and hands us lines).
- Method dispatch (the dispatcher module's job).
- Exception translation from `LocalLibraryError` (the errors module's job).

Standard JSON-RPC 2.0 error codes are exported as module constants.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

# Standard JSON-RPC 2.0 error codes.
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603
# Our generic server-defined error for LocalLibraryError translation.
SERVER_ERROR = -32000


class JsonRpcError(Exception):
    """Base protocol exception, convertible to a JSON-RPC error envelope."""

    code: int = INTERNAL_ERROR
    default_message: str = "Internal error"

    def __init__(self, message: str | None = None, data: Any | None = None) -> None:
        super().__init__(message or self.default_message)
        self.message = message or self.default_message
        self.data = data


class ParseError(JsonRpcError):
    code = PARSE_ERROR
    default_message = "Parse error"


class InvalidRequest(JsonRpcError):
    code = INVALID_REQUEST
    default_message = "Invalid Request"


class MethodNotFound(JsonRpcError):
    code = METHOD_NOT_FOUND
    default_message = "Method not found"


class InvalidParams(JsonRpcError):
    code = INVALID_PARAMS
    default_message = "Invalid params"


class InternalError(JsonRpcError):
    code = INTERNAL_ERROR
    default_message = "Internal error"


@dataclass(frozen=True)
class ParsedRequest:
    """A successfully-parsed JSON-RPC 2.0 request.

    `id` is None for notifications AND for requests with explicit `"id": null`;
    `is_notification` disambiguates — True iff the request omitted the id key.
    """

    method: str
    params: dict[str, Any] = field(default_factory=dict)
    id: int | str | None = None
    is_notification: bool = False


def parse_request(raw: str) -> ParsedRequest:
    """Parse one JSON-RPC 2.0 request line.

    Raises ParseError (malformed JSON) or InvalidRequest (structural violations).
    """
    try:
        body = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ParseError(f"Parse error: {exc.msg}") from exc

    if isinstance(body, list):
        raise InvalidRequest("Batch requests are not supported")
    if not isinstance(body, dict):
        raise InvalidRequest("Request must be a JSON object")

    jsonrpc = body.get("jsonrpc")
    if jsonrpc != "2.0":
        raise InvalidRequest("Missing or invalid 'jsonrpc' version")

    method = body.get("method")
    if not isinstance(method, str) or not method:
        raise InvalidRequest("Missing or non-string 'method' field")

    params_raw = body.get("params", {})
    if params_raw is None:
        params: dict[str, Any] = {}
    elif isinstance(params_raw, dict):
        params = params_raw
    else:
        raise InvalidRequest("'params' must be an object (by-name); by-position not supported")

    id_present = "id" in body
    id_value = body.get("id") if id_present else None
    if id_present and id_value is not None and not isinstance(id_value, (int, str)):
        raise InvalidRequest("'id' must be a string, number, or null")

    return ParsedRequest(
        method=method,
        params=params,
        id=id_value,
        is_notification=not id_present,
    )


def build_success_response(request_id: int | str | None, result: Any) -> str:
    """Return a newline-terminated success envelope line."""
    body = {"jsonrpc": "2.0", "id": request_id, "result": result}
    return _serialize(body)


def build_error_response(
    request_id: int | str | None,
    code: int,
    message: str,
    data: Any | None = None,
) -> str:
    """Return a newline-terminated error envelope line.

    `data` is omitted from the envelope when None (per spec §5.1: data is optional).
    """
    err: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    body = {"jsonrpc": "2.0", "id": request_id, "error": err}
    return _serialize(body)


def _serialize(body: dict[str, Any]) -> str:
    """Compact-serialize `body` and terminate with a single newline.

    `separators=(',', ':')` removes whitespace; `ensure_ascii=False` preserves
    Unicode (but still escapes control characters including 0x0A, so the wire
    remains safely line-delimited).
    """
    return json.dumps(body, separators=(",", ":"), ensure_ascii=False) + "\n"
