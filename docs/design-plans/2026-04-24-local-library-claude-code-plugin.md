# Local-Library Claude Code Plugin Design

## Summary

This design specifies a Claude Code plugin — shipped inside the local-library repository — that makes fluent use of the library's MCP server a default behavior rather than an explicit user instruction. The plugin delivers six skills organized in three layers: two always-apply orientation skills that shape how Claude Code notices and reaches for the library without being asked; a shared grounding kernel that retrieves evidence from one or more library documents, widens context when needed, and synthesizes across sources with per-document citations; and three procedural skills that compose on that kernel for specific research workflows (drafting with grounded sources, checking code implementations against papers, and verifying textual claims against the library). Plugin delivery bundles MCP server registration alongside the skills, so a single install command wires up both.

The key architectural bets are: (1) delivering orientation as always-apply skills rather than CLAUDE.md entries, which is necessary because plugins cannot ship a user-global CLAUDE.md; (2) keeping the grounding kernel strictly atomic — one assertion per invocation, decomposition the caller's responsibility — so it composes cleanly without implicitly biasing toward single-source answers; and (3) plugin-in-repo placement rather than user-global or project-level, so the plugin travels with the library and is shareable while remaining usable from any project the user works in. The result is a system where a citekey appearing in conversation is enough to prompt library lookups, and where structured grounding with quoted evidence and cited sources is the path of least resistance rather than an afterthought.

## Definition of Done

**Primary deliverable:** A Claude Code plugin checked into this repo, containing:

- **(a) Orientation layer** — one or more always-apply skills covering citekey semantics, library-first contextual tool use, and the extraction-quality safety hatch (read the PDF directly via Claude Code's native `Read` tool when extracted markdown looks garbled for math, figures, or other structural content).
- **(b) Shared procedural sub-skill** `grounding-against-library` — the retrieve → compare → report kernel used by the procedural skills below. Supports multi-source grounding (a single assertion may draw on multiple library documents).
- **(c) Three procedural skills composing on the kernel:**
  - `drafting-with-grounded-sources` — writing/editing alongside the library as source-of-truth for claims and quotes.
  - `implementation-check-against-papers` — comparing code/implementation against method descriptions in one or more source papers, reporting mismatches with citations. Multi-source.
  - `verifying-claims-against-library` — checking whether the library supports given textual claims, quoting the supporting chunk. Multi-source.

**Success behavior:** Installed and active, the plugin causes Claude Code to reach for the local-library MCP tools fluently — without explicit user instruction — whenever citekeys or paper-related context appear. The three procedural skills deploy correctly when their triggers fire. The safety hatch fires when extracted markdown looks garbled for math/figures/etc. No per-tool-call approval friction in ordinary use (first-access approval acceptable).

**Portability posture:** Skills are written as clean markdown readable by other agents as reference documentation; auto-discovery only on Claude Code. Explicitly not pursuing auto-loadability on other agent harnesses.

**Out of scope for this design:**
- Literature synthesis skill (fast-follow, next design pass)
- Subagent wrappers around the skills (later extension)
- Neovim-as-REPL integration (separate subproject)
- Evaluation / retrieval-quality work (deferred per user; tracked in RAG Pipeline Improvements feature area)
- Auto-loadability on non-Claude-Code agent harnesses

## Glossary

- **MCP (Model Context Protocol)**: A protocol that exposes server-defined tools to a compatible AI agent; this project uses it to give Claude Code access to the local-library database via four read-only tools (`search_library`, `show_document`, `list_documents`, `get_document_text`).
- **MCP server**: The `local-library-mcp` process (started via `uv run local-library-mcp`) that exposes library tools over MCP's stdio transport.
- **Claude Code plugin**: A self-contained directory, declared via a `plugin.json` manifest, that bundles skills and optionally MCP server configuration for installation into Claude Code.
- **Skill**: A markdown file loaded into Claude Code's context that defines when and how Claude should exhibit a particular behavior; skills can be always-apply (loaded on session start) or manually invocable.
- **Always-apply skill**: A skill with a description broad enough that Claude Code's semantic discovery treats it as a candidate at the start of every session, so its guidance is active without explicit user invocation.
- **Orientation layer**: The two always-apply skills (`using-local-library-mcp`, `handling-extraction-quality`) whose purpose is to shape general Claude Code behavior — noticing library triggers, handling garbled extractions — rather than implement a specific user workflow.
- **Grounding kernel** (`grounding-against-library`): The shared atomic sub-skill that retrieves evidence for exactly one well-scoped assertion, widens context as needed, synthesizes across multiple sources, and reports with per-source citations. Composing skills invoke it once per assertion.
- **Citekey**: A short human-readable identifier for a document (e.g., `Smith2023`), BetterBibTeX-style, used throughout this system to refer to library documents without UUIDs.
- **`${CLAUDE_PLUGIN_ROOT}`**: An environment variable Claude Code sets to the installed plugin's root directory; used in `.mcp.json` so the MCP server path resolves correctly regardless of where the user cloned the repo.
- **Extraction-quality safety hatch**: The `handling-extraction-quality` skill's fallback behavior — when extracted markdown looks garbled (math, figures, tables), read the original PDF directly via Claude Code's native `Read` tool using the path from `show_document`, instead of trusting the extracted text.
- **Functional Core / Imperative Shell**: A code-organization pattern used throughout the codebase; pure transformation logic is separated from code with side effects (I/O, state). Referenced in this document as an existing project convention.
- **`allowed-tools` frontmatter**: A YAML field in a skill's frontmatter that declares which Claude Code tools the skill is permitted to call, used here to pre-authorize MCP tool calls and the native `Read` tool so no per-call approval prompt appears during a skill-driven workflow.
- **Decomposition step**: In each procedural skill, the first step that converts a broad user request into a set of atomic, independently groundable assertions before the grounding kernel is invoked for each.
- **Tier-1 / Tier-3 testing**: A testing tiering used in this design. Tier-1 involves full RED-GREEN-REFACTOR with isolated failure-mode scenarios (applied to orientation and kernel skills). Tier-3 uses realistic end-to-end scenarios (applied to the three procedural skills) — an informed deviation from the `writing-skills` house-style default of full RED-GREEN-REFACTOR per skill.
- **RED-GREEN-REFACTOR (for skills)**: A test-driven development cycle adapted for skill authoring: RED captures a baseline transcript where the skill's target behavior fails; GREEN verifies the skill fixes it; REFACTOR improves the skill text without regressing GREEN behavior.

## Architecture

The plugin is a Claude Code plugin bundled inside the local-library repo. It delivers six skills in three architectural layers, co-located with MCP server configuration that auto-wires the library's MCP server at plugin install time.

**Plugin directory structure:**

```
.claude-plugin/
  plugin.json              # manifest (JSON; name: local-library)
  marketplace.json         # advertises this plugin for `/plugin marketplace add`
.mcp.json                  # MCP server config using ${CLAUDE_PLUGIN_ROOT}
README.md                  # plugin-level user-facing overview
skills/
  using-local-library-mcp/SKILL.md
  handling-extraction-quality/SKILL.md
  grounding-against-library/
    SKILL.md
    references/tool-selection.md
  drafting-with-grounded-sources/SKILL.md
  implementation-check-against-papers/SKILL.md
  verifying-claims-against-library/SKILL.md
```

**Three-layer skill architecture** (follows the orientation → skills → subagents model from `~/development/claude-workflow-testing/design_docs/workflow-architecture.md`; subagents are deferred):

1. **Orientation layer** — two always-apply skills (`using-local-library-mcp`, `handling-extraction-quality`). Descriptions are broad enough that Claude Code's semantic skill discovery treats them as candidates whenever conversation could plausibly involve the library. Purpose: fluency. Shapes Claude's tool-reaching behavior without requiring explicit invocation. Addresses the "not noticing a trigger" failure mode.

2. **Shared procedural kernel** — `grounding-against-library`. Atomic sub-skill that grounds **one** target assertion against library evidence from **one or more** documents. The kernel is scope-bounded: composing skills invoke it per-assertion; the kernel itself does not handle decomposition of broad user requests. Supported by `references/tool-selection.md` (composition and disambiguation matrix — not a restatement of MCP tool mechanics).

3. **Procedural composition skills** — three MVP skills (`drafting-with-grounded-sources`, `implementation-check-against-papers`, `verifying-claims-against-library`). Each has an explicit decomposition step that enumerates the assertions to ground before invoking the kernel, then a per-skill synthesis step that shapes output (annotated draft with grounding appendix; assertion-table; claim-table).

**Session data flow:**

- Orientation skills load on session start (broad descriptions).
- User prompt triggers a procedural skill (semantic match on description).
- Procedural skill runs its decomposition step (converts request into a set of atomic assertions).
- For each assertion: kernel invoked. Kernel retrieves via MCP tools, reads wider context where needed, synthesizes across retrieved evidence (per-source + aggregate), reports with per-source citations.
- Procedural skill aggregates per-assertion results into its output format.
- `handling-extraction-quality` invoked on-demand by any skill when grounding hits garbled extraction content (math, figures, tables); falls back to Claude Code's native `Read` tool on the PDF path from `show_document`.

**Key architectural decisions:**

1. **Plugin-bundled-with-repo** over project-level `.claude/` or user-global. The primary user wants fluency when using the library from *other* projects, not when working on the library itself; project-level is therefore backward. User-global is unshareable. Plugin-in-repo travels with the library and installs cleanly for any user who clones.

2. **Plugin ships `.mcp.json`** using `${CLAUDE_PLUGIN_ROOT}`. Single-command install registers both skills and server. The existing project-root `.mcp.json` is removed in Phase 1; the plugin's version supersedes it for both "working on the library" and "using the library from other projects" cases.

3. **Orientation split into two skills** rather than one omnibus. `using-local-library-mcp` addresses the "not noticing a library trigger" failure mode; `handling-extraction-quality` addresses the "trusting garbled extracted math" failure mode. These failure-mode sets diverge significantly, and merging would dilute the discipline techniques each needs (per `skill_principles.md`).

4. **Kernel is atomic; composing skills handle decomposition.** Without this split, the kernel implicitly biases toward "one chunk → answer," which shortchanges multi-source synthesis and prevents composing skills from checking multiple distinct assertions in a single user request. A scope guardrail at the top of the kernel enforces this: "This skill grounds ONE target assertion. Your caller is responsible for decomposition."

5. **Always-apply orientation implemented as skills, not CLAUDE.md.** Plugins cannot ship a user-global CLAUDE.md; the only mechanism available for always-on orientation is skills with broad descriptions. This is a divergence from the `workflow-architecture.md` framing (where CLAUDE.md is expected to hold orientation content) forced by the plugin delivery mechanism.

6. **No slash commands in MVP.** Skills are manually invocable via automatic namespacing (`/local-library:<skill-name>`). Separate slash commands would add discovery overhead for Claude without adding capability.

7. **Portability posture: weak form.** Skills written as clean markdown readable by other agents as reference documentation. Auto-discovery only on Claude Code. Not pursuing multi-harness auto-loadability.

8. **Permissions via `allowed-tools` frontmatter.** Each skill declares the tools it uses (the four MCP tools + `Read` for the PDF safety hatch). Delivers the DoD's "no per-tool-call approval" constraint. First-install still shows a standard MCP trust prompt.

**Contracts:**

Plugin manifest (`.claude-plugin/plugin.json`):

```json
{
  "name": "local-library",
  "description": "Skills for fluently using the local-library MCP server in research and drafting workflows",
  "version": "0.1.0"
}
```

MCP server config (`.mcp.json` at plugin root):

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

Procedural skill frontmatter pattern (example — `drafting-with-grounded-sources`):

```yaml
---
name: drafting-with-grounded-sources
description: Use when writing or editing text (drafts, essays, research notes, explanations) that should be grounded in specific source documents from local-library. Covers decomposition into grounded propositions, per-claim grounding via the shared kernel, and structured output with audit-trail appendix.
allowed-tools:
  - mcp__local-library__search_library
  - mcp__local-library__show_document
  - mcp__local-library__list_documents
  - mcp__local-library__get_document_text
  - Read
---
```

Kernel procedure (`grounding-against-library`):

1. Confirm ONE well-scoped target; if broad, return control to caller for decomposition.
2. Formulate query or queries (a single assertion may need multiple facet queries).
3. Retrieve — expect evidence from multiple documents is possible; single-chunk answer is one outcome, not the default.
4. Widen context via `get_document_text(ranges=...)` when chunk boundaries truncate relevant content.
5. Synthesize across retrieved evidence (per-source support / contradict / partial / not-found + aggregate conclusion).
6. Report with per-source citations.

Each procedural skill follows the shape: trigger → decomposition → per-assertion kernel invocation → domain-specific synthesis → structured output.

## Existing Patterns

Investigation of the repository (`docs/feature-areas/claude-code-integration/`, `src/local_library/mcp/CLAUDE.md`, `roadmap.md`) and the user's workflow-design material (`~/development/claude-workflow-testing/skill_principles.md`, `~/development/claude-workflow-testing/design_docs/workflow-architecture.md`) identified several patterns this design follows:

- **Three-layer skill architecture** from `workflow-architecture.md` (orientation → procedural skills → subagents). This design implements the first two layers; subagents are deferred per DoD.
- **Failure-mode-driven skill design** from `skill_principles.md`: split skills where failure modes diverge significantly; deploy discipline techniques (rationalization tables, red flags, iron laws) proportionate to domain failure-mode profile, not uniformly across skills.
- **Skill authoring house style** from the `ed3d-extending-claude` plugin (`writing-skills`, `writing-claude-directives`, `testing-skills-with-subagents`): description format `"Use when [triggers] - [what it does]"`; third-person/gerund-form naming; TDD-for-skills cycle (RED baseline → GREEN implementation → REFACTOR); token-efficiency discipline; XML for multi-part directives where needed.
- **MCP server contracts** already established in `src/local_library/mcp/CLAUDE.md`: markdown-only tool output, two-tier error convention, stateless calls, identifier resolution via UUID or `@citekey`. Skills in this plugin consume those contracts; no changes required on the MCP side.
- **Project documentation conventions**: date-prefixed design plans in `docs/design-plans/YYYY-MM-DD-<slug>.md`, `Last verified:` dates in CLAUDE.md files, Functional Core / Imperative Shell classification at module heads.

**Divergences from existing patterns:**

- **Orientation layer is skills, not CLAUDE.md.** `workflow-architecture.md` frames orientation content as belonging in CLAUDE.md / Output Style. Claude Code plugins cannot ship a user-global CLAUDE.md, so orientation is delivered via always-apply skills with broad descriptions. Functional parity; different mechanism.
- **Pragmatic testing tier for procedural skills.** `writing-skills` prescribes full RED-GREEN-REFACTOR per skill. This design applies the full cycle to the three Tier-1 skills (two orientation + kernel) but uses lighter Tier-3 realistic-scenario testing for the three procedural skills. Justification: MVP time-to-ship and preference for iterating on observed real-use failure modes over synthetic pressure scenarios. Documented explicitly so it is an informed deviation rather than an oversight.

## Implementation Phases

Six phases, within the writing-plans eight-phase hard limit. A single implementation plan suffices.

### Phase 1: Plugin scaffolding, MCP reconciliation, RED baselines

**Goal:** Operational plugin skeleton; MCP server reachable via plugin config; baseline failure scenarios captured for Tier-1 skills.

**Components:**

- `.claude-plugin/plugin.json` — manifest (name, description, version)
- `.claude-plugin/marketplace.json` — advertises the plugin for `/plugin marketplace add`
- `.mcp.json` at plugin root — uses `${CLAUDE_PLUGIN_ROOT}`
- Repo-root `.mcp.json` — **removed**
- `skills/` directory skeleton (empty subdirectories for each of the six skills)
- `README.md` at plugin root — skeleton only; content fleshed out in Phase 5
- RED baseline scenarios — recorded for: (a) unmarked citekey in conversation, (b) broad grounding request without kernel, (c) garbled-math extraction scenario. Failure modes and agent rationalizations documented verbatim.

**Dependencies:** None (first phase).

**Done when:** `claude --plugin-dir .` loads the plugin without error; MCP server reachable in a plugin-enabled session; RED baseline transcripts saved under `tests/skills/baselines/` (or equivalent location per project convention).

### Phase 2: Orientation layer

**Goal:** Two always-apply skills implementing citekey / library-first orientation and the extraction-quality safety hatch.

**Components:**

- `skills/using-local-library-mcp/SKILL.md` — ≤150 lines. Description targets citekey / literature / paper-adjacent triggers. Content: library-first inference rule, unmarked-citekey recognition, cross-tool workflow patterns, tool disambiguation. **Explicitly no MCP-tool-mechanic restatement.** Declares `allowed-tools` covering the four MCP tools plus `Read`.
- `skills/handling-extraction-quality/SKILL.md` — ≤150 lines. Description targets math / figure / garbled-extraction cues. Content: recognition cues, PDF fallback procedure via native `Read` tool with `pages:` parameter, iron law ("read the PDF; do not ask the user"), rationalization table. Declares `allowed-tools` including `Read`.

**Dependencies:** Phase 1 (scaffolding + RED baselines for orientation).

**Done when:** GREEN verification — re-running the Phase 1 RED baselines with these two skills active produces the expected behavior (library reach on citekey trigger; PDF fallback on garbled extraction); agent reasoning cites the skill guidance; per-skill token budget met.

### Phase 3: Shared kernel and tool-selection reference

**Goal:** Atomic grounding skill with multi-source synthesis; composition and disambiguation reference.

**Components:**

- `skills/grounding-against-library/SKILL.md` — ≤250 lines. Scope guardrail at top ("This skill grounds ONE target assertion; your caller is responsible for decomposition"). Six-step procedure (confirm scope → formulate query → retrieve → widen context → synthesize → report). Rationalization table covering premature closure, keyword match as semantic support, one-source dispositive, confabulation of support. Iron law: "Quote before you paraphrase. Not-found is a valid result." Declares `allowed-tools`.
- `skills/grounding-against-library/references/tool-selection.md` — composition and disambiguation matrix. Scenarios → right tool. Patterns like search → show → text. **Not** a restatement of individual tool mechanics.

**Dependencies:** Phase 1 (RED baseline for kernel).

**Done when:** GREEN verification — re-running the Phase 1 kernel RED baseline with this skill active produces a full retrieve → quote → compare → report flow, including multi-source synthesis when relevant and correct return-to-caller when the target is broad; token budget met.

### Phase 4: Procedural composition skills

**Goal:** Three MVP procedural skills built on the kernel, each with explicit decomposition.

**Components:**

- `skills/drafting-with-grounded-sources/SKILL.md` — ≤200 lines. Decomposition-first structure (identify proposition before writing prose). Failure-mode table: citation-shopping, paraphrase drift, weaving unsupported citations, collapsing "argues" / "mentions" / "rejects" distinctions. Iron law: "Quote into scratch before paraphrasing; can't quote = not grounded." Output format: draft prose with inline citekeys + grounding-summary appendix. Scope note recommending section-by-section invocation on large drafts.
- `skills/implementation-check-against-papers/SKILL.md` — ≤200 lines. Decomposition-first structure (enumerate code claims: algorithm / hyperparameter / loss term / ...). Failure-mode table: loose correspondence, reading garbled math from extraction, missing distant edge cases, assuming notational differences are "just rewriting." Iron law: "One claim per row, no consolidation. Notational differences verified, not assumed. Math against PDF, not markdown." Cross-invokes `handling-extraction-quality` when hitting math. Output: assertion table (claim / code-locus / paper-locus / status / notes).
- `skills/verifying-claims-against-library/SKILL.md` — ≤200 lines. Decomposition-first structure (enumerate citation-bearing claims). Failure-mode table: rubber-stamping, missing negations / qualifiers, one-chunk-dispositive, "doesn't contradict" passing as "supports." Iron law: "Quote the support. Caveats in the quote that aren't in the claim = partial, not match." Output: claim table (claim / cited source / quoted support / status).
- All three declare `allowed-tools` in frontmatter.

**Dependencies:** Phase 3 (kernel must exist for composition).

**Done when:** Tier-3 realistic scenarios pass for each skill — decomposition step fires, kernel invoked per-assertion, output format correct; per-skill token budget met.

### Phase 5: Plugin README and installation UX polish

**Goal:** User-facing documentation complete; install flow verified for both primary and external users.

**Components:**

- `README.md` at plugin root with sections: what this is / who it's for; install (three-command flow); architectural overview explaining how the three layers compose and why this structure was chosen (~200-300 words); skills at a glance (one-line per skill); test-drive scenarios (handful of prompts to verify the plugin is working); disabling / overriding (how to turn off individual skills; how to adjust `allowed-tools`); pointer to this design doc.
- `marketplace.json` finalized with plugin metadata.
- Permissions verification: with plugin installed and `allowed-tools` declared per skill, confirm zero per-call approval prompts in a realistic session.

**Dependencies:** Phases 1-4 (README describes and points at complete skills).

**Done when:** External-user install path (`git clone` → `uv sync` → `/plugin marketplace add <path>` → `/plugin install local-library`) produces a functional plugin; README architectural overview is accurate to the built plugin; permissions behave as specified in the DoD.

### Phase 6: End-to-end integration and smoke tests

**Goal:** Confirm the plugin delivers the "fluency" property end-to-end.

**Components:**

- Smoke-test scenarios under `tests/skills/` (or equivalent): (a) citekey dropped in conversation triggers library lookup via orientation; (b) implementation-check request produces decomposition + kernel loop + assertion table; (c) verify-claims request produces claim table with quoted support; (d) drafting request produces prose + grounding-summary appendix; (e) garbled-math scenario triggers PDF fallback via safety-hatch skill.
- Test-drive write-up documenting observed behavior, gaps, and candidate refinements for future passes.

**Dependencies:** Phases 1-5.

**Done when:** All smoke-test scenarios produce the expected structural output; observed behavior matches DoD success criteria; gaps recorded as follow-up work rather than silently absorbed.

## Additional Considerations

**Drafting scope-scaling is a load-bearing forcing function.** The grounding-summary appendix scales with draft size. This is the audit trail that makes the skill worth more than "drafting with inline citations" — shrinking it for long drafts would give up the property for convenience. The skill body includes a note recommending section-by-section invocation rather than whole-document drafting when the draft is large. File-output of the summary (to a sibling `.grounding-summary.md`) is a possible future refinement if the in-conversation summary proves cumbersome in real use, but is not included in MVP.

**Safety hatch depends on Claude Code's native `Read` tool supporting PDFs** with the `pages:` parameter. This is already true. No new MCP tool is required, and `handling-extraction-quality` references `Read` directly via `allowed-tools`. If future Claude Code changes affect PDF-read behavior, this assumption would need revisiting.

**Token and context budget.** Worst-case all six skills loaded yields ~1,150 lines ≈ 7-9K tokens (<5% of a 200K context). Per-skill budgets enforced at the phase level. Progressive disclosure via `references/*.md` files is the escape valve if any skill approaches its line target. Always-in-context cost (skill descriptions only, not bodies) is ~800 tokens across six skills — tolerable, but a reason to keep descriptions focused on triggers rather than verbose how-to content.

**Deferred scope (explicit non-goals):**

- **`literature-synthesis` skill** — fast-follow, separate design pass. Inverts the MVP skills' flow (topic → documents → synthesis rather than assertion → sources → report). Different enough in shape to warrant its own design.
- **Subagent wrappers.** The procedural skills may later benefit from wrappers (e.g., parallel literature gathering in an isolated context), but subagents layer *over* skills, not *instead of* them.
- **Neovim-as-REPL integration.** Noted as a genuinely interesting direction (a Neovim plugin that opens Claude Code as a floating-window REPL and sends text across the boundary), but out of scope here — it is a separate subproject.
- **Evaluation / retrieval-quality work.** Explicitly deferred; tracked in the RAG Pipeline Improvements feature area.
- **Multi-harness auto-discovery.** Skills are written as clean markdown readable by any agent as reference documentation, but no cross-harness plugin format is pursued.

**Implementation scoping:** 6 phases, within the writing-plans 8-phase hard limit. A single implementation plan is sufficient.
