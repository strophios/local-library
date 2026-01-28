
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

I went ahead and reviewed them both and they overall look really good. I do have a couple of questions/comments. Let's talk about @build_philosophy.md first: 

1) I'm curious about the setup and flow: your statement of the motivating problem makes sense, but you don't actually explain the specific relationship between "The Problem" and "The Two-Axis Model". This is exacerbated by some of the language: you state the problem in terms of bottom-up/layer-first vs. top-down/feature-first and the directional spatial language of bottom-up/top-down resonates with the horizontal/vertical language in the two-axis model, but that resonance doesn't (to me) have any immediate meaning or payoff. Likewise, *layer*-first obviously lines up with the language of "horizontal layers" in the two-axis model, and they're even arguably the same thing, but feature-first doesn't particularly align with "pipeline" and they're not necessarily the same thing. 

I'd like to revise the opening to be more explicit about the relationship between "The Problem" and "The Two-Axis Model" and to clarify the language. Now, to be clear, it's entirely possible that you have a particular relationship between "The Problem" and "The Two-Axis Model" in mind, for which the language choices are doing useful work (or just that you have specific reasons for the language). If that's so, I'd like to hear it and then we can work on revising the opening on that basis. If not, we can work on pinning one down as we revise.

2) I had another thought that might contribute to the "Why Pipeline-First?"/"Why Layer-Complete?" comparison, and I'm curious whether you think it's worth incorporating (either as another pair of bullet points or in some other way): Pipeline-first (helps) prevent mistakes in architectural decisions that can result from a blindness to practical functional requirements. / Layer-complete prevents the deferral/avoidance of necessary architectural decisions. Thoughts?

for clarifying language in the opening, maybe cut bottom-up/top-down and just use a single distinction, then change "layer" to "system" (or something else)?


Yeah, the revisions are solid. Now we can talk about the build plan. As a both a practical plan and a useful document, I think it's already quite good. But I have two meta-level concerns about how to most effectively fit it into the larger project. First, it currently has a brief "What's Deferred" section and then notes some components as "Future" features in parentheses in the overview of the architectural layers. This is a totally reasonable way to do this, but I'm wondering if we might be better of reframing this as just the "immediate"/"MVP"/"minimum (pdf) pipeline" build plan (or similar), with a ground-level awareness that it will be incomplete. Then we'd keep a record of stuff that will be implemented in future steps in a separate document, allowing us to be more complete and detailed in discussing those features without either wasting tokens in the active build plan or accidentally losing track of a future feature by leaving it out. 

The second concern is related to the question of overall implementation and what we're deferring, so I'd like your thoughts on this before we bring in the second issue. 


Yep, that's basically exactly what I had in mind. The second concern is about making sure we don't lose any of the work we've done in previous sessions as we start to move forward with this build plan. Specifically, we did a fair bit of preparatory work on the RAG first approach (see @RAG_background/00_final_summary_report.md ), which is similar to our current "thick slice"/pipeline approach, but still quite different, with some overlap (including additional helpfuld detail in some places) but also a number of distinct concerns and features. This kind of the ideal test case to make the most of the two file approach: we want to fold the overlap into the current build plan and move the non-overlapping features into the future_roadmap.md

Does this match your thinking?

We're taking the first steps to actually implement the local-library system described in @CLAUDE.md A lot of planning work has been done and we have an initial @build_plan.md as an overarching guide for building Phase 1, the PDF pipeline. Following the build plan, our task here is to complete the first milestone "M1: Record Creation and Storage" (unless you think a larger or smaller implementation chunk is substantially preferable). Additionally, take a look at @build_philosophy.md as this will guide our approach (at this stage of the project it's likely to be especially relevant for making tooling and architectural decisions). 

1. The full library is ~1400 items at present, the large majority of which have attached PDFs. These are mostly journal articles, but a fair number of conference papers and preprints, as well as a few books, book sections, and reports. Most of these should be relatively easy cases, but there are a number of scanned and non-English documents (some of which are both) and a limited number of historical texts (though nothing handwritten or pre-1800). I've already selected a relatively representative set (or at least a set with good coverage of potential kinds of cases) and put the PDFs in /pdf_test_set
2. Robust vs. manual: Both. Robust automated validation will remain especially useful in production, but having a convenient setup for manual review will be helpful as we're building the prototype. 
    Metadata: I do have at least some ground-truth metadata for the test set available.
3. I have run the add command on two examples thusfar and the extraction quality has been fairly good, but there are a number of particular failure modes I'm worried about: 
    - OCR: both issues of OCR quality in general, but also the failure to use it when appropriate (i.e., if Marker doesn't recognize that it's extracted garbage or extremely incomplete text that would be improved by OCR). 
    - Reading order issues, especially with OCR'd PDFs and especially especially with pdfs that are photocopies of books (i.e., they have facing pages as a single image) or other common but oddly arranged texts (newspaper articles being another example, though uncommon in my particular use case).
    - Finally, while I don't think this is a Marker issue per se, but eventually I'll care about how well we can deal with boilerplate (e.g., page numbers, copyright info, etc.) and annotations (e.g., bibliographic references, footnotes, etc.).
4. Probably option (A) since that's where we construct the archetype of what we're trying to extract. That said, I might actually bundle it slightly differently: metadata *handling* as one step, i.e., when provided with some metadata in some specified format, how do we handle it (so CSL-JSON validation, citekey generation, indexed field extraction, etc.) and then metadata *extraction* as a separate step, i.e., how we get metadata out of PDFs and their extracted markdown when it isn't provided. And we'd build the testing infrastructure as part of this step.  


1. I've already selected a first run at a golden set and placed them in `pdf_test_set/`. With only 20 PDFs, I've simply moved them over. The larger smoke set is most likely best handled via symlinks, although I'm ultimately agnostic here. 
2. The BetterBibTex JSON export. Unless I've missed something, that's where we're getting our Zotero metadata from, we only access the database in order to locate attachments. If we wanted to start using the database for anything else, that'd be an entire additional layer we'd need to build. 
3. Obviously some general testing goals and approaches are discussed in the build plan and build philosophy, but for specific patterns you'll need to investigate yourself. However, you should keep in mind that the testing we're doing here is in many ways quite different from the software testing we're otherwise doing, and the testing patterns may need to differ accordingly. 
4. As mentioned above, I've already selected a first run test set, stored in `pdf_test_set/`.


There are definitely some documents in my Zotero library where it would be easy to find the complete actual text to use as a ground truth for checking extraction quality. I haven't specifically found any yet, but at the very least things like, e.g., the Communist Manifesto would pretty straightforwardly work. See also things that I have (or can access) ebook copies of that are in the library as PDFs.

Potential options: 

- Ökonomisch-philosophische Manuskripte aus dem Jahre 1844: already in Zotero
    - https://www.marxists.org/deutsch/archiv/marx-engels/1844/oek-phil/index.htm
- Manifest der Kommunistischen Partei: appears to not already be in Zotero (in German), but I suspect I could find an ugly/requires OCR pdf version online pretty easily. Also, I do have a (pretty clean) PDF version on my hard drive (easily searchable via Spotlight). Below are options for the clean full text: 
    - https://de.wikisource.org/wiki/Manifest_der_Kommunistischen_Partei_(1848)
    - https://www.marxists.org/deutsch/archiv/marx-engels/1848/manifest/index.htm
- The Gadamer book, which I'm pretty sure I had in German + English?
- Pretty sure there are journal articles that show up in both JSTOR and elsewhere where one version has the text as machine readable and one doesn't?


To-do: 

- Improve extraction, including updating/improving testing for these things: 
    - Dealing with boilerplate (page numbers, copyright info, etc.) and annotations (footnotes, bibliographic references, etc.)
    - Testing: evaluating extraction quality for a subset of cases where I have an ugly/requires-OCR PDF and also the raw text as plain text (this can also help with evaluating how we deal with boilerplate and annotations).
    - This may actually be more (or as much) a chunking issue, but making sure that we're not just only getting meaningful chunks, but that we're only feeding meaningful text into the chunks, and that we're not splitting the text such that we're feeding it in in a non-meaningful way. Some of this is realted to the "dealing with boilerplate" issue and should (maybe?) be handled purely on the ingestion + extraction end (e.g., making sure that we're not providing chunks that are like "meaningful words \[page break + header\] meaningful words" or "meaningful words \[meaningful words but from an unrelated footnote\]", etc.), but some of it could be addressed partly by the chunking process itself (either the chunking algorithm or by specific pre-processing). This is particularly the case because there are probably cases where we want to keep the text (i.e., have it in the extracted markdown doc) but not include it in the chunks for embedding (we might filter out tables, or bibliographic references, reference sections, etc. even though we probably want to keep those in the extracted text). 


- check that we have in fact fulfilled the definition of done for M3b. If so, write a completion report summarizing what was done and detailing how we know it works, including significant detail on the quality extraction tests on the golden test set.
    - make sure that `test_extraction_quality.py` works correctly; we appeared to get all the way through it and then just waited around as though it hadn't completed. unless there's some other issue in its implementation such that it hadn't actually completed (I think). 
    - make sure that `test_metadata_extraction.py` doesn't have to re-extract text from the test PDFs if we either A) already have it in the library (I think); or, B) just extracted it for `test_extraction_quality.py`
        - same goes for the confidence tests.
    - also, are they running multiple times? or does it just print the (apparently complete) summary multiple times while still running?
- Add centralized basic user-facing documentation for all commands and options (as well as making sure our help summaries from the command line are up to date and sufficiently complete). 
- Now that we have metadata provision + extraction, we need ways for the user to review and update that information (i.e., via the command line interface). I'm open to other/additional suggestions, but at a minimum, I think we need: 
    - To change the table displayed by the `list` command to include: id, citekey, status, title (truncated for length), author(s) (truncated for length), hash (possibly other columns, and I'm ambivalent on including the hash or not; really I'm just of the opinion that we *need* the first five of those columns). 
    - To enable `list` to filter by status
    - An `open` command (or similar) to make it easy for the user to actually go look at an item's stored pdf and/or extracted text. 
        - We might want `open` with different flags to do different things (e.g., `open [id] --md` opens markdown) and/or we might want a separate command (maybe `compare`) that would open both the pdf and extracted markdown side-by-side
    - An `update` command (or similar) to allow the user to actually update the extracted metadata.
    - (maybe) A quality of life `review` command that would bundle opening an item's pdf and/or markdown together with the `update` flow. 
    - Update all item retrieval commands (i.e., `show` plus `open`, `update`, `compare`, `review`, if added) to be able to take citekey in addition to or instead of UUID. We might do this via an input convention rather than a pure heuristic or requiring a flag, something like "command assumes it's being passed a UUID unless the passed value starts with `@` (e.g., `show @Smith2017Attention`)". 

1. Launch and external editor with a file to modify. 
2. I think we use the system default for PDFs and (ideally) nvim for markdown (vim would also be acceptable). Side-by-side comparison is a quality of life feature for the moment, so I can be flexible to get it working. That said, I suppose a mild preference for terminal split aesthetically, but that may not be feasible with PDFs/markdown as the side-by-side. Frankly, just markdown in the existing terminal + PDF in new window would be fine, I think. 
3. Terminal constraints: 
    - I tend to use a full width window (240 columns), but we won't want to use the full width; maybe max 200?
    - No particular color preferences, other than that we should use it effectively. 
    - I think we'll want to default to just displaying a maximum number of rows (e.g., 10-15). Pagination might also be effective, I just don't want to ever be taking over a user's terminal in an inconvenient way. 
4. The user should explicitly set status, probably within the same external editor call in which they edit the metadata. (Note that we should, of course, be validating their updates; including to the status field.)
5. It's worth considering whether any changes to underlying storage/models would be warranted, but I think my default is to assume that we are unlikely to do so. And I don't think there are any fields that need to be editable, except (potentially) status, as just mentioned. Additionally, we should make sure to re-index any changed fields from the JSON blob (i.e., we don't want to accidentally have `update` allow the user to change the authors in the CSL-JSON blob, but not see that change reflected in the item's `author` field in the database). 

at some point potentially adding search text of abstract (or search by LLM generated summary if no abstract?)

at some point, get it to handle the entire CSL-JSON spec (and thus the entire blob it will get from Zotero when importing). not that it needs to index any more fields or anything, just that all the info should be there if provided, editable via update, and (maybe) we eventually expand what it is capable of extracting, etc.

get zotero import working ahead of embedding pipeline?


PCC Training questions: 

- sending an updated file: keeps everyone who's already in the file and add new people, right? can we update info as will + will that rerun the matching?
    - they will accept updated info and rerun matching when they get new info. 
    - they basically rerun the file each time (so they'll drop people if we drop the people from the file)
- the IDs in the census tab are the IDs we provided and that's always true of any ID they show us

enabling LLM fallback

looks like there are a number of text normalization functions in `tests/extraction/conftest.py` that I kind of expect should also exist in the ingestion/extraction pipeline itself? like, we should also be normalizing the extracted author names and stuff in actual production, even if we don't have a ground truth to compare to later. so are they duplicating functionality, or not present in the production pipeline, or what?


Generally yes, though I've realized we have an issue: we're currently testing accuracy on three of the most substantively important pieces of metadata (for the user), which is good; however, we're not currently checking document *type*, which is a required field in CSL-JSON and thus required for our schema. That said, it's possible that the appropriate approach for item type is either to 1) have a default/fallback option; or, 2) require that it always be supplied (or selected) by the user at input, rather than extracting it from the document. Given those options, maybe we don't want to change anything now, but what do you think?


I agree with keeping type out of M3b extraction scope, and I think your suggestion of a default generic type with optional user input is a good place to start. Ultimately, having some level of heuristic inference with a flag for review (even, potentially an immediate flag, i.e., the add command has a step where (if the user doesn't provide a type) it heuristically assigns one and then asks the user "this appears to be a journal article/blog post/book/etc. is that right?") would probably be the ideal version, but we should defer for the moment.Note: currently, the metadata handler requires a "type" from the input JSON, which is fine for now, but I want to flag that we may not want to leave type assignment to metadata extraction and have the option (or require) that it be passed in by the user from the start


Just upgraded to Zotero 8, will need to go back and make sure M4 (Zotero import) still works and make changes as necessary. Also make sure BetterBibTex still works. 




What would help complete the picture:

1. Existing patterns: yes, definitely. 
2. Marker output characteristics: 
    - It does tend to do a pretty good job of preserving font size, structure, or other emphasis signals, though this is sometimes via heading levels and sometimes via bold or italics. 
    - It does a pretty decent job at omitting headers and footers (e.g., page numbers, repeated titles, etc.), but sometimes in ways that omit actual text. 
3. Particular concern: 
    - Book sections or essays in collections, where we might have the book title as well as the section or essay title. 
    - Yes, there are a number of scanned and non-English documents (some of which are both) and a limited number of historical texts (though nothing handwritten or pre-1800). All of these could present challenges. 
4. Ideally flagging for manual review.


Oh, do we know for sure/can we confirm LLM providers that will support validated structured output

You seem to have been errored out during implementation. This has happened a couple of times; I don't think it's something with the code per se, but just in case, I want you to investigate the codebase and git history to establish where we are, make a note in @CLAUDE.md so that, in case there's an error, we can look at where this run started and see what progress was made, or if we keep erroring in the same place. Then continue with implementation using the executing-an-implementation-plan skill.

other options for embedding: 

- Qwen3
- BGE
- E5-Mistral

To-Do: 

- more robust testing framework for PDF extraction pipeline (especially Marker extraction) using a selection of actual pdfs from my Zotero library.
    - currently not including any really long docs (anything more than 50/100 pages), but we will need a strategy for dealing with them in actual production. 
    - 20 docs, combination of easy + hard, some non-english, some rotated pages, etc.


## Implementation Layers (Build Order)

1. **Storage layer**: SQLite schema + filesystem layout for documents and notes
2. **Ingestion layer**: Handlers for web URLs (trafilatura) and PDFs (marker/PyMuPDF)
3. **Zotero import**: Read Zotero database, map to internal schema
4. **Note management**: Generate markdown stubs, maintain frontmatter links
5. **Embedding pipeline**: Chunk documents, compute embeddings, store vectors
6. **Auto-tagging**: Nearest-neighbor tag suggestion or LLM classification
7. **RAG interface**: Query interface feeding relevant chunks to LLM
8. **Zotero export**: Push tags back, optional note sync
