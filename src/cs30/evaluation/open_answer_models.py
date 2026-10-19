"""Local, versioned inputs for offline open-answer assessment."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from cs30.v2.contracts import GeneratedAnswer, NonEmptyText, StudentLevel

if TYPE_CHECKING:
    from cs30.v2.generation import V2BatchResult


class ScoringModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Criterion(ScoringModel):
    criterion_id: NonEmptyText
    description: NonEmptyText
    core: bool = False
    reference_span_ids: list[NonEmptyText] = Field(min_length=1)


class NumericTarget(ScoringModel):
    value: float = Field(allow_inf_nan=False)
    accepted_units: list[str] = Field(min_length=1)
    absolute_tolerance: float = Field(default=0.0, ge=0, allow_inf_nan=False)
    relative_tolerance: float = Field(default=0.0, ge=0, allow_inf_nan=False)


class OpenAnswerRubric(ScoringModel):
    schema_version: Literal["0.1"] = "0.1"
    question_id: NonEmptyText
    gold_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    rubric_version: NonEmptyText
    review_record_id: NonEmptyText | None = None
    criteria: list[Criterion] = Field(min_length=1)
    required_paths: list[list[NonEmptyText]] = Field(min_length=1)
    full_credit_answers: list[NonEmptyText] = Field(default_factory=list)
    alias_case_sensitive: bool = True
    numeric_target: NumericTarget | None = None

    @model_validator(mode="after")
    def validate_paths(self) -> OpenAnswerRubric:
        identifiers = [item.criterion_id for item in self.criteria]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("rubric criterion IDs must be unique")
        for path in self.required_paths:
            if not path or len(set(path)) != len(path) or not set(path) <= set(identifiers):
                raise ValueError("each required path must contain unique known criterion IDs")
        if self.numeric_target is not None and (
            len(identifiers) != 1 or self.required_paths != [identifiers]
        ):
            raise ValueError("numeric fast scoring requires one complete result criterion")
        if self.numeric_target is not None and self.full_credit_answers:
            raise ValueError("numeric rubrics cannot bypass unit checking through text aliases")
        return self


class ExpectedAnswer(ScoringModel):
    run_id: NonEmptyText
    question_id: NonEmptyText
    condition_id: NonEmptyText
    student_level: StudentLevel
    generator_model: NonEmptyText


class OpenAnswerExperiment(ScoringModel):
    schema_version: Literal["0.1"] = "0.1"
    matrix_version: NonEmptyText
    gold_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    rubrics_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    cases: list[ExpectedAnswer] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_cases(self) -> OpenAnswerExperiment:
        ids = [case.run_id for case in self.cases]
        cells = [
            (c.question_id, c.condition_id, c.student_level, c.generator_model) for c in self.cases
        ]
        if len(set(ids)) != len(ids) or len(set(cells)) != len(cells):
            raise ValueError(
                "expected run IDs and question/condition/level/model cells must be unique"
            )
        return self


RunStatus = Literal["answered", "abstained", "retrieval_error", "generation_error", "parse_error"]


class OpenAnswerRun(ExpectedAnswer):
    schema_version: Literal["0.1"] = "0.1"
    status: RunStatus
    answer: GeneratedAnswer | None = None
    error: NonEmptyText | None = None

    @classmethod
    def from_v2_result(cls, expected: ExpectedAnswer, result: V2BatchResult) -> OpenAnswerRun:
        """Export a scoring view of a saved V2 batch cell, preserving the original answer."""

        if result.trace.model != expected.generator_model:
            raise ValueError("V2 generation model differs from the expected cell")
        if (result.answer is None) == (result.error is None):
            raise ValueError("V2 result must contain either an answer or a technical error")
        status = (
            "generation_error"
            if result.answer is None
            else ("abstained" if result.answer.abstained else "answered")
        )
        return cls(**expected.model_dump(), status=status, answer=result.answer, error=result.error)

    @model_validator(mode="after")
    def validate_answer(self) -> OpenAnswerRun:
        if self.status in {"answered", "abstained"}:
            if self.answer is None or self.answer.abstained != (self.status == "abstained"):
                raise ValueError("run status must agree with the saved answer's abstention flag")
            if self.error is not None:
                raise ValueError("successful runs must not carry a technical error")
        elif self.answer is not None or self.error is None:
            raise ValueError("technical failures require an error and no final answer")
        return self


class CriterionVerdict(ScoringModel):
    criterion_id: NonEmptyText
    verdict: Literal["met", "missing", "contradicted", "uncertain"]
    answer_quote: str | None
    reason: NonEmptyText


class JudgeAssessment(ScoringModel):
    """The judge supplies observations; the program computes the numeric score."""

    criteria: list[CriterionVerdict]
    critical_error: bool
    critical_error_quote: str | None
    minor_error: bool
    minor_error_quote: str | None
    needs_review: bool
    review_reason: str | None
    rationale: NonEmptyText


class JudgeAttempt(ScoringModel):
    raw_output: str | None
    error: str | None
    reported_model: str | None = None
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)


class OpenAnswerScore(ExpectedAnswer):
    schema_version: Literal["0.1"] = "0.1"
    split: str | None
    gold_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    rubric_sha256: str | None = Field(pattern=r"^[0-9a-f]{64}$")
    rubric_version: str | None
    answer_sha256: str | None = Field(pattern=r"^[0-9a-f]{64}$")
    run_status: RunStatus | Literal["missing"]
    score_status: Literal["scored", "needs_review", "judge_error", "missing_run", "excluded"]
    score: int | None = Field(default=None, ge=0, le=2, strict=True)
    scoring_source: Literal["rule", "judge", "system", "human", "none"]
    reason: NonEmptyText
    assessment: JudgeAssessment | None = None
    judge_model: str | None = None
    judge_prompt_version: str | None = None
    judge_prompt_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    judge_config_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    judge_attempts: list[JudgeAttempt] = Field(default_factory=list)
    cache_hit: bool = False
    judge_calls_this_run: int = Field(default=0, ge=0)
    review_record_id: str | None = None
    human_rater_id: str | None = None

    @model_validator(mode="after")
    def validate_score(self) -> OpenAnswerScore:
        if (self.score_status == "scored") != (self.score is not None):
            raise ValueError("only completed scores may carry a numeric score")
        if self.score_status == "scored" and self.scoring_source == "none":
            raise ValueError("completed scores require an explicit scoring source")
        if self.scoring_source == "human" and not (self.review_record_id and self.human_rater_id):
            raise ValueError("human scores require a review record and rater identity")
        if self.judge_calls_this_run > len(self.judge_attempts):
            raise ValueError("fresh judge call count cannot exceed saved attempts")
        return self


class HumanRating(ScoringModel):
    run_id: NonEmptyText
    answer_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    rubric_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    rater_id: NonEmptyText
    score: int = Field(ge=0, le=2, strict=True)
    note: NonEmptyText


class HumanDecision(HumanRating):
    review_record_id: NonEmptyText
