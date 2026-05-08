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
