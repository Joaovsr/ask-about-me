import asyncio
from dataclasses import replace
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from ask_about_me.app import create_app
from ask_about_me.config import Settings
from ask_about_me.openai_generation import AnswerGenerationUnavailableError
from ask_about_me.rag import (
    AnswerGenerationRequest,
    CalibratedEvidenceSupportEvaluator,
    ClaimType,
    DeterministicRetrievalQueryBuilder,
    DocumentType,
    GeneratedAnswer,
    GeneratedClaim,
    LimitationReason,
    PortfolioRag,
    RetrievalSignals,
    RetrievedChunk,
)

CHUNK_ID = UUID("1b3d640f-9f4c-4894-aad2-9740f50a1647")
DOCUMENT_ID = UUID("72c78f20-52b8-4b0d-a29b-04b8adba2219")
SOURCE_ID = UUID("7580bd75-32e6-49c7-854d-e70737823b43")
UNKNOWN_CHUNK_ID = UUID("d8fa2461-da11-46f9-ab8c-ff54921c2d46")


class CaseStudyKnowledgeBase:
    async def search_my_work(
        self, question: str, history: tuple[object, ...]
    ) -> tuple[RetrievedChunk, ...]:
        return (
            RetrievedChunk(
                id=CHUNK_ID,
                document_id=DOCUMENT_ID,
                source_id=SOURCE_ID,
                source_revision=3,
                document_type=DocumentType.CASE_STUDY,
                title="Case Study de exemplo",
                section="Implementação",
                excerpt="Trecho factual publicado para um teste determinístico.",
                source_url="/case-studies/exemplo?locale=pt-BR&version=3",
                signals=RetrievalSignals(
                    vector_distance=0.2,
                    vector_similarity=0.8,
                    vector_rank=1,
                    text_rank_cd=None,
                    text_rank=None,
                    title_match=False,
                    section_match=False,
                    rrf_score=1 / 61,
                ),
            ),
        )


class GroundedAnswerGenerator:
    async def generate_answer(self, request: AnswerGenerationRequest) -> GeneratedAnswer:
        return GeneratedAnswer(
            claims=(
                GeneratedClaim(
                    claim_type=ClaimType.EXPERIENCE,
                    text="João implementou a solução descrita no Case Study.",
                    chunk_ids=(CHUNK_ID,),
                ),
            ),
            requested_claim_types=(ClaimType.EXPERIENCE,),
        )


class EmptyKnowledgeBase:
    async def search_my_work(
        self, question: str, history: tuple[object, ...]
    ) -> tuple[RetrievedChunk, ...]:
        return ()


class WeakKnowledgeBase:
    def __init__(self) -> None:
        self.calls = 0

    async def search_my_work(
        self, question: str, history: tuple[object, ...]
    ) -> tuple[RetrievedChunk, ...]:
        self.calls += 1
        return (
            RetrievedChunk(
                id=CHUNK_ID,
                document_id=DOCUMENT_ID,
                source_id=SOURCE_ID,
                source_revision=3,
                document_type=DocumentType.CASE_STUDY,
                title="Case Study sem relação",
                section="Implementação",
                excerpt="Trecho que não sustenta a pergunta.",
                source_url="/case-studies/exemplo?locale=pt-BR&version=3",
                signals=RetrievalSignals(
                    vector_distance=0.75,
                    vector_similarity=0.25,
                    vector_rank=1,
                    text_rank_cd=None,
                    text_rank=None,
                    title_match=False,
                    section_match=False,
                    rrf_score=1 / 61,
                ),
            ),
        )


class EssayKnowledgeBase:
    async def search_my_work(
        self, question: str, history: tuple[object, ...]
    ) -> tuple[RetrievedChunk, ...]:
        return (
            RetrievedChunk(
                id=CHUNK_ID,
                document_id=DOCUMENT_ID,
                source_id=SOURCE_ID,
                source_revision=1,
                document_type=DocumentType.ESSAY,
                title="Essay de exemplo",
                section="Tese",
                excerpt="Uma opinião técnica publicada para um teste determinístico.",
                source_url="/essays/exemplo?locale=pt-BR&version=1",
                signals=RetrievalSignals(
                    vector_distance=0.2,
                    vector_similarity=0.8,
                    vector_rank=1,
                    text_rank_cd=None,
                    text_rank=None,
                    title_match=False,
                    section_match=False,
                    rrf_score=1 / 61,
                ),
            ),
        )


class ProfileKnowledgeBase:
    async def search_my_work(
        self, question: str, history: tuple[object, ...]
    ) -> tuple[RetrievedChunk, ...]:
        return (
            RetrievedChunk(
                id=CHUNK_ID,
                document_id=DOCUMENT_ID,
                source_id=SOURCE_ID,
                source_revision=1,
                document_type=DocumentType.PROFILE,
                title="Perfil técnico",
                section="Experiência",
                excerpt="O perfil informa que João desenvolveu sistemas de recrutamento.",
                source_url="/profile?locale=pt-BR&version=1",
                signals=RetrievalSignals(
                    vector_distance=0.2,
                    vector_similarity=0.8,
                    vector_rank=1,
                    text_rank_cd=None,
                    text_rank=None,
                    title_match=False,
                    section_match=False,
                    rrf_score=1 / 61,
                ),
            ),
        )


class FollowUpKnowledgeBase:
    async def search_my_work(
        self, question: str, history: tuple[object, ...]
    ) -> tuple[RetrievedChunk, ...]:
        if not history:
            return ()
        return await CaseStudyKnowledgeBase().search_my_work(question, history)


class AnswerGeneratorThatMustNotRun:
    async def generate_answer(self, request: AnswerGenerationRequest) -> GeneratedAnswer:
        raise AssertionError("generation must not run without retrieved evidence")


class NonAtomicAnswerGenerator:
    async def generate_answer(self, request: AnswerGenerationRequest) -> GeneratedAnswer:
        return GeneratedAnswer(
            claims=(
                GeneratedClaim(
                    claim_type=ClaimType.EXPERIENCE,
                    text="João implementou a solução e liderou a implantação.",
                    chunk_ids=(CHUNK_ID,),
                ),
            ),
            requested_claim_types=(ClaimType.EXPERIENCE,),
        )


class MixedAtomicityAnswerGenerator:
    async def generate_answer(self, request: AnswerGenerationRequest) -> GeneratedAnswer:
        return GeneratedAnswer(
            claims=(
                GeneratedClaim(
                    claim_type=ClaimType.EXPERIENCE,
                    text="João implementou a solução descrita no Case Study.",
                    chunk_ids=(CHUNK_ID,),
                ),
                GeneratedClaim(
                    claim_type=ClaimType.EXPERIENCE,
                    text="João implementou a solução e liderou a implantação.",
                    chunk_ids=(CHUNK_ID,),
                ),
            ),
            requested_claim_types=(ClaimType.EXPERIENCE,),
        )


class UnknownCitationAnswerGenerator:
    async def generate_answer(self, request: AnswerGenerationRequest) -> GeneratedAnswer:
        return GeneratedAnswer(
            claims=(
                GeneratedClaim(
                    claim_type=ClaimType.EXPERIENCE,
                    text="João implementou a solução descrita.",
                    chunk_ids=(UNKNOWN_CHUNK_ID,),
                ),
            ),
            requested_claim_types=(ClaimType.EXPERIENCE,),
        )


class PartiallyGroundedAnswerGenerator:
    async def generate_answer(self, request: AnswerGenerationRequest) -> GeneratedAnswer:
        return GeneratedAnswer(
            claims=(
                GeneratedClaim(
                    claim_type=ClaimType.EXPERIENCE,
                    text="João implementou a solução descrita no Case Study.",
                    chunk_ids=(CHUNK_ID,),
                ),
            ),
            requested_claim_types=(ClaimType.EXPERIENCE,),
            limitations=(LimitationReason.INCOMPLETE_EVIDENCE,),
        )


class ProfileAnswerGenerator:
    async def generate_answer(self, request: AnswerGenerationRequest) -> GeneratedAnswer:
        requested_claim_type = (
            ClaimType.EXPERIENCE
            if "implement" in request.question.casefold()
            else ClaimType.PROFILE
        )
        return GeneratedAnswer(
            claims=(
                GeneratedClaim(
                    claim_type=ClaimType.PROFILE,
                    text="O perfil informa experiência com sistemas de recrutamento.",
                    chunk_ids=(CHUNK_ID,),
                ),
            ),
            requested_claim_types=(requested_claim_type,),
        )


class MisclassifiedProfileAnswerGenerator:
    async def generate_answer(self, request: AnswerGenerationRequest) -> GeneratedAnswer:
        return GeneratedAnswer(
            claims=(
                GeneratedClaim(
                    claim_type=ClaimType.PROFILE,
                    text="O perfil informa experiência com sistemas de recrutamento.",
                    chunk_ids=(CHUNK_ID,),
                ),
            ),
            requested_claim_types=(ClaimType.PROFILE,),
        )


class CorrectionCapableAnswerGenerator:
    async def generate_answer(self, request: AnswerGenerationRequest) -> GeneratedAnswer:
        text = (
            "João implementou a solução e liderou a implantação."
            if request.correction is None
            else "João implementou a solução descrita no Case Study."
        )
        return GeneratedAnswer(
            claims=(
                GeneratedClaim(
                    claim_type=ClaimType.EXPERIENCE,
                    text=text,
                    chunk_ids=(CHUNK_ID,),
                ),
            ),
            requested_claim_types=(ClaimType.EXPERIENCE,),
        )


class UnavailableAnswerGenerator:
    async def generate_answer(self, request: AnswerGenerationRequest) -> GeneratedAnswer:
        raise AnswerGenerationUnavailableError("secret provider failure")


def test_ask_returns_a_grounded_claim_with_a_server_hydrated_citation() -> None:
    rag = PortfolioRag(
        knowledge_base=CaseStudyKnowledgeBase(),
        answer_generator=GroundedAnswerGenerator(),
    )
    settings = Settings(database_url="postgresql+psycopg://unused:unused@localhost/unused")

    with TestClient(create_app(settings, portfolio_rag=rag)) as client:
        response = client.post(
            "/ask",
            json={
                "question": "O que João implementou?",
                "locale": "pt-BR",
                "history": [],
            },
        )

    assert response.status_code == 200
    assert response.json() == {
        "status": "answered",
        "answerItems": [
            {
                "kind": "claim",
                "claimType": "experience",
                "text": "João implementou a solução descrita no Case Study.",
                "citationIds": [str(CHUNK_ID)],
            }
        ],
        "citations": [
            {
                "id": str(CHUNK_ID),
                "documentId": str(DOCUMENT_ID),
                "sourceId": str(SOURCE_ID),
                "documentVersion": 3,
                "documentType": "case_study",
                "title": "Case Study de exemplo",
                "section": "Implementação",
                "excerpt": "Trecho factual publicado para um teste determinístico.",
                "sourceUrl": "/case-studies/exemplo?locale=pt-BR&version=3",
            }
        ],
    }


def test_ask_declares_insufficient_evidence_without_generating_an_answer() -> None:
    rag = PortfolioRag(
        knowledge_base=EmptyKnowledgeBase(),
        answer_generator=AnswerGeneratorThatMustNotRun(),
    )
    settings = Settings(database_url="postgresql+psycopg://unused:unused@localhost/unused")

    with TestClient(create_app(settings, portfolio_rag=rag)) as client:
        response = client.post(
            "/ask",
            json={"question": "O que não está publicado?", "locale": "pt-BR"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "status": "insufficient",
        "answerItems": [
            {
                "kind": "limitation",
                "text": "Não há evidência publicada suficiente para responder com segurança.",
            }
        ],
        "citations": [],
    }


def test_ask_declares_insufficient_evidence_in_the_requested_locale() -> None:
    rag = PortfolioRag(
        knowledge_base=EmptyKnowledgeBase(),
        answer_generator=AnswerGeneratorThatMustNotRun(),
    )
    settings = Settings(database_url="postgresql+psycopg://unused:unused@localhost/unused")

    with TestClient(create_app(settings, portfolio_rag=rag)) as client:
        response = client.post(
            "/ask",
            json={"question": "What is not published?", "locale": "en-US"},
        )

    assert response.status_code == 200
    assert response.json()["answerItems"] == [
        {
            "kind": "limitation",
            "text": "There is not enough published evidence to answer safely.",
        }
    ]


def test_ask_rejects_an_unsupported_question_after_retrieval_without_generation() -> None:
    knowledge_base = WeakKnowledgeBase()
    rag = PortfolioRag(
        knowledge_base=knowledge_base,
        answer_generator=AnswerGeneratorThatMustNotRun(),
    )
    settings = Settings(database_url="postgresql+psycopg://unused:unused@localhost/unused")

    with TestClient(create_app(settings, portfolio_rag=rag)) as client:
        response = client.post(
            "/ask",
            json={
                "question": "Qual o presidente do Brasil?",
                "locale": "pt-BR",
                "history": [
                    {"role": "user", "content": "Como funciona o Fictor360 AI?"},
                    {"role": "assistant", "content": "É um agente com Power BI."},
                ],
            },
        )

    assert response.status_code == 200
    assert knowledge_base.calls == 1
    assert response.json() == {
        "status": "insufficient",
        "answerItems": [
            {
                "kind": "limitation",
                "text": "Não há evidência publicada suficiente para responder com segurança.",
            }
        ],
        "citations": [],
    }


def test_support_gate_accepts_a_published_title_without_a_strong_vector_neighbor() -> None:
    chunk = WeakKnowledgeBase()
    evidence = asyncio.run(chunk.search_my_work("Portal do Candidato", ()))
    title_match = replace(
        evidence[0],
        title="Portal do Candidato",
        signals=replace(evidence[0].signals, title_match=True),
    )
    question = "Portal do Candidato"

    decision = CalibratedEvidenceSupportEvaluator().evaluate(
        question=question,
        retrieval_query=DeterministicRetrievalQueryBuilder().build(question, ()),
        chunks=(title_match,),
        retrieval_profile=title_match.signals.retrieval_profile,
    )

    assert decision.supported is True
    assert decision.reasons == ("published_title_match",)


def test_support_gate_rejects_a_semantic_neighbor_for_a_generic_tutorial_request() -> None:
    question = "Ensine como criar uma medida DAX no Power BI."
    evidence = asyncio.run(CaseStudyKnowledgeBase().search_my_work(question, ()))
    neighbor = replace(
        evidence[0],
        signals=replace(
            evidence[0].signals,
            vector_distance=0.443,
            vector_similarity=0.557,
        ),
    )

    decision = CalibratedEvidenceSupportEvaluator().evaluate(
        question=question,
        retrieval_query=DeterministicRetrievalQueryBuilder().build(question, ()),
        chunks=(neighbor,),
        retrieval_profile=neighbor.signals.retrieval_profile,
    )

    assert decision.supported is False


def test_support_gate_accepts_a_supported_cross_language_question() -> None:
    question = "What did João build for external job candidates?"
    evidence = asyncio.run(CaseStudyKnowledgeBase().search_my_work(question, ()))
    neighbor = replace(
        evidence[0],
        signals=replace(
            evidence[0].signals,
            vector_distance=0.5,
            vector_similarity=0.5,
        ),
    )

    decision = CalibratedEvidenceSupportEvaluator().evaluate(
        question=question,
        retrieval_query=DeterministicRetrievalQueryBuilder().build(question, ()),
        chunks=(neighbor,),
        retrieval_profile=neighbor.signals.retrieval_profile,
    )

    assert decision.supported is True


def test_support_gate_rejects_thresholds_for_a_different_retrieval_profile() -> None:
    question = "Portal do Candidato"
    evidence = asyncio.run(CaseStudyKnowledgeBase().search_my_work(question, ()))

    with pytest.raises(RuntimeError, match="incompatible with retrieval profile"):
        CalibratedEvidenceSupportEvaluator().evaluate(
            question=question,
            retrieval_query=DeterministicRetrievalQueryBuilder().build(question, ()),
            chunks=(
                replace(
                    evidence[0],
                    signals=replace(
                        evidence[0].signals,
                        retrieval_profile=(
                            "retrieval=hybrid-rrf-v2;query=deterministic-query-v2;"
                            "embedding=openai/text-embedding-3-large/3072;"
                            "chunker=section-token-v1:text-embedding-3-large:350:500:50;"
                            "locale=pt-BR;lexical=weighted-portuguese-v1"
                        ),
                    ),
                ),
            ),
            retrieval_profile=(
                "retrieval=hybrid-rrf-v2;query=deterministic-query-v2;"
                "embedding=openai/text-embedding-3-large/3072;"
                "chunker=section-token-v1:text-embedding-3-large:350:500:50;"
                "locale=pt-BR;lexical=weighted-portuguese-v1"
            ),
        )


def test_ask_rejects_a_generated_claim_with_multiple_assertions() -> None:
    rag = PortfolioRag(
        knowledge_base=CaseStudyKnowledgeBase(),
        answer_generator=NonAtomicAnswerGenerator(),
    )
    settings = Settings(database_url="postgresql+psycopg://unused:unused@localhost/unused")

    with TestClient(create_app(settings, portfolio_rag=rag)) as client:
        response = client.post(
            "/ask",
            json={"question": "O que João fez?", "locale": "pt-BR"},
        )

    assert response.status_code == 200
    assert response.json()["status"] == "insufficient"
    assert response.json()["citations"] == []


def test_ask_preserves_grounded_atomic_claims_when_other_claims_are_rejected() -> None:
    rag = PortfolioRag(
        knowledge_base=CaseStudyKnowledgeBase(),
        answer_generator=MixedAtomicityAnswerGenerator(),
    )
    settings = Settings(database_url="postgresql+psycopg://unused:unused@localhost/unused")

    with TestClient(create_app(settings, portfolio_rag=rag)) as client:
        response = client.post(
            "/ask",
            json={"question": "O que João fez?", "locale": "pt-BR"},
        )

    assert response.status_code == 200
    assert response.json()["status"] == "partial"
    assert response.json()["answerItems"] == [
        {
            "kind": "claim",
            "claimType": "experience",
            "text": "João implementou a solução descrita no Case Study.",
            "citationIds": [str(CHUNK_ID)],
        },
        {
            "kind": "limitation",
            "text": "A evidência publicada responde apenas parte da pergunta.",
        },
    ]


def test_ask_returns_a_corrected_answer_after_the_first_output_is_invalid() -> None:
    rag = PortfolioRag(
        knowledge_base=CaseStudyKnowledgeBase(),
        answer_generator=CorrectionCapableAnswerGenerator(),
    )
    settings = Settings(database_url="postgresql+psycopg://unused:unused@localhost/unused")

    with TestClient(create_app(settings, portfolio_rag=rag)) as client:
        response = client.post(
            "/ask",
            json={"question": "O que João fez?", "locale": "pt-BR"},
        )

    assert response.status_code == 200
    assert response.json()["status"] == "answered"
    assert response.json()["answerItems"][0]["text"] == (
        "João implementou a solução descrita no Case Study."
    )


def test_ask_rejects_a_citation_that_was_not_retrieved() -> None:
    rag = PortfolioRag(
        knowledge_base=CaseStudyKnowledgeBase(),
        answer_generator=UnknownCitationAnswerGenerator(),
    )
    settings = Settings(database_url="postgresql+psycopg://unused:unused@localhost/unused")

    with TestClient(create_app(settings, portfolio_rag=rag)) as client:
        response = client.post(
            "/ask",
            json={"question": "O que João implementou?", "locale": "pt-BR"},
        )

    assert response.status_code == 200
    assert response.json()["status"] == "insufficient"
    assert response.json()["citations"] == []


def test_ask_renders_only_server_owned_limitation_text() -> None:
    rag = PortfolioRag(
        knowledge_base=CaseStudyKnowledgeBase(),
        answer_generator=PartiallyGroundedAnswerGenerator(),
    )
    settings = Settings(database_url="postgresql+psycopg://unused:unused@localhost/unused")

    with TestClient(create_app(settings, portfolio_rag=rag)) as client:
        response = client.post(
            "/ask",
            json={"question": "O que mais João fez?", "locale": "pt-BR"},
        )

    assert response.status_code == 200
    assert response.json()["status"] == "partial"
    assert response.json()["answerItems"][-1] == {
        "kind": "limitation",
        "text": "A evidência publicada responde apenas parte da pergunta.",
    }


def test_ask_does_not_use_an_essay_as_evidence_of_practical_experience() -> None:
    rag = PortfolioRag(
        knowledge_base=EssayKnowledgeBase(),
        answer_generator=GroundedAnswerGenerator(),
    )
    settings = Settings(database_url="postgresql+psycopg://unused:unused@localhost/unused")

    with TestClient(create_app(settings, portfolio_rag=rag)) as client:
        response = client.post(
            "/ask",
            json={"question": "O que João implementou?", "locale": "pt-BR"},
        )

    assert response.status_code == 200
    assert response.json()["status"] == "insufficient"
    assert response.json()["citations"] == []


def test_ask_marks_profile_only_support_as_partial_for_an_experience_question() -> None:
    rag = PortfolioRag(
        knowledge_base=ProfileKnowledgeBase(),
        answer_generator=MisclassifiedProfileAnswerGenerator(),
    )
    settings = Settings(database_url="postgresql+psycopg://unused:unused@localhost/unused")

    with TestClient(create_app(settings, portfolio_rag=rag)) as client:
        response = client.post(
            "/ask",
            json={"question": "O que João implementou?", "locale": "pt-BR"},
        )

    assert response.status_code == 200
    assert response.json()["status"] == "partial"
    assert response.json()["answerItems"][-1]["kind"] == "limitation"


def test_ask_allows_profile_only_support_to_answer_a_profile_question() -> None:
    rag = PortfolioRag(
        knowledge_base=ProfileKnowledgeBase(),
        answer_generator=ProfileAnswerGenerator(),
    )
    settings = Settings(database_url="postgresql+psycopg://unused:unused@localhost/unused")

    with TestClient(create_app(settings, portfolio_rag=rag)) as client:
        response = client.post(
            "/ask",
            json={"question": "Qual é o perfil técnico de João?", "locale": "pt-BR"},
        )

    assert response.status_code == 200
    assert response.json()["status"] == "answered"


def test_ask_does_not_treat_projects_mentioned_in_a_profile_question_as_practical() -> None:
    rag = PortfolioRag(
        knowledge_base=ProfileKnowledgeBase(),
        answer_generator=ProfileAnswerGenerator(),
    )
    settings = Settings(database_url="postgresql+psycopg://unused:unused@localhost/unused")

    with TestClient(create_app(settings, portfolio_rag=rag)) as client:
        response = client.post(
            "/ask",
            json={
                "question": "Quais projetos estão listados no perfil de João?",
                "locale": "pt-BR",
            },
        )

    assert response.status_code == 200
    assert response.json()["status"] == "answered"


def test_ask_allows_profile_claims_to_answer_employment_history() -> None:
    rag = PortfolioRag(
        knowledge_base=ProfileKnowledgeBase(),
        answer_generator=ProfileAnswerGenerator(),
    )
    settings = Settings(database_url="postgresql+psycopg://unused:unused@localhost/unused")

    with TestClient(create_app(settings, portfolio_rag=rag)) as client:
        response = client.post(
            "/ask",
            json={
                "question": "Em quais empresas João trabalhou?",
                "locale": "pt-BR",
            },
        )

    assert response.status_code == 200
    assert response.json()["status"] == "answered"


def test_ask_allows_profile_claims_to_answer_developed_skills() -> None:
    rag = PortfolioRag(
        knowledge_base=ProfileKnowledgeBase(),
        answer_generator=ProfileAnswerGenerator(),
    )
    settings = Settings(database_url="postgresql+psycopg://unused:unused@localhost/unused")

    with TestClient(create_app(settings, portfolio_rag=rag)) as client:
        response = client.post(
            "/ask",
            json={
                "question": "Quais habilidades João desenvolveu?",
                "locale": "pt-BR",
            },
        )

    assert response.status_code == 200
    assert response.json()["status"] == "answered"


def test_ask_allows_profile_claims_to_answer_a_career_question() -> None:
    rag = PortfolioRag(
        knowledge_base=ProfileKnowledgeBase(),
        answer_generator=ProfileAnswerGenerator(),
    )
    settings = Settings(database_url="postgresql+psycopg://unused:unused@localhost/unused")

    with TestClient(create_app(settings, portfolio_rag=rag)) as client:
        response = client.post(
            "/ask",
            json={
                "question": "Como João desenvolveu sua carreira?",
                "locale": "pt-BR",
            },
        )

    assert response.status_code == 200
    assert response.json()["status"] == "answered"


def test_ask_does_not_treat_an_english_hypothetical_as_past_experience() -> None:
    rag = PortfolioRag(
        knowledge_base=ProfileKnowledgeBase(),
        answer_generator=ProfileAnswerGenerator(),
    )
    settings = Settings(database_url="postgresql+psycopg://unused:unused@localhost/unused")

    with TestClient(create_app(settings, portfolio_rag=rag)) as client:
        response = client.post(
            "/ask",
            json={"question": "How would you build a RAG system?", "locale": "en-US"},
        )

    assert response.status_code == 200
    assert response.json()["status"] == "answered"


def test_ask_guards_an_english_past_delivery_question_from_misclassification() -> None:
    rag = PortfolioRag(
        knowledge_base=ProfileKnowledgeBase(),
        answer_generator=MisclassifiedProfileAnswerGenerator(),
    )
    settings = Settings(database_url="postgresql+psycopg://unused:unused@localhost/unused")

    with TestClient(create_app(settings, portfolio_rag=rag)) as client:
        response = client.post(
            "/ask",
            json={"question": "What did you implement?", "locale": "en-US"},
        )

    assert response.status_code == 200
    assert response.json()["status"] == "partial"


def test_ask_rejects_a_conversation_payload_above_the_initial_limit() -> None:
    rag = PortfolioRag(
        knowledge_base=EmptyKnowledgeBase(),
        answer_generator=AnswerGeneratorThatMustNotRun(),
    )
    settings = Settings(database_url="postgresql+psycopg://unused:unused@localhost/unused")
    history = [
        {"role": "user", "content": "x" * 2000},
        {"role": "assistant", "content": "x" * 2000},
        {"role": "user", "content": "x" * 2000},
        {"role": "assistant", "content": "x" * 2000},
    ]

    with TestClient(create_app(settings, portfolio_rag=rag)) as client:
        response = client.post(
            "/ask",
            json={
                "question": "Esta pergunta excede o limite total.",
                "locale": "pt-BR",
                "history": history,
            },
        )

    assert response.status_code == 422


def test_ask_rejects_an_oversized_http_body_even_when_extra_data_is_unknown() -> None:
    rag = PortfolioRag(
        knowledge_base=EmptyKnowledgeBase(),
        answer_generator=AnswerGeneratorThatMustNotRun(),
    )
    settings = Settings(database_url="postgresql+psycopg://unused:unused@localhost/unused")

    with TestClient(create_app(settings, portfolio_rag=rag)) as client:
        response = client.post(
            "/ask",
            json={
                "question": "Pergunta curta.",
                "locale": "pt-BR",
                "padding": "x" * 20_000,
            },
        )

    assert response.status_code == 413


def test_ask_uses_conversation_history_to_retrieve_evidence_for_a_follow_up() -> None:
    rag = PortfolioRag(
        knowledge_base=FollowUpKnowledgeBase(),
        answer_generator=GroundedAnswerGenerator(),
    )
    settings = Settings(database_url="postgresql+psycopg://unused:unused@localhost/unused")

    with TestClient(create_app(settings, portfolio_rag=rag)) as client:
        response = client.post(
            "/ask",
            json={
                "question": "E qual foi o resultado?",
                "locale": "pt-BR",
                "history": [
                    {"role": "user", "content": "Fale do Case Study de exemplo."},
                    {"role": "assistant", "content": "Ele descreve uma implementação."},
                ],
            },
        )

    assert response.status_code == 200
    assert response.json()["status"] == "answered"


def test_configured_app_composes_the_default_rag_at_startup() -> None:
    rag = PortfolioRag(
        knowledge_base=CaseStudyKnowledgeBase(),
        answer_generator=GroundedAnswerGenerator(),
    )
    settings = Settings(
        database_url="postgresql+psycopg://unused:unused@localhost/unused",
        openai_api_key=SecretStr("test-key"),
    )
    received_settings: list[Settings] = []

    def build_rag(resolved_settings: Settings, database: object) -> PortfolioRag:
        received_settings.append(resolved_settings)
        return rag

    with TestClient(create_app(settings, rag_factory=build_rag)) as client:
        response = client.post(
            "/ask",
            json={"question": "O que João implementou?", "locale": "pt-BR"},
        )

    assert response.status_code == 200
    assert response.json()["status"] == "answered"
    assert received_settings == [settings]


def test_app_treats_an_empty_openai_key_as_unconfigured() -> None:
    settings = Settings(
        database_url="postgresql+psycopg://unused:unused@localhost/unused",
        openai_api_key=SecretStr(""),
    )

    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/ask",
            json={"question": "O que João implementou?", "locale": "pt-BR"},
        )

    assert response.status_code == 503
    assert response.json() == {"detail": {"status": "unavailable", "dependency": "rag"}}


def test_ask_maps_generation_outages_without_exposing_provider_details() -> None:
    rag = PortfolioRag(
        knowledge_base=CaseStudyKnowledgeBase(),
        answer_generator=UnavailableAnswerGenerator(),
    )
    settings = Settings(database_url="postgresql+psycopg://unused:unused@localhost/unused")

    with TestClient(create_app(settings, portfolio_rag=rag)) as client:
        response = client.post(
            "/ask",
            json={"question": "O que João implementou?", "locale": "pt-BR"},
        )

    assert response.status_code == 503
    assert response.json() == {"detail": {"status": "unavailable", "dependency": "openai"}}
    assert "secret provider failure" not in response.text
