# Preserve the Vue portfolio and a separate backend

The existing `joaovsr.github.io` Vue/Vite application remains the public portfolio instead of being rewritten in Next.js or moved into this repository. `ask-about-me` will own the FastAPI backend, content management, indexing, and RAG modules; both repositories will be deployed behind the same origin on the DigitalOcean droplet, preserving the current visual investment while keeping content and RAG responsibilities together.
