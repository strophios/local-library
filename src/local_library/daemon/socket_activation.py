"""Socket acquisition: launchd FD inheritance with manual-bind fallback.

# pattern: Imperative Shell (socket I/O, env inspection)

When the daemon runs under a future launchd LaunchAgent, launchd will
pre-bind the socket and hand us a file descriptor. For Phase 1 there is no
launchd wiring; the shim still exists as the single code path for acquiring
the listening socket, so the launchd upgrade is a packaging change — not a
code change.

The shim supports two activation modes:

1. **Env-var FD inheritance** (Phase 1, testable today): caller — typically
   a wrapper script or a future test harness — pre-binds a socket and passes
   the integer FD in the `LAUNCH_ACTIVATE_SOCKET_FD` environment variable.

2. **Native launchd `launch_activate_socket`** (TODO — activated when we
   migrate to a LaunchAgent plist with a `Sockets` key). The real API lives
   in `<launch.h>` and requires a ctypes binding against libc. See
   docs/concepts/daemons.md §2 for the full launchd migration recipe.

If neither activation path produces a socket, `bind_listen()` binds one
manually at the configured path, unlinks any stale socket file, and chmods
to 0600.
"""

from __future__ import annotations

import os
import socket
from pathlib import Path

ACTIVATION_ENV_VAR = "LAUNCH_ACTIVATE_SOCKET_FD"
"""Name of the env var carrying a pre-bound, listening Unix-socket FD.

This name mirrors Apple's `launch_activate_socket` API while being explicit
about the mechanism (FD inheritance via env var). Under a future launchd
migration, a short ctypes wrapper around `launch_activate_socket` will
supersede this env var — callers won't need to change."""


def inherited_socket() -> socket.socket | None:
    """Return a socket built from an inherited FD, or None if not activated.

    Returns None when:
    - The env var is unset.
    - The env var value is not a decimal integer.
    - The FD is not open (os.fstat raises OSError).
    """
    raw = os.environ.get(ACTIVATION_ENV_VAR)
    if raw is None:
        return None
    try:
        fd = int(raw)
    except ValueError:
        return None
    try:
        os.fstat(fd)
    except OSError:
        return None
    # dup() so that the caller owns a socket object whose close() is safe;
    # the original FD remains owned by the parent.
    return socket.socket(fileno=os.dup(fd))


def bind_listen(path: Path, backlog: int = 128) -> socket.socket:
    """Bind a new Unix-domain listening socket at `path`.

    Removes any pre-existing socket file (stale from a prior crash) before
    binding. Sets 0600 permissions on the socket file — only the daemon's
    user can connect. Returns the listening socket (caller must close).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.bind(str(path))
    os.chmod(path, 0o600)
    sock.listen(backlog)
    return sock
