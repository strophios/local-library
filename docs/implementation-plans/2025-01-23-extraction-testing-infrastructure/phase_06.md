# Phase 6: Diagnostic Output and Summary

**Goal:** Provide actionable diagnostic output when tests run.

**Codebase verification findings:**
- ✓ `DocumentResult` dataclass from Phase 4 captures per-document outcomes
- ✓ pytest hooks available: `pytest_sessionfinish`, `pytest_terminal_summary`
- ✓ Design requires: per-document status, field-level diffs, aggregate accuracy

---

<!-- START_TASK_1 -->
### Task 1: Add AccuracyReport dataclass

**Files:**
- Modify: `tests/extraction/conftest.py`

**Step 1: Add AccuracyReport dataclass**

Add to `tests/extraction/conftest.py` (near DocumentResult):

```python


@dataclass
class AccuracyReport:
    """Aggregate accuracy statistics across documents.

    Used for summary reporting at end of test session.

    Attributes:
        total_documents: Total documents in golden set
        extraction_successes: Documents that extracted without error
        title_passes: Documents meeting title threshold
        author_passes: Documents meeting author threshold
        year_passes: Documents with matching year
        results: Individual DocumentResult for each document
    """

    total_documents: int = 0
    extraction_successes: int = 0
    title_passes: int = 0
    author_passes: int = 0
    year_passes: int = 0
    results: list[DocumentResult] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.results is None:
            self.results = []

    @property
    def extraction_rate(self) -> float:
        """Percentage of documents that extracted successfully."""
        if self.total_documents == 0:
            return 0.0
        return self.extraction_successes / self.total_documents

    @property
    def title_accuracy(self) -> float:
        """Percentage of documents meeting title threshold."""
        if self.extraction_successes == 0:
            return 0.0
        return self.title_passes / self.extraction_successes

    @property
    def author_accuracy(self) -> float:
        """Percentage of documents meeting author threshold."""
        if self.extraction_successes == 0:
            return 0.0
        return self.author_passes / self.extraction_successes

    @property
    def year_accuracy(self) -> float:
        """Percentage of documents with matching year."""
        if self.extraction_successes == 0:
            return 0.0
        return self.year_passes / self.extraction_successes

    def add_result(self, result: DocumentResult) -> None:
        """Add a document result and update counts."""
        self.results.append(result)
        self.total_documents += 1

        if result.extraction_success:
            self.extraction_successes += 1
            if result.passed_title():
                self.title_passes += 1
            if result.passed_authors():
                self.author_passes += 1
            if result.passed_year():
                self.year_passes += 1

    def failed_documents(self) -> list[DocumentResult]:
        """Return documents that failed any check."""
        return [r for r in self.results if not r.passed_all()]

    def format_summary(self) -> str:
        """Format a human-readable summary string."""
        lines = [
            "",
            "=" * 70,
            "EXTRACTION ACCURACY REPORT",
            "=" * 70,
            "",
            f"Documents:    {self.extraction_successes}/{self.total_documents} extracted successfully ({self.extraction_rate:.0%})",
            "",
            "Accuracy (of successfully extracted):",
            f"  Title:      {self.title_passes}/{self.extraction_successes} ({self.title_accuracy:.0%})",
            f"  Authors:    {self.author_passes}/{self.extraction_successes} ({self.author_accuracy:.0%})",
            f"  Year:       {self.year_passes}/{self.extraction_successes} ({self.year_accuracy:.0%})",
        ]

        failures = self.failed_documents()
        if failures:
            lines.extend([
                "",
                "-" * 70,
                f"FAILURES ({len(failures)} documents):",
                "-" * 70,
            ])
            for r in failures:
                lines.append(f"\n  {r.citekey}:")
                if not r.extraction_success:
                    lines.append(f"    Extraction failed: {r.extraction_error}")
                else:
                    if not r.passed_title():
                        lines.append(f"    Title: {r.title_similarity:.0%} similarity")
                        lines.append(f"      Extracted: {r.extracted_title!r}")
                    if not r.passed_authors():
                        lines.append(f"    Authors: {r.author_score:.0%} match")
                        lines.append(f"      Extracted: {r.extracted_authors}")
                    if not r.passed_year():
                        lines.append(f"    Year: mismatch")
                        lines.append(f"      Extracted: {r.extracted_year!r}")

        lines.extend(["", "=" * 70, ""])
        return "\n".join(lines)
```

**Step 2: Test the AccuracyReport**

Run: `uv run python -c "
from tests.extraction.conftest import AccuracyReport, DocumentResult

report = AccuracyReport()

# Add a passing result
report.add_result(DocumentResult(
    citekey='Pass2023',
    extraction_success=True,
    title_similarity=0.95,
    author_score=0.8,
    year_match=True,
))

# Add a failing result
report.add_result(DocumentResult(
    citekey='Fail2024',
    extraction_success=True,
    title_similarity=0.5,
    author_score=0.3,
    year_match=False,
))

assert report.total_documents == 2
assert report.extraction_successes == 2
assert report.title_passes == 1
assert report.author_passes == 1
assert report.year_passes == 1

print(report.format_summary())
print('AccuracyReport tests passed')
"`
Expected: Shows formatted summary and `AccuracyReport tests passed`

**Step 3: Commit**

```bash
git add tests/extraction/conftest.py
git commit -m "feat(tests): add AccuracyReport dataclass for aggregate statistics"
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Add session-scoped report fixture

**Files:**
- Modify: `tests/extraction/conftest.py`

**Step 1: Add accuracy_report fixture**

Add to `tests/extraction/conftest.py`:

```python


@pytest.fixture(scope="session")
def accuracy_report() -> AccuracyReport:
    """Session-scoped accuracy report for collecting results.

    Tests can add DocumentResult instances to this report.
    The report is printed at end of session via pytest hook.

    Returns:
        Shared AccuracyReport instance
    """
    return AccuracyReport()
```

**Step 2: Verify fixture is discoverable**

Run: `uv run pytest tests/extraction/ --collect-only --fixtures 2>&1 | grep accuracy_report`
Expected: Shows `accuracy_report` fixture listed

**Step 3: Commit**

```bash
git add tests/extraction/conftest.py
git commit -m "feat(tests): add accuracy_report fixture for session-wide collection"
```
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Add pytest hook for summary output

**Files:**
- Modify: `tests/extraction/conftest.py`

**Step 1: Add pytest_terminal_summary hook**

Add to `tests/extraction/conftest.py`:

```python


def pytest_terminal_summary(
    terminalreporter: pytest.TerminalReporter,
    exitstatus: int,  # noqa: ARG001
    config: pytest.Config,  # noqa: ARG001
) -> None:
    """Print accuracy report at end of test session.

    This hook is called after all tests complete. It retrieves the
    session-scoped accuracy_report and prints the summary.
    """
    # Get the accuracy report from the session fixture
    # This is a bit awkward because hooks don't have direct fixture access
    # We need to check if any extraction tests ran and collected results
    if hasattr(terminalreporter.config, "_accuracy_report"):
        report: AccuracyReport = terminalreporter.config._accuracy_report
        if report.total_documents > 0:
            terminalreporter.write_line("")
            for line in report.format_summary().split("\n"):
                terminalreporter.write_line(line)
```

**Step 2: Update accuracy_report fixture to register with config**

**IMPORTANT:** Replace the `accuracy_report` fixture from Task 2 with this updated version that registers with pytest config. Find the existing `accuracy_report` fixture and replace it entirely:

```python
@pytest.fixture(scope="session")
def accuracy_report(request: pytest.FixtureRequest) -> AccuracyReport:
    """Session-scoped accuracy report for collecting results.

    Tests can add DocumentResult instances to this report.
    The report is printed at end of session via pytest hook.

    Returns:
        Shared AccuracyReport instance
    """
    report = AccuracyReport()
    # Register with config so hook can access it
    request.config._accuracy_report = report  # type: ignore[attr-defined]
    return report
```

**Step 3: Verify the hook doesn't break test collection**

Run: `uv run pytest tests/extraction/ --collect-only`
Expected: Collection completes without errors

**Step 4: Commit**

```bash
git add tests/extraction/conftest.py
git commit -m "feat(tests): add pytest hook for accuracy report summary"
```
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Add helper to record extraction results

**Files:**
- Modify: `tests/extraction/conftest.py`

**Step 1: Add record_extraction_result helper function**

Add to `tests/extraction/conftest.py`:

```python


def record_extraction_result(
    report: AccuracyReport,
    citekey: str,
    ground_truth: GroundTruth | None,
    extracted_text: str,
    extraction_error: str | None = None,
) -> DocumentResult:
    """Record extraction result and add to accuracy report.

    Creates a DocumentResult from extraction output and ground truth,
    computes comparison metrics, and adds to the report.

    Args:
        report: AccuracyReport to add result to
        citekey: Document identifier
        ground_truth: Expected metadata (or None if unavailable)
        extracted_text: Text extracted from PDF
        extraction_error: Error message if extraction failed

    Returns:
        The created DocumentResult
    """
    result = DocumentResult(citekey=citekey)

    if extraction_error:
        result.extraction_success = False
        result.extraction_error = extraction_error
        report.add_result(result)
        return result

    result.extraction_success = True

    # If we have ground truth and M3b extraction is implemented,
    # we would extract metadata and compare here
    # For now, just record that extraction succeeded

    if ground_truth is not None:
        # Placeholder: when M3b implements extract_metadata_from_text,
        # this will compute actual comparison metrics
        # For now, just mark as not compared
        result.title_similarity = 0.0
        result.author_score = 0.0
        result.year_match = False

    report.add_result(result)
    return result
```

**Step 2: Test the helper function**

Run: `uv run python -c "
from tests.extraction.conftest import (
    AccuracyReport,
    GroundTruth,
    record_extraction_result,
)

report = AccuracyReport()
gt = GroundTruth('Test2023', 'test title', ('Smith, John',), '2023')

# Record a successful extraction
result = record_extraction_result(
    report=report,
    citekey='Test2023',
    ground_truth=gt,
    extracted_text='Some extracted content',
)

assert result.extraction_success is True
assert report.total_documents == 1
assert report.extraction_successes == 1

# Record a failed extraction
result2 = record_extraction_result(
    report=report,
    citekey='Test2024',
    ground_truth=None,
    extracted_text='',
    extraction_error='File not found',
)

assert result2.extraction_success is False
assert report.total_documents == 2
assert report.extraction_successes == 1

print('record_extraction_result tests passed')
"`
Expected: `record_extraction_result tests passed`

**Step 3: Commit**

```bash
git add tests/extraction/conftest.py
git commit -m "feat(tests): add record_extraction_result helper for result tracking"
```
<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Verify Phase 6 completion

**Files:**
- None (verification only)

**Step 1: Verify all diagnostic components are importable**

Run: `uv run python -c "
from tests.extraction.conftest import (
    AccuracyReport,
    DocumentResult,
    record_extraction_result,
)
print('All diagnostic components importable')
"`
Expected: `All diagnostic components importable`

**Step 2: Verify report formatting works**

Run: `uv run python -c "
from tests.extraction.conftest import AccuracyReport, DocumentResult

report = AccuracyReport()
for i in range(5):
    report.add_result(DocumentResult(
        citekey=f'Doc{i}',
        extraction_success=True,
        title_similarity=0.95 - (i * 0.1),
        author_score=0.8,
        year_match=(i % 2 == 0),
    ))

summary = report.format_summary()
assert 'EXTRACTION ACCURACY REPORT' in summary
assert 'Title:' in summary
assert 'FAILURES' in summary
print('Report formatting verified')
"`
Expected: `Report formatting verified`

**Step 3: Run ruff to check code quality**

Run: `uv run ruff check tests/extraction/conftest.py`
Expected: No errors

Run: `uv run ruff format tests/extraction/conftest.py`
Expected: File formatted

**Step 4: Commit any formatting changes**

```bash
git add tests/extraction/conftest.py
git commit -m "style: apply ruff formatting to extraction conftest" --allow-empty
```

**Phase 6 complete when:**
- `AccuracyReport` dataclass aggregates results with computed properties
- `accuracy_report` fixture provides session-scoped collection
- `pytest_terminal_summary` hook prints report at session end
- `record_extraction_result` helper simplifies result tracking
- Report formats with per-document failures and field-level diffs
- All code passes ruff check
<!-- END_TASK_5 -->
