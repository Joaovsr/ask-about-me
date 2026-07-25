# Published content is the source of truth

The portfolio will evolve from static files edited by commits into a small content system. Published content stored in Postgres will be the source of truth for both the public portfolio and the RAG knowledge base; edits made through an admin UI should update the public site and trigger indexing into chunks and embeddings. This avoids maintaining one copy of the same facts for the portfolio and another for RAG, at the cost of building content management, publishing, indexing, and operational safeguards.
