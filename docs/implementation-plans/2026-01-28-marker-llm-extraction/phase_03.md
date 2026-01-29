## Phase 3: CLI Integration and Validation

This phase adds the `--llm-extract` flag to the add command and implements early API key validation with warning output for both `--llm` and `--llm-extract` flags.

**Key insight:** The design calls for "early validation" - checking GEMINI_API_KEY at the CLI layer before Library instantiation. If the key is missing but LLM features were requested, we warn and disable them (graceful degradation).

---

<!-- START_TASK_1 -->
### Task 1: Add --llm-extract flag to add command

**Files:**
- Modify: `src/local_library/cli/add.py:41-58` (add new option)

**Step 1: Add the --llm-extract option**

Open `src/local_library/cli/add.py` and add the new option after `llm_model`. Insert after line 54:

```python
llm_extract: Annotated[
    bool,
    typer.Option(
        "--llm-extract",
        help="Use Marker's LLM-enhanced PDF extraction (better tables, math, images). Requires GEMINI_API_KEY.",
    ),
] = False,
```

The updated function signature (parameters section) should now be:

```python
def add(
    path: Annotated[Path, typer.Argument(help="Path to the document file")],
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Create failed record for inaccessible files"),
    ] = False,
    metadata_path: Annotated[
        Path | None,
        typer.Option(
            "--metadata",
            "-m",
            help="Path to CSL-JSON metadata file",
            exists=True,
            dir_okay=False,
            readable=True,
        ),
    ] = None,
    llm: Annotated[
        bool,
        typer.Option(
            "--llm",
            help="Use LLM fallback for low-confidence metadata extraction",
        ),
    ] = False,
    llm_model: Annotated[
        str,
        typer.Option(
            "--llm-model",
            help="LLM model for fallback (default: gemini-2.0-flash)",
        ),
    ] = "gemini/gemini-2.0-flash",
    llm_extract: Annotated[
        bool,
        typer.Option(
            "--llm-extract",
            help="Use Marker's LLM-enhanced PDF extraction (better tables, math, images). Requires GEMINI_API_KEY.",
        ),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", "-j", help="Output result as JSON"),
    ] = False,
) -> None:
```

**Step 2: Verify the CLI accepts the new flag**

Run: `uv run local-library add --help`

Expected: `--llm-extract` should appear in the help output with its description

**Step 3: Commit**

```bash
git add src/local_library/cli/add.py
git commit -m "$(cat <<'EOF'
feat(cli): add --llm-extract flag to add command

Flag for enabling Marker's LLM-enhanced PDF extraction.
Parameter accepted but not yet passed to Library or validated.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Implement check_api_key_available helper function

**Files:**
- Modify: `src/local_library/cli/add.py` (add import and helper function)

**Step 1: Add os import at top of file**

Update the imports at the top of the file to include `os`:

```python
"""Add command - add documents to the library."""

# pattern: Imperative Shell

import json
import os
from pathlib import Path
from typing import Annotated
```

**Step 2: Add the helper function after the console declarations**

After line 22 (after `err_console = Console(stderr=True)`), add:

```python

def check_api_key_available(
    env_var: str,
    feature_name: str,
    json_output: bool,
) -> bool:
    """Check if an API key environment variable is available.

    Args:
        env_var: Name of the environment variable to check
        feature_name: Human-readable name of the feature (for warning message)
        json_output: Whether to format warning as JSON

    Returns:
        True if the key is available, False otherwise (with warning output)
    """
    if os.environ.get(env_var):
        return True

    if json_output:
        err_console.print(
            json.dumps({
                "warning": f"{env_var} not set, {feature_name} disabled",
            })
        )
    else:
        err_console.print(
            f"[yellow]warning:[/yellow] {env_var} not set, {feature_name} disabled"
        )
    return False
```

**Step 3: Verify syntax**

Run: `uv run python -c "from local_library.cli.add import check_api_key_available; print('OK')"`

Expected: `OK`

**Step 4: Commit**

```bash
git add src/local_library/cli/add.py
git commit -m "$(cat <<'EOF'
feat(cli): add check_api_key_available helper function

Helper for early API key validation with warning output.
Used to gracefully disable LLM features when keys are missing.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Add early validation and pass pdf_llm_enabled to Library

**Files:**
- Modify: `src/local_library/cli/add.py` (add validation logic and update Library call)

**Step 1: Add early validation before Library instantiation**

Find the section that loads metadata (around line 68-78 after the function signature). After the metadata loading block and before the `try: with Library(...)` block, add the validation logic:

```python
    # Early validation of API keys for LLM features
    effective_llm = llm
    effective_llm_extract = llm_extract

    if llm or llm_extract:
        if not check_api_key_available("GEMINI_API_KEY", "LLM features", json_output):
            effective_llm = False
            effective_llm_extract = False
```

**Step 2: Update the Library instantiation to use effective values and add pdf_llm_enabled**

Find the `with Library(...)` block and update it:

```python
    try:
        with Library(
            text_extraction_llm_enabled=effective_llm,
            text_extraction_llm_model=llm_model,
            pdf_llm_enabled=effective_llm_extract,
        ) as lib:
            result = lib.add(str(path), force=force, metadata=metadata)
```

**Step 3: Verify the complete function works**

Run: `uv run local-library add --help`

Expected: Should show help without errors

Run: `uv run python -c "from local_library.cli.add import add; print('OK')"`

Expected: `OK`

**Step 4: Commit**

```bash
git add src/local_library/cli/add.py
git commit -m "$(cat <<'EOF'
feat(cli): add early API key validation and pass pdf_llm_enabled

- Validates GEMINI_API_KEY before Library instantiation
- Warns and disables LLM features if key missing
- Passes pdf_llm_enabled to Library constructor

Both --llm and --llm-extract now gracefully degrade without API key.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Add tests for --llm-extract flag and API key validation

**Files:**
- Modify: `tests/unit/test_cli.py`

**Step 1: Add test class for LLM extraction CLI behavior**

Add the following test class at the end of the file:

```python
class TestAddCommandLLMExtract:
    """Tests for add command --llm-extract flag."""

    def test_llm_extract_flag_accepted(
        self, mock_library: MagicMock, temp_dir: Path
    ) -> None:
        """add command should accept --llm-extract flag."""
        pdf_path = temp_dir / "test.pdf"
        pdf_path.write_bytes(b"%PDF-1.4")

        mock_doc = MagicMock()
        mock_doc.id = "12345678-1234-1234-1234-123456789abc"
        mock_doc.status = DocumentStatus.READY
        mock_doc.storage_path = "/storage/test.pdf"
        mock_doc.original_path = str(pdf_path)
        mock_doc.content_hash = "abcd1234"
        mock_doc.citekey = None
        mock_doc.title = None
        mock_doc.authors = None
        mock_doc.issued_date = None

        mock_library.add.return_value = AddResult(document=mock_doc)

        result = runner.invoke(app, ["add", "--llm-extract", str(pdf_path)])

        # Should succeed (or warn about missing API key, not error)
        assert result.exit_code == 0

    def test_llm_extract_warns_without_api_key(
        self, mock_library: MagicMock, temp_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """add --llm-extract should warn when GEMINI_API_KEY is missing."""
        # Ensure no API key
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

        pdf_path = temp_dir / "test.pdf"
        pdf_path.write_bytes(b"%PDF-1.4")

        mock_doc = MagicMock()
        mock_doc.id = "12345678-1234-1234-1234-123456789abc"
        mock_doc.status = DocumentStatus.READY
        mock_doc.storage_path = "/storage/test.pdf"
        mock_doc.original_path = str(pdf_path)
        mock_doc.content_hash = "abcd1234"
        mock_doc.citekey = None
        mock_doc.title = None
        mock_doc.authors = None
        mock_doc.issued_date = None

        mock_library.add.return_value = AddResult(document=mock_doc)

        result = runner.invoke(app, ["add", "--llm-extract", str(pdf_path)])

        assert result.exit_code == 0
        # Warning should be in stderr, but CliRunner captures both
        assert "GEMINI_API_KEY" in result.output or "warning" in result.output.lower()

    def test_llm_extract_no_warning_with_api_key(
        self, mock_library: MagicMock, temp_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """add --llm-extract should not warn when GEMINI_API_KEY is present."""
        monkeypatch.setenv("GEMINI_API_KEY", "test-api-key")

        pdf_path = temp_dir / "test.pdf"
        pdf_path.write_bytes(b"%PDF-1.4")

        mock_doc = MagicMock()
        mock_doc.id = "12345678-1234-1234-1234-123456789abc"
        mock_doc.status = DocumentStatus.READY
        mock_doc.storage_path = "/storage/test.pdf"
        mock_doc.original_path = str(pdf_path)
        mock_doc.content_hash = "abcd1234"
        mock_doc.citekey = None
        mock_doc.title = None
        mock_doc.authors = None
        mock_doc.issued_date = None

        mock_library.add.return_value = AddResult(document=mock_doc)

        result = runner.invoke(app, ["add", "--llm-extract", str(pdf_path)])

        assert result.exit_code == 0
        # Should not contain warning about missing key
        assert "GEMINI_API_KEY not set" not in result.output

    def test_llm_flag_warns_without_api_key(
        self, mock_library: MagicMock, temp_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """add --llm should warn when GEMINI_API_KEY is missing."""
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

        pdf_path = temp_dir / "test.pdf"
        pdf_path.write_bytes(b"%PDF-1.4")

        mock_doc = MagicMock()
        mock_doc.id = "12345678-1234-1234-1234-123456789abc"
        mock_doc.status = DocumentStatus.READY
        mock_doc.storage_path = "/storage/test.pdf"
        mock_doc.original_path = str(pdf_path)
        mock_doc.content_hash = "abcd1234"
        mock_doc.citekey = None
        mock_doc.title = None
        mock_doc.authors = None
        mock_doc.issued_date = None

        mock_library.add.return_value = AddResult(document=mock_doc)

        result = runner.invoke(app, ["add", "--llm", str(pdf_path)])

        assert result.exit_code == 0
        assert "GEMINI_API_KEY" in result.output or "warning" in result.output.lower()

    def test_llm_extract_json_warning_format(
        self, mock_library: MagicMock, temp_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """add --llm-extract --json should output JSON-formatted warning."""
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)

        pdf_path = temp_dir / "test.pdf"
        pdf_path.write_bytes(b"%PDF-1.4")

        mock_doc = MagicMock()
        mock_doc.id = "12345678-1234-1234-1234-123456789abc"
        mock_doc.status = DocumentStatus.READY
        mock_doc.storage_path = "/storage/test.pdf"
        mock_doc.original_path = str(pdf_path)
        mock_doc.content_hash = "abcd1234"
        mock_doc.citekey = None
        mock_doc.title = None
        mock_doc.authors = None
        mock_doc.issued_date = None

        mock_library.add.return_value = AddResult(document=mock_doc)

        result = runner.invoke(app, ["add", "--llm-extract", "--json", str(pdf_path)])

        assert result.exit_code == 0
        # Warning should be JSON formatted
        assert '"warning"' in result.output
```

**Step 2: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_cli.py::TestAddCommandLLMExtract -v`

Expected: All 5 tests pass

**Step 3: Commit**

```bash
git add tests/unit/test_cli.py
git commit -m "$(cat <<'EOF'
test(cli): add tests for --llm-extract flag and API key validation

Tests verify:
- --llm-extract flag accepted
- Warning shown when GEMINI_API_KEY missing
- No warning when key is present
- --llm flag also warns when key missing (unified validation)
- JSON output format for warnings

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```
<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Run full test suite and verify no regressions

**Files:**
- None (verification only)

**Step 1: Run ruff check**

Run: `uv run ruff check src/local_library/cli/add.py tests/unit/test_cli.py`

Expected: No linting errors

**Step 2: Run ruff format check**

Run: `uv run ruff format --check src/local_library/cli/add.py tests/unit/test_cli.py`

Expected: No formatting issues (or run `uv run ruff format` to fix)

**Step 3: Run the full unit test suite**

Run: `uv run pytest tests/unit/ -v`

Expected: All tests pass

**Step 4: Commit any formatting fixes if needed**

If ruff format made changes:

```bash
git add -A
git commit -m "$(cat <<'EOF'
style: apply ruff formatting

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```
<!-- END_TASK_5 -->

---

## Phase 3 Completion Checklist

- [ ] `--llm-extract` flag added to add command
- [ ] `check_api_key_available()` helper function implemented
- [ ] Early validation checks GEMINI_API_KEY for both `--llm` and `--llm-extract`
- [ ] Warning output when API key missing (graceful degradation)
- [ ] `pdf_llm_enabled` passed to Library constructor
- [ ] All new tests pass
- [ ] No regressions in existing tests
- [ ] Code passes ruff check and format
