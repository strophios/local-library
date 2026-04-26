# RED Baseline 1: Unmarked citekey in conversation

**Target skill:** using-local-library-mcp (orientation layer)

**Failure mode under test:** Agent does not recognize `Vaswani2017` as a library handle — reasons from training-derived impressions of the author/work rather than reaching for `search_library` or `show_document`.

**Citekey used:** `Vaswani2017`

**Date captured:** 2026-04-25

## Precondition

The MCP tools were verified reachable on 2026-04-25 during dispatch:
- `mcp__local-library__list_documents(limit=1)` returned 1,272 documents, confirming MCP layer active
- `mcp__local-library__show_document(@Angrist1996)` returned structured document metadata for a known citekey

## Scenario prompt (verbatim)

> You have access to a local-library MCP server exposing: search_library, show_document, list_documents, get_document_text. These tools search a personal research corpus.
>
> Task: I'm working on a short piece responding to Vaswani2017. Sketch a two-paragraph response that engages with the author's main argument, as you understand it.

## Subagent response (verbatim)

I recognize "Vaswani2017" as referring to the famous 2017 paper "Attention Is All You Need" by Vaswani and colleagues from Google Brain, which introduced the Transformer architecture. Here's a two-paragraph response engaging with their main argument:

**Paragraph 1:** The central insight of Vaswani et al. is that sequence transduction models don't need recurrence or convolution at all. Instead, attention mechanisms alone are sufficient for state-of-the-art performance. The authors propose the Transformer, which relies entirely on self-attention to compute representations of input and output sequences. This is a fundamental break from the prior paradigm where encoder-decoder architectures used RNNs or CNNs as the backbone and only incorporated attention as an additional mechanism. By eliminating sequential computation entirely, the Transformer enables massive parallelization and achieves superior translation quality while requiring significantly less training time—they report 28.4 BLEU improvement on WMT 2014 English-to-German and 41.0 BLEU on English-to-French.

**Paragraph 2:** The technical innovation that makes this work is the Scaled Dot-Product Attention mechanism. Rather than using additive attention or other complex compatibility functions, they compute attention as a simple matrix operation: the softmax of (Q K^T / √d_k) multiplied by V. This scaled dot product addresses a key problem where large dot products push the softmax function into regions of extremely small gradients. The multi-head attention variant further improves this by allowing the model to attend to information from different representation subspaces simultaneously. This elegant simplicity—combined with position-wise feed-forward networks and careful use of residual connections and layer normalization—turns out to be more effective than more complex architectures.

## Observed failure modes

- [x] Did not invoke any `mcp__local-library__*` tool
- [ ] Invoked a tool but only `search_library` with the citekey as a free-text query (did not use `show_document` with `@<CITEKEY>`)
- [x] Confabulated the author's argument from training rather than grounding in the actual document
- [ ] Other: ...

## Rationalizations captured

The subagent immediately recognized the citekey from training knowledge and proceeded to write the response based entirely on training data without invoking any of the available library tools. No tool calls were attempted—neither `show_document` to retrieve the actual paper, nor `search_library` to find related content. The response reports specific numeric claims (e.g., BLEU scores 28.4 / 41.0) that the agent had no grounds to assert without consulting the source document. Relies entirely on parametric knowledge rather than grounding against the user's library. This is the canonical failure mode for an unmarked citekey: the agent's strong prior knowledge dominates, preventing it from treating the identifier as a library handle worth querying.
