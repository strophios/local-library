# Phase 6: CLI Ask Command

**Goal:** User-facing CLI command with streaming display and JSON output.

**Done when:** `local-library ask "question"` streams an answer with source citations, `--json` produces valid JSON output, `--no-stream` works, `--doc @citekey` scopes correctly, `--model` switches provider, error cases display cleanly, tests pass.

**Note:** Rich `Live` is new to this CLI. The codebase has a documented `Rich + Marker conflict` (see `cli/CLAUDE.md` § Gotchas) where Rich's terminal state conflicts with Marker's multiprocessing. The `ask` command doesn't invoke Marker, so this is unlikely to surface here, but if `Live` causes unexpected terminal behavior during streaming (particularly if `litellm` uses subprocesses internally), investigate Rich terminal state management as a first step.

---

<!-- START_SUBCOMPONENT_A (tasks 1-4) -->
<!-- START_TASK_1 -->
### Task 1: Write tests for ask command

**Files:**
- Create: `tests/unit/test_cli_ask.py`

Tests first — these define the expected CLI behavior before implementation.

**Step 1: Create test file**

```python
"""Tests for CLI ask command."""

# pattern: Imperative Shell

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from typer.testing import CliRunner

from local_library.cli.main import app
from local_library.core.models import RAGResponse
from local_library.embeddings.base import Chunk, SearchResult

runner = CliRunner()


def _make_response(
    question: str = "What is attention?",
    answer: str = "Attention is a mechanism [@Smith2023].",
    citekey: str = "Smith2023",
    title: str = "Attention Paper",
    model: str = "test-model",
) -> RAGResponse:
    """Helper to create a RAGResponse for testing."""
    chunk = Chunk.create(doc_id=uuid4(), chunk_index=0, text="Test text")
    result = SearchResult(
        chunk=chunk,
        score=0.9,
        doc_title=title,
        doc_citekey=citekey,
        search_methods=frozenset({"vector"}),
    )
    return RAGResponse(
        question=question,
        answer=answer,
        context_chunks=(result,),
        model=model,
        retrieval_mode="hybrid",
    )


class TestAskCommand:
    """Tests for the ask CLI command."""

    @patch("local_library.cli.ask.is_vec_available", return_value=False)
    def test_ask_fails_without_vec(self, _mock_vec: MagicMock) -> None:
        """ask should fail gracefully when sqlite-vec is unavailable."""
        result = runner.invoke(app, ["ask", "What is X?"])

        assert result.exit_code == 1
        assert "sqlite-vec" in result.output.lower() or "sqlite-vec" in (result.stderr or "")

    @patch("local_library.cli.ask.is_vec_available", return_value=True)
    @patch("local_library.cli.ask.Library")
    def test_ask_no_stream_returns_answer(
        self, mock_lib_cls: MagicMock, _mock_vec: MagicMock
    ) -> None:
        """ask --no-stream should print the answer text and sources."""
        response = _make_response()
        mock_lib = MagicMock()
        mock_lib.__enter__ = MagicMock(return_value=mock_lib)
        mock_lib.__exit__ = MagicMock(return_value=False)
        mock_lib.query.return_value = response
        mock_lib_cls.return_value = mock_lib

        result = runner.invoke(app, ["ask", "What is attention?", "--no-stream"])

        assert result.exit_code == 0
        assert "Attention is a mechanism" in result.output
        assert "Smith2023" in result.output

    @patch("local_library.cli.ask.is_vec_available", return_value=True)
    @patch("local_library.cli.ask.Library")
    def test_ask_json_output(
        self, mock_lib_cls: MagicMock, _mock_vec: MagicMock
    ) -> None:
        """ask --json should produce valid JSON with expected fields."""
        import json

        response = _make_response()
        mock_lib = MagicMock()
        mock_lib.__enter__ = MagicMock(return_value=mock_lib)
        mock_lib.__exit__ = MagicMock(return_value=False)
        mock_lib.query.return_value = response
        mock_lib_cls.return_value = mock_lib

        result = runner.invoke(app, ["ask", "What is attention?", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["question"] == "What is attention?"
        assert "Attention is a mechanism" in data["answer"]
        assert data["model"] == "test-model"
        assert data["retrieval_mode"] == "hybrid"
        assert len(data["sources"]) == 1
        assert data["sources"][0]["citekey"] == "Smith2023"

    @patch("local_library.cli.ask.is_vec_available", return_value=True)
    @patch("local_library.cli.ask.Library")
    def test_ask_passes_model_flag(
        self, mock_lib_cls: MagicMock, _mock_vec: MagicMock
    ) -> None:
        """ask --model should pass model to Library constructor."""
        response = _make_response()
        mock_lib = MagicMock()
        mock_lib.__enter__ = MagicMock(return_value=mock_lib)
        mock_lib.__exit__ = MagicMock(return_value=False)
        mock_lib.query.return_value = response
        mock_lib_cls.return_value = mock_lib

        runner.invoke(
            app, ["ask", "Q?", "--model", "anthropic/claude-3-haiku", "--no-stream"]
        )

        mock_lib_cls.assert_called_once()
        call_kwargs = mock_lib_cls.call_args[1]
        assert call_kwargs["rag_model"] == "anthropic/claude-3-haiku"

    @patch("local_library.cli.ask.is_vec_available", return_value=True)
    @patch("local_library.cli.ask.Library")
    def test_ask_passes_mode_flag(
        self, mock_lib_cls: MagicMock, _mock_vec: MagicMock
    ) -> None:
        """ask --mode should pass retrieval mode to query."""
        response = _make_response()
        mock_lib = MagicMock()
        mock_lib.__enter__ = MagicMock(return_value=mock_lib)
        mock_lib.__exit__ = MagicMock(return_value=False)
        mock_lib.query.return_value = response
        mock_lib_cls.return_value = mock_lib

        runner.invoke(app, ["ask", "Q?", "--mode", "fts", "--no-stream"])

        mock_lib.query.assert_called_once()
        call_kwargs = mock_lib.query.call_args[1]
        assert call_kwargs["mode"] == "fts"

    @patch("local_library.cli.ask.is_vec_available", return_value=True)
    @patch("local_library.cli.ask.Library")
    def test_ask_passes_limit_flag(
        self, mock_lib_cls: MagicMock, _mock_vec: MagicMock
    ) -> None:
        """ask --limit should pass limit to query."""
        response = _make_response()
        mock_lib = MagicMock()
        mock_lib.__enter__ = MagicMock(return_value=mock_lib)
        mock_lib.__exit__ = MagicMock(return_value=False)
        mock_lib.query.return_value = response
        mock_lib_cls.return_value = mock_lib

        runner.invoke(app, ["ask", "Q?", "--limit", "5", "--no-stream"])

        mock_lib.query.assert_called_once()
        call_kwargs = mock_lib.query.call_args[1]
        assert call_kwargs["limit"] == 5

    @patch("local_library.cli.ask.is_vec_available", return_value=True)
    @patch("local_library.cli.ask.Library")
    @patch("local_library.cli.ask.resolve_identifier")
    def test_ask_doc_flag_scopes_to_document(
        self,
        mock_resolve: MagicMock,
        mock_lib_cls: MagicMock,
        _mock_vec: MagicMock,
    ) -> None:
        """ask --doc should resolve identifier and pass doc_ids to query."""
        doc_id = uuid4()
        mock_doc = MagicMock()
        mock_doc.id = doc_id
        mock_resolve.return_value = mock_doc

        response = _make_response()
        mock_lib = MagicMock()
        mock_lib.__enter__ = MagicMock(return_value=mock_lib)
        mock_lib.__exit__ = MagicMock(return_value=False)
        mock_lib.query.return_value = response
        mock_lib_cls.return_value = mock_lib

        runner.invoke(app, ["ask", "Q?", "--doc", "@Smith2023", "--no-stream"])

        mock_resolve.assert_called_once_with("@Smith2023", mock_lib)
        call_kwargs = mock_lib.query.call_args[1]
        assert call_kwargs["doc_ids"] == [doc_id]

    def test_ask_invalid_mode(self) -> None:
        """ask with invalid mode should fail."""
        with patch("local_library.cli.ask.is_vec_available", return_value=True):
            result = runner.invoke(app, ["ask", "Q?", "--mode", "invalid"])

        assert result.exit_code == 1

    @patch("local_library.cli.ask.is_vec_available", return_value=True)
    @patch("local_library.cli.ask.Library")
    def test_ask_empty_context_shows_message(
        self, mock_lib_cls: MagicMock, _mock_vec: MagicMock
    ) -> None:
        """ask with no relevant docs should show appropriate message."""
        response = RAGResponse(
            question="Q?",
            answer="I don't have relevant context to answer this question.",
            context_chunks=(),
            model="test-model",
            retrieval_mode="hybrid",
        )
        mock_lib = MagicMock()
        mock_lib.__enter__ = MagicMock(return_value=mock_lib)
        mock_lib.__exit__ = MagicMock(return_value=False)
        mock_lib.query.return_value = response
        mock_lib_cls.return_value = mock_lib

        result = runner.invoke(app, ["ask", "Q?", "--no-stream"])

        assert result.exit_code == 0
        assert "don't have relevant context" in result.output.lower() or "no relevant" in result.output.lower()

    @patch("local_library.cli.ask.is_vec_available", return_value=True)
    @patch("local_library.cli.ask.Library")
    def test_ask_json_with_empty_sources(
        self, mock_lib_cls: MagicMock, _mock_vec: MagicMock
    ) -> None:
        """ask --json with empty context should produce valid JSON with empty sources."""
        import json

        response = RAGResponse(
            question="Q?",
            answer="No context available.",
            context_chunks=(),
            model="test-model",
            retrieval_mode="hybrid",
        )
        mock_lib = MagicMock()
        mock_lib.__enter__ = MagicMock(return_value=mock_lib)
        mock_lib.__exit__ = MagicMock(return_value=False)
        mock_lib.query.return_value = response
        mock_lib_cls.return_value = mock_lib

        result = runner.invoke(app, ["ask", "Q?", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["sources"] == []

    @patch("local_library.cli.ask.is_vec_available", return_value=True)
    @patch("local_library.cli.ask.Library")
    def test_ask_streaming_calls_query_stream(
        self, mock_lib_cls: MagicMock, _mock_vec: MagicMock
    ) -> None:
        """Default ask (streaming) should call query_stream and iterate tokens."""
        from local_library.rag.interface import RAGStream

        response = _make_response()
        mock_lib = MagicMock()
        mock_lib.__enter__ = MagicMock(return_value=mock_lib)
        mock_lib.__exit__ = MagicMock(return_value=False)

        # Create a mock stream that yields tokens and returns response
        mock_stream = MagicMock(spec=RAGStream)
        mock_stream.__iter__ = MagicMock(return_value=iter(["Hello", " world"]))
        mock_stream.to_response.return_value = response
        mock_lib.query_stream.return_value = mock_stream
        mock_lib_cls.return_value = mock_lib

        result = runner.invoke(app, ["ask", "What is X?"])

        # Should have called query_stream (not query)
        mock_lib.query_stream.assert_called_once()
        mock_lib.query.assert_not_called()
        mock_stream.to_response.assert_called_once()

    @patch("local_library.cli.ask.is_vec_available", return_value=True)
    @patch("local_library.cli.ask.Library")
    def test_ask_rag_error_displays_cleanly(
        self, mock_lib_cls: MagicMock, _mock_vec: MagicMock
    ) -> None:
        """ask should display RAGError cleanly and exit 1."""
        from local_library.core.errors import RAGError

        mock_lib = MagicMock()
        mock_lib.__enter__ = MagicMock(return_value=mock_lib)
        mock_lib.__exit__ = MagicMock(return_value=False)
        mock_lib.query.side_effect = RAGError("generation failed")
        mock_lib_cls.return_value = mock_lib

        result = runner.invoke(app, ["ask", "Q?", "--no-stream"])

        assert result.exit_code == 1

    @patch("local_library.cli.ask.is_vec_available", return_value=True)
    @patch("local_library.cli.ask.Library")
    def test_ask_llm_error_displays_cleanly(
        self, mock_lib_cls: MagicMock, _mock_vec: MagicMock
    ) -> None:
        """ask should display LLMError cleanly and exit 1."""
        from local_library.core.errors import LLMError

        mock_lib = MagicMock()
        mock_lib.__enter__ = MagicMock(return_value=mock_lib)
        mock_lib.__exit__ = MagicMock(return_value=False)
        mock_lib.query.side_effect = LLMError("model not found")
        mock_lib_cls.return_value = mock_lib

        result = runner.invoke(app, ["ask", "Q?", "--no-stream"])

        assert result.exit_code == 1

    @patch("local_library.cli.ask.is_vec_available", return_value=True)
    @patch("local_library.cli.ask.Library")
    def test_ask_json_error_format(
        self, mock_lib_cls: MagicMock, _mock_vec: MagicMock
    ) -> None:
        """ask --json errors should produce JSON error output."""
        import json

        from local_library.core.errors import RAGError

        mock_lib = MagicMock()
        mock_lib.__enter__ = MagicMock(return_value=mock_lib)
        mock_lib.__exit__ = MagicMock(return_value=False)
        mock_lib.query.side_effect = RAGError("generation failed")
        mock_lib_cls.return_value = mock_lib

        result = runner.invoke(app, ["ask", "Q?", "--json"])

        assert result.exit_code == 1
```

Note: Rich `Live` streaming display rendering cannot be fully verified via `CliRunner` (terminal state is not captured). The `test_ask_streaming_calls_query_stream` test verifies the control flow (correct method called, tokens iterated, `to_response()` invoked). Visual rendering of streaming output should be verified manually during integration testing.

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_cli_ask.py -v`
Expected: FAIL — `ask` module doesn't exist, command not registered
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Create ask command module

**Files:**
- Create: `src/local_library/cli/ask.py`

**Step 1: Create the ask command file**

```python
"""Ask command - query the library using RAG."""

# pattern: Imperative Shell

import json
from typing import Annotated
from uuid import UUID

import typer
from rich.console import Console
from rich.live import Live
from rich.text import Text

from local_library.cli.utils import resolve_identifier
from local_library.core import Library
from local_library.core.errors import EmbeddingError, LLMError, LookupError, RAGError
from local_library.core.models import RAGResponse
from local_library.core.vec_extension import is_vec_available

console = Console()
err_console = Console(stderr=True)

VALID_MODES = ("hybrid", "vector", "fts")


def ask(
    question: Annotated[
        str,
        typer.Argument(help="Question to ask about your library"),
    ],
    model: Annotated[
        str | None,
        typer.Option("--model", help="LLM model for answer generation"),
    ] = None,
    mode: Annotated[
        str,
        typer.Option("--mode", "-m", help="Retrieval mode: hybrid, vector, or fts"),
    ] = "hybrid",
    limit: Annotated[
        int,
        typer.Option("--limit", "-n", help="Maximum number of context chunks"),
    ] = 10,
    doc_id: Annotated[
        str | None,
        typer.Option("--doc", "-d", help="Scope to a document (UUID or @citekey)"),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", "-j", help="Output as JSON (implies --no-stream)"),
    ] = False,
    no_stream: Annotated[
        bool,
        typer.Option("--no-stream", help="Disable streaming (wait for full answer)"),
    ] = False,
) -> None:
    """Ask a question and get a RAG-generated answer from your library.

    Retrieves relevant document chunks and generates an answer with source
    citations. By default, the answer streams token-by-token.

    Examples:

        # Basic question
        local-library ask "What is attention in transformers?"

        # Use a specific model
        local-library ask "Summarize the findings" --model anthropic/claude-3-haiku

        # Search only within a specific document
        local-library ask "What methods were used?" --doc @Smith2023

        # Get structured JSON output
        local-library ask "What are the key results?" --json
    """
    if not is_vec_available():
        if json_output:
            err_console.print(json.dumps({"error": "sqlite-vec extension not available"}))
        else:
            err_console.print("[red]error:[/red] sqlite-vec extension not available")
            err_console.print("[dim]Install sqlite-vec to enable ask features[/dim]")
        raise typer.Exit(code=1)

    if mode not in VALID_MODES:
        if json_output:
            err_console.print(
                json.dumps({"error": f"invalid mode: {mode} (expected hybrid, vector, or fts)"})
            )
        else:
            err_console.print(
                f"[red]error:[/red] invalid mode: {mode} (expected hybrid, vector, or fts)"
            )
        raise typer.Exit(code=1)

    # JSON implies no-stream (must collect full response for structured output)
    if json_output:
        no_stream = True

    lib_kwargs: dict = {"embed_on_add": False}
    if model:
        lib_kwargs["rag_model"] = model

    try:
        with Library(**lib_kwargs) as lib:
            # Resolve document scope if provided
            doc_ids: list[UUID] | None = None
            if doc_id:
                doc = resolve_identifier(doc_id, lib)
                doc_ids = [doc.id]

            if no_stream:
                response = lib.query(
                    question, mode=mode, limit=limit, doc_ids=doc_ids,
                )
                if json_output:
                    _output_json(response)
                else:
                    _output_answer(response)
            else:
                _stream_answer(lib, question, mode=mode, limit=limit, doc_ids=doc_ids)

    except LookupError as e:
        if json_output:
            err_console.print(json.dumps({"error": e.message, "code": e.code.value}))
        else:
            err_console.print(f"[red]error:[/red] {e.message}")
        raise typer.Exit(code=1) from None
    except EmbeddingError as e:
        if json_output:
            err_console.print(json.dumps({"error": e.message, "code": e.code.value}))
        else:
            err_console.print(f"[red]error:[/red] {e.message}")
        raise typer.Exit(code=1) from None
    except (RAGError, LLMError) as e:
        if json_output:
            err_console.print(json.dumps({"error": e.message, "code": e.code.value}))
        else:
            err_console.print(f"[red]error:[/red] {e.message}")
        raise typer.Exit(code=1) from None
    except KeyboardInterrupt:
        err_console.print("\n[dim]interrupted[/dim]")
        raise typer.Exit(code=130) from None


def _stream_answer(
    lib: Library,
    question: str,
    mode: str,
    limit: int,
    doc_ids: list[UUID] | None,
) -> None:
    """Stream answer tokens with Rich Live display."""
    console.print("[dim]Searching...[/dim]")

    stream = lib.query_stream(question, mode=mode, limit=limit, doc_ids=doc_ids)

    accumulated = ""
    try:
        with Live(Text(""), console=console, refresh_per_second=10) as live:
            for token in stream:
                accumulated += token
                live.update(Text(accumulated))
    except KeyboardInterrupt:
        # Graceful Ctrl+C: show what we have so far
        if accumulated:
            console.print(Text(accumulated))
        err_console.print("\n[dim]interrupted[/dim]")
        raise typer.Exit(code=130) from None

    # Print final answer (Live clears on exit)
    console.print()
    console.print(accumulated)

    # Sources footer
    response = stream.to_response()
    _print_sources(response)


def _output_answer(response: RAGResponse) -> None:
    """Print non-streaming answer with sources footer."""
    console.print(response.answer)
    _print_sources(response)


def _print_sources(response: RAGResponse) -> None:
    """Print sources footer from RAGResponse."""
    if not response.context_chunks:
        return

    # Deduplicate by citekey, preserving order
    seen: dict[str | None, str | None] = {}
    for chunk in response.context_chunks:
        key = chunk.doc_citekey
        if key not in seen:
            seen[key] = chunk.doc_title

    console.print()
    console.print("[bold]Sources:[/bold]")
    for citekey, title in seen.items():
        label = f"[@{citekey}]" if citekey else "[unknown source]"
        title_str = f'  "{title}"' if title else ""
        console.print(f"  {label}{title_str}")


def _output_json(response: RAGResponse) -> None:
    """Output RAGResponse as JSON."""
    # Aggregate sources: deduplicate by citekey, count chunks per source
    source_map: dict[str | None, dict] = {}
    for chunk in response.context_chunks:
        key = chunk.doc_citekey
        if key not in source_map:
            source_map[key] = {
                "citekey": key,
                "title": chunk.doc_title,
                "doc_id": str(chunk.chunk.doc_id),
                "chunks_used": 0,
            }
        source_map[key]["chunks_used"] += 1

    output = {
        "question": response.question,
        "answer": response.answer,
        "model": response.model,
        "retrieval_mode": response.retrieval_mode,
        "sources": list(source_map.values()),
    }
    console.print(json.dumps(output, indent=2))
```

**Step 2: Verify linting**

Run: `uv run ruff check src/local_library/cli/ask.py`
Expected: No errors
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Register command and run tests

**Files:**
- Modify: `src/local_library/cli/main.py`

**Step 1: Add import**

At line 7, after `from local_library.cli import add as add_cmd`, add:
```python
from local_library.cli import ask as ask_cmd
```

**Step 2: Register the command**

At line 35 (after `app.command(name="search")(search_cmd.search)`), add:
```python
app.command(name="ask")(ask_cmd.ask)
```

**Step 3: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_cli_ask.py -v`
Expected: All 14 tests PASS

**Step 4: Verify linting**

Run: `uv run ruff check src/local_library/cli/ask.py src/local_library/cli/main.py`
Expected: No errors
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Verify full test suite and commit

**Step 1: Run full test suite**

Run: `uv run pytest -x -q`
Expected: All tests pass

**Step 2: Verify linting**

Run: `uv run ruff check src/local_library/cli/`
Expected: No errors

**Step 3: Commit**

```bash
git add src/local_library/cli/ask.py src/local_library/cli/main.py tests/unit/test_cli_ask.py
git commit -m "feat(cli): add ask command for RAG queries

Add CLI ask command with streaming display (Rich Live), non-streaming
mode, and JSON output. Supports --model, --mode, --limit, --doc, --json,
and --no-stream flags.

Streaming displays tokens via Rich Live with graceful Ctrl+C handling.
JSON output aggregates sources with chunk counts per document.
Sources footer deduplicates by citekey."
```
<!-- END_TASK_4 -->
<!-- END_SUBCOMPONENT_A -->
