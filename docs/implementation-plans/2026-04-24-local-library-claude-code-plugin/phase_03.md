# Local-Library Claude Code Plugin Implementation Plan — Phase 3

**Goal:** Create the atomic grounding kernel `skills/grounding-against-library/SKILL.md` and its `references/tool-selection.md` composition matrix; GREEN-verify both the scope guardrail (broad input returns control) and the atomic-execution path (full six-step procedure).

**Architecture:** The kernel is the architectural heart of the plugin: composing skills (Phase 4) decompose user requests into atomic assertions, then invoke the kernel once per assertion. Multi-source synthesis is a feature of the kernel (per-source support/contradict/partial/not-found, then aggregate). The kernel's scope guardrail enforces atomicity by returning control to the caller on broad inputs.

**Tech Stack:** Same as Phase 2 — Claude Code skill format with progressive disclosure via `references/*.md`.

**Scope:** 3 of 6 phases.

**Codebase verified:** 2026-04-24

---

## Executing-engineer context

- **MCP tool signatures** (`src/local_library/mcp/server.py`):
  - `search_library(query, limit=10, mode="hybrid", doc_id=None, no_rerank=False)` — `doc_id` accepts `@citekey` or UUID; document-scoped search uses this parameter, not a separate tool.
  - `show_document(doc_id)` — single param.
  - `list_documents(status, year, year_missing, author_contains, title_contains, citekey_prefix, limit=20)`.
  - `get_document_text(doc_id, start_chunk, end_chunk)` — **0-based, inclusive** chunk indices. `SHORT_DOC_THRESHOLD=50`, `PREVIEW_CHUNK_COUNT=20`.
- **Reranking inversion**: `no_rerank: bool = False` means reranking is **on** by default. The parameter is inverted internally (`server.py:99`: `rerank=not no_rerank`). Reference doc must call this out so the kernel doesn't accidentally disable reranking.
- **Mode values**: `VALID_MODES = ("hybrid", "vector", "fts")` (`server.py:29`); hybrid is the default and almost always the right choice.
- **RED baseline 2** (`tests/skills/baselines/02-broad-grounding-request.md`) is the source of failure modes for the scope-guardrail GREEN check.
- **Atomic-execution GREEN test** uses a deliberately atomic claim about a real corpus document — the executing engineer picks the citekey from `uv run local-library list`. The claim should be specific enough that "support" requires an actual quoted excerpt.

---

## Tasks

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Write `skills/grounding-against-library/SKILL.md`

**Type:** Functionality

**Files:**
- Create: `skills/grounding-against-library/SKILL.md` (≤250 lines)

**Step 1: Read the RED baseline and contract references**

```bash
cat tests/skills/baselines/02-broad-grounding-request.md
sed -n '57,234p' src/local_library/mcp/server.py
cat src/local_library/mcp/CLAUDE.md
```

Note specific RED rationalizations to address (e.g., "I summarized both papers from their abstracts", "one chunk was a strong match so I reported it", "the second paper didn't surface so I dropped it").

**Step 2: Write the skill file**

Structure (≤250 lines total, fill prose yourself; do NOT copy bracketed guidance verbatim):

```markdown
---
name: grounding-against-library
description: Use when grounding exactly ONE target assertion against library evidence — retrieves via MCP tools, widens context as needed, synthesizes across all retrieved evidence (per-source: support/contradict/partial/not-found, then aggregate), and reports with per-source citations and quoted evidence. Callers must decompose broad requests into atomic assertions and invoke this skill per-assertion; the kernel returns control to the caller if the target is too broad.
allowed-tools:
  - mcp__local-library__search_library
  - mcp__local-library__show_document
  - mcp__local-library__list_documents
  - mcp__local-library__get_document_text
  - Read
---

# Grounding against library

## Scope guardrail — READ FIRST

[Prominent block at the top, framed so the kernel cannot rationalize past it:]

This skill grounds ONE target assertion. Your caller — a composing skill or user instruction — is responsible for decomposition.

If the input is broad ("explain how X handles Y", "summarize what the literature says about Z", "compare A and B"), STOP and return control to the caller with:

> This request covers multiple assertions. Please decompose into atomic claims and invoke this skill once per claim. Example decomposition for "<input>": {2–4 candidate atomic assertions}.

Do NOT attempt a partial answer. Do NOT fold multiple claims into one grounding pass.

## Core principle
[1–2 sentences: grounding produces per-source evidence and an aggregate judgment. A single chunk that "looks relevant" is not grounding; it's a hint.]

## Iron law
- **Quote before you paraphrase.** If you cannot quote the supporting text, you have not grounded the claim.
- **Not-found is a valid result.** Reporting "no evidence for this claim in the corpus" is better than confabulating support.

## Six-step procedure

### Step 1 — Confirm one scope
Verify the input is ONE assertion. If not, return control per the scope guardrail.

### Step 2 — Formulate query or queries
A single assertion may need multiple facet queries. Plan them before calling tools. Example for "Vaswani2017 claims multi-head attention reduces compute compared to single-head":
- `search_library("multi-head attention computational cost", doc_id="@Vaswani2017", limit=10)`
- `search_library("single-head attention complexity", doc_id="@Vaswani2017", limit=10)`

If unscoped, issue corpus-wide queries (omit `doc_id`).

### Step 3 — Retrieve
Call the planned queries. Multiple documents surfacing is a feature, not a problem to collapse.

### Step 4 — Widen context
If a chunk appears truncated at a boundary that matters, call `get_document_text(doc_id="@Name2023", start_chunk=N, end_chunk=M)`. Indices are 0-based inclusive.

### Step 5 — Synthesize
Per-source tagging: support / contradict / partial / not-found. Then aggregate.

### Step 6 — Report
Per-source rows with citekey + quoted excerpt + chunk index + status. Aggregate conclusion last.

## Rationalization table
| Excuse | Reality |
|--------|---------|
| "Top chunk matched the keyword; I don't need to read more" | Keyword match ≠ semantic support. Quote the support or mark partial. |
| "One strong hit is dispositive" | Other documents may contradict or qualify. Continue. |
| "I can paraphrase from the chunk; quotation is pedantic" | Paraphrase drift is where false grounding enters. Quote first. |
| "The second document didn't surface, so it's not relevant" | If named, retry with `doc_id="@<citekey>"` before concluding not-found. |
| "The claim is obviously true; I'll skip the quote" | If obvious, quoting is trivial. |
| "Not-found feels like failure — I'll try harder to extract support" | Not-found is a result. Forcing support is confabulation. |
[Append rows for rationalizations observed in RED baseline 2 not covered.]

## Red flags — stop
- About to produce an answer without a quoted excerpt
- About to collapse multiple documents' evidence into one summary
- About to tag `support` based on keyword overlap
- About to skip Step 1 because input "sounds specific enough"
- About to write "the corpus shows..." without per-source breakdown

## See also
- `references/tool-selection.md` — composition and disambiguation matrix.
```

**Step 3: Line-count check**

```bash
wc -l skills/grounding-against-library/SKILL.md
```
Expected: ≤250.

**Step 4: Commit**

```bash
git add skills/grounding-against-library/SKILL.md
git commit -m "feat(plugin): add grounding-against-library kernel skill (atomic, multi-source)"
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Write `skills/grounding-against-library/references/tool-selection.md`

**Type:** Functionality (reference)

**Files:**
- Create: `skills/grounding-against-library/references/tool-selection.md`
- Delete: `skills/grounding-against-library/references/.gitkeep`

**Step 1: Confirm parameter signatures**

```bash
sed -n '57,72p' src/local_library/mcp/server.py
sed -n '127,132p' src/local_library/mcp/server.py
sed -n '164,172p' src/local_library/mcp/server.py
sed -n '230,234p' src/local_library/mcp/server.py
```

**Step 2: Write the reference**

Focus on *scenarios → tools*. Not a parameter dictionary.

```markdown
# Tool selection for grounding

This reference complements `SKILL.md`. It maps common grounding scenarios to MCP tool calls. For exhaustive parameter docs, see `src/local_library/mcp/CLAUDE.md`.

## Identifiers
All four tools accept `doc_id: str` as `@citekey` (preferred) or UUID. Fuzzy match on misses produces a `Did you mean @...?` suggestion — use it.

## Scenario → tool matrix

| Scenario | Start with | Follow-up | Notes |
|---|---|---|---|
| Known citekey; metadata only | `show_document(doc_id="@C")` | — | Check `**Status:** needs_review` → cross-invoke `handling-extraction-quality`. |
| Known citekey; full text (short doc) | `get_document_text(doc_id="@C")` | — | Returns full text if total chunks < 50. |
| Known citekey; long doc | `get_document_text(doc_id="@C")` | `get_document_text(doc_id="@C", start_chunk=N, end_chunk=M)` | Preview + section outline first; range follow-up. |
| Known citekey + topic | `search_library(query, doc_id="@C")` | `get_document_text(doc_id="@C", start_chunk=…, end_chunk=…)` | Doc-scoped search via `doc_id`. |
| Topic across corpus | `search_library(query, limit=10)` | `show_document` for metadata; `get_document_text` for context | `mode="hybrid"` + reranking on (defaults). |
| Multi-facet assertion | Multiple `search_library` calls | Combine in synthesis | 2–4 queries per assertion is normal. |
| Citekey misspelled | `show_document(doc_id="@Guess")` | Use `Did you mean @...?` suggestion | Don't guess twice. |
| Narrow by metadata | `list_documents(year=…, author_contains=…)` | `show_document` on the hit | `limit` only, no offset (default 20). |

## Mode selection
- `mode="hybrid"` (default): RRF fusion of vector + FTS. Use unless you have a reason not to.
- `mode="vector"`: pure semantic.
- `mode="fts"`: pure keyword (BM25). Useful for exact strings.

## Reranking
`no_rerank: bool = False` — default is reranking ON. The parameter is inverted internally (`server.py:99`: `rerank=not no_rerank`); do not set `no_rerank=True` thinking you are *enabling* reranking.

## Chunk indices
`start_chunk` / `end_chunk` are 0-based, inclusive. `start_chunk=3, end_chunk=7` returns five chunks. Reuse the indices `search_library` labels in its output (e.g., `Chunk 42`).

## Short-doc vs long-doc behavior
- `<50` chunks: full text regardless of range.
- `≥50` + no range: preview of first 20 chunks + section outline + range instructions.
- `≥50` + range: requested slice.

## What this reference is NOT
- Not a parameter dictionary (see `src/local_library/mcp/CLAUDE.md`).
- Not an argument for when to ground (see `SKILL.md`).
```

**Step 3: Commit**

```bash
rm skills/grounding-against-library/references/.gitkeep
git add skills/grounding-against-library/references/
git commit -m "feat(plugin): add tool-selection reference for grounding kernel"
```
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 3-4) -->
<!-- START_TASK_3 -->
### Task 3: GREEN 3A — scope guardrail

**Type:** Functionality

**Files:**
- Create: `tests/skills/phase3/grounding-scope-guardrail-green.md`

**Step 1: Re-run RED baseline 2 with the kernel injected**

```bash
mkdir -p tests/skills/phase3
```

Dispatch general-purpose subagent. Scenario prompt = verbatim RED baseline 2. Pre-prompt:

```
You have access to a local-library MCP server (search_library, show_document, list_documents, get_document_text) and Read. Apply this skill as if part of your system prompt:

<SKILL>
<full body of skills/grounding-against-library/SKILL.md>
</SKILL>

<REFERENCE name="tool-selection.md">
<full body of skills/grounding-against-library/references/tool-selection.md>
</REFERENCE>

Task: <verbatim RED baseline 2 prompt>
```

Capture full response.

**Step 2: Write GREEN transcript**

```markdown
# GREEN 3A: scope guardrail vs RED baseline 2

**Date:** <YYYY-MM-DD>
**RED baseline:** `tests/skills/baselines/02-broad-grounding-request.md`
**Expected behavior:** kernel returns control with decomposition request; does NOT attempt the answer.

## Scenario (unchanged from RED)
> <verbatim>

## Subagent response (verbatim)
<full response>

## Guardrail assessment
- [x/✗] Subagent declined to answer the broad question directly
- [x/✗] Subagent produced a decomposition into atomic assertions
- [x/✗] Subagent cited the scope guardrail
- [x/✗] Subagent did NOT silently collapse to a single-source answer

## Assessment
PASS / PARTIAL / FAIL — one-sentence justification.

**Final:** <PASS or PARTIAL or FAIL>
```

**Step 3: Commit**

```bash
git add tests/skills/phase3/grounding-scope-guardrail-green.md
git commit -m "test(plugin): GREEN 3A — kernel scope guardrail returns control on broad input"
```

**Step 4: Refactor if needed**

If subagent produced a partial answer, strengthen the guardrail (move earlier, add red flag, add rationalization row). Re-verify; commit; do not proceed until PASS.
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: GREEN 3B — atomic execution (full six-step cycle)

**Type:** Functionality

**Files:**
- Create: `tests/skills/phase3/grounding-atomic-execution-green.md`

**Step 1: Pick an atomic assertion grounded in a real document**

```bash
uv run local-library list --limit 20
```

Choose `<CITEKEY_ATOMIC>`. Construct a specific, checkable claim — ideally one whose answer is "support with quote" so the kernel must actually retrieve and quote.

**Step 2: Dispatch subagent**

Same injection format as Task 3 Step 1. Scenario prompt:

```
Ground the following atomic assertion against the local library:

Claim: <atomic claim mentioning @<CITEKEY_ATOMIC>>

Produce a grounded report with per-source status and quoted evidence.
```

Capture full response.

**Step 3: Write GREEN transcript**

```markdown
# GREEN 3B: atomic execution

**Date:** <YYYY-MM-DD>
**Citekey used:** @<CITEKEY_ATOMIC>
**Claim:** <verbatim>

## Subagent response (verbatim)
<full response>

## Six-step procedure checklist
- [x/✗] Step 1 (scope confirmation)
- [x/✗] Step 2 (query formulation) — quote the plan
- [x/✗] Step 3 (retrieve) — appropriate `search_library` / `show_document` / `get_document_text` calls
- [x/✗] Step 4 (widen context) — called `get_document_text` with chunk range, OR correctly skipped (note which)
- [x/✗] Step 5 (synthesize) — per-source tags present
- [x/✗] Step 6 (report) — quoted evidence with chunk index + aggregate conclusion

## Iron law adherence
- [x/✗] Quoted before paraphrasing
- [x/✗] Willing to report not-found if applicable

## Assessment
PASS / PARTIAL / FAIL — one-sentence justification.

**Final:** <PASS or PARTIAL or FAIL>
```

**Step 4: Commit**

```bash
git add tests/skills/phase3/grounding-atomic-execution-green.md
git commit -m "test(plugin): GREEN 3B — kernel executes six-step procedure on atomic assertion"
```

**Step 5: Refactor if needed**

If specific steps fail (e.g., skipped Step 4, paraphrased without quote), patch SKILL.md (reorder/strengthen the relevant section, add rationalization rows, beef up red flags). Re-verify; commit; do not proceed until PASS.
<!-- END_TASK_4 -->
<!-- END_SUBCOMPONENT_B -->

<!-- START_TASK_5 -->
### Task 5: Phase 3 integration — frontmatter validation + human reload gate

**Type:** Infrastructure

**Files:** None.

**Step 1: Confirm files in place**

```bash
ls skills/grounding-against-library/ skills/grounding-against-library/references/
```
Expected: `SKILL.md` at the skill root; `tool-selection.md` under `references/`.

**Step 2: Validate frontmatter**

```bash
uv run python - <<'PY'
import re, yaml, pathlib
p = "skills/grounding-against-library/SKILL.md"
body = pathlib.Path(p).read_text()
m = re.match(r"^---\n(.*?)\n---\n", body, re.DOTALL)
assert m, f"{p}: no YAML frontmatter"
fm = yaml.safe_load(m.group(1))
assert fm.get("name") == "grounding-against-library"
assert fm.get("description")
tools = fm.get("allowed-tools")
assert isinstance(tools, list) and len(tools) >= 5
print(f"{p}: OK")
PY
```

**Step 3: Line-count check**

```bash
wc -l skills/grounding-against-library/SKILL.md skills/grounding-against-library/references/tool-selection.md
```
Expected: SKILL.md ≤250; tool-selection.md no hard budget but flag if >150.

**Step 4: Confirm both GREEN transcripts are PASS**

```bash
grep -l "^\*\*Final:\*\* PASS" tests/skills/phase3/grounding-scope-guardrail-green.md tests/skills/phase3/grounding-atomic-execution-green.md
```
Expected: both listed (the `**Final:** PASS` sentinel must appear at start of a line).

**Step 5: Human verification gate**

Report to user:

> Phase 3 complete. Before Phase 4, in a fresh plugin-enabled session:
>
> 1. `/plugin reload`.
> 2. Confirm `grounding-against-library` is listed.
> 3. Manually invoke with a broad prompt — verify return-to-caller with decomposition.
> 4. Manually invoke with an atomic prompt about a real citekey — verify six-step procedure with quoted evidence.
> 5. Pause Phase 4 if either check fails.
<!-- END_TASK_5 -->

---

## Done when

- `skills/grounding-against-library/SKILL.md` ≤250 lines, frontmatter valid, scope guardrail at the top
- `skills/grounding-against-library/references/tool-selection.md` covers scenario→tool matrix, mode selection, reranking inversion note, chunk-index semantics
- GREEN 3A transcript shows PASS (broad input returns control)
- GREEN 3B transcript shows PASS (atomic input runs full six-step procedure)
- User has confirmed both paths work in a fresh plugin-enabled session
