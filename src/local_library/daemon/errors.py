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
