"""CLI subcommands for daemon process lifecycle management.

# pattern: Imperative Shell

`run` is foreground (the launchd / test-harness entry).
`start` spawns a detached background process running the daemon module.
`stop` sends SIGTERM to the PID and waits for release of the PID file.
`status` reports pid, uptime, resident memory (reads live data via psutil).
`restart` is stop-then-start.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time

import psutil
import typer
from rich.console import Console
from rich.table import Table

from local_library import config
from local_library.daemon import pid_file
from local_library.daemon import server as daemon_server

app = typer.Typer(
    name="daemon",
    help="Manage the long-running local-library daemon.",
    add_completion=False,
)

_console = Console()


def _resolve_running_pid() -> int | None:
    """Return the PID of a running daemon, or None if not running."""
    pid = pid_file.read_pid(config.get_daemon_pid_path())
    if pid is None:
        return None
    if not pid_file.is_process_alive(pid):
        return None
    return pid


@app.command()
def run() -> None:
    """Run the daemon in the foreground (does not return until SIGTERM)."""
    raise typer.Exit(code=daemon_server.main())


@app.command()
def start() -> None:
    """Start the daemon as a detached background process."""
    if _resolve_running_pid() is not None:
        _console.print("[yellow]daemon already running[/yellow]")
        raise typer.Exit(code=0)

    config.ensure_directories()
    log_path = config.get_daemon_log_dir() / "daemon.out"

    # Use the python module form to avoid depending on the script-entry path
    # being on PATH at the exact moment `start` runs.
    cmd = [sys.executable, "-m", "local_library.daemon.server"]

    stdout = open(log_path, "ab")
    proc = subprocess.Popen(
        cmd,
        stdout=stdout,
        stderr=subprocess.STDOUT,
        start_new_session=True,  # detach: new process group, no controlling TTY
        close_fds=True,
    )
    # Close the parent's copy of the log FD. The child has its own copy via Popen,
    # so closing here prevents FD leak in the parent process.
    stdout.close()

    # Poll briefly for the PID file to appear as confirmation.
    deadline = time.monotonic() + 5.0
    pid_path = config.get_daemon_pid_path()
    while time.monotonic() < deadline:
        if pid_path.exists() and pid_file.read_pid(pid_path) == proc.pid:
            _console.print(f"[green]daemon started[/green] (pid={proc.pid})")
            return
        if proc.poll() is not None:
            _console.print(
                f"[red]daemon exited during startup[/red] (exit={proc.returncode}, see {log_path})"
            )
            raise typer.Exit(code=1)
        time.sleep(0.1)

    _console.print(
        f"[red]daemon did not report ready within 5s[/red] (pid={proc.pid}, see {log_path})"
    )
    raise typer.Exit(code=1)


@app.command()
def stop() -> None:
    """Stop the running daemon (SIGTERM + wait for PID file removal)."""
    pid = _resolve_running_pid()
    if pid is None:
        _console.print("[yellow]daemon not running[/yellow]")
        raise typer.Exit(code=0)

    os.kill(pid, signal.SIGTERM)

    deadline = time.monotonic() + 10.0
    pid_path = config.get_daemon_pid_path()
    while time.monotonic() < deadline:
        if not pid_path.exists():
            _console.print(f"[green]daemon stopped[/green] (pid={pid})")
            return
        if not pid_file.is_process_alive(pid):
            _console.print(f"[green]daemon stopped[/green] (pid={pid}, stale PID file left)")
            return
        time.sleep(0.1)

    _console.print(f"[red]daemon did not stop within 10s[/red] (pid={pid})")
    raise typer.Exit(code=1)


@app.command()
def restart() -> None:
    """Stop the daemon (if running) and start a fresh instance."""
    if _resolve_running_pid() is not None:
        stop()
    start()


@app.command()
def status() -> None:
    """Report daemon liveness, pid, uptime, and resident memory."""
    pid = _resolve_running_pid()
    if pid is None:
        _console.print("[red]daemon not running[/red]")
        raise typer.Exit(code=1)

    proc = psutil.Process(pid)
    rss = proc.memory_info().rss
    uptime = time.time() - proc.create_time()

    table = Table(show_header=False, box=None)
    table.add_row("pid", str(pid))
    table.add_row("socket", str(config.get_socket_path()))
    table.add_row("uptime", f"{uptime:.1f}s")
    table.add_row("resident", f"{rss / (1024 * 1024):.1f} MiB")
    _console.print(table)
