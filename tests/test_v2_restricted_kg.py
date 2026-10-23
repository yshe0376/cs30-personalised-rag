"""Tests for the evidence-bound Restricted KG sidecar."""

from __future__ import annotations

from types import MappingProxyType, SimpleNamespace

import pytest

from cs30.v2.ids import sha256_text
from cs30.v2.restricted_kg import (
    KGConcept,
    KGRelation,
    KGSourceEvidence,
    RestrictedKG,
    audit_restricted_kg,
    extract_restricted_kg_candidates,
    validate_restricted_kg,
)


def _evidence() -> KGSourceEvidence:
    return KGSourceEvidence(
        chunk_id="chunk-1",
        char_start=10,
        char_end=15,
        quoted_text="force",
        text_hash=sha256_text("force"),
    )


def _corpus():
    chunk = SimpleNamespace(
        chunk_id="chunk-1",
        char_start=10,
        char_end=20,
        text="force mass",
    )
    return SimpleNamespace(
        manifest=SimpleNamespace(
            corpus_version="2.0.0-dev.test",
            corpus_hash="sha256:corpus",
        ),
        chunks_by_id=MappingProxyType({"chunk-1": chunk}),
    )


def _concept(concept_id: str, *, accepted: bool = True) -> KGConcept:
    return KGConcept(
        concept_id=concept_id,
        label=concept_id,
        evidence=(_evidence(),),
        status="accepted" if accepted else "candidate",
        review_reasons=() if accepted else ("candidate_not_reviewed",),
    )


def test_accepted_items_cannot_keep_review_reasons() -> None:
    with pytest.raises(ValueError, match="must not carry"):
        KGConcept(
            concept_id="force",
            label="Force",
            evidence=(_evidence(),),
            status="accepted",
            review_reasons=("candidate_not_reviewed",),
        )


def test_a_valid_accepted_graph_passes_the_corpus_audit() -> None:
    graph = RestrictedKG(
        corpus_version="2.0.0-dev.test",
        corpus_hash="sha256:corpus",
        concepts=(_concept("force"), _concept("motion")),
        relations=(
            KGRelation(
                relation_id="relation-1",
                source_concept_id="force",
                target_concept_id="motion",
                relation_type="applied_to",
                evidence=(_evidence(),),
                status="accepted",
                review_reasons=(),
            ),
        ),
    )

    validate_restricted_kg(graph, _corpus())
    assert audit_restricted_kg(graph, _corpus()).passed


def test_tampered_evidence_blocks_an_accepted_graph() -> None:
    bad_evidence = _evidence().model_copy(
        update={"quoted_text": "wrong", "text_hash": sha256_text("wrong")}
    )
    graph = RestrictedKG(
        corpus_version="2.0.0-dev.test",
        corpus_hash="sha256:corpus",
        concepts=(
            KGConcept(
                concept_id="force",
                label="Force",
                evidence=(bad_evidence,),
                status="accepted",
                review_reasons=(),
            ),
        ),
    )

    with pytest.raises(ValueError, match="EVIDENCE_INVALID"):
        validate_restricted_kg(graph, _corpus())


def test_accepted_relation_requires_accepted_endpoints() -> None:
    graph = RestrictedKG(
        corpus_version="2.0.0-dev.test",
        corpus_hash="sha256:corpus",
        concepts=(_concept("force"), _concept("motion", accepted=False)),
        relations=(
            KGRelation(
                relation_id="relation-1",
                source_concept_id="force",
                target_concept_id="motion",
                relation_type="next_concept",
                evidence=(_evidence(),),
                status="accepted",
                review_reasons=(),
            ),
        ),
    )

    with pytest.raises(ValueError, match="ACCEPTED_RELATION_ENDPOINT_NOT_ACCEPTED"):
        validate_restricted_kg(graph, _corpus())


def test_duplicate_and_reverse_prerequisites_fail_audit() -> None:
    relation = KGRelation(
        relation_id="relation-1",
        source_concept_id="force",
        target_concept_id="motion",
        relation_type="prerequisite_of",
        evidence=(_evidence(),),
        status="accepted",
        review_reasons=(),
    )
    graph = RestrictedKG(
        corpus_version="2.0.0-dev.test",
        corpus_hash="sha256:corpus",
        concepts=(_concept("force"), _concept("motion")),
        relations=(
            relation,
            relation.model_copy(update={"relation_id": "relation-2"}),
            relation.model_copy(
                update={
                    "relation_id": "relation-3",
                    "source_concept_id": "motion",
                    "target_concept_id": "force",
                }
            ),
        ),
    )

    codes = {finding.code for finding in audit_restricted_kg(graph, _corpus()).findings}
    assert "RELATION_DUPLICATE" in codes
    assert "PREREQUISITE_DIRECTION_CONFLICT" in codes


def test_extractor_keeps_section_order_relations_in_review() -> None:
    def chunk(chunk_id: str, section_id: str, title: str, start: int):
        text = f"Evidence for {title}."
        return SimpleNamespace(
            chunk_id=chunk_id,
            textbook_id="physics-book",
            chapter_id="1",
            section_id=section_id,
            section_title=title,
            char_start=start,
            char_end=start + len(text),
            text=text,
        )

    corpus = SimpleNamespace(
        manifest=SimpleNamespace(
            corpus_version="2.0.0-dev.test",
            corpus_hash="sha256:corpus",
        ),
        chunks=(
            chunk("chunk-1", "1.1", "Force", 10),
            chunk("chunk-2", "1.2", "Motion", 50),
            chunk("chunk-3", "1.glossary", "Glossary", 90),
        ),
    )

    graph = extract_restricted_kg_candidates(
        corpus, max_concepts=10, max_relations=10
    )

    assert [item.label for item in graph.concepts] == ["Force", "Motion"]
    assert {item.relation_type for item in graph.relations} == {
        "next_concept",
        "prerequisite_of",
    }
    assert all(item.status == "candidate" for item in graph.relations)
    assert all(item.review_reasons for item in graph.relations)
