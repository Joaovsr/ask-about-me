# ask-about-me

Sistema de conteúdo e RAG do portfólio do João. Responde perguntas sobre sua trajetória técnica com evidências recuperadas de material publicado e citações visíveis.

**Status:** base local e primeiro walking skeleton da pipeline RAG disponíveis.

## V1

- Chat real embutido no [portfólio Vue existente](https://github.com/joaovsr/joaovsr.github.io).
- Perguntas livres e prompts sugeridos passam pelo mesmo fluxo de retrieval e geração.
- Respostas completas com cards de citação e declaração explícita de evidência insuficiente.
- Conteúdo público bilíngue gerenciado por um painel privado.
- Postgres como fonte de verdade do portfólio e da Knowledge Base.
- Indexação automática e consistente a cada publicação.
- Conversa efêmera mantida apenas no navegador.

## Arquitetura

- **Frontend público:** Vue 3, Vite e TypeScript no repositório do portfólio.
- **Backend:** FastAPI com fluxo retrieve-then-generate explícito, sem framework de agente.
- **Dados:** Postgres e pgvector.
- **Avaliação e observabilidade:** Golden Dataset versionado e Langfuse.
- **Infraestrutura:** portfólio, backend e banco no mesmo droplet da DigitalOcean.
- **Modelos:** OpenAI como provedor inicial; modelos e parâmetros são validados com conteúdo real.

O backend concentra três módulos: Conteúdo publicado, Knowledge Base e RAG de Portfólio. O frontend público, o painel admin e os handlers HTTP são adapters dessas interfaces.

## Desenvolvimento Local

Pré-requisitos: Docker Desktop e Python 3.12 ou superior.

```bash
make setup
make db-up
make migrate
make seed-dev
make dev
```

O Postgres de desenvolvimento fica restrito a `127.0.0.1:5432`, com pgvector habilitado por migration. Os testes criam um container efêmero separado em `127.0.0.1:5433`. A API roda em `http://127.0.0.1:8000` e expõe:

- `GET /health/live`: processo FastAPI disponível.
- `GET /health/ready`: processo e Postgres disponíveis.
- `GET /case-studies/{slug}?locale=pt-BR|en-US`: conteúdo público localizado do
  Case Study atual, incluindo sua revisão.
- `GET /portfolio?locale=pt-BR|en-US`: snapshot público localizado de perfil,
  experiências e projetos para o portfólio Vue.
- `POST /ask`: pipeline retrieve-then-generate completa. Com
  `AAM_OPENAI_API_KEY` configurada, a aplicação compõe automaticamente retrieval,
  embeddings e geração; sem a chave, responde `503` de forma explícita.
- `POST /admin/session`, `GET /admin/csrf` e `/admin/case-studies`: primeiro
  adapter do Painel admin. Configure `AAM_ADMIN_PASSWORD` e um
  `AAM_ADMIN_SESSION_SECRET` longo para habilitá-lo. A sessão é HTTP-only e as
  mutações exigem o token CSRF retornado por `/admin/csrf`. A publicação também
  requer `AAM_OPENAI_API_KEY`; sem ela, login continua disponível, mas a API de
  conteúdo responde que a publicação está indisponível.

A Knowledge Base recebe KB Docs projetados, divide suas seções em chunks e gera embeddings
por uma interface substituível. A reindexação grava uma geração candidata inativa, verifica
o retrieval nela e só então troca o ponteiro ativo em uma transação. Se a preparação ou a
verificação falhar, a geração anterior continua pesquisável. A busca `search_my_work`
combina pgvector e full-text search em português por Reciprocal Rank Fusion. Geração e
embeddings ficam atrás de interfaces estreitas para permitir o spike de provedor sem
alterar os módulos de Knowledge Base e RAG de Portfólio.

O seed versionado inclui um Case Study da plataforma de gestão de pessoas com IA e o
snapshot inicial de perfil, experiências e projetos do portfólio. A
revisão mantém campos explícitos em `pt-BR` e `en-US`; sua projeção determinística usa
o `pt-BR` como texto canônico do KB. A publicação prepara os
embeddings antes e confirma revisão, ponteiro público e geração do índice na mesma
transação, evitando conteúdo publicado sem evidência pesquisável. A nova geração substitui
somente as origens alteradas e preserva os demais KB Docs ativos, independentemente do
`doc_type`.

`make seed-dev` é idempotente e usa embeddings hash locais apenas para desenvolvimento.
Eles não substituem a avaliação nem os modelos do provedor de produção; ao configurar o
provedor escolhido, o conteúdo deve ser reindexado antes de servir tráfego.

Para usar a pipeline real da OpenAI, copie as configurações de `.env.example`, preencha
`AAM_OPENAI_API_KEY` somente no `.env` ignorado pelo Git, reindexe o conteúdo e inicie a
API:

```bash
make reindex-openai
make dev
```

O primeiro corte do Painel admin permite publicar Case Studies bilíngues. A publicação
usa a mesma transação de conteúdo e indexação: se a geração de embeddings ou a verificação
do índice falhar, a revisão pública anterior permanece ativa. Em desenvolvimento, mantenha
`AAM_ADMIN_COOKIE_SECURE=false`; o padrão da aplicação é `true` para exigir cookie
de sessão seguro em produção HTTPS.

O adapter usa `text-embedding-3-small` com 1.536 dimensões por padrão e envia os chunks em
lotes. O chunker preserva os limites das seções, prefere fronteiras de parágrafo e frase e
usa inicialmente alvo de 350 tokens, máximo de 500 e overlap de até 50 tokens. Cada geração
do índice registra provider, modelo, dimensões e versão do chunker; uma configuração
incompatível exige reindexação em vez de misturar vetores.

A geração usa a Responses API com Structured Outputs e `gpt-5.6-sol` por padrão. O modelo
recebe apenas a pergunta, o histórico efêmero e os chunks recuperados como dados não
confiáveis. Ele devolve claims atômicas tipadas e IDs de chunks; o servidor valida
autoridade, citações e se todos os tipos solicitados pela pergunta foram atendidos, tenta
uma correção estruturada quando necessário e hidrata os metadados finais. As respostas não
são armazenadas pela OpenAI via `store`, e timeout, retries, modelo e limite de saída podem
ser ajustados pelas variáveis `AAM_OPENAI_*` e `AAM_GENERATION_*` do `.env.example`.

Para executar todos os checks locais:

```bash
make check
```

`make db-down` encerra os containers preservando os dados. `make db-reset` também remove o volume local.

## Evidência

- Case Studies sustentam experiência prática.
- Profile Docs sustentam claims auto-declarados com menor força factual.
- Essays sustentam opiniões técnicas, não entregas realizadas.
- Toda afirmação factual substantiva precisa de citação.
- Sem evidência suficiente, o sistema responde parcialmente ou declara a limitação.

## Documentação

- [CONTEXT.md](CONTEXT.md): linguagem canônica do domínio.
- [docs/SPEC.md](docs/SPEC.md): especificação vigente do V1.
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): arquitetura implementada e seus limites atuais.
- [docs/DEVELOPMENT_PLAN.md](docs/DEVELOPMENT_PLAN.md): plano de execução em fatias verticais.
- [docs/adr/](docs/adr/): decisões arquiteturais e seus trade-offs.

## Fora Do V1

- Comparação estruturada com vagas e `compare_to_role`.
- Booking, captura de contatos e integrações de calendário.
- Streaming de tokens e tool calls visíveis.
- Sessões ou analytics persistentes de conversas.
- Voice, multiagente e crawler automático do GitHub.

## License

MIT.
