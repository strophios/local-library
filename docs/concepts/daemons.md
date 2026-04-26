# Daemons, IPC, and RPC — a working reference

Last verified: 2026-04-24

This document is a standalone teaching reference for the concepts that shape
the local-library daemon. It is written in lockstep with the implementation
phases: each chapter is grounded in specific design decisions made in this
project, cross-referenced into `docs/design-plans/2026-04-24-neovim-citation-workflow.md`.

## Chapter 1 — What is a daemon?

A **daemon** is a long-running process that provides services to other
processes without being tied to a user's interactive session. The defining
properties:

1. **Lifetime decoupled from a TTY.** A daemon survives logout, terminal
   close, and SSH disconnect. Mechanically, this means the daemon runs in
   its own session (`setsid`) and has no controlling terminal.
2. **Stable endpoint.** A daemon publishes a well-known address — a socket
   path, TCP port, D-Bus name — that other processes know how to reach.
3. **Idle-tolerant.** A daemon spends most of its time blocked waiting for
   requests, not computing. Its value is amortized model-load cost, not
   throughput.
4. **Single-instance per endpoint.** Two daemons cannot own the same socket
   path simultaneously; some coordination (PID file, systemd socket, launchd
   LaunchAgent) ensures only one is live at a time.

In the local-library architecture, the daemon exists to avoid paying
cold-start costs repeatedly: the embedding model (~200 MB) and sqlite-vec
connection initialize once, then serve many small queries over the lifetime
of a Neovim session.

### Why a daemon for local-library specifically?

Two alternatives were considered and rejected:

- **CLI-per-query.** Shelling out to `local-library search` from the editor
  pays ~3–8 s cold-start on every invocation (embedder + reranker load).
  Unusable for a claim-driven search workflow that fires on every `<leader>c`.
- **Editor plugin with in-process Python.** Requires embedding a Python
  interpreter in Neovim (pynvim), which composes poorly with the editor's
  Lua event loop and would couple the retrieval engine to the Neovim
  lifecycle. Non-starter once we want a future MCP server v2 to share the
  same warm state.

The daemon is the architecturally smallest change that resolves both: warm
state, editor-agnostic. See design doc §"High-level shape" and §"Process model".

## Chapter 2 — Process supervision and service management

A daemon that can start is not a daemon that will stay running. **Service
management** covers the questions: who launches the daemon on boot or on
demand? Who restarts it after a crash? Who routes its logs?

### The three common answers

1. **User-managed (CLI-driven).** The user runs `my-daemon start` and
   `my-daemon stop`. The program is responsible for its own lifecycle:
   forking, PID file, signal handling. Simple; no OS coupling. Poor for
   always-on services because the user has to remember to start it.
2. **System supervisor.** systemd on Linux, launchd on macOS, SMF on
   illumos. The supervisor owns process lifecycle: starts on boot, restarts
   on crash, aggregates logs. The daemon ships a unit file / plist and lets
   the supervisor manage it. Requires learning the supervisor's conventions
   but eliminates a class of lifecycle bugs.
3. **Socket activation.** The supervisor pre-binds the listening socket
   itself and hands the daemon an inherited FD on start. This lets the
   daemon be started on-demand (first client connect) and shut down after
   idle, without losing requests in the handoff.

### local-library's choice: CLI-managed with launchd forward-compat

For MVP, local-library's daemon is user-managed: `local-library daemon start`,
`stop`, `status`. This matches the developer's workflow (start the daemon in
the morning, stop it when the machine shuts down) and avoids forcing launchd
configuration on users who don't want system-level service integration.

However, the daemon is structured so that a future move to launchd
socket-activation is a packaging change — not a code change. Specifically:

- `socket_activation.inherited_socket()` checks for a pre-bound FD (Phase 1
  via the `LAUNCH_ACTIVATE_SOCKET_FD` env var; future via ctypes wrapper
  around Apple's `launch_activate_socket`). If present, the server wraps it
  as the listening socket and skips the manual bind.
- `main()` is a plain function; no double-fork, no demonization. Under
  launchd, the process stays in the foreground and launchd takes care of
  TTY detachment.
- Logging goes to `config.get_daemon_log_dir()/daemon.log`. Under launchd,
  the plist's `StandardOutPath` / `StandardErrorPath` can redirect cleanly.

### The pieces that stay the daemon's problem

Even with socket activation, the daemon still owns:

- **Single-instance enforcement.** The PID file + `fcntl.flock` combo
  (see `daemon/pid_file.py`) ensures that only one daemon process writes
  to the sqlite-vec database at a time. sqlite-vec's single-threaded access
  requirement makes this non-optional; launchd's socket activation does
  not substitute for it, because a buggy start script could still launch
  two processes.
- **Signal-driven cleanup.** SIGTERM is the supervisor's "please shut down"
  request. The daemon must close the server, unlink the socket, release
  the PID lock, and exit 0 within the supervisor's grace period (launchd
  default: 20 s). See `daemon/server.py` `_install_signal_handlers`.

### Cross-references

- Design doc §"Process model" — the CLI-managed-with-launchd-compat decision
- Design doc §"Patterns this design deliberately does not follow" —
  rejection of double-fork / PEP 3143 daemonization
- `src/local_library/daemon/pid_file.py` — PID file + flock implementation
- `src/local_library/daemon/socket_activation.py` — FD-inheritance shim

*Chapters 3–8 are written in Phases 2–7.*
