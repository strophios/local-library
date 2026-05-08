# Local-Library Claude Code Plugin Implementation Plan — Phase 6

**Goal:** Run end-to-end smoke tests covering the five DoD-critical scenarios (citekey trigger, impl-check, verify-claims, drafting, garbled-math fallback); aggregate results with a test-drive write-up that audits all DoD criteria.

**Architecture:** Smoke tests have two complementary forms — subagent-based (automatable, with skill content inlined) and in-session (human-gated, relying on real always-apply discovery). Both are necessary for the design's "fluency" criterion to be honestly verified.

**Tech Stack:** Same as prior phases.

**Scope:** 6 of 6 phases.

**Codebase verified:** 2026-04-24

---

## Executing-engineer context

- **All Phase 1–5 deliverables must be complete and verified** before Phase 6 starts. Phase 5's install audit is the final gate — if it FAIL/PARTIAL, fix Phase 1 (`.mcp.json`) or Phase 2–4 (skill `allowed-tools`) before proceeding.
- **Smoke tests use fresh scenarios** (different citekeys, code files, claims than the GREEN/Tier-3 tests in Phases 2–4). Reusing the same scenarios would test memorization, not capability.
- **In-session smoke tests are the final gate.** A scenario that PASSes in subagent-inlined form but FAILs in a real session means the gap is in skill *discovery* (description tuning), not in skill *content*. The write-up surfaces this distinction.

---

## Tasks

<!-- START_TASK_1 -->
### Task 1: Orientation-layer smoke tests (a + e)

**Type:** Functionality

**Files:**
- Create: `tests/skills/phase6/smoke-a-citekey-trigger.md`
- Create: `tests/skills/phase6/smoke-e-garbled-math-fallback.md`

**Step 1: Smoke (a) — bare citekey triggers library lookup**

```bash
mkdir -p tests/skills/phase6
```

Pick `<NEW_CITEKEY>` from `uv run local-library list --limit 30` — choose one not used in earlier verifications.

Dispatch general-purpose subagent. Inline both orientation skills (`using-local-library-mcp` + `handling-extraction-quality`) as operative context. Conversational scenario (deliberately not a directive):

```
[Inline both orientation SKILL.md bodies]

I was reading @<NEW_CITEKEY> last night and got a bit lost in section 3. Can you help me make sense of what the author is doing there?
```

Capture full response.

Write `tests/skills/phase6/smoke-a-citekey-trigger.md`:

```markdown
# Smoke (a): citekey trigger via orientation

**Date:** <YYYY-MM-DD>
**Citekey:** @<NEW_CITEKEY>

## Scenario (verbatim)
> <prompt>

## Subagent response (verbatim)
<full response>

## Structural assessment
- [x/✗] Subagent invoked `mcp__local-library__show_document` (or `search_library`) without being told
- [x/✗] Subagent quoted excerpts from the actual document, not summaries from training
- [x/✗] If `show_document` reported `**Status:** needs_review`, subagent cross-invoked `handling-extraction-quality`

## Assessment
PASS / PARTIAL / FAIL.

**Final:** <PASS or PARTIAL or FAIL>
```

**Step 2: Smoke (e) — garbled-math triggers PDF fallback**

Pick a math-heavy citekey (`<CITEKEY_MATH_NEW>` — prefer one not used in RED baseline 3).

Dispatch subagent with both orientation skills inlined. Scenario:

```
[Inline both orientation SKILL.md bodies]

I'm trying to understand the loss function in @<CITEKEY_MATH_NEW>. The way it's written in the paper is throwing me. Can you walk me through it term by term?
```

Capture full response.

Write `tests/skills/phase6/smoke-e-garbled-math-fallback.md`:

```markdown
# Smoke (e): garbled-math PDF fallback

**Date:** <YYYY-MM-DD>
**Citekey:** @<CITEKEY_MATH_NEW>

## Scenario (verbatim)
> <prompt>

## Subagent response (verbatim)
<full response>

## Structural assessment
- [x/✗] Subagent called `show_document` to get PDF path
- [x/✗] On garbled math (or `Status: needs_review`), subagent invoked `Read` on the PDF
- [x/✗] Subagent did NOT ask the user to retype the equation
- [x/✗] Subagent cited a PDF page number in its explanation

## Assessment
PASS / PARTIAL / FAIL.

**Final:** <PASS or PARTIAL or FAIL>
```

**Step 3: Commit**

```bash
git add tests/skills/phase6/smoke-a-citekey-trigger.md tests/skills/phase6/smoke-e-garbled-math-fallback.md
git commit -m "test(plugin): Phase 6 orientation-layer smoke tests (a, e)"
```

**Step 4: Refactor any FAIL**

If orientation didn't trigger or fallback didn't fire: failure mode is (i) skill description not broad enough for discovery, or (ii) skill content not concrete enough to drive behavior. Patch the relevant SKILL.md and re-run.
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Procedural-skill smoke tests (b + c + d)

**Type:** Functionality

**Files:**
- Create: `tests/skills/phase6/smoke-b-impl-check.md`
- Create: `tests/skills/phase6/smoke-c-verify-claims.md`
- Create: `tests/skills/phase6/smoke-d-drafting.md`

**Step 1: Smoke (b) — implementation-check end-to-end**

Pick a code module + paper pair distinct from the Phase 4 Tier-3 scenario. For example: a different file under `src/local_library/embeddings/` or `src/local_library/ingestion/` and a corpus paper that plausibly addresses the same concern.

Dispatch subagent with `implementation-check-against-papers` SKILL.md + kernel SKILL.md + tool-selection.md + `handling-extraction-quality` inlined. Scenario:

```
[Inline skills]

Compare <FILE> against the method described in @<CITEKEY>. Where do they agree and where do they diverge?
```

Capture full response.

Write `tests/skills/phase6/smoke-b-impl-check.md`:

```markdown
# Smoke (b): implementation-check end-to-end

**Date:** <YYYY-MM-DD>
**Code file:** <FILE>
**Paper:** @<CITEKEY>

## Scenario (verbatim)
> <prompt>

## Subagent response (verbatim)
<full response>

## Structural assessment
- [x/✗] Decomposition step fired — claims enumerated as separate rows
- [x/✗] Kernel invoked per claim (visible in tool-call sequence)
- [x/✗] Assertion table produced with all required columns
- [x/✗] Each `match` / `mismatch` row has a quoted excerpt
- [x/✗] If equations were involved, `handling-extraction-quality` was invoked OR markdown was sufficient

## Assessment
PASS / PARTIAL / FAIL.

**Final:** <PASS or PARTIAL or FAIL>
```

**Step 2: Smoke (c) — verify-claims end-to-end**

Construct a fresh three-claim scenario (different citekeys than Phase 4 Task 6):
- Claim 1: a true claim (expect match/partial)
- Claim 2: a true claim with an invented qualifier (expect partial)
- Claim 3: a fabricated claim (expect not-found/mismatch)

Dispatch subagent with `verifying-claims-against-library` + kernel + tool-selection inlined. Scenario:

```
[Inline skills]

Verify these claims against my library:

1. "<true claim>" — per @<X>
2. "<qualifier-stripped claim>" — per @<Y>
3. "<fabricated claim>" — per @<Z>
```

Capture full response.

Write `tests/skills/phase6/smoke-c-verify-claims.md`:

```markdown
# Smoke (c): verify-claims end-to-end

**Date:** <YYYY-MM-DD>
**Claims:**
1. <claim 1 — expected: match/partial>
2. <claim 2 — expected: partial>
3. <claim 3 — expected: not-found/mismatch>

## Subagent response (verbatim)
<full response>

## Structural assessment
- [x/✗] Three rows in the claim table (one per claim)
- [x/✗] Each row has quoted support (or `<none>` for not-found)
- [x/✗] Statuses align with expected
- [x/✗] Summary line present

## Assessment
PASS / PARTIAL / FAIL.

**Final:** <PASS or PARTIAL or FAIL>
```

**Step 3: Smoke (d) — drafting end-to-end**

Pick a topic with two corpus citekeys (fresh, not Phase 4 Task 2 reuse).

Dispatch subagent with `drafting-with-grounded-sources` + kernel + tool-selection inlined. Scenario:

```
[Inline skills]

Write a short paragraph on <topic> drawing from @<A> and @<B>. Engage with each source's specific claims.
```

Write `tests/skills/phase6/smoke-d-drafting.md`:

```markdown
# Smoke (d): drafting end-to-end

**Date:** <YYYY-MM-DD>
**Topic:** <topic>
**Citekeys:** @<A>, @<B>

## Scenario (verbatim)
> <prompt>

## Subagent response (verbatim)
<full response>

## Structural assessment
- [x/✗] Decomposition step fired (propositions enumerated)
- [x/✗] Kernel invoked per proposition
- [x/✗] Prose has inline `@citekeys` at every claim
- [x/✗] Grounding-summary appendix present with chunk indices

## Assessment
PASS / PARTIAL / FAIL.

**Final:** <PASS or PARTIAL or FAIL>
```

**Step 4: Commit**

```bash
git add tests/skills/phase6/smoke-b-impl-check.md tests/skills/phase6/smoke-c-verify-claims.md tests/skills/phase6/smoke-d-drafting.md
git commit -m "test(plugin): Phase 6 procedural-skill smoke tests (b, c, d)"
```

**Step 5: Refactor any FAIL**

For each failed smoke test, identify the structural break. Most likely: skill description didn't trigger discovery, or skill body didn't drive the prescribed output structure. Patch the relevant SKILL.md and re-run that specific smoke test until PASS. Do not proceed until all three are PASS.
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Test-drive write-up + DoD audit + final commit

**Type:** Documentation + verification

**Files:**
- Create: `tests/skills/phase6/test-drive-writeup.md`

**Step 1: Aggregate findings**

```bash
cat tests/skills/phase6/*.md tests/skills/phase5/install-and-permissions-audit.md
```

**Step 2: Write the synthesis**

Write `tests/skills/phase6/test-drive-writeup.md`:

```markdown
# Local-Library Plugin — Test-Drive Write-Up

**Date:** <YYYY-MM-DD>
**Plugin version:** 0.1.0 (initial release)

## Smoke-test results

| # | Scenario | Skill(s) tested | Status | Notes |
|---|----------|------------------|--------|-------|
| a | Citekey trigger via orientation | using-local-library-mcp | PASS/PARTIAL/FAIL | <one-line> |
| b | Impl-check decomposition + assertion table | implementation-check-against-papers + kernel + extraction-quality | PASS/PARTIAL/FAIL | <one-line> |
| c | Verify-claims + claim table | verifying-claims-against-library + kernel | PASS/PARTIAL/FAIL | <one-line> |
| d | Drafting + grounding-summary appendix | drafting-with-grounded-sources + kernel | PASS/PARTIAL/FAIL | <one-line> |
| e | Garbled-math PDF fallback | handling-extraction-quality + using-local-library-mcp | PASS/PARTIAL/FAIL | <one-line> |

## DoD audit (from design doc)

- [x/✗] **Plugin checked into the repo** with the four-component structure (.claude-plugin/, .mcp.json, skills/, README) — verify with `git ls-files | grep -E "(claude-plugin|skills/|.mcp.json)"`
- [x/✗] **Six skills delivered**: list them — confirm with `ls skills/`
- [x/✗] **Always-apply orientation fires without instruction** — Smoke (a), (e)
- [x/✗] **Three procedural skills deploy when triggers fire** — Smoke (b), (c), (d)
- [x/✗] **Safety hatch fires on garbled extraction** — Smoke (e)
- [x/✗] **No per-tool-call approval friction in ordinary use** — Phase 5 install audit
- [x/✗] **Single-command install** via `/plugin install local-library` — Phase 5 install audit
- [x/✗] **Plugin-bundled-with-repo placement** — repo structure
- [x/✗] **MCP server registered via plugin's `.mcp.json` using `${CLAUDE_PLUGIN_ROOT}`** — Phase 1 Task 8

## Observed behavior

[200–400 words. What actually happened across the five smoke tests. Highlight what exceeded expectations and what was surprisingly brittle.]

## Gaps and candidate refinements

[Free text. Categories:
- **Description tuning**: skills whose descriptions were too narrow or too broad
- **Procedure precision**: steps that produced inconsistent outputs
- **Cross-skill flow**: orientation → kernel → procedural handoffs that felt awkward
- **Output-format edge cases**: scenarios where the prescribed format didn't fit naturally
- **MCP tool gaps**: missing capabilities that would have made grounding cleaner
- **Documentation gaps**: things in README / SKILL.md that needed clarification]

## Follow-up work (recorded for future passes)

- [ ] <each gap that warrants action>
- [ ] <fast-follows from the design: `literature-synthesis` skill, subagent wrappers, neovim REPL integration, evaluation/retrieval-quality work>

## Final assessment

PASS / PASS WITH CAVEATS / FAIL.

Justification: <2–4 sentences>.
```

**Step 3: Commit**

```bash
git add tests/skills/phase6/test-drive-writeup.md
git commit -m "test(plugin): Phase 6 test-drive write-up + DoD audit"
```

**Step 4: Final human verification gate (in-session smoke tests)**

Report to user:

> Phase 6 subagent-based smoke tests are complete. To honor the design's "fluency in real sessions" criterion, please run the same five scenarios in a fresh plugin-enabled Claude Code session (no skill content inlined — relying on always-apply discovery). Compare your observations to the smoke transcripts.
>
> If a scenario PASSed in the subagent-inlined test but FAILs in the real session, the gap is in skill *discovery* (description tuning), not in skill *content*.
>
> Append observations to `tests/skills/phase6/test-drive-writeup.md` under a new `## In-session smoke results` section, then commit:
>
>     git add tests/skills/phase6/test-drive-writeup.md
>     git commit -m "test(plugin): record in-session smoke test observations"
>
> If everything PASSes, the implementation plan is complete and ready to merge to main.
<!-- END_TASK_3 -->

---

## Done when

- Five smoke transcripts under `tests/skills/phase6/` (a–e) all show PASS
- `tests/skills/phase6/test-drive-writeup.md` aggregates results, audits the DoD, documents observed behavior + gaps + follow-up work, ends with a final assessment
- User has appended in-session smoke results confirming scenarios PASS in a real plugin-enabled session (not just in subagent-inlined tests)
