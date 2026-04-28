# Phase 5 install + permissions audit

**Date:** <YYYY-MM-DD>
**Operator:** <user-name>

This audit is performed manually by the user (operator) from a fresh shell, NOT inside the orchestrator's Claude Code session. The orchestrator's session has the plugin's MCP tools already loaded from session start; auditing install + permissions correctly requires a session that loads the plugin from a clean state.

## External-user install path

Pretend you are an external user discovering the plugin for the first time. Run from a fresh shell, NOT inside an active Claude Code session:

1. `cd /tmp && rm -rf local-library-test`
2. `git clone /Users/strophios/development/local-library/.worktrees/local-library-plugin /tmp/local-library-test` (or the canonical remote URL `https://github.com/strophios/local-library` once published)
3. `cd /tmp/local-library-test && uv sync`
4. Open Claude Code in any project (NOT necessarily this repo). The point is to verify the plugin works from arbitrary working directories.
5. `/plugin marketplace add /tmp/local-library-test`
6. `/plugin install local-library@local-library`

Record observations:

- [ ] `uv sync` completed without error
- [ ] `/plugin marketplace add` reported the marketplace as added (no schema validation errors)
- [ ] `/plugin install local-library@local-library` reported the plugin as installed
- [ ] Six skills are listed when Claude Code surfaces available skills:
  - [ ] `using-local-library-mcp`
  - [ ] `handling-extraction-quality`
  - [ ] `grounding-against-library`
  - [ ] `drafting-with-grounded-sources`
  - [ ] `implementation-check-against-papers`
  - [ ] `verifying-claims-against-library`
- [ ] Four MCP tools are reachable:
  - [ ] `mcp__local-library__search_library`
  - [ ] `mcp__local-library__show_document`
  - [ ] `mcp__local-library__list_documents`
  - [ ] `mcp__local-library__get_document_text`

## Permissions audit

In the same session, exercise each skill with a small representative prompt. Watch for per-call approval prompts; record any that fire.

### 1. Bare-citekey lookup (orientation: using-local-library-mcp)

Prompt: "What does @<real-citekey-from-your-library> argue?"

- [ ] No per-call approval prompts on `mcp__local-library__show_document`
- [ ] No per-call approval prompts on `mcp__local-library__get_document_text`
- [ ] Skill fires automatically without manual selection
- [ ] Notes: <free text>

### 2. Garbled-extraction fallback (orientation: handling-extraction-quality)

Prompt: "Open @<mathy-citekey-from-your-library> and explain the main equation."

- [ ] No per-call approval prompts on `mcp__local-library__show_document`
- [ ] No per-call approval prompts on `mcp__local-library__get_document_text`
- [ ] No per-call approval prompts on `Read` (when invoked on the PDF)
- [ ] Skill correctly evaluates markdown for garbling cues; escalates to PDF only when cues fire
- [ ] Notes: <free text>

### 3. Atomic grounding via kernel (grounding-against-library)

Prompt: "Verify the claim that @<real-citekey> says <specific assertion>."

- [ ] No per-call approval prompts during retrieve / widen / synthesize
- [ ] Kernel produces per-source table with quoted excerpts and chunk indices
- [ ] Notes: <free text>

### 4. Drafting (drafting-with-grounded-sources)

Prompt: "Draft a paragraph defending the claim that <X> using @<A> and @<B>."

- [ ] No per-call approval prompts during decomposition / kernel invocations / appendix construction
- [ ] Output has inline `@citekeys` + grounding-summary appendix at the end
- [ ] Notes: <free text>

### 5. Implementation-check (implementation-check-against-papers)

Prompt: "Compare <some-small-file>.py against the method described in @<relevant-citekey>."

- [ ] No per-call approval prompts during code-Read / kernel invocations / cross-invocation of handling-extraction-quality (if math involved)
- [ ] Output is an assertion table with status (match/mismatch/partial/not-found) and quoted evidence
- [ ] Notes: <free text>

### 6. Verify-claims (verifying-claims-against-library)

Prompt: "Verify these claims against my library:
1. <claim 1> — per @<X>
2. <claim 2> — per @<Y>
3. <claim 3 — fabricated> — per @<Z>"

- [ ] No per-call approval prompts during multi-claim grounding
- [ ] Output is a claim table with quoted support, status per row, and a summary line
- [ ] Fabricated claim correctly tagged not-found (or mismatch with contradicting evidence)
- [ ] Notes: <free text>

## Skill body audit

For each skill, grep its `SKILL.md` for any inline tool invocations that are not declared in its `allowed-tools` frontmatter:

```bash
for skill in skills/*/; do
  echo "=== $skill ==="
  grep -E '`Bash\(|`Edit\(|`Write\(|`Glob\(|`Grep\(' "$skill/SKILL.md" || echo "  (no undeclared tools)"
done
```

- [ ] No skill body inlines a tool invocation that isn't declared in its `allowed-tools` (Bash/Edit/Write/Glob/Grep are common culprits)
- If any appear: either add the tool to that skill's `allowed-tools` frontmatter or rewrite the skill body to use a different tool

## Findings

- **Per-call approvals observed**: <count, with per-skill notes>
- **Skills missing from list**: <none / list>
- **Tools missing from list**: <none / list>
- **Schema validation errors at marketplace-add or install**: <none / details>
- **Any unexpected behavior**: <free text>

## Assessment

PASS / PARTIAL / FAIL — one-sentence justification.

If FAIL or PARTIAL:

- For permission prompts on tools that should be in `allowed-tools`: patch the relevant `SKILL.md` frontmatter; commit; re-run the affected scenario.
- For missing skills in the listing: investigate plugin install (likely a frontmatter parse error, a misnamed skill directory, or a missing `SKILL.md` at the expected path). Do not proceed to Phase 6.
- For missing MCP tools: investigate `.mcp.json` interpolation of `${CLAUDE_PLUGIN_ROOT}`; check `uv run local-library-mcp` works from the installed plugin path (`~/.claude/plugins/cache/local-library@local-library` or similar) without errors.
- For schema-validation errors at marketplace-add: re-check `.claude-plugin/marketplace.json`'s `source` field — must start with `./` and point at a real directory; the plan's `.` form fails (this is the issue addressed by commit `49db670`).
