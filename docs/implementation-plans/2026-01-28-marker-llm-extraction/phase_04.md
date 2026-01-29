## Phase 4: Documentation and Manual Testing

This phase updates documentation to reflect the new `--llm-extract` flag and contracts, then performs manual testing with real PDFs to verify quality improvements.

**Note:** This phase is infrastructure-focused (documentation updates) followed by manual verification. No new code features are added.

---

<!-- START_TASK_1 -->
### Task 1: Update CLI help text for add command

**Files:**
- Verify: `src/local_library/cli/add.py` (already done in Phase 3)

**Step 1: Verify the help text is accurate**

Run: `uv run local-library add --help`

Expected output should include:

```
--llm-extract    Use Marker's LLM-enhanced PDF extraction (better tables,
                 math, images). Requires GEMINI_API_KEY.
```

If the help text is missing or incorrect, update the option definition in `add.py`.

**Step 2: Verify the command works with --help**

Run: `uv run local-library --help`

Expected: Shows all commands including `add`

Run: `uv run local-library add --help`

Expected: Shows `--llm-extract` option with description

This task is verification only - no commit needed if help text is correct.
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Update ingestion CLAUDE.md with PdfExtractor LLM contract

**Files:**
- Modify: `src/local_library/ingestion/CLAUDE.md`

**Step 1: Update the Contracts section**

Find the `## Contracts` section and update the guarantees to include LLM extraction:

Add this bullet point under `- **Guarantees**:`:

```markdown
  - PdfExtractor supports LLM-enhanced extraction via `llm_enabled` parameter (better tables, math, images when GEMINI_API_KEY available)
```

**Step 2: Update the Key Decisions section**

Add a new decision after "Lazy Marker loading":

```markdown
- **PdfExtractor LLM mode**: When `llm_enabled=True` and GEMINI_API_KEY is set, configures Marker with `use_llm`, `redo_inline_math`, and `disable_image_extraction` (images become text descriptions). Falls back silently to standard extraction without API key.
```

**Step 3: Update the Gotchas section**

Add a new gotcha:

```markdown
- PdfExtractor with `llm_enabled=True` passes `gemini_api_key` directly via Marker's config dict (avoids environment variable mutation)
```

**Step 4: Update the "Last verified" date**

Change the date at the top to today's date:

```markdown
Last verified: 2026-01-28
```

**Step 5: Commit**

```bash
git add src/local_library/ingestion/CLAUDE.md
git commit -m "$(cat <<'EOF'
docs(ingestion): update CLAUDE.md for PdfExtractor LLM support

- Add LLM extraction guarantee to contracts
- Document LLM mode configuration decision
- Add gotcha about gemini_api_key config dict approach
- Update last verified date

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Update core CLAUDE.md with Library pdf_llm_enabled parameter

**Files:**
- Modify: `src/local_library/core/CLAUDE.md`

**Step 1: Update the Contracts section**

Find the `## Contracts` section. Update the guarantees to include:

```markdown
  - Library accepts `pdf_llm_enabled` parameter to enable Marker LLM-enhanced extraction for PDFs
```

**Step 2: Update the Key Decisions section**

The existing `Handler injection` decision mentions PdfExtractor defaults. Update or add:

```markdown
- **PDF LLM extraction config**: Library accepts `pdf_llm_enabled` parameter (default False) passed to default PdfExtractor. Custom extractors (passed via constructor) are not affected.
```

**Step 3: Update the Gotchas section**

Add:

```markdown
- `pdf_llm_enabled` only affects the default PdfExtractor; custom extractors must configure LLM mode themselves
```

**Step 4: Update the "Last verified" date**

```markdown
Last verified: 2026-01-28
```

**Step 5: Commit**

```bash
git add src/local_library/core/CLAUDE.md
git commit -m "$(cat <<'EOF'
docs(core): update CLAUDE.md for pdf_llm_enabled parameter

- Add pdf_llm_enabled to Library contracts
- Document configuration passthrough decision
- Add gotcha about custom extractors
- Update last verified date

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Update CLI CLAUDE.md with --llm-extract flag documentation

**Files:**
- Modify: `src/local_library/cli/CLAUDE.md`

**Step 1: Update the Contracts section**

Find the `## Contracts` section. Update the guarantees to include early validation behavior:

```markdown
  - Both `--llm` and `--llm-extract` flags validate GEMINI_API_KEY early, warn and disable if missing
```

**Step 2: Update the Key Decisions section**

Add:

```markdown
- **Early API key validation**: `--llm` and `--llm-extract` check GEMINI_API_KEY before Library instantiation; warn and gracefully disable features if missing
```

**Step 3: Update the "Last verified" date**

```markdown
Last verified: 2026-01-28
```

**Step 4: Commit**

```bash
git add src/local_library/cli/CLAUDE.md
git commit -m "$(cat <<'EOF'
docs(cli): update CLAUDE.md for --llm-extract flag

- Add early API key validation guarantee
- Document graceful degradation behavior
- Update last verified date

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```
<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Update root CLAUDE.md Commands section

**Files:**
- Modify: `CLAUDE.md` (root)

**Step 1: Update the Commands section**

Find the `## Commands` section and update the `add` command documentation to mention `--llm-extract`:

```markdown
- `uv run local-library add <path>` - Add a PDF to the library
- `uv run local-library add <path> --metadata <csl-json-file>` - Add with bibliographic metadata
- `uv run local-library add <path> --llm-extract` - Add with LLM-enhanced PDF extraction (requires GEMINI_API_KEY)
```

**Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "$(cat <<'EOF'
docs: add --llm-extract to Commands section

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```
<!-- END_TASK_5 -->

<!-- START_TASK_6 -->
### Task 6: Manual testing with test PDFs

**Files:**
- None (manual verification)

This task is manual testing to verify the implementation works correctly with real PDFs. The design document specifies these test PDFs:

- Tables: `NIST2023.pdf`, `Massachusetts2024.pdf`
- Math: `Hu2018.pdf`, `Dhingra2022.pdf`

**Step 1: Test without LLM extraction (baseline)**

If you have test PDFs available, establish a baseline:

```bash
# Without --llm-extract (standard extraction)
uv run local-library add /path/to/NIST2023.pdf
uv run local-library show <id>
uv run local-library open <id>  # View extracted markdown
```

Note the quality of table extraction in the markdown output.

**Step 2: Test with LLM extraction (requires GEMINI_API_KEY)**

```bash
# Set API key
export GEMINI_API_KEY=your-api-key-here

# With --llm-extract
uv run local-library add /path/to/NIST2023.pdf --llm-extract
uv run local-library show <id>
uv run local-library open <id>  # Compare markdown quality
```

Compare:
- Table formatting (should be more accurate with LLM)
- Math expressions (should use proper LaTeX)
- Image placeholders (should be text descriptions instead of image references)

**Step 3: Test graceful degradation (no API key)**

```bash
# Unset API key
unset GEMINI_API_KEY

# Should warn and proceed without LLM
uv run local-library add /path/to/test.pdf --llm-extract
```

Expected: Warning message about missing GEMINI_API_KEY, extraction proceeds normally

**Step 4: Test with --json output**

```bash
unset GEMINI_API_KEY
uv run local-library add /path/to/test.pdf --llm-extract --json
```

Expected: JSON-formatted warning message

This task is verification only - no commit needed.
<!-- END_TASK_6 -->

<!-- START_TASK_7 -->
### Task 7: Run full test suite and final verification

**Files:**
- None (verification only)

**Step 1: Run ruff check on all modified files**

Run: `uv run ruff check src/local_library/`

Expected: No linting errors

**Step 2: Run ruff format check**

Run: `uv run ruff format --check src/local_library/`

Expected: No formatting issues

**Step 3: Run the full test suite**

Run: `uv run pytest tests/unit/ tests/integration/ -v`

Expected: All tests pass

**Step 4: Verify git status is clean (all changes committed)**

Run: `git status`

Expected: Only untracked files (if any), no uncommitted changes to tracked files

**Step 5: Review commit history**

Run: `git log --oneline -10`

Expected: Clean commit history with all phase commits
<!-- END_TASK_7 -->

---

## Phase 4 Completion Checklist

- [ ] CLI help text shows `--llm-extract` with accurate description
- [ ] `src/local_library/ingestion/CLAUDE.md` updated with LLM extraction contracts
- [ ] `src/local_library/core/CLAUDE.md` updated with pdf_llm_enabled parameter
- [ ] `src/local_library/cli/CLAUDE.md` updated with early validation behavior
- [ ] Root `CLAUDE.md` Commands section includes `--llm-extract` example
- [ ] Manual testing completed (if test PDFs available)
- [ ] All tests pass
- [ ] Code passes ruff check and format
- [ ] All changes committed

---

## Implementation Complete Checklist

After all 4 phases, verify:

- [ ] `uv run local-library add --help` shows `--llm-extract` flag
- [ ] `uv run local-library add file.pdf --llm-extract` works with GEMINI_API_KEY set
- [ ] Warning appears when `--llm-extract` used without GEMINI_API_KEY
- [ ] Warning appears when `--llm` used without GEMINI_API_KEY
- [ ] All unit tests pass: `uv run pytest tests/unit/ -v`
- [ ] All integration tests pass: `uv run pytest tests/integration/ -v`
- [ ] Code quality: `uv run ruff check && uv run ruff format --check`
