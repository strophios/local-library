"""Daemon asyncio server: line-delimited JSON-RPC 2.0 over a Unix-domain socket.

# pattern: Imperative Shell

Owns the event loop, the listening socket (from socket_activation), the PID
file lock (from pid_file), and SIGTERM/SIGINT handling.

`protocol_handler` runs the per-connection read → parse → dispatch → write
loop, delegating to a `Dispatcher` built once per server start by
`build_dispatcher`. Methods are registered at startup time; `ping` is the
canonical health probe. Subsequent phases add further methods (e.g.,
`search`, `get_document`) by extending `build_dispatcher`.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import socket
import sys
import time
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import psutil

from local_library import config
from local_library.daemon import dispatcher as dispatcher_mod
from local_library.daemon import pid_file, protocol, socket_activation
from local_library.daemon.errors import translate as translate_error

_START_TIME = time.monotonic()
_LOGGER = logging.getLogger("local_library.daemon")


def library_version() -> str:
    """Return the installed local-library distribution version."""
    try:
        return version("local-library")
    except PackageNotFoundError:
        return "0.0.0+unknown"


def resident_bytes() -> int:
    """Return the current process's resident set size in bytes."""
    return int(psutil.Process().memory_info().rss)


def uptime_seconds() -> float:
    """Return seconds since the daemon main() entered its serving loop."""
    return time.monotonic() - _START_TIME


def acquire_listening_socket(fallback_path: Path) -> socket.socket:
    """Return a listening UDS socket: inherited from launchd if available,
    else bound manually at `fallback_path`.
    """
    inherited = socket_activation.inherited_socket()
    if inherited is not None:
        _LOGGER.info("acquired inherited socket from launchd FD")
        return inherited
    _LOGGER.info("binding new socket at %s", fallback_path)
    return socket_activation.bind_listen(fallback_path)


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


async def _serve(listening: socket.socket, stop_event: asyncio.Event) -> None:
    dispatch = build_dispatcher()

    async def on_connect(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await protocol_handler(reader, writer, dispatch)

    server_obj = await asyncio.start_unix_server(on_connect, sock=listening)
    async with server_obj:
        await stop_event.wait()
        server_obj.close()
        await server_obj.wait_closed()


def _install_signal_handlers(loop: asyncio.AbstractEventLoop, stop_event: asyncio.Event) -> None:
    def _stop(_sig: int) -> None:
        _LOGGER.info("received signal %s, initiating shutdown", _sig)
        stop_event.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _stop, sig)


def _configure_logging() -> None:
    log_dir = config.get_daemon_log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=[
            logging.FileHandler(log_dir / "daemon.log", mode="a"),
            logging.StreamHandler(sys.stderr),
        ],
    )


def main() -> int:
    """Foreground entry point for the daemon process.

    Invoked by the `local-library-daemon` script entry and by
    `local-library daemon run`. Returns process exit code.
    """
    global _START_TIME  # noqa: PLW0603 — uptime anchors at serve start
    _configure_logging()
    _LOGGER.info("daemon starting (pid=%s, version=%s)", os.getpid(), library_version())

    config.ensure_directories()

    try:
        lock = pid_file.acquire(config.get_daemon_pid_path())
    except pid_file.AlreadyRunningError as exc:
        _LOGGER.error("refusing to start: %s", exc)
        return 1

    listening = acquire_listening_socket(config.get_socket_path())
    _START_TIME = time.monotonic()

    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        stop_event = asyncio.Event()
        _install_signal_handlers(loop, stop_event)
        _LOGGER.info("daemon ready at %s", config.get_socket_path())
        loop.run_until_complete(_serve(listening, stop_event))
        _LOGGER.info("daemon shut down cleanly")
        return 0
    finally:
        try:
            listening.close()
        except OSError:
            pass
        try:
            config.get_socket_path().unlink()
        except FileNotFoundError:
            pass
        pid_file.release(lock)
        loop.close()


if __name__ == "__main__":
    sys.exit(main())
