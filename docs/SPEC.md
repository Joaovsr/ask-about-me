# Especificação do V1

Esta é a especificação vigente do `ask-about-me`. O vocabulário canônico está em [`CONTEXT.md`](../CONTEXT.md), e decisões difíceis de reverter estão registradas em [`docs/adr/`](adr/).

## 1. Resultado esperado

O V1 transforma o portfólio público do João em uma experiência de RAG confiável para recrutadores técnicos e clientes potenciais. O visitante deve conseguir fazer uma pergunta sobre trajetória, projetos, competências ou opiniões técnicas e receber uma resposta fundamentada em conteúdo publicado, com evidências verificáveis.

O sistema também substitui os arquivos estáticos do portfólio por um pequeno sistema de conteúdo bilíngue, administrado sem commits e usado como origem da Knowledge Base.

## 2. Escopo

O V1 inclui:

- Portfólio Vue existente consumindo conteúdo publicado por HTTP.
- Conteúdo explícito em `pt-BR` e `en-US`.
- Painel admin privado para um único proprietário.
- Publicação imediata e consistente com a indexação.
- KB derivada do conteúdo publicado em `pt-BR`.
- Retrieval vetorial e textual atrás de uma única interface.
- Chat embutido com perguntas livres e prompts sugeridos.
- Respostas completas com cards de citação.
- Respostas parciais ou recusa quando não houver evidência suficiente.
- Histórico efêmero mantido no navegador.
- Deploy do portfólio, backend e Postgres/pgvector em um droplet da DigitalOcean.

O V1 não inclui:

- `compare_to_role`, parsing de vagas ou score de aderência.
- Booking, captura de contatos ou integrações de calendário.
- Streaming de tokens ou exposição de tool calls.
- Persistência ou analytics de conversas.
- Drafts, aprovação editorial ou agendamento de publicação.
- Voice, múltiplos agentes, crawler do GitHub ou reranker externo sem evidência de necessidade.

## 3. Limites do sistema

O trabalho abrange dois repositórios:

| Repositório | Responsabilidade |
|---|---|
| `joaovsr.github.io` | Portfólio Vue/Vite, carregamento de conteúdo público, chat embutido e renderização das citações. |
| `ask-about-me` | FastAPI, painel admin, conteúdo publicado, Knowledge Base, RAG, persistência e operações do backend. |

Em produção, os dois são servidos na mesma origem. O reverse proxy entrega o build estático do portfólio e encaminha as rotas do backend antes do fallback da SPA.

### 3.1 Módulos

**Conteúdo publicado**

Interface responsável por consultar o snapshot público atual e publicar uma alteração validada. Esconde tabelas, traduções, ordenação e controle de versão dos callers.

**Knowledge Base**

Interface responsável por projetar conteúdo em KB Docs, substituir chunks e embeddings e executar `search_my_work`. Esconde chunking, pgvector, full-text search e ranking.

**RAG de Portfólio**

Interface conceitual `answer(question, locale, history) -> complete answer`. Sempre recupera evidências antes de gerar e concentra as regras de autoridade, evidência insuficiente e integridade das citações.

**Adapters**

O portfólio Vue, o painel admin e os handlers HTTP apenas traduzem suas entradas para as interfaces dos módulos. Regras de publicação, retrieval ou evidência não pertencem aos adapters.

## 4. Conteúdo publicado

### 4.1 Entidades

O sistema administra:

- Profile
- Experience
- Project
- Skill
- Education
- Certification
- Case Study
- Essay
- Suggested Prompt

Textos de interface, labels de botões e mensagens genéricas continuam nos arquivos de localização do frontend. Eles não são conteúdo publicado nem entram na KB.

### 4.2 Identidade e estrutura

Toda entidade possui:

- ID interno estável.
- Slug público estável e único dentro do tipo.
- Posição explícita de exibição quando fizer parte de uma coleção ordenada.
- Versão usada para detectar edições concorrentes e identificar a origem de citações.
- Timestamps de criação e alteração.
- Campos localizados explícitos em `pt-BR` e `en-US` quando houver texto público.

Relacionamentos usam IDs estáveis, nunca nomes exibidos. Ícones são representados por chaves conhecidas pelo frontend, não por componentes Vue serializados.

Cada publicação bem-sucedida cria uma revisão imutável e move o ponteiro da versão atual. Revisões anteriores permanecem disponíveis para resolver citações versionadas enquanto a entidade estiver publicada; elas são histórico, não drafts editáveis.

O estado `private` de um Project descreve a visibilidade de seu repositório ou entrega. Ele não representa estado editorial, pois todo registro retornado pela interface pública já está publicado.

### 4.3 Mídia

Imagens possuem identidade, URL pública, ordem e texto alternativo localizado. No V1, uploads ficam em armazenamento persistente do droplet e fazem parte da política de backup. Binários e caminhos de arquivo não são indexados no KB.

### 4.4 Localização

`pt-BR` e `en-US` são obrigatórios para a publicação de campos localizados. O frontend pede apenas o locale ativo e usa `pt-BR` como fallback defensivo, não como substituto para uma tradução ausente no momento da publicação.

O idioma solicitado pelo frontend determina o idioma da resposta do RAG. As evidências e seus links canônicos permanecem no `pt-BR` original no V1, mesmo em uma resposta em inglês.

## 5. Projeção para a Knowledge Base

A projeção determinística converte conteúdo publicado em KB Docs:

| Conteúdo | `doc_type` resultante |
|---|---|
| Case Study | `case_study` |
| Essay | `essay` |
| Profile | `profile` |
| Cada Experience | `profile` |
| Cada Project | `profile` |
| Cada Skill | `profile` |
| Cada Education | `profile` |
| Cada Certification | `profile` |

Um Project pode estar relacionado a um Case Study, mas seu resumo continua sendo um Profile Doc. Apenas conteúdo explicitamente publicado como Case Study recebe a força factual de experiência prática.

Suggested Prompts, textos de interface, dados de contato, caminhos de mídia e metadados operacionais não são indexados.

Cada KB Doc registra:

- ID e revisão de uma única entidade de origem.
- `doc_type`.
- Título e slug públicos.
- Seção lógica.
- Texto canônico em `pt-BR`.
- Chunks e embeddings derivados.
- Geração do índice, separada da revisão do conteúdo de origem.

## 6. Publicação consistente

Salvar no painel admin executa uma única operação lógica:

1. Validar estrutura, relacionamentos e as duas localizações.
2. Construir a projeção em `pt-BR` dos conteúdos afetados.
3. Gerar chunks e embeddings antes de substituir a versão pública.
4. Confirmar a revisão imutável, o ponteiro atual, a versão do snapshot, os KB Docs e os chunks juntos no Postgres.

Se validação, embedding ou persistência falhar, a alteração não é publicada e a versão anterior continua atendendo tanto o portfólio quanto o RAG. O painel apresenta o erro sem criar um draft implícito.

O V1 não mantém cache de conteúdo no backend. O snapshot usa sua versão transacional como ETag, portanto uma publicação não depende de uma etapa falível de invalidação.

Exclusões obedecem à mesma regra e removem os derivados da KB junto com o conteúdo atual. Revisões de uma entidade excluída deixam de ser publicamente acessíveis. Uma reindexação completa de recuperação fica vinculada à versão do snapshot que leu, constrói uma nova geração de KB em paralelo e só troca o ponteiro ativo se essa versão ainda for a atual. Se houver publicação concorrente, a geração candidata é descartada e refeita; o índice vigente nunca é apagado antes do sucesso.

## 7. Retrieval

O módulo Knowledge Base expõe uma única operação `search_my_work`. Sua implementação combina:

- Busca vetorial com pgvector.
- Full-text search ponderado do Postgres para título, seção e corpo em português.
- Deduplicação e ranking híbrido dos candidatos por RRF.
- Gate de suporte pós-retrieval calibrado no Golden Dataset.

Cada resultado inclui pelo menos:

- ID do chunk.
- ID e versão do KB Doc.
- `doc_type`.
- Título e seção.
- Trecho original.
- Identidade e URL do conteúdo público de origem.
- Distância e similaridade de cosseno, ranks por canal, `ts_rank_cd`, matches em
  título/seção e score RRF.
- Geração e perfil do índice.

Esses sinais são internos e observáveis no inspector, não probabilidades nem parte do
contrato de `/ask`. RRF serve apenas para ordenação. Chunk size, overlap, top-K, pesos e
thresholds são calibrados no Golden Dataset e versionados com o perfil ao qual se aplicam.
O gate também pode usar um sinal negativo de intenção para pedidos explícitos de
implementação ou tutorial genérico. Esse sinal roda somente depois do retrieval e não é
uma allowlist de produtos: nomes publicados continuam sendo reconhecidos pelos próprios
sinais textual e vetorial.

V1 usa um único provedor externo para geração e embeddings. Reranking só pode executar localmente ou pelo provedor já escolhido e apenas se uma avaliação mostrar ganho relevante sobre pgvector e full-text search. Adicionar outro serviço exige revisão explícita do ADR 0002.

## 8. Geração fundamentada

O backend usa FastAPI e orquestra explicitamente o fluxo:

1. Validar pergunta, locale e histórico recebido.
2. Construir uma consulta autônoma para o turno atual, usando somente a última pergunta do
   visitante quando o turno for realmente elíptico.
3. Recuperar candidatos e seus sinais brutos no índice ativo.
4. Aplicar o gate de suporte e selecionar contexto com diversidade limitada por KB Doc.
5. Sem suporte, retornar `insufficient` sem chamar o gerador.
6. Com suporte, pedir ao modelo itens ordenados, cada claim contendo uma única afirmação
   substantiva e IDs de chunks aprovados.
7. Validar todos os IDs, a atomicidade do claim e a autoridade permitida.
8. Hidratar no servidor títulos, excerpts, versões e URLs das citações válidas.
9. Retornar a resposta completa com claims, limitações e cards deduplicados.

O histórico ajuda a interpretar referências como "e nesse projeto?", mas respostas do
assistente nunca entram na consulta de retrieval nem constituem evidência. Uma pergunta
completa ou mudança de assunto usa somente o turno atual. O servidor não persiste o
histórico.

O modelo não cria metadados de citação. Ele apenas referencia chunk IDs apresentados no contexto; todos os demais campos vêm do Postgres. Um claim não pode combinar afirmações independentes no mesmo texto. Se a saída não passar na validação após a tentativa de correção configurada, o backend retorna `insufficient` em vez de entregar claims sem suporte.

### 8.1 Estados da resposta

- `answered`: há evidência suficiente para responder ao núcleo da pergunta.
- `partial`: apenas parte da pergunta possui sustentação e a limitação é declarada.
- `insufficient`: não há evidência suficiente para uma resposta factual útil.

Experiência prática e opinião técnica podem coexistir, desde que a resposta diferencie explicitamente as duas.

Cada claim obedece à seguinte matriz:

| Tipo de claim | Evidência obrigatória | Citações permitidas | Regra |
|---|---|---|---|
| `experience` | Pelo menos um `case_study` | `case_study` e `profile` | Pode afirmar execução, entrega ou liderança; Profile Docs apenas corroboram. |
| `profile` | Pelo menos um `profile` | Somente `profile` | Deve ser apresentado como informação do perfil publicado, não como entrega comprovada. |
| `opinion` | Pelo menos um `essay` | Somente `essay` | Deve ser rotulado como opinião ou tese do João. |

Limitações são itens separados, não claims, não possuem citações e não podem introduzir fatos. Uma pergunta sobre perfil pode ser `answered` apenas com claims `profile`. Uma pergunta que exige experiência prática fica no máximo `partial` quando só existem Profile Docs. `insufficient` é obrigatório quando não existe nenhum claim substantivo válido.

### 8.2 Contrato de `/ask`

Exemplo de request:

```json
{
  "question": "Qual foi sua experiência construindo sistemas RAG?",
  "locale": "pt-BR",
  "history": [
    { "role": "user", "content": "Em quais setores você trabalhou?" },
    { "role": "assistant", "content": "Trabalhei principalmente..." }
  ]
}
```

Exemplo de response:

```json
{
  "status": "answered",
  "answerItems": [
    {
      "kind": "claim",
      "claimType": "experience",
      "text": "João construiu...",
      "citationIds": ["citation-id"]
    }
  ],
  "citations": [
    {
      "id": "citation-id",
      "documentId": "kb-doc-id",
      "documentVersion": 3,
      "documentType": "case_study",
      "title": "RAG para operações corporativas",
      "section": "Resultado",
      "excerpt": "Trecho original em português...",
      "sourceUrl": "/case-studies/rag-operacoes?locale=pt-BR&version=3"
    }
  ]
}
```

O servidor limita tamanho da pergunta, quantidade de turnos e payload total. A API usa JSON em `camelCase` para alinhar com o cliente TypeScript; o adapter HTTP faz a conversão para os modelos internos do backend.

## 9. Portfólio público

O frontend recebe um snapshot agregado por locale, adequado à página única atual. O snapshot inclui uma versão usada como ETag; o backend sempre valida essa versão contra o ponteiro atual no Postgres.

A migração preserva a linguagem visual existente e adiciona estados explícitos de loading, vazio e erro. Uma falha na API não pode produzir dados antigos silenciosamente como se ainda fossem canônicos.

O chat oferece:

- Campo para pergunta livre.
- Prompts sugeridos que chamam `/ask`.
- Histórico visual da visita atual.
- Estado de espera compatível com resposta completa.
- Erros recuperáveis para timeout, indisponibilidade e limite de uso.
- Cards de citação abaixo de cada resposta.
- Acessibilidade por teclado, gerenciamento de foco e anúncio das respostas.

A animação atual pode ser reaproveitada como indicação visual genérica de processamento, mas não pode alegar streaming, modelo específico, scores fictícios ou etapas que não representem o fluxo real.

## 10. Painel admin

O painel é um adapter privado servido pelo backend e voltado a um único proprietário. Não existe cadastro, organização, papéis ou permissão granular no V1.

O painel permite:

- Criar, editar, reordenar e excluir todas as entidades publicadas.
- Editar `pt-BR` e `en-US` lado a lado.
- Fazer upload e ordenar mídia.
- Visualizar erros de validação ou indexação sem alterar a versão pública.
- Detectar tentativa de salvar sobre uma versão já alterada.

Autenticação usa uma credencial de proprietário armazenada como secret, sempre sobre TLS. Operações mutáveis têm proteção contra CSRF e não expõem credenciais ou chaves de modelos ao navegador.

## 11. Migração inicial

Os arquivos atuais do portfólio são uma fonte de importação única, não uma segunda fonte permanente. Antes da importação, claims divergentes entre `pt-BR`, `en-US`, metadados, PDF e RAG simulado devem ser revisados.

A migração deve:

- Preservar slugs e ordem quando forem semanticamente corretos.
- Criar slugs estáveis onde hoje existem apenas IDs numéricos.
- Converter relações de Skills por nome em relações por ID.
- Converter componentes Vue de ícones em chaves serializáveis.
- Separar status de privacidade de projeto de qualquer conceito editorial.
- Importar metadados e alt text das imagens existentes.
- Remover respostas e chunks fictícios do RAG.
- Adaptar o gerador de currículo para usar o snapshot publicado.
- Eliminar imports de dados estáticos depois da verificação de paridade.

## 12. Segurança e operações

Antes da exposição pública, o sistema precisa de:

- Limites por origem, tamanho, frequência e concorrência no `/ask`.
- Limite configurável de gasto diário com o provedor.
- Timeouts e respostas seguras para falhas externas.
- Secrets apenas no backend.
- Logs operacionais sem conteúdo integral das conversas.
- Traces de retrieval e geração no Langfuse com retenção e redação compatíveis com a natureza efêmera da conversa.
- Avaliação versionada por Golden Dataset, cobrindo retrieval, autoridade, citações e estados da resposta sem comparação textual exata.
- Health checks para aplicação e banco.
- Migrations aplicadas de forma controlada antes da nova versão.
- Backups externos criptografados do Postgres e da mídia.
- Restauração testada, não apenas backup configurado.
- Estratégia de rollback do deploy e das migrations compatíveis.
- TLS, monitoramento básico de disponibilidade e renovação automática de certificados.

## 13. Critérios de conclusão

O V1 está pronto quando:

- Todo conteúdo público do portfólio vem do Postgres nos dois locales.
- Não existe fonte estática concorrente para dados de domínio.
- Um admin consegue publicar conteúdo sem commit, e uma falha de indexação preserva a versão anterior.
- Toda pergunta, inclusive prompt sugerido, percorre retrieval e geração reais.
- Todo claim contém uma única afirmação e referencia apenas citações válidas, compatíveis com sua autoridade e navegáveis até a revisão em `pt-BR`.
- Perguntas sem suporte produzem `partial` ou `insufficient`, sem completar lacunas com conhecimento geral.
- Follow-ups funcionam com histórico enviado pelo navegador e nenhuma conversa é persistida no servidor.
- O portfólio funciona em desktop e mobile nos estados de sucesso, vazio, loading e erro.
- O Golden Dataset passa nos idiomas `pt-BR` e `en-US`, com execução comparável registrada no Langfuse.
- Deploy, backup e restauração foram exercitados no droplet alvo.
