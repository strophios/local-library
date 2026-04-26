"""Daemon asyncio server: echo loop (Phase 1), JSON-RPC dispatch arrives in Phase 2.

# pattern: Imperative Shell

Owns the event loop, the listening socket (from socket_activation), the PID
file lock (from pid_file), and SIGTERM/SIGINT handling.

Phase 1 protocol is a literal echo: the server reads bytes from each client
and writes them back unchanged. Phase 2 replaces `echo_handler` with the
JSON-RPC dispatch loop; the lifecycle scaffolding stays intact.
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
from local_library.daemon import pid_file, socket_activation

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


async def echo_handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    """Phase 1 handler: echo bytes until EOF, then close cleanly.

    Phase 2 replaces this with the JSON-RPC dispatch loop.
    """
    try:
        while True:
            chunk = await reader.read(4096)
            if not chunk:
                break
            writer.write(chunk)
            await writer.drain()
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:  # noqa: BLE001 — best-effort shutdown
            pass


async def _serve(listening: socket.socket, stop_event: asyncio.Event) -> None:
    server_obj = await asyncio.start_unix_server(echo_handler, sock=listening)
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
