# Welcome to your Local Library!

My aim is to develop the infrastructure for a kind of personal knowledge library. The end goal is to be able to take any digital document, save the content, record some kind of bibliographic metadata, process the content into a local RAG database, use that to auto-generate tags in relation to everything else in the library, and automatically create a linked markdown note where I can put down any notes or commentary (and which will likely include an LLM generated summary as well). 

In some ways this is replicating functionality from [Zotero](https://www.zotero.org), which I use extensively for my academic research work. However, it expands on that significantly in three ways:

1. The addition of content extraction (e.g., OCR and parsing of PDFs, extraction of content from web articles, eventually the extraction and formatting of content from social media or video).
2. Leveraging that extracted content using deep learning/LLMs via auto-tagging and the creation of a query-able RAG.
3. Improved transparency to other applications, in particular via shifting notes out of the SQL database and into the filesystem as markdown docs.
4. Substantially improved handling of web content (e.g., blog posts, articles, etc.).

The goal is easy and fluid *interoperability* with Zotero (and, ultimately, other applications) even as we maintain and develop expanded capabilities. 

# Development

This project is also an experiment in working with [Claude Code](https://code.claude.com/docs) and building up complete, complex, and effective workflows. The original brainstorming conversation happened directly with Claude and is recorded verbatim in `background/chat_transcript.md` and summarized in `background/chat_summary.md`.
