import re
from collections.abc import Sequence
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Protocol
from uuid import UUID

RETRIEVAL_PIPELINE_VERSION = "hybrid-rrf-v2"
CALIBRATED_RETRIEVAL_PROFILE = (
    "retrieval=hybrid-rrf-v2;query=deterministic-query-v2;"
    "embedding=openai/text-embedding-3-small/1536;"
    "chunker=section-token-v1:text-embedding-3-small:350:500:50;"
    "locale=pt-BR;lexical=weighted-portuguese-v1"
)


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
    OUT_OF_SCOPE = "out_of_scope"


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
class RetrievalQuery:
    original_question: str
    embedding_text: str
    lexical_text: str
    history_used: tuple[ConversationMessage, ...]
    history_reason: str | None
    title_text: str = ""
    strategy_version: str = "deterministic-query-v2"


@dataclass(frozen=True)
class RetrievalSignals:
    vector_distance: float | None
    vector_similarity: float | None
    vector_rank: int | None
    text_rank_cd: float | None
    text_rank: int | None
    title_match: bool
    section_match: bool
    rrf_score: float
    retrieval_profile: str = CALIBRATED_RETRIEVAL_PROFILE
    index_generation: UUID | None = None
    index_profile: str = ""


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
    signals: RetrievalSignals
    source_slug: str = ""


@dataclass(frozen=True)
class SupportFeatures:
    best_vector_similarity: float | None
    best_text_rank_cd: float | None
    has_title_match: bool
    has_section_match: bool
    channels_agree: bool
    supporting_document_count: int


@dataclass(frozen=True)
class SupportDecision:
    supported: bool
    rule_version: str
    features: SupportFeatures
    reasons: tuple[str, ...]
    approved_chunks: tuple[RetrievedChunk, ...]


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


class EvidenceSupportEvaluator(Protocol):
    def evaluate(
        self,
        *,
        question: str,
        retrieval_query: RetrievalQuery,
        chunks: tuple[RetrievedChunk, ...],
        retrieval_profile: str,
    ) -> SupportDecision: ...


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


class DeterministicRetrievalQueryBuilder:
    """Build a standalone retrieval query without allowing history to mask topic changes."""

    _elliptical = re.compile(
        r"^(?:e|and)\s+(?:qual|quais|quanto|como|what|which|how)\b|"
        r"\b(?:nesse|nessa|neste|nesta|dele|dela|disso|desse|dessa|"
        r"that|this|it|its|there)\b|"
        r"^(?:qual|quais|what|which)\s+(?:foi|foram|era|were|was|is|are)\b",
        re.IGNORECASE,
    )
    _navigation = re.compile(
        r"\b(?:jo[aã]o|ele|ela|he|she|you|voc[eê])\b|"
        r"\b(?:trabalhou|trabalha|worked|works)\s+com\b|"
        r"\b(?:fale|conte|tell\s+me|talk)\s+(?:sobre|about)\b",
        re.IGNORECASE,
    )
    _title_term = re.compile(r"\b[A-ZÁÀÂÃÉÊÍÓÔÕÚÜÇ][\wÀ-ÿ-]*\b")
    _title_noise = frozenset(
        {
            "and",
            "como",
            "conte",
            "e",
            "ensine",
            "fale",
            "how",
            "qual",
            "quais",
            "que",
            "quanto",
            "tell",
            "what",
            "which",
            "who",
            "write",
        }
    )

    def build(
        self,
        question: str,
        history: tuple[ConversationMessage, ...],
    ) -> RetrievalQuery:
        stripped_question = question.strip()
        history_used: tuple[ConversationMessage, ...] = ()
        history_reason: str | None = None
        if self._elliptical.search(stripped_question):
            last_user_message = next(
                (message for message in reversed(history) if message.role is ConversationRole.USER),
                None,
            )
            if last_user_message is not None:
                history_used = (last_user_message,)
                history_reason = "elliptical_turn"

        embedding_parts = (*(message.content for message in history_used), stripped_question)
        lexical_parts = (
            *(self._lexical_terms(message.content) for message in history_used),
            self._lexical_terms(stripped_question),
        )
        lexical_text = " OR ".join(part for part in lexical_parts if part).strip()
        title_parts = tuple(self._title_terms(part) for part in lexical_parts)
        title_text = " OR ".join(part for part in title_parts if part).strip()
        return RetrievalQuery(
            original_question=stripped_question,
            embedding_text="\n".join(embedding_parts),
            lexical_text=lexical_text or stripped_question,
            history_used=history_used,
            history_reason=history_reason,
            title_text=title_text,
        )

    def _lexical_terms(self, value: str) -> str:
        return " ".join(self._navigation.sub(" ", value).split())

    def _title_terms(self, value: str) -> str:
        return " ".join(
            term
            for term in self._title_term.findall(value)
            if term.casefold() not in self._title_noise
        )


class CalibratedEvidenceSupportEvaluator:
    """Decide whether retrieved evidence supports generation using raw retrieval signals."""

    _generic_task_request = re.compile(
        r"^\s*(?:por favor[,\s]+)?(?:"
        r"implemente\b|ensine\s+como\b|escreva\s+(?:um|uma)\s+(?:tutorial|guia)\b"
        r")|"
        r"^\s*(?:please[,\s]+)?(?:"
        r"implement\b|teach\s+(?:me\s+)?how\b|"
        r"write\s+(?:a|an)\s+(?:tutorial|guide)\b"
        r")|"
        r"^\s*(?:como|how\s+(?:do|can)\s+i)\s+"
        r"(?:criar|implementar|build|create|implement)\b",
        re.IGNORECASE,
    )

    def __init__(
        self,
        *,
        minimum_vector_similarity: float = 0.45,
        minimum_text_rank_cd: float = 0.05,
        rule_version: str = "support-v2",
        retrieval_profile: str = CALIBRATED_RETRIEVAL_PROFILE,
        generation_limit: int = 6,
        per_document_limit: int = 2,
    ) -> None:
        self._minimum_vector_similarity = minimum_vector_similarity
        self._minimum_text_rank_cd = minimum_text_rank_cd
        self._rule_version = rule_version
        self._retrieval_profile = retrieval_profile
        self._generation_limit = generation_limit
        self._per_document_limit = per_document_limit

    def evaluate(
        self,
        *,
        question: str,
        retrieval_query: RetrievalQuery,
        chunks: tuple[RetrievedChunk, ...],
        retrieval_profile: str,
    ) -> SupportDecision:
        if f"query={retrieval_query.strategy_version};" not in retrieval_profile:
            raise RuntimeError(
                "retrieval query strategy does not match the profile that produced the chunks"
            )
        observed_profiles = {
            retrieval_profile,
            *(chunk.signals.retrieval_profile for chunk in chunks),
        }
        incompatible = observed_profiles - {self._retrieval_profile}
        if incompatible or len(observed_profiles) != 1:
            profiles = ", ".join(sorted(observed_profiles))
            raise RuntimeError(
                f"support thresholds are incompatible with retrieval profile(s): {profiles}"
            )

        generic_task_request = self._generic_task_request.search(question) is not None
        approved = (
            ()
            if generic_task_request
            else tuple(chunk for chunk in chunks if self._supports_generation(chunk))
        )
        selected = self._select_context(approved)
        similarities = [
            chunk.signals.vector_similarity
            for chunk in chunks
            if chunk.signals.vector_similarity is not None
        ]
        text_ranks = [
            chunk.signals.text_rank_cd for chunk in chunks if chunk.signals.text_rank_cd is not None
        ]
        has_title_match = any(chunk.signals.title_match for chunk in chunks)
        has_section_match = any(chunk.signals.section_match for chunk in chunks)
        channels_agree = any(
            chunk.signals.vector_rank is not None and chunk.signals.text_rank is not None
            for chunk in chunks
        )
        reasons: list[str] = []
        if generic_task_request:
            reasons.append("generic_task_request")
        if has_title_match:
            reasons.append("published_title_match")
        if text_ranks and max(text_ranks) >= self._minimum_text_rank_cd:
            reasons.append("strong_lexical_match")
        if similarities and max(similarities) >= self._minimum_vector_similarity:
            reasons.append("strong_semantic_match")
        if not selected:
            reasons.append("no_chunk_passed_support_thresholds")

        return SupportDecision(
            supported=bool(selected),
            rule_version=self._rule_version,
            features=SupportFeatures(
                best_vector_similarity=max(similarities, default=None),
                best_text_rank_cd=max(text_ranks, default=None),
                has_title_match=has_title_match,
                has_section_match=has_section_match,
                channels_agree=channels_agree,
                supporting_document_count=len({chunk.document_id for chunk in approved}),
            ),
            reasons=tuple(reasons),
            approved_chunks=selected,
        )

    def _supports_generation(self, chunk: RetrievedChunk) -> bool:
        signals = chunk.signals
        return bool(
            signals.title_match
            or (
                signals.text_rank_cd is not None
                and signals.text_rank_cd >= self._minimum_text_rank_cd
            )
            or (
                signals.vector_similarity is not None
                and signals.vector_similarity >= self._minimum_vector_similarity
            )
        )

    def _select_context(self, chunks: tuple[RetrievedChunk, ...]) -> tuple[RetrievedChunk, ...]:
        selected: list[RetrievedChunk] = []
        per_document: dict[UUID, int] = {}
        seen_sections: set[tuple[UUID, str]] = set()
        deferred: list[RetrievedChunk] = []
        for chunk in chunks:
            document_count = per_document.get(chunk.document_id, 0)
            if document_count >= self._per_document_limit:
                continue
            section_key = (chunk.document_id, chunk.section.casefold())
            if section_key in seen_sections:
                deferred.append(chunk)
                continue
            selected.append(chunk)
            per_document[chunk.document_id] = document_count + 1
            seen_sections.add(section_key)
            if len(selected) == self._generation_limit:
                return tuple(selected)
        for chunk in deferred:
            document_count = per_document.get(chunk.document_id, 0)
            if document_count >= self._per_document_limit:
                continue
            selected.append(chunk)
            per_document[chunk.document_id] = document_count + 1
            if len(selected) == self._generation_limit:
                break
        return tuple(selected)


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
        evidence_support_evaluator: EvidenceSupportEvaluator | None = None,
        retrieval_query_builder: DeterministicRetrievalQueryBuilder | None = None,
    ) -> None:
        self._knowledge_base = knowledge_base
        self._answer_generator = answer_generator
        self._claim_atomicity_validator = (
            claim_atomicity_validator or ConservativeClaimAtomicityValidator()
        )
        self._evidence_support_evaluator = (
            evidence_support_evaluator or CalibratedEvidenceSupportEvaluator()
        )
        self._retrieval_query_builder = (
            retrieval_query_builder or DeterministicRetrievalQueryBuilder()
        )

    async def answer(
        self,
        *,
        question: str,
        locale: Locale,
        history: Sequence[ConversationMessage],
    ) -> PortfolioAnswer:
        normalized_history = tuple(history)
        retrieval_query = self._retrieval_query_builder.build(question, normalized_history)
        evidence = await self._knowledge_base.search_my_work(question, normalized_history)
        if not evidence:
            return self._insufficient_answer(locale)
        support = self._evidence_support_evaluator.evaluate(
            question=question,
            retrieval_query=retrieval_query,
            chunks=evidence,
            retrieval_profile=evidence[0].signals.retrieval_profile,
        )
        if not support.supported:
            return self._insufficient_answer(locale)
        evidence = support.approved_chunks

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
            isinstance(claim_type, ClaimType) for claim_type in generated.requested_claim_types
        ):
            issues.append(AnswerValidationIssue.INVALID_REQUESTED_CLAIM_TYPE)

        recoverable_claim_issues = {
            AnswerValidationIssue.NON_ATOMIC_CLAIM,
            AnswerValidationIssue.UNKNOWN_CITATION,
            AnswerValidationIssue.INVALID_AUTHORITY,
        }
        if issues and (
            not claims or any(issue not in recoverable_claim_issues for issue in issues)
        ):
            return None, tuple(dict.fromkeys(issues))

        limitation_reasons = list(generated.limitations)
        if issues and LimitationReason.INCOMPLETE_EVIDENCE not in limitation_reasons:
            limitation_reasons.append(LimitationReason.INCOMPLETE_EVIDENCE)
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

        limitations = tuple(self._limitation_item(reason, locale) for reason in limitation_reasons)
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
            },
            LimitationReason.OUT_OF_SCOPE: {
                Locale.PT_BR: "Este chat responde apenas sobre a trajetória técnica do João.",
                Locale.EN_US: "This chat only answers questions about João's technical journey.",
            },
        }
        return LimitationAnswerItem(text=texts[reason][locale])

    @staticmethod
    def _insufficient_answer(
        locale: Locale,
        reason: LimitationReason | None = None,
    ) -> PortfolioAnswer:
        text = (
            PortfolioRag._limitation_item(reason, locale).text
            if reason is not None
            else {
                Locale.PT_BR: "Não há evidência publicada suficiente para responder com segurança.",
                Locale.EN_US: "There is not enough published evidence to answer safely.",
            }[locale]
        )
        return PortfolioAnswer(
            status=AnswerStatus.INSUFFICIENT,
            answer_items=(LimitationAnswerItem(text=text),),
            citations=(),
        )
