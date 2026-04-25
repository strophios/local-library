# Local-Library Claude Code Plugin Implementation Plan — Phase 2

**Goal:** Create two always-apply orientation skills — `using-local-library-mcp` and `handling-extraction-quality` — and GREEN-verify each against the Phase 1 RED baselines.

**Architecture:** Both skills are always-apply (broad descriptions) and declare `allowed-tools` covering the four MCP tools plus Claude Code's native `Read`. Content is grounded in concrete cues the agent can observe in MCP tool output (field names, error prefixes, specific artifact patterns) rather than generic principles.

**Tech Stack:** Claude Code skill format (YAML frontmatter + markdown body); MCP tool names `mcp__local-library__{search_library,show_document,list_documents,get_document_text}`.

**Scope:** 2 of 6 phases.

**Codebase verified:** 2026-04-24

---

## Executing-engineer context

- **RED baselines from Phase 1** live in `tests/skills/baselines/01-unmarked-citekey.md` and `tests/skills/baselines/03-garbled-math.md`. Read them *first* — the SKILL.md rationalization tables should address the specific excuses the subagent produced, not generic ones.
- **PDF-path field** is `**Original path:** <filesystem-path>` in `show_document` output (`src/local_library/mcp/formatters.py:172`). The safety-hatch skill relies on extracting this literal string from the tool's markdown return.
- **Error prefixes**: `⚠ USER-FACING ERROR:` = infrastructure failure (surface to user); `Error:` = tool-level (agent handles). See `src/local_library/mcp/CLAUDE.md` and `src/local_library/mcp/formatters.py:67-94`.
- **Garbled-extraction cues** that the skill enumerates: raw `$$...$$`, unprocessed `\sum`/`\int`, empty `$...$` or `<!-- image -->`, broken markdown tables. Source: `src/local_library/ingestion/markdown_cleanup.py:45-104`. Also `**Status:** needs_review` in `show_document` indicates the pdftext fallback fired (extraction unreliable).
- **Line budgets** per design: each SKILL.md ≤150 lines.
- **GREEN-verification mechanics**: no existing project pattern. This phase establishes one under `tests/skills/phase2/`. The automated step dispatches a general-purpose subagent with the SKILL.md body inlined into its prompt (simulates the skill being active). A manual human-gated step at the end of Task 5 asks the user to `/plugin reload` and verify in a real plugin-enabled session.
- **`writing-skills` discipline**: RED → GREEN → REFACTOR. If Task 2 or Task 4 assesses PARTIAL or FAIL, patch the SKILL.md rationalization/red-flags list and re-verify before moving on.

---

## Tasks

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Write `skills/using-local-library-mcp/SKILL.md`

**Type:** Functionality (skill body)

**Files:**
- Create: `skills/using-local-library-mcp/SKILL.md` (≤150 lines)
- Delete: `skills/using-local-library-mcp/.gitkeep`

**Step 1: Read the Phase 1 RED baseline 1 transcript**

```bash
cat tests/skills/baselines/01-unmarked-citekey.md
```

Note the specific rationalizations and tool-use omissions the subagent produced. The SKILL.md rationalization table must address those, not generic hypotheticals.

**Step 2: Read contract references that inform skill content**

```bash
sed -n '1,80p' src/local_library/mcp/server.py
sed -n '1,80p' src/local_library/mcp/CLAUDE.md
sed -n '1,100p' src/local_library/mcp/formatters.py
```

**Step 3: Write the skill file**

Use the structure below. Fill in placeholder prose yourself — do NOT copy the bracketed guidance verbatim.

```markdown
---
name: using-local-library-mcp
description: Use when citekeys (`@Name2023`, bare `Name2023`), paper/book/chapter references, phrasing like "what does X argue", "from my library", "cite this", or any request that could plausibly be grounded in the user's local research corpus — reaches for `mcp__local-library__*` tools before answering from training, and treats `@citekey` as a library handle rather than a topic label.
allowed-tools:
  - mcp__local-library__search_library
  - mcp__local-library__show_document
  - mcp__local-library__list_documents
  - mcp__local-library__get_document_text
  - Read
---

# Using local-library MCP

## Core principle
[1–2 sentences: the local library is the first place to look when a citekey or library-adjacent cue appears. Do not answer about `@Name2023` from training when the actual document is one `show_document` call away.]

## Triggers — reach for library tools when you see
[Concrete bullets covering at minimum:
- Citekey patterns: `@Name2023`, `Name2023`, `Name et al. 2023`
- "What does X argue / say / claim about ..."
- "In my library", "from my notes", "my corpus"
- "Cite this", "ground this", "source for this"
- A named paper/book/chapter/author when ambiguous between library item and general work]

## Tool disambiguation
[Small table mapping intent → tool:
- Get metadata for a known citekey → `show_document @Name2023`
- Search by topic across the corpus → `search_library "topic phrase"`
- Browse/filter the corpus → `list_documents`
- Read a document's text → `get_document_text @Name2023` (note `SHORT_DOC_THRESHOLD=50` in `src/local_library/mcp/server.py:35`: >50 chunks triggers preview mode; follow up with range calls)]

## Procedure — unmarked citekey in conversation
1. User mentions `@Name2023` (or unmarked but plausible citekey).
2. Call `show_document @Name2023` first.
3. If response starts with `Error: No document found matching...`, use the `Did you mean @...?` suggestion.
4. If response starts with `⚠ USER-FACING ERROR:`, surface the infrastructure problem — do not silently fall back to training.
5. For engagement with the argument, pull evidence via `get_document_text @Name2023` or targeted `search_library` calls before writing.

## Reading the tool output
[Explicit cues per tool:
- `search_library`: `### Results (N chunks from M documents)`; lines `@citekey | score: X | *Title*`; Section / Chunk N labels for follow-up
- `show_document`: `**Status:**` (watch for `needs_review` → cross-invoke `handling-extraction-quality`), `**Original path:**`, `**Embedding status:**`
- `get_document_text`: short-doc mode = full text; long-doc no-range = preview + `### Sections` outline; long-doc range mode = `Chunks S–E of N`]

## Rationalization table
| Excuse | Reality |
|--------|---------|
| "I know this author from training, I can just summarize" | The library has their *specific document*. One `show_document` call is cheaper than being wrong. |
| "The citekey is just a label — the real question is topical" | If the user wrote a citekey, they mean *that* document. |
| "`search_library` returned nothing, so the library doesn't have it" | Try `show_document @<citekey>` directly. Search can miss; metadata lookup is authoritative. |
| "Listing all documents would be tedious" | `list_documents` supports filters. Use them. |
[Append rows for any rationalization observed in RED baseline 1 not covered above.]

## Red flags — stop
- Writing two paragraphs about `@Name2023` without calling a library tool
- Paraphrasing what the author "argues" without quoted evidence from `get_document_text`
- Treating `⚠ USER-FACING ERROR:` as a reason to proceed from memory
```

Refine the rationalization table and red flags using the specific failures in RED baseline 1.

**Step 4: Line-count check**

```bash
wc -l skills/using-local-library-mcp/SKILL.md
```
Expected: ≤150.

**Step 5: Commit**

```bash
rm skills/using-local-library-mcp/.gitkeep
git add skills/using-local-library-mcp/SKILL.md skills/using-local-library-mcp/.gitkeep
git commit -m "feat(plugin): add using-local-library-mcp orientation skill"
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: GREEN-verify `using-local-library-mcp` against RED baseline 1

**Type:** Functionality (verification transcript)

**Files:**
- Create: `tests/skills/phase2/using-local-library-mcp-green.md`
- Create: `tests/skills/phase2/` directory

**Step 1: Re-run the RED baseline 1 scenario with the skill injected as context**

```bash
mkdir -p tests/skills/phase2
cat tests/skills/baselines/01-unmarked-citekey.md skills/using-local-library-mcp/SKILL.md
```

Dispatch a general-purpose subagent. The scenario prompt is exactly what RED baseline 1 used (same `<CITEKEY>`, same wording). Inline the SKILL.md body as operative context:

```
You have access to a local-library MCP server exposing: search_library, show_document, list_documents, get_document_text, and Claude Code's native Read tool. Before responding, apply this skill as if it were part of your system prompt:

<SKILL>
<full SKILL.md body from skills/using-local-library-mcp/SKILL.md>
</SKILL>

Task: <same prompt as RED baseline 1>
```

Capture the full response verbatim.

**Step 2: Write the GREEN transcript**

Write `tests/skills/phase2/using-local-library-mcp-green.md`:

```markdown
# GREEN: using-local-library-mcp vs RED baseline 1

**Date:** <YYYY-MM-DD>
**RED baseline reference:** `tests/skills/baselines/01-unmarked-citekey.md`

## Scenario (unchanged from RED)

> <verbatim scenario prompt>

## Subagent response (verbatim, skill active)

<full response>

## RED failure-mode checklist — resolved?

- [x/✗] Did NOT invoke any `mcp__local-library__*` tool → <now resolved? cite evidence>
- [x/✗] Used only `search_library` with citekey as free-text → ...
- [x/✗] Confabulated author's argument from training → ...
- [x/✗] (other RED-observed failures)

## Agent reasoning cites skill guidance?

- [x/✗] <quote where subagent referenced skill triggers, procedure, or rationalization>

## Assessment

PASS / PARTIAL / FAIL — with one-sentence justification.

**Final:** <PASS or PARTIAL or FAIL>
```

**Step 3: Commit**

```bash
git add tests/skills/phase2/using-local-library-mcp-green.md
git commit -m "test(plugin): GREEN verification for using-local-library-mcp vs RED baseline 1"
```

**Step 4: If FAIL or PARTIAL — refactor before moving on**

- Identify the specific new rationalization.
- Patch the SKILL.md rationalization table and/or red-flags list.
- Re-run step 1. Commit updated SKILL.md and updated GREEN transcript.
- Do not proceed to Task 3 until Task 2 is PASS.
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 3-4) -->
<!-- START_TASK_3 -->
### Task 3: Write `skills/handling-extraction-quality/SKILL.md`

**Type:** Functionality

**Files:**
- Create: `skills/handling-extraction-quality/SKILL.md` (≤150 lines)
- Delete: `skills/handling-extraction-quality/.gitkeep`

**Step 1: Read the Phase 1 RED baseline 3 transcript**

```bash
cat tests/skills/baselines/03-garbled-math.md
```

**Step 2: Read contract references**

```bash
sed -n '45,104p' src/local_library/ingestion/markdown_cleanup.py
sed -n '160,180p' src/local_library/mcp/formatters.py
sed -n '566,600p' src/local_library/ingestion/pdf.py
```

**Step 3: Write the skill file**

```markdown
---
name: handling-extraction-quality
description: Use when extracted markdown shows garbled math (raw `$$...$$`, unprocessed `\sum`/`\int`, empty `$...$`), empty `<!-- image -->` comments, broken markdown tables, or when `show_document` reports `**Status:** needs_review` — falls back to reading the original PDF directly with Claude Code's native `Read` tool at the path from `show_document`, using `pages:` to scope, rather than trusting the degraded markdown or asking the user for the equation.
allowed-tools:
  - mcp__local-library__search_library
  - mcp__local-library__show_document
  - mcp__local-library__list_documents
  - mcp__local-library__get_document_text
  - Read
---

# Handling extraction quality

## Core principle
[1–2 sentences: extracted markdown is an artifact; the PDF is the source of truth. When the artifact is degraded for what the user is asking about, read the PDF directly.]

## Recognition cues — markdown is garbled when you see
- Raw `$$...$$` blocks rendered as LaTeX source (Marker LaTeX fallback failed)
- Unprocessed `\sum`, `\int`, `\alpha`, `\frac{...}{...}` mixed with prose
- Empty math delimiters: `$$` or `$...$` with whitespace only
- Empty `<!-- image -->` comments
- Broken markdown tables (missing pipes, uneven cell counts)
- Single-character "words" scattered through what should be dense math

Also: `show_document` reporting `**Status:** needs_review` (the project's pdftext-fallback signal — see `src/local_library/mcp/CLAUDE.md`).

## Iron law — read the PDF; do not ask the user
[Make this the most prominent block in the file. Concrete: the agent must NOT ask the user to retype the equation when the PDF is on disk.]

## Procedure
1. `show_document @<citekey>`.
2. Extract the value of the `**Original path:** ...` field (literal filesystem path, typically under `~/Library/Application Support/local-library/storage/...`).
3. `Read(file_path="<path>", pages="<range>")`. Start narrow (e.g., `pages: "1-3"`) to orient; widen as needed.
4. Read math/figures from the PDF's rendered content.
5. Cite the PDF page number in your response so the user can verify.

## Rationalization table
| Excuse | Reality |
|--------|---------|
| "The user can probably tell me what the equation is" | They shouldn't have to. The PDF is on disk. |
| "The markdown is garbled but I can summarize what's readable" | A summary that elides the math is a wrong answer in a polite wrapper. |
| "I'll just flag the garbling and stop" | Flagging is right only if the PDF is also unreadable. Try first. |
| "Marker is usually accurate — I'll trust it this once" | You already saw the garbling cues. That's the trigger. |
| "The PDF is long; reading will use context" | Use `pages:` to scope. |
[Append rows for rationalizations observed in RED baseline 3 not covered above.]

## Red flags — stop
- About to type "could you tell me the equation" to the user
- About to paraphrase an equation you cannot clearly see
- About to say "Marker output is unclear on this point"
- `show_document` reported `needs_review` and you proceeded anyway
```

**Step 4: Line-count check**

```bash
wc -l skills/handling-extraction-quality/SKILL.md
```
Expected: ≤150.

**Step 5: Commit**

```bash
rm skills/handling-extraction-quality/.gitkeep
git add skills/handling-extraction-quality/SKILL.md skills/handling-extraction-quality/.gitkeep
git commit -m "feat(plugin): add handling-extraction-quality orientation skill (PDF safety hatch)"
```
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: GREEN-verify `handling-extraction-quality` against RED baseline 3

**Type:** Functionality

**Files:**
- Create: `tests/skills/phase2/handling-extraction-quality-green.md`

**Step 1: Re-run the RED baseline 3 scenario with the skill injected**

Same pattern as Task 2 Step 1: dispatch general-purpose subagent with SKILL.md body inlined and the exact RED baseline 3 scenario prompt (same `<CITEKEY_MATH>`).

**Step 2: Write the GREEN transcript**

Same structure as Task 2. Failure-mode resolution checklist mirrors RED baseline 3:

```markdown
## RED failure-mode checklist — resolved?

- [x/✗] Read extracted markdown only; did not reach for PDF via `Read` → <resolved? cite the Read call>
- [x/✗] Confabulated equation → ...
- [x/✗] Asked user for clarification → ...
- [x/✗] Reported markdown content as-extracted without noting garbling → ...
```

**Step 3: Assessment**

Fill PASS/PARTIAL/FAIL and justification. Cite any quoted reference to the skill's iron law, procedure, or `**Original path:**` extraction step.

**Step 4: Commit**

```bash
git add tests/skills/phase2/handling-extraction-quality-green.md
git commit -m "test(plugin): GREEN verification for handling-extraction-quality vs RED baseline 3"
```

**Step 5: Refactor if needed**

Same as Task 2 Step 4. Do not proceed to Task 5 until PASS.
<!-- END_TASK_4 -->
<!-- END_SUBCOMPONENT_B -->

<!-- START_TASK_5 -->
### Task 5: Phase 2 integration — frontmatter validation + human reload gate

**Type:** Infrastructure

**Files:** None.

**Step 1: Confirm SKILL.md files exist as expected**

```bash
ls skills/using-local-library-mcp/ skills/handling-extraction-quality/
```
Expected: each directory contains `SKILL.md` only.

**Step 2: Validate YAML frontmatter**

```bash
uv run python - <<'PY'
import re, yaml, pathlib
for p in ["skills/using-local-library-mcp/SKILL.md", "skills/handling-extraction-quality/SKILL.md"]:
    body = pathlib.Path(p).read_text()
    m = re.match(r"^---\n(.*?)\n---\n", body, re.DOTALL)
    assert m, f"{p}: no YAML frontmatter"
    fm = yaml.safe_load(m.group(1))
    assert fm.get("name"), f"{p}: missing name"
    assert fm.get("description"), f"{p}: missing description"
    assert isinstance(fm.get("allowed-tools"), list) and len(fm["allowed-tools"]) >= 1, f"{p}: allowed-tools must be non-empty list"
    print(f"{p}: OK (name={fm['name']}, tools={len(fm['allowed-tools'])})")
PY
```
Expected: both report OK.

**Step 3: Confirm line-count budgets**

```bash
wc -l skills/using-local-library-mcp/SKILL.md skills/handling-extraction-quality/SKILL.md
```
Expected: each ≤150 lines.

**Step 4: Confirm GREEN transcripts exist and both are PASS**

```bash
grep -l "^\*\*Final:\*\* PASS" tests/skills/phase2/using-local-library-mcp-green.md tests/skills/phase2/handling-extraction-quality-green.md
```
Expected: both files listed (the `**Final:** PASS` sentinel must appear at start of a line). If not, return to Task 2 or Task 4.

**Step 5: Human verification gate**

Report to user at end of Phase 2:

> Phase 2 complete. Before Phase 3, in a fresh Claude Code session in this worktree:
>
> 1. `/plugin reload` (or reinstall via `/plugin install local-library`).
> 2. Confirm `using-local-library-mcp` and `handling-extraction-quality` appear in the skills list.
> 3. Type a prompt with a bare citekey ("what does @<real-citekey> argue about X") and verify Claude reaches for `mcp__local-library__show_document` without being told.
> 4. Paste a snippet of known-garbled markdown (with `$$` or `\sum` artifacts) and verify Claude offers to read the PDF directly.
> 5. Pause Phase 3 if any check fails.
<!-- END_TASK_5 -->

---

## Done when

- Both SKILL.md files committed, each ≤150 lines, with YAML frontmatter that parses and declares `name`, `description`, `allowed-tools`
- Both GREEN transcripts under `tests/skills/phase2/` show PASS assessment against the respective Phase 1 RED baselines
- User has manually confirmed in a fresh plugin-enabled session that both skills are discoverable and exert the expected behavioral pull
