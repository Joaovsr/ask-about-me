# Estratégia de retrieval e evidência para o RAG de Portfólio

Pesquisa realizada em 2026-07-29 a partir da implementação local, documentação oficial,
artigos acadêmicos e repositórios open source mantidos pelos autores das ferramentas.

## Resumo executivo

A análise proposta está correta no ponto principal: o gate atual mistura duas perguntas
diferentes — “a pergunta parece falar do portfólio?” e “o KB contém evidência suficiente
para respondê-la?” — e tenta resolver a primeira com palavras-chave antes de consultar a
evidência. Isso cria falsos negativos para nomes de produtos publicados. Para este produto,
a decisão útil deve ocorrer depois da recuperação de candidatos e deve ser chamada de
**gate de suporte/evidência**, não de gate de escopo.

Também está correta a leitura do score: o valor exposto hoje é a soma de posições de duas
listas por Reciprocal Rank Fusion (RRF), não uma probabilidade nem uma medida absoluta de
relevância. O artigo original define RRF em termos de ranks e explica que a constante `k`
reduz o efeito de resultados excepcionalmente altos de uma lista; ele é um método de
fusão de ordenações, não de rejeição de perguntas
([Cormack, Clarke e Büttcher, 2009](https://cormack.uwaterloo.ca/cormacksigir09-rrf.pdf)).
Por isso, valores como `1 / (60 + rank)` só dizem onde um chunk ficou na lista.

A direção recomendada é:

1. construir uma consulta de retrieval autônoma;
2. recuperar candidatos densos e lexicais, preservando scores brutos;
3. fundir as listas para recall;
4. opcionalmente reranquear os candidatos;
5. aplicar um gate de suporte calibrado no Golden Dataset;
6. enviar à geração apenas os chunks aprovados.

O gate não deve nascer de um número escolhido intuitivamente. Ele deve ser calibrado com
perguntas positivas, negativas e difíceis do próprio portfólio. A documentação de busca
híbrida do Qdrant mostra o mesmo padrão — filtrar resultados semânticos por score antes da
fusão — e avisa explicitamente que o threshold mostrado é apenas um exemplo e precisa ser
ajustado para os dados e o modelo
([Qdrant, Hybrid Search](https://qdrant.tech/documentation/search/text-search/hybrid-search/)).

## O que a implementação atual faz

### Chunking

O `TokenSectionChunker` atual:

- nunca cruza o limite de uma seção;
- prefere parágrafos e depois sentenças;
- usa alvo de 350 tokens, máximo de 500 e overlap de até 50 tokens;
- só corta por tokens quando uma sentença isolada passa do máximo.

Isso está em
[`src/ask_about_me/knowledge_base.py`](../../src/ask_about_me/knowledge_base.py) e a
configuração está em
[`src/ask_about_me/config.py`](../../src/ask_about_me/config.py). A estratégia é uma boa
baseline para conteúdo editorial estruturado. O starter kit open source de Knowledge
Retrieval da OpenAI oferece estratégias muito parecidas: preservar headings, recuar para
parágrafos/sentenças/tokens e combinar as duas abordagens
([OpenAI Knowledge Retrieval, chunking](https://github.com/openai/openai-knowledge-retrieval#chunking-strategies)).

Há, porém, duas propriedades que precisam entrar nas avaliações:

- “overlap de 50” significa **até** 50 tokens e somente unidades semânticas inteiras. Se a
  sentença anterior tiver mais de 50 tokens, não haverá overlap;
- se as seções publicadas forem curtas, 350/500 será quase irrelevante porque cada seção
  já vira um chunk. Nesse caso, qualidade editorial, títulos e metadados pesam mais que
  reduzir o tamanho nominal.

No seed atual, essa segunda hipótese é o caso real: 11 KB Docs produzem 33 chunks, com
19 tokens no menor, 43 na mediana e 154 no maior. Nenhum chunk passa do alvo de 350 tokens.
Portanto, os resultados observados hoje são principalmente consequência das fronteiras
editoriais das seções, não dos limites 350/500/50.

Não existe evidência para trocar imediatamente por “semantic chunking”. O
[`SemanticSplitterNodeParser`](https://github.com/run-llama/llama_index/blob/main/llama-index-core/llama_index/core/node_parser/text/semantic_splitter.py)
do LlamaIndex é uma implementação útil para um experimento controlado, mas adiciona
embeddings e um threshold de quebra a um corpus que já possui seções humanas. Ele só deve
ser adotado se superar o chunker atual no Golden Dataset.

### Contexto no embedding e assimetria lexical

Cada embedding de documento já recebe:

```text
Tipo de documento: …
Título: …
Seção: …
Conteúdo: …
```

Essa contextualização manual é adequada para um portfólio, pois impede que um trecho como
“reduziu o tempo de horas para milissegundos” perca a identidade do produto. É uma versão
determinística e barata da ideia de contextualizar cada chunk antes de indexá-lo. A
Anthropic relata ganho ao prefixar contexto específico ao chunk antes dos índices denso e
lexical, mas os números publicados são do corpus e da configuração deles e devem ser
tratados como hipótese a reproduzir, não como garantia
([Anthropic, Contextual Retrieval](https://www.anthropic.com/engineering/contextual-retrieval)).

Existe uma assimetria concreta na implementação: o embedding inclui título e seção, mas a
coluna gerada `search_vector` usa apenas `content`, conforme
[`migrations/versions/0002_create_knowledge_base.py`](../../migrations/versions/0002_create_knowledge_base.py).
Assim, “Portal do Candidato” não produz match textual quando o nome aparece no título, mas
não é repetido no corpo daquele chunk.

Antes de alterar chunk size ou modelo, o primeiro experimento deveria indexar um documento
estruturado no canal lexical:

- título com peso `A`;
- seção com peso `B`;
- aliases/termos canônicos, se existirem como conteúdo publicado, com peso `B`;
- corpo com peso `D`.

O PostgreSQL recomenda `setweight` precisamente para diferenciar título, palavras-chave,
resumo e corpo em um `tsvector` estruturado
([PostgreSQL, Controlling Text Search](https://www.postgresql.org/docs/current/textsearch-controls.html#TEXTSEARCH-PARSING-DOCUMENTS)).
Isso resolve nomes de produtos publicados sem introduzir uma lista manual no gate. A lista
de aliases, se necessária, deve pertencer ao conteúdo canônico do produto, não a uma regex
de “assuntos permitidos”.

### Retrieval e score

O retrieval atual cria até `result_limit * 4` candidatos por canal, ordena o canal vetorial
por distância de cosseno e o textual por `ts_rank_cd`, une IDs e retorna oito chunks pela
soma RRF. Essa arquitetura híbrida é coerente com a orientação do próprio pgvector, que
recomenda combiná-lo com Full Text Search e cita RRF ou cross-encoder como formas de
combinar resultados
([pgvector, Hybrid Search](https://github.com/pgvector/pgvector#hybrid-search)).

O problema não é usar RRF; é esconder os sinais originais atrás dele. O pgvector define
`<=>` como distância de cosseno e documenta `1 - distância` como similaridade de cosseno
([pgvector, Querying](https://github.com/pgvector/pgvector#querying)). O inspector deveria
mostrar, para cada candidato:

| Sinal | Uso |
|---|---|
| `vector_distance` e `vector_similarity` | diagnóstico e possível feature do gate |
| `vector_rank` | contribuição densa para a fusão |
| `text_match` e `text_rank_cd` | evidência lexical bruta |
| `text_rank` | contribuição lexical para a fusão |
| `rrf_score` | ordenação combinada, nunca confiança |
| `title_match` / `section_match` | explicação de matches de entidades publicadas |
| `reranker_score`, se houver | relevância par-a-par, calibrada separadamente |
| chunker, embedding model e geração do índice | reprodutibilidade |

Uma busca k-NN sempre consegue ordenar os vizinhos existentes. Logo, “presidente do
Brasil” ainda terá um vizinho mais próximo mesmo quando todos forem ruins. O fato de o
pgvector aceitar também uma condição de distância mostra que recuperar top-k e aceitar
top-k são operações diferentes
([pgvector, distance filtering](https://github.com/pgvector/pgvector#querying)).

O `ts_rank_cd` também não é probabilidade. A documentação do PostgreSQL diz que relevância
é específica da aplicação e que suas normalizações não usam informação global; transformar
o valor para `[0, 1]` pode ser apenas cosmético
([PostgreSQL, Ranking Search Results](https://www.postgresql.org/docs/current/textsearch-controls.html#TEXTSEARCH-RANKING)).
Portanto, expor scores brutos é necessário, mas nenhum deles deve receber um threshold
universal sem avaliação local.

### Medição do índice ativo

Uma consulta diagnóstica no índice OpenAI ativo em 2026-07-29 confirmou que os quatro
resultados analisados vieram exclusivamente do canal vetorial: o `ts_rank_cd` foi `0` em
todos os melhores chunks. Os melhores sinais densos foram:

| Pergunta | Melhor similaridade de cosseno | Melhor distância | Resultado esperado |
|---|---:|---:|---|
| Qual o presidente do Brasil? | 0,252112 | 0,747888 | sem suporte |
| João trabalhou com Power BI? | 0,557582 | 0,442418 | com suporte |
| Portal do Candidato | 0,676224 | 0,323776 | com suporte |
| Plataforma de Gestão de Pessoas | 0,660126 | 0,339874 | com suporte |

Há separação clara nessa amostra, o que confirma que a distância bruta carrega informação
que o RRF exposto descartou. Ela **não** autoriza usar `0,50` como threshold: quatro
perguntas não representam paráfrases, inglês, follow-ups, negativos semanticamente próximos
nem mudanças futuras de conteúdo, modelo ou chunker.

## Gate recomendado

### Separar intenção de suporte

O `PortfolioQuestionScopeEvaluator` atual reconhece nomes do dono e uma lista de tópicos.
Ele pode continuar existindo temporariamente como telemetria, mas não deve bloquear antes
do retrieval. A pergunta que decide geração deveria ser:

> Há pelo menos uma evidência recuperada que sustenta uma resposta sobre o conteúdo
> publicado do João?

Isso permite “Portal do Candidato”, “Plataforma de Gestão de Pessoas” e nomes futuros sem
mudança de código. Também bloqueia “presidente do Brasil” quando os sinais não atingem o
critério calibrado.

Convém manter estados internos distintos:

- `supported`: evidência suficiente; gera resposta;
- `partial`: alguma evidência responde apenas parte da pergunta;
- `unsupported`: o KB não sustenta a resposta;
- opcionalmente `clearly_out_of_scope`: classificação de produto posterior, sem afetar a
  decisão segura de não gerar.

Isso evita prometer que o sistema compreendeu a intenção do visitante quando, na verdade,
apenas constatou ausência de evidência.

### Features e regra inicial

Uma primeira versão do gate pode ser determinística e observável. Ela não precisa começar
como um classificador aprendido. Features candidatas:

- match lexical em título ou alias canônico;
- `ts_rank_cd` do melhor chunk;
- similaridade de cosseno do melhor chunk;
- diferença entre o primeiro e o segundo resultado denso;
- concordância entre os canais denso e lexical;
- score do reranker;
- número de chunks/documentos que passam individualmente;
- `doc_type`, apenas para validar autoridade depois da relevância, nunca para fabricar
  relevância.

Uma regra prudente é aceitar quando houver **um sinal lexical forte** ou **um sinal
semântico/reranker forte**, em vez de exigir ambos. Exigir concordância dos dois canais
recriaria o falso negativo de nomes, sinônimos e perguntas em inglês; aceitar qualquer
vizinho denso recriaria o falso positivo de “presidente”.

Os thresholds devem ser escolhidos em um conjunto de calibração e confirmados em um
conjunto separado. Deve-se registrar a curva precisão–recall da classe `supported`,
priorizando alta cobertura das perguntas válidas sem perder o teto aceitável de falsas
aceitações. Qualquer modelo ou chunker novo exige recalibração.

### Histórico de conversa

Hoje, até quatro mensagens anteriores são concatenadas à pergunta para embedding e
ligadas por `OR` no Full Text Search. Isso ajuda follow-ups, mas pode contaminar o gate:
depois de uma pergunta válida, “e o presidente?” herdará sinais fortes do turno anterior.

O experimento recomendado é construir uma consulta autônoma apenas quando o turno for um
follow-up elíptico. O inspector deve exibir separadamente:

- pergunta original;
- histórico usado;
- consulta reescrita ou expandida;
- scores para a pergunta atual e para a consulta final.

O gate deve exigir que a evidência responda ao turno atual no contexto, não apenas que seja
parecida com algum texto recente.

## Reranking

RRF deve continuar como baseline de fusão. Um reranker entra somente se a avaliação mostrar
que candidatos relevantes chegam ao pool, mas ficam mal ordenados ou se o score par-a-par
separar melhor positivos de negativos.

O padrão “retrieve then rerank” é bem estabelecido: um bi-encoder ou busca lexical produz
um conjunto amplo, e um cross-encoder avalia query e documento juntos. A documentação do
Sentence Transformers traz implementação, exemplos e avaliação específica para esse
pipeline
([Sentence Transformers, Retrieve & Re-Rank](https://www.sbert.net/examples/sentence_transformer/applications/retrieve_rerank/README.html)).

Para este corpus pequeno:

- testar primeiro reranking dos 16–32 candidatos híbridos já disponíveis;
- avaliar um reranker multilíngue em `pt-BR` e em perguntas `en-US → pt-BR`;
- medir latência no droplet, não apenas no notebook;
- calibrar o score do reranker no mesmo protocolo do gate;
- evitar um segundo provedor externo sem revisar as restrições arquiteturais existentes.

Também é válido experimentar um reranker do mesmo modelo gerador, como faz o starter kit
da OpenAI com estágio opcional de reranking e `score_threshold`
([OpenAI Knowledge Retrieval, retrieval pipeline](https://github.com/openai/openai-knowledge-retrieval#retrieval-pipeline)).
Ele preserva a restrição de provedor, mas adiciona custo, latência e variância. Um
cross-encoder local é mais determinístico, porém exige operação e precisa provar qualidade
multilíngue.

## Chunking recomendado para o portfólio

Manter o chunker atual como baseline e comparar configurações, não escolher um número por
receita externa:

| Variante | Hipótese |
|---|---|
| seção atual, 350/500/50 | baseline |
| seção, 180/280/30 | claims mais concentrados e melhor reranking |
| seção, 250/350/40 | compromisso entre contexto e precisão |
| child 120–200 + expansão para seção/vizinhos | busca precisa e geração contextual |
| semantic splitter dentro de seções longas | útil apenas quando uma seção mistura assuntos |

O teste deve medir:

- Recall@k do chunk ou documento esperado;
- nDCG@k/MRR quando há múltiplos chunks com diferentes graus de relevância;
- quantidade de chunks duplicados por overlap no top-k;
- cobertura das afirmações necessárias para responder;
- tokens totais enviados à geração;
- falsos positivos do gate.

Em um portfólio, a unidade editorial é mais importante que uniformidade de tamanho. Um
Case Study bem estruturado pode ter chunks por “Contexto”, “Decisão”, “Implementação” e
“Resultado”. Um Profile Doc pode usar unidades ainda menores. Overlap deve ser reduzido
quando ele faz vários chunks quase idênticos ocuparem o top-k.

Se um chunk pequeno passar no gate, a geração pode receber também sua seção ou vizinhos
imediatos, identificados como contexto auxiliar. A citação continua apontando para a
evidência mínima que sustenta a afirmação.

## Embeddings

`text-embedding-3-small` é uma baseline razoável e tem resultado multilíngue melhor que a
geração anterior nos benchmarks divulgados pela OpenAI. `text-embedding-3-large` obteve
resultado médio maior em MIRACL, mas isso não prova ganho no portfólio
([OpenAI, New embedding models](https://openai.com/index/new-embedding-models-and-api-updates/)).

Recomendação:

1. não trocar o modelo para consertar o gate;
2. corrigir primeiro a observabilidade e o índice lexical estruturado;
3. comparar `text-embedding-3-small` e `text-embedding-3-large` no mesmo índice/chunker e
   Golden Dataset;
4. incluir queries em inglês contra evidência canônica em português;
5. tratar qualquer mudança de modelo, dimensão ou formato de contexto como nova versão do
   índice e recalibrar scores.

O projeto [MTEB](https://github.com/embeddings-benchmark/mteb) é útil para selecionar
candidatos multilíngues, mas leaderboard público não substitui o conjunto de perguntas do
João. Títulos próprios, nomes de produtos e linguagem de recrutadores formam uma
distribuição muito menor e específica.

## Avaliação e protocolo de decisão

O Golden Dataset planejado no repositório é o mecanismo correto. Ele deve separar:

### Retrieval

- Hit Rate/Recall@1, @3, @5 e @8 para evidência esperada;
- MRR ou nDCG quando a posição importa;
- recall do pool antes do reranker e ranking depois dele;
- resultado por canal: lexical, denso, híbrido e híbrido + reranker.

O repositório [BEIR](https://github.com/beir-cellar/beir) implementa nDCG, MAP, Recall,
Precision e MRR e pode servir de referência para o formato `queries/corpus/qrels`. Não é
necessário adotar a biblioteca para copiar a disciplina de avaliação.

### Gate

- recall de perguntas suportadas;
- precision de `supported`;
- taxa de falsa aceitação de perguntas sem evidência;
- taxa de falsa recusa de nomes de produtos;
- métricas separadas por `pt-BR`, `en-US`, follow-up e tipo de documento;
- curva precisão–recall e matriz de confusão para cada configuração.

### Geração

- todas as afirmações têm citações válidas;
- a citação realmente sustenta a afirmação;
- autoridade compatível com `doc_type`;
- completude dos tipos de afirmação solicitados;
- estado `partial/unsupported` correto;
- custo e latência.

O dataset mínimo precisa conter:

- perguntas diretas e paráfrases sobre cada produto publicado;
- título exato, título parcial, sigla, tecnologia e resultado;
- perguntas cruzadas entre produtos;
- inglês contra o índice em português;
- follow-ups válidos e mudanças abruptas de assunto;
- negativos fáceis (“presidente do Brasil”);
- negativos difíceis, semanticamente próximos (“como implementar RAG?” quando a pergunta
  não é sobre o trabalho/opinião do João);
- perguntas parcialmente respondíveis;
- chunks contraditórios ou de autoridade inadequada.

As quatro perguntas observadas devem virar casos de regressão, mas não bastam para escolher
threshold. O starter kit da OpenAI também separa dataset curado, recuperação, reranking e
avaliação, o que o torna uma referência mais próxima desta arquitetura que frameworks de
agente genéricos
([OpenAI Knowledge Retrieval](https://github.com/openai/openai-knowledge-retrieval)).

## Ordem de implementação sugerida

1. **Inspector:** expor scores brutos, ranks, canal de origem, match de título/seção,
   consulta final e versão do índice.
2. **Índice lexical:** incluir título e seção com pesos; reindexar.
3. **Golden Dataset:** adicionar positivos, negativos e hard negatives; definir qrels por
   chunk e documento.
4. **Baseline:** registrar lexical, denso e RRF sem gate.
5. **Gate pós-retrieval:** calibrar uma regra simples com sinais brutos; remover o bloqueio
   por regex.
6. **Chunking:** executar a matriz de tamanhos e expansão de vizinhos.
7. **Embedding:** comparar `small`/`large` somente depois das correções anteriores.
8. **Reranker:** adotar apenas se houver ganho claro em gate/ranking que justifique
   custo e latência.

## Repositórios e fontes para exploração

- [openai/openai-knowledge-retrieval](https://github.com/openai/openai-knowledge-retrieval):
  referência de chunkers estruturais, filtros, reranking e evals; vale copiar ideias e
  formatos, não migrar a arquitetura.
- [pgvector/pgvector](https://github.com/pgvector/pgvector): semântica de distâncias,
  exact/approximate search e orientação oficial de hybrid search; já é a fundação correta.
- [UKPLab/sentence-transformers](https://github.com/UKPLab/sentence-transformers):
  referência para cross-encoders locais e avaliações de reranking.
- [beir-cellar/beir](https://github.com/beir-cellar/beir): métricas e formato de benchmark
  de Information Retrieval.
- [embeddings-benchmark/mteb](https://github.com/embeddings-benchmark/mteb): triagem de
  modelos multilíngues e tarefas em português.
- [run-llama/llama_index `semantic_splitter.py`](https://github.com/run-llama/llama_index/blob/main/llama-index-core/llama_index/core/node_parser/text/semantic_splitter.py):
  variante experimental para seções longas, não recomendação inicial.
- [stanford-futuredata/ColBERT](https://github.com/stanford-futuredata/ColBERT): referência
  de late interaction se, no futuro, dense + lexical + reranker simples ainda não bastarem;
  complexidade excessiva para o V1 atual.

## Conclusão

O problema observado não pede uma lista de palavras melhor nem uma troca imediata de
embedding. Ele pede que o sistema preserve a diferença entre **ordenação** e
**aceitação**. RRF pode continuar ordenando candidatos; o gate deve usar evidência
recuperada, sinais brutos e calibração local.

A correção de maior retorno imediato é tornar o índice lexical tão contextual quanto o
denso, incluindo título e seção. Em seguida, o inspector e o Golden Dataset permitem
calibrar um gate pós-retrieval que aceita nomes publicados e recusa vizinhos apenas
“menos distantes”. Chunking, embeddings e reranking passam então a ser decisões
experimentais mensuráveis, não tentativas de corrigir um gate conceitualmente errado.
