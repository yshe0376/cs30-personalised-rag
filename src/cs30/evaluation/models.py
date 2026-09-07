"""Internal evaluation models kept separate from the frozen team contracts."""

from __future__ import annotations

from enum import StrEnum
from math import isclose
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from cs30.contracts.models import ChoiceLabel, Identifier


class EvaluationModel(BaseModel):
    """Strict local model so malformed evaluation inputs fail visibly."""

    model_config = ConfigDict(extra="forbid")


class Answerability(StrEnum):
    """Corpus-relative gold answerability state.

    ``UNRESOLVED`` is deliberately not treated as unanswerable. SciQ support
    that has not aligned to the frozen OpenStax corpus still needs review.
    """

    ANSWERABLE = "answerable"
    VERIFIED_UNANSWERABLE = "verified_unanswerable"
    UNRESOLVED = "unresolved"


class ExecutionStatus(StrEnum):
    """Mutually exclusive run outcome used by failure-aware metrics."""

    COMPLETED = "completed"
    RETRIEVAL_FAILURE = "retrieval_failure"
    GENERATION_CALL_FAILURE = "generation_call_failure"
    PARSE_FAILURE = "parse_failure"
    CITATION_FAILURE = "citation_failure"
    TECHNICAL_FAILURE = "technical_failure"


class EvaluationRecord(EvaluationModel):
    """Schema-independent record consumed by every M8 scorer."""

    schema_version: Literal["0.1"] = "0.1"
    question_id: Identifier
    gold_choice: ChoiceLabel | None = None
    answerability: Answerability = Answerability.UNRESOLVED
    gold_evidence_ids: list[Identifier] = Field(default_factory=list)
    predicted_choice: ChoiceLabel | None = None
    abstained: bool | None = None
    citation_ids: list[Identifier] = Field(default_factory=list)
    retrieved_chunk_ids: list[Identifier] = Field(default_factory=list)
    citation_status: Literal["passed", "failed", "skipped", "unknown"] = "unknown"
    execution_status: ExecutionStatus
    raw_json_valid: bool | None = None
    raw_schema_valid: bool | None = None
    repair_used: bool | None = None
    source_schema: Identifier
    split: Identifier | None = None
    dataset_version: Identifier | None = None
    error: str | None = None

    @model_validator(mode="after")
    def validate_outcome(self) -> EvaluationRecord:
        if self.abstained is True:
            if self.predicted_choice is not None:
                raise ValueError("an abstention cannot have a predicted choice")
            if self.citation_ids:
                raise ValueError("an abstention cannot have citations")
        if len(set(self.citation_ids)) != len(self.citation_ids):
            raise ValueError("citation_ids must be unique")
        if len(set(self.retrieved_chunk_ids)) != len(self.retrieved_chunk_ids):
            raise ValueError("retrieved_chunk_ids must be unique")
        if len(set(self.gold_evidence_ids)) != len(self.gold_evidence_ids):
            raise ValueError("gold_evidence_ids must be unique")
        return self


class RecordScore(EvaluationModel):
    """Auditable per-question result behind aggregate metrics."""

    question_id: Identifier
    answer_outcome: Literal[
        "correct",
        "incorrect",
        "abstained",
        "missing_gold",
        "technical_failure",
    ]
    answer_correct: bool | None
    abstention_correct: bool | None
    citation_valid: bool | None
    gold_citation_hit: bool | None
    execution_status: ExecutionStatus


class MetricResult(EvaluationModel):
    """One metric with an explicit numerator and denominator."""

    numerator: float = Field(ge=0)
    denominator: float = Field(ge=0)
    value: float | None
    excluded: int = Field(default=0, ge=0)
    definition: str

    @model_validator(mode="after")
    def validate_value(self) -> MetricResult:
        expected = None if self.denominator == 0 else self.numerator / self.denominator
        if self.value is None and expected is None:
            return self
        if self.value is None or expected is None or not isclose(self.value, expected):
            raise ValueError("metric value must equal numerator / denominator")
        return self


class EvaluationReport(EvaluationModel):
    """Deterministic report that can be regenerated from saved run files."""

    schema_version: Literal["0.1"] = "0.1"
    total_records: int = Field(ge=0)
    metrics: dict[str, MetricResult]
    failure_counts: dict[ExecutionStatus, int]
    records: list[RecordScore]
