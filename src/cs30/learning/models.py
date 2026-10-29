"""Server-side state and browser-safe views for the learning demo."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from cs30.concept_check.service import PreparedRound
from cs30.v2.contracts import (
    ConceptCheckGrade,
    ConceptCheckQuestion,
    EvidenceBundle,
    GeneratedAnswer,
    LearnerContextSnapshot,
    LearnerState,
    RetrievalResult,
    StudentLevel,
    TopicResolution,
    ValidatedAnswer,
)


class CitedTopicEvidence(BaseModel):
    """Topic-map assignments for one citation that passed answer validation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    chunk_id: str
    rank: int | None = Field(default=None, ge=1)
    topic_ids: tuple[str, ...] = ()
    approved_topic_ids: tuple[str, ...] = ()


class TopicSelectionCandidate(BaseModel):
    """An approved Topic appearing in the answer's actual cited chunks."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    topic_id: str
    rank_weighted_support: float = Field(ge=0.0, le=1.0)
    cited_chunk_ids: tuple[str, ...] = ()
    sufficient_evidence_chunk_ids: tuple[str, ...] = ()
    evidence_sufficient: bool
    eligible: bool


class TopicSelectionTrace(BaseModel):
    """Auditable, Demo-only Topic choice made before quiz generation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    policy_version: Literal[
        "online-demo-cited-topic-weighted-v1", "online-demo-cited-topic-weighted-v2"
    ]
    policy_validation_status: Literal["demo-only-not-m7-validated"]
    audit_id: str
    profile_id: str
    turn_id: str
    quiz_index: int = Field(ge=1)
    created_at_utc: datetime
    rng_seed: int = Field(ge=0)
    rng_algorithm: str
    rng_draw: float | None = Field(default=None, ge=0.0)
    support_definition: str
    minimum_evidence_rule: str
    approved_topic_ids: tuple[str, ...]
    resolver_status: str
    resolver_error_code: str | None = None
    cited_evidence: tuple[CitedTopicEvidence, ...] = ()
    candidates: tuple[TopicSelectionCandidate, ...] = ()
    selection_method: Literal["weighted_random", "single_candidate", "none"]
    selected_topic_id: str | None = None
    failure_reason: str | None = None


class OnlineQuizView(BaseModel):
    """Only fields that may be rendered before the learner submits an answer."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    turn_id: str
    quiz_index: int
    practice_id: str | None = None
    status: Literal["pending", "offered", "unavailable", "interrupted", "expired", "submitted"]
    topic_id: str | None = None
    candidate_topic_ids: tuple[str, ...] = ()
    topic_selection_trace: TopicSelectionTrace | None = None
    difficulty: StudentLevel | None = None
    question: str | None = None
    options: dict[str, str] = field(default_factory=dict)
    notice: str
    evidence_labels: tuple[str, ...] = ()


@dataclass
class LearningTurn:
    turn_id: str
    question: str
    status: Literal["pending", "answered", "failed", "interrupted"] = "pending"
    retrieval: RetrievalResult | None = None
    reranked_retrieval: RetrievalResult | None = None
    prepared: PreparedRound | None = None
    snapshot: LearnerContextSnapshot | None = None
    evidence: EvidenceBundle | None = None
    answer: GeneratedAnswer | None = None
    validated_answer: ValidatedAnswer | None = None
    rerank_trace: dict[str, object] = field(default_factory=dict)
    retrieval_topic: TopicResolution | None = None
    retrieval_ms: float = 0.0
    generation_ms: float = 0.0
    api_requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    answer_trace: object | None = None
    error: str | None = None
    quizzes: dict[int, OnlineQuizView] = field(default_factory=dict)
    private_quizzes: dict[int, OnlineQuizRecord] = field(default_factory=dict)
    practice_results: dict[str, PracticeResult] = field(default_factory=dict)
    comparison: dict[str, str] = field(default_factory=dict)
    comparison_done: bool = False


@dataclass
class OnlineQuizRecord:
    turn_id: str
    quiz_index: int
    practice_id: str
    question: ConceptCheckQuestion
    topic_id: str
    evidence_chunk_ids: tuple[str, ...]
    attempt_id: str
    event_id: str
    topic_selection_trace: TopicSelectionTrace | None = None
    auto_check_status: Literal["passed", "evidence_bound"] = "evidence_bound"
    verifier_model: str = ""
    status: Literal["offered", "submitted", "skipped", "interrupted", "expired"] = "offered"
    selected_choice: str | None = None
    grade: ConceptCheckGrade | None = None


@dataclass(frozen=True)
class PracticeResult:
    grade: ConceptCheckGrade
    learner_state: LearnerState
    correct_answer: str
    explanation: str
    topic_id: str
    level_before: StudentLevel
    level_after: StudentLevel
