# Plano de desenvolvimento do V1

Este plano implementa a [especificação vigente](SPEC.md) em fatias verticais. A ordem prioriza validar cedo as interfaces entre portfólio, conteúdo, retrieval e geração, sem construir antecipadamente toda a infraestrutura de cada camada.

Não há estimativa de calendário nesta versão. Cada fatia deve ser refinada em issues depois que a anterior reduzir suas principais incertezas.

## Princípios de execução

- Entregar um caminho ponta a ponta antes de ampliar o modelo de dados.
- Manter as regras atrás dos módulos de Conteúdo publicado, Knowledge Base e RAG de Portfólio.
- Testar os módulos pelas mesmas interfaces usadas pelos adapters.
- Usar Postgres real em testes de integração; não substituir pgvector ou transações por mocks de repositório.
- Usar um adapter determinístico do provedor nos testes automatizados.
- Não manter arquivos estáticos e banco como fontes concorrentes depois da migração de uma entidade.
- Validar toda a pipeline localmente antes de provisionar infraestrutura em nuvem.
- Tratar avaliação de retrieval como requisito de produto, não como observabilidade opcional.

## Visão das fatias

| Ordem | Fatia | Resultado observável | Porte inicial |
|---:|---|---|---|
| 0 | Base executável e spike de modelos | Contratos executáveis e provedor inicial escolhido com conteúdo real | M |
| 1 | Primeira resposta citada | Uma pergunta real percorre Vue, FastAPI, pgvector e volta com citação | L |
| 2 | Primeiro ciclo de publicação | Uma edição no admin altera portfólio e RAG sem inconsistência | L |
| 3 | Semântica de evidência | Case Study, Profile Doc e Essay produzem respostas seguras | M |
| 4A | Perfil, experiências e projetos | Seções principais passam a consumir Postgres | L |
| 4B | Skills, formação e currículo | Restante do portfólio e PDF deixam os arquivos estáticos | L |
| 4C | Case Studies, Essays e citações | Fontes ganham páginas públicas e navegação estável | M |
| 5 | Conversa completa | Chat substitui integralmente a simulação atual | L |
| 6 | Qualidade de retrieval | KB e Golden Dataset atingem o gate de lançamento | M |
| 7 | Operação segura | Deploy, limites, backup e restauração funcionam no droplet | L |
| 8 | Cutover e lançamento | Domínio serve a nova arquitetura e o V1 está publicamente disponível | M |

Os portes são relativos e devem ser revistos durante o refinamento. `L` não deve virar uma única pull request; os critérios de saída definem o fechamento da fatia, não o tamanho de cada mudança.

## Fatia 0: base executável e spike de modelos

### Objetivo

Criar o mínimo de fundação compartilhada e remover a incerteza sobre o único provedor externo antes que ela contamine retrieval, schema e custos.

### Backend

- Criar projeto Python com FastAPI, configuração tipada, lint, typecheck e testes.
- Criar ambientes locais reproduzíveis para FastAPI e Postgres com pgvector.
- Configurar migrations desde o primeiro schema.
- Implementar `/health` com checks separados de processo e banco.
- Definir modelos HTTP iniciais para `/ask` e snapshot público usando JSON em `camelCase`.
- Criar interfaces iniciais dos módulos Conteúdo publicado, Knowledge Base e RAG de Portfólio.
- Criar interface estreita para geração e embeddings, com adapters de produção e teste determinístico.
- Configurar testes de integração contra Postgres descartável.

### Portfólio

- Criar um client HTTP dedicado em vez de chamadas `fetch` espalhadas pelos componentes.
- Criar tipos dos contratos públicos e fixtures para desenvolvimento isolado.
- Definir configuração de origem da API para desenvolvimento e produção same-origin.

### Ambiente local

- Subir Postgres com pgvector por Docker Compose e volume local persistente.
- Incluir healthcheck do banco e criação da extensão por migration.
- Fornecer configuração de exemplo sem secrets e comandos curtos para iniciar, testar e encerrar o ambiente.
- Executar FastAPI e portfólio localmente sem depender de DNS, TLS ou serviços de nuvem.

### Spike do provedor

- Preparar um conjunto pequeno com um Case Study, um Profile Doc e um Essay reais em `pt-BR`.
- Preparar perguntas diretas, em inglês, sem evidência e com mistura de opinião e experiência.
- Comparar provedores que ofereçam geração e embeddings na mesma dependência contratual.
- Medir recuperação das fontes esperadas, qualidade em `pt-BR`, retrieval cross-language, latência e custo.
- Confirmar suporte confiável ao formato estruturado da resposta.
- Escolher o provedor e modelos iniciais sem tornar top-K, chunk size ou prompt contratos permanentes.

### Critério de saída

Backend, banco e portfólio executam localmente; os contratos compilam nos dois repositórios; migrations e testes rodam em CI; o provedor inicial foi escolhido a partir do material representativo da KB usado no spike.

## Fatia 1: primeira resposta citada

### Objetivo

Provar a arquitetura completa com um único conteúdo e um único caminho feliz antes de criar o CMS inteiro.

### Conteúdo e KB

- Criar o schema mínimo para uma entidade Case Study bilíngue e sua versão.
- Criar schemas para KB Doc e chunk com `doc_type`, origem e embedding.
- Adicionar um Case Study real por seed versionado.
- Implementar projeção determinística do Case Study em um KB Doc `case_study` em `pt-BR`.
- Implementar chunking inicial e embeddings.
- Implementar `search_my_work` combinando pgvector e full-text search em português.

### RAG

- Implementar o fluxo explícito retrieve-then-generate.
- Instruir o modelo a usar apenas evidências recuperadas para claims sobre João.
- Receber itens ordenados com claims atômicos que referenciam chunk IDs, sem aceitar metadados de citação produzidos pelo modelo.
- Validar que cada claim contém uma afirmação, que todas as citações têm autoridade permitida e que seus IDs pertencem aos chunks recuperados.
- Hidratar os cards no servidor a partir do Postgres.
- Implementar o response `answered` com `answerItems` e cards deduplicados.
- Expor `POST /ask` com limites iniciais de payload e timeout.
- Aplicar localmente um limite mínimo de concorrência e gasto diário antes da primeira chamada paga.

### Portfólio

- Fazer um prompt sugerido chamar o endpoint real.
- Renderizar a resposta completa e um card de citação no componente visual existente.
- Remover desse caminho qualquer label de GPT-4, streaming ou score fictício.
- Adicionar loading e erro básico sem redesenhar toda a conversa.

### Verificação

- Teste de integração da projeção até a busca.
- Teste do RAG com provider fake, incluindo autoridade, hidratação, claim com duas afirmações, fonte de tipo indevido e citação desconhecida.
- Teste de contrato entre response FastAPI e tipos TypeScript.
- Smoke test local usando os mesmos contratos da suíte automatizada.

### Critério de saída

Um visitante aciona um prompt no portfólio local e recebe uma resposta gerada a partir do Case Study real, com trecho e identidade de origem válidos.

## Fatia 2: primeiro ciclo de publicação

### Objetivo

Provar que Postgres é a fonte de verdade e que uma publicação nunca deixa portfólio e KB em versões diferentes.

### Backend e admin

- Expor leitura pública do Case Study por locale.
- Criar o primeiro formulário admin servido pelo backend.
- Proteger o admin com credencial de proprietário, TLS e CSRF.
- Validar presença de `pt-BR` e `en-US` antes da publicação.
- Implementar controle otimista por versão.
- Persistir uma revisão imutável a cada publicação e mover o ponteiro atual na mesma transação.
- Preparar projeção, chunks e embeddings antes da transação de publicação.
- Confirmar revisão, ponteiro atual, versão do snapshot e derivados da KB na mesma operação transacional.
- Manter a versão anterior quando embedding ou commit falhar.
- Implementar exclusão com remoção consistente dos derivados.
- Implementar reindexação de recuperação vinculada à versão do snapshot, com geração paralela e troca condicional do índice ativo.

### Portfólio

- Exibir o Case Study a partir do endpoint público.
- Usar versão ou ETag do snapshot para invalidação de cache.
- Exibir estado de erro em vez de recorrer silenciosamente ao conteúdo compilado.

### Verificação

- Injetar falha de embedding e confirmar que conteúdo e resposta antigos permanecem ativos.
- Simular duas edições concorrentes e rejeitar a segunda versão obsoleta.
- Alterar um fato pelo admin e confirmar sua mudança no conteúdo público e em uma nova resposta.
- Excluir o conteúdo e confirmar que ele não aparece mais no portfólio nem na busca.
- Interromper uma reindexação completa e confirmar que a geração anterior continua ativa.
- Publicar durante uma reindexação e confirmar que a geração baseada no snapshot antigo não pode se tornar ativa.

### Critério de saída

Uma edição feita apenas pelo painel altera de forma consistente o conteúdo exibido e a evidência usada pelo RAG; falhas preservam a versão anterior.

## Fatia 3: semântica de evidência

### Objetivo

Implementar a principal promessa de confiança do produto antes de importar toda a KB.

### Conteúdo e projeção

- Adicionar Profile, Experience, Project e Essay suficientes para exercitar os três `doc_type`.
- Projetar Profile, Experience e Project como Profile Docs.
- Projetar Essay como `essay`.
- Permitir relação explícita entre Project e Case Study sem promover o Project a Case Study.

### RAG

- Implementar os estados `answered`, `partial` e `insufficient`.
- Implementar claims `experience`, `profile` e `opinion`, além de itens separados de limitação, conforme a matriz da especificação.
- Exigir Case Study para claim `experience`, Profile Doc para `profile` e Essay para `opinion`.
- Limitar a `partial` perguntas de experiência prática sustentadas apenas por Profile Docs.
- Recuperar evidências novamente em toda pergunta, inclusive follow-up.
- Garantir que histórico do assistente nunca seja tratado como evidência.
- Validar que respostas sem suporte declaram a limitação.

### Avaliação inicial

- Criar casos dourados de experiência sustentada por Case Study.
- Criar casos sustentados apenas por Profile Doc.
- Criar perguntas sobre opinião sustentadas por Essay.
- Criar perguntas mistas que exigem rótulos claros.
- Criar perguntas parcialmente respondíveis e totalmente sem suporte.
- Criar saídas inválidas com dois claims no mesmo texto e com fontes de autoridade incompatível.
- Executar cada categoria em `pt-BR` e `en-US`.

### Critério de saída

Os casos dourados demonstram a hierarquia de evidência; nenhuma resposta usa Essay como prova de entrega; toda citação referencia um resultado recuperado; perguntas sem suporte não recebem facts inventados.

## Fatia 4A: perfil, experiências e projetos

### Objetivo

Migrar primeiro as seções públicas com maior valor para recrutadores e provar o snapshot agregado do portfólio.

### Migração

- Auditar divergências atuais entre locales, metadados HTML, PDF e respostas simuladas.
- Resolver claims conflitantes antes da importação, incluindo tempo de experiência, cargo e domínio público.
- Modelar Profile, Experience, Project e mídia com ordem explícita.
- Preservar slugs existentes quando corretos.
- Separar privacidade do projeto de estado editorial.
- Importar imagens existentes com alt text localizado.

### APIs e admin

- Incluir essas entidades no snapshot público por locale.
- Expandir o admin com criação, edição, ordenação, exclusão e upload de mídia.
- Aplicar a publicação consistente a todos os tipos indexáveis.

### Portfólio

- Migrar Hero, About, Projects, modal de projeto e Experience para o client de conteúdo.
- Derivar métricas do snapshot carregado, não de imports estáticos.
- Adicionar loading, vazio e erro por seção sem desmontar a página inteira.
- Remover os dados estáticos dessas entidades no mesmo conjunto de mudanças que ativa o banco.

### Critério de saída

Perfil, experiências e projetos são editáveis pelo admin, bilíngues, indexáveis e exibidos sem imports concorrentes de `src/data`.

## Fatia 4B: skills, formação e currículo

### Objetivo

Concluir a migração dos dados estruturados e eliminar a dependência do PDF em módulos estáticos.

### Migração

- Criar slugs para Certifications e Skills que hoje usam apenas IDs.
- Substituir relações entre Skills por nome por relações entre IDs.
- Mapear componentes Vue de ícone para chaves serializáveis conhecidas pelo frontend.
- Modelar Education e Certification com ordem e campos localizados.
- Projetar cada Skill, Education e Certification como um Profile Doc ligado a uma única revisão de origem.

### APIs e admin

- Incluir Skills, Education e Certifications no snapshot público por locale.
- Criar formulários admin para publicação, ordenação e exclusão dessas entidades.
- Validar as duas localizações e aplicar a mesma barreira consistente de indexação.

### Portfólio

- Migrar Skills Graph e Education para o snapshot público.
- Adaptar o gerador de currículo para receber o snapshot já carregado.
- Preservar a geração de PDF nos dois idiomas.
- Tratar indisponibilidade de conteúdo antes de iniciar o download.
- Remover os módulos estáticos restantes e chaves de locale que duplicavam conteúdo de domínio.

### Critério de saída

Skills, Education e Certifications são administráveis nos dois locales; todas as seções e o currículo usam exclusivamente o Conteúdo publicado; relações do grafo continuam estáveis após renomear uma Skill.

## Fatia 4C: Case Studies, Essays e citações

### Objetivo

Dar às evidências mais ricas uma superfície pública estável e tornar citações navegáveis.

### Backend e admin

- Completar os editores de Case Study e Essay nos dois locales.
- Suportar seções ordenadas para que citações preservem contexto.
- Expor slugs e URLs públicas versionadas em `pt-BR` por tipo de conteúdo.
- Manter leitura das revisões imutáveis enquanto a entidade estiver publicada.
- Manter identidade da citação vinculada à versão publicada.

### Portfólio

- Criar views públicas para Case Studies e Essays.
- Ajustar o router para preservar deep links em vez de redirecionar toda rota para `/`.
- Implementar abertura da fonte a partir do card de citação.
- Indicar a revisão e manter o excerpt e a fonte canônica em `pt-BR` quando a interface estiver em inglês.

### Critério de saída

Todo card leva a uma fonte pública estável e ao contexto correto; editar uma fonte cria uma nova versão sem confundir citações novas com a versão anterior.

## Fatia 5: conversa completa

### Objetivo

Substituir integralmente a simulação atual por uma experiência de chat honesta, acessível e resiliente.

### Estado e contrato

- Migrar Suggested Prompts para o Conteúdo publicado com slug, ordem e as duas localizações.
- Incluir Suggested Prompts no snapshot público sem projetá-los na KB.
- Criar no admin as operações de criação, edição, ordenação e exclusão de Suggested Prompts.
- Implementar input livre e submissão por teclado.
- Manter histórico apenas no estado do navegador.
- Enviar ao backend um histórico limitado em cada nova pergunta.
- Limitar quantidade de turnos e tamanho total tanto no frontend quanto no backend.
- Limpar a conversa ao recarregar a página.
- Manter o locale escolhido como idioma explícito da resposta.

### Interface

- Fazer todos os prompts sugeridos executarem `/ask`.
- Renderizar múltiplos turnos e seus respectivos cards.
- Exibir os estados `partial` e `insufficient` sem tratá-los como erro técnico.
- Implementar timeout, retry seguro, limite de uso e indisponibilidade.
- Permitir cancelamento da requisição em andamento.
- Reaproveitar a animação do pipeline apenas como feedback genérico e verdadeiro.
- Remover chunks, respostas e fontes fictícias.
- Validar layout e interação em desktop e mobile.
- Implementar foco, live regions, labels e navegação por teclado.

### Critério de saída

Perguntas livres, prompts e follow-ups usam o fluxo real; refresh remove a conversa; não há armazenamento servidor; estados de sucesso e falha são utilizáveis em desktop, mobile e teclado.

## Fatia 6: qualidade de retrieval e KB de lançamento

### Objetivo

Transformar retrieval quality em um gate verificável de lançamento, sem adotar complexidade apenas por sinal técnico.

### KB de lançamento

- Importar e revisar o conjunto mínimo de Case Studies, Essays e Profile Docs necessário para cobrir as perguntas prioritárias.
- Fazer revisão de NDA e LGPD antes de indexar conteúdo corporativo.
- Remover duplicações e claims contraditórios entre entidades.
- Revisar a qualidade das duas localizações públicas.

### Avaliação

- Versionar o Golden Dataset com pergunta, locale, intenção, evidências esperadas, estado da resposta, tipos de claim e regras de citação.
- Expandir o Golden Dataset com perguntas factuais diretas e indiretas.
- Incluir perguntas em inglês contra o índice em português.
- Incluir follow-ups, negações, termos técnicos, perguntas sem evidência e tentativas de prompt injection.
- Medir se a fonte esperada aparece nos resultados antes de avaliar a geração.
- Medir validade das citações, cobertura factual, recusa correta, latência e custo.
- Executar e comparar as avaliações versionadas no Langfuse, sem usar igualdade textual como critério de correção.
- Registrar regressões como testes ou casos de avaliação antes de ajustar o sistema.

### Tuning

- Medir separadamente a contribuição de pgvector e full-text search sem remover a busca híbrida aprovada do V1.
- Ajustar chunking, top-K, pesos e threshold de evidência a partir dos erros observados.
- Adicionar reranking local ou pelo provider escolhido apenas se o ganho superar claramente custo e latência; outro serviço exige revisão do ADR 0002.
- Ajustar embeddings multilíngues ou normalização da pergunta mantendo o índice em `pt-BR`; qualquer índice bilíngue exige revisão explícita do ADR 0006.

### Critério de saída

Todas as perguntas críticas do Golden Dataset recuperam evidência adequada ou recusam corretamente; citações inválidas são zero; latência e custo respeitam os limites definidos no spike, com uma execução comparável registrada no Langfuse.

## Fatia 7: operação segura

### Objetivo

Levar a stack já validada localmente ao droplet e torná-la segura para ser a fonte canônica do portfólio e expor chamadas pagas à internet.

### Deploy

- Provisionar o droplet somente depois do gate local de qualidade da Fatia 6.
- Adaptar os containers locais para FastAPI, Postgres, reverse proxy e build Vue sem mudar os contratos validados.
- Criar staging protegido, configurar TLS e verificar a precedência das rotas de backend sobre o fallback da SPA.
- Automatizar migrations antes da troca da versão da aplicação.
- Validar a stack em staging e então criar produção com rollback documentado.
- Coordenar artefatos dos dois repositórios sem acoplá-los em um monorepo.

### Proteção

- Implementar limites de frequência, payload e concorrência sem Redis.
- Implementar teto diário de gasto e resposta clara quando esgotado.
- Configurar timeouts, retries limitados e circuit breaking do provedor.
- Proteger o admin contra brute force e registrar tentativas sem secrets.
- Revisar CORS, CSRF, headers de segurança e tratamento de erros.
- Não registrar perguntas ou respostas integrais nos logs operacionais.

### Durabilidade

- Automatizar backup criptografado de Postgres e mídia para destino externo ao droplet.
- Definir retenção e monitorar falhas de backup.
- Restaurar um backup em ambiente limpo e documentar o tempo e os passos.
- Testar migrations de avanço e recuperação compatíveis com o rollback suportado.

### Observabilidade

- Monitorar disponibilidade, latência, erros, espaço em disco e saúde do banco.
- Registrar request IDs, status, duração e consumo estimado sem conteúdo de conversa.
- Instrumentar retrieval e geração no Langfuse com versão de prompt, modelo, configuração, tokens, custo e latência por etapa.
- Definir retenção e redação de dados para impedir que observabilidade se torne analytics persistente de visitantes; avaliações usam apenas o Golden Dataset curado ou sanitizado.
- Configurar alertas para indisponibilidade, disco, backup e teto de gasto.

### Critério de saída

Deploy e rollback foram exercitados; limites bloqueiam abuso simulado; um backup foi restaurado; falhas relevantes geram alerta; nenhuma chave ou conversa integral aparece no frontend ou nos logs.

## Fatia 8: cutover e lançamento

### Objetivo

Transferir o domínio do GitHub Pages para o droplet sem perda de conteúdo ou rotas e realizar o soft launch.

### Preparação

- Executar importação final e comparar visualmente todos os dados nos dois locales.
- Validar currículo, mídia, deep links, metadata e compartilhamento social.
- Executar a suíte de avaliação e os smoke tests no ambiente de produção.
- Revisar conteúdo quanto a NDA, dados pessoais e claims desatualizados.
- Preparar runbook de incidentes, restauração e teto de gasto.

### Cutover

- Reduzir TTL de DNS antes da mudança.
- Apontar o domínio para o droplet e validar certificado.
- Desativar o deploy concorrente do GitHub Pages depois da confirmação.
- Verificar `/`, conteúdo profundo, `/ask`, `/admin` e assets após propagação.
- Manter caminho de rollback durante a janela definida.

### Lançamento

- Fazer soft launch para a rede e LinkedIn.
- Monitorar erros, custo, latência e perguntas que resultam em evidência insuficiente.
- Transformar falhas reais em melhorias de conteúdo ou novos casos de avaliação.

### Critério de saída

O domínio público atende a nova arquitetura, o GitHub Pages não compete pelo deploy, os caminhos críticos passam em produção e o sistema opera dentro dos limites definidos.

## Estratégia de testes

| Nível | Responsabilidade |
|---|---|
| Unidade | Projeção de conteúdo, regras de autoridade, validação de estado e transformações puras. |
| Integração | Migrations, queries, pgvector, full-text search, transações de publicação e exclusão. |
| Contrato | OpenAPI, aliases `camelCase`, fixtures compartilhadas e compatibilidade do client Vue. |
| RAG determinístico | Orquestração, limites e citações usando provider fake. |
| Avaliação | Retrieval e respostas com modelos reais sobre material representativo da KB. |
| End-to-end | Publicar, exibir, perguntar, citar e abrir a fonte localmente; repetir em staging e produção apenas na Fatia 7. |

Avaliações com modelos reais não substituem testes determinísticos. Testes determinísticos não substituem a avaliação de retrieval.

## Paralelismo seguro

Depois da Fatia 1:

- A auditoria e tradução do conteúdo atual podem avançar em paralelo à Fatia 2.
- O desenho visual do chat pode avançar com fixtures do contrato `/ask`.
- Scripts e runbooks de infraestrutura podem avançar, mas nenhum recurso de nuvem é pré-requisito antes da Fatia 7.
- A escrita de Case Studies e Essays pode avançar sem bloquear o CMS completo.

Não devem avançar em paralelo sem contrato fechado:

- Migração das seções Vue e formato do snapshot público.
- Cards de citação e schema de `/ask`.
- Admin de uma entidade e suas regras de publicação/indexação.
- Cutover de DNS e restauração comprovada.

## Riscos que alteram o plano

| Risco | Sinal antecipado | Resposta planejada |
|---|---|---|
| Um provedor único não entrega embeddings cross-language suficientes | Perguntas em inglês não recuperam fontes em português no spike | Avaliar normalização ou tradução da pergunta dentro do mesmo provider; se ainda falhar, revisar explicitamente os ADRs 0002 e 0006 antes de mudar provider ou índice. |
| Publicação síncrona demora demais | Save do admin excede o limite definido nos testes locais | Reduzir trabalho afetado e otimizar o provider; qualquer job ou estado pendente exige um ADR que substitua os ADRs 0004 e 0007. |
| O modelo mistura opinião e experiência | Casos dourados usam Essay como prova de entrega | Reforçar estrutura da saída e validação; não aumentar quantidade de agentes. |
| Migração revela claims divergentes | `pt-BR`, `en-US`, PDF e dados estruturais não concordam | Resolver conteúdo antes de importar; não automatizar a escolha de uma versão. |
| Conteúdo client-side prejudica descoberta | Crawlers não indexam páginas de fonte | Medir páginas públicas e adicionar prerender ou SSR apenas onde necessário. |
| Mídia local ameaça recuperação | Restore não recompõe screenshots e avatar | Incluir mídia no mesmo ensaio de backup e restauração do banco. |

## Definition of Done do V1

A conclusão global é determinada pelos critérios da [seção 13 da especificação](SPEC.md#13-critérios-de-conclusão). Nenhuma fatia está concluída apenas porque seu código foi integrado; seus critérios precisam passar no ambiente indicado e a documentação afetada deve refletir o comportamento entregue.
