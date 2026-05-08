# Local-Library Plugin — Test-Drive Write-Up

**Date:** 2026-05-08
**Plugin version:** 0.1.0 (initial release)
**Branch:** `local-library-plugin` (39 commits on top of main)

## Smoke-test results

| # | Scenario | Skill(s) tested | Status | Notes |
|---|----------|------------------|--------|-------|
| a | Citekey trigger via orientation | `using-local-library-mcp` + `handling-extraction-quality` | **PASS** | 10 tool_uses; agent disambiguated "section 3" (no numbered sections in document), walked through 4 named "moves" with line-number citations + verbatim quotes; proactively flagged broken-table garbling cues without forcing PDF escalation |
| b | Impl-check decomposition + assertion table | `implementation-check-against-papers` + kernel + `handling-extraction-quality` | **PASS** | 11 tool_uses; pair-note hypothesis (chunking.py × @Ruder2019) turned out to be a false-friend trap — agent caught that "chunking" in @Ruder2019 means BIO-tagged shallow parsing, not retrieval chunking; all 9 rows correctly tagged not-found with explicit search-scope description |
| c | Verify-claims + claim table | `verifying-claims-against-library` + kernel | **PASS** | 10 tool_uses; status distribution 1 match / 0 partial / 2 mismatch / 0 not-found — agent caught Claim 2's added qualifier as outright mismatch (Bloemraad explicitly rejects the white-vs-Latino contrast) and Claim 3's fabricated attribution as inverting Meyer's actual position (he's defending PPT, not abandoning it) |
| d | Drafting + grounding-summary appendix | `drafting-with-grounded-sources` + kernel | **PASS** | 15 tool_uses; 4 propositions decomposed, prose with inline `@citekeys`, full appendix; agent honestly handled the asymmetric source load (substantive @Goodwin1999 vs peripheral @Bloemraad2015) by tagging Bloemraad rows as `partial` with explicit caveat and recommending better source candidates for heavier load |
| e | Garbled-math PDF fallback | `handling-extraction-quality` + `using-local-library-mcp` | **PASS** | 7 tool_uses (after 3 prior attempts; see transcript history); recalibration-aware behavior — agent inspected equations 3.21-3.24, found bodies are clean LaTeX (despite `\n(N)` escape-sequence remnants at equation TAILS), correctly used markdown as source per the "well-formed LaTeX is success" calibration; cited line-level provenance per equation |

## DoD audit (from design doc)

- [x] **Plugin checked into the repo** with the four-component structure (`.claude-plugin/`, `.mcp.json`, `skills/`, README) — verified via `git ls-files | grep -E "(claude-plugin|skills/|.mcp.json)"`. All four components present.
- [x] **Six skills delivered**, all in `skills/`:
  - `using-local-library-mcp/SKILL.md`
  - `handling-extraction-quality/SKILL.md`
  - `grounding-against-library/SKILL.md` + `references/tool-selection.md`
  - `drafting-with-grounded-sources/SKILL.md`
  - `implementation-check-against-papers/SKILL.md`
  - `verifying-claims-against-library/SKILL.md`
- [x] **Always-apply orientation fires without instruction** — Smoke (a) confirms `using-local-library-mcp` triggers on a conversational "I was reading @Goodwin1999..." prompt without being told; Smoke (e) confirms `handling-extraction-quality` triggers on math-equation prompts proactively. Phase 5 install audit also independently confirmed both fire on the user's interactive testing.
- [x] **Three procedural skills deploy when triggers fire** — Smoke (b) confirms `implementation-check-against-papers` produces an assertion table on a code-vs-paper comparison prompt; Smoke (c) confirms `verifying-claims-against-library` produces a claim table with summary line on a multi-claim verification prompt; Smoke (d) confirms `drafting-with-grounded-sources` produces prose + grounding-summary appendix on a Shape-A claim-supplied drafting prompt.
- [x] **Safety hatch fires on garbled extraction** — Smoke (e) (via attempt 3) confirms `handling-extraction-quality` recognizes `\n(N)` escape-sequence remnants as genuine garbling cues; the recalibrated SKILL correctly distinguishes these from well-formed LaTeX (the success case). Smoke (a) also independently demonstrates the safety hatch firing on broken markdown tables.
- [x] **No per-tool-call approval friction in ordinary use** — Phase 5 install audit by user (commit `4e60512`) recorded zero per-call approvals across all six skills. One-time MCP tool approval at first use is the standard Claude Code pattern, not a per-call issue. User assessed: "PASS - all tests passed with no unexpected behavior."
- [x] **Single-command install** via `/plugin marketplace add <path>` + `/plugin install local-library@local-library` — Phase 5 install audit confirmed both commands work cleanly with the post-`49db670` `source: "./"` fix.
- [x] **Plugin-bundled-with-repo placement** — repo structure verified: `.claude-plugin/`, `.mcp.json`, `skills/` all at repo root; the same repo provides the Python MCP server it references via `${CLAUDE_PLUGIN_ROOT}` interpolation.
- [x] **MCP server registered via plugin's `.mcp.json` using `${CLAUDE_PLUGIN_ROOT}`** — Phase 1 Task 8 (commit `eacb520`) and Phase 5 install audit confirm: the `.mcp.json` at repo root uses `--directory ${CLAUDE_PLUGIN_ROOT}` for `uv run local-library-mcp`, resolves correctly at install time, and surfaces the four `mcp__local-library__*` tools to Claude Code sessions.

## Observed behavior

The plugin's three-layer architecture (orientation → kernel → procedural composition) held up cleanly across all five smoke scenarios. Several patterns recurred and are worth flagging:

**The skills exceeded test design in multiple instances.** Phase 4's verify-claims Tier-3 caught a Wang2012-vs-Earl2004 attribution error I hadn't constructed for. Phase 6's smoke (c) caught Bloemraad et al.'s explicit rejection of the white-vs-Latino contrast my designed-partial claim asserted. Smoke (b) caught the chunking-as-retrieval-vs-chunking-as-shallow-parsing false friend without forcing matches on terminology overlap. The discipline of "quote the specific claim, not topical overlap" is genuinely doing work — false-positive matches would have been the easier failure mode and the SKILLs consistently avoided it.

**Multi-source asymmetry handled honestly.** Smoke (d)'s drafting test paired substantive @Goodwin1999 with peripheral @Bloemraad2015. The dispatched agent didn't try to balance the prose by inflating Bloemraad's contribution; instead it correctly positioned Bloemraad as providing field-level diagnostic support (a historiographical premise) and tagged those rows `partial` with explicit caveat. The "Caveats" section's recommendation of better source candidates for heavier Bloemraad-side load is bonus discipline beyond the SKILL's required output.

**Recalibration-aware extraction-quality behavior.** The post-`cd75136` "well-formed LaTeX is success, NOT garbling" recalibration paid off in Smoke (e): the dispatched agent inspected equations 3.21-3.24, found the equation bodies are clean LaTeX (despite `\n(N)` escape-sequence remnants at equation tails), and correctly used the markdown as source rather than forcing PDF escalation. A pre-recalibration version would have flagged `$$...$$` blocks themselves as garbling cues and triggered unnecessary PDF reads on cleanly-extracted papers.

**Surprising-but-correct behaviors emerged from skill composition.** Smoke (e)'s third attempt demonstrated kernel-scope-guardrail-shaped graceful disambiguation behavior on an ambiguous prompt ("the loss function" in a 300+ page thesis with multiple loss functions), even though no formal scope guardrail is declared in the orientation skills. The discipline propagated from the kernel to its caller-context naturally.

## Gaps and candidate refinements

- **Description tuning**: discovery worked well in interactive testing across all skills. The two known-corrected gaps (`handling-extraction-quality`'s symptom-only triggers fixed in `ea3bdfb`+`1cb88dc`+`cd75136`; `drafting-with-grounded-sources`'s over-claim of exploration territory fixed in `83e1d69`) are post-fix verified. No further description-vs-discovery issues observed.
- **Procedure precision**: the kernel's six-step procedure produces consistent shape across direct invocations and procedural-skill compositions. No procedure precision issues observed.
- **Cross-skill flow**: orientation→kernel and kernel→procedural handoffs were not heavily tested in autonomous tests (skills are inlined into dispatched agents rather than discovered via Claude Code's plugin loader). The user's interactive testing in Phase 5 audit independently verified that real cross-skill invocation works.
- **Output-format edge cases**:
  - Citekey rendering: GREEN 3B's dispatched agent rendered `@Vaswani2017` as `@Vaswani_2017` (with underscore) in its grounding report. Real grounding was correct; only the report formatting deviated. Worth normalizing in Phase 4 procedural skills that consume kernel reports.
  - **Citation formatting in drafting** (from Phase 5 audit notes): user observed that drafting's inline citations use `(@citekey)` format; pandoc-citeproc syntax `[@citekey, p. N]` would be more usable for downstream processing. User's reasoning: keeping the friction (chunk number ≠ page number) prevents accidental misrepresentation. Worth considering as a future SKILL refinement, but not urgent.
- **MCP tool gaps**: the four read-only tools (search_library, show_document, list_documents, get_document_text) are sufficient for all six skills' procedures. No additional tools requested in any test.
- **Documentation gaps**: README's "Test-drive scenarios" section provides clear post-install verification steps. The `.claude-plugin/marketplace.json` schema gotcha (`source: "."` fails validation, must be `source: "./"`) is captured in the install-audit template's troubleshooting section but worth surfacing in the README too if external users hit it.

## Methodology lessons (orchestrator-side)

These aren't gaps in the plugin itself but observations from the build-and-test process worth capturing:

- **Subagent dispatch reliability**: `task-implementor-fast` does not reliably dispatch nested general-purpose subagents — three independent attempts during Phases 1-2 produced impersonation rather than dispatch. Going forward, orchestrators should handle subagent dispatches directly when verification depends on authentic unprimed-agent behavior.
- **Recurring `.gitkeep` omission**: SKILL-authoring task-implementor dispatches consistently failed to capture the sibling `.gitkeep` deletion alongside the SKILL.md addition unless the prompt used explicit `git rm` invocation. The Phase 3 onward fix (explicit `git rm` instruction) worked.
- **YAML colon footgun**: SKILL descriptions with inline colons (e.g., `**Status:** needs_review`) break plain-scalar YAML parsing. Folded scalar (`description: >-`) sidesteps the issue and should be the default for skill descriptions going forward.
- **MCP availability for parallel subagents**: intermittent in this orchestrator session; smoke (e) needed four attempts (two of which hit the unavailability). Sequential dispatch may be more reliable than parallel for tests that depend on MCP.

## Follow-up work (recorded for future passes)

- [ ] Surface the `.claude-plugin/marketplace.json` `source` schema gotcha (`./` not `.`) in the README's "Where the plugin's pieces live" section, since external users discovering the marketplace.json file would otherwise hit the same validation error
- [ ] Citekey-rendering normalization in procedural skills that consume kernel reports (catch `@Vaswani_2017` underscore drift before it reaches user-facing output)
- [ ] Pandoc-citeproc-compatible citation formatting investigation (per Phase 5 audit note 4 on drafting): cost/benefit of `[@citekey, p. N]` syntax with chunk-vs-page friction preserved
- [ ] Re-test smoke (e) with a fresh fully-specified equation prompt once MCP availability for parallel subagents stabilizes (current PASS is a single-attempt result on attempt 4)
- [ ] **Fast-follows from the design doc**:
  - `literature-synthesis` skill (cross-source synthesis at the literature-review level, beyond the per-paragraph drafting scope of `drafting-with-grounded-sources`)
  - subagent wrappers for the procedural skills (so heavyweight grounding work happens in a fresh-context subagent rather than the user's main session, to avoid context bloat on long drafts)
  - neovim REPL integration (the original headline use case the plugin is meant to support — citekey workflows in editor)
- [ ] **Plan annotations carried forward**: the KNOWN ISSUE comment in `phase_02.md` (commit `ae20429`) documents the cue-list conflation that the recalibrated `handling-extraction-quality` SKILL fixes. If the implementation plan is re-executed from scratch, the recalibration must be applied at SKILL-authoring time rather than as a post-hoc fix.

## Final assessment

**PASS.**

All nine DoD criteria met. All five smoke scenarios PASS, three of them with structural shape exceeding the test design. Phase 5's user-driven install + permissions audit returned PASS with zero per-call approvals. The plugin installs cleanly via `/plugin marketplace add` + `/plugin install local-library@local-library`, surfaces all six skills + four MCP tools, and operates without per-call approval friction. The recurring methodology lessons from the build process (subagent-dispatch reliability, `.gitkeep` discipline, YAML-colon footgun, MCP availability) are captured for future plan execution.

The plugin is ready to ship at `0.1.0`. The follow-up work list documents refinements that would come in a `0.2.0` rather than blocking the initial release.
