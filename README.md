# ask-about-me

> Um agente IA que conhece minha trajetória técnica e responde, com citações, perguntas de recrutadores e clientes potenciais.

**Status:** 🟡 em planejamento (V1 spec definido, código ainda não iniciado)

---

## O que é

Bot conversacional que vive no meu portfolio e responde perguntas sobre minha experiência técnica — mas com três diferenciais que separam de qualquer "RAG bot tutorial":

1. **`compare_to_role`**: recrutador cola a JD da vaga e o agente devolve um diagnóstico estruturado de fit, com evidências citadas dos meus projetos e 3 perguntas sugeridas pra entrevista.
2. **Tool calls visíveis durante streaming**: você vê o agente pensando (`🔧 buscando experiência em RAG corporativo...`).
3. **Conversão real**: tools `book_a_call` e `request_contact` transformam visita em conversa marcada, não em "tchau".

## Stack

- **Backend**: FastAPI + [PydanticAI](https://ai.pydantic.dev/) + Anthropic Claude Sonnet 4.6
- **Frontend**: Next.js 15 (App Router) + Vercel AI SDK
- **Retrieval**: pgvector (Supabase) + hybrid search (BM25 + dense) + Cohere Rerank
- **Infra**: Fly.io (backend) + Vercel (frontend) + Upstash Redis + Supabase Postgres
- **Anti-abuse**: Cloudflare Turnstile + rate limit + daily budget cap
- **Custo perpétuo**: ~$0/mês (free tiers + Claude pay-per-use limitado)

## Por que isso existe

Construí ~15 sistemas de IA em produção em empresa tradicional brasileira (cobrança, voice agents, RH, supply, governança, big data). Quase tudo privado por NDA.

Este repo é a **versão pública e auditável** do que aprendi montando agentes corporativos em pt-BR. O código aqui demonstra os padrões que repeti N vezes em ambiente fechado.

## Documentação

- [docs/SPEC.md](docs/SPEC.md) — Especificação técnica completa do V1
- [docs/DECISIONS.md](docs/DECISIONS.md) — Log das decisões de design e por quê (ADR-style)

## Roadmap

**V1 (3 semanas)** — escopo deste repo:
- 4 tools (`search_my_work`, `compare_to_role`, `book_a_call`, `request_contact`)
- Production-grade retrieval
- pt-BR + tradução por modelo
- Citations + tool calls visíveis

**V2 (depois de tração)**:
- Cal.com OAuth real
- LinkedIn OAuth opcional ("premium feel")
- Voice via Anthropic Realtime
- GitHub crawler automático
- Tools adicionais: `share_link`, `code_sample`

## License

MIT.
