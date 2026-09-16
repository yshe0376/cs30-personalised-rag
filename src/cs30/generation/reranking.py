"""Fixture-first level-aware reranking without changing shared contracts.

Evidence-role labels are supplied as a sidecar mapping keyed by stable chunk ID.
Until M5 freezes the taxonomy, callers must mark the configuration as
``fixture`` and must not present the output as validated personalisation.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from cs30.contracts import (
    EvidenceBundle,
    RetrievalResult,
    StudentLevel,
    StudentProfile,
)

from .evidence import GenerationEvidence, PromptEvidenceItem, evidence_items


class EvidenceRole(StrEnum):
    """Candidate roles from the project design; the taxonomy is not frozen here."""

    DEFINITION = "definition"
    EXAMPLE = "example"
    COMPARISON = "comparison"
    APPLICATION = "application"
    DERIVATION = "derivation"
    BOUNDARY = "boundary"


PREFERRED_ROLES: dict[StudentLevel, frozenset[EvidenceRole]] = {
    StudentLevel.BEGINNER: frozenset({EvidenceRole.DEFINITION, EvidenceRole.EXAMPLE}),
    StudentLevel.INTERMEDIATE: frozenset({EvidenceRole.COMPARISON, EvidenceRole.APPLICATION}),
    StudentLevel.ADVANCED: frozenset({EvidenceRole.DERIVATION, EvidenceRole.BOUNDARY}),
}


@dataclass(frozen=True)
class RoleLabel:
    """Sidecar label for one chunk; multiple roles are explicitly ambiguous."""

    roles: tuple[EvidenceRole, ...]
    source: str = "fixture"

    def __post_init__(self) -> None:
        object.__setattr__(self, "roles", tuple(EvidenceRole(role) for role in self.roles))
        if not self.source.strip():
            raise ValueError("role label source must not be empty")
        if len(set(self.roles)) != len(self.roles):
            raise ValueError("role label roles must be unique")

    @classmethod
    def single(cls, role: EvidenceRole | str, *, source: str = "fixture") -> RoleLabel:
        return cls((EvidenceRole(role),), source=source)


@dataclass(frozen=True)
class RerankConfig:
    """Local configuration with provenance that prevents Test-set tuning."""

    lambda_weight: float = 0.35
    parameter_source: Literal["fixture", "dev"] = "fixture"
    taxonomy_status: Literal["fixture", "frozen"] = "fixture"
    taxonomy_version: str = "candidate-v1"
    normalizer: Literal["minmax-v1"] = "minmax-v1"
    fallback_strategy: Literal["retrieval_only"] = "retrieval_only"

    def __post_init__(self) -> None:
        if not 0.0 <= self.lambda_weight <= 1.0:
            raise ValueError("lambda_weight must be in the interval [0, 1]")
        if self.parameter_source not in {"fixture", "dev"}:
            raise ValueError("parameter_source must be fixture or dev; Test tuning is forbidden")
        if self.taxonomy_status not in {"fixture", "frozen"}:
            raise ValueError("taxonomy_status must be fixture or frozen")
        if self.normalizer != "minmax-v1":
            raise ValueError("normalizer must be minmax-v1")
        if self.fallback_strategy != "retrieval_only":
            raise ValueError("fallback_strategy must be retrieval_only")
        if not self.taxonomy_version.strip():
            raise ValueError("taxonomy_version must not be empty")


@dataclass(frozen=True)
class CandidateScore:
    chunk_id: str
    original_rank: int
    reranked_rank: int
    retrieval_score: float
    normalised_retrieval_score: float
    role: str | None
    role_match: float
    final_score: float
    fallback_reason: str | None = None

    def model_dump(self) -> dict[str, object]:
        return {
            "chunk_id": self.chunk_id,
            "original_rank": self.original_rank,
            "reranked_rank": self.reranked_rank,
            "retrieval_score": self.retrieval_score,
            "normalised_retrieval_score": self.normalised_retrieval_score,
            "role": self.role,
            "role_match": self.role_match,
            "final_score": self.final_score,
            "fallback_reason": self.fallback_reason,
        }


@dataclass(frozen=True)
class RerankTrace:
    enabled: bool
    lambda_weight: float
    confidence: float
    effective_lambda: float
    parameter_source: str
    taxonomy_status: str
    taxonomy_version: str
    normalizer: str
    fallback_strategy: str
    candidates: tuple[CandidateScore, ...]

    def model_dump(self) -> dict[str, object]:
        return {
            "enabled": self.enabled,
            "lambda_weight": self.lambda_weight,
            "confidence": self.confidence,
            "effective_lambda": self.effective_lambda,
            "parameter_source": self.parameter_source,
            "taxonomy_status": self.taxonomy_status,
            "taxonomy_version": self.taxonomy_version,
            "normalizer": self.normalizer,
            "fallback_strategy": self.fallback_strategy,
            "candidates": [candidate.model_dump() for candidate in self.candidates],
        }


@dataclass(frozen=True)
class RerankResult:
    evidence: GenerationEvidence
    trace: RerankTrace


def _normalise_scores(items: Sequence[PromptEvidenceItem]) -> list[float]:
    if not items:
        return []
    scores = [float(item.score) for item in items]
    low = min(scores)
    high = max(scores)
    if high == low:
        return [1.0] * len(items)
    width = high - low
    return [(score - low) / width for score in scores]


def _rebuild_evidence(
    evidence: GenerationEvidence,
    ordered_items: Sequence[PromptEvidenceItem],
) -> GenerationEvidence:
    reranked_items = [
        item.model_copy(update={"rank": rank}) for rank, item in enumerate(ordered_items, 1)
    ]
    if isinstance(evidence, RetrievalResult):
        return evidence.model_copy(update={"hits": reranked_items})
    if isinstance(evidence, EvidenceBundle):
        return evidence.model_copy(update={"evidence_items": reranked_items})
    raise TypeError("generation requires EvidenceBundle or RetrievalResult")


class LevelAwareReranker:
    """Apply the frozen score formula to sidecar-labelled evidence candidates."""

    def __init__(
        self,
        labels: Mapping[str, RoleLabel],
        *,
        config: RerankConfig | None = None,
    ) -> None:
        if any(not isinstance(label, RoleLabel) for label in labels.values()):
            raise TypeError("every sidecar label must be a RoleLabel")
        self.labels = dict(labels)
        self.config = config or RerankConfig()

    def rerank(
        self,
        evidence: GenerationEvidence,
        profile: StudentProfile,
        *,
        enabled: bool = True,
    ) -> RerankResult:
        items = list(evidence_items(evidence))
        normalised = _normalise_scores(items)
        confidence = float(profile.confidence or 0.0)
        effective_lambda = self.config.lambda_weight * confidence if enabled else 0.0
        preferred = PREFERRED_ROLES[profile.level]
        provisional: list[
            tuple[float, int, PromptEvidenceItem, float, str | None, float, str | None]
        ] = []

        for item, retrieval_score in zip(items, normalised, strict=True):
            label = self.labels.get(item.chunk_id)
            role: str | None = None
            fallback_reason: str | None = None
            if label is None or not label.roles:
                role_match = retrieval_score
                fallback_reason = "missing_label"
            elif len(label.roles) != 1:
                role_match = retrieval_score
                role = ",".join(role.value for role in label.roles)
                fallback_reason = "ambiguous_label"
            else:
                selected_role = label.roles[0]
                role = selected_role.value
                role_match = 1.0 if selected_role in preferred else 0.0

            final_score = (1.0 - effective_lambda) * retrieval_score + effective_lambda * role_match
            provisional.append(
                (
                    final_score,
                    item.rank,
                    item,
                    retrieval_score,
                    role,
                    role_match,
                    fallback_reason,
                )
            )

        if effective_lambda == 0.0:
            ordered = provisional
        else:
            ordered = sorted(provisional, key=lambda row: (-row[0], row[1], row[2].chunk_id))

        candidate_scores = tuple(
            CandidateScore(
                chunk_id=item.chunk_id,
                original_rank=original_rank,
                reranked_rank=reranked_rank,
                retrieval_score=float(item.score),
                normalised_retrieval_score=retrieval_score,
                role=role,
                role_match=role_match,
                final_score=final_score,
                fallback_reason=fallback_reason,
            )
            for reranked_rank, (
                final_score,
                original_rank,
                item,
                retrieval_score,
                role,
                role_match,
                fallback_reason,
            ) in enumerate(ordered, 1)
        )
        ordered_items = [row[2] for row in ordered]
        return RerankResult(
            evidence=_rebuild_evidence(evidence, ordered_items),
            trace=RerankTrace(
                enabled=enabled,
                lambda_weight=self.config.lambda_weight,
                confidence=confidence,
                effective_lambda=effective_lambda,
                parameter_source=self.config.parameter_source,
                taxonomy_status=self.config.taxonomy_status,
                taxonomy_version=self.config.taxonomy_version,
                normalizer=self.config.normalizer,
                fallback_strategy=self.config.fallback_strategy,
                candidates=candidate_scores,
            ),
        )
