# Neovim Citation Workflow Implementation Plan — Phase 2: JSON-RPC Protocol Layer

**Goal:** Replace Phase 1's echo handler with a compliant JSON-RPC 2.0 server. Add the protocol parsing, envelope construction, exception translation, and async dispatch layers, then register a single `ping` method as the first real RPC. Lifecycle scaffolding (PID lock, socket activation, signal handling) is unchanged.

**Architecture:** Three new pure-Python modules — `protocol.py` (Functional Core: framing + parse + envelope construction), `errors.py` (Functional Core: `LocalLibraryError` → JSON-RPC envelope translation), `dispatcher.py` (Mixed: pure registry, async dispatch with exception routing) — plus a `protocol_handler` coroutine in `server.py` that replaces `echo_handler`. The dispatcher is built once per server start; each connection drives a per-line read → parse → dispatch → respond loop until EOF.

**Tech Stack:** Python stdlib `json`, `asyncio.StreamReader`/`StreamWriter`, `dataclasses`. No new third-party dependencies — neither `python-lsp-jsonrpc` (wrong framing) nor `jsonrpcserver` (no transport handling) earns its keep at this scope.

**Scope:** 2 of 7 phases from `docs/design-plans/2026-04-24-neovim-citation-workflow.md`.

**Codebase verified:** 2026-04-24.

**Executor skills:** `ed3d-house-style:coding-effectively` (FCIS classification matters here — `protocol.py` and `errors.py` are pure Functional Core; `dispatcher.py` is Mixed; the new server bits are Imperative Shell), `astral:uv`, `astral:ruff`, `ed3d-plan-and-execute:test-driven-development`, `ed3d-plan-and-execute:verification-before-completion`.

---

<!-- START_SUBCOMPONENT_A (tasks 1-3) -->

<!-- START_TASK_1 -->
## Task 1: Protocol layer — framing + request parse + response envelopes (TDD)

**Type:** Functionality. Pure-function module; no I/O.

**Files:**
- Create: `tests/unit/daemon/test_protocol.py`
- Create: `src/local_library/daemon/protocol.py`

### Step 1: Write failing tests

`tests/unit/daemon/test_protocol.py`:

```python
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
```

### Step 2: Run tests, confirm they fail

```bash
uv run pytest tests/unit/daemon/test_protocol.py -v
```

Expected: ImportError for `local_library.daemon.protocol` across all tests.

### Step 3: Implement `protocol.py`

`src/local_library/daemon/protocol.py`:

```python
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
        raise InvalidRequest(
            "'params' must be an object (by-name); by-position not supported"
        )

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


def build_success_response(
    request_id: int | str | None, result: Any
) -> str:
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
```

### Step 4: Run tests, confirm they pass

```bash
uv run pytest tests/unit/daemon/test_protocol.py -v
```

Expected: 18 tests pass.

### Step 5: Lint + format

```bash
uv run ruff check src/local_library/daemon/protocol.py tests/unit/daemon/test_protocol.py
uv run ruff format src/local_library/daemon/protocol.py tests/unit/daemon/test_protocol.py
```

### Step 6: Commit

```bash
git add src/local_library/daemon/protocol.py tests/unit/daemon/test_protocol.py
git commit -m "feat(daemon): JSON-RPC 2.0 protocol parse + envelope builders

Pure-function module for request parsing (with typed ParseError/InvalidRequest
exceptions) and success/error response envelope construction. Enforces spec
§4.1 (notification = absent id, not null id), §5 (jsonrpc field required on
every response), and explicitly rejects batch requests with -32600 per MVP
scope. Compact JSON serialization keeps the wire safely line-delimited."
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
## Task 2: Error translation — LocalLibraryError → JSON-RPC envelope (TDD)

**Type:** Functionality. Pure-function module.

**Files:**
- Create: `tests/unit/daemon/test_errors.py`
- Create: `src/local_library/daemon/errors.py`

### Step 1: Write failing tests

`tests/unit/daemon/test_errors.py`:

```python
"""Tests for LocalLibraryError → JSON-RPC error envelope translation."""

import json

from local_library.core.errors import (
    EmbeddingError,
    ErrorCode,
    LocalLibraryError,
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
    exc = EmbeddingError(
        "extension unavailable", ErrorCode.EMBEDDING_EXTENSION_UNAVAILABLE
    )
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
```

### Step 2: Run tests, confirm they fail

```bash
uv run pytest tests/unit/daemon/test_errors.py -v
```

Expected: ImportError for `local_library.daemon.errors`.

### Step 3: Implement `errors.py`

`src/local_library/daemon/errors.py`:

```python
"""Exception → JSON-RPC error envelope translation.

# pattern: Functional Core (pure transformation; caller handles logging I/O)

The daemon catches three exception categories inside its dispatch loop:

1. `JsonRpcError` subclasses — the protocol layer's own typed failures
   (ParseError, InvalidRequest, MethodNotFound, InvalidParams). Each carries
   its standard JSON-RPC error code and optional `data` payload.

2. `LocalLibraryError` subclasses — domain errors from the Library. These
   map to the generic server error code (-32000) with a structured `data`
   payload that carries the `ErrorCode` enum value as a string under
   `error_code`, plus the exception's `details` dict. Clients branch on
   `error_code` strings.

3. Any other `Exception` — unexpected programming errors. These map to
   `-32603 Internal error` with a generic message; the raw exception text
   is NOT leaked to the client (callers must log the full exception
   server-side before calling this translator).
"""

from __future__ import annotations

from local_library.core.errors import LocalLibraryError
from local_library.daemon import protocol


def translate(request_id: int | str | None, exception: BaseException) -> str:
    """Translate any exception into a newline-terminated JSON-RPC error line.

    Contract: callers MUST log the exception server-side before invoking this
    function. The returned envelope is safe to send to untrusted clients — it
    never leaks raw exception messages from unknown exception types.
    """
    if isinstance(exception, protocol.JsonRpcError):
        return protocol.build_error_response(
            request_id=request_id,
            code=exception.code,
            message=exception.message,
            data=exception.data,
        )

    if isinstance(exception, LocalLibraryError):
        return protocol.build_error_response(
            request_id=request_id,
            code=protocol.SERVER_ERROR,
            message=exception.message,
            data={
                "error_code": exception.code.value,
                "details": exception.details,
            },
        )

    # Unknown exception type — hide the real message, report as internal error.
    return protocol.build_error_response(
        request_id=request_id,
        code=protocol.INTERNAL_ERROR,
        message="Internal error",
    )
```

### Step 4: Run tests, confirm they pass

```bash
uv run pytest tests/unit/daemon/test_errors.py -v
```

Expected: 5 tests pass.

### Step 5: Lint + format

```bash
uv run ruff check src/local_library/daemon/errors.py tests/unit/daemon/test_errors.py
uv run ruff format src/local_library/daemon/errors.py tests/unit/daemon/test_errors.py
```

### Step 6: Commit

```bash
git add src/local_library/daemon/errors.py tests/unit/daemon/test_errors.py
git commit -m "feat(daemon): exception translation to JSON-RPC error envelopes

Three-way dispatch: JsonRpcError subclasses use their own codes, LocalLibraryError
maps to -32000 with data.error_code (clients branch on this), unknown exceptions
map to -32603 with a redacted generic message to avoid leaking raw exception text."
```
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
## Task 3: Dispatcher — method registry + async dispatch (TDD)

**Type:** Functionality. Mixed — async dispatch is Imperative-flavored, but the registry itself is pure.

**Files:**
- Create: `tests/unit/daemon/test_dispatcher.py`
- Create: `src/local_library/daemon/dispatcher.py`

### Step 1: Write failing tests

`tests/unit/daemon/test_dispatcher.py`:

```python
"""Tests for the async JSON-RPC dispatcher."""

import asyncio
import json

import pytest

from local_library.core.errors import ErrorCode, LookupError as LibLookupError
from local_library.daemon import dispatcher, protocol


def _run(coro):
    return asyncio.run(coro)


def test_dispatch_happy_path() -> None:
    d = dispatcher.Dispatcher()

    async def handler(params: dict) -> dict:
        return {"pong": True, "name": params.get("name", "")}

    d.register("ping", handler)
    req = protocol.ParsedRequest(method="ping", params={"name": "hi"}, id=1)
    line = _run(d.dispatch(req))
    body = json.loads(line)
    assert body["result"] == {"pong": True, "name": "hi"}
    assert body["id"] == 1


def test_dispatch_unknown_method_returns_method_not_found() -> None:
    d = dispatcher.Dispatcher()
    req = protocol.ParsedRequest(method="nope", params={}, id=1)
    line = _run(d.dispatch(req))
    body = json.loads(line)
    assert body["error"]["code"] == protocol.METHOD_NOT_FOUND


def test_dispatch_handler_type_error_maps_to_invalid_params() -> None:
    """If the handler raises TypeError (bad kwargs), report -32602."""
    d = dispatcher.Dispatcher()

    async def handler(*, required: str) -> dict:
        return {"got": required}

    d.register("m", handler)
    req = protocol.ParsedRequest(method="m", params={}, id=1)
    line = _run(d.dispatch(req))
    body = json.loads(line)
    assert body["error"]["code"] == protocol.INVALID_PARAMS


def test_dispatch_handler_raises_invalid_params_is_passed_through() -> None:
    d = dispatcher.Dispatcher()

    async def handler(**_) -> dict:
        raise protocol.InvalidParams("need a non-empty query")

    d.register("m", handler)
    req = protocol.ParsedRequest(method="m", params={}, id=1)
    line = _run(d.dispatch(req))
    body = json.loads(line)
    assert body["error"]["code"] == protocol.INVALID_PARAMS
    assert body["error"]["message"] == "need a non-empty query"


def test_dispatch_handler_raises_local_library_error_translates() -> None:
    d = dispatcher.Dispatcher()

    async def handler(**_) -> dict:
        raise LibLookupError(
            "doc not found", ErrorCode.NOT_FOUND, details={"identifier": "@xyz"}
        )

    d.register("m", handler)
    req = protocol.ParsedRequest(method="m", params={}, id=1)
    line = _run(d.dispatch(req))
    body = json.loads(line)
    assert body["error"]["code"] == protocol.SERVER_ERROR  # -32000
    assert body["error"]["data"]["error_code"] == "NOT_FOUND"


def test_dispatch_handler_raises_unknown_exception_maps_to_internal_error() -> None:
    d = dispatcher.Dispatcher()

    async def handler(**_) -> dict:
        raise RuntimeError("something unexpected")

    d.register("m", handler)
    req = protocol.ParsedRequest(method="m", params={}, id=1)
    line = _run(d.dispatch(req))
    body = json.loads(line)
    assert body["error"]["code"] == protocol.INTERNAL_ERROR
    assert "unexpected" not in body["error"]["message"].lower()


def test_dispatch_notification_returns_empty_string() -> None:
    """Notifications (no id) produce no response per spec §4.1."""
    d = dispatcher.Dispatcher()
    called = {"yes": False}

    async def handler(**_) -> dict:
        called["yes"] = True
        return {"unused": True}

    d.register("m", handler)
    req = protocol.ParsedRequest(method="m", params={}, id=None, is_notification=True)
    line = _run(d.dispatch(req))
    assert line == ""
    assert called["yes"] is True


def test_dispatch_notification_of_unknown_method_still_no_response() -> None:
    d = dispatcher.Dispatcher()
    req = protocol.ParsedRequest(
        method="unknown", params={}, id=None, is_notification=True
    )
    line = _run(d.dispatch(req))
    assert line == ""


def test_register_rejects_duplicate_methods() -> None:
    d = dispatcher.Dispatcher()

    async def h(**_) -> dict:
        return {}

    d.register("m", h)
    with pytest.raises(ValueError, match="already registered"):
        d.register("m", h)
```

### Step 2: Run tests, confirm they fail

```bash
uv run pytest tests/unit/daemon/test_dispatcher.py -v
```

Expected: ImportError.

### Step 3: Implement `dispatcher.py`

`src/local_library/daemon/dispatcher.py`:

```python
"""Async method registry and dispatch for the JSON-RPC server.

# pattern: Mixed — the registry is pure; dispatch is async and catches exceptions.

Single responsibility: given a `ParsedRequest`, call the registered handler
(if any), catch any exception, and return either a serialized response line
or "" for notifications.

The dispatcher does NOT do:
- Framing / transport (`server.py` reads and writes lines).
- Request parsing (`protocol.parse_request` does).
- Exception translation beyond the three categories documented in `errors.translate`.

Handler contract:
- `async def handler(**params) -> Any` — called with the parsed params dict
  as keyword arguments.
- Return value is JSON-serializable via `json.dumps`.
- Raise `protocol.InvalidParams` to report validation failures with a clear
  message; raise `LocalLibraryError` subclasses for domain errors; let any
  other exception propagate (dispatcher will catch and log).
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from local_library.daemon import errors, protocol

_LOGGER = logging.getLogger("local_library.daemon.dispatcher")

Handler = Callable[..., Awaitable[Any]]


class Dispatcher:
    """Mutable registry of method name → async handler."""

    def __init__(self) -> None:
        self._methods: dict[str, Handler] = {}

    def register(self, name: str, handler: Handler) -> None:
        if name in self._methods:
            raise ValueError(f"method '{name}' already registered")
        self._methods[name] = handler

    async def dispatch(self, request: protocol.ParsedRequest) -> str:
        """Dispatch a request and return the wire response line.

        Returns "" for notifications (no response per JSON-RPC 2.0 §4.1).
        """
        if request.is_notification:
            handler = self._methods.get(request.method)
            if handler is None:
                return ""
            try:
                await handler(**request.params)
            except Exception:  # noqa: BLE001 — notifications swallow all errors
                _LOGGER.exception(
                    "notification handler raised (method=%s)", request.method
                )
            return ""

        handler = self._methods.get(request.method)
        if handler is None:
            return protocol.build_error_response(
                request_id=request.id,
                code=protocol.METHOD_NOT_FOUND,
                message=f"Method not found: {request.method}",
            )

        try:
            result = await handler(**request.params)
        except protocol.JsonRpcError as exc:
            return errors.translate(request.id, exc)
        except TypeError as exc:
            # TypeError from **params kwargs mismatch = invalid params.
            return errors.translate(
                request.id,
                protocol.InvalidParams(f"Invalid params: {exc}"),
            )
        except Exception as exc:  # noqa: BLE001 — must not leak to client
            _LOGGER.exception(
                "handler raised unexpected exception (method=%s)", request.method
            )
            return errors.translate(request.id, exc)

        return protocol.build_success_response(request.id, result)
```

### Step 4: Run tests, confirm they pass

```bash
uv run pytest tests/unit/daemon/test_dispatcher.py -v
```

Expected: 9 tests pass.

### Step 5: Lint + format

```bash
uv run ruff check src/local_library/daemon/dispatcher.py tests/unit/daemon/test_dispatcher.py
uv run ruff format src/local_library/daemon/dispatcher.py tests/unit/daemon/test_dispatcher.py
```

### Step 6: Commit

```bash
git add src/local_library/daemon/dispatcher.py tests/unit/daemon/test_dispatcher.py
git commit -m "feat(daemon): async dispatcher with method registry and error routing

Dispatch takes a ParsedRequest, routes to a registered async handler, and
returns a serialized response line. Notifications swallow handler errors
and never respond. TypeError on kwargs mismatch maps to -32602; protocol
errors pass through; LocalLibraryError translates to -32000 with data.error_code;
unknown exceptions are logged server-side and returned as -32603 with no
message leakage."
```
<!-- END_TASK_3 -->

<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 4-5) -->

<!-- START_TASK_4 -->
## Task 4: Wire protocol into server + register `ping` method

**Type:** Functionality. Replaces Phase 1's `echo_handler` with a protocol-aware handler; adds the first real method.

**Files:**
- Modify: `src/local_library/daemon/server.py` (replace `echo_handler`, add `protocol_handler`, `build_dispatcher`, register `ping`)
- Create: `tests/unit/daemon/test_server_protocol.py`
- Modify: `tests/unit/daemon/test_server.py` (delete the now-stale `test_echo_handler_roundtrip_via_socketpair`)
- Modify: `tests/unit/daemon/test_lifecycle.py` (rename echo test, send/receive JSON-RPC ping)

### Step 1: Update Phase 1 tests to reflect the new handler contract

Edit `tests/unit/daemon/test_server.py` — delete `test_echo_handler_roundtrip_via_socketpair` (the echo handler is replaced). Leave the other four tests intact.

### Step 2: Write failing tests for the new protocol handler

`tests/unit/daemon/test_server_protocol.py`:

```python
"""Tests for the server's protocol handler (line-delimited JSON-RPC loop)."""

import asyncio
import json
import socket

from local_library.daemon import dispatcher, server


def test_protocol_handler_ping_roundtrip() -> None:
    """End-to-end: client writes a ping request, handler responds on the same socket."""
    parent, child = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        d = server.build_dispatcher()

        async def run() -> str:
            reader, writer = await asyncio.open_unix_connection(sock=parent)
            child_reader, child_writer = await asyncio.open_connection(sock=child)
            handler_task = asyncio.create_task(
                server.protocol_handler(child_reader, child_writer, d)
            )
            writer.write(b'{"jsonrpc":"2.0","id":1,"method":"ping"}\n')
            await writer.drain()
            line = await reader.readline()
            writer.close()
            await writer.wait_closed()
            await asyncio.wait_for(handler_task, timeout=1.0)
            return line.decode("utf-8")

        response_line = asyncio.run(run())
        body = json.loads(response_line)
        assert body["jsonrpc"] == "2.0"
        assert body["id"] == 1
        assert body["result"]["ok"] is True
        assert isinstance(body["result"]["daemon_pid"], int)
        assert isinstance(body["result"]["resident_bytes"], int)
        assert body["result"]["resident_bytes"] > 0
        assert isinstance(body["result"]["uptime_seconds"], (int, float))
        assert isinstance(body["result"]["library_version"], str)
    finally:
        parent.close()
        child.close()


def test_protocol_handler_malformed_input_returns_parse_error() -> None:
    parent, child = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        d = server.build_dispatcher()

        async def run() -> str:
            reader, writer = await asyncio.open_unix_connection(sock=parent)
            child_reader, child_writer = await asyncio.open_connection(sock=child)
            handler_task = asyncio.create_task(
                server.protocol_handler(child_reader, child_writer, d)
            )
            writer.write(b"not json at all\n")
            await writer.drain()
            line = await reader.readline()
            writer.close()
            await writer.wait_closed()
            await asyncio.wait_for(handler_task, timeout=1.0)
            return line.decode("utf-8")

        body = json.loads(asyncio.run(run()))
        assert body["error"]["code"] == -32700
        assert body["id"] is None
    finally:
        parent.close()
        child.close()


def test_protocol_handler_unknown_method_returns_method_not_found() -> None:
    parent, child = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        d = server.build_dispatcher()

        async def run() -> str:
            reader, writer = await asyncio.open_unix_connection(sock=parent)
            child_reader, child_writer = await asyncio.open_connection(sock=child)
            handler_task = asyncio.create_task(
                server.protocol_handler(child_reader, child_writer, d)
            )
            writer.write(b'{"jsonrpc":"2.0","id":2,"method":"does_not_exist"}\n')
            await writer.drain()
            line = await reader.readline()
            writer.close()
            await writer.wait_closed()
            await asyncio.wait_for(handler_task, timeout=1.0)
            return line.decode("utf-8")

        body = json.loads(asyncio.run(run()))
        assert body["error"]["code"] == -32601
        assert body["id"] == 2
    finally:
        parent.close()
        child.close()


def test_protocol_handler_multiple_requests_in_sequence() -> None:
    """Verify the handler processes back-to-back requests on the same connection."""
    parent, child = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        d = server.build_dispatcher()

        async def run() -> list[str]:
            reader, writer = await asyncio.open_unix_connection(sock=parent)
            child_reader, child_writer = await asyncio.open_connection(sock=child)
            handler_task = asyncio.create_task(
                server.protocol_handler(child_reader, child_writer, d)
            )
            writer.write(b'{"jsonrpc":"2.0","id":1,"method":"ping"}\n')
            writer.write(b'{"jsonrpc":"2.0","id":2,"method":"ping"}\n')
            await writer.drain()
            lines = [
                (await reader.readline()).decode("utf-8"),
                (await reader.readline()).decode("utf-8"),
            ]
            writer.close()
            await writer.wait_closed()
            await asyncio.wait_for(handler_task, timeout=1.0)
            return lines

        lines = asyncio.run(run())
        ids = [json.loads(line)["id"] for line in lines]
        assert ids == [1, 2]
    finally:
        parent.close()
        child.close()


def test_protocol_handler_notification_produces_no_response() -> None:
    parent, child = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        d = dispatcher.Dispatcher()
        called = {"yes": False}

        async def handler(**_) -> dict:
            called["yes"] = True
            return {"unused": True}

        d.register("notify", handler)

        async def run() -> bytes:
            reader, writer = await asyncio.open_unix_connection(sock=parent)
            child_reader, child_writer = await asyncio.open_connection(sock=child)
            handler_task = asyncio.create_task(
                server.protocol_handler(child_reader, child_writer, d)
            )
            writer.write(b'{"jsonrpc":"2.0","method":"notify"}\n')
            await writer.drain()
            writer.close()
            await writer.wait_closed()
            await asyncio.wait_for(handler_task, timeout=1.0)
            data = await reader.read()
            return data

        data = asyncio.run(run())
        assert data == b""
        assert called["yes"] is True
    finally:
        parent.close()
        child.close()


def test_ping_result_contains_expected_fields() -> None:
    """Unit-test the ping handler directly (no socket in the loop)."""
    result = asyncio.run(server._ping_handler())
    assert result["ok"] is True
    assert isinstance(result["daemon_pid"], int)
    assert result["daemon_pid"] > 0
    assert isinstance(result["resident_bytes"], int)
    assert result["resident_bytes"] > 0
    assert isinstance(result["uptime_seconds"], (int, float))
    assert isinstance(result["library_version"], str)
```

### Step 3: Run failing tests

```bash
uv run pytest tests/unit/daemon/test_server_protocol.py -v
```

Expected: AttributeError / ImportError because `server.protocol_handler`, `server.build_dispatcher`, and `server._ping_handler` don't exist yet.

### Step 4: Replace `echo_handler` with `protocol_handler` in `server.py`

Edit `src/local_library/daemon/server.py`:

- Remove the `echo_handler` function entirely.
- Add the imports near the top of the module (after the existing imports):

  ```python
  from local_library.daemon import dispatcher as dispatcher_mod
  from local_library.daemon import protocol
  from local_library.daemon.errors import translate as translate_error
  ```

- Add the new module-level functions below `acquire_listening_socket` and above `_serve`:

  ```python
  async def _ping_handler(**_: object) -> dict[str, object]:
      """The canonical health / observability probe."""
      return {
          "ok": True,
          "daemon_pid": os.getpid(),
          "resident_bytes": resident_bytes(),
          "uptime_seconds": uptime_seconds(),
          "library_version": library_version(),
      }


  def build_dispatcher() -> dispatcher_mod.Dispatcher:
      """Return a Dispatcher with all Phase 2 methods registered.

      Phase 3 will add `search` and `get_document` here.
      """
      d = dispatcher_mod.Dispatcher()
      d.register("ping", _ping_handler)
      return d


  async def protocol_handler(
      reader: asyncio.StreamReader,
      writer: asyncio.StreamWriter,
      dispatch: dispatcher_mod.Dispatcher,
  ) -> None:
      """Per-connection loop: read one line → parse → dispatch → write response.

      Continues until the client half-closes (EOF) or an unrecoverable transport
      error occurs. Malformed messages produce an error envelope and the loop
      continues — a single bad message does not terminate the connection.
      """
      try:
          while True:
              raw = await reader.readline()
              if not raw:
                  break  # clean EOF
              try:
                  line = raw.decode("utf-8").rstrip("\n")
              except UnicodeDecodeError as exc:
                  err = protocol.build_error_response(
                      request_id=None,
                      code=protocol.PARSE_ERROR,
                      message=f"Parse error: invalid UTF-8: {exc.reason}",
                  )
                  writer.write(err.encode("utf-8"))
                  await writer.drain()
                  continue

              if not line.strip():
                  continue  # blank keep-alive line; ignore

              try:
                  request = protocol.parse_request(line)
              except protocol.JsonRpcError as exc:
                  err = translate_error(request_id=None, exception=exc)
                  writer.write(err.encode("utf-8"))
                  await writer.drain()
                  continue

              response_line = await dispatch.dispatch(request)
              if response_line:
                  writer.write(response_line.encode("utf-8"))
                  await writer.drain()
      finally:
          try:
              writer.close()
              await writer.wait_closed()
          except Exception:  # noqa: BLE001 — best-effort shutdown
              pass
  ```

- Update `_serve` to build the dispatcher once and pass it to each connection handler:

  ```python
  async def _serve(listening: socket.socket, stop_event: asyncio.Event) -> None:
      dispatch = build_dispatcher()

      async def on_connect(
          reader: asyncio.StreamReader, writer: asyncio.StreamWriter
      ) -> None:
          await protocol_handler(reader, writer, dispatch)

      server_obj = await asyncio.start_unix_server(on_connect, sock=listening)
      async with server_obj:
          await stop_event.wait()
          server_obj.close()
          await server_obj.wait_closed()
  ```

### Step 5: Run tests, confirm they pass

```bash
uv run pytest tests/unit/daemon/test_server_protocol.py tests/unit/daemon/test_server.py -v
```

Expected: 4 tests in `test_server.py` + 6 tests in `test_server_protocol.py` = 10 tests pass.

### Step 6: Update `test_lifecycle.py` to exercise JSON-RPC

Modify the first test in `tests/unit/daemon/test_lifecycle.py`. Rename `test_daemon_starts_echoes_and_shuts_down` → `test_daemon_responds_to_ping_and_shuts_down`. Replace the echo block (`client.sendall(b"ping\n") ... assert data == b"ping\n"`) with:

```python
        import json as _json

        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.connect(str(socket_path))
            client.sendall(b'{"jsonrpc":"2.0","id":1,"method":"ping"}\n')
            data = b""
            while not data.endswith(b"\n"):
                chunk = client.recv(4096)
                if not chunk:
                    break
                data += chunk
            response = _json.loads(data)
            assert response["jsonrpc"] == "2.0"
            assert response["id"] == 1
            assert response["result"]["ok"] is True
            assert response["result"]["daemon_pid"] == proc.pid
            assert response["result"]["library_version"]
```

### Step 7: Run the updated lifecycle test

```bash
uv run pytest tests/unit/daemon/test_lifecycle.py -v
```

Expected: 2 tests pass (same two as Phase 1, with a real RPC assertion in place of the echo).

### Step 8: Run the full daemon test suite

```bash
uv run pytest tests/unit/daemon/ -v
```

Expected: roughly 62 tests pass (Phase 1 counts adjusted for the deleted echo test, plus all Phase 2 additions).

### Step 9: Lint + format

```bash
uv run ruff check src/local_library/daemon/ tests/unit/daemon/
uv run ruff format src/local_library/daemon/ tests/unit/daemon/
```

### Step 10: Commit

```bash
git add src/local_library/daemon/server.py tests/unit/daemon/test_server.py tests/unit/daemon/test_server_protocol.py tests/unit/daemon/test_lifecycle.py
git commit -m "feat(daemon): replace echo handler with JSON-RPC protocol loop + ping

server.protocol_handler reads line-delimited requests, parses them, dispatches
through the registered method table, and writes newline-terminated response
envelopes. A single bad message no longer terminates the connection; malformed
input produces a -32700 envelope and the loop continues. The ping method
is the first registered method and reports {ok, daemon_pid, resident_bytes,
uptime_seconds, library_version}. Updates the lifecycle integration test to
exercise the real RPC path."
```
<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
## Task 5: Concepts doc chapters 3–4 (IPC framing + RPC envelopes)

**Type:** Documentation.

**Files:**
- Modify: `docs/concepts/daemons.md` (append chapters 3 and 4; update the closing line)

### Step 1: Append chapters 3–4 to the concepts doc

Open `docs/concepts/daemons.md`. Remove the closing line `*Chapters 3–8 are written in Phases 2–7.*` and append after chapter 2:

```markdown

## Chapter 3 — IPC: byte streams and framing

A **byte stream** is a bidirectional pipe that carries bytes in order with no
native notion of "messages." TCP is a byte stream; Unix domain sockets in
`SOCK_STREAM` mode are byte streams. If the application wants to exchange
messages over a byte stream, it needs a **framing protocol** — a convention
that tells the receiver where one message ends and the next begins.

### Three common framing strategies

1. **Fixed-length records.** Every message is exactly N bytes. Trivially
   unambiguous, but inflexible and wasteful unless all messages are the
   same size (think hardware packet formats). Never appropriate for
   variable-length JSON.

2. **Length-prefix framing.** Each message is preceded by a header saying
   how many bytes follow. LSP uses `Content-Length: 1234\r\n\r\n` before
   each JSON payload. This is robust — message contents can contain any
   bytes, including the delimiter pattern — but requires the reader to
   parse the header, allocate a buffer, and read exactly the right number
   of bytes.

3. **Delimiter framing.** Each message is terminated by a reserved byte
   sequence. NDJSON and syslog use a single newline (0x0A) as the delimiter.
   Simple to implement — `readline()` is a standard primitive on every
   stream abstraction — but requires a guarantee that the delimiter byte
   cannot appear inside message contents.

### Why local-library's daemon uses delimiter framing (0x0A)

For our JSON-RPC traffic, delimiter framing on 0x0A is provably safe because
of two facts:

1. Python's `json.dumps` **always** escapes control characters (U+0000–U+001F,
   which includes 0x0A newline) in string values, regardless of the
   `ensure_ascii` flag. A string containing `"line1\nline2"` serializes to
   the 14-byte sequence `"line1\nline2"` where `\n` is the two-character
   escape sequence 0x5C 0x6E, **not** the raw 0x0A byte.

2. UTF-8 continuation bytes are in the range 0x80–0xBF, so no multi-byte
   code point can accidentally contain an 0x0A byte. ASCII control
   characters in UTF-8 occupy exactly one byte and are subject to the
   escape rule in #1.

Therefore: splitting the incoming byte stream on the 0x0A byte always yields
exactly one complete JSON object per resulting chunk. No length-prefix
bookkeeping, no delimiter-in-payload bug class.

### The `\n` in-string vs wire-on-wire distinction

There are two completely different "newlines" at play; confusing them is how
framing bugs get written:

- **In-string `\n`.** When a serialized JSON string contains a literal
  "newline," what's actually on the wire is the two-character sequence
  0x5C 0x6E (backslash + n). The JSON parser on the other end decodes this
  to a single 0x0A code point in the reconstructed Python string. No raw
  0x0A crosses the socket.
- **Wire-on-wire 0x0A.** A single raw 0x0A byte, emitted outside any string
  literal, is our framing terminator. Exactly one of these separates every
  pair of adjacent messages, and exactly one terminates the last message
  before EOF.

The test `test_wire_output_contains_no_embedded_newlines` in
`tests/unit/daemon/test_protocol.py` verifies the invariant: a result
containing `"line1\nline2\nline3"` produces a wire message with exactly
one 0x0A byte — the terminator.

### Cross-references

- Design doc §"Framing" (in the JSON-RPC Contract section)
- `src/local_library/daemon/protocol.py` `_serialize` — the place where
  the compact+no-indent+newline-terminator invariant lives
- `src/local_library/daemon/server.py` `protocol_handler` — the reader side
  that uses `StreamReader.readline()` to consume one framed message at a
  time

## Chapter 4 — RPC: encoding, framing, envelopes

**RPC (Remote Procedure Call)** is a pattern where a client invokes a
procedure by name on a server, receives a result or an error, and treats
the round-trip as if it were a local function call. An RPC protocol must
specify:

1. **Serialization format** for the procedure name, arguments, result, and
   error — typically JSON, MessagePack, Protocol Buffers, CBOR.
2. **Framing** (Chapter 3) so request/response pairs can be demultiplexed
   over a byte stream.
3. **Envelope shape** — the structured wrapper that says "this is a
   request," "this is a response," "this is an error."
4. **Correlation** — how a response is matched to its request in an
   asynchronous or batched session. Typically an `id` field.
5. **Error semantics** — what it means for a call to fail, how errors are
   reported, what error codes are standardized vs. application-defined.

### Why JSON-RPC 2.0

We chose JSON-RPC 2.0 over msgpack-rpc and a custom protocol because:

- **Debuggability.** A human can `nc -U` into the socket and type valid
  requests. `tcpdump` / `dtrace` output is legible. msgpack's binary
  framing requires tooling to decode.
- **Python ecosystem maturity.** JSON handling is stdlib; msgpack requires
  a third-party dep with a patchy asyncio story.
- **Payload sizes are small.** Our typical result is <10 KB of chunk text —
  the theoretical bytes-on-wire advantage of a binary format is negligible
  for this use case.
- **Spec stability.** JSON-RPC 2.0 has been stable since 2010; the spec is
  short (about three pages) and implementations converge on the same
  behavior.

### Envelope shape (what's actually on the wire)

A JSON-RPC request:
```
{"jsonrpc":"2.0","id":1,"method":"ping","params":{}}
```

A success response:
```
{"jsonrpc":"2.0","id":1,"result":{"ok":true,"daemon_pid":12345, ...}}
```

An error response:
```
{"jsonrpc":"2.0","id":1,"error":{"code":-32000,"message":"document not found","data":{"error_code":"NOT_FOUND","details":{"identifier":"@xyz"}}}}
```

The `id` field correlates response to request. `method` names the procedure.
`params` is a dictionary (we only accept by-name params, not by-position
arrays — simpler contract, no argument-order bugs). `result` carries the
return value on success; `error` carries a structured failure with a
standard numeric code and an optional free-form `data` payload.

### The error code space and our `data.error_code` convention

JSON-RPC 2.0 reserves five transport-layer error codes:

| Code | Meaning |
|------|---------|
| -32700 | Parse error (malformed JSON) |
| -32600 | Invalid Request (structural spec violation) |
| -32601 | Method not found |
| -32602 | Invalid params |
| -32603 | Internal error |

And it reserves the range -32000 to -32099 for "server-defined" application
errors. We use **exactly one server-defined code** — `-32000` — for all
domain errors. Clients branch on the string carried inside `error.data.error_code`,
which is drawn from our `ErrorCode` enum (`src/local_library/core/errors.py`):

```json
{
  "code": -32000,
  "message": "extension unavailable",
  "data": {
    "error_code": "EMBEDDING_EXTENSION_UNAVAILABLE",
    "details": { ... }
  }
}
```

This separates the **transport** error space (small, fixed, spec-defined)
from the **domain** error space (large, app-specific, string-valued). Adding
a new domain error never requires allocating a new numeric code or updating
the spec document; it's a plain enum extension plus a dispatcher-side `raise`.

### Spec compliance gotchas we got right

Five places where partial implementations commonly diverge:

1. **Notifications.** A request with no `id` key at all (not `"id": null`)
   is a notification and **must not** receive a response. Our `ParsedRequest`
   tracks `is_notification` separately from `id is None` because `"id": null`
   is a different case (a regular request with an unknown correlator).

2. **Parse-error `id`.** When the request cannot be parsed, we still
   respond — with `id: null`. The `id` field is always present in every
   response envelope.

3. **`jsonrpc: "2.0"` is always on the wire.** On success, on error, on
   parse-error. `_serialize` bakes it into every envelope.

4. **Method-not-found (-32601) beats invalid-params (-32602).** The
   dispatcher checks the registry first; only if the method exists does it
   try to invoke the handler. A request to an unregistered method with
   wrong params returns -32601, not -32602.

5. **Batch requests.** The spec uses "SHOULD" rather than "MUST" for batch
   support. We explicitly reject batches with -32600, documented in the
   protocol module's docstring. Internal clients control both ends; they
   never need batching.

### Cross-references

- Design doc §"JSON-RPC contract"
- `src/local_library/daemon/protocol.py` — envelope construction + parser
- `src/local_library/daemon/errors.py` — `LocalLibraryError` → -32000 with
  `data.error_code` mapping
- `src/local_library/daemon/dispatcher.py` — registry + async dispatch
- `tests/unit/daemon/test_protocol.py` — the spec-compliance test set;
  exists specifically to keep us honest about the gotchas above

*Chapters 5–8 are written in Phases 3, 6, and 7.*
```

### Step 2: Verify chapter count

```bash
grep -c '^## Chapter' docs/concepts/daemons.md
```

Expected: `4`.

### Step 3: Run the full daemon test suite as a closeout

```bash
uv run pytest tests/unit/daemon/ -v
```

Expected: ~62 tests pass.

### Step 4: Verify all Phase 2 "Done when" criteria from design doc

- ✓ Python test client sends valid ping → receives full response — `test_protocol_handler_ping_roundtrip` + `test_daemon_responds_to_ping_and_shuts_down`
- ✓ Malformed input → -32700 — `test_protocol_handler_malformed_input_returns_parse_error`
- ✓ Unknown method → -32601 — `test_protocol_handler_unknown_method_returns_method_not_found` + `test_dispatch_unknown_method_returns_method_not_found`
- ✓ Missing required param → -32602 — `test_dispatch_handler_type_error_maps_to_invalid_params`
- ✓ LocalLibraryError → -32000 with data.error_code — `test_local_library_error_maps_to_server_error_code` + `test_dispatch_handler_raises_local_library_error_translates`

### Step 5: Commit

```bash
git add docs/concepts/daemons.md
git commit -m "docs(concepts): add chapters 3-4 of the daemons concepts doc

Chapter 3: byte streams, framing strategies, why we chose 0x0A delimiter
framing for JSON-RPC, and the wire-vs-escape newline distinction.
Chapter 4: JSON-RPC envelope shape, the -32000 + data.error_code split
between transport and domain error spaces, and the five spec-compliance
gotchas the test suite enforces."
```
<!-- END_TASK_5 -->

<!-- END_SUBCOMPONENT_B -->
