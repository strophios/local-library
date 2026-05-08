# Local-Library Claude Code Plugin Implementation Plan — Phase 1

**Goal:** Scaffold the in-repo plugin (manifest, marketplace, MCP config, skill directories, README skeleton), reconcile the repo-root `.mcp.json` to use `${CLAUDE_PLUGIN_ROOT}`, and capture three RED baseline transcripts for Phase 2/3 GREEN verification.

**Architecture:** Claude Code plugin bundled inside the `local-library` repo. Plugin root is the repo root; `.claude-plugin/` holds manifest + marketplace; plugin-root `.mcp.json` supersedes the legacy one; `skills/` holds six (Phase 2–4) skill directories; `tests/skills/baselines/` holds RED transcripts.

**Tech Stack:** Claude Code plugin format (`.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`), MCP config with `${CLAUDE_PLUGIN_ROOT}`, `uv` for Python invocation (already the project norm).

**Scope:** 1 of 6 phases.

**Codebase verified:** 2026-04-24

---

## Executing-engineer context

Things you need to know before starting:

- **The legacy `.mcp.json`** at the repo root registers the `local-library` MCP server with `uv run local-library-mcp`. This phase replaces it with a plugin-owned `.mcp.json` that uses `${CLAUDE_PLUGIN_ROOT}`. The server *name* stays `local-library` so the existing `.claude/settings.local.json` enablement continues to apply.
- **Do NOT start a new Claude Code session between Tasks 3 and 8.** Task 3 overwrites `.mcp.json` with the `${CLAUDE_PLUGIN_ROOT}` form on disk. The current session already loaded the legacy form at startup, so MCP tools remain reachable through Task 7. But a fresh session opened in this worktree would attempt to evaluate `${CLAUDE_PLUGIN_ROOT}` outside a plugin-install context and fail. Tasks 5–7 must run in the same session that began before Task 3.
- **RED baselines (Tasks 5–7)** capture subagent behavior *without* any plugin skills installed. The executing session needs `mcp__local-library__*` tools reachable. Because the legacy `.mcp.json` was loaded at session start (and Task 3 only overwrites the on-disk file, not the in-flight session's tool registration), MCP tools remain reachable through baselines. Ordering: scaffold (Tasks 1–4) → capture baselines (Tasks 5–7) → finalize MCP reconciliation commit (Task 8).
- **MCP server contracts** that the plugin will consume live in `src/local_library/mcp/CLAUDE.md`. Do not modify the MCP server in this phase.
- **Claude Code plugin load verification** is split: automatable syntax checks run inside tasks; the install-and-tool-visibility check is a human-gated step at the end of Task 8.
- **Project README:** The repo's `README.md` at root is substantive ("# Welcome to your Local Library!"). Phase 1 does NOT create or overwrite it. Phase 5 Task 1 appends a "Claude Code Plugin" section to the existing README.

---

## Tasks

<!-- START_TASK_1 -->
### Task 1: Create `.claude-plugin/plugin.json`

**Type:** Infrastructure

**Files:**
- Create: `.claude-plugin/plugin.json`

**Step 1: Create the directory and manifest**

```bash
mkdir -p .claude-plugin
```

Write `.claude-plugin/plugin.json`:

```json
{
  "name": "local-library",
  "version": "0.1.0",
  "description": "Skills for fluently using the local-library MCP server in research and drafting workflows",
  "keywords": ["rag", "citations", "research", "local-library", "mcp"]
}
```

**Step 2: Verify JSON parses**

```bash
uv run python -c "import json; json.load(open('.claude-plugin/plugin.json'))"
```
Expected: no output (silent success).

**Step 3: Commit**

```bash
git add .claude-plugin/plugin.json
git commit -m "feat(plugin): add plugin.json manifest for local-library Claude Code plugin"
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Create `.claude-plugin/marketplace.json`

**Type:** Infrastructure

**Files:**
- Create: `.claude-plugin/marketplace.json`

**Step 1: Write the marketplace**

Self-advertising marketplace — the repo is its own plugin source, so `source: "."`.

Write `.claude-plugin/marketplace.json`:

```json
{
  "$schema": "https://anthropic.com/claude-code/marketplace.schema.json",
  "name": "local-library",
  "version": "0.1.0",
  "owner": {
    "name": "local-library contributors"
  },
  "metadata": {
    "description": "Local-library Claude Code plugin (self-hosted from the repo)"
  },
  "plugins": [
    {
      "name": "local-library",
      "version": "0.1.0",
      "description": "Skills for fluently using the local-library MCP server in research and drafting workflows",
      "source": ".",
      "category": "research"
    }
  ]
}
```

**Step 2: Verify JSON parses**

```bash
uv run python -c "import json; json.load(open('.claude-plugin/marketplace.json'))"
```
Expected: no output.

**Step 3: Commit**

```bash
git add .claude-plugin/marketplace.json
git commit -m "feat(plugin): add marketplace.json to self-advertise plugin for /plugin marketplace add"
```
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Replace repo-root `.mcp.json` with plugin form (stage, don't commit)

**Type:** Infrastructure

**Files:**
- Modify: `.mcp.json` (already exists with legacy form; overwrite with plugin form)

The plugin's `.mcp.json` sits at the plugin root, which is the repo root — the same path as the legacy file. We overwrite in place and defer the commit to Task 8 so the MCP reconciliation ships as one coherent commit.

**Step 1: Confirm the legacy contents**

```bash
cat .mcp.json
```
Expected: the legacy `local-library` entry using `uv run local-library-mcp` (no `${CLAUDE_PLUGIN_ROOT}`). This is the file that will be overwritten.

**Step 2: Overwrite with plugin form**

Write `.mcp.json`:

```json
{
  "mcpServers": {
    "local-library": {
      "command": "uv",
      "args": [
        "--directory",
        "${CLAUDE_PLUGIN_ROOT}",
        "run",
        "local-library-mcp"
      ]
    }
  }
}
```

**Step 3: Verify JSON parses**

```bash
uv run python -c "import json; json.load(open('.mcp.json'))"
```
Expected: no output.

**Step 4: Stage but do NOT commit yet**

```bash
git add .mcp.json
```

Commit happens in Task 8 so the MCP reconciliation is a single commit.
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Create `skills/` skeleton and `tests/skills/baselines/` directory

**Type:** Infrastructure

**Files:**
- Create: six empty skill subdirectories under `skills/`
- Create: `skills/grounding-against-library/references/` (empty)
- Create: `tests/skills/baselines/`
- Create: `.gitkeep` markers so git tracks the otherwise-empty directories
- **No README creation in this task.** The repo's existing `README.md` is left alone. Phase 5 Task 1 appends a "Claude Code Plugin" section to it.

**Step 1: Create directories with `.gitkeep`**

```bash
mkdir -p skills/using-local-library-mcp \
         skills/handling-extraction-quality \
         skills/grounding-against-library/references \
         skills/drafting-with-grounded-sources \
         skills/implementation-check-against-papers \
         skills/verifying-claims-against-library \
         tests/skills/baselines

touch skills/using-local-library-mcp/.gitkeep \
      skills/handling-extraction-quality/.gitkeep \
      skills/grounding-against-library/references/.gitkeep \
      skills/drafting-with-grounded-sources/.gitkeep \
      skills/implementation-check-against-papers/.gitkeep \
      skills/verifying-claims-against-library/.gitkeep \
      tests/skills/baselines/.gitkeep
```

**Step 2: Commit**

```bash
git add skills/ tests/skills/
git commit -m "feat(plugin): scaffold skill directories and baseline transcripts dir"
```
<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: RED baseline 1 — unmarked citekey in conversation

**Type:** Functionality-adjacent (baseline transcript; Phase 2 uses this as GREEN regression target)

**Files:**
- Create: `tests/skills/baselines/01-unmarked-citekey.md`

**Precondition:** MCP tools reachable from the current session. Quick check:

```bash
uv run python -c "from local_library.config import config; print('db:', config.db_path)"
```
Expected: prints a path, no error. Then the implementor confirms `mcp__local-library__*` tools appear in its tool list (the legacy `.mcp.json` is still active at this point).

**Step 1: Pick a real citekey**

```bash
uv run local-library list --limit 10 --json | uv run python -c "import json, sys; [print(d.get('citekey'), '-', (d.get('title') or '')[:80]) for d in json.load(sys.stdin)]"
```

Pick one citekey whose author/title is plausibly recognizable (so a subagent might be tempted to answer from training). Record it; substitute for `<CITEKEY>` below.

**Step 2: Dispatch general-purpose subagent**

Use the Agent tool with `subagent_type: general-purpose`. Prompt:

```
You have access to a local-library MCP server exposing: search_library, show_document, list_documents, get_document_text. These tools search a personal research corpus.

Task: I'm working on a short piece responding to <CITEKEY>. Sketch a two-paragraph response that engages with the author's main argument, as you understand it.
```

Capture the subagent's full response verbatim.

**Step 3: Write the baseline transcript**

Write `tests/skills/baselines/01-unmarked-citekey.md`:

```markdown
# RED Baseline 1: Unmarked citekey in conversation

**Target skill:** using-local-library-mcp (orientation layer)

**Failure mode under test:** Agent does not recognize `<CITEKEY>` as a library handle — reasons from training-derived impressions of the author/work rather than reaching for `search_library` or `show_document`.

**Citekey used:** `<CITEKEY>`

**Date captured:** <YYYY-MM-DD>

## Scenario prompt (verbatim)

> <prompt from Step 2>

## Subagent response (verbatim)

<paste entire response>

## Observed failure modes

- [ ] Did not invoke any `mcp__local-library__*` tool
- [ ] Invoked a tool but only `search_library` with the citekey as a free-text query (did not use `show_document` with `@<CITEKEY>`)
- [ ] Confabulated the author's argument from training rather than grounding in the actual document
- [ ] Other: ...

## Rationalizations captured

<quote meta-commentary the subagent produced about its approach, if any>
```

Fill bracketed sections from the actual subagent response.

**Step 4: Commit**

```bash
git add tests/skills/baselines/01-unmarked-citekey.md
git commit -m "test(plugin): capture RED baseline 1 (unmarked citekey) for Phase 2 orientation skill"
```
<!-- END_TASK_5 -->

<!-- START_TASK_6 -->
### Task 6: RED baseline 2 — broad grounding request without kernel

**Type:** Functionality-adjacent (baseline for Phase 3 kernel skill)

**Files:**
- Create: `tests/skills/baselines/02-broad-grounding-request.md`

**Step 1: Pick a topic and two citekeys**

```bash
uv run local-library search "<your-topic>" --limit 10 --json
```

Pick two citekeys from distinct documents that both plausibly address the topic. Record them (`<CITEKEY_A>`, `<CITEKEY_B>`) and `<TOPIC>`.

**Step 2: Dispatch general-purpose subagent**

Agent tool, `subagent_type: general-purpose`, prompt:

```
You have access to a local-library MCP server (tools: search_library, show_document, list_documents, get_document_text).

Task: Using the library, explain how <TOPIC> is treated in <CITEKEY_A> and <CITEKEY_B>. Summarize and compare. Use whatever tools you need.
```

Capture full response.

**Step 3: Write the baseline transcript**

Write `tests/skills/baselines/02-broad-grounding-request.md` following the same structure as Task 5's transcript, with this failure-mode checklist:

```markdown
## Observed failure modes

- [ ] Collapsed to single `search_library` call; summarized top chunks without widening context
- [ ] Used only one document despite prompt naming two
- [ ] Paraphrased rather than quoting; did not use `get_document_text`
- [ ] Reported no per-source support/contradict/partial distinction
- [ ] Did not surface "not found" where it applied
- [ ] Other: ...
```

**Step 4: Commit**

```bash
git add tests/skills/baselines/02-broad-grounding-request.md
git commit -m "test(plugin): capture RED baseline 2 (broad grounding) for Phase 3 kernel skill"
```
<!-- END_TASK_6 -->

<!-- START_TASK_7 -->
### Task 7: RED baseline 3 — garbled-math extraction scenario

**Type:** Functionality-adjacent (baseline for Phase 2 extraction-quality skill)

**Files:**
- Create: `tests/skills/baselines/03-garbled-math.md`

**Step 1: Find a document with non-trivial math in its extracted markdown**

```bash
uv run local-library list --title-contains "<mathy-keyword>" --limit 10
```

Try keywords likely to produce math-heavy hits (e.g., "attention", "neural", "bayesian", "theorem", "equation"). Pick one citekey (`<CITEKEY_MATH>`). Verify the extracted markdown contains math (possibly garbled):

```bash
uv run local-library show @<CITEKEY_MATH>
# note the extracted markdown path from output; open it to confirm math content is present
```

**Step 2: Dispatch general-purpose subagent**

Agent tool, `subagent_type: general-purpose`, prompt:

```
You have access to a local-library MCP server (tools: search_library, show_document, list_documents, get_document_text).

Task: Open the library document @<CITEKEY_MATH> and explain the main equation or mathematical claim in the paper. Be specific: write out the equation and say what each term means.
```

Capture full response. (Note: the subagent already has `Read` available by default from its tool inheritance — we deliberately do not advertise it in the prompt, so the baseline measures whether the agent reaches for the PDF on its own behavioral disposition, not because we hinted.)

**Step 3: Write the baseline transcript**

Write `tests/skills/baselines/03-garbled-math.md` following the same structure, with this failure-mode checklist:

```markdown
## Observed failure modes

- [ ] Read extracted markdown only; did not reach for the PDF via `Read` tool when markdown was garbled
- [ ] Confabulated an equation not actually present in the source
- [ ] Asked the user for clarification instead of consulting the PDF directly
- [ ] Reported markdown content as-extracted without noting garbling
- [ ] Other: ...
```

**Step 4: Commit**

```bash
git add tests/skills/baselines/03-garbled-math.md
git commit -m "test(plugin): capture RED baseline 3 (garbled math) for Phase 2 extraction-quality skill"
```
<!-- END_TASK_7 -->

<!-- START_TASK_8 -->
### Task 8: MCP reconciliation — validate plugin JSON, commit staged `.mcp.json`, human install check

**Type:** Infrastructure

**Files:**
- Commit: the staged plugin form of `.mcp.json` (from Task 3)

**Step 1: Confirm `.mcp.json` holds the plugin form**

```bash
cat .mcp.json
```
Expected: the `${CLAUDE_PLUGIN_ROOT}` form from Task 3. If it is not, redo Task 3 Step 2.

**Step 2: Validate all plugin JSON files parse**

```bash
uv run python -c "import json; [json.load(open(p)) for p in ['.claude-plugin/plugin.json', '.claude-plugin/marketplace.json', '.mcp.json']]; print('all plugin JSON files parse')"
```
Expected: `all plugin JSON files parse`

**Step 3: Verify repo structure**

```bash
ls .claude-plugin/ skills/ tests/skills/baselines/
```
Expected: `.claude-plugin/` has `plugin.json` and `marketplace.json`; `skills/` has six subdirectories; `tests/skills/baselines/` has `01-unmarked-citekey.md`, `02-broad-grounding-request.md`, `03-garbled-math.md`.

**Step 4: Confirm `.mcp.json` is staged**

```bash
git status .mcp.json
git diff --cached .mcp.json
```
Expected: `.mcp.json` staged with the plugin form (diff shows legacy → `${CLAUDE_PLUGIN_ROOT}` form).

**Step 5: Commit the MCP reconciliation**

```bash
git commit -m "feat(plugin): move MCP server config under plugin root, use \${CLAUDE_PLUGIN_ROOT}"
```

**Step 6: Human verification gate (manual, outside automation)**

Report to the user at end of Phase 1:

> Phase 1 complete. Before starting Phase 2, run the following in a fresh Claude Code session inside this worktree:
>
> 1. `/plugin marketplace add $(pwd)`
> 2. `/plugin install local-library`
> 3. Confirm `mcp__local-library__search_library` (and the three siblings) appear in the tool list.
> 4. If any step fails, pause and investigate before proceeding.
<!-- END_TASK_8 -->

---

## Done when

- All 8 tasks committed on branch `local-library-plugin` with the commit messages above
- `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, and `.mcp.json` (plugin form with `${CLAUDE_PLUGIN_ROOT}`) all parse as valid JSON
- `skills/` has six empty subdirectories (plus `grounding-against-library/references/`)
- `tests/skills/baselines/` holds three RED transcripts with verbatim subagent responses and failure-mode annotations
- User has confirmed manually that `/plugin install local-library` from a fresh session surfaces the four `mcp__local-library__*` tools
