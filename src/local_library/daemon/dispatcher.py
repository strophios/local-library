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
import time
from collections.abc import Awaitable, Callable
from typing import Any

from local_library.core.errors import LocalLibraryError
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

        start = time.perf_counter()

        handler = self._methods.get(request.method)
        if handler is None:
            duration_ms = (time.perf_counter() - start) * 1000
            _LOGGER.info(
                "method=%s id=%s status=method_not_found duration_ms=%.1f",
                request.method, request.id, duration_ms,
            )
            return protocol.build_error_response(
                request_id=request.id,
                code=protocol.METHOD_NOT_FOUND,
                message=f"Method not found: {request.method}",
            )

        try:
            result = await handler(**request.params)
        except protocol.JsonRpcError as exc:
            duration_ms = (time.perf_counter() - start) * 1000
            _LOGGER.info(
                "method=%s id=%s status=protocol_error code=%d duration_ms=%.1f",
                request.method, request.id, exc.code, duration_ms,
            )
            return errors.translate(request.id, exc)
        except TypeError as exc:
            duration_ms = (time.perf_counter() - start) * 1000
            _LOGGER.info(
                "method=%s id=%s status=invalid_params duration_ms=%.1f",
                request.method, request.id, duration_ms,
            )
            return errors.translate(
                request.id,
                protocol.InvalidParams(f"Invalid params: {exc}"),
            )
        except LocalLibraryError as exc:
            duration_ms = (time.perf_counter() - start) * 1000
            _LOGGER.warning(
                "method=%s id=%s status=domain_error error_code=%s duration_ms=%.1f",
                request.method, request.id, exc.code.value, duration_ms,
            )
            return errors.translate(request.id, exc)
        except Exception as exc:  # noqa: BLE001
            duration_ms = (time.perf_counter() - start) * 1000
            _LOGGER.exception(
                "method=%s id=%s status=internal_error duration_ms=%.1f",
                request.method, request.id, duration_ms,
            )
            return errors.translate(request.id, exc)

        duration_ms = (time.perf_counter() - start) * 1000
        _LOGGER.info(
            "method=%s id=%s status=ok duration_ms=%.1f",
            request.method, request.id, duration_ms,
        )
        return protocol.build_success_response(request.id, result)
