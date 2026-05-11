# Local Library Claude Code Plugin

Bring your local library into Claude Code sessions: an MCP server exposing four read-only tools, plus six skills that turn citekeys into library lookups by default and make grounded writing, code-vs-paper checking, and claim verification the path of least resistance.

## Why this exists

Without the plugin, working with a local research corpus from inside Claude Code looks like either:

- *Ad-hoc shell commands* — `local-library show @citekey` in a separate terminal, copy-paste output back into the conversation, lose chunk indices and provenance along the way.
- *Trained answers* — Claude paraphrases from training when you mention a paper, often confidently, sometimes wrong.

The plugin closes both gaps. It registers the MCP server so Claude can call library tools directly inside the session, and it ships six skills that train Claude to reach for those tools (and to read the source PDF when extracted markdown is unreliable) before answering from training.

The plugin is for you if you want Claude Code to:
- Treat citekeys as library handles, not topic labels
- Quote evidence by default, not paraphrase from training
- Tag claims with explicit support / contradict / partial / not-found rather than rubber-stamp them
- Read the PDF when extracted markdown can't be trusted (math, figures, tables)

The library doesn't have to be the project you're working on — the plugin works from any Claude Code session anywhere on your machine.

## Quickstart

After cloning the parent repo and running `uv sync`, in a Claude Code session:

```
/plugin marketplace add /absolute/path/to/local-library
/plugin install local-library@local-library
```

Then try:
- *"What does @<your-citekey> argue about <topic>?"* — orientation skill triggers a library lookup before answering.
- *"Open @<your-mathy-citekey> and explain the main equation."* — safety hatch falls back to the PDF if extracted markdown is garbled.

## Installation

The plugin lives inside the `local-library` repository (no separate package). To install it you first need the Python package set up, so the bundled MCP server can run.

### From a local checkout (recommended for development)

```bash
git clone https://github.com/strophios/local-library.git
cd local-library
uv sync
```

Then in a Claude Code session:

```
/plugin marketplace add /absolute/path/to/local-library
/plugin install local-library@local-library
```

### From GitHub

```
/plugin marketplace add https://github.com/strophios/local-library.git
/plugin install local-library@local-library
```

The marketplace-add argument needs the full Git URL form (`https://github.com/<owner>/<repo>.git`), not a bare `<owner>/<repo>` shortcut. This fetches the plugin assets directly from GitHub. `uv run` (used by the MCP server config) handles dependency sync on first invocation, but `uv` must already be installed on your system.

The plugin's `.mcp.json` uses `${CLAUDE_PLUGIN_ROOT}` to locate the bundled MCP server, so no manual MCP registration is needed either way.

## The six skills

The plugin ships six skills organized in three layers: two orientation skills that fire on library-adjacent cues, one grounding kernel that handles per-assertion evidence work, and three procedural composition skills that decompose complex requests and orchestrate the kernel.

### Orientation (always-apply)

These skills don't wait to be invoked — they fire whenever specific cues appear in your message.

**`using-local-library-mcp`** — *Library reach reflex.* Fires on citekey patterns (`@Smith2023`, bare `Smith2023`), library cues ("what does X argue", "from my library", "cite this"), and verification phrasings. Reaches for `mcp__local-library__*` tools before answering from training, and treats `@citekey` as a library handle rather than a topic label.

**`handling-extraction-quality`** — *Extraction-quality safety hatch.* Fires on math/equation/figure/table prompts. Inspects retrieved markdown for *genuine* garbling cues (subscript collapse like `QWQ i`, escape-sequence remnants like `\n(1)` at equation tails, empty math delimiters, broken tables, `Status: needs_review`); escalates to native `Read` on the PDF when cues fire. Well-formed LaTeX is the success case, NOT garbling — only malformed LaTeX triggers escalation. Provenance disclosure is mandatory either way (chunk index for markdown, page number for PDF).

### Kernel

The kernel is the atomic unit of grounded retrieval. Procedural skills cross-invoke it per claim.

**`grounding-against-library`** — Atomic per-assertion grounding cycle: confirm scope, formulate query/queries, retrieve, widen context if needed, synthesize per-source tags (support / contradict / partial / not-found), report with per-source rows and an aggregate line. Multi-source. The kernel is invoked by procedural skills, not by user prompts directly — on broad inputs it returns control to its invoking procedural skill rather than attempting one-pass synthesis, leaving decomposition to the composing skill. (As a user you usually won't see the kernel surface in isolation; you see the procedural-skill output it feeds into.)

The kernel's `references/tool-selection.md` documents when to use which MCP tool, including the `no_rerank: bool = False` inversion footgun (the parameter default keeps reranking ON; setting True disables it).

### Procedural composition

These skills decompose complex requests and cross-invoke the kernel per claim. Each produces a specific output shape.

**`drafting-with-grounded-sources`** — For prose that defends or develops specific claims using cited evidence. Three input shapes: claims supplied → proceed; argument-shaped without claims → surface inferred propositions for user review before grounding; topic-only exploration → return control to `using-local-library-mcp` (drafting is not the right tool for tour-the-literature requests). Output: prose with inline `@citekeys` + grounding-summary appendix listing per-proposition citekey, chunk index, quote, and status.

**`implementation-check-against-papers`** — For comparing code against method descriptions in source papers. Decomposes code into checkable claims (algorithm shape, hyperparameters, loss/objective terms, normalization, initialization, edge cases) and grounds each via the kernel. For equation/symbol claims where the extracted markdown is garbled, cross-invokes `handling-extraction-quality` to verify against the PDF. Output: assertion table mapping each code claim to its paper locus + a status (match / mismatch / partial / not-found).

**`verifying-claims-against-library`** — For checking whether the library supports given textual claims (claims with explicit citekeys, claims attributing positions to named authors, claims about what a source "argues" / "shows" / "concludes"). Enumerates each citation-bearing claim, invokes the kernel per claim, reports a claim table with verbatim quoted support and a per-claim status. Catches "doesn't contradict" passing as "supports," silent qualifier-stripping, and one-chunk-dispositive errors.

### Skills at a glance

| Skill | Layer | Triggers when... | Produces |
|---|---|---|---|
| `using-local-library-mcp` | Orientation | Citekey or library cue appears | MCP tool calls before training answer |
| `handling-extraction-quality` | Orientation | Math/figure/table prompt + garbled markdown cue | PDF fallback via `Read` |
| `grounding-against-library` | Kernel | Cross-invoked by procedural skills | Per-source rows + aggregate |
| `drafting-with-grounded-sources` | Procedural | "Defend/develop the claim that..." | Prose + grounding appendix |
| `implementation-check-against-papers` | Procedural | "Does this code match @<paper>?" | Assertion table |
| `verifying-claims-against-library` | Procedural | "Are these citations warranted?" | Claim table with quoted support |

### What's not covered (yet)

The procedural skills are claim-shaped — they assume you have specific claims to defend, verify, or check against code. For *topic exploration*, *summary*, or *cross-source synthesis* ("what does the literature say about X", "tour these papers", "summarize what my library has on Y"), the procedural skills don't fire (or, if they fire, hand off back to orientation). Exploration happens ad hoc via `using-local-library-mcp` and the MCP tools. That works, but it's less structured than the claim-shaped flows — a dedicated exploration / summary / synthesis skill is a likely next addition to the plugin.

## Test-drive scenarios

After installing, try these. They each exercise a different part of the plugin.

1. **Orientation triggers on bare citekey:**
   > *"What does @<your-citekey> argue about <topic>?"*

   Expected: Claude calls `show_document` (or `search_library`) before responding; quotes evidence rather than summarizing from training.

2. **Safety hatch triggers on garbled extraction:**
   > *"Open @<your-mathy-citekey> and explain the main equation."*

   Expected: if the extracted markdown shows genuine garbling cues, Claude reads the PDF directly via `Read` and cites a page number. If extraction is clean (well-formed LaTeX), Claude works from the markdown and cites a chunk index. Either way, provenance is disclosed.

3. **Drafting prose with grounded support:**
   > *"Write a paragraph defending the claim that <specific claim>, drawing on @<A> and @<B>."*

   Expected: drafting skill decomposes the claim into propositions, invokes the kernel per proposition, and returns prose with inline citekeys + a grounding-summary appendix (per-proposition citekey, chunk index, quote, status). Phrasing matters: a topic-shaped request like *"write a note on <topic>"* won't fire the drafting skill — it'll fall through to `using-local-library-mcp` for ad hoc exploration via the MCP tools (see *What's not covered (yet)* above).

4. **Verifying claims against the library:**
   > *"Check whether my library supports these claims:*
   > *1. <claim> — per @<X>*
   > *2. <claim> — per @<Y>"*

   Expected: claim table with quoted support, per-claim status (match / partial / mismatch / not-found), and a summary line. Watch for the cases the skill is specifically designed to catch: *doesn't contradict* passing as *supports*, silent qualifier-stripping, and one-chunk-dispositive errors.

5. **Implementation check against a paper:**
   > *"Does this implementation of <method> match @<paper>? [paste code]"*

   Expected: skill decomposes the code into checkable claims (algorithm shape, hyperparameters, loss terms, normalization, edge cases), grounds each against the paper, and returns an assertion table mapping each claim to its paper locus + a status. For equation/symbol claims where the extracted markdown is garbled, cross-invokes `handling-extraction-quality` to verify against the PDF.

## Configuration

### Disabling individual skills

To disable a skill without uninstalling the plugin:
- Edit `~/.claude/settings.json` and add the skill name to the `disabledSkills` list, or use the `/plugin` UI to toggle individual skills.

### Narrowing tool authorization for a skill

To restrict the tools a specific skill is authorized to use:
- Edit the `allowed-tools` block in that skill's `SKILL.md` after installation.

Note: this edits the installed copy in your plugin tree, not the source repo. Re-installation will overwrite your changes.

### Using the MCP server without the plugin skills

If you want the MCP tools but not the skill scaffolding, register the MCP server directly in your project's `.mcp.json` and skip the plugin install. The repo's root `.mcp.json` is a working example to copy from (replace `${CLAUDE_PLUGIN_ROOT}` with the absolute path to your local-library checkout).

## Troubleshooting

| Symptom | Action |
|---------|--------|
| `/plugin marketplace add` fails | Confirm the path is absolute (`/absolute/path/to/local-library`) and points to a directory containing `.claude-plugin/marketplace.json` |
| Skills don't appear to fire on citekey | Check `~/.claude/settings.json` for `disabledSkills`; confirm the plugin is enabled in the `/plugin` UI |
| MCP tool calls fail with import errors | Confirm `uv sync` ran successfully in the local-library checkout; the plugin's `.mcp.json` uses `${CLAUDE_PLUGIN_ROOT}` to locate the bundled MCP server, so `uv` must be on PATH |
| Math/equation answers cite no provenance | The `handling-extraction-quality` skill may be disabled; check `disabledSkills` |
| MCP tools start but return empty results | Library may be empty or sqlite-vec may not be available; run `local-library list` from the command line to confirm the library is populated and accessible |

## Architecture

### Three-layer skill split

**Orientation skills are always-apply** (no explicit invocation needed). They fire on cues — citekeys, library phrasings, math/figure prompts. Their job is to ensure that library-adjacent requests trigger MCP tool use before training-derived answers, and that extraction-quality fallback happens before garbled markdown leaks into the response.

**The kernel is atomic**: a single claim, one retrieve pass, evidence quoted and synthesized. It returns control on broad inputs because composing skills handle decomposition. Without this scope guardrail, the kernel would bias toward "one chunk answers the whole question," which short-changes multi-source synthesis and forces users to manually narrow broad questions.

**Procedural composition skills decompose** complex requests (a paragraph to defend, an implementation to audit, a list of claims to verify) into atomic claims, invoke the kernel per claim, and assemble per-claim results into a specific output shape (prose + appendix, assertion table, claim table).

Why this split? Plugins can't ship a user-global `CLAUDE.md`, so orientation skills must be always-apply to catch citekeys and extraction problems automatically. The kernel is deliberately atomic so composing skills can decompose. The procedural skills exist to handle the request shapes (drafting, code-check, claim-check) that benefit from explicit per-claim grounding plus an audit-able output format.

### End-to-end flow

A citekey appears in conversation. The orientation skill `using-local-library-mcp` triggers `show_document` (or `search_library`) and quotes the abstract. You ask a question that decomposes into multiple claims. A procedural skill enumerates them. The kernel runs per claim — retrieve relevant chunks, quote evidence, synthesize — and each result flows to the output formatter. The final result (prose with appendix, assertion table, or claim table) is assembled per skill format.

If at any point the retrieved markdown contains genuine garbling cues, `handling-extraction-quality` triggers a fallback: native `Read` on the PDF path provided by `show_document`. Provenance is preserved across both code paths.

## Where the plugin's pieces live

- `skills/<skill-name>/SKILL.md` — six SKILL.md files (one per skill above)
- `skills/grounding-against-library/references/tool-selection.md` — tool-call shapes and the `no_rerank` footgun
- `.claude-plugin/plugin.json` — plugin manifest
- `.claude-plugin/marketplace.json` — self-advertising marketplace entry (`source: "./"` is required; bare `"."` fails schema validation)
- `.mcp.json` at the repo root — MCP server config (uses `${CLAUDE_PLUGIN_ROOT}`)
- `src/local_library/mcp/` — MCP server implementation (FastMCP, stdio transport)
- `tests/skills/` — RED baselines (Phase 1), GREEN/Tier-3 verifications (Phases 2–4), install-and-permissions audit (Phase 5), smoke transcripts + DoD audit (Phase 6)
- `docs/feature-areas/claude-code-integration/README.md` — feature-area planning, design history, longer-term ideas
- `docs/design-plans/2026-04-24-local-library-claude-code-plugin.md` — original design document
- `docs/implementation-plans/2026-04-24-local-library-claude-code-plugin/` — six-phase implementation plan

## Uninstall

```
/plugin uninstall local-library@local-library
/plugin marketplace remove local-library
```

The plugin's MCP server registration is removed automatically; no separate `.mcp.json` cleanup needed.

## License

Same as the parent project (MIT).
