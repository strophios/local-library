# Phase 6: Update Existing Tests

**Goal:** Ensure test suite works with new architecture.

**Codebase verification findings:**
Tests that patch `library._extractor` need updating to use `library._extractors[0]`:
- `tests/unit/test_library.py:92` - TestLibraryAdd.test_add_duplicate_path_returns_existing
- `tests/unit/test_library.py:115` - TestLibraryAdd.test_add_duplicate_hash_returns_existing
- `tests/unit/test_library.py:143` - TestLibraryGet.library_with_doc fixture
- `tests/unit/test_library.py:202` - TestLibraryList.test_list_returns_all_documents
- `tests/unit/test_library.py:217` - TestLibraryList.test_list_filters_by_status
- `tests/unit/test_library.py:248` - TestLibraryDelete.library_with_doc fixture

**Testing approach:** Update patches from `library._extractor` to `library._extractors[0]`.

---

<!-- START_TASK_1 -->
### Task 1: Update TestLibraryAdd patches

**Files:**
- Modify: `tests/unit/test_library.py`

**Step 1: Update test_add_duplicate_path_returns_existing**

Find the test at approximately line 89 and change:
```python
        with patch.object(library._extractor, "extract_and_validate") as mock_extract:
```

To:
```python
        with patch.object(library._extractors[0], "extract_and_validate") as mock_extract:
```

**Step 2: Update test_add_duplicate_hash_returns_existing**

Find the test at approximately line 105 and change:
```python
        with patch.object(library._extractor, "extract_and_validate") as mock_extract:
```

To:
```python
        with patch.object(library._extractors[0], "extract_and_validate") as mock_extract:
```

**Step 3: Verify the tests pass**

Run:
```bash
uv run pytest tests/unit/test_library.py::TestLibraryAdd -v
```

Expected: All TestLibraryAdd tests pass.

**Step 4: Commit**

```bash
git add tests/unit/test_library.py
git commit -m "test(library): update TestLibraryAdd patches for handler lists

Change _extractor to _extractors[0] for new list-based architecture."
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Update TestLibraryGet patches

**Files:**
- Modify: `tests/unit/test_library.py`

**Step 1: Update library_with_doc fixture in TestLibraryGet**

Find the fixture at approximately line 131 and change:
```python
        with patch.object(library._extractor, "extract_and_validate") as mock_extract:
```

To:
```python
        with patch.object(library._extractors[0], "extract_and_validate") as mock_extract:
```

**Step 2: Verify the tests pass**

Run:
```bash
uv run pytest tests/unit/test_library.py::TestLibraryGet -v
```

Expected: All TestLibraryGet tests pass.

**Step 3: Commit**

```bash
git add tests/unit/test_library.py
git commit -m "test(library): update TestLibraryGet fixture for handler lists"
```
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Update TestLibraryList patches

**Files:**
- Modify: `tests/unit/test_library.py`

**Step 1: Update test_list_returns_all_documents**

Find the test at approximately line 194 and change:
```python
        with patch.object(library._extractor, "extract_and_validate") as mock_extract:
```

To:
```python
        with patch.object(library._extractors[0], "extract_and_validate") as mock_extract:
```

**Step 2: Update test_list_filters_by_status**

Find the test at approximately line 211 and change:
```python
        with patch.object(library._extractor, "extract_and_validate") as mock_extract:
```

To:
```python
        with patch.object(library._extractors[0], "extract_and_validate") as mock_extract:
```

**Step 3: Verify the tests pass**

Run:
```bash
uv run pytest tests/unit/test_library.py::TestLibraryList -v
```

Expected: All TestLibraryList tests pass.

**Step 4: Commit**

```bash
git add tests/unit/test_library.py
git commit -m "test(library): update TestLibraryList patches for handler lists"
```
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Update TestLibraryDelete patches

**Files:**
- Modify: `tests/unit/test_library.py`

**Step 1: Update library_with_doc fixture in TestLibraryDelete**

Find the fixture at approximately line 236 and change:
```python
        with patch.object(library._extractor, "extract_and_validate") as mock_extract:
```

To:
```python
        with patch.object(library._extractors[0], "extract_and_validate") as mock_extract:
```

**Step 2: Verify the tests pass**

Run:
```bash
uv run pytest tests/unit/test_library.py::TestLibraryDelete -v
```

Expected: All TestLibraryDelete tests pass.

**Step 3: Commit**

```bash
git add tests/unit/test_library.py
git commit -m "test(library): update TestLibraryDelete fixture for handler lists"
```
<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Verify integration tests pass

**Files:**
- `tests/integration/test_workflow.py`
- `tests/integration/test_cli_integration.py`

**Step 1: Run integration tests**

Run:
```bash
uv run pytest tests/integration/ -v
```

Expected: All integration tests pass (they use Library defaults, which should work).

**Step 2: If any tests fail, investigate**

Integration tests likely use fixtures that patch extractors. Check:
- `tests/integration/conftest.py` for fixtures that might need updating
- Any direct patches to `library._extractor`

If issues found in integration fixtures, apply same fix: change `_extractor` to `_extractors[0]`.

**Step 3: Commit any fixes**

If fixes were needed:
```bash
git add tests/integration/
git commit -m "test(integration): update fixtures for handler list architecture"
```

If no fixes needed, skip this commit.
<!-- END_TASK_5 -->

<!-- START_TASK_6 -->
### Task 6: Run full test suite and verify no regressions

**Files:**
- All test files

**Step 1: Run full test suite**

Run:
```bash
uv run pytest -v
```

Expected: All tests pass.

**Step 2: Run with coverage to verify coverage maintained**

Run:
```bash
uv run pytest --cov=local_library --cov-report=term-missing
```

Expected: Coverage should be similar to or better than before the refactoring.

**Step 3: Run linting**

Run:
```bash
uv run ruff check src/ tests/
```

Expected: No linting errors.

**Step 4: Create final commit summarizing the feature**

```bash
git add -A
git commit -m "feat: complete ingestion layer extensibility refactoring

Implements registry-based dispatch for content handlers:
- Library accepts acquirers/extractors lists via dependency injection
- _find_acquirer/_find_extractor dispatch to first matching handler
- FileAcquirer is now content-agnostic (handles any local file)
- Dynamic MIME type detection replaces hardcoded PDF
- Failed records preserve acquired files for future re-processing

Adding new content types now requires only:
1. Implement ContentAcquirer or ContentExtractor protocol
2. Register with Library via constructor injection

No changes to Library.add() logic needed for new content types."
```
<!-- END_TASK_6 -->

---

**Phase 6 complete when:**
- All patches updated from `_extractor` to `_extractors[0]`
- Full test suite passes
- No linting errors
- Coverage maintained
