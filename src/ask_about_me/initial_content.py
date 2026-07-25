from uuid import UUID

from ask_about_me.case_studies import CaseStudySection, PublishedCaseStudy

INITIAL_CASE_STUDY = PublishedCaseStudy(
    id=UUID("28e81ec7-57e5-4d4d-ad79-064cb9aab3e2"),
    revision=1,
    slug="plataforma-gestao-pessoas-ia",
    title_pt_br="Plataforma de Gestão de Pessoas com IA",
    title_en_us="AI-Powered People Management Platform",
    sections=(
        CaseStudySection(
            position=0,
            heading_pt_br="Contexto",
            heading_en_us="Context",
            body_pt_br=(
                "Sistema corporativo de recrutamento com pipeline Kanban, SLA automático e "
                "scoring semântico de currículos usando Azure OpenAI + pgvector."
            ),
            body_en_us=(
                "Corporate recruitment system with a Kanban pipeline, automatic SLA tracking, "
                "and semantic CV scoring using Azure OpenAI + pgvector."
            ),
        ),
        CaseStudySection(
            position=1,
            heading_pt_br="Problema",
            heading_en_us="Problem",
            body_pt_br=(
                "O processo de requisição de contratação era manual, distribuído entre "
                "formulários, e-mails e planilhas, sem rastreabilidade, fluxo de aprovação ou "
                "dados de SLA."
            ),
            body_en_us=(
                "The hiring requisition process was manual and spread across forms, emails, "
                "and spreadsheets, without traceability, approval flows, or SLA data."
            ),
        ),
        CaseStudySection(
            position=2,
            heading_pt_br="Solução",
            heading_en_us="Solution",
            body_pt_br=(
                "Plataforma multiempresa com aprovação de cargos e requisições, assistente de "
                "formulários, RAG para scoring de currículos, embeddings de transcrições do "
                "Microsoft Teams e integração para agendamento de entrevistas. A aplicação "
                "roda em Kubernetes com Git Flow e CI/CD."
            ),
            body_en_us=(
                "Multi-company platform with role and requisition approvals, a form assistant, "
                "RAG-based CV scoring, Microsoft Teams transcript embeddings, and interview "
                "scheduling integration. The application runs on Kubernetes with Git Flow and "
                "CI/CD."
            ),
        ),
        CaseStudySection(
            position=3,
            heading_pt_br="Resultado",
            heading_en_us="Result",
            body_pt_br=(
                "O scoring de currículos passou a ocorrer em milissegundos em vez de horas de "
                "leitura manual, com Kanban, SLA por estágio e jobs assíncronos em Bull."
            ),
            body_en_us=(
                "CV scoring moved from hours of manual reading to milliseconds, supported by "
                "Kanban, stage-level SLA tracking, and asynchronous Bull jobs."
            ),
        ),
    ),
)
