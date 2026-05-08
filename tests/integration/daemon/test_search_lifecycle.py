"""End-to-end socket lifecycle: spawn daemon, populate library out-of-band,
issue real search and get_document requests over the UDS, verify shapes.

This is the largest integration test — it confirms that the executor wiring,
the protocol_handler, the dispatcher, and the methods all compose correctly
under real subprocess conditions.
"""

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

_SETUP_SCRIPT = """
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
from local_library.core.library import Library

# The sample PDF is passed as argv[1]; we'll add it with mocked extraction
# to avoid needing Marker to run.
pdf_path = sys.argv[1]
metadata = {
    'id': 'Sample2026',
    'type': 'article-journal',
    'title': 'Sample Paper on RAG',
    'author': [{'family': 'Author', 'given': 'Test'}],
    'issued': {'date-parts': [[2026]]},
}

# Construct Library with same isolation as daemon will use
data_dir_str = os.environ.get("LOCAL_LIBRARY_DATA_DIR")
if data_dir_str:
    data_dir = Path(data_dir_str)
    lib = Library(
        db_path=data_dir / "library.db",
        storage_dir=data_dir / "storage",
        extracted_dir=data_dir / "extracted",
        embed_on_add=False,
    )
else:
    lib = Library(embed_on_add=False)

with lib:
    # Mock the extraction to avoid loading Marker
    with patch.object(
        lib._extractors[0],
        "extract_and_validate",
    ) as mock_extract:
        mock_extract.return_value = MagicMock(
            text="This document discusses retrieval-augmented generation in detail. "
            "Specifically, the use of dense embeddings combined with full-text search."
        )
        lib.add(pdf_path, metadata=metadata)

    # Embed if possible; skip if sqlite-vec unavailable
    try:
        lib.embed_all()
    except Exception as e:
        if "EMBEDDING_EXTENSION_UNAVAILABLE" not in str(e):
            raise
"""


@pytest.fixture
def daemon_with_corpus(short_tmp_path: Path, sample_pdf: Path):
    """Spawn the daemon against a tmp data dir prepopulated with one document.

    Uses short_tmp_path to avoid Darwin's AF_UNIX sun_path length constraint.
    Populates a library out-of-band via a _SETUP_SCRIPT subprocess invocation,
    then starts the daemon.
    """
    env = os.environ.copy()
    # Set both XDG_DATA_HOME and LOCAL_LIBRARY_DATA_DIR to ensure isolation
    # on all platforms, particularly Darwin where platformdirs ignores XDG_DATA_HOME
    data_home = str(short_tmp_path / "data")
    data_dir = str(short_tmp_path / "data" / "local-library")
    env["XDG_DATA_HOME"] = data_home
    env["LOCAL_LIBRARY_DATA_DIR"] = data_dir
    env["PYTHONUNBUFFERED"] = "1"
    # Skip model warmup. The tests using this fixture exercise RPC
    # semantics (results, error envelopes, concurrency), not search
    # latency. Warmup parks the asyncio loop on the executor task for
    # ~10s before _serve runs, so requests queue in the kernel accept
    # backlog while the fixture's socket-bound poll already considers
    # the daemon "ready" — which corrupts any timing-based assertion
    # (notably test_ping_remains_responsive_during_search).
    env["LOCAL_LIBRARY_DAEMON_SKIP_WARMUP"] = "1"

    # Pre-populate the library
    setup = subprocess.run(
        [sys.executable, "-c", _SETUP_SCRIPT, str(sample_pdf)],
        env=env,
        capture_output=True,
        text=True,
    )
    if setup.returncode != 0:
        pytest.skip(f"could not populate test library: {setup.stderr}")

    # Spawn the daemon
    proc = subprocess.Popen(
        [sys.executable, "-m", "local_library.daemon.server"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    socket_path = Path(data_dir) / "daemon.sock"
    deadline = time.monotonic() + 30.0
    while time.monotonic() < deadline:
        if socket_path.is_socket():
            break
        if proc.poll() is not None:
            stdout = proc.stdout.read().decode() if proc.stdout else ""
            pytest.fail(f"daemon exited during startup: {stdout}")
        time.sleep(0.1)
    else:
        proc.kill()
        pytest.fail("daemon did not bind socket within 30s")

    yield {"env": env, "socket_path": socket_path, "proc": proc}

    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()


def _rpc(socket_path: Path, request: dict) -> dict:
    """Send a JSON-RPC request over the Unix-domain socket and receive response."""
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.settimeout(15.0)
        s.connect(str(socket_path))
        s.sendall(json.dumps(request).encode("utf-8") + b"\n")
        data = b""
        while not data.endswith(b"\n"):
            chunk = s.recv(65536)
            if not chunk:
                break
            data += chunk
    return json.loads(data)


def test_search_via_socket_returns_results(daemon_with_corpus: dict) -> None:
    response = _rpc(
        daemon_with_corpus["socket_path"],
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "search",
            "params": {"query": "retrieval generation", "limit": 5},
        },
    )
    assert response["id"] == 1
    assert "result" in response, response
    assert response["result"]["total_candidates"] >= 1
    assert response["result"]["reranked"] is True


def test_get_document_via_socket(daemon_with_corpus: dict) -> None:
    # First search to find the actual citekey (it's generated from metadata fields)
    search_response = _rpc(
        daemon_with_corpus["socket_path"],
        {
            "jsonrpc": "2.0",
            "id": 100,
            "method": "search",
            "params": {"query": "retrieval augmented generation", "limit": 1},
        },
    )
    assert search_response["id"] == 100
    assert "result" in search_response
    actual_citekey = search_response["result"]["results"][0]["citekey"]

    # Now test get_document with the actual citekey
    response = _rpc(
        daemon_with_corpus["socket_path"],
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "get_document",
            "params": {"identifier": f"@{actual_citekey}"},
        },
    )
    assert response["id"] == 2
    if "error" in response:
        pytest.fail(f"get_document returned error: {response['error']}")
    # Verify the daemon round-trips the supplied metadata. csl_json["id"] is
    # the strongest assertion — it pins the input metadata against the wire
    # output regardless of how citekey generation chose to derive the citekey.
    assert response["result"]["csl_json"]["id"] == "Sample2026"
    assert response["result"]["csl_json"]["title"] == "Sample Paper on RAG"


def test_search_doc_id_hook_returns_not_implemented_via_socket(
    daemon_with_corpus: dict,
) -> None:
    response = _rpc(
        daemon_with_corpus["socket_path"],
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "search",
            "params": {"query": "x", "doc_id": "@Sample2026"},
        },
    )
    assert response["error"]["code"] == -32000
    assert response["error"]["data"]["error_code"] == "NOT_IMPLEMENTED"


def test_unknown_method_returns_method_not_found_via_socket(
    daemon_with_corpus: dict,
) -> None:
    response = _rpc(
        daemon_with_corpus["socket_path"],
        {"jsonrpc": "2.0", "id": 4, "method": "no_such_method"},
    )
    assert response["error"]["code"] == -32601


def test_ping_remains_responsive_during_search(daemon_with_corpus: dict) -> None:
    """ping must not block on search — it doesn't go through the executor."""
    import threading

    sock_path = daemon_with_corpus["socket_path"]
    search_done = threading.Event()
    search_latency = []

    def _search() -> None:
        t0 = time.perf_counter()
        _rpc(
            sock_path,
            {
                "jsonrpc": "2.0",
                "id": 100,
                "method": "search",
                "params": {"query": "retrieval"},
            },
        )
        search_latency.append(time.perf_counter() - t0)
        search_done.set()

    t = threading.Thread(target=_search)
    t.start()
    time.sleep(0.05)
    t0 = time.perf_counter()
    _rpc(sock_path, {"jsonrpc": "2.0", "id": 101, "method": "ping"})
    ping_latency = time.perf_counter() - t0
    search_done.wait(timeout=30.0)
    t.join(timeout=5.0)

    assert ping_latency < 0.5, (
        f"ping took {ping_latency:.3f}s while search took "
        f"{search_latency[0]:.3f}s — daemon is NOT concurrent"
    )
