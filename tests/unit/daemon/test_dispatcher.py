"""Tests for the async JSON-RPC dispatcher."""

import asyncio
import json

import pytest

from local_library.core.errors import ErrorCode
from local_library.core.errors import LookupError as LibLookupError
from local_library.daemon import dispatcher, protocol


def _run(coro):
    return asyncio.run(coro)


def test_dispatch_happy_path() -> None:
    d = dispatcher.Dispatcher()

    async def handler(**params: object) -> dict:
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
