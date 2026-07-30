# Plano de desenvolvimento: retrieval e gate de suporte

Este plano refina a **Fatia 6: qualidade de retrieval** do
[`DEVELOPMENT_PLAN.md`](DEVELOPMENT_PLAN.md) a partir da auditoria registrada em
[`research/portfolio-rag-retrieval-strategy.md`](research/portfolio-rag-retrieval-strategy.md).

O objetivo é fazer o RAG de Portfólio aceitar perguntas sustentadas pelo KB, inclusive
nomes de produtos publicados, e recusar perguntas sem evidência sem depender de uma lista
manual de palavras permitidas.

## Resultado esperado

Ao final:

- toda pergunta válida executa retrieval antes da decisão de geração;
- o sistema distingue **ordenação** de **suporte**;
- RRF continua disponível para ordenar candidatos, mas nunca é tratado como confiança;
- o canal lexical considera título, seção e corpo;
- o inspector explica por que cada chunk foi recuperado;
- o gate de suporte usa sinais brutos calibrados no Golden Dataset;
- mudanças de chunker, embedding ou reranker só entram após comparação reproduzível;
- perguntas sem suporte não chegam ao gerador;
- follow-ups não herdam evidência indevida de um assunto anterior.

## Fora de escopo

- substituir Postgres/pgvector por um vector database externo;
- migrar a orquestração explícita para um framework de agentes;
- criar um índice bilíngue antes de medir o índice canônico em `pt-BR`;
- adotar semantic chunking, `text-embedding-3-large` ou reranker por intuição;
- usar o modelo gerador como classificador obrigatório em toda pergunta;
- alterar a matriz de autoridade entre Case Study, Profile Doc e Essay.

## Arquitetura alvo

```text
pergunta + histórico
        |
        v
validação de payload
        |
        v
consulta autônoma de retrieval
        |
        v
candidatos densos + lexicais
        |
        v
sinais brutos + RRF
        |
        v
gate de suporte calibrado
    |                 |
    | sem suporte     | com suporte
    v                 v
insufficient      seleção de contexto
                      |
                      v
                   geração
                      |
                      v
            validação de claims/citações
```

O gate anterior por palavras-chave deixa de bloquear o fluxo. Classificar uma pergunta
como claramente fora do tema pode continuar existindo para escolher uma mensagem de
limitação, mas não pode ser a fonte de verdade sobre a existência de evidência.

## Decisões de desenho

### Um score não representa todos os sinais

Cada resultado recuperado deve preservar:

- distância e similaridade de cosseno;
- posição no ranking vetorial;
- existência e valor do match textual;
- posição no ranking textual;
- match em título e seção;
- score RRF;
- score de reranker, somente se esse estágio for adotado;
- geração e perfil do índice usados.

Esses campos formam uma explicação do retrieval. Nenhum deles é uma probabilidade por
definição.

### O gate avalia suporte, não autoridade

O gate responde apenas se existe evidência relevante o suficiente para justificar
geração. A validação posterior continua decidindo se um chunk possui autoridade para
sustentar um claim `experience`, `profile` ou `opinion`.

`doc_type` não deve aumentar artificialmente a relevância de um chunk.

### O Golden Dataset usa identidades estáveis

IDs de chunks mudam após reindexação. As expectativas devem apontar para:

- `source_id` ou slug estável;
- seção semântica esperada;
- grau de relevância;
- tipos de claim e estado esperado.

O evaluator resolve essas expectativas contra a geração avaliada.

### O índice lexical é materializado na indexação

O título pertence a `kb_documents`, enquanto o chunk e seu `search_vector` pertencem a
`kb_chunks`. Como uma coluna gerada não pode depender de outra tabela, a alternativa
preferida é materializar um `tsvector` imutável durante a escrita da geração:

- título com peso `A`;
- seção com peso `B`;
- aliases publicados com peso `B`, quando existirem;
- conteúdo com peso `D`.

Como documentos e chunks de uma geração são imutáveis, não existe risco de o vetor
textual ficar dessincronizado dentro da geração.

## Gate de qualidade

As metas abaixo são critérios iniciais de lançamento e podem ser endurecidas quando o
dataset crescer:

| Dimensão | Critério |
|---|---|
| Perguntas críticas | 100% recuperam uma origem esperada no top 5 |
| Nomes de produtos publicados | zero falsas recusas no conjunto crítico |
| Negativos críticos | zero perguntas chegam à geração |
| Retrieval geral | Recall@5 mínimo de 95% no conjunto de validação |
| Gate | precision de `supported` mínima de 95% no conjunto de validação |
| Citações | zero IDs desconhecidos ou autoridade incompatível entregues |
| Latência | nenhuma variante entra com regressão de p95 superior a 20% sem ganho aprovado |
| Reprodutibilidade | todo resultado registra perfil e geração do índice |

Percentuais devem ser apresentados junto de contagens absolutas. Com datasets pequenos,
“95%” isolado pode esconder um único erro crítico.

## Fase 0: congelar a baseline

### Entregáveis

- Criar `evals/retrieval/golden.jsonl`.
- Definir schema versionado para casos de avaliação.
- Criar runner local que execute o índice ativo ou uma geração candidata.
- Produzir métricas por canal: lexical, vetorial e híbrido.
- Registrar a baseline atual antes de mudar SQL, chunking ou embedding.

### Schema mínimo de um caso

```json
{
  "id": "pt-product-candidate-portal-title",
  "locale": "pt-BR",
  "question": "Portal do Candidato",
  "history": [],
  "expectedSupport": "supported",
  "relevantSources": [
    {
      "slug": "candidate_portal",
      "sections": ["Resumo", "Problema", "Solução", "Resultado"],
      "relevance": 3
    }
  ],
  "tags": ["product-title", "pt-BR", "profile"]
}
```

### Cobertura mínima inicial

- as quatro perguntas da auditoria;
- título exato e parcial de cada produto;
- paráfrases sobre problema, solução, tecnologia e resultado;
- perguntas sobre João que usam e não usam seu nome;
- inglês consultando evidência em português;
- perguntas com múltiplos produtos;
- perguntas parcialmente respondíveis;
- negativos fáceis, como presidente do Brasil;
- negativos semanticamente próximos, como pedidos genéricos para implementar RAG;
- follow-ups válidos;
- mudança abrupta de assunto depois de uma pergunta válida.

### Métricas

- Hit Rate e Recall@1, @3, @5 e @8;
- MRR;
- nDCG@5 quando houver relevância graduada;
- precision e recall do estado `supported`;
- falsas aceitações e falsas recusas por tag;
- total de chunks e tokens enviados à geração;
- latência de embedding, banco, gate e geração separadamente.

### Critério de saída

A baseline reproduz os quatro comportamentos observados e gera um relatório legível sem
chamar a geração de respostas.

## Fase 1: tornar o retrieval observável

### Modelo interno

- Substituir o campo genérico `RetrievedChunk.score` por um objeto de sinais, mantendo
  `rrf_score` explicitamente nomeado.
- Representar ausência de match textual como `None`, não como um score indistinguível de
  zero.
- Registrar ranks por canal antes da fusão.
- Incluir `index_generation` e perfil de retrieval nos resultados diagnósticos.
- Não expor esses sinais no contrato público de `/ask`.

Uma forma possível:

```python
@dataclass(frozen=True, slots=True)
class RetrievalSignals:
    vector_distance: float | None
    vector_similarity: float | None
    vector_rank: int | None
    text_rank_cd: float | None
    text_rank: int | None
    title_match: bool
    section_match: bool
    rrf_score: float
```

### SQL

- Calcular `chunk.embedding <=> query_embedding` uma única vez por candidato.
- Expor `1 - distance` como similaridade sem descartar a distância original.
- Preservar `ts_rank_cd` antes de gerar o rank textual.
- Informar por quais canais cada candidato entrou no pool.
- Manter RRF como baseline de ordenação.

### Inspector

- Mostrar pergunta original, histórico usado e consulta final.
- Imprimir scores brutos e ranks por canal.
- Adicionar saída JSON para consumo do evaluator.
- Mostrar perfil do índice e versão da estratégia lexical.
- Manter modo humano como default.

### Testes

- chunk apenas vetorial;
- chunk apenas textual;
- chunk presente nos dois canais;
- empate determinístico;
- ausência de índice ativo;
- incompatibilidade de perfil;
- serialização JSON do inspector.

### Critério de saída

O inspector reproduz os valores brutos da auditoria e deixa evidente que `0.016393` é RRF,
não relevância.

## Fase 2: corrigir o canal lexical

### Migration e perfil de índice

- Adicionar uma versão explícita da estratégia lexical ao perfil da geração.
- Tornar a migration aditiva e compatível com a geração ativa.
- Materializar o `tsvector` ponderado durante `_write_generation`.
- Criar ou substituir o índice GIN correspondente.
- Reindexar para uma nova geração antes de ativá-la.
- Garantir rollback pela troca do ponteiro de geração, não pela destruição do índice
  anterior.

### Construção da consulta

- Introduzir um `RetrievalQuery` com:
  - pergunta original;
  - texto usado no embedding;
  - expressão lexical;
  - histórico efetivamente usado;
  - versão da estratégia.
- Remover da expressão lexical termos de navegação como “João”, “ele”, “trabalhou com”,
  somente quando isso não remover a entidade pesquisada.
- Preservar nomes próprios, siglas e tecnologias.
- Separar busca por frase/título da busca ampla por termos.
- Tratar aliases como Conteúdo publicado, não como regex de escopo.

### Testes de regressão

- “Portal do Candidato” encontra o título pelo canal textual.
- “Plataforma de Gestão de Pessoas” encontra Profile Doc e Case Study.
- “João trabalhou com Power BI?” mantém “Power BI” na consulta útil.
- “presidente do Brasil” não cria match lexical.
- acentos, plural, hífen e caixa não alteram os casos esperados.

### Critério de saída

Todos os nomes de produtos do Golden Dataset possuem match lexical explicável, e a busca
híbrida não regride o Recall@5 vetorial.

## Fase 3: implementar o gate pós-retrieval

### Contrato

Criar uma interface separada:

```python
class EvidenceSupportEvaluator(Protocol):
    def evaluate(
        self,
        *,
        question: str,
        retrieval_query: RetrievalQuery,
        chunks: tuple[RetrievedChunk, ...],
        index_profile: RetrievalProfile,
    ) -> SupportDecision: ...
```

`SupportDecision` deve incluir:

- `supported: bool`;
- regra ou versão do modelo usada;
- features agregadas;
- razões diagnósticas;
- chunks aprovados para geração.

### Regra inicial

- Calibrar thresholds usando o conjunto de treino/calibração.
- Confirmar o resultado em um holdout separado.
- Aceitar um sinal lexical forte **ou** um sinal semântico forte.
- Não exigir que os dois canais concordem.
- Não usar RRF como feature absoluta.
- Não enviar chunks reprovados ao gerador.
- Versionar thresholds junto do perfil ao qual pertencem.

Features iniciais:

- melhor similaridade vetorial;
- margem entre o primeiro e o segundo documento;
- melhor `ts_rank_cd`;
- match de título ou alias;
- presença em ambos os canais;
- quantidade de documentos com suporte;
- concentração dos resultados em uma mesma origem.

### Integração no RAG

- Executar `search_my_work` antes da decisão de suporte.
- Quando não houver suporte, retornar `insufficient` sem chamar o gerador.
- Manter a mensagem de falta de evidência como resposta segura padrão.
- Usar uma classificação opcional de intenção apenas para escolher entre “sem evidência”
  e “fora da trajetória”, nunca para liberar geração.
- Remover o bloqueio por `PortfolioQuestionScopeEvaluator` depois que a nova avaliação
  passar no Golden Dataset.

### Testes

- pergunta válida chama retrieval e geração;
- nome de produto chama retrieval e geração;
- pergunta sem suporte chama retrieval, mas não geração;
- vizinhos vetoriais fracos são descartados;
- match forte em título é suficiente sem similaridade excepcional;
- match semântico forte é suficiente sem texto literal;
- RRF alto por posição não libera um chunk fraco;
- thresholds incompatíveis com o perfil ativo falham de forma explícita.

### Critério de saída

As quatro perguntas da auditoria recebem a decisão correta e os critérios do gate de
qualidade passam no holdout.

## Fase 4: controlar o uso do histórico

### Estratégia inicial

- Usar apenas a pergunta atual por padrão.
- Considerar histórico somente quando o turno atual for elíptico.
- Usar preferencialmente a última pergunta do visitante.
- Não concatenar respostas do assistente à consulta lexical ou ao embedding.
- Registrar se e por que o histórico foi usado.

### Evolução opcional

Adicionar um `QueryRewriter` somente se as regras determinísticas não cobrirem os casos
dourados. Sua saída deve ser uma pergunta autônoma e nunca uma resposta.

### Casos obrigatórios

- “Fale sobre o Fictor360 AI” → “qual foi o resultado?”;
- “Portal do Candidato” → “qual stack foi usada?”;
- pergunta válida → “e o presidente?”;
- pergunta válida → nova pergunta completa sobre outro produto;
- histórico em inglês → pergunta atual em português e o inverso.

### Critério de saída

Follow-ups recuperam a origem correta, e mudanças de assunto não herdam suporte do turno
anterior.

## Fase 5: selecionar contexto e reduzir duplicação

O Profile Doc e o Case Study da Plataforma de Gestão de Pessoas possuem trechos próximos.
Isso é legítimo para autoridade, mas pode ocupar todo o top-k.

### Entregáveis

- Medir recall do pool antes de qualquer deduplicação.
- Limitar quantidade de chunks por documento na seleção final, sem alterar o pool de
  diagnóstico.
- Favorecer diversidade de seções quando a pergunta for ampla.
- Preservar Case Study e Profile Doc juntos quando suas autoridades forem complementares.
- Testar expansão para vizinhos ou seção-pai somente depois que um chunk filho passar no
  gate.
- Separar chunks citáveis de contexto auxiliar.

### Critério de saída

O contexto enviado à geração cobre as evidências necessárias com menos duplicação e sem
reduzir Recall@5 ou autoridade.

## Fase 6: executar experimentos controlados

Os experimentos são sequenciais. Uma variante só avança se superar a baseline no holdout.

### Chunking

Comparar:

1. baseline por seção: 350/500/50;
2. seção: 250/350/40;
3. seção: 180/280/30;
4. child chunks de 120–200 tokens com expansão de contexto;
5. semantic splitter apenas em seções que excedam um limite medido.

Avaliar recall, ranking, duplicação, cobertura de claims e tokens de contexto. Como os
chunks atuais são curtos, a expectativa inicial é manter a baseline.

### Embeddings

Comparar `text-embedding-3-small` e `text-embedding-3-large` com:

- o mesmo corpus;
- o mesmo chunker;
- as mesmas dimensões declaradas;
- as mesmas perguntas;
- reindexações separadas;
- thresholds recalibrados para cada perfil.

Não usar a mudança de modelo para compensar um índice lexical ou gate incorreto.

### Reranking

Adicionar somente se:

- a evidência relevante já aparece no pool de 16–32 candidatos;
- sua posição ou separação de negativos ainda é insuficiente;
- um reranker multilíngue melhora o holdout;
- latência e operação cabem no droplet.

Comparar RRF puro com:

- cross-encoder local;
- reranking pelo provedor atual;
- nenhuma etapa adicional.

### Critério de saída

Cada decisão possui relatório comparável. Variantes sem ganho claro são rejeitadas e não
permanecem como complexidade desativada no código.

## Fase 7: rollout e documentação

### Rollout

- Construir a nova geração sem desativar a anterior.
- Executar o Golden Dataset contra a geração candidata.
- Ativar somente após passar os gates.
- Manter rollback por ponteiro para a geração anterior.
- Registrar métricas agregadas sem persistir conversas integrais.
- Não usar perguntas reais de visitantes como dataset sem política explícita de
  privacidade e retenção.

### Documentação

- Atualizar `README.md` com os sinais mostrados pelo inspector.
- Atualizar `docs/SPEC.md` para substituir o gate pré-retrieval por gate de suporte.
- Atualizar `docs/ARCHITECTURE.md` com o fluxo retrieval-first.
- Registrar ADR se a mudança introduzir reranker externo, índice bilíngue ou novo serviço.
- Adicionar changeset `patch` para cada mudança pública de recusa, inspector ou resposta.

### Critério de saída

A geração candidata passa no Golden Dataset, pode ser ativada e revertida sem downtime, e
a documentação descreve o comportamento realmente executado.

## Sequência sugerida de commits

Cada item deve ser pequeno o suficiente para revisão independente:

1. adicionar schema e fixtures iniciais do Golden Dataset;
2. adicionar runner e métricas de retrieval;
3. registrar baseline do índice atual;
4. modelar sinais brutos de retrieval;
5. expor sinais na consulta Postgres;
6. adicionar JSON e perfil de índice ao inspector;
7. versionar a estratégia lexical no perfil da geração;
8. materializar `tsvector` ponderado por título, seção e corpo;
9. introduzir `RetrievalQuery` e corrigir termos lexicais;
10. adicionar regressões de nomes de produtos;
11. modelar `SupportDecision` e calibrar a primeira regra;
12. mover o gate para depois do retrieval;
13. remover o bloqueio por palavras-chave;
14. restringir histórico a follow-ups elípticos;
15. selecionar contexto com diversidade controlada;
16. atualizar README, SPEC, arquitetura e changeset;
17. executar e documentar experimentos opcionais separadamente.

Commits de migration, reindexação e ativação devem permanecer separados para que a
geração anterior continue sendo um rollback válido.

## Riscos e mitigação

| Risco | Mitigação |
|---|---|
| Threshold ajustado às quatro perguntas | calibração e holdout com categorias amplas |
| Título forte aceita pergunta ambígua | exigir entidade publicada completa ou suporte semântico complementar conforme os dados |
| Histórico mascara mudança de assunto | pergunta atual por padrão e casos dourados de topic switch |
| Duplicação Profile/Case Study ocupa top-k | diversidade apenas na seleção final, não no pool |
| Migration lexical invalida busca ativa | geração candidata e troca atômica do ponteiro |
| Mudança de embedding altera distribuição | thresholds versionados por perfil e nova avaliação |
| Reranker aumenta custo/latência | etapa opcional com critério explícito de adoção |
| Logs violam conversa efêmera | métricas agregadas e conteúdo integral desabilitado |

## Definição de pronto

O trabalho está concluído quando:

- o Golden Dataset e seu runner fazem parte dos checks reproduzíveis;
- “Portal do Candidato” e “Plataforma de Gestão de Pessoas” passam pelo fluxo real;
- “presidente do Brasil” executa retrieval, é reprovado pelo gate e não chama geração;
- o inspector diferencia scores vetorial, textual, RRF e eventual reranker;
- o índice lexical considera título, seção e conteúdo;
- follow-ups funcionam sem contaminar mudanças de assunto;
- thresholds estão versionados e validados fora do conjunto usado para escolhê-los;
- nenhuma mudança de chunker, embedding ou reranker foi adotada sem ganho mensurável;
- README, SPEC, arquitetura e changeset refletem o comportamento público;
- a geração anterior continua disponível para rollback.
