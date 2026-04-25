# Local-Library Claude Code Plugin Implementation Plan — Phase 4

**Goal:** Create three procedural composition skills — `drafting-with-grounded-sources`, `implementation-check-against-papers`, `verifying-claims-against-library` — each composing on the Phase 3 grounding kernel via explicit decomposition; Tier-3 verify each with a realistic end-to-end scenario.

**Architecture:** All three procedural skills follow the same shape: trigger → decomposition → per-assertion kernel invocation → per-skill synthesis → structured output. The decomposition step lives in the composing skill (not in the kernel — the kernel is atomic by design). Each procedural skill's output format is distinct (prose + appendix; assertion table; claim table) but the decomposition discipline is shared.

**Tech Stack:** Same as Phase 2/3.

**Scope:** 4 of 6 phases.

**Codebase verified:** 2026-04-24

---

## Executing-engineer context

- **Kernel dependency:** All three procedural skills cross-reference `grounding-against-library` (Phase 3). The kernel must be in place and PASS its GREEN tests before this phase starts.
- **Cross-skill invocation in Claude Code:** Skills reference each other by name; the agent loads the cross-referenced skill on demand based on description matching. The `implementation-check-against-papers` skill explicitly cross-invokes `handling-extraction-quality` when claims involve equations.
- **Tier-3 testing posture (per design):** Realistic end-to-end scenarios, *not* RED-GREEN-REFACTOR with synthetic pressure. Verification checks structural properties (decomposition fires, kernel invoked per-assertion, output format correct). Refinement is deferred to Phase 6 smoke tests and observed real-use failures.
- **Realistic scenario sources:** For Tier-3 tests, executing engineer picks real citekeys from the corpus (`uv run local-library list`). The implementation-check Tier-3 has a particularly clean target in `src/local_library/embeddings/reranking.py` — the project's own cross-encoder reranker.
- **Line budget:** each SKILL.md ≤200 lines.

---

## Tasks

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Write `skills/drafting-with-grounded-sources/SKILL.md`

**Type:** Functionality

**Files:**
- Create: `skills/drafting-with-grounded-sources/SKILL.md` (≤200 lines)
- Delete: `skills/drafting-with-grounded-sources/.gitkeep`

**Step 1: Read kernel + reference**

```bash
cat skills/grounding-against-library/SKILL.md skills/grounding-against-library/references/tool-selection.md
```

**Step 2: Write the skill file**

Structure (≤200 lines, fill prose yourself):

```markdown
---
name: drafting-with-grounded-sources
description: Use when writing or editing text (drafts, essays, research notes, explanations) that should be grounded in specific source documents from the local library — covers decomposition into grounded propositions, per-claim invocation of the grounding-against-library kernel, and structured output with prose + audit-trail appendix. Recommends section-by-section invocation on large drafts.
allowed-tools:
  - mcp__local-library__search_library
  - mcp__local-library__show_document
  - mcp__local-library__list_documents
  - mcp__local-library__get_document_text
  - Read
---

# Drafting with grounded sources

## When to invoke
[Bullets: drafting/editing prose where every claim with a citekey or every claim that *could* take one from the library should be grounded. Examples: 2-paragraph response about a paper's argument; research note synthesizing 3 sources; editorial pass on a section with unsourced claims.]

## Iron law
- **Quote into scratch before paraphrasing.** Cannot quote = not grounded = not citable.
- **One proposition, one grounding pass.** "A and B" needs A grounded and B grounded.

## Procedure

### Step 1 — Decompose before writing
List propositions before producing prose. Example: "Vaswani et al. 2017 introduced the Transformer architecture, which replaced recurrence with attention and reduced sequential compute" decomposes to:
1. @Vaswani2017 introduced the Transformer architecture.
2. @Vaswani2017's Transformer replaced recurrence with attention.
3. @Vaswani2017 claims this reduces sequential compute.

### Step 2 — Ground each proposition
Per proposition: invoke `grounding-against-library` (six-step procedure). Capture per-source quoted evidence into a scratch buffer.

If the kernel returns not-found for a proposition: drop it OR rewrite to match what the corpus supports. Do not paraphrase past not-found.

### Step 3 — Write the prose
Draft from the scratch buffer. Inline `@citekeys` at every claim. Paraphrase from quoted excerpts, never from memory.

### Step 4 — Build the grounding-summary appendix
At the end of the draft:

```
## Grounding summary
- Proposition 1: <verbatim>
  - Source: @Citekey1 (Chunk N)
  - Quote: "..."
  - Status: support
- Proposition 2: <verbatim>
  - Source: @Citekey2 (Chunk M)
  - Quote: "..."
  - Status: partial — caveat noted in prose
```

The appendix scales with draft size. For long drafts, invoke section-by-section to keep the appendix manageable.

## Output format
- Draft prose with inline `@citekeys` at every claim
- Grounding-summary appendix at end (one entry per proposition)

## Failure-mode table
| Excuse | Reality |
|--------|---------|
| "I'll cite this from memory; the paper definitely says it" | Memory is where false grounding enters. Quote first; cite from quote. |
| "Top result was thematically related; that's enough to cite" | Citation-shopping. The chunk must support the *specific* claim. |
| "`mentions` / `discusses` / `argues` mean the same thing" | They don't. Match the verb to the quote. |
| "I'll add the citekey at the end and figure out the chunk later" | Citations decay. Capture the chunk index when you capture the quote. |
| "This proposition's a connector — it doesn't need grounding" | Connectors quietly assert relationships. Ground them or mark as synthesis. |

## Red flags — stop
- About to add inline citekey without a corresponding grounding-summary entry
- About to skip decomposition because the section "is short"
- About to keep a not-found proposition by fudging the wording
- About to consolidate two propositions into one citation
- About to draft prose before the scratch buffer is populated
```

**Step 3: Line-count + commit**

```bash
wc -l skills/drafting-with-grounded-sources/SKILL.md
rm skills/drafting-with-grounded-sources/.gitkeep
git add skills/drafting-with-grounded-sources/
git commit -m "feat(plugin): add drafting-with-grounded-sources composition skill"
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Tier-3 verification — drafting

**Type:** Functionality

**Files:**
- Create: `tests/skills/phase4/drafting-tier3.md`

**Step 1: Pick a realistic scenario**

```bash
uv run local-library search "<topic>" --limit 10
```

Pick `<CITEKEY_A>`, `<CITEKEY_B>` (and optionally `<CITEKEY_C>`) on a topic the user might draft about.

**Step 2: Dispatch subagent**

```bash
mkdir -p tests/skills/phase4
```

Inline this SKILL.md + kernel SKILL.md + tool-selection.md as operative context. Scenario:

```
Write a 2-paragraph research note on <topic> drawing from <CITEKEY_A>, <CITEKEY_B>[, and <CITEKEY_C>]. Engage with each source's specific claims, not generic background.
```

Capture full response.

**Step 3: Write Tier-3 transcript**

```markdown
# Tier-3: drafting-with-grounded-sources

**Date:** <YYYY-MM-DD>
**Scenario:**
> <verbatim>

**Citekeys:** @<A>, @<B>[, @<C>]

## Subagent response (verbatim)
<full response>

## Structural assessment
- [x/✗] Step 1 (decomposition) — propositions enumerated before prose
- [x/✗] Step 2 (per-proposition grounding) — kernel invoked per proposition; quoted evidence captured
- [x/✗] Step 3 (prose) — inline `@citekeys` at every claim
- [x/✗] Step 4 (grounding-summary appendix) — present, with one entry per proposition + chunk index
- [x/✗] Iron law — paraphrases trace to captured quotes; no memory-grounded citations

## Failure modes observed
<list rationalizations>

## Assessment
PASS / PARTIAL / FAIL.

**Final:** <PASS or PARTIAL or FAIL>
```

**Step 4: Commit**

```bash
git add tests/skills/phase4/drafting-tier3.md
git commit -m "test(plugin): Tier-3 verification for drafting-with-grounded-sources"
```

**Step 5: Refactor if structural failures.**
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 3-4) -->
<!-- START_TASK_3 -->
### Task 3: Write `skills/implementation-check-against-papers/SKILL.md`

**Type:** Functionality

**Files:**
- Create: `skills/implementation-check-against-papers/SKILL.md` (≤200 lines)
- Delete: `skills/implementation-check-against-papers/.gitkeep`

**Step 1: Read kernel + extraction-quality skill**

```bash
cat skills/grounding-against-library/SKILL.md skills/handling-extraction-quality/SKILL.md
```

**Step 2: Write the skill file**

```markdown
---
name: implementation-check-against-papers
description: Use when comparing code/implementation against method descriptions in one or more source papers — covers decomposition of code into checkable claims (algorithm, hyperparameters, loss terms, normalization, edge cases), per-claim grounding via the grounding-against-library kernel, math-verification fallback to PDF via handling-extraction-quality, and an assertion-table output that maps each code claim to its paper locus and a status. Multi-source.
allowed-tools:
  - mcp__local-library__search_library
  - mcp__local-library__show_document
  - mcp__local-library__list_documents
  - mcp__local-library__get_document_text
  - Read
---

# Implementation check against papers

## When to invoke
[Reviewing code that implements a paper method; verifying a refactor preserved fidelity; auditing a "follows X et al." claim in code comments.]

## Iron law
- **One claim per row. No consolidation.** "Algorithm matches" is not a claim.
- **Notational differences are verified, not assumed.** Confirm symbol substitutions; do not assume "just rewriting".
- **Math against PDF, not markdown.** For equations or symbol-level details, invoke `handling-extraction-quality`.

## Procedure

### Step 1 — Decompose the code
List checkable claims. Per area:
- **Algorithm shape**: control flow, ordering, loop structure
- **Hyperparameters**: numeric values
- **Loss / objective terms**: components, regularization, weighting
- **Normalization / activation**: where softmax/layer-norm/sigmoid appear; scale factors
- **Initialization / scheduling**: warmup, decay, init distributions
- **Edge cases**: empty inputs, masks, padding

Each bullet → one row in the assertion table.

### Step 2 — Ground each claim against the paper(s)
For each claim, invoke `grounding-against-library` with assertion phrased as "the paper(s) `@<citekey>` specify <claim>". Capture per-source evidence with chunk indices.

For equation/symbol claims with garbled markdown, cross-invoke `handling-extraction-quality` to read the PDF; quote the equation as it appears in the PDF + page number.

### Step 3 — Build the assertion table

```
| # | Claim | Code locus | Paper locus | Status | Notes |
|---|-------|-----------|-------------|--------|-------|
| 1 | softmax over time dim before value projection | reranking.py:128 | @Vaswani2017 §3.2.1 (chunk 14) | match | quote: "..." |
| 2 | learning rate warmup over 4000 steps | train.py:62 | @Vaswani2017 §5.3 (chunk 31) | mismatch | code uses 8000; paper says 4000 |
| 3 | mask out padded positions in attention | reranking.py:142 | @Vaswani2017 §3.2.3 (chunk 18) | partial | paper specifies mask shape; code's mask scope is broader |
| 4 | ... | ... | ... | not-found | searched §3, §4, §5; no equivalent |
```

Status values: `match` / `mismatch` / `partial` / `not-found`.

## Output format
- Assertion table: rows = claims; columns = (#, claim, code locus, paper locus, status, notes)
- Paper locus = citekey + section + chunk index (or PDF page when math)
- Notes = quoted evidence or divergence description

## Failure-mode table
| Excuse | Reality |
|--------|---------|
| "Loose correspondence is good enough at this granularity" | Loose correspondence hides bugs. One claim per row. |
| "Math markdown is garbled but I can guess" | Cross-invoke `handling-extraction-quality`. |
| "Notational difference, surely just rewriting" | Verify substitutions. Subscripts and signs flip more often than expected. |
| "Couldn't find it in §3, must not be in the paper" | Search the rest. Use `search_library(query, doc_id="@<citekey>")`. |
| "Multiple claims map to same section; merge rows" | No. One claim per row. Statuses may differ. |

## Red flags — stop
- About to write `match` without a quoted excerpt in Notes
- About to read symbols off Marker output without checking the PDF
- About to skip a code claim because "it's just an implementation detail"
- About to consolidate rows with different statuses
- About to tag `not-found` without searching the full paper
```

**Step 3: Line-count + commit**

```bash
wc -l skills/implementation-check-against-papers/SKILL.md
rm skills/implementation-check-against-papers/.gitkeep
git add skills/implementation-check-against-papers/
git commit -m "feat(plugin): add implementation-check-against-papers composition skill"
```
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Tier-3 verification — implementation-check

**Type:** Functionality

**Files:**
- Create: `tests/skills/phase4/implementation-check-tier3.md`

**Step 1: Pick a realistic scenario**

The local-library codebase has `src/local_library/embeddings/reranking.py` (cross-encoder reranking, document-aware grouping). Pick a corpus citekey that is the closest paper analog (consult `docs/benchmarks/2026-03-06-reranker-model-selection.md` and `docs/RAG_background/00_final_summary_report.md` for candidates).

If no clean analog: construct a deliberately mixed synthetic pair. Pick a small standard-library or well-known algorithm in the codebase (e.g., a sorting routine, a tokenizer, a chunker) and a corpus paper that *describes* the same algorithm or method. Even a partial-overlap pair will exercise more of the assertion-table statuses (`match`/`mismatch`/`partial`) than a fully-disconnected pair, which would produce mostly `not-found` rows and fail to test the more diagnostic paths.

Record `<TARGET_CODE_FILE>` and `<CITEKEY_PAPER>`.

**Step 2: Dispatch subagent**

Inline kernel + tool-selection + this SKILL.md + handling-extraction-quality. Scenario:

```
Compare the implementation in <TARGET_CODE_FILE> against the method described in @<CITEKEY_PAPER>. Produce an assertion table covering algorithm shape, hyperparameters, and any normalization/loss details. Tag each row with status (match/mismatch/partial/not-found) and quoted evidence.
```

Capture full response with all tool calls.

**Step 3: Write Tier-3 transcript**

```markdown
# Tier-3: implementation-check-against-papers

**Date:** <YYYY-MM-DD>
**Code file:** <TARGET_CODE_FILE>
**Paper:** @<CITEKEY_PAPER>

## Subagent response (verbatim)
<full response>

## Structural assessment
- [x/✗] Step 1 (decomposition) — ≥3 claims for non-trivial module
- [x/✗] Step 2 (grounding) — kernel invoked per claim; per-row paper locus has citekey + section/chunk
- [x/✗] Math-handling — for equation claims, `handling-extraction-quality` invoked OR markdown was sufficient
- [x/✗] Step 3 (assertion table) — table present with all required columns
- [x/✗] Iron law — quoted evidence in Notes for each `match` and `mismatch`; no consolidated rows

## Status distribution
- match: <count>
- mismatch: <count>
- partial: <count>
- not-found: <count>

## Assessment
PASS / PARTIAL / FAIL.

**Final:** <PASS or PARTIAL or FAIL>
```

**Step 4: Commit**

```bash
git add tests/skills/phase4/implementation-check-tier3.md
git commit -m "test(plugin): Tier-3 verification for implementation-check-against-papers"
```

**Step 5: Refactor if needed.**
<!-- END_TASK_4 -->
<!-- END_SUBCOMPONENT_B -->

<!-- START_SUBCOMPONENT_C (tasks 5-6) -->
<!-- START_TASK_5 -->
### Task 5: Write `skills/verifying-claims-against-library/SKILL.md`

**Type:** Functionality

**Files:**
- Create: `skills/verifying-claims-against-library/SKILL.md` (≤200 lines)
- Delete: `skills/verifying-claims-against-library/.gitkeep`

**Step 1: Read kernel**

```bash
cat skills/grounding-against-library/SKILL.md
```

**Step 2: Write the skill file**

```markdown
---
name: verifying-claims-against-library
description: Use when checking whether the local library supports given textual claims (claims with citekeys, claims attributing positions to authors, claims about what a source "argues" / "shows" / "finds") — enumerates each citation-bearing claim, invokes the grounding-against-library kernel per claim, and reports a claim table with quoted support and status. Multi-source. Catches "doesn't contradict" passing as "supports", missing negations/qualifiers, and one-chunk-dispositive errors.
allowed-tools:
  - mcp__local-library__search_library
  - mcp__local-library__show_document
  - mcp__local-library__list_documents
  - mcp__local-library__get_document_text
  - Read
---

# Verifying claims against library

## When to invoke
[A user pastes cited prose and asks "does my library support this?"; an editor pass on a draft asking which citations are warranted; a fact-check pass on someone else's text against the local corpus.]

## Iron law
- **Quote the support.** `match` without a quoted excerpt is rubber-stamping.
- **Caveats in the quote that aren't in the claim = `partial`, not `match`.** "X causes Y in low-income countries" ≠ "X causes Y".
- **`doesn't contradict` is not `supports`.** Source silent on a claim is `not-found`.

## Procedure

### Step 1 — Enumerate citation-bearing claims
Each claim becomes a row. A claim that combines two assertions ("X causes Y, and Y causes Z, per @Smith2020") is two claims.

### Step 2 — Per-claim grounding
For each claim, invoke `grounding-against-library`. The assertion is the verbatim claim with its attributed citekey(s).

Watch for:
- **Negation**: "X does not cause Y" — quoted excerpt must explicitly negate, not merely omit.
- **Qualifiers**: "X usually causes Y" / "under condition C" — quote must include the qualifier; if not, status is `partial`.
- **Attribution voice**: "argues" vs "mentions" vs "rejects" — match quote stance to claim verb.

### Step 3 — Build the claim table

```
| # | Claim (verbatim) | Cited source | Quoted support | Status | Notes |
|---|------------------|--------------|----------------|--------|-------|
| 1 | "X causes Y" | @Smith2020 | "...X causes Y in low-income economies..." | partial | claim drops qualifier "in low-income economies" |
| 2 | "Z is invariant under T" | @Jones2021 | <none> | not-found | searched §2, §3, §4; no claim about T-invariance |
| 3 | "Both papers agree on policy implications" | @Smith2020, @Jones2021 | <quoted excerpts from both> | mismatch | Smith favors A; Jones favors B |
```

Status values: `match` / `mismatch` / `partial` / `not-found`.

## Output format
- Claim table: rows = citation-bearing claims; columns = (#, claim verbatim, cited source, quoted support, status, notes)
- Summary line at end: "Of N claims: <match> match, <partial> partial, <mismatch> mismatch, <not-found> not-found."

## Failure-mode table
| Excuse | Reality |
|--------|---------|
| "Cited source mentions the topic, that's good enough" | Topical overlap is not support. Quote the specific claim. |
| "Couldn't find it on first chunk; close enough to match" | Premature closure. More queries; widen context. |
| "Qualifier is implicit; no need to flag" | Implicit qualifiers are how false claims travel. Status is `partial`. |
| "Source doesn't contradict, so it's a match" | Silence is `not-found`. |
| "Two sources cited together; one supports, so the row is match" | Per-source status. If both attributed, all-or-partial. |

## Red flags — stop
- About to mark `match` without a quote in the table
- About to ignore a qualifier ("usually", "in some cases", "for X") in the source
- About to merge two distinct claims into one row
- About to tag `not-found` after one search query (let the kernel do multi-facet)
- About to treat "the source discusses the topic" as supporting "the source argues the claim"
```

**Step 3: Line-count + commit**

```bash
wc -l skills/verifying-claims-against-library/SKILL.md
rm skills/verifying-claims-against-library/.gitkeep
git add skills/verifying-claims-against-library/
git commit -m "feat(plugin): add verifying-claims-against-library composition skill"
```
<!-- END_TASK_5 -->

<!-- START_TASK_6 -->
### Task 6: Tier-3 verification — verify-claims

**Type:** Functionality

**Files:**
- Create: `tests/skills/phase4/verify-claims-tier3.md`

**Step 1: Construct a deliberately-mixed scenario**

Three claims:
- Claim 1: a true claim about a real corpus citekey (expect `match` or `partial`)
- Claim 2: a true claim with an added qualifier the source does NOT contain (expect `partial`)
- Claim 3: a fabricated claim attributed to a real corpus citekey (expect `not-found` or `mismatch`)

Pick real citekeys via `uv run local-library list --limit 20`.

Scenario template:

```
Verify the following citation-bearing claims against my library:

1. "<true claim>" — per @<CITEKEY_X>
2. "<true-but-extra-qualifier claim>" — per @<CITEKEY_Y>
3. "<fabricated claim>" — per @<CITEKEY_Z>

Produce a claim table with quoted support and status.
```

**Step 2: Dispatch subagent**

Inline kernel + tool-selection + this SKILL.md. Pose scenario.

Capture full response.

**Step 3: Write Tier-3 transcript**

```markdown
# Tier-3: verifying-claims-against-library

**Date:** <YYYY-MM-DD>
**Claims:**
1. <claim 1 — expected: match/partial>
2. <claim 2 — expected: partial>
3. <claim 3 — expected: not-found/mismatch>

## Subagent response (verbatim)
<full response>

## Structural assessment
- [x/✗] Three rows in the claim table
- [x/✗] Each row has quoted support (or `<none>` for not-found)
- [x/✗] Statuses align with expected (or divergence justified by actual evidence)
- [x/✗] Qualifier-stripped claim 2 tagged `partial` (not `match`)
- [x/✗] Fabricated claim 3 tagged `not-found` or `mismatch` (not `match`)
- [x/✗] Summary line present

## Iron law adherence
- [x/✗] No `match` without quote
- [x/✗] No silent qualifier-dropping

## Assessment
PASS / PARTIAL / FAIL.

**Final:** <PASS or PARTIAL or FAIL>
```

**Step 4: Commit**

```bash
git add tests/skills/phase4/verify-claims-tier3.md
git commit -m "test(plugin): Tier-3 verification for verifying-claims-against-library"
```

**Step 5: Refactor if needed.**
<!-- END_TASK_6 -->
<!-- END_SUBCOMPONENT_C -->

<!-- START_TASK_7 -->
### Task 7: Phase 4 integration — frontmatter + cross-skill checks + human reload gate

**Type:** Infrastructure

**Files:** None.

**Step 1: Confirm files in place**

```bash
ls skills/drafting-with-grounded-sources/ skills/implementation-check-against-papers/ skills/verifying-claims-against-library/
```
Expected: each contains only `SKILL.md`.

**Step 2: Validate frontmatter**

```bash
uv run python - <<'PY'
import re, yaml, pathlib
for p in [
    "skills/drafting-with-grounded-sources/SKILL.md",
    "skills/implementation-check-against-papers/SKILL.md",
    "skills/verifying-claims-against-library/SKILL.md",
]:
    body = pathlib.Path(p).read_text()
    m = re.match(r"^---\n(.*?)\n---\n", body, re.DOTALL)
    assert m, f"{p}: no YAML frontmatter"
    fm = yaml.safe_load(m.group(1))
    assert fm.get("name"), f"{p}: missing name"
    assert fm.get("description"), f"{p}: missing description"
    tools = fm.get("allowed-tools")
    assert isinstance(tools, list) and len(tools) >= 5, f"{p}: allowed-tools incomplete"
    print(f"{p}: OK")
PY
```

**Step 3: Line-count check**

```bash
wc -l skills/drafting-with-grounded-sources/SKILL.md skills/implementation-check-against-papers/SKILL.md skills/verifying-claims-against-library/SKILL.md
```
Expected: each ≤200.

**Step 4: Cross-skill reference check**

```bash
grep -l "grounding-against-library" skills/drafting-with-grounded-sources/SKILL.md skills/implementation-check-against-papers/SKILL.md skills/verifying-claims-against-library/SKILL.md
grep -l "handling-extraction-quality" skills/implementation-check-against-papers/SKILL.md
```
Expected: all three reference the kernel; impl-check references handling-extraction-quality.

**Step 5: Confirm Tier-3 transcripts are PASS**

```bash
grep -l "^\*\*Final:\*\* PASS" tests/skills/phase4/drafting-tier3.md tests/skills/phase4/implementation-check-tier3.md tests/skills/phase4/verify-claims-tier3.md
```
Expected: all three listed (the `**Final:** PASS` sentinel must appear at start of a line).

**Step 6: Human verification gate**

Report to user:

> Phase 4 complete. Before Phase 5, in a fresh plugin-enabled session:
>
> 1. `/plugin reload`.
> 2. Confirm all six skills are in the skills list.
> 3. Test each procedural skill with a small realistic prompt and verify output structure (drafting → prose + appendix; impl-check → assertion table; verify-claims → claim table).
> 4. Pause Phase 5 if any structural break appears.
<!-- END_TASK_7 -->

---

## Done when

- Three SKILL.md files committed, each ≤200 lines, frontmatter valid
- Each procedural skill cross-references the kernel; `implementation-check-against-papers` cross-references `handling-extraction-quality`
- All three Tier-3 transcripts under `tests/skills/phase4/` show PASS
- User has confirmed all six skills are discoverable and produce prescribed output formats in a fresh plugin-enabled session
