# Neovim Citation Workflow Implementation Plan — Phase 3: Library Integration (`search` + `get_document`)

**Goal:** Wire the existing `Library` orchestrator into the daemon, register `search` and `get_document` JSON-RPC methods, and route all `Library` work through a single-worker `ThreadPoolExecutor` so sqlite-vec's single-thread access invariant is preserved while the asyncio event loop stays free for socket I/O and `ping`.

**Architecture:** A single-worker executor owns the `Library` for its full lifetime. The Library is constructed *on the executor thread*, all method handlers (`search`, `get_document`) execute their full validation→`get_retriever`→`retrieve`→serialize call stack on that same thread, and the Library is closed on the same thread at shutdown. The asyncio event loop never touches the connection. Method handlers live in a new `daemon/methods.py` module; serialization helpers there project `SearchResult` + `Document` to the design's RPC wire shape.

**Tech Stack:** `concurrent.futures.ThreadPoolExecutor`, `asyncio.run_in_executor`, existing `Library`/`Retriever`/`SearchResult`/`Document` APIs. No new dependencies.

**Scope:** 3 of 7 phases from `docs/design-plans/2026-04-24-neovim-citation-workflow.md`.

**Codebase verified:** 2026-04-24.

**Known platform constraint (Darwin AF_UNIX):** Task 5 of this phase spawns a daemon and binds sockets in the test fixture. See the "Known platform constraint (Darwin AF_UNIX)" note in phase_01.md for the full explanation and workaround. The constraint affects this phase's Task 5 (`tests/integration/daemon/test_search_lifecycle.py`); use `short_tmp_path` from `tests/unit/daemon/conftest.py` if you need to bind AF_UNIX sockets in fixtures.

**Design deviations (deliberate, captured in concepts chapter 5):**
- The design specified "model calls in executor; sqlite-vec on event-loop thread." Codebase reality: `Retriever.retrieve()` interleaves model + sqlite calls in one sync function. Without a Retriever refactor (out of scope), splitting them is infeasible. Resolution: single-worker executor owns the Library entirely; Library never crosses thread boundaries. This preserves the design's two important properties — sqlite-vec single-thread access intact; loop responsive during slow work — without the refactor cost. Trade-off documented and acceptable.
- `SearchResult` lacks `document_authors`, `document_year`, `extracted_markdown_path`. We join `Document` per result (k≤10, cheap).
- Reranker overwrites pre-rerank score; `rerank_score` mirrors `score` when reranking is on. Preserving both is a deferred Library enhancement.

**Executor skills:** `ed3d-house-style:coding-effectively` (FCIS: serialization helpers are pure Functional Core; method handlers are Mixed; server lifecycle is Imperative Shell), `astral:uv`, `astral:ruff`, `ed3d-plan-and-execute:test-driven-development`, `ed3d-plan-and-execute:verification-before-completion`. Required reading before this phase: `src/local_library/core/library.py:111-311`, `src/local_library/embeddings/base.py:14-216`, `src/local_library/cli/utils.py:50-124`, `src/local_library/mcp/server.py:412-423`.

---

<!-- START_TASK_1 -->
## Task 1: Add `NOT_IMPLEMENTED` ErrorCode

**Type:** Functionality (small).

**Files:**
- Modify: `src/local_library/core/errors.py`
- Modify: `tests/unit/test_errors.py`

### Step 1: Add the enum member

Open `src/local_library/core/errors.py`. In the Lookup section, immediately after `AMBIGUOUS_MATCH = "AMBIGUOUS_MATCH"`, insert:

```python
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
```

### Step 2: Add a smoke assertion

Open `tests/unit/test_errors.py` (the existing file in `tests/unit/`, not `tests/unit/daemon/test_errors.py`). Append:

```python
def test_not_implemented_error_code_exists() -> None:
    from local_library.core.errors import ErrorCode

    assert ErrorCode.NOT_IMPLEMENTED.value == "NOT_IMPLEMENTED"
```

### Step 3: Run + lint + commit

```bash
uv run pytest tests/unit/test_errors.py -v
uv run ruff check src/local_library/core/errors.py tests/unit/test_errors.py
git add src/local_library/core/errors.py tests/unit/test_errors.py
git commit -m "feat(errors): add NOT_IMPLEMENTED error code for daemon hook responses"
```
<!-- END_TASK_1 -->

<!-- START_SUBCOMPONENT_A (tasks 2-4) -->

<!-- START_TASK_2 -->
## Task 2: Library lifecycle on a single-worker executor

**Type:** Functionality. Establishes the executor model that subsequent tasks use.

**Files:**
- Modify: `src/local_library/daemon/server.py` (add executor + library singleton + helpers; wire startup/shutdown)
- Create: `tests/unit/daemon/test_server_library.py`

### Step 1: Write failing tests

`tests/unit/daemon/test_server_library.py`:

```python
"""Tests for the daemon's Library-on-executor lifecycle."""

import asyncio
import threading

from local_library.daemon import server


def test_library_executor_is_single_worker() -> None:
    """The retrieval executor must have exactly one worker thread to preserve
    sqlite-vec single-thread access discipline."""
    executor = server._make_library_executor()
    try:
        assert executor._max_workers == 1
    finally:
        executor.shutdown(wait=True)


def test_run_on_library_thread_executes_in_executor() -> None:
    """Verify run_on_library_thread routes work to the executor (not the loop)."""

    async def run() -> int:
        loop_thread = threading.current_thread().ident
        executor = server._make_library_executor()
        try:
            def task() -> int:
                assert threading.current_thread().ident != loop_thread
                return 42

            result = await server.run_on_library_thread(executor, task)
            return result
        finally:
            executor.shutdown(wait=True)

    assert asyncio.run(run()) == 42


def test_run_on_library_thread_serializes_calls() -> None:
    """Two concurrent calls must execute sequentially on the single-worker executor."""

    async def run() -> list[int]:
        executor = server._make_library_executor()
        seen: list[int] = []

        def task(n: int) -> int:
            import time as _t

            _t.sleep(0.05)
            seen.append(n)
            return n

        try:
            await asyncio.gather(
                server.run_on_library_thread(executor, task, 1),
                server.run_on_library_thread(executor, task, 2),
                server.run_on_library_thread(executor, task, 3),
            )
            return seen
        finally:
            executor.shutdown(wait=True)

    seen = asyncio.run(run())
    assert seen == [1, 2, 3]


def test_library_singleton_initially_none() -> None:
    assert server._library is None
```

### Step 2: Run tests, confirm they fail

```bash
uv run pytest tests/unit/daemon/test_server_library.py -v
```

Expected: AttributeError for `_make_library_executor`, `run_on_library_thread`, `_library`.

### Step 3: Add executor + singleton scaffolding to `server.py`

Edit `src/local_library/daemon/server.py`:

- Add imports near the top:

  ```python
  from concurrent.futures import ThreadPoolExecutor
  from typing import TYPE_CHECKING, Any, Callable, TypeVar

  if TYPE_CHECKING:
      from local_library.core.library import Library

  _T = TypeVar("_T")
  ```

- Add module-level state after `_LOGGER`:

  ```python
  _library: "Library | None" = None
  _library_executor: ThreadPoolExecutor | None = None
  ```

- Add helper functions below `_configure_logging`:

  ```python
  def _make_library_executor() -> ThreadPoolExecutor:
      """Create the single-worker executor that owns all Library calls.

      A single worker preserves sqlite-vec's single-threaded access invariant:
      the long-lived sqlite3 connection is created and used exclusively from
      this thread, so the asyncio event loop never touches the connection
      directly. See docs/concepts/daemons.md §5 for the full rationale.
      """
      return ThreadPoolExecutor(max_workers=1, thread_name_prefix="library")


  async def run_on_library_thread(
      executor: ThreadPoolExecutor,
      fn: Callable[..., _T],
      *args: Any,
      **kwargs: Any,
  ) -> _T:
      """Submit `fn(*args, **kwargs)` to the library executor and await result."""
      from functools import partial

      loop = asyncio.get_running_loop()
      bound = partial(fn, *args, **kwargs)
      return await loop.run_in_executor(executor, bound)
  ```

### Step 4: Wire startup + shutdown in `main()`

Replace the existing `main()` body's serve/cleanup block. The new flow:

1. Acquire PID lock and listening socket as before (unchanged).
2. Create the event loop and the library executor.
3. **Construct the Library on the executor thread** via `loop.run_until_complete(run_on_library_thread(...))`.
4. Run `_serve` as before.
5. In `finally`: close Library on the executor thread, shut down the executor, then close socket / unlink / release PID as before.

Replace the section starting at `loop = asyncio.new_event_loop()` with:

```python
    global _library, _library_executor  # noqa: PLW0603
    _library_executor = _make_library_executor()

    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        stop_event = asyncio.Event()
        _install_signal_handlers(loop, stop_event)

        from local_library.core.library import Library

        # Construct AND enter the Library on the executor thread. Entering
        # via __enter__ matches the codebase's idiomatic Library lifecycle
        # (every other Library user — MCP, CLI, integration tests — uses
        # `with Library(...) as lib:`); the matching __exit__ is fired in
        # the finally block below by calling close() on the executor.
        def _construct_and_enter() -> "Library":
            lib = Library(embed_on_add=False)
            lib.__enter__()
            return lib

        _library = loop.run_until_complete(
            run_on_library_thread(_library_executor, _construct_and_enter)
        )
        _LOGGER.info("daemon ready at %s", config.get_socket_path())
        loop.run_until_complete(_serve(listening, stop_event))
        _LOGGER.info("daemon shut down cleanly")
        return 0
    finally:
        if _library is not None and _library_executor is not None:
            try:
                loop.run_until_complete(
                    run_on_library_thread(_library_executor, _library.close)
                )
            except Exception:  # noqa: BLE001
                _LOGGER.exception("error closing Library on shutdown")
            _library = None
        if _library_executor is not None:
            _library_executor.shutdown(wait=True)
            _library_executor = None
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
```

### Step 5: Run unit tests

```bash
uv run pytest tests/unit/daemon/test_server_library.py -v
```

Expected: 4 tests pass.

### Step 6: Run full daemon unit suite for regression check

```bash
uv run pytest tests/unit/daemon/ -v
```

Expected: all Phase 1+2 tests still pass — `ping` doesn't touch the Library so adding the lifecycle has no functional effect on existing tests.

### Step 7: Lint + format + commit

```bash
uv run ruff check src/local_library/daemon/server.py tests/unit/daemon/test_server_library.py
uv run ruff format src/local_library/daemon/server.py tests/unit/daemon/test_server_library.py
git add src/local_library/daemon/server.py tests/unit/daemon/test_server_library.py
git commit -m "feat(daemon): single-worker executor for Library, constructed on its own thread

A ThreadPoolExecutor(max_workers=1) owns all Library work — including
construction and close — so sqlite-vec's single-thread access invariant is
preserved without requiring check_same_thread=False on the connection. The
asyncio event loop never touches the Library directly; run_on_library_thread
is the sole boundary."
```
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
## Task 3: `search` method handler (TDD with mocked Library)

**Type:** Functionality.

**Files:**
- Create: `tests/unit/daemon/test_methods_search.py`
- Create: `src/local_library/daemon/methods.py`

### Step 1: Write failing tests

`tests/unit/daemon/test_methods_search.py`:

```python
"""Tests for the daemon's search method handler.

Uses a mocked Library so this tests handler logic + serialization without
loading the real embedder or sqlite-vec. The end-to-end smoke test against a
real corpus lives in tests/integration/daemon/test_methods.py (Task 4).
"""

import asyncio
from unittest.mock import MagicMock
from uuid import UUID

import pytest

from local_library.core.errors import EmbeddingError, ErrorCode
from local_library.daemon import methods, protocol


def _fake_chunk(
    chunk_id: str = "c-1",
    doc_id: str = "00000000-0000-0000-0000-000000000001",
    text: str = "the quick brown fox",
    section: str = "Introduction",
) -> MagicMock:
    chunk = MagicMock()
    chunk.chunk_id = chunk_id
    chunk.doc_id = UUID(doc_id)
    chunk.text = text
    chunk.section = section
    return chunk


def _fake_search_result(
    chunk_id: str = "c-1",
    doc_id: str = "00000000-0000-0000-0000-000000000001",
    score: float = 0.9,
    title: str = "A Paper",
    citekey: str = "Smith2023",
) -> MagicMock:
    result = MagicMock()
    result.chunk = _fake_chunk(chunk_id=chunk_id, doc_id=doc_id)
    result.score = score
    result.doc_title = title
    result.doc_citekey = citekey
    return result


def _fake_document(
    doc_id: str = "00000000-0000-0000-0000-000000000001",
    citekey: str = "Smith2023",
    title: str = "A Paper",
    authors: str = "Smith, J.; Doe, A.",
    issued_year: int = 2023,
    extracted_path: str = "/tmp/extracted/ab/cd/foo.md",
) -> MagicMock:
    doc = MagicMock()
    doc.id = UUID(doc_id)
    doc.citekey = citekey
    doc.title = title
    doc.authors = authors
    doc.issued_year = issued_year
    doc.extracted_path = extracted_path
    doc.csl_json = {"id": citekey, "title": title}
    return doc


@pytest.fixture
def fake_library() -> MagicMock:
    lib = MagicMock()
    retriever = MagicMock()
    retriever.retrieve.return_value = [_fake_search_result()]
    lib.get_retriever.return_value = retriever
    lib.get.return_value = _fake_document()
    return lib


def _run(value):
    # Handlers are now plain sync functions; this shim stays for symmetry
    # with prior test code and so adding `async` later doesn't churn callers.
    return value


def test_search_happy_path_returns_well_shaped_result(fake_library: MagicMock) -> None:
    result = _run(methods.search(library=fake_library, query="hello"))
    assert result["total_candidates"] == 1
    assert result["reranked"] is True
    assert len(result["results"]) == 1
    r = result["results"][0]
    assert r["chunk_id"] == "c-1"
    assert r["doc_id"] == "00000000-0000-0000-0000-000000000001"
    assert r["citekey"] == "Smith2023"
    assert r["document_title"] == "A Paper"
    assert r["document_authors"] == ["Smith, J.", "Doe, A."]
    assert r["document_year"] == 2023
    assert r["score"] == pytest.approx(0.9)
    assert r["rerank_score"] == pytest.approx(0.9)
    assert r["chunk_text"] == "the quick brown fox"
    assert r["chunk_section_heading"] == "Introduction"
    assert r["extracted_markdown_path"] == "/tmp/extracted/ab/cd/foo.md"


def test_search_passes_mode_and_limit_through(fake_library: MagicMock) -> None:
    _run(methods.search(library=fake_library, query="q", mode="vector", limit=5))
    fake_library.get_retriever.assert_called_with(mode="vector", rerank=True)
    retriever = fake_library.get_retriever.return_value
    retriever.retrieve.assert_called_with(query="q", k=5, doc_ids=None)


def test_search_rerank_false_reflected_in_response(fake_library: MagicMock) -> None:
    result = _run(methods.search(library=fake_library, query="q", rerank=False))
    fake_library.get_retriever.assert_called_with(mode="hybrid", rerank=False)
    assert result["reranked"] is False
    assert "rerank_score" not in result["results"][0]


def test_search_invalid_mode_raises_invalid_params(fake_library: MagicMock) -> None:
    with pytest.raises(protocol.InvalidParams):
        _run(methods.search(library=fake_library, query="q", mode="bogus"))


def test_search_empty_query_raises_invalid_params(fake_library: MagicMock) -> None:
    with pytest.raises(protocol.InvalidParams):
        _run(methods.search(library=fake_library, query=""))


def test_search_doc_id_hook_returns_not_implemented(fake_library: MagicMock) -> None:
    """Loud-error hook: scoping by doc_id is not yet implemented."""
    from local_library.core.errors import LocalLibraryError

    with pytest.raises(LocalLibraryError) as exc_info:
        _run(methods.search(library=fake_library, query="q", doc_id="@Smith2023"))
    assert exc_info.value.code == ErrorCode.NOT_IMPLEMENTED


def test_search_boost_citekeys_silently_ignored(fake_library: MagicMock) -> None:
    """Silent-inert hook: boost_citekeys is accepted and ignored."""
    result_a = _run(methods.search(library=fake_library, query="q"))
    result_b = _run(
        methods.search(library=fake_library, query="q", boost_citekeys=["Smith2023"])
    )
    assert result_a == result_b


def test_search_propagates_embedding_extension_error(fake_library: MagicMock) -> None:
    fake_library.get_retriever.side_effect = EmbeddingError(
        "sqlite-vec missing", ErrorCode.EMBEDDING_EXTENSION_UNAVAILABLE
    )
    from local_library.core.errors import LocalLibraryError

    with pytest.raises(LocalLibraryError) as exc_info:
        _run(methods.search(library=fake_library, query="q"))
    assert exc_info.value.code == ErrorCode.EMBEDDING_EXTENSION_UNAVAILABLE


def test_search_authors_none_serializes_to_empty_list(fake_library: MagicMock) -> None:
    doc = _fake_document(authors=None)
    fake_library.get.return_value = doc
    result = _run(methods.search(library=fake_library, query="q"))
    assert result["results"][0]["document_authors"] == []


def test_search_year_none_serializes_to_null(fake_library: MagicMock) -> None:
    doc = _fake_document(issued_year=None)
    fake_library.get.return_value = doc
    result = _run(methods.search(library=fake_library, query="q"))
    assert result["results"][0]["document_year"] is None
```

### Step 2: Run failing tests

```bash
uv run pytest tests/unit/daemon/test_methods_search.py -v
```

Expected: ImportError for `local_library.daemon.methods`.

### Step 3: Implement `methods.py`

`src/local_library/daemon/methods.py`:

```python
"""JSON-RPC method handlers for the daemon.

# pattern: Mixed — handlers orchestrate Library calls (Imperative); the
# serialization helpers (_serialize_search_result, etc.) are pure (Functional Core).

The Library is passed in as an argument rather than imported globally so that
unit tests can inject a mock Library without needing the real Library
constructed. The server-side wiring (server.py:build_dispatcher) provides the
Library singleton at registration time.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from local_library.core.errors import ErrorCode, LocalLibraryError
from local_library.daemon import protocol

if TYPE_CHECKING:
    from local_library.core.library import Library
    from local_library.core.models import Document
    from local_library.embeddings.base import SearchResult

VALID_MODES = {"hybrid", "vector", "fts"}


# Note: `search` and `get_document` are plain sync functions, not coroutines.
# They run on the library executor thread (no real awaits inside). The
# dispatcher's executor wrapper (server.build_dispatcher) bridges sync ↔
# async at the executor boundary; keeping the handlers themselves sync
# avoids spinning up a per-request event loop via `asyncio.run`.


def search(
    *,
    library: "Library",
    query: str,
    mode: str = "hybrid",
    limit: int = 10,
    rerank: bool = True,
    doc_id: str | None = None,
    boost_citekeys: list[str] | None = None,
) -> dict[str, Any]:
    """Run a retrieval search and return the wire-shape result.

    Hook semantics (per design doc §"Structural hooks"):
    - `doc_id` (loud-error): non-null raises NOT_IMPLEMENTED so the client
      can surface "scoping not yet available" rather than silently returning
      whole-corpus results.
    - `boost_citekeys` (silent-inert): accepted and ignored. The plugin
      passes it routinely so a future daemon-side rollout requires no plugin
      change.
    """
    if not query or not query.strip():
        raise protocol.InvalidParams("'query' must be a non-empty string")
    if mode not in VALID_MODES:
        raise protocol.InvalidParams(
            f"'mode' must be one of {sorted(VALID_MODES)} (got {mode!r})"
        )
    if not isinstance(limit, int) or limit < 1 or limit > 100:
        raise protocol.InvalidParams("'limit' must be an integer in [1, 100]")

    if doc_id is not None:
        raise LocalLibraryError(
            "document-scoped search is not yet implemented",
            ErrorCode.NOT_IMPLEMENTED,
            details={"hook": "doc_id"},
        )
    _ = boost_citekeys  # silent-inert

    retriever = library.get_retriever(mode=mode, rerank=rerank)
    results = retriever.retrieve(query=query, k=limit, doc_ids=None)

    serialized = [
        _serialize_search_result(library=library, result=r, reranked=rerank)
        for r in results
    ]
    return {
        "results": serialized,
        "total_candidates": len(serialized),
        "reranked": rerank,
    }


def _serialize_search_result(
    *,
    library: "Library",
    result: "SearchResult",
    reranked: bool,
) -> dict[str, Any]:
    """Project a (SearchResult, joined Document) pair to the RPC wire shape."""
    doc = library.get(str(result.chunk.doc_id))
    payload: dict[str, Any] = {
        "chunk_id": result.chunk.chunk_id,
        "doc_id": str(result.chunk.doc_id),
        "citekey": doc.citekey or "",
        "document_title": doc.title or "",
        "document_authors": _split_authors(doc.authors),
        "document_year": doc.issued_year,
        "score": float(result.score),
        "chunk_text": result.chunk.text,
        "chunk_section_heading": result.chunk.section or None,
        "extracted_markdown_path": doc.extracted_path or "",
    }
    if reranked:
        payload["rerank_score"] = float(result.score)
    return payload


def _split_authors(authors: str | None) -> list[str]:
    """The Document model stores authors as 'Last, First; Last, First' strings.
    Wire shape is a list. Empty string → empty list.
    """
    if not authors:
        return []
    return [a.strip() for a in authors.split(";") if a.strip()]
```

### Step 4: Run tests, confirm they pass

```bash
uv run pytest tests/unit/daemon/test_methods_search.py -v
```

Expected: 10 tests pass.

### Step 5: Lint + format + commit

```bash
uv run ruff check src/local_library/daemon/methods.py tests/unit/daemon/test_methods_search.py
uv run ruff format src/local_library/daemon/methods.py tests/unit/daemon/test_methods_search.py
git add src/local_library/daemon/methods.py tests/unit/daemon/test_methods_search.py
git commit -m "feat(daemon): search method handler with hook semantics

Validates query/mode/limit, raises NOT_IMPLEMENTED for non-null doc_id
(loud-error hook), silently ignores boost_citekeys (silent-inert hook),
projects SearchResult + joined Document to the design's RPC wire shape.
Splits the Document.authors string on semicolons; rerank_score mirrors
score when reranking is on (preserving pre-rerank score is a deferred
Library enhancement)."
```
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
## Task 4: `get_document` method handler + dispatcher wiring + integration test

**Type:** Functionality.

**Files:**
- Modify: `src/local_library/daemon/methods.py` (append `get_document`)
- Create: `tests/unit/daemon/test_methods_get_document.py`
- Modify: `src/local_library/daemon/server.py` (extend `build_dispatcher`)
- Create: `tests/integration/daemon/__init__.py`
- Create: `tests/integration/daemon/test_methods.py`

### Step 1: Write failing unit tests for `get_document`

`tests/unit/daemon/test_methods_get_document.py`:

```python
"""Tests for the daemon's get_document method handler."""

import asyncio
from unittest.mock import MagicMock
from uuid import UUID

import pytest

from local_library.core.errors import ErrorCode, LookupError as LibLookupError
from local_library.daemon import methods, protocol


def _fake_doc() -> MagicMock:
    doc = MagicMock()
    doc.id = UUID("00000000-0000-0000-0000-000000000001")
    doc.citekey = "Smith2023"
    doc.title = "A Paper"
    doc.authors = "Smith, J."
    doc.issued_year = 2023
    doc.extracted_path = "/tmp/foo.md"
    doc.csl_json = {"id": "Smith2023", "title": "A Paper", "issued": {"date-parts": [[2023]]}}
    doc.status = MagicMock()
    doc.status.value = "READY"
    return doc


def _fake_library_with(doc: MagicMock, chunk_count: int = 12) -> MagicMock:
    library = MagicMock()
    library.get.return_value = doc
    library.get_by_citekey.return_value = doc
    library.get_chunk_count.return_value = chunk_count
    return library


def _run(value):
    # Handlers are now plain sync functions; this shim stays for symmetry
    # with prior test code and so adding `async` later doesn't churn callers.
    return value


def test_get_document_happy_path() -> None:
    library = _fake_library_with(_fake_doc(), chunk_count=12)
    result = _run(methods.get_document(library=library, identifier="00000000-0000-0000-0000-000000000001"))
    assert result["doc_id"] == "00000000-0000-0000-0000-000000000001"
    assert result["citekey"] == "Smith2023"
    assert result["csl_json"] == {
        "id": "Smith2023",
        "title": "A Paper",
        "issued": {"date-parts": [[2023]]},
    }
    assert result["title"] == "A Paper"
    assert result["authors"] == ["Smith, J."]
    assert result["year"] == 2023
    assert result["extracted_markdown_path"] == "/tmp/foo.md"
    assert result["chunk_count"] == 12
    assert result["status"] == "READY"


def test_get_document_resolves_citekey() -> None:
    library = _fake_library_with(_fake_doc())
    result = _run(methods.get_document(library=library, identifier="@Smith2023"))
    library.get_by_citekey.assert_called_with("Smith2023")
    assert result["doc_id"] == "00000000-0000-0000-0000-000000000001"


def test_get_document_propagates_not_found() -> None:
    library = MagicMock()
    library.get.side_effect = LibLookupError(
        "no such document",
        ErrorCode.NOT_FOUND,
        details={"identifier": "00000000-0000-0000-0000-deadbeefdead"},
    )
    library.get_chunk_count.return_value = 0
    from local_library.core.errors import LocalLibraryError

    with pytest.raises(LocalLibraryError) as exc_info:
        _run(methods.get_document(library=library, identifier="00000000-0000-0000-0000-deadbeefdead"))
    assert exc_info.value.code == ErrorCode.NOT_FOUND


def test_get_document_empty_identifier_raises_invalid_params() -> None:
    library = MagicMock()
    with pytest.raises(protocol.InvalidParams):
        _run(methods.get_document(library=library, identifier=""))


def test_get_document_csl_json_none_serializes_to_empty_object() -> None:
    doc = _fake_doc()
    doc.csl_json = None
    library = _fake_library_with(doc)
    result = _run(methods.get_document(library=library, identifier="00000000-0000-0000-0000-000000000001"))
    assert result["csl_json"] == {}


def test_get_document_chunk_count_via_library_method() -> None:
    """chunk_count comes from Library.get_chunk_count, not from the Document."""
    library = _fake_library_with(_fake_doc(), chunk_count=42)
    result = _run(methods.get_document(library=library, identifier="00000000-0000-0000-0000-000000000001"))
    assert result["chunk_count"] == 42
    library.get_chunk_count.assert_called_with(UUID("00000000-0000-0000-0000-000000000001"))
```

### Step 2: Implement `get_document`

Append to `src/local_library/daemon/methods.py`:

```python
def get_document(
    *,
    library: "Library",
    identifier: str,
) -> dict[str, Any]:
    """Return full metadata for a document, including its CSL-JSON entry.

    The plugin uses this to populate the bibliography auto-append on insert.
    Identifier is either a UUID (full) or '@citekey'.
    """
    if not identifier or not identifier.strip():
        raise protocol.InvalidParams("'identifier' must be a non-empty string")

    if identifier.startswith("@"):
        doc = library.get_by_citekey(identifier[1:])
    else:
        doc = library.get(identifier)

    return _serialize_document(library, doc)


def _serialize_document(library: "Library", doc: "Document") -> dict[str, Any]:
    # chunk_count lives on Library (Library.get_chunk_count), not on the
    # Document dataclass. Best-effort: 0 if the call fails (e.g., document
    # has not been embedded yet).
    try:
        chunk_count = int(library.get_chunk_count(doc.id))
    except Exception:  # noqa: BLE001 — degrade gracefully on any storage failure
        chunk_count = 0
    return {
        "doc_id": str(doc.id),
        "citekey": doc.citekey or "",
        "csl_json": doc.csl_json or {},
        "title": doc.title or "",
        "authors": _split_authors(doc.authors),
        "year": doc.issued_year,
        "extracted_markdown_path": doc.extracted_path or "",
        "chunk_count": chunk_count,
        "status": doc.status.value if hasattr(doc.status, "value") else str(doc.status),
    }
```

### Step 3: Wire methods into the dispatcher

Modify `build_dispatcher()` in `src/local_library/daemon/server.py`:

```python
def build_dispatcher() -> dispatcher_mod.Dispatcher:
    """Return a Dispatcher with all daemon methods registered."""
    from local_library.daemon import methods as method_handlers

    d = dispatcher_mod.Dispatcher()
    d.register("ping", _ping_handler)

    async def search_via_executor(**params: Any) -> Any:
        if _library is None or _library_executor is None:
            raise protocol.InternalError("library not initialized")
        return await run_on_library_thread(
            _library_executor,
            method_handlers.search,
            library=_library,
            **params,
        )

    async def get_document_via_executor(**params: Any) -> Any:
        if _library is None or _library_executor is None:
            raise protocol.InternalError("library not initialized")
        return await run_on_library_thread(
            _library_executor,
            method_handlers.get_document,
            library=_library,
            **params,
        )

    d.register("search", search_via_executor)
    d.register("get_document", get_document_via_executor)
    return d
```

**Note on `asyncio.run(...)` inside the executor thread:** `asyncio.run` creates a new event loop scoped to the executor thread for the duration of the handler. This is safe — the outer event loop is on the main thread, so we are not nesting two loops on the same thread. The handlers are `async def` only because the `Dispatcher` contract requires async callables; they perform no real `await`s and finish synchronously inside the executor.

### Step 4: Write the integration test

`tests/integration/daemon/__init__.py`: empty.

`tests/integration/daemon/test_methods.py`:

```python
"""Integration tests for daemon methods against a real Library.

Builds a minimal corpus via the existing integration_library fixture, then
exercises the search and get_document handlers exactly as the dispatcher
would (with a real Library, but without going through the socket).
"""

from __future__ import annotations

import asyncio

import pytest

from local_library.core.errors import ErrorCode, LocalLibraryError
from local_library.daemon import methods


@pytest.fixture
def populated_library(integration_library, tmp_path):
    """Add a single tiny document so search has something to find.

    The exact add API may differ from this sketch — consult
    tests/integration/conftest.py and tests/integration/test_search_integration.py
    for the canonical recipe and adjust this fixture accordingly.
    """
    sample = tmp_path / "sample.md"
    sample.write_text(
        "# Sample\n\n"
        "This document discusses retrieval-augmented generation in detail.\n"
        "Specifically, the use of dense embeddings combined with full-text search.\n"
    )
    pytest.importorskip("local_library.embeddings.nomic")
    integration_library.add(sample, metadata={"id": "Sample2026", "title": "Sample"})
    integration_library.embed_all()
    return integration_library


def test_search_returns_results_against_real_corpus(populated_library) -> None:
    result = methods.search(library=populated_library, query="retrieval augmented generation")
    assert result["total_candidates"] >= 1
    first = result["results"][0]
    assert first["citekey"] == "Sample2026"
    assert "retrieval" in first["chunk_text"].lower()
    assert first["extracted_markdown_path"]


def test_get_document_returns_csl_json_against_real_corpus(populated_library) -> None:
    result = methods.get_document(library=populated_library, identifier="@Sample2026")
    assert result["citekey"] == "Sample2026"
    assert result["csl_json"]["id"] == "Sample2026"
    assert result["chunk_count"] >= 1


def test_search_doc_id_hook_not_implemented_against_real_corpus(populated_library) -> None:
    with pytest.raises(LocalLibraryError) as exc_info:
        methods.search(library=populated_library, query="x", doc_id="@Sample2026")
    assert exc_info.value.code == ErrorCode.NOT_IMPLEMENTED


def test_search_boost_citekeys_silently_ignored_against_real_corpus(populated_library) -> None:
    a = methods.search(library=populated_library, query="retrieval")
    b = methods.search(
        library=populated_library,
        query="retrieval",
        boost_citekeys=["Sample2026", "Other2024"],
    )
    assert a == b
```

**Note:** The exact fixture API (`integration_library.add(...)`, `.embed(...)`) may differ from the codebase's actual signatures. Implementer must consult `tests/integration/conftest.py` and an existing integration test before finalizing. Adjust the fixture body to match the canonical recipe; the test intent is what matters.

### Step 5: Run

```bash
uv run pytest tests/unit/daemon/test_methods_get_document.py -v
uv run pytest tests/integration/daemon/ -v
```

Expected: 5 unit tests + 4 integration tests pass.

### Step 6: Run full daemon suite

```bash
uv run pytest tests/unit/daemon/ tests/integration/daemon/ -v
```

### Step 7: Lint + format + commit

```bash
uv run ruff check src/local_library/daemon/ tests/unit/daemon/ tests/integration/daemon/
uv run ruff format src/local_library/daemon/ tests/unit/daemon/ tests/integration/daemon/
git add src/local_library/daemon/methods.py src/local_library/daemon/server.py tests/unit/daemon/test_methods_get_document.py tests/integration/daemon/__init__.py tests/integration/daemon/test_methods.py
git commit -m "feat(daemon): get_document handler + register search/get_document

get_document accepts UUID or @citekey; routes through library.get or
library.get_by_citekey; serializes Document to the wire shape with CSL-JSON,
chunk_count, and status. server.build_dispatcher wraps both handlers so
they run on the library executor — entire validation→retrieve→serialize
call stacks execute on the connection-owning thread. Adds an integration
test against a real-Library populated corpus."
```
<!-- END_TASK_4 -->

<!-- END_SUBCOMPONENT_A -->

<!-- START_TASK_5 -->
## Task 5: End-to-end socket test for `search` and `get_document`

**Type:** Functionality / verification.

**Files:**
- Create: `tests/integration/daemon/test_search_lifecycle.py`

### Step 1: Write the test

`tests/integration/daemon/test_search_lifecycle.py`:

```python
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
import sys
from local_library.core.library import Library
with Library() as lib:
    lib.add(sys.argv[1], metadata={'id': 'Sample2026', 'title': 'Sample'})
    lib.embed_all()
"""


@pytest.fixture
def daemon_with_corpus(tmp_path: Path):
    """Spawn the daemon against a tmp data dir prepopulated with one document."""
    env = os.environ.copy()
    env["XDG_DATA_HOME"] = str(tmp_path / "data")
    env["PYTHONUNBUFFERED"] = "1"

    probe = subprocess.run(
        [sys.executable, "-c",
         "from local_library import config; print(config.get_data_dir())"],
        env=env, capture_output=True, text=True, check=True,
    )
    data_dir = Path(probe.stdout.strip())

    sample = tmp_path / "sample.md"
    sample.write_text("# Sample\n\nThis discusses retrieval-augmented generation.\n")
    setup = subprocess.run(
        [sys.executable, "-c", _SETUP_SCRIPT, str(sample)],
        env=env, capture_output=True, text=True,
    )
    if setup.returncode != 0:
        pytest.skip(f"could not populate test library: {setup.stderr}")

    proc = subprocess.Popen(
        [sys.executable, "-m", "local_library.daemon.server"],
        env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    socket_path = data_dir / "daemon.sock"
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
        {"jsonrpc": "2.0", "id": 1, "method": "search",
         "params": {"query": "retrieval generation", "limit": 5}},
    )
    assert response["id"] == 1
    assert "result" in response, response
    assert response["result"]["total_candidates"] >= 1
    assert response["result"]["reranked"] is True


def test_get_document_via_socket(daemon_with_corpus: dict) -> None:
    response = _rpc(
        daemon_with_corpus["socket_path"],
        {"jsonrpc": "2.0", "id": 2, "method": "get_document",
         "params": {"identifier": "@Sample2026"}},
    )
    assert response["id"] == 2
    assert response["result"]["citekey"] == "Sample2026"
    assert response["result"]["csl_json"]["title"] == "Sample"


def test_search_doc_id_hook_returns_not_implemented_via_socket(
    daemon_with_corpus: dict,
) -> None:
    response = _rpc(
        daemon_with_corpus["socket_path"],
        {"jsonrpc": "2.0", "id": 3, "method": "search",
         "params": {"query": "x", "doc_id": "@Sample2026"}},
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
        _rpc(sock_path, {"jsonrpc": "2.0", "id": 100, "method": "search",
                          "params": {"query": "retrieval"}})
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
```

### Step 2: Run

```bash
uv run pytest tests/integration/daemon/test_search_lifecycle.py -v
```

Expected: 5 tests pass. Cold model load may take 5-15 s on the first fixture invocation; the 30 s deadline accommodates this.

### Step 3: Commit

```bash
git add tests/integration/daemon/test_search_lifecycle.py
git commit -m "test(daemon): end-to-end socket tests for search + get_document

Spawns a daemon against a tmp data dir prepopulated with one document,
issues real RPCs over the UDS, verifies wire shapes for search, get_document,
the doc_id NOT_IMPLEMENTED hook, and method-not-found. Includes a concurrency
assertion: ping must remain responsive while search is in flight on the
single-worker library executor."
```
<!-- END_TASK_5 -->

<!-- START_TASK_6 -->
## Task 6: Warm-latency benchmark + Phase 3 verification

**Type:** Verification (manual benchmark; not a CI assertion).

**Files:**
- Create: `tests/integration/daemon/test_search_latency.py`
- Modify: `pyproject.toml` (register the `daemon_latency` marker)
- Modify: `tests/conftest.py` (add `--run-daemon-latency` flag handler — model on existing `--run-extraction-quality`)

### Step 1: Inspect the existing `--run-extraction-quality` plumbing

Read `tests/conftest.py`. Find the existing `--run-extraction-quality` flag's `pytest_addoption` and `pytest_collection_modifyitems` handlers. Mirror that pattern exactly for `--run-daemon-latency` and a new `daemon_latency` marker.

### Step 2: Register the marker

In `pyproject.toml` `[tool.pytest.ini_options]` `markers = [...]`, append:

```toml
"daemon_latency: Daemon warm-latency benchmark (slow; requires real corpus)",
```

### Step 3: Add the flag handler

In `tests/conftest.py`, alongside the `--run-extraction-quality` plumbing, add:

```python
def pytest_addoption(parser):
    # existing --run-extraction-quality registration above ...
    parser.addoption(
        "--run-daemon-latency",
        action="store_true",
        default=False,
        help="Run the daemon warm-latency benchmark (slow; requires real corpus)",
    )


def pytest_collection_modifyitems(config, items):
    # existing extraction_quality skip plumbing above ...
    if not config.getoption("--run-daemon-latency"):
        skip_marker = pytest.mark.skip(reason="needs --run-daemon-latency")
        for item in items:
            if "daemon_latency" in item.keywords:
                item.add_marker(skip_marker)
```

(Adjust the actual structure to match the existing handler's shape — these are likely additions to existing `pytest_addoption` / `pytest_collection_modifyitems` rather than new functions.)

### Step 4: Write the benchmark

`tests/integration/daemon/test_search_latency.py`:

```python
"""Warm reranked hybrid search latency benchmark.

Skipped by default. Run with:
    uv run pytest tests/integration/daemon/test_search_latency.py --run-daemon-latency

Confirms Phase 3's "Done when":
    Measured warm reranked hybrid search latency on the dev corpus
    confirms p95 ≤ 500 ms.
"""

from __future__ import annotations

import time

import pytest

from local_library.core.library import Library

pytestmark = pytest.mark.daemon_latency


WARM_UP_QUERIES = ["retrieval augmented generation"] * 5
BENCHMARK_QUERIES = [
    "embeddings improve search quality over keyword matching",
    "single-instance daemon prevents concurrent database access",
    "JSON-RPC error codes map to domain error categories",
    "cross-encoder reranking improves NDCG over bi-encoder retrieval",
    "asyncio event loops compose with thread pool executors",
] * 10


def test_warm_reranked_hybrid_p95_under_500ms() -> None:
    with Library(embed_on_add=False) as lib:
        retriever = lib.get_retriever(mode="hybrid", rerank=True)
        for q in WARM_UP_QUERIES:
            retriever.retrieve(query=q, k=10)

        latencies: list[float] = []
        for q in BENCHMARK_QUERIES:
            t0 = time.perf_counter()
            retriever.retrieve(query=q, k=10)
            latencies.append(time.perf_counter() - t0)

        latencies.sort()
        p50 = latencies[len(latencies) // 2]
        p95 = latencies[int(0.95 * len(latencies))]
        p99 = latencies[min(int(0.99 * len(latencies)), len(latencies) - 1)]

        print(f"\n  p50={p50*1000:.1f}ms  p95={p95*1000:.1f}ms  p99={p99*1000:.1f}ms"
              f"  (n={len(latencies)})")

        assert p95 < 1.0, (
            f"warm reranked hybrid p95={p95*1000:.0f}ms exceeds 1s — "
            f"latency target needs revisiting"
        )
        if p95 > 0.5:
            pytest.fail(
                f"p95={p95*1000:.0f}ms exceeds 500ms target. This is the design's "
                f"developer yardstick; investigate before declaring Phase 3 done."
            )
```

### Step 5: Run the benchmark

```bash
uv run pytest tests/integration/daemon/test_search_latency.py --run-daemon-latency -v -s
```

Expected on dev corpus (~20 docs): p95 < 500 ms, test passes. Per-percentile numbers print via `-s`.

If the benchmark fails: do NOT mark Phase 3 done. Per design line 515, the 500 ms target is "a developer yardstick, not a formal SLO; if full-corpus baseline shows different numbers once re-annotation lands, the target is revisited." Investigate first; consult the user before changing the threshold.

### Step 6: Verify all Phase 3 "Done when" criteria

- ✓ Search returns ranked results — `test_search_via_socket_returns_results`
- ✓ `get_document(@citekey)` returns CSL-JSON — `test_get_document_via_socket`
- ✓ `search(doc_id=...)` errors with NOT_IMPLEMENTED — `test_search_doc_id_hook_returns_not_implemented_via_socket`
- ✓ `boost_citekeys` silent-inert — `test_search_boost_citekeys_silently_ignored_against_real_corpus`
- ✓ Warm reranked hybrid p95 ≤ 500 ms — this task's benchmark

### Step 7: Lint + format + commit

```bash
uv run ruff check tests/integration/daemon/test_search_latency.py tests/conftest.py
uv run ruff format tests/integration/daemon/test_search_latency.py tests/conftest.py
git add tests/integration/daemon/test_search_latency.py tests/conftest.py pyproject.toml
git commit -m "test(daemon): warm reranked hybrid search latency benchmark

Opt-in benchmark behind --run-daemon-latency. Confirms Phase 3's
'p95 ≤ 500 ms' yardstick on the dev corpus by running 5 warm-up queries
plus 50 measured retrieve() calls and asserting the 95th percentile
under the threshold."
```
<!-- END_TASK_6 -->

<!-- START_TASK_7 -->
## Task 7: Concepts doc chapters 5–6

**Type:** Documentation.

**Files:**
- Modify: `docs/concepts/daemons.md` (append chapters 5 and 6; update closing line)

### Step 1: Append chapters

Open `docs/concepts/daemons.md`. Replace `*Chapters 5–8 are written in Phases 3, 6, and 7.*` (the closing line from Phase 2) with the content below, ending with `*Chapter 7 is written in Phase 6 (reliability case study); chapter 8 in Phase 7.*`:

```markdown

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

*Chapter 7 is written in Phase 6 (reliability case study); chapter 8 in Phase 7.*
```

### Step 2: Verify chapter count

```bash
grep -c '^## Chapter' docs/concepts/daemons.md
```

Expected: `6`.

### Step 3: Commit

```bash
git add docs/concepts/daemons.md
git commit -m "docs(concepts): add chapters 5-6 of the daemons concepts doc

Chapter 5: asyncio + single-threaded concurrency, why a single-worker
executor that owns the Library is the right resolution to the sqlite-vec
constraint, and what we deliberately give up.
Chapter 6: cross-process error handling, the two-tier transport+domain
error model, why string codes beat numeric ones at our scale, and the
client-vs-operator audience split for envelopes vs logs."
```
<!-- END_TASK_7 -->
