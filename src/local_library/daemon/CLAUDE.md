# Daemon Domain

Last verified: 2026-05-06

## Purpose

Long-running process that wraps the `Library` orchestrator as a Unix-domain-socket
service, keeping the embedding model and sqlite-vec connection warm so downstream
clients (Neovim plugin today; future MCP v2) see sub-500 ms warm search latency.

This seed is updated per phase; Phase 7 marks it complete.

## Contracts

- **Exposes:** Unix-domain-socket endpoint at `config.get_socket_path()`, serving
  line-delimited JSON-RPC 2.0 (protocol specified in Phase 2).
- **Guarantees:** Single-instance daemon with PID file lock + asyncio
  Unix-socket server speaking line-delimited JSON-RPC 2.0. Methods:
  `ping`, `search`, `get_document`. Library wrapped on a single-worker
  ThreadPoolExecutor so sqlite-vec single-thread access is preserved
  while asyncio handles socket I/O concurrently. Structured per-request
  logs at INFO/WARNING/ERROR with method, id, status, duration_ms (and
  error_code on domain errors). Clean shutdown on SIGTERM/SIGINT:
  server closed → socket unlinked → Library closed → PID file removed
  → exit 0. CLI lifecycle via `local-library daemon {start|stop|
  status|restart|run}`. launchd socket-activation forward-compat shim
  in `socket_activation.inherited_socket()`.
- **Expects:** The existing `Library` orchestrator (wired in Phase 3).

## Dependencies

- **Uses:** `asyncio` (event loop), `psutil` (resident memory for status),
  `fcntl` (PID file locking), `platformdirs` via `config.py`.
- **Used by:** `cli/daemon.py` (process management commands), Phase 4+ Neovim plugin.
- **Boundary:** Read-only library access service. Does not touch bibliography
  files, project state, or editor context — those belong to the plugin.

## Key Decisions

- **Single event loop + single `Library` instance + single sqlite-vec connection.**
  Blocking model inference (Phase 3) will be wrapped in `run_in_executor`;
  sqlite-vec calls stay on the loop thread (see Phase 3 CLAUDE.md additions).
- **CLI-managed process lifecycle for MVP.** launchd socket-activation is
  scaffolded (env-var-based FD inheritance hook in Phase 1) but not wired.
- **Python 3.10 compatibility.** Socket cleanup is manual (no `cleanup_socket=True`).
- **Eager model warmup at startup.** `_construct_library` calls `Library.warmup()`
  on the executor thread before the daemon logs "ready" or accepts traffic. This
  moves the embedder + cross-encoder cold-load cost (~5-30s) off the request path
  so the plugin's first search finds a warm system. Override via
  `LOCAL_LIBRARY_DAEMON_SKIP_WARMUP=1` for tests that exercise transport only.
- **Force-close clients on shutdown.** `_active_writers` tracks in-flight
  connections; SIGTERM/SIGINT closes each one before awaiting `Server.wait_closed()`.
  Without this, long-lived plugin clients keep `wait_closed()` parked and the
  daemon ignores SIGTERM until the client disconnects (or SIGKILL).

## Invariants

- PID file is exclusive-locked for the lifetime of the process; if the lock
  cannot be acquired at startup, a live peer is assumed and startup refuses.
- On clean shutdown (SIGTERM/SIGINT): server closed → active client connections
  force-closed → server `wait_closed()` completes → Library closed → socket file
  unlinked → PID file unlocked and removed → process exits 0.
- `Library.warmup()` is invoked synchronously during startup (skippable via the
  `LOCAL_LIBRARY_DAEMON_SKIP_WARMUP` env var). Note: while warmup runs, signal
  handlers fire on the loop thread but the loop is parked awaiting the executor
  task, so SIGTERM is honored only after warmup completes. Tests that need fast
  shutdown should set the skip env var.

## Key Files

- `server.py` — main(), asyncio server, signal handling, single-worker
  Library executor, build_dispatcher, `_construct_library` (with warmup),
  `_active_writers` set + force-close-on-shutdown
- `pid_file.py` — atomic PID write + stale detection + fcntl lock
- `socket_activation.py` — launchd FD-inheritance + manual-bind fallback
- `protocol.py` — JSON-RPC parse + envelope builders (Functional Core)
- `errors.py` — exception → JSON-RPC error envelope translator
- `dispatcher.py` — method registry + async dispatch + structured logging
- `methods.py` — search + get_document handlers + serialization

## Gotchas

- On Python <3.13, `asyncio.start_unix_server` does not unlink the socket file
  when the server closes; shutdown code must do it explicitly.
- Never use `os.umask` in daemon code (changes global process state); set
  socket file perms via `os.chmod(path, 0o600)` post-bind instead.
- `daemon start` immediately followed by `daemon stop` may hit the CLI's 10s stop timeout — SIGTERM is queued during warmup but only honored once the executor task returns. Acceptable: a warmup-window stop is rare in normal use, and the daemon does eventually exit cleanly. Set `LOCAL_LIBRARY_DAEMON_SKIP_WARMUP=1` if you need fast turnaround during development.
- All Library calls must go through `run_on_library_thread(executor, ...)`.
  Never invoke `_library.<anything>()` directly from the asyncio loop —
  it will violate sqlite3's `check_same_thread` and may crash sqlite-vec.
