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
