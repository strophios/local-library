# Daemon Domain

Last verified: 2026-04-24

## Purpose

Long-running process that wraps the `Library` orchestrator as a Unix-domain-socket
service, keeping the embedding model and sqlite-vec connection warm so downstream
clients (Neovim plugin today; future MCP v2) see sub-500 ms warm search latency.

This seed is updated per phase; Phase 7 marks it complete.

## Contracts

- **Exposes:** Unix-domain-socket endpoint at `config.get_socket_path()`, serving
  line-delimited JSON-RPC 2.0 (protocol specified in Phase 2).
- **Guarantees (Phase 1 only):** A single-instance daemon process can be started,
  stopped, and queried for status via the `local-library daemon <subcommand>` CLI.
  The socket echoes bytes during Phase 1; JSON-RPC semantics arrive in Phase 2.
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

## Invariants

- PID file is exclusive-locked for the lifetime of the process; if the lock
  cannot be acquired at startup, a live peer is assumed and startup refuses.
- On clean shutdown (SIGTERM/SIGINT): server closed → socket file unlinked →
  PID file unlocked and removed → process exits 0.

## Key Files

- `server.py` — asyncio server + main() entry point + signal handling
- `pid_file.py` — atomic PID write + stale-detection + fcntl lock
- `socket_activation.py` — launchd FD-inheritance shim (env-var-based stub)
- (Phase 2+) `protocol.py`, `dispatcher.py`, `errors.py` — JSON-RPC layer

## Gotchas

- On Python <3.13, `asyncio.start_unix_server` does not unlink the socket file
  when the server closes; shutdown code must do it explicitly.
- Never use `os.umask` in daemon code (changes global process state); set
  socket file perms via `os.chmod(path, 0o600)` post-bind instead.
