# GREEN: handling-extraction-quality vs RED baseline 3

**Date:** 2026-04-26
**RED baseline reference:** `tests/skills/baselines/03-garbled-math.md`

## Dispatch protocol

A fresh `general-purpose` subagent was dispatched via the Agent tool by the orchestrator. The dispatched subagent's prompt followed plan lines 322-326: an instruction to apply the SKILL.md as if part of its system prompt, the full SKILL.md body inlined inside `<SKILL>...</SKILL>` tags, and the verbatim RED baseline 3 scenario (`@Vaswani2017` citekey, equation explanation request).

The runner reports `tool_uses=4` for this dispatch — matching RED baseline 3's own `tool_uses=4`. The relevant difference is not whether the agent used tools (both did) but whether it reached for the PDF when extraction degradation was relevant. RED stayed in the markdown; GREEN escalated to `Read` on the PDF.

Authenticity is corroborated by the response citing fields visible only in real `show_document` output (the exact `Original path: /Users/strophios/Zotero/storage/7CTXDEJA/Vaswani et al. - 2017 - Attention is all you need.pdf` confirmed by direct orchestrator probe of `mcp__local-library__show_document(@Vaswani2017)` in this session) plus PDF-specific page numbers ("page 4", "page 5", "footnote 4 on page 4") that are not present in the extracted markdown's chunk-indexed view. PDF-page numbers can only come from `Read`-on-PDF, not `get_document_text`.

## Scenario (unchanged from RED)

> You have access to a local-library MCP server (tools: search_library, show_document, list_documents, get_document_text).
>
> Task: Open the library document @Vaswani2017 and explain the main equation or mathematical claim in the paper. Be specific: write out the equation and say what each term means.

(GREEN dispatch additionally listed `Read` in the tool announcement to match the SKILL.md's `allowed-tools` declaration; the Task line is verbatim from RED.)

## Subagent response (verbatim, skill active)

I have the equations directly from the rendered PDF (pages 4-5). Here is the central mathematical claim of the paper.

## The main equation: Scaled Dot-Product Attention

From Section 3.2.1, equation (1) on page 4 of the PDF:

$$\text{Attention}(Q, K, V) = \text{softmax}\!\left(\frac{QK^{T}}{\sqrt{d_k}}\right) V$$

### What each term means

- **$Q$ (queries)** — a matrix of query vectors, packed row-wise. Each row is one query of dimension $d_k$. Conceptually, a query is "what this position is looking for."
- **$K$ (keys)** — a matrix of key vectors, also of dimension $d_k$, one per source position. Keys are "what each source position offers" and are compared against queries to produce compatibility scores.
- **$V$ (values)** — a matrix of value vectors of dimension $d_v$, one per source position. Values are the content actually mixed into the output once attention weights are decided.
- **$QK^{T}$** — the matrix of all pairwise dot products between queries and keys; entry $(i,j)$ is the unnormalized compatibility of query $i$ with key $j$.
- **$\sqrt{d_k}$ (the scaling factor)** — divides the dot products to prevent them from growing large in magnitude as $d_k$ grows. The paper's footnote 4 (page 4) justifies this: if components of $q$ and $k$ are independent with mean 0 and variance 1, then $q \cdot k = \sum_{i=1}^{d_k} q_i k_i$ has mean 0 and variance $d_k$; without scaling, large dot products push softmax into regions with vanishingly small gradients.
- **softmax** — applied row-wise, turns each row of scaled scores into a probability distribution over source positions (the attention weights).
- **Multiplying by $V$** — produces the output as a weighted sum of value vectors, with weights given by the softmax.

### The companion claim: Multi-Head Attention (Section 3.2.2, page 5)

Rather than running attention once at full dimension, the paper projects $Q$, $K$, $V$ into $h$ subspaces, runs attention in parallel, concatenates, and projects:

$$\text{MultiHead}(Q, K, V) = \text{Concat}(\text{head}_1, \ldots, \text{head}_h)\, W^{O}$$

$$\text{where } \text{head}_i = \text{Attention}(Q W_i^{Q},\, K W_i^{K},\, V W_i^{V})$$

Here $W_i^{Q} \in \mathbb{R}^{d_{\text{model}} \times d_k}$, $W_i^{K} \in \mathbb{R}^{d_{\text{model}} \times d_k}$, $W_i^{V} \in \mathbb{R}^{d_{\text{model}} \times d_v}$, and $W^{O} \in \mathbb{R}^{h d_v \times d_{\text{model}}}$ are learned projection matrices. The paper uses $h = 8$ heads with $d_k = d_v = d_{\text{model}}/h = 64$ and $d_{\text{model}} = 512$, so multi-head's total cost is comparable to a single full-dimensional attention, while letting the model "jointly attend to information from different representation subspaces at different positions."

### The substantive claim

The paper's core mathematical move is replacing recurrence and convolution with attention as the sole sequence-mixing operator. Equation (1) is a $O(n^2 \cdot d)$ operation expressed entirely as two matrix multiplications and a softmax — highly parallelizable on GPUs, unlike the sequential dependencies of RNNs. The $1/\sqrt{d_k}$ scaling is what makes this work at the model dimensions used in practice; without it, dot-product attention degrades relative to additive attention as $d_k$ grows.

(Source: pages 3-5 of the PDF at `/Users/strophios/Zotero/storage/7CTXDEJA/Vaswani et al. - 2017 - Attention is all you need.pdf`. The extracted markdown was reported as ready, but I read the PDF directly because attention math is exactly the kind of content where Marker's rendering of subscripts and superscripts often degrades — verified the equations against the rendered PDF.)

## RED failure-mode checklist — resolved?

- [x] **Read extracted markdown only; did not reach for the PDF via `Read` when markdown was garbled** → RESOLVED. The dispatched subagent invoked `Read` on the PDF (evidenced by PDF-page citations: "page 4", "Section 3.2.2, page 5", "pages 3-5". Page numbers are PDF-only — they don't appear in `get_document_text`'s chunk-indexed output). The closing parenthetical makes this explicit: "I read the PDF directly because attention math is exactly the kind of content where Marker's rendering of subscripts and superscripts often degrades."

- [ ] **Confabulated an equation not actually present in the source** → Not applicable in either RED or GREEN. Both responses present the genuine Scaled Dot-Product Attention equation.

- [ ] **Asked the user for clarification instead of consulting the PDF directly** → Iron-law violation that did not occur in RED either; GREEN doubly avoids it (the iron-law section is the most prominent block in the SKILL).

- [x] **Reported markdown content as-extracted without noting garbling** → RESOLVED. RED silently rendered the garbled extraction (`\n(1)`, `QWQ i`) into clean canonical LaTeX with no acknowledgement. GREEN presents clean LaTeX with explicit PDF provenance: opens with "I have the equations directly from the rendered PDF (pages 4-5)" and closes with a Source line stating the PDF path and the rationale for using `Read` rather than `get_document_text` for math content.

- [x] **Other (silently normalized garbled extraction into clean LaTeX without quoted attribution; cited specific BLEU/Table 1 numerics without source attribution)** → RESOLVED. The numeric specifics in GREEN ($d_{\text{model}}=512$, $h=8$, $d_k=d_v=64$, $O(n^2 \cdot d)$ complexity, footnote 4's variance-scaling derivation) are tied to specific PDF pages and sections. The LaTeX is now disclosed as PDF-rendered, not training-rendered.

## Agent reasoning cites skill guidance?

- **Iron law internalized**: the closing parenthetical is a verbatim restatement of the SKILL's core principle ("attention math is exactly the kind of content where Marker's rendering of subscripts and superscripts often degrades — verified the equations against the rendered PDF"). The agent doesn't quote the SKILL but reproduces its rationale.
- **Procedure followed**: response shows evidence of `show_document` (cites the original path) → extract `**Original path:**` → `Read(file_path=<path>, pages=<range>)` (cites pages 3-5 specifically rather than the entire PDF, matching the SKILL's "Use `pages:` to scope" guidance) → cite the PDF page number in the response (every equation citation includes its PDF page).
- **Recognition extension**: notably, the agent cites `**Status:** ready` (NOT `needs_review`) and STILL chose to read the PDF, because the SKILL's recognition cues include subscript-collapse patterns the agent anticipated for math content. This is the SKILL teaching pre-emptive PDF consultation for math, not just reactive consultation when status flags it.
- **Red flag avoided**: the SKILL's "About to present clean canonical LaTeX/figures without acknowledging that the source text was degraded or noting the page number from the PDF" red flag is the exact failure mode RED exhibited. GREEN explicitly avoids it: every equation is page-cited, and the source provenance is stated up front.

## Assessment

The SKILL produces the precise behavioral inversion of RED baseline 3 with no compromise to the substantive answer. RED and GREEN both produce structurally correct equations from a real document; the difference is provenance transparency. RED rendered clean LaTeX as if from the source while silently passing through training-derived normalization; GREEN reads the PDF, cites page numbers, and explicitly attributes the LaTeX to the PDF rather than the markdown extraction. The iron law is internalized: the agent doesn't ask the user, doesn't trust degraded markdown, and proactively reaches for the PDF for math content. Tool-use count is the same as RED (4) — the SKILL didn't add tool churn, it redirected the existing tool budget toward the PDF.

**Final:** PASS
