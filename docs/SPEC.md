# SPEC — ask-about-me V1

> Documento de especificação técnica do V1. Derivado de uma sessão de grilling com Claude
> (skill `grill-me`) em 2026-05-13.

---

## 1. Objetivo e usuário-alvo

**Objetivo:** quick win shippable em ~3 semanas. Bot público que demonstra padrões técnicos
modernos (PydanticAI, hybrid retrieval, agent com tools, observability) usando como vetor
a experiência real de quem construiu agentes IA em produção numa empresa tradicional brasileira.

**Usuário primário:** Recrutador técnico (BR + internacional).

**Usuário secundário:** Cliente freelance/consultoria potencial.

**Não-usuários (V1):** Devs curiosos buscando deep-dive técnico (ficam no GitHub README do repo,
não interagem com o bot); o próprio João como "segundo cérebro" (separado).

## 2. Base de conhecimento (KB)

**Escopo:** ~25 documentos curados em pt-BR.

**Composição:**
- 1 CV.md
- ~10 case-studies dos projetos (1 por projeto da Fictor, anonimizados onde NDA exigir)
- 5-8 opinion pieces técnicas (ver §11)
- 3-5 LinkedIn posts (reaproveitar `gestao-pessoas/linkedin-*.md`)
- 1 skills-matrix.md

**Constraint LGPD/NDA:** zero código-fonte da Fictor. Descrições de alto nível, decisões de arquitetura,
patterns reusáveis — sim. Snippets proprietários — não.

**Pipeline de ingestão:**
1. Markdown em `data/kb/*.md`
2. Chunking semântico (não fixed-size dumb) — ver §6
3. Embeddings via OpenAI `text-embedding-3-small` ou Voyage AI
4. Upload pra pgvector
5. Reindex via comando `make reindex` (idempotente)

## 3. Arquitetura

**Nível 2: agente com tools** (não multi-agente; não RAG puro).

```
┌──────────────────┐         ┌──────────────────────────┐
│  Next.js 15      │ ──HTTP─▶│  FastAPI                 │
│  (Vercel)        │ ◀─SSE──│  ├─ /chat (streaming)    │
│  Vercel AI SDK   │         │  ├─ /admin (basic auth)  │
└──────────────────┘         │  └─ /health              │
                             │                          │
                             │  PydanticAI Agent        │
                             │  ├─ search_my_work       │
                             │  ├─ compare_to_role      │
                             │  ├─ book_a_call          │
                             │  └─ request_contact      │
                             └──┬──────┬──────┬─────────┘
                                │      │      │
                       ┌────────▼┐ ┌───▼───┐ ┌▼────────┐
                       │ pgvector│ │ Redis │ │ Postgres│
                       │(Supabase)│ │Upstash│ │(Supabase)│
                       └─────────┘ └───────┘ └─────────┘
                                │
                                ▼
                         ┌──────────────┐
                         │ Anthropic    │
                         │ Claude 4.6   │
                         │ + Cohere     │
                         │   Rerank     │
                         └──────────────┘
```

## 4. Stack

| Camada | Tecnologia | Por quê |
|---|---|---|
| LLM | Anthropic Claude Sonnet 4.6 | Melhor pt-BR; tool_use API limpa; diversifica vs Azure |
| Agent framework | PydanticAI | Typed, moderno; sinal de "estuda o que vem depois" |
| Embeddings | OpenAI `text-embedding-3-small` | Custo baixo, qualidade comprovada |
| Reranker | Cohere Rerank v3 (free tier) | Baseline production-grade |
| Vector DB | pgvector (Supabase free) | Postgres familiar + FTS no mesmo DB |
| Backend | FastAPI | Python + ecossistema PydanticAI |
| Frontend | Next.js 15 App Router + Vercel AI SDK | Streaming nativo, deploy free, diversifica do CV |
| Backend host | Fly.io free always-on | Sem cold start, edge global, sem lock Azure |
| Frontend host | Vercel | Padrão Next.js |
| Session store | Upstash Redis (free) | Serverless, REST, free tier perpétuo |
| Auth admin | Basic Auth | João é o único admin |
| Anti-bot | Cloudflare Turnstile | Captcha invisível |

## 5. Tools do agente

### 5.1 `search_my_work(query: str, top_k: int = 5)`
RAG sobre o KB. Retorna `list[Chunk]` com `text`, `source_doc`, `score`. Usado em quase toda resposta.

### 5.2 `compare_to_role(jd_text: str)` ⭐
**Killer feature.** Recrutador cola a JD da vaga. Pipeline:
1. Claude extrai requirements estruturados (Pydantic schema forçado).
2. Pra cada requirement, faz RAG no KB.
3. Classifica cada requirement: ✅ atende (com evidências), ⚠️ parcial, ❌ gap.
4. Retorna `FitAnalysis` com fit_score (0-100), strengths, gaps, suggested_interview_questions[].

**Risco:** alucinação. Mitigação: few-shot examples + saída estruturada + cada requirement
ancorado em evidência citada do KB (sem evidência = ⚠️ ou ❌, nunca ✅).

### 5.3 `book_a_call(name: str, email: str, time_window: str, context: str)`
V1 modo notificação simples:
- Validação básica (email format, não vazio)
- Envia Telegram pro João via bot token + chat_id
- Persiste em Postgres tabela `bookings`
- Retorna confirmação com mensagem "te respondo em 24h"

**V2:** Cal.com OAuth real.

### 5.4 `request_contact(name: str, role: str, message: str, channel: str)`
Fallback de conversão pra quem não quer marcar call. Mesma pipeline que `book_a_call`,
status diferente. Telegram + Postgres.

## 6. Retrieval (production-grade)

**Chunking:**
- Markdown-aware: split por `##` headings primeiro
- Chunks alvo: 400-800 tokens
- Overlap: 50 tokens
- Preserve metadata: `source_doc`, `section`, `tags`

**Indexing:**
- Embedding por chunk: `text-embedding-3-small` (1536 dim)
- Também guardar texto raw em `content` (pra BM25/FTS)
- Postgres FTS index em `content` com config `portuguese`

**Query time:**
1. **Dense**: `query embedding ⟷ chunks` via pgvector cosine, top-K=20
2. **Sparse**: Postgres FTS `to_tsquery('portuguese', query)`, top-K=20
3. **Merge**: união, dedup por chunk_id
4. **Rerank**: Cohere Rerank v3 com query + chunks → top-5
5. **Stuff** os top-5 no prompt do agente

**Por que não Ragas/eval suite:** escala de 25 docs não justifica. V2 se a base crescer.

## 7. Idioma

**Estratégia:** KB 100% pt-BR. Claude detecta idioma da pergunta no system prompt e responde
no mesmo idioma do user. Citações ficam em pt-BR (idioma da fonte) com tradução inline se a
conversa for em inglês.

**Justificativa:** Claude 4.6 traduz pt-BR corporativo sem perder nuance técnica. Custo extra zero.

## 8. UI/Observabilidade

**Stack visual:** Next.js + Tailwind + shadcn/ui + Vercel AI SDK (streaming).

**Elementos visíveis:**

1. **Citations inline:** cada afirmação fatual com footnote `[1]` clicável. Footnote expande popup
   com `source_doc`, trecho destacado, link pra doc completo.
2. **Tool calls durante streaming:**
   - `🔧 buscando em projetos sobre RAG...` (search_my_work)
   - `🎯 comparando com a vaga...` (compare_to_role)
   - `📅 registrando interesse em call...` (book_a_call)
   - `✉️ encaminhando contato...` (request_contact)
3. **Botão "Ver trace técnico":** abre modal com:
   - Chunks recuperados (texto + score)
   - Tool calls + args + responses (JSON)
   - Tokens used + custo USD aproximado
   - Tempo de cada step

**Disclaimer fixo no rodapé:**
> Conversas são armazenadas anonimamente (com redação de PII) para análise.
> [Política de privacidade]

## 9. Anti-abuse + custo

**Camadas (defense in depth):**

1. **Cloudflare Turnstile invisible** no frontend antes do POST `/chat`. Token validado no backend.
2. **Rate limit por IP**: 10 mensagens / 5min (slowapi + Redis backend).
3. **Daily budget cap absoluto**: wrapper em torno do Anthropic SDK. Lê `spent_today_usd`
   do Redis; se passar de $5/dia, dispara `HTTPException(429, "daily budget exhausted")`.
4. **Per-IP daily message cap**: 50 mensagens/dia/IP (paranoid mode).

**Métricas Redis:**
- `budget:YYYY-MM-DD` → cents spent today (TTL 48h)
- `rate:ip:{ip}:5min` → counter (TTL 5min)
- `daily:ip:{ip}:YYYY-MM-DD` → counter (TTL 48h)

## 10. Sessão + analytics

**Sessão:**
- httpOnly cookie `aam_sid` (random UUID, TTL 24h)
- Mensagens da sessão em Redis: `session:{sid}` → JSON array (TTL 24h)
- Refresh dentro de 24h mantém contexto

**Analytics:**
- Tabela Postgres `conversations` (anonymized): id, started_at, ended_at, message_count, ip_hash
- Tabela `messages`: conversation_id, role, content, tools_called, citations, created_at
- **PII redaction antes do insert**: regex pra emails, telefones BR, CPF, CNPJ + Claude redactor pra free-form. Reusar lógica do projeto `pesquisa-clima`.
- IP hash = SHA-256(IP + salt secret), não IP cru

**`/admin` route:**
- Basic Auth (env var)
- Queries SQL pré-definidas:
  - Top 20 perguntas dessa semana
  - Tools mais usadas
  - Conversões (bookings + contacts)
  - Custo diário
- ~20 linhas FastAPI + 1 template Jinja

## 11. Opinion pieces (o gargalo real)

Os 5-8 opinion pieces são o asset mais valioso e o que mais facilmente vira meia-boca. Cada um
deve ter ~1500 palavras, opinião forte, exemplo concreto da Fictor (anonimizado), e DEVE virar
post no LinkedIn separadamente.

**Lista sugerida (alinhada à experiência real):**

1. **"5 erros que cometi construindo RAG em pt-BR pra empresa tradicional brasileira"**
   — chunking ingênuo, embeddings que não entendem jargão fiscal, retrieval sem rerank, etc.
2. **"Embeddings de transcrições do Microsoft Teams: o que aprendi avaliando comportamento de funcionários com IA"**
   — case real do projeto gestao-pessoas, viés ético, sinal vs ruído.
3. **"PII masking em pt-BR: o que LGPD exige e os tutoriais americanos não te contam"**
   — case do pesquisa-clima, CPF/CNPJ/RG, regex vs LLM redactor.
4. **"Construindo agentes que falam com ERP brasileiro via MCP: a saga TOTVS/Protheus"**
   — case anonimizado do projeto cobrança.
5. **"Multi-agente é over-engineering 9 em 10 vezes — quando vale e quando não vale"**
   — opinião contrarian, exemplos de quando você usou e quando NÃO usou.
6. **"Azure OpenAI vs Anthropic vs OpenAI em produção: 6 meses depois"**
   — comparação honesta, latência, qualidade pt-BR, custo, lock-in.
7. **"Pesquisa de clima com IA: por que classificação supervisionada perdeu pra zero-shot LLM"**
   — case do pesquisa-clima.
8. **"Voz em pt-BR pra agente de call center: o que ninguém te conta sobre Twilio + Azure Realtime"**
   — case do callcenter, latência percebida, jitter, transcrição.

**Tempo realista:** 3-4h por peça → 24-32h total de escrita. Espalhar pelas 3 semanas.

## 12. Cronograma (3 semanas)

| Dia | Tarefa |
|---|---|
| D1-2 | Escrever KB inicial (CV + ~10 case-studies + 3 opinion pieces dos 8 — resto vem ao longo do projeto) |
| D3 | Pipeline ingestão (chunking, embeddings, upload pgvector) |
| D4 | FastAPI base (/chat, /admin, /health) + Supabase + Upstash setup |
| D5 | PydanticAI agent + 4 tools com mock |
| D6-7 | Hybrid search + Cohere Rerank + medir qualidade subjetiva |
| D8 | Tools reais: `compare_to_role` (prompt engineering pesado) + `book_a_call` (Telegram) + `request_contact` |
| D9 | Next.js + Vercel AI SDK + UI básica |
| D10 | Streaming com citations + tool calls visíveis |
| D11 | Turnstile + slowapi + budget cap wrapper |
| D12 | Cookie+Redis session + PII redaction + log Postgres |
| D13 | /admin dashboard básico |
| D14 | Deploy: `fly deploy` + Vercel + DNS (askjoao.dev ou similar) |
| D15 | README polish: Deploy-buttons + GIF demo + screenshots |
| D16 | Soft launch: post LinkedIn com `compare_to_role` em ação |
| D17-21 | Buffer / restantes opinion pieces / itera baseado em primeiros usos |

## 13. Riscos e mitigações

| Risco | Probabilidade | Mitigação |
|---|---|---|
| PydanticAI rough edge em streaming tool calls | Média | Validar em D5; fallback = Anthropic SDK direto |
| `compare_to_role` alucina sobre fit | Alta | Few-shot examples + saída estruturada + ancoragem obrigatória em chunks citados |
| Opinion pieces não saem | Alta | Lançar com 3 prontos; resto na vibe, sem bloquear V1 |
| Cohere free tier estoura | Baixa | Fallback bge-reranker local (CPU) |
| Bill shock por bug | Baixa | Budget cap absoluto faz hard stop em $5/dia |
| Cold start mata UX | Baixa | Fly free always-on resolve |
| Crawler hostil dos modelos abertos | Média | robots.txt + Turnstile + rate limit |

## 14. Escopo cortado de V1 (vai pra V2)

- Voice (Twilio + Anthropic Realtime)
- Cal.com OAuth real
- LinkedIn OAuth opcional
- Multi-agente com handoff visível
- Crawler dinâmico do GitHub público
- Tools: `get_resume_pdf` (substituído por botão direto no UI), `code_sample`, `share_link`, `escalate_to_human`
- Ragas eval suite
- A/B test de prompts
- i18n manual (currently via Claude)

## 15. Launch (soft)

**Estratégia escolhida:** soft launch + post LinkedIn. Sem Hacker News (risco de queimar budget).

**Sequência D16:**
1. Repo público no GitHub (`joaovsr/ask-about-me` ou similar)
2. Domínio `askjoao.dev` (ou similar) apontando pra Vercel
3. Botão "Chat com meu agente IA" no `joaovsr.github.io`
4. Post LinkedIn com GIF mostrando `compare_to_role` rodando + link
5. Mensagem direta pra 10-15 pessoas-chave da rede com link

**Métrica de sucesso V1 (4 semanas pós-launch):**
- ≥ 50 conversas de pessoas reais (não você testando)
- ≥ 5 `book_a_call` ou `request_contact` reais
- ≥ 1 conversa que vire entrevista real
