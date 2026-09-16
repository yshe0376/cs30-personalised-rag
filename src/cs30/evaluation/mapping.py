"""Versioned gold-span to chunk mappings supplied by M4.

The gold schema keeps semantic evidence groups (OR between alternatives and
AND within one group).  This module records how each individual gold span is
covered by the frozen chunking output.  A span may have several acceptable
chunk sets when different chunk boundaries cover the same source text.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from cs30.contracts.models import ContractModel, Identifier


class SpanChunkMapping(ContractModel):
    """Alternative chunk sets that fully cover one gold span."""

    span_id: Identifier
    acceptable_chunk_sets: list[list[Identifier]] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_chunk_sets(self) -> SpanChunkMapping:
        for chunk_set in self.acceptable_chunk_sets:
            if not chunk_set:
                raise ValueError("acceptable chunk sets must not be empty")
            if len(set(chunk_set)) != len(chunk_set):
                raise ValueError("chunk IDs must be unique within an acceptable chunk set")
        return self


class QuestionChunkMapping(ContractModel):
    """Mapping records for all gold spans belonging to one question."""

    schema_version: Literal["0.1"] = "0.1"
    question_id: Identifier
    corpus_version: Identifier
    chunk_config_hash: Identifier
    mapping_version: Identifier
    spans: list[SpanChunkMapping] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_span_ids(self) -> QuestionChunkMapping:
        ids = [item.span_id for item in self.spans]
        if len(ids) != len(set(ids)):
            raise ValueError("span_id values must be unique within a question mapping")
        return self

    def for_span(self, span_id: str) -> SpanChunkMapping:
        """Return one span mapping or raise a useful key error."""

        for item in self.spans:
            if item.span_id == span_id:
                return item
        raise KeyError(f"mapping does not contain span_id {span_id!r}")


class GoldChunkMapping(ContractModel):
    """A versioned collection of M4 mappings, one record per question."""

    schema_version: Literal["0.1"] = "0.1"
    mapping_version: Identifier
    corpus_version: Identifier
    chunk_config_hash: Identifier
    items: list[QuestionChunkMapping] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_metadata(self) -> GoldChunkMapping:
        question_ids = [item.question_id for item in self.items]
        if len(question_ids) != len(set(question_ids)):
            raise ValueError("question_id values must be unique in a mapping artifact")
        for item in self.items:
            if item.mapping_version != self.mapping_version:
                raise ValueError("all question mappings must use the artifact mapping_version")
            if item.corpus_version != self.corpus_version:
                raise ValueError("all question mappings must use the artifact corpus_version")
            if item.chunk_config_hash != self.chunk_config_hash:
                raise ValueError(
                    "all question mappings must use the artifact chunk_config_hash"
                )
        return self

    def for_question(self, question_id: str) -> QuestionChunkMapping:
        """Return one question mapping or raise a useful key error."""

        for item in self.items:
            if item.question_id == question_id:
                return item
        raise KeyError(f"mapping does not contain question_id {question_id!r}")


MappingArtifact = GoldChunkMapping
