"""Generation-only manifests; scoring binds its own rubric independently."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from cs30.evaluation.open_answer_models import ExpectedAnswer, OpenAnswerRun


class GenerationExperiment(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["0.2"] = "0.2"
    matrix_version: str
    gold_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    cases: list[ExpectedAnswer] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_cells(self):
        ids = [c.run_id for c in self.cases]
        cells = [
            (c.question_id, c.condition_id, c.student_level, c.generator_model) for c in self.cases
        ]
        if len(set(ids)) != len(ids) or len(set(cells)) != len(cells):
            raise ValueError("expected run IDs and experiment cells must be unique")
        return self


class GenerationRun(OpenAnswerRun):
    status: Literal[
        "answered",
        "abstained",
        "retrieval_error",
        "generation_error",
        "parse_error",
        "output_truncated",
    ]

    @classmethod
    def from_v2_result(cls, expected, result):
        record = super().from_v2_result(expected, result)
        if (
            result.answer is None
            and result.trace.attempts
            and (result.trace.attempts[-1].status == "output_truncated")
        ):
            record = record.model_copy(update={"status": "output_truncated"})
        return record
