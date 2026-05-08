# Local-Library Claude Code Plugin Implementation Plan — Phase 5

**Goal:** Populate the plugin README with full install + architectural overview + skills-at-a-glance + test-drive scenarios; finalize `marketplace.json` metadata; verify the external-user install path and that no per-call approval prompts fire during normal use.

**Architecture:** README is the user-facing entry point. Architectural overview (~200–300 words) explains the three-layer composition (orientation → kernel → procedural). Marketplace metadata supports `/plugin marketplace add` from a remote URL once the repo is published. Permissions audit is human-gated.

**Tech Stack:** Same as prior phases.

**Scope:** 5 of 6 phases.

**Codebase verified:** 2026-04-24

---

## Executing-engineer context

- **README target:** The repo's existing `README.md` at root is substantive ("# Welcome to your Local Library!"). Phase 1 leaves it untouched. Phase 5 Task 1 *appends* a "Claude Code Plugin" section to the existing README, preserving project content while satisfying the plugin convention that plugin docs live at the plugin-root README.
- **Marketplace metadata** is finalized with description/homepage/keywords. The `homepage` field uses a placeholder if the repo's GitHub URL is not known; this is updated when the repo is published.
- **Permissions audit** is fundamentally a session-level property (per-call approval prompts depend on Claude Code's evaluation of `allowed-tools` against `.claude/settings*.json`). The audit is performed manually by the user from a fresh shell; the implementor automates only the audit template.

---

## Tasks

<!-- START_TASK_1 -->
### Task 1: Append the plugin section to the existing project README

**Type:** Functionality (documentation)

**Files:**
- Modify: `README.md` (append a new section; do NOT overwrite existing content)

**Step 1: Confirm the existing README is what investigation expected**

```bash
head -10 README.md
```
Expected: starts with `# Welcome to your Local Library!` (the existing project README). If the file looks different, stop and investigate — do not destructively edit.

**Step 2: Append the plugin section**

Append the following content to the END of `README.md` (after the existing project content). The section header `## Claude Code Plugin` keeps it discoverable from a TOC; subheadings are level-3 to nest under it cleanly.

Architectural overview ≈200–300 words.

```markdown


---

## Claude Code Plugin

This repo also ships as a Claude Code plugin: six skills bundled with the MCP server config Claude Code needs to talk to your local library. With the plugin installed, a citekey dropped in conversation prompts a library lookup automatically, and grounded writing/checking is the path of least resistance.

### What the plugin provides

- Two **orientation** skills (always-apply): teach Claude to notice library-adjacent cues and reach for `mcp__local-library__*` tools fluently; teach Claude to fall back to the original PDF when extracted markdown is garbled.
- One **shared grounding kernel**: atomic per-assertion retrieve → quote → synthesize → report cycle the procedural skills compose on.
- Three **procedural composition** skills: drafting with grounded sources (prose + audit appendix), implementation-check against papers (assertion table comparing code to method descriptions), verifying claims against the library (claim-by-claim status with quoted support).

The plugin works from any project where you have Claude Code running — the library doesn't have to be the project you're working on.

### Who this is for

Anyone using the local-library MCP server who wants Claude Code to:
- Treat citekeys as library handles, not topic labels
- Quote evidence by default, not paraphrase from training
- Tag claims with explicit support / contradict / partial / not-found rather than rubber-stamp them
- Read the PDF when extracted markdown can't be trusted (math, figures, tables)

### Plugin install

From a fresh checkout:

    git clone <this-repo>
    cd local-library
    uv sync

Then in a Claude Code session anywhere on your machine:

    /plugin marketplace add /absolute/path/to/local-library
    /plugin install local-library

The plugin's `.mcp.json` brings the MCP server with it (no separate registration), and the six skills auto-discover via Claude Code's plugin loader.

### Architectural overview

[~200-300 words covering:
- Three-layer architecture (orientation → kernel → procedural)
- Why orientation as always-apply skills (plugins can't ship a user-global CLAUDE.md)
- Why the kernel is atomic (composing skills handle decomposition; without this split the kernel implicitly biases toward "one chunk → answer", short-changing multi-source synthesis)
- Why plugin-bundled-with-repo (travels with the library, shareable, usable from any project)
- How the safety hatch works (extraction-quality skill cross-invoked on garbled-math cues; uses native Read on PDF path from show_document)
- One-paragraph end-to-end flow: citekey appears → orientation skill triggers show_document → user asks question that decomposes into multiple claims → procedural skill enumerates → kernel runs per-claim → output assembled per skill format]

### Skills at a glance

| Skill | Layer | What it does |
|---|---|---|
| `using-local-library-mcp` | Orientation | Reach for `mcp__local-library__*` tools when citekeys or library cues appear |
| `handling-extraction-quality` | Orientation | Fall back to `Read` on the PDF when extracted markdown is garbled |
| `grounding-against-library` | Kernel | Per-assertion retrieve → quote → synthesize → report; multi-source |
| `drafting-with-grounded-sources` | Procedural | Decompose into propositions; ground each via the kernel; produce prose + appendix |
| `implementation-check-against-papers` | Procedural | Decompose code into claims; ground against paper(s); produce assertion table |
| `verifying-claims-against-library` | Procedural | Enumerate citation-bearing claims; per-claim grounding; produce claim table |

### Test-drive scenarios

After installing, try these:

1. **Orientation triggers on bare citekey:**
   > "What does @<your-citekey> argue about <topic>?"
   Expected: Claude calls `show_document` (or `search_library`) before responding; quotes evidence rather than summarizing from training.

2. **Safety hatch triggers on garbled extraction:**
   > "Open @<your-mathy-citekey> and explain the main equation."
   Expected: Claude reads the PDF directly via `Read` if extracted markdown is garbled; cites page number.

3. **Kernel returns control on a broad request:**
   > "Tell me how the literature in my library handles <topic>."
   Expected: Claude declines to answer and proposes a decomposition.

4. **Drafting with appendix:**
   > "Write a short note on <topic> drawing from @<A> and @<B>."
   Expected: prose with inline citekeys + grounding-summary appendix at end.

5. **Verifying claims:**
   > "Check whether my library supports these:
   > 1. <claim> — per @<X>
   > 2. <claim> — per @<Y>"
   Expected: claim table with quoted support, statuses, summary line.

### Disabling / overriding plugin skills

To disable individual skills without uninstalling the plugin:
- Edit `~/.claude/settings.json` and add the skill name to the `disabledSkills` list (or use the `/plugin` UI).
- To narrow tool authorization for a single skill, edit the `allowed-tools` block in that skill's `SKILL.md` after installation (note: this edits the installed copy, not the source repo).

To uninstall:

    /plugin uninstall local-library
    /plugin marketplace remove local-library

### Where the plugin's pieces live

- Skills: `skills/<skill-name>/SKILL.md`
- Plugin manifest: `.claude-plugin/plugin.json`
- Marketplace advertisement: `.claude-plugin/marketplace.json`
- MCP server config: `.mcp.json` (uses `${CLAUDE_PLUGIN_ROOT}`)
- Design doc: `docs/design-plans/2026-04-24-local-library-claude-code-plugin.md`
- Implementation plan: `docs/implementation-plans/2026-04-24-local-library-claude-code-plugin/`
- RED baselines, GREEN/Tier-3 transcripts, smoke tests: `tests/skills/`
```

**Step 3: Sanity check**

```bash
wc -l README.md
tail -50 README.md
```
Expected: README has grown by ~100 lines; the new `## Claude Code Plugin` section appears at the end with clean heading hierarchy; no broken backticks; existing project content unchanged.

**Step 4: Commit**

```bash
git add README.md
git commit -m "docs(plugin): append Claude Code Plugin section to project README"
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Finalize `marketplace.json`

**Type:** Infrastructure

**Files:**
- Modify: `.claude-plugin/marketplace.json`

**Step 1: Read current state**

```bash
cat .claude-plugin/marketplace.json
```

**Step 2: Replace contents**

```json
{
  "$schema": "https://anthropic.com/claude-code/marketplace.schema.json",
  "name": "local-library",
  "version": "0.1.0",
  "owner": {
    "name": "local-library contributors"
  },
  "metadata": {
    "description": "Local-library Claude Code plugin — skills for fluent use of the local-library MCP server in research, drafting, and verification workflows.",
    "homepage": "https://github.com/<owner>/local-library"
  },
  "plugins": [
    {
      "name": "local-library",
      "version": "0.1.0",
      "description": "Skills for fluently using the local-library MCP server: two orientation skills (citekey/library-first reach, extraction-quality safety hatch), one grounding kernel, three procedural composition skills (drafting, implementation-check, verify-claims).",
      "source": ".",
      "category": "research",
      "keywords": ["rag", "citations", "research", "local-library", "mcp", "grounding"]
    }
  ]
}
```

If the actual GitHub URL is known, substitute for the `homepage` placeholder.

**Step 3: Validate JSON**

```bash
uv run python -c "import json; m = json.load(open('.claude-plugin/marketplace.json')); print('plugins:', len(m['plugins']), 'name:', m['name'])"
```
Expected: `plugins: 1 name: local-library`

**Step 4: Commit**

```bash
git add .claude-plugin/marketplace.json
git commit -m "chore(plugin): finalize marketplace.json metadata"
```
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Install verification + permissions audit (human-gated)

**Type:** Infrastructure (verification template + manual fill-in)

**Files:**
- Create: `tests/skills/phase5/install-and-permissions-audit.md`

**Step 1: Write the audit template**

```bash
mkdir -p tests/skills/phase5
```

Write `tests/skills/phase5/install-and-permissions-audit.md`:

```markdown
# Phase 5 install + permissions audit

**Date:** <YYYY-MM-DD>
**Operator:** <user-name>

## External-user install path

From a fresh shell, NOT inside an active Claude Code session:

1. `cd /tmp && rm -rf local-library-test`
2. `git clone /Users/strophios/development/local-library/.worktrees/local-library-plugin /tmp/local-library-test` (or the canonical remote once published)
3. `cd /tmp/local-library-test && uv sync`
4. Open Claude Code in any project (NOT necessarily this repo).
5. `/plugin marketplace add /tmp/local-library-test`
6. `/plugin install local-library`

Record:
- [ ] `uv sync` completed without error
- [ ] `/plugin marketplace add` reported the marketplace as added
- [ ] `/plugin install` reported the plugin as installed
- [ ] Six skills are listed: <list as Claude Code reports>
- [ ] Four MCP tools are listed: `mcp__local-library__{search_library, show_document, list_documents, get_document_text}`

## Permissions audit

In the same session, exercise each skill:

1. Bare-citekey lookup: "What does @<real-citekey> argue?"
   - [ ] No per-call approval prompts; tools fire silently
2. Garbled-extraction fallback: "Open @<mathy-citekey> and explain the main equation."
   - [ ] No prompt for `Read` invocation on the PDF
3. Atomic grounding via kernel.
   - [ ] No prompts during retrieve/widen/synthesize
4. Drafting (`drafting-with-grounded-sources` with a 2-source prompt).
   - [ ] No prompts during decomposition or grounding
5. Implementation-check on a small file.
   - [ ] No prompts during the assertion-table flow
6. Verify-claims on three claims.
   - [ ] No prompts during the claim-table flow

## Skill body audit

- [ ] No skill body inlines a `Bash` invocation that is not declared in its `allowed-tools` (grep each `SKILL.md` for backtick-bash patterns; if any appear, either add `Bash` to `allowed-tools` or rewrite the skill to use a different tool)

## Findings

- Per-call approvals observed: <count, with notes>
- Skills missing from list: <none / list>
- Tools missing from list: <none / list>
- Any unexpected behavior: <free text>

## Assessment

PASS / PARTIAL / FAIL — one-sentence justification.

If FAIL or PARTIAL:
- For permission prompts on tools that should be in `allowed-tools`: patch the relevant SKILL.md frontmatter; commit; re-run.
- For missing skills: investigate plugin install or skill discovery; do not proceed to Phase 6.
- For missing tools: investigate `.mcp.json` interpolation of `${CLAUDE_PLUGIN_ROOT}`; check `uv run local-library-mcp` works from the installed plugin path.
```

**Step 2: Commit the template**

```bash
git add tests/skills/phase5/install-and-permissions-audit.md
git commit -m "test(plugin): Phase 5 install + permissions audit template (to be filled by user)"
```

**Step 3: Pause and request user run**

Report to user:

> Phase 5 Task 3 requires manual install verification. Please:
>
> 1. Open `tests/skills/phase5/install-and-permissions-audit.md`.
> 2. Follow its steps in a fresh Claude Code session.
> 3. Fill in checkboxes and findings.
> 4. Commit: `git add tests/skills/phase5/install-and-permissions-audit.md && git commit -m "test(plugin): record Phase 5 install + permissions audit results"`.
> 5. If PARTIAL or FAIL, return to the relevant phase before Phase 6.
<!-- END_TASK_3 -->

---

## Done when

- `README.md` at repo root has a `## Claude Code Plugin` section appended with install, architectural overview, skills-at-a-glance, test-drive scenarios, disabling/overriding, and a pointer to the design plan; existing project content unchanged
- `.claude-plugin/marketplace.json` finalized
- `tests/skills/phase5/install-and-permissions-audit.md` filled in by user, assessed PASS — fresh-session install via `/plugin marketplace add` + `/plugin install` produces a functional plugin with zero per-call approval prompts during normal use
