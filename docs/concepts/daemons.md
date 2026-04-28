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


## Chapter 5 — asyncio and single-threaded concurrency

**asyncio** gives us cooperative concurrency on a single OS thread. Tasks
voluntarily yield (`await`) and the event loop schedules whichever ready
coroutine runs next. There is no preemption: a task that doesn't yield
blocks every other task and the event loop itself.

This works beautifully for I/O — sockets, files, subprocess pipes — because
the kernel readiness notifications are exactly the moments when "yield to
the loop" is correct. It does not work for CPU-bound work: a torch model
inference call that takes 200 ms is 200 ms during which no other task can
run, no socket can be accepted, no `ping` can be answered.

### `run_in_executor` — the asyncio escape hatch for blocking work

`asyncio.AbstractEventLoop.run_in_executor(executor, fn, *args)` submits
`fn(*args)` to a `concurrent.futures.Executor` (typically a thread pool)
and returns an awaitable that resolves when `fn` finishes. While `fn` runs
on its own thread, the event loop is free to handle other coroutines.

The asyncio side gets a coroutine; the executor side gets a normal
synchronous function. This is the bridge.

### The sqlite-vec single-thread constraint

`sqlite-vec` requires that all operations against a vector index happen
from a single thread. This is on top of the underlying `sqlite3` module's
own `check_same_thread=True` default, which forbids using a connection
from a thread other than the one that created it.

Naively combined with asyncio, this is a contradiction:
- Model inference (embedder, reranker) is CPU-bound and must run off the
  event loop thread to keep `ping` responsive.
- sqlite-vec calls must run on the same thread that owns the connection.
- Our `Retriever.retrieve()` interleaves model inference and sqlite-vec
  queries inside one synchronous call.

### local-library's resolution: a single-worker executor that owns the Library

We use a `ThreadPoolExecutor(max_workers=1)` that owns the Library entirely:

- The Library is **constructed** on the executor thread (via
  `run_on_library_thread(executor, lambda: Library(embed_on_add=False))`).
  This means the long-lived sqlite3 connection is created on the executor
  thread, and `check_same_thread=True` is satisfied because every
  subsequent query also runs on that thread.
- Every method handler (`search`, `get_document`) runs entirely inside
  `run_on_library_thread`. Validation, `get_retriever`, `retrieve`,
  serialization — all on the same single thread.
- The asyncio event loop never touches the Library directly. It owns the
  socket I/O, the protocol parsing, and the dispatch — none of which need
  the connection.
- `ping` does not go through the executor. It reads `psutil`, `os.getpid`,
  and a monotonic uptime — all event-loop-cheap. So `ping` stays sub-ms
  responsive even while a search is occupying the executor for ~300 ms.

The original design imagined a finer split: model calls in the executor,
sqlite-vec calls on the loop thread. That split was infeasible without
refactoring the Retriever to expose embed/query/rerank as separate steps.
The single-worker-executor model preserves the design's two important
properties — sqlite-vec single-thread access; loop-thread liveness during
slow work — without that refactor.

### What we lose, and why it's fine

A single-worker executor cannot run two searches in parallel. If two
clients fire searches simultaneously, the second waits for the first.

In practice this is the right behavior. sqlite-vec wouldn't have allowed
parallelism anyway; even a multi-worker executor would have to serialize
on the connection. And our actual concurrency need is:

- *Multiple slow operations interleaved with fast probes* — e.g., the
  Neovim plugin sending `ping` while a search is in flight. The
  single-worker model handles this perfectly, since `ping` doesn't enter
  the executor.
- *Multiple clients each making sequential calls* — e.g., the future
  MCP server v2 + the Neovim plugin both connected. The single-worker
  model handles this fine: their calls serialize on the executor, but
  each client's connection stays responsive between calls.

What we don't get is *one client overlapping two searches*. No realistic
client does that.

### Cross-references

- Design doc §"Concurrency model" — original two-thread split
- `src/local_library/daemon/server.py` — `_make_library_executor`,
  `run_on_library_thread`, the construct-on-executor pattern in `main()`
- `src/local_library/daemon/methods.py` — handlers that assume
  single-threaded Library access
- `tests/integration/daemon/test_search_lifecycle.py::test_ping_remains_responsive_during_search`
  — the assertion that ping stays fast during a slow search

## Chapter 6 — Error handling across process boundaries

When a function fails locally, you get a Python traceback in the same
process. When a function fails over RPC, the client gets bytes — and those
bytes have to encode enough for the client to do something useful.

A good cross-process error envelope answers four questions:

1. **What went wrong?** A short, human-readable message.
2. **What category?** A machine-readable code so the client can branch.
3. **What to do?** Optional structured details — suggestions, identifiers,
   anything that lets the client recover or retry.
4. **Was it the client's fault or the server's?** Often implicit in the
   code, but matters for retry semantics.

### local-library's two-tier error model

JSON-RPC 2.0 gives us a small set of *transport-layer* error codes:
parse error, invalid request, method not found, invalid params, internal
error. These answer "did your message reach me, and could I act on it?"
They are not enough to convey domain semantics: "I understood your
request, but the document doesn't exist."

We layer a *domain* error namespace on top, using the spec's `data` field:

```json
{
  "error": {
    "code": -32000,
    "message": "document not found",
    "data": {
      "error_code": "NOT_FOUND",
      "details": { "identifier": "@xyz", "suggestions": ["Smith2023"] }
    }
  }
}
```

The numeric code is `-32000` — JSON-RPC's reserved "server-defined" range.
The string in `data.error_code` is from our `ErrorCode` enum. The client
branches on the *string*, not the number; the number is fixed (-32000)
for every domain error.

### Why a string, not a number, for the domain code

We could have allocated -32001, -32002, -32003 for individual domain
errors. We chose a single -32000 plus a string for three reasons:

1. **Adding new errors doesn't require coordinating two registries.** New
   error → add to `ErrorCode` enum → done. No "is -32027 used? what was
   it last assigned to?" bookkeeping.
2. **Strings are self-documenting.** A client logging `error_code: "NOT_FOUND"`
   is more useful than `code: -32014`. Grep for the string across the
   codebase finds where it's raised and where it's handled.
3. **Numbers cluster meaning unhelpfully at this scale.** With ~40 domain
   error codes, there's no clean numeric grouping that adds value over
   the existing enum's grouping by section header.

### What gets logged where

The translator (`daemon/errors.translate`) is a pure function — it does
not log. Logging is the dispatcher's job, **before** translation:

- **`JsonRpcError` subclasses** (parse error, invalid request) are
  client-side problems. The dispatcher logs them at INFO level — they're
  expected, and the message is safe to include because we constructed it.
- **`LocalLibraryError` subclasses** are domain conditions. The dispatcher
  logs them at WARNING level with the full structured details, then
  translates with the safe message + code.
- **Unknown exceptions** are programming errors. The dispatcher logs them
  at ERROR level with the full traceback, then translates with a redacted
  generic message — never echoing the raw exception text to the client.

This separation matters: the wire envelope is *what the client should know*,
the log line is *what the operator needs to debug*. They are not the same
audience and not the same content.

### Suggestions and structured `details`

`LocalLibraryError.details` is a free-form `dict[str, Any]` carried straight
through to `data.details`. The convention is:

- For `NOT_FOUND` errors on identifier lookup: `{"identifier": ..., "suggestions": [...]}`
  where `suggestions` is a list of citekeys returned by the existing
  `cli/utils.suggest_citekeys` helper. The plugin uses this to display
  "did you mean…?" hints.
- For `EMBEDDING_EXTENSION_UNAVAILABLE`: empty `details` — this is an
  install-time condition the user fixes by reinstalling sqlite-vec.
- For `NOT_IMPLEMENTED`: `{"hook": "doc_id"}` — names the hook the client
  asked for so future code can branch on it.

Clients should treat `details` as *informative but optional*: keys may
appear or disappear as features evolve. The contract is `error_code`;
`details` is best-effort context.

### Cross-references

- Design doc §"Error envelope"
- `src/local_library/core/errors.py` — the `ErrorCode` enum and
  `LocalLibraryError` class
- `src/local_library/daemon/errors.py` — the pure translator
- `src/local_library/daemon/dispatcher.py` — the logging-then-translating
  exception path


## Chapter 7 — Reliability: crash recovery, timeouts, liveness

A daemon plus a client is a distributed system, even when both processes
live on the same machine. The daemon can crash, hang, become slow, or
just stop responding. The client must:

1. Detect that the daemon is unreachable and tell the user something
   actionable (not "request failed: -1").
2. Recover when the daemon comes back, ideally without restarting itself.
3. Bound the time it will wait for any single request, so a hung daemon
   doesn't lock up the editor.

These three behaviors compose into what we call **tier-1 reliability** —
enough to keep the workflow usable under common failure modes (the user
killed the daemon manually, the machine slept, a query is genuinely slow).
Higher tiers (transparent failover, persistent request queues, retries
with idempotency tokens) are out of scope for this MVP.

### Detection: dead-channel + structured envelopes

Two signals tell the client the daemon is gone:

- **OS-level dead channel.** `vim.fn.chansend` returns 0 on a closed
  socket. `vim.fn.chaninfo(chan_id)` returns an empty table. We check
  the latter before every request and the former after every send.
- **No response within the per-method timeout.** If the daemon is alive
  but hung, our deferred timeout fires and we surface a request-level
  error with the method name and elapsed time.

Both paths produce a typed error table with a stable shape:
`{ code, message, error_code, details }`. The plugin's `notify.lua`
mapper translates the `error_code` to a user-facing string and a
`vim.log.levels` value. `DAEMON_UNREACHABLE` always pairs with an
ERROR-level toast that names `:LocalLibraryDaemon start` so the user
knows the next step.

### Recovery: bounded retry, not infinite reconnection

When `request_async` finds the channel dead, it tries to reconnect up
to three times with exponential backoff (50 ms, 150 ms, 450 ms). If all
three fail, the request errors out with `DAEMON_UNREACHABLE`. We do
*not* loop forever:

- **Three attempts is enough** to ride through a launchd respawn or a
  manual `daemon restart`, both of which complete in well under 1 s on
  a warm system.
- **Failing fast is correct** when the daemon is genuinely down. The
  user has actionable information; further retries just delay the
  notification.

The client also reconnects between sessions transparently. If the user
kills the daemon, runs `:LocalLibraryDaemon start`, and immediately
fires `<leader>c` without reloading Neovim, the first request succeeds
via the reconnect path.

### Bounded waits: per-method timeouts

Different RPCs have different reasonable durations:

- `ping`: ~1 ms warm, 50 ms cold. **2 s timeout** flags real wedging.
- `get_document`: a few SQL lookups, no model inference. **2 s timeout**.
- `search`: includes embedder + reranker + sqlite-vec. **5 s timeout**
  by default; the warm p95 should be well under this.

Configurable per-method timeouts are essential because a search timeout
must be larger than a ping timeout, and tying them together means
either pings hang too long or searches abort spuriously.

The timeout is implemented via `vim.defer_fn` + a pending-id check in
`request_async`. If the response arrives before the timeout fires, the
deferred callback finds the pending entry already cleared and does
nothing. If the timeout wins, the response (when it eventually
arrives) is dropped — its id is no longer in `_pending`.

### What we did NOT build (and why)

- **Idempotency tokens for retries.** All our methods are read-only;
  retrying a `search` that may have partially completed is harmless.
  When write methods land (Phase 7+ MCP v2 ingestion), this becomes
  necessary.
- **Connection pooling.** A single client instance per Neovim session
  is fine; the daemon happily multiplexes via `asyncio.start_unix_server`'s
  per-connection coroutines.
- **Circuit breakers.** With a 3-attempt cap and per-method timeouts,
  the existing logic is effectively a tiny circuit breaker (open after
  3 failures within ~700 ms; closes on the next successful connect).
  A formal breaker would add state we don't currently need.

### Operator visibility: structured logs

The daemon-side logging change emits one log line per request:

```
2026-04-25 09:15:01,234 INFO local_library.daemon.dispatcher
  method=search id=42 status=ok duration_ms=183.4
```

`grep status=domain_error` shows all errors over a session. `grep
duration_ms=` plus `awk` gives ad-hoc latency distributions without
spinning up a metrics stack. This is the simplest possible observability
that's still useful — operator tooling builds on top of grep, not under it.

### Cross-references

- Design doc §"Edge cases" — the table of failure modes and their UX
- `nvim/lua/local_library/client.lua` — reconnect + timeout logic
- `nvim/lua/local_library/notify.lua` — `error_code` → user message mapper
- `src/local_library/daemon/dispatcher.py` — structured per-request log
- `nvim/tests/reliability_spec.lua` — kill + restart roundtrip verification


## Chapter 8 — Case studies: how the abstract patterns landed in this project

Earlier chapters introduced abstract patterns: daemons (ch. 1), service
management (ch. 2), framing (ch. 3), RPC envelopes (ch. 4), single-thread
DB constraints (ch. 5), cross-process error handling (ch. 6), reliability
(ch. 7). This final chapter pulls four of the most consequential decisions
into one place — what we chose, what we considered, and why the result is
what it is.

### Case study 1 — sqlite-vec → asyncio: the single-worker executor

**Context (ch. 5):** sqlite-vec requires single-thread access. asyncio
gives us cooperative concurrency on one thread, which seems compatible —
until you observe that model inference (embedder, reranker) is CPU-bound
and would block the event loop, killing `ping` responsiveness.

**Considered:**

1. *Refactor `Retriever.retrieve()` to expose embed/query/rerank phases
   separately,* so the daemon could run model phases in an executor and
   sqlite-vec phases on the loop thread. Would honor the original design
   verbatim. Cost: changes to the Retriever protocol, ripples through
   `VectorRetriever`, `FTSRetriever`, `HybridRetriever`, `RerankedRetriever`,
   plus their tests. High-touch, scope-bending.
2. *Use a multi-worker executor with `check_same_thread=False`.* Would
   permit theoretical parallelism but defeat sqlite-vec's invariant; we'd
   need our own mutex on the connection. The "concurrency" we'd buy is
   illusory — sqlite-vec serializes anyway.
3. *Run the entire `retrieve()` call on the asyncio loop thread.* Simplest
   to write; hangs `ping` for the duration of any search. Unacceptable.

**Chose:** A `ThreadPoolExecutor(max_workers=1)` that owns the Library
end-to-end. The Library is *constructed* on the executor thread, *closed*
on the executor thread, and every `retrieve()` runs on it. The asyncio
loop thread handles only socket I/O and dispatch.

**Why it works:** sqlite-vec sees one thread for its entire lifetime.
The event loop stays free for `ping` (which doesn't enter the executor)
and for accepting new connections. The "loss" of parallel searches is
illusory — sqlite-vec wouldn't have allowed it anyway.

**See:** `daemon/server.py:_make_library_executor`,
`run_on_library_thread`; concepts ch. 5 §"local-library's resolution".

### Case study 2 — JSON-RPC + debuggability: rejecting msgpack-rpc

**Context (ch. 4):** RPC needs a serialization format. The mainstream
choices for a Python daemon talking to a Neovim plugin are JSON-RPC 2.0,
msgpack-rpc (Neovim's native protocol), and a custom binary protocol.

**Considered:**

1. *msgpack-rpc.* Neovim's `vim.fn.sockconnect("...", ..., {rpc=true})`
   speaks it natively. Bytes on the wire are 30-50% smaller than JSON
   for our payloads. `msgpack` is faster to parse than `json`. Looks
   like the obvious choice.
2. *A custom binary protocol.* Maximum compactness; no library
   dependency. Real overhead in implementation and debugging.
3. *JSON-RPC 2.0.* Human-readable, debuggable with `nc -U` + a text
   editor, every language has a JSON library, the spec is three pages
   and two decades stable.

**Chose:** JSON-RPC 2.0.

**Why it works:** Our payloads are small (`<10 KB` typical search
result). The 30-50% size difference is negligible at our scale —
microseconds of wire transit on a Unix socket. What we lose: a small
amount of throughput we never needed. What we gain:

- A human can `nc -U $socket` and type a request. msgpack is opaque
  bytes you can't paste.
- `tcpdump -i lo0 -A` (or its UDS equivalent) shows readable traffic.
  msgpack requires a decoder.
- `python-lsp-jsonrpc` and `jsonrpcserver` exist, but neither earned
  its keep at our 3-method scale (ch. 4 §"Library choice"). We rolled
  our own framing + parser in ~200 LOC and own every line.

**Why msgpack-rpc was actually wrong, not just suboptimal:** Neovim's
msgpack-rpc framing is *its own* — it's not the standard msgpack-rpc
spec. Adopting `rpc=true` would have entangled us with Neovim's RPC
quirks (notification dispatch through Neovim, request-id semantics,
the implicit `nvim_*` method namespace). Our daemon must remain
editor-agnostic for the future MCP server v2 to share it.

**See:** `daemon/protocol.py`; design doc §"Patterns this design
deliberately does not follow"; concepts ch. 4 §"Why JSON-RPC 2.0".

### Case study 3 — CLI-managed with launchd pathway

**Context (ch. 2):** Three styles of process supervision: user-managed
CLI, system supervisor (launchd/systemd), socket activation.

**Considered:**

1. *Full launchd LaunchAgent now.* Plist with `KeepAlive`, `RunAtLoad`,
   `Sockets`. Pays for itself if the daemon is "always on." Requires
   the user to install the plist, deal with launchd diagnostics
   (`launchctl print user/$UID/com.local-library.daemon`), and accept
   that "stop the daemon" means "edit the plist."
2. *Double-fork demonization (PEP 3143).* The classic Unix daemon
   recipe. Modern consensus (per `man systemd.exec` and the
   "type=simple" design): cargo-cult for user-level services in 2025.
3. *CLI-managed (foreground + signal-driven shutdown).* User runs
   `local-library daemon start`/`stop`. No double-fork. Process is a
   plain foreground program for tooling purposes (`ps`, `lsof`).

**Chose:** CLI-managed for MVP, with explicit forward-compat for
launchd via the `LAUNCH_ACTIVATE_SOCKET_FD` env var hook.

**Why it works:**

- The user's workflow is "start the daemon when I begin writing,
  stop it when I'm done." launchd's "always on" model would burn
  ~200 MB of RSS across days when nothing is happening.
- The forward-compat shim (`socket_activation.inherited_socket()`)
  is ~15 LOC and tested. Migrating to launchd is a *packaging* change
  (write a plist, add a `KeepAlive` policy), not a code change.
- Avoiding double-fork avoids a class of bugs: TTY detachment, file
  descriptor inheritance, working directory surprises. We don't pay
  for this complexity because we don't need it.

**The path forward:** A LaunchAgent plist with a `Sockets` key would
pre-bind the socket and pass the FD; the daemon's `inherited_socket()`
would pick it up. No code change in the daemon. The shim turns the
launchd migration from a refactor into a config edit.

**See:** `daemon/socket_activation.py`; design doc §"Process model";
concepts ch. 2 §"local-library's choice".

### Case study 4 — Three hook scaffolding mechanisms

**Context (Phase 5/6):** The MVP defers three features (document-scoped
search, bib-aware ranking, direct text input). Each could be
"deferred" with no scaffolding — but then enabling each later requires
coordinated changes on both sides of the socket boundary. We wanted to
choose hook mechanisms that match each feature's failure semantics.

The three mechanisms (named for their failure mode):

#### Loud-error hook: `search.doc_id`

Document-scoped search ("find chunks within `@Smith2023`") would
silently change the *content* of the response if the daemon ignored
the parameter — the user asks for "within Smith2023" and gets the full
corpus.

**Mechanism:** Daemon accepts `doc_id` parameter. Non-null value raises
`LocalLibraryError(NOT_IMPLEMENTED, details={"hook": "doc_id"})`. The
plugin's `notify` mapper translates this to "document-scoped search is
not yet available." The user gets *signal*, not a wrong answer.

**Coupling profile:** When implementation lands, daemon and plugin
both need to update — daemon to actually filter, plugin to remove the
"not yet available" notification path. Tight two-side coordination.

#### Silent-inert hook: `search.boost_citekeys`

Bib-aware preferential ranking would silently change the *ordering* of
search results if the daemon ignored the parameter — degraded
gracefully, the user just gets unsorted-by-citation-presence results.
That's a quality regression, not a correctness regression.

**Mechanism:** Daemon accepts `boost_citekeys` and currently ignores
it. The plugin always passes the current project's citekeys
(`bibliography.list_citekeys(refs_path)`). When the daemon-side
implementation lands, it has effect immediately — no plugin release
needed.

**Coupling profile:** Plugin-leads-backend. Plugin code is already
correct; daemon catches up in a future release with zero coordination.

#### Architectural hook: direct text input mode

A future feature lets the user type a free-text query (not a visual
selection). The daemon already accepts arbitrary query strings via
`search.query`, so there's no protocol change to make. The hook is
*structural*: the plugin's hybrid UI/data split means a future
`input_ui.lua` module (or an alternative Telescope picker) can feed
the existing pipeline without touching the daemon or any other module.

**Mechanism:** None on the wire. The hook is the architecture itself —
the discipline that `client.lua`, `actions.lua`, `bibliography.lua`
know nothing about Telescope. A new UI consumes them as-is.

**Coupling profile:** Plugin-only. Adding direct input mode is purely
a plugin change.

#### What this vocabulary buys us

We now have three named patterns for "scaffold a future feature today,"
each matched to a different failure mode:

| Mechanism | Failure mode if ignored | Coupling on rollout |
|-----------|-------------------------|---------------------|
| Loud-error | Wrong content | Tight two-side |
| Silent-inert | Degraded ordering | Plugin-leads-backend |
| Architectural | N/A (structural) | Plugin-only |

Each design choice — *not just* "build a hook" but *which kind of
hook* — is a small decision that compounds over the project's life.
Documenting the vocabulary explicitly (here and in design doc
§"Structural hooks") means future contributors can reach for the right
mechanism by name.

**See:** Design doc §"Structural hooks"; `daemon/methods.py`
(loud-error in `search()`); `nvim/lua/local_library/init.lua`
(silent-inert via `boost_citekeys` always passed);
`nvim/lua/local_library/` module organization (architectural).

---

The daemons concepts doc closes here. Each chapter has cross-references
into the design doc and the codebase; each design and code decision has
a return path into a chapter. Future maintainers — including future-you
— have a single document that explains both *what* the daemon does and
*why* it's shaped the way it is.
