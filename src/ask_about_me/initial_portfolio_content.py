# ruff: noqa: E501

from ask_about_me.portfolio_content import (
    PORTFOLIO_SNAPSHOT_ID,
    LocalizedPortfolioContent,
    PublishedPortfolioSnapshot,
)


def _profile(
    *,
    location: str,
    tagline: str,
    about_lead: str,
    about_body: str,
    differentials: list[str],
    open_to: str,
    languages: list[dict[str, str]],
) -> dict[str, object]:
    return {
        "name": "João Vinicius Rodrigues",
        "nameShort": "João Vinicius",
        "email": "joaovinicius2525@gmail.com",
        "avatar": "/avatar.jpg",
        "brand": "// neural-lab",
        "careerStart": "2022-09",
        "github": "https://github.com/joaovsr",
        "linkedin": "https://www.linkedin.com/in/joaovinirodrigues/",
        "role": "Software Engineer",
        "roleSub": "Full Stack",
        "location": location,
        "tagline": tagline,
        "aboutLead": about_lead,
        "aboutBody": about_body,
        "differentials": differentials,
        "openTo": open_to,
        "languages": languages,
    }


_EXPERIENCE_SHARED = (
    {
        "slug": "fictor",
        "company": "Fictor Alimentos",
        "startDate": "2025-03",
        "finishDate": "2026-04",
        "skills": [
            "Flutter",
            "React",
            "Node.js",
            "TypeScript",
            "RAG",
            "Azure OpenAI",
            "pgvector",
            "LLM",
            "Docker",
            "Kubernetes",
            "CI/CD",
            "Azure AD",
        ],
    },
    {
        "slug": "atalaia",
        "company": "Atalaia Alimentos",
        "startDate": "2022-09",
        "finishDate": "2025-03",
        "skills": [
            "Python",
            "RPA",
            "Selenium",
            "Pandas",
            "ETL",
            "Metabase",
            "Power BI",
            "Django",
            "SQL",
            "LLMs",
        ],
    },
    {
        "slug": "inss",
        "company": "INSS",
        "startDate": "2019-08",
        "finishDate": "2020-05",
        "skills": ["Suporte Técnico", "Hardware", "Redes", "Infraestrutura"],
    },
)


def _experiences(
    *, roles: tuple[str, str, str], descriptions: tuple[str, str, str]
) -> tuple[dict[str, object], ...]:
    return tuple(
        {**shared, "role": role, "description": description}
        for shared, role, description in zip(_EXPERIENCE_SHARED, roles, descriptions, strict=True)
    )


_PROJECT_SHARED = (
    {
        "slug": "super_app",
        "technologies": [
            "Flutter",
            "NestJS",
            "React",
            "TypeScript",
            "Kubernetes",
            "RabbitMQ",
            "Azure AD",
        ],
        "status": "private",
        "images": ["/projects/super-app-mobile.jpeg"],
    },
    {
        "slug": "fictor360_pbi",
        "technologies": ["Power BI Embedded", "NestJS", "TypeScript", "Azure AD", "RLS", "API"],
        "status": "private",
        "images": ["/projects/fictor360.jpeg"],
    },
    {
        "slug": "hr_platform",
        "technologies": [
            "NestJS",
            "React",
            "PostgreSQL",
            "pgvector",
            "Azure OpenAI",
            "Azure AD",
            "Bull",
            "Microsoft Teams",
            "Kubernetes",
        ],
        "status": "private",
        "images": ["/projects/hr-platform.png", "/projects/hr-platform-2.png"],
    },
    {
        "slug": "fictor360_ai",
        "technologies": [
            "LangChain",
            "Azure OpenAI",
            "TypeScript",
            "Power BI MCP",
            "DAX",
            "WebSocket",
        ],
        "status": "private",
        "images": ["/projects/fictor360ai.jpeg"],
    },
    {
        "slug": "candidate_portal",
        "technologies": [
            "NestJS",
            "React",
            "Vite",
            "PostgreSQL",
            "OAuth2",
            "Azure OpenAI",
            "Webhooks HMAC",
        ],
        "status": "private",
        "images": ["/projects/candidate-portal.png", "/projects/candidate-portal-2.png"],
    },
    {
        "slug": "data_pipeline",
        "technologies": ["Python", "Pandas", "Metabase", "Power BI", "SQL"],
        "status": "private",
        "images": ["/projects/data-pipeline.png"],
    },
)


def _projects(details: tuple[tuple[str, str, str, str, str], ...]) -> tuple[dict[str, object], ...]:
    return tuple(
        {
            **shared,
            "title": title,
            "description": description,
            "problem": problem,
            "solution": solution,
            "result": result,
        }
        for shared, (title, description, problem, solution, result) in zip(
            _PROJECT_SHARED, details, strict=True
        )
    )


INITIAL_PORTFOLIO_CONTENT = PublishedPortfolioSnapshot(
    id=PORTFOLIO_SNAPSHOT_ID,
    revision=1,
    pt_br=LocalizedPortfolioContent(
        profile=_profile(
            location="Barbacena, MG — Brasil",
            tagline="Software Engineer com 4 anos de experiência criando aplicações web e mobile - do backend ao frontend, com integrações de IA e criação de agentes.",
            about_lead="Atuo com o desenvolvimento web e mobile, do backend ao frontend até o deploy da aplicação. Construo produtos com integrações de IA, RAG e criação de agentes — transformando LLMs em features confiáveis de negócio com observabilidade, fallbacks e testes determinísticos nos trechos críticos.",
            about_body="Combino engenharia de software e IA para entregar produtos que funcionam de ponta a ponta. Acredito que a IA Generativa vai muito além de prompts — quero construir soluções robustas, seguras e escaláveis que transformam a forma como pessoas interagem com dados e informações.",
            differentials=[
                "Curiosidade e aprendizado contínuo",
                "Adaptabilidade",
                "Visão de ponta a ponta",
            ],
            open_to="Aberto a oportunidades remotas",
            languages=[
                {"name": "Português", "level": "Nativo"},
                {"name": "Inglês", "level": "Avançado"},
            ],
        ),
        experiences=_experiences(
            roles=(
                "Desenvolvedor Full Stack | IA Engineer",
                "Analista de Desenvolvimento de Sistemas | Analista de Dados",
                "Estagiário de T.I.",
            ),
            descriptions=(
                "Desenvolvi aplicações web e mobile integradas com IA utilizadas em múltiplas empresas do grupo. Plataforma completa de RH com scoring semântico de currículos, avaliação de fit técnico e integração com Totvs/RM. Super-app corporativo em Flutter, React e Node.js com reserva de veículos com validação por IA, hospedagem, notificações em tempo real, dashboards de BI e autenticação via Azure AD com RBAC por módulo. Fictor360 AI: consulta de indicadores corporativos em linguagem natural via LLM + MCP PowerBI. Infraestrutura com Docker, Kubernetes e pipelines CI/CD via Azure DevOps + GitFlow.",
                "Desenvolvi e implantei soluções tecnológicas com Python, automatizando operações, estruturando pipelines de dados e criando sistemas internos para suporte às áreas de negócio. Desenvolvimento de agente de cobrança de clientes inadimplentes, pipelines de dados e ETL com Pandas, análise e visualização de dados com Pandas e Seaborn, implantação do Metabase com 10+ dashboards automatizados para suporte à decisão, desenvolvimento do site institucional e plataforma de intranet em Django. Suporte técnico e funcional ao ERP Agrosys, análise de bugs e gestão de acessos.",
                "Responsável pela manutenção de equipamentos de informática, suporte técnico ao usuário com foco em hardware, software e rede, além de recuperação de sistemas com formatação e reinstalação de sistemas operacionais, melhorando o desempenho das máquinas.",
            ),
        ),
        projects=_projects(
            (
                (
                    "InCubo — Super-App Fictor Alimentos",
                    "Plataforma interna desenvolvida do zero para digitalizar operações da Fictor Alimentos. Centraliza reserva de veículos com fluxo de aprovação e validação por IA, hospedagem em hotéis, comunicados internos com notificações em tempo real e dashboards de BI — tudo com autenticação corporativa via Azure AD e RBAC por módulo.",
                    "Operações da Fictor distribuídas em múltiplos sistemas desconectados — reservas de veículos em planilhas, comunicados em e-mail, BI em portais separados, hospedagem por telefone. Sem app único, sem comunicação interna estruturada.",
                    "InCubo — ecossistema digital em Flutter + React + NestJS, com Azure AD SSO, RBAC por módulo, push notifications em tempo real (Firebase + RabbitMQ), validação por IA em reservas de veículos e dashboards Power BI embedded. Mobile + web rodando em Kubernetes com CI/CD via Azure DevOps.",
                    "Plataforma corporativa única usada por todas as empresas do grupo. Substituiu 4 sistemas que rodavam soltos e cortou ~40% das chamadas operacionais ao TI.",
                ),
                (
                    "Fictor360 — Power BI Embedded",
                    "Módulo que leva dashboards Power BI diretamente ao Super-App, garantindo que cada usuário veja apenas os dados do seu perfil via RLS configurado por papel e grupo Azure. Geração de embed tokens dinâmicos e gerenciamento de workspaces via API.",
                    "Licenças Power BI individuais geravam gargalo de custo conforme a empresa crescia. Governança limitada — controlar quem vê o quê exigia duplicar workspaces por área, com risco de exposição de dados sensíveis.",
                    "Portal customizado de Embedded Analytics com validação de grupos e usuários via Azure AD e injeção dinâmica de roles RLS no token de acesso. Gestão do ciclo de vida dos dashboards e identidade via API.",
                    "Redução de custos, democratização do acesso aos dados e governança granular por usuário.",
                ),
                (
                    "Plataforma de Gestão de Pessoas com IA",
                    "Sistema corporativo de recrutamento com pipeline Kanban, SLA automático e scoring semântico de currículos usando Azure OpenAI + pgvector. Autenticação via Azure AD, jobs assíncronos com Bull e integração bidirecional com portal externo via webhooks.",
                    "Processo de requisição de contratação manual via formulários, e-mails e planilhas Excel. Sem rastreabilidade, fluxo de aprovação ou dados de SLA.",
                    "Plataforma multiempresa com fluxos de aprovação, assistente de formulários, RAG para scoring de currículos, embeddings de transcrições do Microsoft Teams e integração para agendamento de entrevistas.",
                    "Score de currículos em milissegundos ao invés de horas de leitura manual, com Kanban, SLA por estágio e jobs assíncronos em Bull.",
                ),
                (
                    "Fictor360 AI — Agente Conversacional com Power BI",
                    "Agente conversacional que transforma perguntas em linguagem natural em queries DAX e consulta modelos semânticos do Power BI em tempo real.",
                    "Gerentes tinham os dados na frente, mas para qualquer análise profunda precisavam pedir ao analista e conhecer DAX.",
                    "Agente conversacional com MCP expondo o modelo semântico, validação do plano de consulta antes de gerar DAX e orquestração end-to-end com LangChain TS.",
                    "Analistas e gestores consultam dados em linguagem natural sem precisar conhecer DAX.",
                ),
                (
                    "Portal do Candidato — Fictor Alimentos",
                    "Portal público de recrutamento desacoplado do sistema interno de RH, com autenticação multicanal, scoring automático de currículos por IA e sincronização bidirecional via webhooks.",
                    "Candidatos externos não tinham canal próprio e RH recebia currículos por e-mail, sem visibilidade do processo seletivo.",
                    "Portal em NestJS + React + Vite, autenticação OAuth2 e e-mail, scoring automático e webhooks HMAC-SHA256, com conformidade LGPD e rate limiting.",
                    "Candidatos acompanham o processo em tempo real e RH recebe currículos já pontuados e integrados automaticamente.",
                ),
                (
                    "Pipeline de Dados BI",
                    "Pipelines em Python para extração, tratamento e carga de dados de múltiplas fontes internas, com Metabase como BI self-service.",
                    "Dados de ERP legado, planilhas e APIs internas chegavam em formatos inconsistentes e exigiam consolidação manual.",
                    "Pipelines Python + Pandas para ETL automatizado e Metabase conectado ao Power BI para consolidação de KPIs.",
                    "Mais de 10 dashboards automatizados e gestores com acesso direto aos indicadores.",
                ),
            )
        ),
    ),
    en_us=LocalizedPortfolioContent(
        profile=_profile(
            location="Barbacena, MG — Brazil",
            tagline="Software Engineer with 4 years of experience building web and mobile applications — from backend to frontend, with AI integrations and agent building.",
            about_lead="Software Engineer with 4 years of experience in web and mobile development, working from backend to frontend all the way to cloud deployment. I ship end-to-end products with AI integrations, RAG, and agent building — turning LLMs into reliable business features with observability, fallbacks, and deterministic tests on critical paths.",
            about_body="I combine software engineering and AI to ship products that work end-to-end — from backend to the conversational interface. I believe Generative AI goes far beyond prompts — I want to build robust, secure, and scalable solutions that transform how people interact with data and information.",
            differentials=[
                "Curiosity and continuous learning",
                "Adaptability",
                "End-to-end vision",
            ],
            open_to="Open to remote opportunities",
            languages=[
                {"name": "Portuguese", "level": "Native"},
                {"name": "English", "level": "Advanced"},
            ],
        ),
        experiences=_experiences(
            roles=(
                "Full Stack Developer | AI Engineer",
                "Systems Developer | Data Analyst",
                "IT Intern",
            ),
            descriptions=(
                "Developed web and mobile applications integrated with AI, used across multiple companies in the group. Built a complete HR platform with semantic resume scoring, role fit evaluation, and Totvs/RM integration. Delivered a corporate super-app with Flutter, React, Node.js, Azure AD RBAC, real-time notifications, BI dashboards, Docker, Kubernetes, and CI/CD.",
                "Developed and deployed technology solutions with Python, automating operations, structuring data pipelines, and building internal systems. Built debt collection automation, ETL with Pandas, Metabase dashboards, a Django intranet, and provided ERP support, bug analysis, and access management.",
                "Maintained computer equipment, provided technical user support for hardware, software, and networking, and recovered systems through OS formatting and reinstallation.",
            ),
        ),
        projects=_projects(
            (
                (
                    "InCubo — Fictor Alimentos Super-App",
                    "Internal platform built from scratch to digitize Fictor Alimentos operations, centralizing vehicle reservations, hotel bookings, announcements, notifications, and BI dashboards with Azure AD RBAC.",
                    "Operations were spread across disconnected systems, spreadsheets, email, separate BI portals, and phone calls.",
                    "Flutter, React, and NestJS digital ecosystem with Azure AD SSO, per-module RBAC, real-time notifications, AI-validated vehicle reservations, embedded Power BI, Kubernetes, and CI/CD.",
                    "One platform for the group, replacing four disconnected systems and cutting operational IT requests by about 40%.",
                ),
                (
                    "Fictor360 — Power BI Embedded",
                    "Module that brings Power BI dashboards into the Super-App with Azure group and role-based RLS, dynamic embed tokens, and workspace management.",
                    "Per-user Power BI licenses and duplicated workspaces created cost and governance problems.",
                    "Custom embedded analytics portal with Azure AD validation and dynamic Row-Level Security roles injected in access tokens.",
                    "Reduced costs, broad data access, and granular per-user governance.",
                ),
                (
                    "AI-Powered People Management Platform",
                    "Corporate recruitment system with Kanban, SLA tracking, semantic CV scoring using Azure OpenAI and pgvector, Azure AD, Bull jobs, and webhooks.",
                    "Hiring requisitions were manual, scattered across forms, emails, and spreadsheets without traceability or SLA data.",
                    "Multi-company platform with approval workflows, form assistant, RAG CV scoring, Microsoft Teams transcript embeddings, and interview scheduling.",
                    "CV scoring moved from hours of manual work to milliseconds, supported by Kanban, stage SLA, and async jobs.",
                ),
                (
                    "Fictor360 AI — Conversational Power BI Agent",
                    "Conversational agent that turns natural language questions into DAX queries and queries Power BI semantic models in real time.",
                    "Managers needed analysts and DAX knowledge for deeper analysis.",
                    "Conversational AI with MCP exposing the semantic model, query-plan validation before DAX generation, and LangChain TypeScript orchestration.",
                    "Managers and analysts query data in natural language without knowing DAX.",
                ),
                (
                    "Candidate Portal — Fictor Alimentos",
                    "Public recruitment portal decoupled from the internal HR system, with multi-channel authentication, AI-powered CV scoring, and bidirectional webhooks.",
                    "External candidates had no dedicated channel and HR received CVs by email without process visibility.",
                    "NestJS, React, and Vite portal with OAuth2, email authentication, automatic scoring, HMAC-SHA256 webhooks, LGPD compliance, and rate limiting.",
                    "Candidates track their process in real time and HR receives pre-scored, automatically integrated CVs.",
                ),
                (
                    "BI Data Pipeline",
                    "Python pipelines for extraction, transformation, and loading from internal sources, with Metabase as self-service BI.",
                    "Legacy ERP, spreadsheet, and API data arrived inconsistently and needed manual consolidation.",
                    "Python and Pandas automated ETL with Metabase and Power BI KPI consolidation.",
                    "More than ten automated dashboards and direct access to metrics for managers.",
                ),
            )
        ),
    ),
)
