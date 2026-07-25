# Publish content and its index together

An admin save becomes visible only after the affected KB projection, chunks, and embeddings are ready to be committed with the content change. If validation or indexing fails, the save fails and the previous published version remains active; this favors portfolio/KB consistency over faster asynchronous publishing in V1.
