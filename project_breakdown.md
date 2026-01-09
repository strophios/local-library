
This project breaks down into the following modules: 


- Import raw content
    - From URL
    - Raw PDF
    - PDF (or URL) from Zotero

raw content can originate from: the web (passed as URL), local storage (passed as a path to PDF), or Zotero (connection to the sqlite database, resulting in URL or path)

flow from URL: SingleFile CLI to download to HTML -> trafilatura to extract/parse main text to markdown
flow from PDF: PDF file is itself the raw content -> PyMuPDF (or PyMuPDF4LLM) or marker or DocLing
    (potential to use Docling for both PDF and HTML?)



- Parse content to plain text (markdown)

- Generate metadata




- record level flow: call to create a document record. passed either a bare content locator (URL/path) or a content locator with metadata (taken from Zotero). 
    - time stamped record (with UUID) is created with any provided metadata filled in. 
        - (we also record the passed URL/path in order to allow duplicate checking later? or maybe we get a file hash for the raw content?)
    - the raw content downloaded/copied (not sure whether we're copying, aliasing, or what PDFs from Zotero) and the path to it is added to the record
    - the raw content is parsed to markdown which is saved. either in the database or as a separate file (either alongside or separate from the raw content)
    - extract metadata from raw/parsed content as necessary. figure there are two ways to condition this: 1) do it only if no metadata was provided as input, 2) do it only if any of the key metadata is missing (key values to be defined, but likely include title, author, pub date). The first avoids attempting to add metadata to Zotero records (which I generally will not want to do), while the second allows for the provision of partial metadata in non-Zotero cases, which could be a useful feature. 
    - 

duplicate checking?
- could check at multiple points. some subset of: on attempted record creation (the passed URL/path), on raw content download (using file hash), on metadata extraction/entry (using the metadata), on chunking and embedding (using vector similarity), any others?
    - and the various points could have different levels of strictness to the criteria and/or different default behaviors; e.g., passing a URL that's already in the database gets you a "not doing that, it's a duplicate, would you like to open the connected note or edit the metadata?", but sufficiently high vector similarity gets you "hey, this is extremely similar to document X; are you sure it's not a duplicate?"

Zotero import functions by opening a connection to the Zotero database and iterating over all items not already in our database. For each one, it checks whether there's an attachment. If so, it calls the "new record flow", passing the path to the attachment and the Zotero CSL-JSON record. 


thinking in terms of objects/interfaces: every object is a document, documents are all the same (in terms of what their component parts are, etc.), but one of their "attributes" is always a "raw content" object, but that raw content object is just an interface into "raw content html", "raw content pdf", "raw content epub", etc., or something


parts: content ingest (pdf/html/epub/etc. to markdown), markdown to embedding, handling the embeddings (indexing, vector similarity search, etc.), 



I want to get started on this by figuring out the RAG implementation. That is, in some ways, the most interesting and potentially most useful piece of this: having an effective embedding database of my full Zotero library could itself be dramatically useful, even without the ability to query it via LLM, and adding that will make it even lower friction to use. I understand the basics of what RAG is and how it works, but I haven't ever built an implementation myself and I'm not familiar with the current state of the ecosystem (available tooling, advantages/disadvantages of whatever off-the-shelf solutions there are versus building a more bespoke implementation, the varying levels of local vs. network reliant, etc.). In building the RAG system, I am looking to do handle the following steps/functions:

1. PDF to markdown (ideally well formatted and structured markdown; e.g., omitted or clearly delimited headers/footers/references, accurate parsing of headings to assist with chunking, etc.)
2. Markdown to embeddings (including potential chunking strategies, using local models vs. external providers, etc.)
3. Handling the embeddings (effective, fast, and efficient database solutions, indexing strategies, search implementations, etc.)
4. Querying by LLM
5. Ultimately will want custom tooling to allow both me and LLM agents I invoke to work with the database specifically from the perspective of academic citations/references; this may include things like: 
    - Given an input sentence, is there something in my database I could cite for this?
    - Acting as an autocomplete source in Neovim, suggesting citations based on semantic similarity to the preceding text when invoked via the cite shortcut.
    - Checking the citations in a document; i.e., given a manuscript with citations (via citekey) to refs in the RAG database, confirm that the cited works actually support the content they are being cited for.
    - The inverse: given a document, checking whether any of its major claims are substantially contradicted by any of the references in the database. 
    - etc.

In building this system, I am working within the following constraints: 

- My current Zotero library contains 1390 items. Not all of them have attached PDFs, but I am obviously continuing to add items (and, ultimately, will be adding items to the fully implemented local-library much faster), so we're talking about potentially thousands of items, some of which may be relatively small (especially with the full local-library), but many of which are 20+ page PDFs running 10k or more words. I'd also, ultimately, like to be able to handle books (though this is a more minor concern and not an immediate requirement). So, in constructing your report, keep that in mind as the scale we're working at. This will be particularly relevant when thinking about performance and the fact that I'd like to store and run as much as possible locally (not necessarily the actual LLM that will use the RAG database, but processing, storing, and embedding the content), but am willing to go with non-local solutions if they offer sufficient increases in quality or performance (for reference, "local" presently means a 2021 MacBook Pro with an M1 Pro chip). 
- I have a mild preference for Python or Rust as implementation languages.
- Portability, transparency, and a clean interface (i.e., to work easily with other applications, enable extensibility, etc.) is a *requirement*.
- This system will utlimately fit into the overall local-library project.

I want you to put together a report covering the various ways to build such a RAG system, explaining and evaluating them, and offering well reasoned recommendations as to the 1) easiest, 2) absolute best, and 3) optimum return on effort invested options. This report does not need to be exhaustive, you should absolutely rule out options that are a bad fit and you don't need to waste my time or yours going into detail on them, but you should be thorough in what you consider. Keep in mind that I have not previously implemented any of this, so the reports will be most useful to me if they provide additional context and explanation for the *why* and *how*. 

The first step in creating this report is to think through everything I've just given you and process it into guidance that we can reference in the process going forward. Ask any clarifying or follow up questions if needed, then write out that guidance to RAG_report_guidance.md

---

The guidance looks solid as-is. One note as we proceed: don't over-index on any existing tooling suggestions or even architectural choices, as we proceed with the report. The *requirements* are important (and are accurately documented in the guidance doc), but part of the point of the report is to potentially surface things (alternatives, issues, etc.) that we don't know about yet. 

To proceed with the report, I want you to dispatch a separate research agent for each of the RAG system components, resulting in five separate reports. Then use five separate critical reviewer agents to check each report for accuracy, review it, and revise it. Then write those reports out to RAG_background/ as markdown files. Our ultimate goal will be a final summary report with recommendations and rationales, but before moving on to that, I want you to review these component reports, especially for any gaps, open issues, or potential integration challenges, and check-in with me.

---

To quickly address your questions: 

1. A quick investigation into DuckDB VSS seems like a good idea. You don't necessarily need to go deep in depth, but I'd like enough that we can potentially make a decision. 
2. I'm not sure quite how important native hybrid search is, but I do know that I don't need *strict* single-file simplicity, so I'm certainly okay with this tradeoff, so long as non-single-file option isn't impossibly complex.
3. I suspect the 200 line wrapper is sufficient, although I would be curious to hear a little bit about the notional upsides of LiteLLM.
4. We can focus mainly on the suggestion/autocomplete MVP, but do address the other features, at least in high-level summary, to make clear *why* we're focusing on suggestion/autocomplete and what would need to change to make the other features workable. 

Now you can proceed to the final summary report, basing it on the individual reports and the results of any further investigations you think are necessary (which can be conducted by sonnet subagents), and including your recommendations. Have the report reviewed by a critical reviewer subagent, make any necessary revisions, and write it out to a new markdown file in RAG_background/ , then present a high level overview to me. 

---

Finally, before we get to building, I want you to write out a summary of this whole research and writing process to summary_logs/rag_research_process_2.md . In writing this summary, the goal is to provide context so that a future user or agent can 1) most effectively build on and extend the report; and/or, 2) understand what worked well and what didn't in the process of making the report so that the process can be improved. 


Review those reports, consider whether there are any gaps or open issues requiring further research. 

If so, dispatch agent(s) to investigate those areas and report back to you. 


Having reviewed both the final summary report and the individual subject reports (all the markdown files in @RAG_background/), I've got some follow up questions. Before the questions though, I want you to start by getting the necessary context, so review @RAG_report_guidance.md and the resulting reports in @RAG_background/ Once you've done that, report back and let me know if you've got any immediate thoughts or questions. This is just to make sure we're on the same page before actually getting to the questions. 

---

Now that we're on the same page, we can get to my questions. I'd like you first review the questions (included below, separated by subject) and let me know if there's anything you'd like me to expand on or clarify before you start on answering them.

- PDF processing: 
    - While I would like to do processing locally in general, I do have access to remote compute with NVIDIA GPUS and would be okay with the one time logistical cost of using it to process some or all of my existing Zotero library. There are also a significant number of older documents in my library that will require OCR. Given this, is olmOCR enough of an improvement over Marker that it would be worth the hassle to use it to process existing PDFs that need OCR, while still using Marker in the actual production pipeline?
- Embeddings:
    - I will also ultimately want to have semantic-based clustering for automated document tagging (both generation and application). Does this change the calculus around the utility of late chunking and the importance of task instruction prefixes? Specifically, I would imagine that late chunking without the need for a specific task prefix would result in more general purpose embeddings, which could then support both the RAG pipeline (via chunking) and semantic-based clustering. Or are embeddings generated, e.g., using nomic-embed-text with the "search_document" prefix, still meaningfully usable for clustering while also being significantly better for search?
    - Why not go with late chunking with nomic-embed-text as the recommendation?
    - Is the recommendation of nomic-embed-text based on the 86% MTEB score? Since it looks like the actual score is ~65%?
- Vector storage: 
    - Minor questions: 
        - Is sqlite-vec production ready? 
        - Is LanceDB enough additional complexity to make it not worth it?
- LLM Querying: 
    - The summary report suggests a custom wrapper for handling multiple providers, but it doesn't actually address the vast majority of the task here; i.e., query processing, retrieval, and response generation. These are addressed in the separate llm_query_interface_report.md report (especially in, e.g., recommendation 2). Recommended path 2 is the only one which doesn't involve LiteLLM, are we assuming that we're just following that one?
- Citation infrastructure: 
    - Rather than claim verification and contradiction detection in any kind of strict sense, what about looser approaches designed essentially as time-savers for human verification? So, for claim verification, instead of asking "does this paper support this claim?", the goal is "is it plausible that this paper supports this claim?" or "is this paper strongly related to/about this claim?"; and for contradiction detection, instead of "is there anything in my library that contradicts this?", the goal is "what in my library is most likely to contradict this?" or "what are the things in my library most closely related to this claim that don't strongly support it?" In both cases the tool helps narrow the search space for human verification by either shifting the nature of the question or lowering the confidence level needed (or both). 



ooh, is there anything special we want/need to do for particularly long documents? I'm thinking in particular about books (whether in ebook formats or as PDFs)



## Implementation Layers (Build Order)

1. **Storage layer**: SQLite schema + filesystem layout for documents and notes
2. **Ingestion layer**: Handlers for web URLs (trafilatura) and PDFs (marker/PyMuPDF)
3. **Zotero import**: Read Zotero database, map to internal schema
4. **Note management**: Generate markdown stubs, maintain frontmatter links
5. **Embedding pipeline**: Chunk documents, compute embeddings, store vectors
6. **Auto-tagging**: Nearest-neighbor tag suggestion or LLM classification
7. **RAG interface**: Query interface feeding relevant chunks to LLM
8. **Zotero export**: Push tags back, optional note sync
