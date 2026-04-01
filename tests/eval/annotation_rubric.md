# Evaluation Query Annotation Rubric

Last updated: 2026-04-01

This rubric defines how to consistently label evaluation queries for the retrieval evaluation framework. It covers three dimensions: **category** (what kind of retrieval challenge), **difficulty** (how hard for the system), and **relevance grade** (how related is each document to the query).

## Query Categories

Categories describe **what cognitive operation the retrieval system must perform** to match the query to the right document.

### Factual

The query asks for a specific piece of information that the document states directly. The answer is a relatively bounded fact, definition, or data point.

- **Test**: Could someone answer this by pointing to a specific passage?
- **Boundary with conceptual**: If the answer requires synthesizing across sections or explaining a mechanism, it's conceptual. If you could answer with a single quoted sentence, it's factual.
- **Example**: "What are the income eligibility requirements for energy assistance programs in Massachusetts?"

### Conceptual

The query asks about a relationship, mechanism, argument, or theoretical framework. Answering it requires understanding *how* or *why*, not just *what*. The answer is distributed across an argument rather than stated in one place.

- **Test**: Does answering this require explaining a relationship or mechanism?
- **Boundary with factual**: Factual queries locate information; conceptual queries require reconstructing an argument.
- **Example**: "What conditions are necessary for economic agents to engage in rational calculation?"

### Paraphrase

The query expresses the same information need as a factual or conceptual query, but deliberately uses **different vocabulary** than the source document. The vocabulary mismatch is the primary retrieval challenge.

- **Test**: Would this query match zero or very few keywords in the relevant document(s)?
- **Boundary with conceptual/factual**: Paraphrase is an overlay — a paraphrase query is also factual or conceptual in nature. Label it paraphrase when the vocabulary gap is the most interesting retrieval challenge. If the document uses similar vocabulary and the challenge is understanding the concept, label it conceptual.
- **Example**: "How does perceived danger from an opposing group strengthen identification with one's own group?" (document uses "threat" and "social identity")

### Methodology

The query asks about a method, technique, procedure, or research approach — *how something was done* rather than what was found or why it matters.

- **Test**: Is the query about a process, tool, or technique?
- **Boundary with conceptual**: "Why does this method work?" is conceptual. "What is this method / how is it applied?" is methodology.
- **Example**: "What are the main subtasks involved in computationally extracting structured event data from news text?"

### Comparative

The query explicitly asks for differences, similarities, or relationships *between* two or more distinct things — concepts, methods, documents, or positions.

- **Test**: Does the query contain or imply a comparison between distinct things?
- **Boundary with conceptual**: Many conceptual queries involve implicit contrasts, but comparative queries make the comparison the *point*. "How does X work?" is conceptual; "How does X differ from Y?" is comparative.
- **Example**: "Can the general strike be understood as a form of coercion, and how does this differ between political and proletarian versions?"

### Adversarial

The query is designed to test graceful failure: it asks about something the corpus cannot answer, either because it's entirely out of scope or because it's misleadingly close to in-scope topics.

- **Test**: Is the correct answer "this corpus doesn't contain relevant information"?
- Flagged with `"unanswerable": true` in the query set.
- **Example**: "What is the current stock price of Apple?"

## Difficulty Levels

Difficulty describes **how hard it is for the retrieval system to find the right document(s)**, not how hard the question is intellectually. Difficulty and category are intentionally orthogonal — a factual query can be hard (if stated in very different vocabulary), and a conceptual query can be easy (if it uses the document's own framing).

### Easy

High lexical overlap between query and document. Both keyword search (BM25) and vector search should find it.

- **Signals**: Query contains the document's title words, author names, or key technical terms. Ctrl-F in the document would find matching passages.
- **Example**: "What is constitutional hardball?" — the document defines this exact term.

### Medium

Some vocabulary overlap but not dominant. Vector search should handle it; BM25 might struggle or rank it lower. The query paraphrases the document's language or asks about the topic from a slightly different angle.

- **Signals**: The query shares some terms with the document but the core information need is expressed differently.
- **Example**: "How do political actors exploit informal norms and conventions?" — the document uses "constitutional hardball" and "norms" but not "exploit informal norms."

### Hard

Minimal lexical overlap. BM25 is likely to fail; vector search may struggle too. The query requires significant semantic inference — vocabulary mismatch, cross-document reasoning, or asking about implications rather than stated claims.

- **Signals**: A human reading both query and document would say "yes, this is relevant" but the connection isn't on the surface.
- **Example**: "What role has deliberate norm-breaking played in the asymmetric radicalization of American political parties?" — requires connecting Tushnet's concept to a broader political science argument.

## Relevance Grading

Each query is annotated with a relevance grade (0, 1, or 2) for every document it could plausibly relate to. In the query set JSON, `relevant_docs` lists grade 2 documents and `also_relevant` lists grade 1 documents. Unlisted documents are grade 0.

### Grade 2 — Highly relevant

The document directly addresses the query topic. A reader would say "this answers the question" or "this is about exactly this."

### Grade 1 — Partially relevant

The document discusses the query topic, but as a secondary concern. It addresses a closely related concept, or treats the topic as background rather than its primary focus. A reader of the document would encounter content about the query topic without having to make inferences.

- **Test**: Could you point to a passage in the document that a non-expert would recognize as being about the query topic?

### Grade 0 — Not relevant

The document doesn't address the query topic. A knowledgeable reader could connect the document to the query through inference or domain knowledge, but the document itself doesn't discuss it.

### Boundary examples

**Good grade 1** (document discusses the topic secondarily):
- Query about "group identification" → Melucci1995: collective identity is directly discussed, overlapping with but distinct from Tajfel's social identity.
- Query about "federal nutrition programs" → Massachusetts2024: discusses LIHEAP alongside food programs, partial topical overlap.

**Should be grade 0** (connection requires inference):
- Query about "group identification" → Goodwin2011: discusses protest motivation, connected to identity only through theoretical inference.
- Query about "alienated labor" → Rideout2016: both concern workers' conditions, but Rideout is about technology access, not labor theory.

### Design tradeoff note

Grade 1 requires the document to *discuss* the topic, not merely to be *connectable* to it through domain knowledge. This is a deliberate choice that prioritizes evaluation precision over testing inferential reach.

Rationale:
- Over-populating grade 1 with inferentially-connected documents rewards the retrieval system for returning tangentially related results, masking a real failure mode (noisy context in the RAG pipeline).
- Inferential connections are difficult to annotate consistently — catching some but not all adds noise without reliable diagnostic value.
- Inferential retrieval quality is better assessed through **comparative queries** (which test cross-document connections explicitly) and **qualitative RAG evaluation** (where surprising but useful retrievals are noticed in practice).
