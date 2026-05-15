# DECISIONS — log de decisões de design (ADR-style)

> Cada decisão tem o contexto, opções consideradas, escolha, e o **por quê** — pra que daqui
> a 6 meses (ou um colaborador novo) entenda os trade-offs sem ter que reconstruir o raciocínio.
> Decisões saíram de uma sessão de grilling em 2026-05-13.

---

## ADR-001 — Objetivo do repo: quick win shippable

**Contexto:** João tem ~15 projetos AI corporativos privados na Fictor. Quer abrir um repo público
que cristalize esse trabalho. Considerou-se desde "embrião de startup" (HRTech AI / Fiscal AI /
Industrial Compliance OS / AgentOps BR / Industrial Copilot) até "marketing pessoal".

**Decisão:** Quick win shippable em ~3 semanas. Foco em marketing pessoal e portfolio técnico.

**Justificativa:** Apetite de risco e tempo disponível favoreceram escopo menor com ROI rápido.
As ideias de startup ficam documentadas e podem ser retomadas depois.

---

## ADR-002 — Persona primária: recrutador técnico

**Contexto:** Bot precisa otimizar pra UM perfil pra ter tom, conteúdo, idioma coerentes.

**Decisão:** Recrutador técnico (pt-BR + internacional). Secundário: cliente freelance.
Não-usuários V1: outros devs em deep-dive técnico (ficam no GitHub do repo, não no bot).

**Justificativa:** Próximo passo de carreira é o vetor de uso mais provável. Conteúdo do KB já
existe (case studies + LinkedIn posts). Tom profissional é mais fácil de calibrar que comercial.

---

## ADR-003 — Escopo do KB: médio (~25 docs com opinion pieces)

**Contexto:** KB define quanto trabalho de conteúdo. Três níveis discutidos: mínimo (12 docs, 1 sem),
médio (25 docs com opinion pieces, 2-3 sem), máximo (KB dinâmica com crawler, 1-2 meses).

**Decisão:** Médio. CV + ~10 case studies + 5-8 opinion pieces + LinkedIn posts.

**Justificativa:** Opinion pieces são o ÚNICO jeito do bot não soar como "ChatGPT lendo CV".
Reusam como conteúdo de marca no LinkedIn — leverage dupla. Mínimo é commodity demais; máximo
contradiz "quick win".

---

## ADR-004 — Arquitetura: agente com tools (Nível 2)

**Contexto:** Três níveis discutidos: RAG puro / agente com tools / multi-agente com handoff.

**Decisão:** Agente único com 4 tools.

**Justificativa:** RAG puro é commodity (tutorial level). Multi-agente é over-engineering pra
"1 bot de portfolio". Agente com tools é o sweet spot de sinal técnico vs escopo.

---

## ADR-005 — Stack: FastAPI + Next.js split

**Contexto:** Considerado Next.js monolito (mais rápido, sinal "diversifica do CV Python"),
FastAPI + Next.js split (sinal "real backend AI engineer"), Python all-the-way com HTMX (datado).

**Decisão:** FastAPI + Next.js split. Backend e frontend deployados separadamente.

**Justificativa:** Apesar de o monolito ser mais rápido e diversificar mais, o split signaliza
arquitetura real e permite reutilizar o backend pra outras superfícies depois (voice, WhatsApp).
Aceita-se o custo extra de tempo (3-4 sem vs 2 sem).

---

## ADR-006 — Agent stack: PydanticAI + Anthropic Claude

**Contexto:** Opções: LangGraph+Azure (zona de conforto), PydanticAI+Anthropic (moderno),
raw Anthropic SDK (sem framework), LangGraph+Anthropic (meio termo).

**Decisão:** PydanticAI + Anthropic Claude Sonnet 4.6.

**Justificativa:**
1. **Diversifica sinal:** João já tem 5+ repos LangGraph+Azure em produção. Repetir não soma.
   PydanticAI sinaliza "estuda o que vem depois".
2. Anthropic Claude tem melhor pt-BR para esse caso de uso (resposta sobre projetos em português).
3. Forker do repo usa Anthropic API key (mainstream), não precisa de subscription Azure.
4. LangGraph para 1 agente com 4 tools é canhão pra mosca.

**Risco:** PydanticAI ainda pode ter rough edges em streaming tool calls. Mitigação: validar
cedo (D5); fallback raw Anthropic SDK.

---

## ADR-007 — Retrieval: production-grade (hybrid + rerank)

**Contexto:** Três níveis: baseline (dense top-K=5), production-grade (hybrid BM25+dense + rerank),
over-engineered (+ Ragas eval + agentic retrieval).

**Decisão:** Production-grade. pgvector + Postgres FTS (BM25) + Cohere Rerank v3 + chunking semântico.

**Justificativa:** Em uma escala de 25 docs, baseline funciona tecnicamente — mas o SINAL
pra recrutador técnico é o que importa. Recrutador testa com pergunta específica; se errar,
perde respeito. Hybrid + rerank é a diferença entre "tem algo sobre isso" e "essas 3 evidências
exatas". Over-engineered (Ragas) é pretensioso pra escala atual.

---

## ADR-008 — Idioma: KB pt-BR + modelo traduz output

**Contexto:** pt-BR only / en-US only / KB bilíngue / KB pt-BR com tradução pelo modelo.

**Decisão:** KB 100% pt-BR. Claude detecta idioma da pergunta e responde no mesmo.

**Justificativa:** Conteúdo-fonte (LinkedIn posts, READMEs) já em pt-BR. Claude 4.6 traduz
pt-BR corporativo sem perder nuance — custo extra zero. KB bilíngue dobraria esforço de
conteúdo (gargalo real).

---

## ADR-009 — Tools V1: 4 tools, sem Cal.com OAuth

**Contexto:** Decidir set de tools entre 5+ candidatos: search_my_work, compare_to_role,
book_a_call, request_contact, get_resume_pdf, code_sample, share_link, escalate_to_human.

**Decisão:**
1. `search_my_work(query)` — RAG
2. `compare_to_role(jd_text)` — diagnóstico de fit com JD (killer feature)
3. `book_a_call(name, email, time_window, context)` — modo notificação Telegram, não Cal.com real
4. `request_contact(name, role, message, channel)` — fallback de conversão

**Cortado de V1:**
- `get_resume_pdf` — substituído por botão direto no UI (não precisa ser tool)
- `code_sample` — risco NDA com código Fictor
- `share_link` — pode adicionar V2 se alucinar URLs
- `escalate_to_human` — prematuro
- Cal.com OAuth — 2-3 dias de OAuth/webhook hell; notificação manual ganha 80% do valor

**Justificativa:** `compare_to_role` é o mecanismo viral (screenshot-worthy no LinkedIn).
`book_a_call` + `request_contact` são a conversão real (objetivo final = call agendada).
4 tools = ~2 dias de wiring no PydanticAI; cabe no prazo.

---

## ADR-010 — Anti-abuse: Turnstile + rate limit + budget cap

**Contexto:** Bot público com Claude Sonnet 4.6 exposto = risco de bill shock (Reddit em uma noite
pode custar centenas de dólares).

**Decisão:** Defense in depth, sem login:
1. Cloudflare Turnstile invisível no frontend
2. Rate limit por IP: 10 msg / 5min (slowapi + Redis)
3. Daily budget cap absoluto: $5/dia (wrapper Anthropic SDK)
4. Per-IP daily cap: 50 msg/dia

**Justificativa:** LinkedIn OAuth obrigatório foi descartado por atrito + app approval lento.
Turnstile resolve 95% do abuse com zero atrito pra humano. Budget cap é a última linha de defesa.

---

## ADR-011 — Observabilidade UI: citations + tool calls + trace escondido

**Contexto:** Quanto do internals expor pro usuário? Hidden / Citations / Citations+Tools /
Full trace sempre visível.

**Decisão:** Citations clicáveis + tool calls visíveis inline durante streaming + botão
"Ver trace técnico" que abre modal com chunks/scores/tokens/custo.

**Justificativa:**
1. **Tool calls visíveis = sinal viral.** "🔧 comparando com a vaga..." é screenshot-worthy.
2. Citations é hygiene mínima — sem isso parece tutorial.
3. Trace completo atrás de botão = sinal técnico máximo pra quem quer, sem poluir UX dos 95%
   de visitantes que não querem ver tokens/bytes.
4. Vercel AI SDK suporta streaming de tool calls nativamente — implementação ~grátis.

---

## ADR-012 — Hosting backend: Fly.io free always-on

**Contexto:** Backend FastAPI precisa de host. Opções: Fly.io free, Railway ($5/mo), Azure
Container Apps, Render free (sleeps).

**Decisão:** Fly.io free tier (3 VMs always-on).

**Justificativa:**
1. **Cold start mata UX:** Render free com sleep = primeira mensagem de recrutador depois de
   ociosidade demora 45s. Bot perdido.
2. Free tier perpétuo: você não vai pagar pra manter o portfolio vivo daqui a 2 anos.
3. Diversifica do Azure (overfit do CV).
4. "Deploy to Fly" button no README = forker tem cópia rodando em 5min.

---

## ADR-013 — Sessão: cookie + Redis 24h + analytics anônimo

**Contexto:** Stateless / cookie+Redis / login obrigatório / só log.

**Decisão:** httpOnly cookie + mensagens em Redis com TTL 24h + cópia anonimizada (PII redacted)
em Postgres pra analytics.

**Justificativa:**
1. Recrutador refresh página ou volta amanhã = continua de onde parou (24h é janela razoável).
2. Analytics anônimo é underrated: você descobre quais perguntas mais aparecem e itera o KB.
3. PII redaction antes do log = hygiene LGPD básica. Reusar lógica do projeto pesquisa-clima.
4. IP hashed (não cru) + disclaimer no UI.

---

## ADR-014 — Launch: soft, sem Hacker News

**Contexto:** Como anunciar o V1: soft launch (LinkedIn + rede), Show HN, stealth, série de
posts técnicos.

**Decisão:** Soft launch. Repo público + post LinkedIn com GIF demo + DM pra ~15 pessoas-chave.

**Justificativa:** Show HN tem risco real de queimar budget cap em 1h e perder a janela. Stealth
é desperdício de esforço. Série de posts técnicos é interessante mas exige cadência que pode
não acontecer. Soft launch via rede é o mais previsível.

---

## Decisões deixadas em aberto (a resolver durante implementação)

- **Nome do produto/domínio:** `ask-about-me` é o nome do repo. Domínio público pode ser
  `askjoao.dev`, `joao.bot`, `joao.ai`, etc. Decidir antes de D14.
- **Modelo de embedding exato:** OpenAI `text-embedding-3-small` é default; considerar Voyage AI
  pra ver se entrega melhor pt-BR retrieval.
- **Hard top-K e thresholds do reranker:** ajustar empiricamente em D6-7.
- **Telegram bot token:** criar dedicado pra esse projeto (não reusar pessoal).
- **Onde guardar secrets:** Fly secrets (back) + Vercel env vars (front). 1Password como backup.
