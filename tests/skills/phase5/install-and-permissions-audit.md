# Phase 5 install + permissions audit

**Date:** <2026-04-30>
**Operator:** <strophios>

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

- [x] `uv sync` completed without error
- [x] `/plugin marketplace add` reported the marketplace as added (no schema validation errors)
- [x] `/plugin install local-library@local-library` reported the plugin as installed
- [x] Six skills are listed when Claude Code surfaces available skills:
  - [x] `using-local-library-mcp`
  - [x] `handling-extraction-quality`
  - [x] `grounding-against-library`
  - [x] `drafting-with-grounded-sources`
  - [x] `implementation-check-against-papers`
  - [x] `verifying-claims-against-library`
- [x] Four MCP tools are reachable:
  - [x] `mcp__local-library__search_library`
  - [x] `mcp__local-library__show_document`
  - [x] `mcp__local-library__list_documents`
  - [x] `mcp__local-library__get_document_text`

## Permissions audit

In the same session, exercise each skill with a small representative prompt. Watch for per-call approval prompts; record any that fire.

### 1. Bare-citekey lookup (orientation: using-local-library-mcp)

Prompt: "What does @<real-citekey-from-your-library> argue?"

- [x] No per-call approval prompts on `mcp__local-library__show_document`
- [x] No per-call approval prompts on `mcp__local-library__get_document_text`
- [x] Skill fires automatically without manual selection
- [x] Notes: Approval was required on first use for both skills, but not on subsequent uses. 

### 2. Garbled-extraction fallback (orientation: handling-extraction-quality)

Prompt: "Open @<mathy-citekey-from-your-library> and explain the main equation."

- [x] No per-call approval prompts on `mcp__local-library__show_document`
- [x] No per-call approval prompts on `mcp__local-library__get_document_text`
- [x] No per-call approval prompts on `Read` (when invoked on the PDF)
- [x] Skill correctly evaluates markdown for garbling cues; escalates to PDF only when cues fire
- [x] Notes: Again, all tools required approval on first use (so the `Read` and `mcp__local-library__search_library` tools in this case). 

### 3. Atomic grounding via kernel (grounding-against-library)

Prompt: "Verify the claim that @<real-citekey> says <specific assertion>."

- [x] No per-call approval prompts during retrieve / widen / synthesize
- [x] Kernel produces per-source table with quoted excerpts and chunk indices
- [x] Notes: Perfect, no notes. 

### 4. Drafting (drafting-with-grounded-sources)

Prompt: "Draft a paragraph defending the claim that <X> using @<A> and @<B>."

- [x] No per-call approval prompts during decomposition / kernel invocations / appendix construction
- [x] Output has inline `@citekeys` + grounding-summary appendix at the end
- [x] Notes: Perfect, only note is that we might consider instructions to format the in-draft citations as "\[@citekey, p. chunk number\]" to match pandoc-citeproc syntax by pretending that the chunk number is a page number. But we may actually want to keep the friction of having to hand adjust any references (i.e., reformat and either delete the chunk number or replace with page number) so that we don't ever accidentally just leave the chunk number as page number. 

### 5. Implementation-check (implementation-check-against-papers)

Prompt: "Compare <some-small-file>.py against the method described in @<relevant-citekey>."

- [x] No per-call approval prompts during code-Read / kernel invocations / cross-invocation of handling-extraction-quality (if math involved)
- [x] Output is an assertion table with status (match/mismatch/partial/not-found) and quoted evidence
- [x] Notes: Perfect, no notes. 

### 6. Verify-claims (verifying-claims-against-library)

Prompt: "Verify these claims against my library:
1. <claim 1> — per @<X>
2. <claim 2> — per @<Y>
3. <claim 3 — fabricated> — per @<Z>"

- [x] No per-call approval prompts during multi-claim grounding
- [x] Output is a claim table with quoted support, status per row, and a summary line
- [x] Fabricated claim correctly tagged not-found (or mismatch with contradicting evidence)
- [x] Notes: Prefect, quite strict (which is what we want as opposed to being more loose and permissive), and handled a "oh, actually, what if we look at that claim with @new-source too?" gracefully. 

## Skill body audit

For each skill, grep its `SKILL.md` for any inline tool invocations that are not declared in its `allowed-tools` frontmatter:

```bash
for skill in skills/*/; do
  echo "=== $skill ==="
  grep -E '`Bash\(|`Edit\(|`Write\(|`Glob\(|`Grep\(' "$skill/SKILL.md" || echo "  (no undeclared tools)"
done
```

- [x] No skill body inlines a tool invocation that isn't declared in its `allowed-tools` (Bash/Edit/Write/Glob/Grep are common culprits)
- If any appear: either add the tool to that skill's `allowed-tools` frontmatter or rewrite the skill body to use a different tool

## Findings

- **Per-call approvals observed**: 0
- **Skills missing from list**: none
- **Tools missing from list**: none
- **Schema validation errors at marketplace-add or install**: none
- **Any unexpected behavior**: As noted in various skill notes above, each MCP tool required approval on first use, but not thereafter. 

## Assessment

PASS - all tests passed with no unexpected behavior. The requirement for one-time MCP tool approval is totally fine, so far as I am concerned. 

If FAIL or PARTIAL:

- For permission prompts on tools that should be in `allowed-tools`: patch the relevant `SKILL.md` frontmatter; commit; re-run the affected scenario.
- For missing skills in the listing: investigate plugin install (likely a frontmatter parse error, a misnamed skill directory, or a missing `SKILL.md` at the expected path). Do not proceed to Phase 6.
- For missing MCP tools: investigate `.mcp.json` interpolation of `${CLAUDE_PLUGIN_ROOT}`; check `uv run local-library-mcp` works from the installed plugin path (`~/.claude/plugins/cache/local-library@local-library` or similar) without errors.
- For schema-validation errors at marketplace-add: re-check `.claude-plugin/marketplace.json`'s `source` field — must start with `./` and point at a real directory; the plan's `.` form fails (this is the issue addressed by commit `49db670`).
