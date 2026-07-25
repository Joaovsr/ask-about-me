import re
from collections.abc import Sequence
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Protocol
from uuid import UUID


class Locale(StrEnum):
    PT_BR = "pt-BR"
    EN_US = "en-US"


class DocumentType(StrEnum):
    CASE_STUDY = "case_study"
    PROFILE = "profile"
    ESSAY = "essay"


class ClaimType(StrEnum):
    EXPERIENCE = "experience"
    PROFILE = "profile"
    OPINION = "opinion"


class AnswerStatus(StrEnum):
    ANSWERED = "answered"
    PARTIAL = "partial"
    INSUFFICIENT = "insufficient"


class LimitationReason(StrEnum):
    INCOMPLETE_EVIDENCE = "incomplete_evidence"


class AnswerValidationIssue(StrEnum):
    NON_ATOMIC_CLAIM = "non_atomic_claim"
    UNKNOWN_CITATION = "unknown_citation"
    INVALID_AUTHORITY = "invalid_authority"
    INVALID_LIMITATION = "invalid_limitation"
    INVALID_REQUESTED_CLAIM_TYPE = "invalid_requested_claim_type"
    NO_VALID_CLAIM = "no_valid_claim"


class ConversationRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


@dataclass(frozen=True)
class ConversationMessage:
    role: ConversationRole
    content: str


@dataclass(frozen=True)
class RetrievedChunk:
    id: UUID
    document_id: UUID
    source_id: UUID
    source_revision: int
    document_type: DocumentType
    title: str
    section: str
    excerpt: str
    source_url: str
    score: float


@dataclass(frozen=True)
class GeneratedClaim:
    claim_type: ClaimType
    text: str
    chunk_ids: tuple[UUID, ...]


@dataclass(frozen=True)
class GeneratedAnswer:
    claims: tuple[GeneratedClaim, ...]
    requested_claim_types: tuple[ClaimType, ...]
    limitations: tuple[LimitationReason, ...] = ()


@dataclass(frozen=True)
class GenerationCorrection:
    previous_answer: GeneratedAnswer
    issues: tuple[AnswerValidationIssue, ...]


@dataclass(frozen=True)
class AnswerGenerationRequest:
    question: str
    locale: Locale
    history: tuple[ConversationMessage, ...]
    evidence: tuple[RetrievedChunk, ...]
    correction: GenerationCorrection | None = None


@dataclass(frozen=True)
class ClaimAnswerItem:
    claim_type: ClaimType
    text: str
    citation_ids: tuple[UUID, ...]


@dataclass(frozen=True)
class LimitationAnswerItem:
    text: str


AnswerItem = ClaimAnswerItem | LimitationAnswerItem


@dataclass(frozen=True)
class Citation:
    id: UUID
    document_id: UUID
    source_id: UUID
    source_revision: int
    document_type: DocumentType
    title: str
    section: str
    excerpt: str
    source_url: str


@dataclass(frozen=True)
class PortfolioAnswer:
    status: AnswerStatus
    answer_items: tuple[AnswerItem, ...]
    citations: tuple[Citation, ...]


class KnowledgeBase(Protocol):
    async def search_my_work(
        self, question: str, history: tuple[ConversationMessage, ...]
    ) -> tuple[RetrievedChunk, ...]: ...


class AnswerGenerator(Protocol):
    async def generate_answer(self, request: AnswerGenerationRequest) -> GeneratedAnswer: ...


class ClaimAtomicityValidator(Protocol):
    def is_atomic(self, text: str) -> bool: ...


class ConservativeClaimAtomicityValidator:
    _clause_boundary = re.compile(
        r"[,;:]|\s[—–-]\s|\b(?:e|and|mas|but|al[eé]m disso|additionally)\b",
        re.IGNORECASE,
    )

    def is_atomic(self, text: str) -> bool:
        stripped = text.strip()
        if not stripped or "\n" in stripped:
            return False
        sentence_endings = re.findall(r"[.!?](?=\s+\S|$)", stripped)
        return len(sentence_endings) <= 1 and self._clause_boundary.search(stripped) is None


class PortfolioRag:
    _clear_practical_experience_question = re.compile(
        r"\b(?:o que|qual|quais)\b[^?]{0,80}\b"
        r"(?:jo[aã]o|ele|voc[eê])\b[^?]{0,60}\b"
        r"(?:implementou|entregou)\b|"
        r"\b(?:what|which)\b[^?]{0,30}\bdid\b[^?]{0,30}\b"
        r"(?:jo[aã]o|he|you)\b[^?]{0,60}\b"
        r"(?:implement|deliver)\b|"
        r"\b(?:what|which)\b[^?]{0,30}\b(?:has|have)\b[^?]{0,30}\b"
        r"(?:jo[aã]o|he|you)\b[^?]{0,60}\b"
        r"(?:implemented|delivered)\b",
        re.IGNORECASE,
    )
    _clear_profile_or_opinion_question = re.compile(
        r"\b(?:"
        r"perfil|profile|bio(?:grafia|graphy)?|habilidades?|skills?|expertise|"
        r"conhecimentos?|knowledge|"
        r"compet[eê]ncias?|education|degree|forma[cç][aã]o|"
        r"carreira|career|trajet[oó]ria|trajectory|"
        r"empresas?|companies|employers?|opini[aã]o|opinion|views?|"
        r"teses?|thesis|theses"
        r")\b",
        re.IGNORECASE,
    )

    def __init__(
        self,
        *,
        knowledge_base: KnowledgeBase,
        answer_generator: AnswerGenerator,
        claim_atomicity_validator: ClaimAtomicityValidator | None = None,
    ) -> None:
        self._knowledge_base = knowledge_base
        self._answer_generator = answer_generator
        self._claim_atomicity_validator = (
            claim_atomicity_validator or ConservativeClaimAtomicityValidator()
        )

    async def answer(
        self,
        *,
        question: str,
        locale: Locale,
        history: Sequence[ConversationMessage],
    ) -> PortfolioAnswer:
        normalized_history = tuple(history)
        evidence = await self._knowledge_base.search_my_work(question, normalized_history)
        if not evidence:
            return self._insufficient_answer(locale)

        generation_request = AnswerGenerationRequest(
            question=question,
            locale=locale,
            history=normalized_history,
            evidence=evidence,
        )
        generated = await self._answer_generator.generate_answer(generation_request)
        answer, issues = self._validate_generated_answer(
            generated,
            evidence,
            locale,
            question,
        )
        if answer is not None:
            return answer

        corrected = await self._answer_generator.generate_answer(
            replace(
                generation_request,
                correction=GenerationCorrection(
                    previous_answer=generated,
                    issues=issues,
                ),
            )
        )
        corrected_answer, _ = self._validate_generated_answer(
            corrected,
            evidence,
            locale,
            question,
        )
        return corrected_answer or self._insufficient_answer(locale)

    def _validate_generated_answer(
        self,
        generated: GeneratedAnswer,
        evidence: tuple[RetrievedChunk, ...],
        locale: Locale,
        question: str,
    ) -> tuple[PortfolioAnswer | None, tuple[AnswerValidationIssue, ...]]:
        evidence_by_id = {chunk.id: chunk for chunk in evidence}
        claims: list[ClaimAnswerItem] = []
        cited_chunks: list[RetrievedChunk] = []
        seen_citations: set[UUID] = set()
        issues: list[AnswerValidationIssue] = []

        for generated_claim in generated.claims:
            if not self._claim_atomicity_validator.is_atomic(generated_claim.text):
                issues.append(AnswerValidationIssue.NON_ATOMIC_CLAIM)
                continue
            referenced_chunks = [
                evidence_by_id[chunk_id]
                for chunk_id in generated_claim.chunk_ids
                if chunk_id in evidence_by_id
            ]
            if len(referenced_chunks) != len(generated_claim.chunk_ids):
                issues.append(AnswerValidationIssue.UNKNOWN_CITATION)
                continue
            if not self._has_allowed_authority(generated_claim.claim_type, referenced_chunks):
                issues.append(AnswerValidationIssue.INVALID_AUTHORITY)
                continue

            claims.append(
                ClaimAnswerItem(
                    claim_type=generated_claim.claim_type,
                    text=generated_claim.text,
                    citation_ids=generated_claim.chunk_ids,
                )
            )
            for chunk in referenced_chunks:
                if chunk.id not in seen_citations:
                    seen_citations.add(chunk.id)
                    cited_chunks.append(chunk)

        if not claims:
            issues.append(AnswerValidationIssue.NO_VALID_CLAIM)

        if not all(isinstance(reason, LimitationReason) for reason in generated.limitations):
            issues.append(AnswerValidationIssue.INVALID_LIMITATION)
        if not generated.requested_claim_types or not all(
            isinstance(claim_type, ClaimType)
            for claim_type in generated.requested_claim_types
        ):
            issues.append(AnswerValidationIssue.INVALID_REQUESTED_CLAIM_TYPE)

        if issues:
            return None, tuple(dict.fromkeys(issues))

        limitation_reasons = list(generated.limitations)
        requested_claim_types = set(generated.requested_claim_types)
        if self._clear_practical_experience_question.search(
            question
        ) and not self._clear_profile_or_opinion_question.search(question):
            requested_claim_types.add(ClaimType.EXPERIENCE)
        if (
            not requested_claim_types <= {claim.claim_type for claim in claims}
            and LimitationReason.INCOMPLETE_EVIDENCE not in limitation_reasons
        ):
            limitation_reasons.append(LimitationReason.INCOMPLETE_EVIDENCE)

        limitations = tuple(
            self._limitation_item(reason, locale) for reason in limitation_reasons
        )
        status = AnswerStatus.PARTIAL if limitations else AnswerStatus.ANSWERED
        return (
            PortfolioAnswer(
                status=status,
                answer_items=(*claims, *limitations),
                citations=tuple(self._hydrate_citation(chunk) for chunk in cited_chunks),
            ),
            (),
        )

    @staticmethod
    def _has_allowed_authority(claim_type: ClaimType, chunks: Sequence[RetrievedChunk]) -> bool:
        document_types = {chunk.document_type for chunk in chunks}
        if claim_type is ClaimType.EXPERIENCE:
            return DocumentType.CASE_STUDY in document_types and document_types <= {
                DocumentType.CASE_STUDY,
                DocumentType.PROFILE,
            }
        if claim_type is ClaimType.PROFILE:
            return bool(document_types) and document_types <= {DocumentType.PROFILE}
        return bool(document_types) and document_types <= {DocumentType.ESSAY}

    @staticmethod
    def _hydrate_citation(chunk: RetrievedChunk) -> Citation:
        return Citation(
            id=chunk.id,
            document_id=chunk.document_id,
            source_id=chunk.source_id,
            source_revision=chunk.source_revision,
            document_type=chunk.document_type,
            title=chunk.title,
            section=chunk.section,
            excerpt=chunk.excerpt,
            source_url=chunk.source_url,
        )

    @staticmethod
    def _limitation_item(reason: LimitationReason, locale: Locale) -> LimitationAnswerItem:
        texts = {
            LimitationReason.INCOMPLETE_EVIDENCE: {
                Locale.PT_BR: "A evidência publicada responde apenas parte da pergunta.",
                Locale.EN_US: "The published evidence answers only part of the question.",
            }
        }
        return LimitationAnswerItem(text=texts[reason][locale])

    @staticmethod
    def _insufficient_answer(locale: Locale) -> PortfolioAnswer:
        text = {
            Locale.PT_BR: "Não há evidência publicada suficiente para responder com segurança.",
            Locale.EN_US: "There is not enough published evidence to answer safely.",
        }[locale]
        return PortfolioAnswer(
            status=AnswerStatus.INSUFFICIENT,
            answer_items=(LimitationAnswerItem(text=text),),
            citations=(),
        )
