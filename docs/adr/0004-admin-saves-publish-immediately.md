# Admin saves publish immediately

V1 will not model drafts, reviews, or scheduled publishing. Saving content in the admin UI starts one synchronous publication operation and only updates the published portfolio after the affected RAG index is ready, as refined by ADR 0007. This keeps the content system small and matches a single-owner portfolio, while accepting slower saves and requiring complete edits because there is no unpublished draft state.
