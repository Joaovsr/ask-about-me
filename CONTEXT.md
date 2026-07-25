# ask-about-me

Sistema público de RAG no portfólio do João que responde perguntas sobre sua trajetória técnica, com citações ancoradas em uma base de conhecimento curada.

## Language

### KB e documentos

**Knowledge Base (KB)**:
Conjunto curado de material indexável sobre o João, derivado do **Conteúdo publicado** e usado para retrieval pelo RAG de Portfólio.
_Avoid_: "base", "corpus" (técnico demais), "conteúdo"

**KB Doc**:
Unidade lógica do **KB**. Pode ser derivado de uma experiência, projeto, perfil, skill, case study ou essay publicado, e tem `doc_type` para definir como o agente deve usá-lo.

**Case Study**:
KB Doc do tipo `case_study`. Relato explicitamente publicado como estudo de um projeto entregue e **fonte de fato** sobre experiência prática do João. Um resumo de projeto não se torna Case Study automaticamente.
_Avoid_: "projeto" (overloaded com a Fictor), "caso"

**Essay**:
KB Doc do tipo `essay`. Opinião defendida por João sobre um tema técnico (ex: "Multi-agente é over-engineering 9/10 vezes"). **Fonte de tese, NÃO de fato sobre projeto entregue.**
_Avoid_: "opinion piece" (estrangeirismo), "post" (LinkedIn é derivativo do essay), "artigo"

**Profile Doc**:
KB Doc do tipo `profile`, derivado de perfil, experiências, projetos, skills, formação ou certificações publicadas. **Fonte de claim auto-declarado.** Tem menos força factual que um **Case Study**.
_Avoid_: "CV stuff", "metadata pessoal"

### Conteúdo e publicação

**Conteúdo publicado**:
Dados canônicos exibidos no portfólio público do João e usados como origem do **KB**, como perfil, experiências, projetos, skills, case studies e essays.
_Avoid_: arquivos estáticos como fonte de verdade permanente

**Conteúdo localizado**:
Versão em `pt-BR` ou `en-US` de um **Conteúdo publicado**. As duas versões pertencem à mesma unidade publicável e devem estar completas antes da publicação.
_Avoid_: tradução automática como fonte de verdade do portfólio

**Painel admin**:
Área privada onde João cria, edita e publica **Conteúdo publicado** sem precisar alterar arquivos manualmente nem fazer commit.
_Avoid_: editar JSON/TypeScript local para atualizar o portfólio

**Publicação imediata**:
Modelo de edição sem rascunho em que uma alteração válida substitui diretamente o **Conteúdo publicado** assim que sua indexação estiver pronta.
_Avoid_: workflow de rascunho e aprovação no V1

**Publicação consistente**:
Garantia de que o portfólio público e o **KB** passam a enxergar a mesma versão de um conteúdo. Se a indexação falhar, a versão publicada anterior continua ativa.
_Avoid_: publicar primeiro e deixar o KB desatualizado

**Indexação automática**:
Processo que transforma **Conteúdo publicado** em **KB Docs**, chunks e embeddings sempre que conteúdo relevante é criado ou alterado.
_Avoid_: reindex manual obrigatório após cada atualização de portfólio

### RAG de Portfólio

**RAG de Portfólio**:
Experiência pública no portfólio do João em que visitantes fazem perguntas sobre sua trajetória técnica e recebem respostas fundamentadas no **KB**.
_Avoid_: "compare_to_role", "segundo cérebro", "chat genérico"

**Pergunta do visitante**:
Pergunta feita por um recrutador, cliente potencial ou visitante do portfólio sobre a trajetória técnica do João.
_Avoid_: "query" quando falando com usuário final

**Recrutador técnico**:
Visitante primário do RAG de Portfólio. Avalia experiência, senioridade, stack, impacto e clareza de comunicação do João.
_Avoid_: "usuário genérico", "dev curioso"

**Cliente potencial**:
Visitante secundário do RAG de Portfólio. Avalia se o João consegue resolver um problema técnico ou de consultoria parecido com o seu.
_Avoid_: "lead" quando falando do papel da pessoa no produto

**Citação**:
Referência exibida junto a uma resposta factual, apontando para o **KB Doc** e trecho que sustentam a afirmação.
_Avoid_: "fonte" quando o objeto específico é o trecho citado

**Afirmação fundamentada**:
Menor afirmação substantiva de uma resposta. Contém uma única ideia de experiência, perfil ou opinião e referencia as **Citações** que a sustentam.
_Avoid_: parágrafo com múltiplos claims apoiado por uma citação genérica

**Card de citação**:
Apresentação visível de uma **Citação** abaixo da resposta no **Chat embutido**, com documento, trecho e contexto suficiente para o visitante confiar na evidência.
_Avoid_: esconder a evidência apenas em footnote no V1

**Evidência insuficiente**:
Estado em que o **KB** não sustenta uma resposta factual sobre a trajetória técnica do João. O RAG de Portfólio deve declarar a limitação e, quando útil, responder apenas parcialmente com **Citações** disponíveis.
_Avoid_: inferência sem citação, completar lacunas com conhecimento geral

**Experiência prática**:
Afirmação sobre algo que João executou, entregou ou liderou. Deve ser sustentada preferencialmente por **Case Studies** ou, com menor força, por **Profile Docs**.
_Avoid_: usar **Essay** como prova de entrega

**Opinião técnica**:
Tese ou posicionamento do João sobre tecnologia, arquitetura, IA ou forma de trabalho. Deve ser sustentada por **Essays** e apresentada como opinião, não como fato de entrega.
_Avoid_: tratar tese como experiência prática

**Chat embutido**:
Forma principal do RAG de Portfólio no site: uma seção interativa dentro do portfólio do João, não um app separado nem um iframe genérico.
_Avoid_: "demo externo", "produto separado"

**Prompt sugerido**:
Pergunta pronta exibida no estado inicial do **Chat embutido** para ajudar o visitante a começar uma conversa útil.
_Avoid_: "botão de demo" quando a ação inicia conversa real

**Fluxo real de RAG**:
Caminho executado para toda pergunta do **Chat embutido**: receber a pergunta, recuperar evidências no **KB**, gerar resposta e exibir **Citações**. Também se aplica aos **Prompts sugeridos**.
_Avoid_: resposta pré-cozida, demo cenográfica

**Busca única no KB**:
Estratégia de retrieval do V1: uma única busca sobre o **KB** inteiro, retornando chunks com `doc_type` para que a resposta diferencie **Case Study**, **Essay** e **Profile Doc**.
_Avoid_: tools separadas por tipo de documento no V1

**Idioma canônico do KB**:
Idioma usado como evidência indexada pelo V1. É `pt-BR`, mesmo quando a pergunta e a resposta estão em `en-US`.
_Avoid_: duplicar o índice por idioma antes de medir necessidade

**Conversa efêmera**:
Histórico temporário do **Chat embutido**, mantido apenas no estado do navegador durante a visita atual. Não exige conta, cookie de sessão ou persistência longa no V1.
_Avoid_: sessão persistente, analytics de conversa como requisito de V1

**Resposta completa**:
Resposta do RAG de Portfólio entregue ao frontend de uma vez, após retrieval e geração. No V1 substitui streaming de tokens e tool calls visíveis.
_Avoid_: streaming como requisito de V1

**Golden Dataset**:
Conjunto versionado de perguntas e expectativas usado como gate de qualidade do **RAG de Portfólio**. Registra evidências esperadas, estado da resposta, tipos de claim e regras de citação sem exigir uma redação idêntica do modelo.
_Avoid_: snapshot de respostas literais, coleção informal de prompts

## Relationships

- Um **KB Doc** é exatamente um de: **Case Study** | **Essay** | **Profile Doc**
- **Conteúdo publicado** é a fonte de verdade do portfólio público e do **KB**
- Todo **Conteúdo publicado** textual tem **Conteúdo localizado** em `pt-BR` e `en-US`
- O **Painel admin** altera **Conteúdo publicado** por **Publicação imediata**, não arquivos estáticos do frontend
- **Publicação consistente** e **Indexação automática** mantêm o **KB** sincronizado com o **Conteúdo publicado**
- Uma falha de indexação não substitui a versão publicada anterior
- Força factual por tipo: **Case Study** > **Profile Doc** > **Essay** (essay sustenta tese, não fato de entrega)
- Uma **Pergunta do visitante** pode recuperar N **KB Doc** relevantes
- O **Recrutador técnico** é o visitante primário; o **Cliente potencial** é secundário
- Cada **Afirmação fundamentada** deve ter **Citações** compatíveis com seu tipo de evidência
- No V1, **Citações** aparecem como **Cards de citação** abaixo da resposta
- Com **Evidência insuficiente**, o RAG de Portfólio deve declarar a limitação em vez de inferir
- **Experiência prática** e **Opinião técnica** podem coexistir na resposta, mas devem ser rotuladas de forma clara
- No V1, retrieval usa **Busca única no KB** com `doc_type` por chunk
- No V1, `pt-BR` é o **Idioma canônico do KB**; a resposta usa o idioma escolhido pelo visitante
- O RAG de Portfólio aparece como **Chat embutido** no portfólio, iniciado por **Prompts sugeridos**
- Todo **Prompt sugerido** deve executar o **Fluxo real de RAG**, não retornar resposta pré-cozida
- No V1, o histórico do **Chat embutido** é uma **Conversa efêmera**
- No V1, o backend retorna uma **Resposta completa** em vez de streaming
- O **Golden Dataset** avalia retrieval e geração separadamente e bloqueia o lançamento quando os critérios críticos não passam

## Example dialogue

> **Recrutador:** "Fale do seu trabalho com RAG corporativo."
> **Bot (correto):** Cita **Case Studies** ("no projeto cobrança eu construí...") + **Profile Doc** ("o perfil publicado lista RAG como expertise"). Se também referenciar um **Essay**, marca explicitamente: "tenho uma tese sobre isso em...".
> **Bot (errado):** Cita um **Essay** como se fosse projeto entregue.

## Flagged ambiguities

- **"work" em `search_my_work`** — sobrecarregado: o tool busca o KB inteiro, mas "work" sugere só projetos. Resolução: o tool continua se chamando `search_my_work` (não renomeia), mas retorna chunks **tagueados com `doc_type`**, e o system prompt instrui o agente a diferenciar fato vs tese vs auto-declaração no output.
