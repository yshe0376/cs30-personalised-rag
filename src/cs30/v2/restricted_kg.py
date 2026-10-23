"""Evidence-bound Restricted KG contracts, extraction, and audit helpers.

The Restricted KG is a sidecar over one immutable v2 corpus.  It deliberately
does not alter chunks or the M1-owned topic map.  Candidate concepts and
relations may be generated automatically, but only reviewed items with exact
corpus evidence can enter the accepted graph.
"""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from cs30.v2.contracts import Chunk
from cs30.v2.contracts.models import Identifier, NonEmptyText, V2Model
from cs30.v2.corpus.records import LoadedCorpus
from cs30.v2.ids import canonical_json_bytes, sha256_text, slug

KG_SCHEMA_VERSION = "2.0"
DEFAULT_KG_VERSION = "restricted-kg-v1"

KGItemStatus = Literal["candidate", "accepted", "quarantined"]
KGRelationType = Literal["prerequisite_of", "applied_to", "next_concept"]
KGAuditSeverity = Literal["info", "warning", "error"]


class KGSourceEvidence(V2Model):
    """An exact excerpt inside one chunk of the graph's pinned corpus."""

    chunk_id: Identifier
    char_start: int = Field(ge=0)
    char_end: int = Field(gt=0)
    quoted_text: NonEmptyText
    text_hash: Identifier

    @model_validator(mode="after")
    def validate_span_and_hash(self) -> KGSourceEvidence:
        if self.char_end <= self.char_start:
            raise ValueError("evidence char_end must be greater than char_start")
        if self.text_hash != sha256_text(self.quoted_text):
            raise ValueError("evidence text_hash does not match quoted_text")
        return self


class KGConcept(V2Model):
    concept_id: Identifier
    label: NonEmptyText
    aliases: tuple[NonEmptyText, ...] = ()
    evidence: tuple[KGSourceEvidence, ...] = Field(min_length=1)
    status: KGItemStatus = "candidate"
    review_reasons: tuple[Identifier, ...] = ("candidate_not_reviewed",)

    @model_validator(mode="after")
    def validate_review_state(self) -> KGConcept:
        if len(set(self.aliases)) != len(self.aliases):
            raise ValueError("concept aliases must be unique")
        _validate_review_reasons(self.status, self.review_reasons, "concept")
        return self


class KGRelation(V2Model):
    relation_id: Identifier
    source_concept_id: Identifier
    target_concept_id: Identifier
    relation_type: KGRelationType
    evidence: tuple[KGSourceEvidence, ...] = Field(min_length=1)
    status: KGItemStatus = "candidate"
    review_reasons: tuple[Identifier, ...] = ("candidate_not_reviewed",)

    @model_validator(mode="after")
    def validate_relation(self) -> KGRelation:
        if self.source_concept_id == self.target_concept_id:
            raise ValueError("a Restricted KG relation cannot be a self-loop")
        _validate_review_reasons(self.status, self.review_reasons, "relation")
        return self


class RestrictedKG(V2Model):
    """Versioned graph sidecar bound to exactly one published v2 corpus."""

    schema_version: Literal["2.0"] = KG_SCHEMA_VERSION
    kg_version: Identifier = DEFAULT_KG_VERSION
    corpus_version: Identifier
    corpus_hash: Identifier
    concepts: tuple[KGConcept, ...] = ()
    relations: tuple[KGRelation, ...] = ()

    @model_validator(mode="after")
    def validate_unique_ids(self) -> RestrictedKG:
        _require_unique((item.concept_id for item in self.concepts), "concept_id")
        _require_unique((item.relation_id for item in self.relations), "relation_id")
        return self


class KGAuditFinding(V2Model):
    code: Identifier
    severity: KGAuditSeverity
    item_id: Identifier | None = None
    message: NonEmptyText


class KGAuditReport(V2Model):
    schema_version: Literal["2.0"] = KG_SCHEMA_VERSION
    kg_version: Identifier
    corpus_version: Identifier
    corpus_hash: Identifier
    concept_count: int = Field(ge=0)
    relation_count: int = Field(ge=0)
    accepted_concept_count: int = Field(ge=0)
    accepted_relation_count: int = Field(ge=0)
    candidate_count: int = Field(ge=0)
    quarantined_count: int = Field(ge=0)
    relation_type_counts: dict[KGRelationType, int] = Field(default_factory=dict)
    findings: tuple[KGAuditFinding, ...] = ()

    @property
    def passed(self) -> bool:
        return not any(finding.severity == "error" for finding in self.findings)


def _validate_review_reasons(
    status: KGItemStatus, review_reasons: tuple[str, ...], owner: str
) -> None:
    if len(set(review_reasons)) != len(review_reasons):
        raise ValueError(f"{owner} review_reasons must be unique")
    if status == "accepted" and review_reasons:
        raise ValueError(f"an accepted {owner} must not carry review_reasons")
    if status != "accepted" and not review_reasons:
        raise ValueError(f"a non-accepted {owner} must explain why it is not accepted")


def _require_unique(values, label: str) -> None:
    values = tuple(values)
    if len(values) != len(set(values)):
        raise ValueError(f"{label} values must be unique")


def _evidence_error(evidence: KGSourceEvidence, chunk: Chunk | None) -> str | None:
    if chunk is None:
        return f"evidence references unknown chunk_id {evidence.chunk_id!r}"
    if evidence.char_start < chunk.char_start or evidence.char_end > chunk.char_end:
        return f"evidence span falls outside chunk {chunk.chunk_id!r}"
    relative_start = evidence.char_start - chunk.char_start
    relative_end = evidence.char_end - chunk.char_start
    if chunk.text[relative_start:relative_end] != evidence.quoted_text:
        return f"evidence quote does not match chunk {chunk.chunk_id!r}"
    return None


def audit_restricted_kg(graph: RestrictedKG, corpus: LoadedCorpus) -> KGAuditReport:
    """Audit corpus identity, evidence, direction risks, and graph integrity."""

    findings: list[KGAuditFinding] = []
    if graph.corpus_version != corpus.manifest.corpus_version:
        findings.append(
            KGAuditFinding(
                code="CORPUS_VERSION_MISMATCH",
                severity="error",
                message="Restricted KG corpus_version does not match the loaded corpus.",
            )
        )
    if graph.corpus_hash != corpus.manifest.corpus_hash:
        findings.append(
            KGAuditFinding(
                code="CORPUS_HASH_MISMATCH",
                severity="error",
                message="Restricted KG corpus_hash does not match the loaded corpus.",
            )
        )

    concepts_by_id = {concept.concept_id: concept for concept in graph.concepts}
    for item in (*graph.concepts, *graph.relations):
        for evidence in item.evidence:
            error = _evidence_error(evidence, corpus.chunks_by_id.get(evidence.chunk_id))
            if error:
                findings.append(
                    KGAuditFinding(
                        code="EVIDENCE_INVALID",
                        severity="error" if item.status == "accepted" else "warning",
                        item_id=item.concept_id
                        if isinstance(item, KGConcept)
                        else item.relation_id,
                        message=error,
                    )
                )

    triples: dict[tuple[str, str, str], list[KGRelation]] = defaultdict(list)
    accepted_prerequisites: set[tuple[str, str]] = set()
    for relation in graph.relations:
        triples[
            (
                relation.source_concept_id,
                relation.relation_type,
                relation.target_concept_id,
            )
        ].append(relation)
        source = concepts_by_id.get(relation.source_concept_id)
        target = concepts_by_id.get(relation.target_concept_id)
        if source is None or target is None:
            findings.append(
                KGAuditFinding(
                    code="RELATION_ENDPOINT_UNKNOWN",
                    severity="error",
                    item_id=relation.relation_id,
                    message="Relation source and target must both exist in the graph.",
                )
            )
        elif relation.status == "accepted" and (
            source.status != "accepted" or target.status != "accepted"
        ):
            findings.append(
                KGAuditFinding(
                    code="ACCEPTED_RELATION_ENDPOINT_NOT_ACCEPTED",
                    severity="error",
                    item_id=relation.relation_id,
                    message="An accepted relation requires two accepted concepts.",
                )
            )
        if relation.status == "accepted" and relation.relation_type == "prerequisite_of":
            accepted_prerequisites.add(
                (relation.source_concept_id, relation.target_concept_id)
            )

    for duplicate_relations in triples.values():
        if len(duplicate_relations) > 1:
            for relation in duplicate_relations:
                findings.append(
                    KGAuditFinding(
                        code="RELATION_DUPLICATE",
                        severity="error" if relation.status == "accepted" else "warning",
                        item_id=relation.relation_id,
                        message="Duplicate relation triple requires consolidation.",
                    )
                )
    for source_id, target_id in sorted(accepted_prerequisites):
        if (target_id, source_id) in accepted_prerequisites and source_id < target_id:
            findings.append(
                KGAuditFinding(
                    code="PREREQUISITE_DIRECTION_CONFLICT",
                    severity="error",
                    message=(
                        "Accepted prerequisite relations exist in both directions for "
                        f"{source_id!r} and {target_id!r}."
                    ),
                )
            )

    candidate_count = sum(
        item.status == "candidate" for item in (*graph.concepts, *graph.relations)
    )
    quarantined_count = sum(
        item.status == "quarantined" for item in (*graph.concepts, *graph.relations)
    )
    relation_type_counts = {
        relation_type: sum(
            relation.relation_type == relation_type for relation in graph.relations
        )
        for relation_type in ("prerequisite_of", "applied_to", "next_concept")
    }
    return KGAuditReport(
        kg_version=graph.kg_version,
        corpus_version=graph.corpus_version,
        corpus_hash=graph.corpus_hash,
        concept_count=len(graph.concepts),
        relation_count=len(graph.relations),
        accepted_concept_count=sum(item.status == "accepted" for item in graph.concepts),
        accepted_relation_count=sum(item.status == "accepted" for item in graph.relations),
        candidate_count=candidate_count,
        quarantined_count=quarantined_count,
        relation_type_counts=relation_type_counts,
        findings=tuple(findings),
    )


def validate_restricted_kg(graph: RestrictedKG, corpus: LoadedCorpus) -> None:
    """Reject a graph with any blocking audit finding."""

    report = audit_restricted_kg(graph, corpus)
    errors = [finding for finding in report.findings if finding.severity == "error"]
    if errors:
        summary = "; ".join(f"{item.code}: {item.message}" for item in errors)
        raise ValueError(summary)


def _normalise_title(title: str) -> str:
    return " ".join(title.split()).casefold()


def _is_core_section(chunk: Chunk) -> bool:
    return bool(
        chunk.section_id
        and chunk.section_title
        and re.fullmatch(r"\d+\.\d+", chunk.section_id)
    )


def _evidence_from_chunk(chunk: Chunk, *, limit: int = 280) -> KGSourceEvidence:
    leading = len(chunk.text) - len(chunk.text.lstrip())
    quoted_text = chunk.text[leading : leading + limit].rstrip()
    if not quoted_text:
        quoted_text = chunk.text[:limit]
        leading = 0
    return KGSourceEvidence(
        chunk_id=chunk.chunk_id,
        char_start=chunk.char_start + leading,
        char_end=chunk.char_start + leading + len(quoted_text),
        quoted_text=quoted_text,
        text_hash=sha256_text(quoted_text),
    )


def extract_restricted_kg_candidates(
    corpus: LoadedCorpus,
    *,
    max_concepts: int = 150,
    max_relations: int = 300,
    kg_version: str = DEFAULT_KG_VERSION,
) -> RestrictedKG:
    """Build deterministic, review-required candidates from numbered sections.

    Section order supplies a defensible ``next_concept`` candidate and a weaker
    ``prerequisite_of`` candidate.  Neither is accepted automatically.  Titles
    containing "application" also produce an ``applied_to`` candidate from the
    preceding section.  This keeps semantic judgement in the review stage.
    """

    if not 1 <= max_concepts <= 150:
        raise ValueError("max_concepts must be between 1 and 150")
    if not 1 <= max_relations <= 300:
        raise ValueError("max_relations must be between 1 and 300")

    section_chunks: dict[tuple[str, str, str], Chunk] = {}
    title_chunks: dict[str, list[Chunk]] = defaultdict(list)
    title_order: list[str] = []
    labels: dict[str, str] = {}
    for chunk in corpus.chunks:
        if not _is_core_section(chunk):
            continue
        key = (chunk.textbook_id, chunk.chapter_id, chunk.section_id or "")
        if key in section_chunks:
            continue
        section_chunks[key] = chunk
        normalised = _normalise_title(chunk.section_title or "")
        if normalised not in labels:
            labels[normalised] = chunk.section_title or ""
            title_order.append(normalised)
        if not any(
            evidence_chunk.textbook_id == chunk.textbook_id
            for evidence_chunk in title_chunks[normalised]
        ):
            title_chunks[normalised].append(chunk)

    selected_titles = title_order[:max_concepts]
    selected_set = set(selected_titles)
    concept_ids = {
        title: f"concept-{slug(labels[title])}" for title in selected_titles
    }
    if len(set(concept_ids.values())) != len(concept_ids):
        concept_ids = {
            title: f"concept-{slug(labels[title])}-{sha256_text(title)[7:15]}"
            for title in selected_titles
        }
    concepts = tuple(
        KGConcept(
            concept_id=concept_ids[title],
            label=labels[title],
            evidence=tuple(
                _evidence_from_chunk(chunk) for chunk in title_chunks[title][:3]
            ),
        )
        for title in selected_titles
    )

    by_chapter: dict[tuple[str, str], list[Chunk]] = defaultdict(list)
    for chunk in section_chunks.values():
        title = _normalise_title(chunk.section_title or "")
        if title in selected_set:
            by_chapter[(chunk.textbook_id, chunk.chapter_id)].append(chunk)

    relation_specs: dict[tuple[str, str, str], tuple[Chunk, Chunk, str]] = {}
    for chapter_chunks in by_chapter.values():
        for source, target in zip(chapter_chunks, chapter_chunks[1:], strict=False):
            source_title = _normalise_title(source.section_title or "")
            target_title = _normalise_title(target.section_title or "")
            source_id = concept_ids[source_title]
            target_id = concept_ids[target_title]
            if source_id == target_id:
                continue
            relation_specs.setdefault(
                (source_id, "next_concept", target_id),
                (source, target, "section_order_requires_review"),
            )
            relation_specs.setdefault(
                (source_id, "prerequisite_of", target_id),
                (source, target, "section_order_is_not_prerequisite_proof"),
            )
            if "application" in target_title:
                relation_specs.setdefault(
                    (source_id, "applied_to", target_id),
                    (source, target, "application_title_requires_review"),
                )

    relations: list[KGRelation] = []
    for ordinal, (spec, support) in enumerate(
        sorted(relation_specs.items()), start=1
    ):
        if len(relations) >= max_relations:
            break
        source_id, relation_type, target_id = spec
        source_chunk, target_chunk, reason = support
        relations.append(
            KGRelation(
                relation_id=f"relation-{ordinal:04d}",
                source_concept_id=source_id,
                target_concept_id=target_id,
                relation_type=relation_type,
                evidence=(
                    _evidence_from_chunk(source_chunk),
                    _evidence_from_chunk(target_chunk),
                ),
                review_reasons=(reason,),
            )
        )

    return RestrictedKG(
        kg_version=kg_version,
        corpus_version=corpus.manifest.corpus_version,
        corpus_hash=corpus.manifest.corpus_hash,
        concepts=concepts,
        relations=tuple(relations),
    )


def canonical_restricted_kg(graph: RestrictedKG) -> RestrictedKG:
    """Return stable concept, relation, evidence, and reason ordering."""

    def sort_evidence(evidence: tuple[KGSourceEvidence, ...]):
        return tuple(sorted(evidence, key=lambda item: (item.chunk_id, item.char_start)))

    concepts = tuple(
        item.model_copy(
            update={
                "aliases": tuple(sorted(item.aliases)),
                "evidence": sort_evidence(item.evidence),
                "review_reasons": tuple(sorted(item.review_reasons)),
            }
        )
        for item in sorted(graph.concepts, key=lambda item: item.concept_id)
    )
    relations = tuple(
        item.model_copy(
            update={
                "evidence": sort_evidence(item.evidence),
                "review_reasons": tuple(sorted(item.review_reasons)),
            }
        )
        for item in sorted(graph.relations, key=lambda item: item.relation_id)
    )
    return graph.model_copy(update={"concepts": concepts, "relations": relations})


def write_restricted_kg(graph: RestrictedKG, path: Path) -> None:
    canonical = canonical_restricted_kg(graph)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(canonical.model_dump(mode="json")))


def load_restricted_kg(path: Path) -> RestrictedKG:
    return RestrictedKG.model_validate_json(path.read_text(encoding="utf-8"))
