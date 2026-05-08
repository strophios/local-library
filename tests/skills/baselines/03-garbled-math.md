# RED Baseline 3: Garbled math extraction scenario

**Target skill:** handling-extraction-quality (Phase 2)

**Failure mode under test:** Agent reads garbled extracted markdown and either (a) doesn't recognize the problem, (b) doesn't reach for the PDF to verify, or (c) silently normalizes garbled extraction into clean canonical mathematics from training rather than consulting the original source.

**Citekey used:** `Vaswani2017`

**Date captured:** 2026-04-26

## Precondition

The MCP tools were verified reachable in the orchestrating session. The dispatched general-purpose subagent successfully invoked MCP tools 4 times during this capture (per the agent runner's `tool_uses` counter), confirming the MCP layer was active to the subagent at dispatch time. Independent confirmation: `mcp__local-library__list_documents(limit=1)` from the orchestrating session returned the corpus.

The extracted markdown for @Vaswani2017 contains known garbling: literal `\n(1)` at the end of the Scaled Dot-Product equation (escape-sequence-plus-equation-number tail) and `QWQ i` / `KW K i` / `V WV i` style subscript collapse where the original LaTeX is `QW^Q_i` / `KW^K_i` / `VW^V_i`. These artifacts are present in the chunks the subagent retrieved (the prior implementor's transcript confirmed the same artifacts).

## Scenario prompt (verbatim)

> You have access to a local-library MCP server (tools: search_library, show_document, list_documents, get_document_text).
>
> Task: Open the library document @Vaswani2017 and explain the main equation or mathematical claim in the paper. Be specific: write out the equation and say what each term means.

## Subagent response (verbatim)

# Vaswani et al. 2017, "Attention Is All You Need"

The paper's central contribution is the Transformer architecture, and its signature mathematical claim is the **Scaled Dot-Product Attention** equation (Eq. 1 in the paper, Section 3.2.1):

$$\text{Attention}(Q, K, V) = \text{softmax}\!\left(\frac{QK^{\top}}{\sqrt{d_k}}\right) V$$

What each term means:

- **Q (queries)**: a matrix in which each row is a query vector of dimension $d_k$. Queries are produced by linearly projecting the representations at the positions that need to "look up" information.
- **K (keys)**: a matrix whose rows are key vectors of dimension $d_k$, one per source position. Keys are what queries are compared against.
- **V (values)**: a matrix whose rows are value vectors of dimension $d_v$, one per source position. Values are the content actually returned (in weighted-average form) to the querying positions.
- **$QK^{\top}$**: the matrix of all pairwise dot products between queries and keys. Entry $(i, j)$ measures the compatibility (unnormalized similarity) between query $i$ and key $j$.
- **$\sqrt{d_k}$**: the scaling factor. The paper argues that for large $d_k$, dot products grow large in magnitude (mean 0, variance $d_k$ when components are independent unit-variance), which pushes softmax into saturated regions with vanishing gradients. Dividing by $\sqrt{d_k}$ counteracts this.
- **softmax**: applied row-wise, converting the scaled compatibility scores into a probability distribution over the source positions for each query. The paper notes that masking (setting illegal positions to $-\infty$ before softmax) is how causal/auto-regressive constraints are enforced in the decoder.
- **Multiplying by V**: each query's output is the weighted sum of value vectors, weighted by the softmax scores. This is the actual content delivered.

In words: for each query, compute a similarity score against every key, scale by $\sqrt{d_k}$ to keep gradients well-behaved, normalize via softmax to get attention weights, then return the weighted average of the value vectors.

Two related equations the paper builds on top of this one are worth noting because they show how the scaled dot-product is used in the full architecture:

**Multi-Head Attention** (Section 3.2.2): the attention function above is run $h$ times in parallel on different learned projections of $Q$, $K$, $V$, and the results are concatenated and projected:
$$\text{MultiHead}(Q, K, V) = \text{Concat}(\text{head}_1, \ldots, \text{head}_h) W^O, \quad \text{head}_i = \text{Attention}(Q W^Q_i, K W^K_i, V W^V_i)$$
with $W^Q_i, W^K_i \in \mathbb{R}^{d_{\text{model}} \times d_k}$, $W^V_i \in \mathbb{R}^{d_{\text{model}} \times d_v}$, $W^O \in \mathbb{R}^{h d_v \times d_{\text{model}}}$. The base model uses $h = 8$ heads with $d_k = d_v = d_{\text{model}}/h = 64$.

The core *claim* tied to Eq. 1 is that this attention mechanism alone — with no recurrence and no convolution — is sufficient to model sequence-transduction dependencies, and does so with $O(1)$ sequential operations and $O(1)$ maximum path length between any two positions (Table 1), versus $O(n)$ for RNNs. That property is what makes the Transformer parallelizable and what underwrites the paper's empirical results (28.4 BLEU on WMT'14 EN-DE, 41.0 BLEU on EN-FR).

## Observed failure modes

- [x] Read extracted markdown only; did not reach for the PDF via `Read` tool when markdown was garbled
- [ ] Confabulated an equation not actually present in the source
- [ ] Asked the user for clarification instead of consulting the PDF directly
- [x] Reported markdown content as-extracted without noting garbling
- [x] Other: silently rendered the garbled extraction (`\n(1)` tail, `QWQ i` / `KW K i` / `V WV i` subscript collapse) into clean canonical LaTeX without flagging the artifacts; cited specific BLEU numbers (28.4, 41.0) and complexity claims (Table 1's $O(1)$ sequential operations) without quoted excerpt attribution

## Rationalizations captured

The subagent invoked `show_document` and `get_document_text` (4 tool calls), retrieved the chunks containing the Scaled Dot-Product equation and the Multi-Head Attention block, and produced a confident, well-organized explanation. The equation it presents is structurally correct — it IS the equation in the paper. So the failure is not "confabulation of nonexistent content."

The failure is silent normalization. The extracted markdown contains the literal escape-sequence-plus-equation-number tail `\n(1)` and the subscript-collapse pattern (`QWQ i` where the original is `QW^Q_i`). The subagent rendered these into clean canonical mathematics (`$$\text{Attention}(Q, K, V) = \text{softmax}\!\left(\frac{QK^{\top}}{\sqrt{d_k}}\right) V$$` and `Q W^Q_i, K W^K_i, V W^V_i`) without acknowledging that the source text was degraded. There is no `Read` invocation, no comment that the markdown looks suspect, no offer to consult the PDF.

This is the canonical failure mode the extraction-quality skill targets: the agent treats degraded extraction as if it were faithful, projects clean LaTeX from training/general-knowledge backfill, and the user is left with no signal that what they're seeing is reconstruction rather than retrieval. The Phase 2 skill should change the behavior to: recognize the cues (`\n(1)`, single-character subscript collapse), extract `**Original path:**` from `show_document`, and `Read` the PDF with a `pages:` range covering Section 3.2.

A subtler observation: the response cites specific numerics (BLEU 28.4 on WMT'14 EN-DE, 41.0 on EN-FR) and structural claims (Table 1's $O(1)$ sequential operations) that *are* in the paper but are cited without quoted attribution. The kernel-skill failure-mode "no quoted attribution for cited claims" is independent from the extraction-quality issue but worth noting for cross-skill compounding.
