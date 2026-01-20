
# Record Level Flow

Prototyping design of the record level flow; i.e., what happens when you call the program to add an item to the library. 

- call to create a document record. passed either a bare content locator (URL/path) or a content locator with metadata (taken from Zotero). 
- time stamped record (with UUID) is created with any provided metadata filled in. 
    - (we also record the passed URL/path in order to allow duplicate checking later? or maybe we get a file hash for the raw content?)
- the raw content downloaded/copied (not sure whether we're copying, aliasing, or what PDFs from Zotero) and the path to it is added to the record
- the raw content is parsed to markdown which is saved. either in the database or as a separate file (either alongside or separate from the raw content)
- extract metadata from raw/parsed content as necessary. figure there are two ways to condition this: 1) do it only if no metadata was provided as input, 2) do it only if any of the key metadata is missing (key values to be defined, but likely include title, author, pub date). The first avoids attempting to add metadata to Zotero records (which I generally will not want to do), while the second allows for the provision of partial metadata in non-Zotero cases, which could be a useful feature. 


## Interface w/ Zotero

Zotero import functions by opening a connection to the Zotero database and iterating over all items not already in our database. For each one, it checks whether there's an attachment. If so, it calls the "new record flow", passing the path to the attachment and the Zotero CSL-JSON record. 


## Different kinds of documents

Thinking in terms of objects/interfaces: every object is a document, documents are all the same (in terms of what their component parts are, etc.), but one of their "attributes" is always a "raw content" object, but that raw content object is just an interface into "raw content html", "raw content pdf", "raw content epub", etc., or something


## Duplicate Checking

- could check at multiple points. some subset of: on attempted record creation (the passed URL/path), on raw content download (using file hash), on metadata extraction/entry (using the metadata), on chunking and embedding (using vector similarity), any others?
    - and the various points could have different levels of strictness to the criteria and/or different default behaviors; e.g., passing a URL that's already in the database gets you a "not doing that, it's a duplicate, would you like to open the connected note or edit the metadata?", but sufficiently high vector similarity gets you "hey, this is extremely similar to document X; are you sure it's not a duplicate?"



