"""Strict M8-owned models for the V2 generation evaluation extension.

The models in this module deliberately do not change the shared Gold, run-result,
generation, retrieval, or Role-label contracts.  Upstream artifacts are adapted
into these evaluation-only records and remain hash-bound to their source files.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field, field_validator, model_validator

from cs30.contracts import StudentLevel
from cs30.contracts.models import ContractModel, Identifier, NonEmptyText

from .evidence_quotes import merge_quote_rows
from .models import PersonalisationEligibility


def _validate_sha256(value: str, field_name: str) -> str:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"{field_name} must be a lowercase SHA-256 hex digest")
    return value


_MODEL_SIZE_SUFFIX = re.compile(r"(?:[-_:]?\d+(?:\.\d+)?[bm])(?:[-_:].*)?$", re.IGNORECASE)


def canonical_model_family(value: str) -> str:
    """Normalize model revisions and size suffixes before family comparisons."""

    family = value.strip().casefold().rsplit("/", 1)[-1].split(":", 1)[0]
    if family == "gemini" or family.startswith("gemini-"):
        return "gemini"
    family = _MODEL_SIZE_SUFFIX.sub("", family).rstrip("-_:")
    return family


class EvaluationMode(StrEnum):
    DEVELOPMENT = "development"
    REPORTABLE = "reportable"


class ExperimentArm(StrEnum):
    P0R0_PLAIN = "P0R0_plain"
    P1R0_PROMPT_ONLY = "P1R0_prompt_only"
    P0R1_RERANKING_ONLY = "P0R1_reranking_only"
    P1R1_COMBINED = "P1R1_combined"


class GenerationRunStatus(StrEnum):
    """Statuses preserved exactly from the M7 GenerationRun contract."""

    ANSWERED = "answered"
    ABSTAINED = "abstained"
    RETRIEVAL_ERROR = "retrieval_error"
    GENERATION_ERROR = "generation_error"
    PARSE_ERROR = "parse_error"
    OUTPUT_TRUNCATED = "output_truncated"

    @property
    def is_technical_failure(self) -> bool:
        return self in {
            self.RETRIEVAL_ERROR,
            self.GENERATION_ERROR,
            self.PARSE_ERROR,
            self.OUTPUT_TRUNCATED,
        }


class JudgeTask(StrEnum):
    ADAPTATION = "adaptation"
    DISCRIMINATION = "discrimination"
    EVIDENCE_SUPPORT = "evidence_support"


class CriterionVerdict(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    NOT_APPLICABLE = "not_applicable"


class SupportVerdict(StrEnum):
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    NOT_APPLICABLE = "not_applicable"


class LevelGuess(StrEnum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    UNCERTAIN = "uncertain"


class ApprovalStatus(StrEnum):
    APPROVED = "approved"
    NOT_REQUIRED = "not_required"
    PENDING = "pending"
    REJECTED = "rejected"


class AnchorExample(ContractModel):
    """A non-Gold anchor used to interpret one frozen learner-level profile."""

    anchor_id: Identifier
    question: NonEmptyText
    answer: NonEmptyText
    rationale: NonEmptyText
    is_gold: Literal[False] = False


class LevelProfile(ContractModel):
    """One global learner-level portrait, independent of generation guidance."""

    schema_version: Literal["1.0"] = "1.0"
    profile_version: Identifier
    level: StudentLevel
    student_positioning: NonEmptyText
    assumed_physics_background: list[NonEmptyText] = Field(min_length=1)
    assumed_mathematics_background: list[NonEmptyText] = Field(min_length=1)
    terms_allowed_without_explanation: list[NonEmptyText] = Field(default_factory=list)
    acceptable_inference_span: NonEmptyText
    omittable_intermediate_steps: list[NonEmptyText] = Field(default_factory=list)
    helpful_writing_patterns: list[NonEmptyText] = Field(min_length=1)
    harmful_writing_patterns: list[NonEmptyText] = Field(min_length=1)
    anchor_examples: list[AnchorExample] = Field(min_length=2, max_length=3)

    @model_validator(mode="after")
    def validate_unique_anchors(self) -> LevelProfile:
        anchor_ids = [anchor.anchor_id for anchor in self.anchor_examples]
        if len(anchor_ids) != len(set(anchor_ids)):
            raise ValueError("anchor example IDs must be unique within a profile")
        return self


class ChecklistCriterion(ContractModel):
    """One frozen, auditable level-adaptation criterion."""

    criterion_id: Identifier
    level: StudentLevel
    description: NonEmptyText


class LevelChecklist(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    checklist_version: Identifier
    level: StudentLevel
    criteria: list[ChecklistCriterion] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_criteria(self) -> LevelChecklist:
        expected = {
            StudentLevel.BEGINNER: {"B1", "B2", "B3", "B4"},
            StudentLevel.INTERMEDIATE: {"I1", "I2", "I3"},
            StudentLevel.ADVANCED: {"A1", "A2", "A3", "A4"},
        }[self.level]
        actual = {criterion.criterion_id for criterion in self.criteria}
        if actual != expected:
            raise ValueError(
                f"{self.level.value} checklist requires criteria {sorted(expected)}; "
                f"received {sorted(actual)}"
            )
        if any(criterion.level is not self.level for criterion in self.criteria):
            raise ValueError("every criterion level must match its checklist level")
        return self


class PhysicsReviewWaiver(ContractModel):
    """Leader decision to freeze a package without an independent physics review."""

    waived_by: Identifier
    decided_at: datetime
    reason: NonEmptyText
    decision_record: NonEmptyText

    @field_validator("decided_at")
    @classmethod
    def validate_timezone(cls, value: datetime) -> datetime:
        if value.utcoffset() is None:
            raise ValueError("waiver timestamps must include a timezone")
        return value


class ProfileChecklistPackage(ContractModel):
    """All three profiles and checklists frozen as one evaluation input."""

    schema_version: Literal["1.0"] = "1.0"
    package_version: Identifier
    generation_guidance_version: Identifier
    profiles_independent_of_generation_guidance: Literal[True] = True
    generation_guidance_consistency: Literal["consistent", "mismatch_recorded"]
    generation_guidance_mismatch_notes: NonEmptyText | None = None
    author_ids: list[Identifier] = Field(min_length=1)
    physics_reviewer_ids: list[Identifier] = Field(default_factory=list)
    physics_review_waiver: PhysicsReviewWaiver | None = None
    frozen: Literal[True] = True
    profiles: list[LevelProfile] = Field(min_length=3, max_length=3)
    checklists: list[LevelChecklist] = Field(min_length=3, max_length=3)
    package_sha256: str

    @model_validator(mode="after")
    def validate_complete_package(self) -> ProfileChecklistPackage:
        expected = set(StudentLevel)
        profile_levels = {profile.level for profile in self.profiles}
        checklist_levels = {checklist.level for checklist in self.checklists}
        if profile_levels != expected or checklist_levels != expected:
            raise ValueError("profile/checklist package must contain all three levels exactly once")
        if len(profile_levels) != len(self.profiles) or len(checklist_levels) != len(
            self.checklists
        ):
            raise ValueError("profile/checklist levels must be unique")
        profile_versions = {profile.profile_version for profile in self.profiles}
        checklist_versions = {checklist.checklist_version for checklist in self.checklists}
        if len(profile_versions) != 1 or len(checklist_versions) != 1:
            raise ValueError("all profiles and checklists must use one frozen version each")
        if (
            self.generation_guidance_consistency == "mismatch_recorded"
            and self.generation_guidance_mismatch_notes is None
        ):
            raise ValueError("a generation-guidance mismatch requires notes")
        if (
            self.generation_guidance_consistency == "consistent"
            and self.generation_guidance_mismatch_notes is not None
        ):
            raise ValueError("consistent guidance must not carry mismatch notes")
        if self.frozen and bool(self.physics_reviewer_ids) == (
            self.physics_review_waiver is not None
        ):
            raise ValueError(
                "a frozen package requires physics reviewer IDs or a Leader waiver, not both"
            )
        _validate_sha256(self.package_sha256, "package_sha256")
        return self


class EligibilityRecord(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    question_id: Identifier
    eligibility: PersonalisationEligibility
    reason: NonEmptyText
    annotator_id: Identifier
    calibration_version: Identifier


class EligibilityPackage(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    package_version: Identifier
    gold_version: Identifier
    gold_sha256: str
    calibration_question_count: int = Field(ge=15, le=20)
    leader_calibration_record_sha256: str
    label_provenance_record_sha256: str
    records: list[EligibilityRecord] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_package(self) -> EligibilityPackage:
        _validate_sha256(self.gold_sha256, "gold_sha256")
        _validate_sha256(
            self.leader_calibration_record_sha256,
            "leader_calibration_record_sha256",
        )
        _validate_sha256(
            self.label_provenance_record_sha256,
            "label_provenance_record_sha256",
        )
        question_ids = [record.question_id for record in self.records]
        if len(question_ids) != len(set(question_ids)):
            raise ValueError("eligibility package contains duplicate question_id values")
        return self


class EvaluationEvidence(ContractModel):
    evidence_id: Identifier
    text: NonEmptyText
    rank: int = Field(ge=1)
    role: Identifier | None = None
    source_locator: NonEmptyText | None = None


class GenerationEvaluationInput(ContractModel):
    """Evaluation-only view of one saved generated answer."""

    schema_version: Literal["1.0"] = "1.0"
    evaluation_id: Identifier
    run_id: Identifier
    question_id: Identifier
    question: NonEmptyText
    answer: NonEmptyText | None
    target_level: StudentLevel
    condition: ExperimentArm
    lambda_weight: float = Field(ge=0.0, le=1.0)
    generation_model_family: Identifier
    generation_model_revision: Identifier
    source_split: Identifier = "dev"
    generation_seed: int | None = None
    prompt_sha256: str | None = None
    eligibility: PersonalisationEligibility
    evidence: list[EvaluationEvidence] = Field(default_factory=list)
    citation_ids: list[Identifier] = Field(default_factory=list)
    source_status: GenerationRunStatus = GenerationRunStatus.ANSWERED
    abstained: bool = False
    technical_failure: bool = False
    failure_reason: NonEmptyText | None = None
    source_artifact_sha256: str
    source_run_sha256: str | None = None
    answer_sha256: str | None = None

    @model_validator(mode="before")
    @classmethod
    def preserve_legacy_failure_inputs(cls, value: object) -> object:
        """Map pre-status M8 failure rows to a generic generation error."""

        if (
            isinstance(value, dict)
            and value.get("technical_failure")
            and "source_status" not in value
        ):
            return {**value, "source_status": GenerationRunStatus.GENERATION_ERROR}
        return value

    @model_validator(mode="after")
    def validate_input(self) -> GenerationEvaluationInput:
        _validate_sha256(self.source_artifact_sha256, "source_artifact_sha256")
        if self.source_run_sha256 is not None:
            _validate_sha256(self.source_run_sha256, "source_run_sha256")
        if self.prompt_sha256 is not None:
            _validate_sha256(self.prompt_sha256, "prompt_sha256")
        if self.answer_sha256 is not None:
            _validate_sha256(self.answer_sha256, "answer_sha256")
        if self.technical_failure != self.source_status.is_technical_failure:
            raise ValueError("technical_failure must agree with source_status")
        if self.abstained != (self.source_status is GenerationRunStatus.ABSTAINED):
            raise ValueError("abstained must agree with source_status")
        if self.technical_failure:
            if self.answer is not None:
                raise ValueError("technical failures must not contain an answer")
            if self.failure_reason is None:
                raise ValueError("technical failures require failure_reason")
        elif self.answer is None:
            raise ValueError("non-failure evaluation inputs require an answer")
        expected_answer_sha256 = (
            hashlib.sha256(self.answer.encode("utf-8")).hexdigest()
            if self.answer is not None
            else None
        )
        if self.answer_sha256 is not None and self.answer_sha256 != expected_answer_sha256:
            raise ValueError("answer_sha256 must match the exact saved answer bytes")
        evidence_ids = [item.evidence_id for item in self.evidence]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("evidence IDs must be unique")
        if any(citation not in set(evidence_ids) for citation in self.citation_ids):
            raise ValueError("citation_ids must reference evidence actually sent to generation")
        return self


class JudgeConfiguration(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    config_version: Identifier
    provider: Identifier
    model_family: Identifier
    model_revision: Identifier
    temperature: float = Field(ge=0.0)
    seed: int | None = None
    thinking_level: Literal["minimal", "low", "medium", "high"] | None = None
    prompt_version: Identifier
    output_schema_version: Identifier
    local_model: bool
    data_approval: ApprovalStatus
    allow_same_family_exploratory: bool = False
    role_label_model_families: list[Identifier] = Field(default_factory=list)
    role_label_family_overlap_disclosure: NonEmptyText | None = None

    @model_validator(mode="after")
    def validate_role_label_overlap(self) -> JudgeConfiguration:
        if self.provider.casefold() == "gemini" and self.thinking_level is None:
            raise ValueError("Gemini judge configurations must freeze thinking_level")
        overlap = canonical_model_family(self.model_family) in {
            canonical_model_family(family) for family in self.role_label_model_families
        }
        if overlap and self.role_label_family_overlap_disclosure is None:
            raise ValueError("judge/Role-label model-family overlap requires disclosure")
        return self

    def assert_allowed(self, generation_model_family: str, mode: EvaluationMode) -> None:
        if not self.local_model and self.data_approval is not ApprovalStatus.APPROVED:
            raise ValueError("third-party judge use requires approved data transfer")
        same_family = canonical_model_family(self.model_family) == canonical_model_family(
            generation_model_family
        )
        if same_family and not self.allow_same_family_exploratory:
            raise ValueError("judge model family must differ from generation model family")
        if mode is EvaluationMode.REPORTABLE and self.allow_same_family_exploratory:
            raise ValueError("same-family exploratory judges cannot produce reportable results")


class JudgeRequest(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    task: JudgeTask
    request_id: Identifier
    input_sha256: str
    config_sha256: str
    system_instruction: NonEmptyText
    payload: dict[str, object]

    @model_validator(mode="after")
    def validate_hashes(self) -> JudgeRequest:
        _validate_sha256(self.input_sha256, "input_sha256")
        _validate_sha256(self.config_sha256, "config_sha256")
        return self


class CriterionJudgement(ContractModel):
    criterion_id: Identifier
    verdict: CriterionVerdict
    exact_quote: NonEmptyText | None
    reason: NonEmptyText

    @model_validator(mode="after")
    def validate_quote(self) -> CriterionJudgement:
        if self.verdict is CriterionVerdict.PASS and not self.exact_quote:
            raise ValueError("passing criterion judgements require an exact answer quote")
        if self.verdict is CriterionVerdict.NOT_APPLICABLE and self.exact_quote is not None:
            raise ValueError("not-applicable criterion judgements require a null quote")
        return self


class AdaptationJudgeOutput(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    request_id: Identifier
    criteria: list[CriterionJudgement] = Field(min_length=1)


class DiscriminationJudgeOutput(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    request_id: Identifier
    predicted_level: LevelGuess
    exact_quote: NonEmptyText | None
    reason: NonEmptyText


class ClaimSupportJudgement(ContractModel):
    claim_id: Identifier
    claim_text: NonEmptyText
    bundle_support: SupportVerdict
    citation_support: SupportVerdict
    supporting_evidence_ids: list[Identifier]
    evidence_quotes: dict[Identifier, NonEmptyText]
    reason: NonEmptyText

    @field_validator("evidence_quotes", mode="before")
    @classmethod
    def normalize_online_quote_rows(cls, value: object) -> object:
        return merge_quote_rows(value)


class EvidenceSupportJudgeOutput(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    request_id: Identifier
    claims: list[ClaimSupportJudgement] = Field(min_length=1)


class JudgeResultEnvelope(ContractModel):
    """Cacheable raw/validated result for one blinded judge request."""

    schema_version: Literal["1.0"] = "1.0"
    task: JudgeTask
    request_id: Identifier
    cache_key: str
    judge_config_version: Identifier
    judge_execution_id: Identifier | None = None
    model_digest: NonEmptyText | None = None
    context_window: int | None = Field(default=None, gt=0)
    output: dict[str, object] | None = None
    raw_output: dict[str, object] | None = None
    unresolved: bool = False
    error: NonEmptyText | None = None
    provider_response_id: NonEmptyText | None = None
    completed_at_utc: NonEmptyText | None = None
    reported_model: NonEmptyText | None = None
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    thought_tokens: int = Field(default=0, ge=0)
    cache_hit: bool = False
    attempt_count: int | None = Field(default=None, ge=0)
    usage_complete: bool | None = None

    @model_validator(mode="after")
    def validate_envelope(self) -> JudgeResultEnvelope:
        _validate_sha256(self.cache_key, "cache_key")
        if self.unresolved:
            if self.error is None:
                raise ValueError("unresolved judge results require an error")
        elif self.output is None:
            raise ValueError("resolved judge results require output")
        if not self.unresolved and self.completed_at_utc is None:
            raise ValueError("resolved judge results require a provider completion timestamp")
        if self.completed_at_utc is not None:
            try:
                completed_at = datetime.fromisoformat(
                    self.completed_at_utc.replace("Z", "+00:00")
                )
            except ValueError as exc:
                raise ValueError("completed_at_utc must be an ISO-8601 timestamp") from exc
            if completed_at.tzinfo is None or completed_at.utcoffset() is None:
                raise ValueError("completed_at_utc must include a UTC offset")
        return self


class EvaluationDecisionConfig(ContractModel):
    """Team-frozen decisions required before a reportable evaluation."""

    schema_version: Literal["1.0"] = "1.0"
    decision_version: Identifier
    eligibility_definition_version: Identifier | None = None
    judge_config_version: Identifier | None = None
    validity_threshold_version: Identifier | None = None
    correctness_noninferiority_delta: float | None = Field(default=None, ge=0.0, le=1.0)
    correctness_rubric_set_sha256: str | None = None
    adaptation_pass_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    lambda_selection_artifact_sha256: str | None = None
    selected_lambda: float | None = Field(default=None, gt=0.0, le=1.0)
    primary_metric: Identifier | None = None
    primary_contrast: Identifier | None = None
    multiplicity_policy: NonEmptyText | None = None
    new_test_id: Identifier | None = None
    human_audit_rubric_sha256: str | None = None
    new_test_approved: bool = False
    scoring_plan_approved: bool = False

    def missing_reportable_decisions(self) -> list[str]:
        required = {
            "eligibility_definition_version": self.eligibility_definition_version,
            "judge_config_version": self.judge_config_version,
            "validity_threshold_version": self.validity_threshold_version,
            "correctness_noninferiority_delta": self.correctness_noninferiority_delta,
            "correctness_rubric_set_sha256": self.correctness_rubric_set_sha256,
            "adaptation_pass_threshold": self.adaptation_pass_threshold,
            "lambda_selection_artifact_sha256": self.lambda_selection_artifact_sha256,
            "selected_lambda": self.selected_lambda,
            "primary_metric": self.primary_metric,
            "primary_contrast": self.primary_contrast,
            "multiplicity_policy": self.multiplicity_policy,
            "new_test_id": self.new_test_id,
            "human_audit_rubric_sha256": self.human_audit_rubric_sha256,
        }
        missing = [name for name, value in required.items() if value is None]
        if not self.new_test_approved:
            missing.append("new_test_approved")
        if not self.scoring_plan_approved:
            missing.append("scoring_plan_approved")
        if self.lambda_selection_artifact_sha256 is not None:
            _validate_sha256(
                self.lambda_selection_artifact_sha256,
                "lambda_selection_artifact_sha256",
            )
        if self.correctness_rubric_set_sha256 is not None:
            _validate_sha256(
                self.correctness_rubric_set_sha256,
                "correctness_rubric_set_sha256",
            )
        if self.human_audit_rubric_sha256 is not None:
            _validate_sha256(
                self.human_audit_rubric_sha256,
                "human_audit_rubric_sha256",
            )
        return missing


class CorrectnessScoreBinding(ContractModel):
    """M8-owned provenance sidecar for one imported correctness-score file."""

    schema_version: Literal["1.0"] = "1.0"
    score_sha256: str
    evaluation_inputs_sha256: str
    source_run_sha256: str
    gold_sha256: str
    record_count: int = Field(ge=1)
    identity_set_sha256: str
    rubric_set_sha256: str
    generator_models: list[Identifier] = Field(min_length=1)
    source_splits: list[Identifier] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_hashes(self) -> CorrectnessScoreBinding:
        for name in (
            "score_sha256",
            "evaluation_inputs_sha256",
            "source_run_sha256",
            "gold_sha256",
            "identity_set_sha256",
            "rubric_set_sha256",
        ):
            _validate_sha256(str(getattr(self, name)), name)
        if len(self.generator_models) != len(set(self.generator_models)):
            raise ValueError("generator_models must be unique")
        if len(self.source_splits) != len(set(self.source_splits)):
            raise ValueError("source_splits must be unique")
        return self
