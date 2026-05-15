# ask-about-me

Bot conversacional público que responde perguntas de recrutadores e clientes potenciais sobre a trajetória técnica do João, com citações ancoradas em uma base de conhecimento curada.

## Language

### KB e documentos

**Knowledge Base (KB)**:
Conjunto curado de ~25 documentos em pt-BR sobre o João, indexado para retrieval.
_Avoid_: "base", "corpus" (técnico demais), "conteúdo"

**KB Doc**:
Uma unidade lógica do KB (um arquivo `.md` em `data/kb/`). Tem `doc_type` que define como o agente a usa.

**Case Study**:
KB Doc do tipo `case_study`. Relato de um projeto entregue. **Fonte de fato** — vale como evidência de "atende requisito" em `compare_to_role`.
_Avoid_: "projeto" (overloaded com a Fictor), "caso"

**Essay**:
KB Doc do tipo `essay`. Opinião defendida por João sobre um tema técnico (ex: "Multi-agente é over-engineering 9/10 vezes"). **Fonte de tese, NÃO de evidência de fit.** Em `compare_to_role` aparece como "tese", nunca como prova de competência.
_Avoid_: "opinion piece" (estrangeirismo), "post" (LinkedIn é derivativo do essay), "artigo"

**Profile Doc**:
KB Doc do tipo `profile`. CV.md, skills-matrix.md, LinkedIn posts curtos. **Fonte de claim auto-declarado.** Vale como evidência fraca em `compare_to_role` (sustenta ✅ se um `case_study` confirma; sozinho vira ⚠️ parcial).
_Avoid_: "CV stuff", "metadata pessoal"

### compare_to_role

**Job Description (JD)**:
Texto bruto da vaga, colado pelo recrutador no chat. Input opaco — não-confiável, possivelmente longo, possivelmente em qualquer idioma.

**Requirement**:
Unidade atômica de avaliação de fit. Extraído pelo Claude da **JD** com schema Pydantic forçado. Granularidade média: agrupado por **área** (Python, AWS, Liderança, Inglês), com atributos estruturados (`years_min`, `team_size`, `services[]`) + `must_have: bool` + `raw_quote: str` (trecho literal da JD que originou).
_Avoid_: "skill" (mais atômico que Requirement), "bullet" (formato, não conceito)

**raw_quote**:
Trecho literal da JD que originou o **Requirement**. Renderizado no output ("a JD pede: '...'"). Garante auditabilidade — o recrutador confere que o agente leu a vaga, não alucinou requisitos.

## Relationships

- Um **KB Doc** é exatamente um de: **Case Study** | **Essay** | **Profile Doc**
- Em `compare_to_role`, força de evidência por tipo: **Case Study** > **Profile Doc** > **Essay** (essay nunca prova fit)
- Uma **JD** produz N **Requirement** (esperado: 5-8 por JD típica)
- Cada **Requirement** tem exatamente um `raw_quote` (rastreabilidade 1:1 com a JD)

## Example dialogue

> **Recrutador:** "Fale do seu trabalho com RAG corporativo."
> **Bot (correto):** Cita **Case Studies** ("no projeto cobrança eu construí…") + **Profile Doc** ("skills-matrix lista RAG como expertise"). Se também referenciar um **Essay**, marca explicitamente: "tenho uma tese sobre isso em…".
> **Bot (errado):** Cita um **Essay** como se fosse projeto entregue.

## Flagged ambiguities

- **"work" em `search_my_work`** — sobrecarregado: o tool busca o KB inteiro, mas "work" sugere só projetos. Resolução: o tool continua se chamando `search_my_work` (não renomeia), mas retorna chunks **tagueados com `doc_type`**, e o system prompt instrui o agente a diferenciar fato vs tese vs auto-declaração no output.
