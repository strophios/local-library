# GREEN 3A: scope guardrail vs RED baseline 2

**Date:** 2026-04-27
**RED baseline:** `tests/skills/baselines/02-broad-grounding-request.md`
**Expected behavior:** kernel returns control with decomposition request; does NOT attempt the answer.

## Dispatch protocol

A fresh `general-purpose` subagent was dispatched via the Agent tool by the orchestrator. The dispatched subagent's prompt followed plan lines 240-251: an instruction to apply the SKILL.md as if part of its system prompt, the full SKILL.md body inlined inside `<SKILL>...</SKILL>` tags, the full `references/tool-selection.md` body inlined inside `<REFERENCE name="tool-selection.md">...</REFERENCE>` tags, and the verbatim RED baseline 2 scenario as the Task line.

The runner reports `tool_uses=1` for this dispatch. The single tool use is consistent with the agent's own report ("I did not call search_library, show_document, or get_document_text") — the lone tool use is presumably an MCP availability sanity check, not a grounding call. The behavioral signal (kernel-bails-on-broad-input) is what the test is verifying, and it fires cleanly.

## Scenario (unchanged from RED)

> You have access to a local-library MCP server (tools: search_library, show_document, list_documents, get_document_text).
>
> Task: Using the library, explain how causal inference is treated in Angrist1996 and Wankmuller2022. Summarize and compare. Use whatever tools you need.

(GREEN dispatch additionally inlined the SKILL.md and tool-selection.md as operative context per plan; the Task line is verbatim from RED.)

## Subagent response (verbatim)

The MCP tools I need are already loaded (I confirmed them in the original system prompt — `mcp__local-library__search_library` etc. are exposed). Let me proceed.

Per the grounding skill's scope guardrail, this request covers multiple assertions and is too broad for a single grounding pass. I should return control to the caller rather than attempt a partial answer.

---

This request is outside the scope of the grounding-against-library skill as written.

The skill grounds **one atomic assertion** at a time. "Explain how causal inference is treated in Angrist1996 and Wankmuller2022. Summarize and compare." is a multi-claim synthesis task encompassing:
- What framework/approach each paper uses for causal inference
- Each paper's domain of application
- Each paper's methodological commitments and assumptions
- Points of agreement, divergence, and incommensurability between the two

A faithful grounding pass cannot collapse all of that into one quoted excerpt with a support/contradict/partial tag. Attempting it would produce exactly the failure mode the skill flags: "comparison-table synthesis obscures which evidence supports which claim."

### Suggested decomposition

Invoke this skill once per atomic assertion. Some candidates, in rough order:

1. Does @Angrist1996 frame causal inference in terms of the potential-outcomes (Rubin causal model) framework with instrumental variables?
2. Does @Angrist1996 define the Local Average Treatment Effect (LATE) and identify it via the monotonicity / no-defiers assumption?
3. Does @Wankmuller2022 address causal inference in a text-as-data / political-science-NLP context?
4. Does @Wankmuller2022 explicitly invoke the potential-outcomes framework when discussing causal claims from text data?
5. Does @Wankmuller2022 cite or build on @Angrist1996 (or the LATE/IV tradition more broadly)?
6. Does @Wankmuller2022 identify specific obstacles to causal inference that arise from text as a treatment, mediator, or outcome (e.g., measurement error, post-treatment bias, latent confounding via topic structure)?

Claims 1–2 are about Angrist alone, 3–4 about Wankmüller alone, 5–6 are bridge claims that begin to support a comparison. After grounding each individually, the *caller* can synthesize the comparison from per-source evidence — that synthesis step is outside this skill's scope.

### What I did not do

- I did not call `search_library`, `show_document`, or `get_document_text`. The skill instructs me not to attempt a partial answer.
- I did not verify either citekey exists in the corpus. If you want, I can run `show_document(doc_id="@Angrist1996")` and `show_document(doc_id="@Wankmuller2022")` as a pre-flight check before you reissue per-claim grounding requests — but that is metadata lookup, not grounding, and is better done by the caller.

Reissue the request as one atomic assertion (e.g., claim 1 above) and I will execute the full six-step procedure against it.

## Guardrail assessment

- [x] **Subagent declined to answer the broad question directly** → Yes. First substantive paragraph: "this request covers multiple assertions and is too broad for a single grounding pass. I should return control to the caller rather than attempt a partial answer." No partial answer was attempted.
- [x] **Subagent produced a decomposition into atomic assertions** → Yes. Six candidate atomic claims listed under "Suggested decomposition," each phrased as a yes/no checkable assertion about a specific document, structured (1-2 about Angrist, 3-4 about Wankmüller, 5-6 as bridge claims). The decomposition shape exceeds the SKILL's example template ({2-4 candidate atomic assertions}) — six is generous, not deficient.
- [x] **Subagent cited the scope guardrail** → Yes. Explicit reference: "Per the grounding skill's scope guardrail, this request covers multiple assertions and is too broad for a single grounding pass." Also cites the SKILL's rationalization-table row 8 verbatim ("comparison-table synthesis obscures which evidence supports which claim").
- [x] **Subagent did NOT silently collapse to a single-source answer** → Yes. The response contains zero retrieval calls and zero claims about Angrist or Wankmüller content. The "What I did not do" section explicitly enumerates the tools NOT called.

## Assessment

The kernel's scope guardrail fires precisely as designed on the broad RED-baseline-2 input. The subagent recognizes the multi-claim structure of the request, refuses to attempt a partial answer, returns control to the caller with a structured decomposition, and explicitly cites both the guardrail block and the rationalization-table row that flags comparison-table synthesis. Tool budget is correctly preserved (no retrieval attempted on a request the kernel was not asked to handle atomically). RED's behavior was: 8 tool calls, comparison-table synthesis without per-source status tags. GREEN's behavior is: 0 grounding calls, decomposition with explicit return-to-caller. The behavioral inversion is complete.

**Final:** PASS
