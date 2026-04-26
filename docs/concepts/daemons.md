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
