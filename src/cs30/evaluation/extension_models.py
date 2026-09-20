"""M8-owned inputs for the personalisation evaluation reporting extension.

These models deliberately sit outside the shared run-result contract.  They
annotate saved scoring records for cross-run reporting without requiring M1,
M3, M6, or M7 to change their public schemas.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from cs30.contracts import StudentLevel
from cs30.contracts.models import ContractModel, Identifier, NonEmptyText

from .models import EvaluationSplit, ExecutionMode


class ExperimentCondition(ContractModel):
    """Reporting metadata joined to one saved per-question score record."""

    schema_version: Literal["0.1"] = "0.1"
    run_id: Identifier
    question_id: Identifier
    condition_id: Identifier
    comparison_id: Identifier
    textbook_id: Identifier
    student_level: StudentLevel
    execution_mode: ExecutionMode
    chunk_version: Identifier
    mapping_version: Identifier
    index_version: Identifier
    lambda_weight: float = Field(ge=0.0, le=1.0)
    lambda_status: Literal["baseline", "frozen"]

    @model_validator(mode="after")
    def validate_lambda_status(self) -> ExperimentCondition:
        if self.lambda_status == "baseline" and self.lambda_weight != 0.0:
            raise ValueError("baseline experiment contexts require lambda_weight=0")
        return self


class ExpectedExperimentCell(ContractModel):
    """One required formal experiment group and its exact question coverage."""

    schema_version: Literal["0.1"] = "0.1"
    mode: Identifier
    execution_mode: ExecutionMode
    data_version: Identifier
    split: EvaluationSplit
    corpus_version: Identifier
    chunk_version: Identifier
    mapping_version: Identifier
    index_version: Identifier
    textbook_id: Identifier
    student_level: StudentLevel
    comparison_id: Identifier
    condition_id: Identifier
    lambda_weight: float = Field(ge=0.0, le=1.0)
    lambda_status: Literal["baseline", "frozen"]
    expected_question_ids: list[Identifier] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_cell(self) -> ExpectedExperimentCell:
        if self.lambda_status == "baseline" and self.lambda_weight != 0.0:
            raise ValueError("baseline experiment cells require lambda_weight=0")
        if len(set(self.expected_question_ids)) != len(self.expected_question_ids):
            raise ValueError("expected_question_ids must be unique within a cell")
        return self


class ExpectedExperimentManifest(ContractModel):
    """Frozen acceptance matrix for one formal evaluation report."""

    schema_version: Literal["0.1"] = "0.1"
    matrix_version: Identifier
    cells: list[ExpectedExperimentCell] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_cells(self) -> ExpectedExperimentManifest:
        keys = [
            (
                cell.mode,
                cell.execution_mode,
                cell.data_version,
                cell.split,
                cell.corpus_version,
                cell.chunk_version,
                cell.mapping_version,
                cell.index_version,
                cell.textbook_id,
                cell.student_level,
                cell.comparison_id,
                cell.condition_id,
                cell.lambda_weight,
                cell.lambda_status,
            )
            for cell in self.cells
        ]
        if len(keys) != len(set(keys)):
            raise ValueError("expected experiment cells must be unique")
        return self


class LevelAdaptationRating(ContractModel):
    """One blinded manual rating of answer suitability for a learner level."""

    schema_version: Literal["0.1"] = "0.1"
    rating_id: Identifier
    question_id: Identifier
    blinded_answer_id: Identifier
    assigned_level: StudentLevel
    score: float = Field(allow_inf_nan=False)
    rubric_version: Identifier
    rater_id: Identifier
    notes: NonEmptyText | None = None


class BlindedAnswerKey(ContractModel):
    """Private post-rating key from a blinded answer identifier to a saved run."""

    schema_version: Literal["0.1"] = "0.1"
    blinded_answer_id: Identifier
    run_id: Identifier


class LevelAdaptationRubricManifest(ContractModel):
    """Team-frozen scoring range for the manual adaptation assessment."""

    schema_version: Literal["0.1"] = "0.1"
    rubric_version: Identifier
    score_min: float = Field(allow_inf_nan=False)
    score_max: float = Field(allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_range(self) -> LevelAdaptationRubricManifest:
        if self.score_max <= self.score_min:
            raise ValueError("score_max must be greater than score_min")
        return self


class BlindRatingSubmissionManifest(ContractModel):
    """Integrity metadata for one completed single-rater blind assessment."""

    schema_version: Literal["0.1"] = "0.1"
    ratings_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    key_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    rubric_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_rating_count: int = Field(gt=0)
    rubric_version: Identifier


class ScoreArtifactProvenanceManifest(ContractModel):
    """Integrity binding from one score artifact to its source run results."""

    schema_version: Literal["0.1"] = "0.1"
    score_file: Path
    score_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_runs_file: Path
    source_runs_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    score_record_count: int = Field(gt=0)
    source_run_count: int = Field(gt=0)
    run_ids_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class RoleLabelProvenanceManifest(ContractModel):
    """M8 audit metadata for an M3-owned Role-label package.

    Field-name settings adapt M3's eventual JSONL shape into the audit without
    redefining the Role taxonomy or changing the upstream label schema.
    """

    schema_version: Literal["0.1"] = "0.1"
    role_schema_version: Identifier
    role_taxonomy_version: Identifier
    annotation_version: Identifier
    corpus_version: Identifier
    parser_version: Identifier
    annotation_date: date
    annotator_ids: list[Identifier] = Field(min_length=1)
    double_annotated: Literal[False] = False
    labels_file: Path
    labels_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    declared_record_count: int = Field(gt=0)
    question_id_field: Identifier = "question_id"
    reference_id_field: Identifier = "chunk_id"
    reference_type: Literal["span", "chunk"] = "chunk"
    reference_universe: Literal["gold_mapping", "corpus_records"] = "corpus_records"
    role_field: Identifier = "role"
    record_schema_version_field: Identifier = "schema_version"

    @model_validator(mode="after")
    def validate_annotation_scope(self) -> RoleLabelProvenanceManifest:
        if len(self.annotator_ids) != 1:
            raise ValueError("Role-label provenance requires one primary annotator")
        return self
