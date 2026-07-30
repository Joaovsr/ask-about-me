from uuid import UUID

from ask_about_me.inspect_retrieval import RetrievalInspection, inspection_as_dict
from ask_about_me.rag import (
    DocumentType,
    RetrievalQuery,
    RetrievalSignals,
    RetrievedChunk,
    SupportDecision,
    SupportFeatures,
)


def test_retrieval_inspector_json_keeps_raw_scores_and_query_provenance() -> None:
    generation_id = UUID("d737467e-7c27-46f8-9347-3c6265530475")
    chunk = RetrievedChunk(
        id=UUID("98e30019-a72a-4b72-b21f-3ed73f44234f"),
        document_id=UUID("3ba42f3e-280b-4d40-885f-9cc04aa0e228"),
        source_id=UUID("b3f5f421-3314-48d8-b9cc-02cb458890e5"),
        source_revision=2,
        source_slug="candidate_portal",
        document_type=DocumentType.PROFILE,
        title="Portal do Candidato",
        section="Resumo",
        excerpt="Portal público de recrutamento.",
        source_url="/portfolio?project=candidate_portal",
        signals=RetrievalSignals(
            vector_distance=0.3,
            vector_similarity=0.7,
            vector_rank=1,
            text_rank_cd=0.8,
            text_rank=1,
            title_match=True,
            section_match=False,
            rrf_score=(1 / 61) * 2,
            index_generation=generation_id,
            index_profile="embedding=test/fixed/3;lexical=weighted-portuguese-v1",
        ),
    )
    inspection = RetrievalInspection(
        query=RetrievalQuery(
            original_question="Portal do Candidato",
            embedding_text="Portal do Candidato",
            lexical_text="Portal do Candidato",
            history_used=(),
            history_reason=None,
        ),
        chunks=(chunk,),
        support=SupportDecision(
            supported=True,
            rule_version="support-v1",
            features=SupportFeatures(
                best_vector_similarity=0.7,
                best_text_rank_cd=0.8,
                has_title_match=True,
                has_section_match=False,
                channels_agree=True,
                supporting_document_count=1,
            ),
            reasons=("published_title_match",),
            approved_chunks=(chunk,),
        ),
        index_generation=generation_id,
        index_profile=chunk.signals.index_profile,
        retrieval_profile=chunk.signals.retrieval_profile,
    )

    payload = inspection_as_dict(inspection)

    assert payload["query"]["original_question"] == "Portal do Candidato"
    assert payload["chunks"][0]["signals"]["vector_distance"] == 0.3
    assert payload["chunks"][0]["signals"]["text_rank_cd"] == 0.8
    assert payload["chunks"][0]["signals"]["rrf_score"] == (1 / 61) * 2
    assert payload["chunks"][0]["signals"]["title_match"] is True
    assert payload["index_generation"] == str(generation_id)
