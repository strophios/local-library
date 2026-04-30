"""Tests for the daemon's Library-on-executor lifecycle."""

import asyncio
import threading
from unittest.mock import MagicMock, patch

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


def test_construct_library_skips_warmup_when_env_set(monkeypatch) -> None:
    """LOCAL_LIBRARY_DAEMON_SKIP_WARMUP=1 disables warmup at startup.

    Used by integration tests that spawn ephemeral daemons and would
    otherwise pay (and time out on) the model-load cost.
    """
    monkeypatch.setenv("LOCAL_LIBRARY_DAEMON_SKIP_WARMUP", "1")
    with patch("local_library.core.library.Library") as mock_library_cls:
        mock_lib = MagicMock()
        mock_library_cls.return_value = mock_lib

        result = server._construct_library()

        mock_library_cls.assert_called_once_with(embed_on_add=False)
        mock_lib.__enter__.assert_called_once()
        # Warmup must NOT run when the env var is set.
        mock_lib.warmup.assert_not_called()
        assert result is mock_lib


def test_construct_library_warms_up_models() -> None:
    """The startup helper must call warmup() so the first request is warm.

    Plugin clients see sub-5s timeouts on `search`; the cold load of
    nomic + cross-encoder models exceeds that. Warming during daemon
    startup moves the cost off the request path.
    """
    with patch("local_library.core.library.Library") as mock_library_cls:
        mock_lib = MagicMock()
        mock_library_cls.return_value = mock_lib

        result = server._construct_library()

        # Library constructed with embed_on_add=False (the daemon does not
        # ingest documents).
        mock_library_cls.assert_called_once_with(embed_on_add=False)
        # Lifecycle and warmup invoked in order.
        mock_lib.__enter__.assert_called_once()
        mock_lib.warmup.assert_called_once()
        assert result is mock_lib
