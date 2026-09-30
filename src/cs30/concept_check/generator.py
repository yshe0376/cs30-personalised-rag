"""Development-only offline generation of draft Concept Check questions."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from cs30.generation.client import LLMClient
from cs30.v2.config import ConceptCheckConfig, V2Config
from cs30.v2.contracts import (
    ConceptCheckQuestion,
    ConceptCheckQuestionStatus,
    EvidenceSpan,
    QuestionSourceType,
    StudentLevel,
)


class _CandidatePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str
    options: dict[Literal["A", "B", "C", "D"], str]
    correct_answer: Literal["A", "B", "C", "D"]
    rationale: str


@dataclass(frozen=True)
class DraftResult:
    question: ConceptCheckQuestion | None
    raw_output: str | None
    error: str | None


class OfflineDraftGenerator:
    """Produces drafts only; M3 review and M4 binding are separate gates."""

    def __init__(self, client: LLMClient, *, config: ConceptCheckConfig, environment: str) -> None:
        if environment != "development":
            raise ValueError("Concept Check draft generation is development-only")
        if not config.allow_llm_generation:
            raise ValueError("offline draft generation requires allow_llm_generation=true")
        self.client = client

    @classmethod
    def from_runtime_config(cls, client: LLMClient, config: V2Config) -> OfflineDraftGenerator:
        return cls(client, config=config.concept_check, environment=config.environment)

    def generate_draft(
        self,
        *,
        question_id: str,
        topic_id: str,
        topic_registry_version: str,
        difficulty: StudentLevel,
        evidence_anchors: Sequence[EvidenceSpan],
    ) -> DraftResult:
        if not evidence_anchors:
            return DraftResult(None, None, "at least one reviewed candidate anchor is required")
        prompt = (
            "Create one four-choice practice question grounded only in these candidate "
            "textbook spans. Return strict JSON with question, options A-D, correct_answer, "
            "and rationale. The output remains a draft for human review.\n"
            + json.dumps(
                {
                    "topic_id": topic_id,
                    "difficulty": difficulty.value,
                    "candidate_spans": [
                        anchor.model_dump(mode="json") for anchor in evidence_anchors
                    ],
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        raw: str | None = None
        try:
            response = self.client.complete(
                prompt,
                {
                    "type": "json_schema",
                    "name": "concept_check_draft",
                    "strict": True,
                    "schema": _CandidatePayload.model_json_schema(),
                },
            )
            raw = response.text
            payload = _CandidatePayload.model_validate_json(raw)
            question = ConceptCheckQuestion(
                question_id=question_id,
                question=payload.question,
                options=payload.options,
                correct_answer=payload.correct_answer,
                topic_id=topic_id,
                topic_registry_version=topic_registry_version,
                difficulty=difficulty,
                evidence_anchors=tuple(evidence_anchors),
                source_type=QuestionSourceType.LLM_GENERATED,
                rationale=payload.rationale,
                status=ConceptCheckQuestionStatus.DRAFT,
            )
            return DraftResult(question, raw, None)
        except (ValueError, ValidationError) as exc:
            return DraftResult(None, raw, f"invalid_output: {exc}")
        except Exception as exc:
            return DraftResult(None, raw, f"provider_failure: {exc}")

    def generate_batch(
        self,
        candidates: Sequence[tuple[str, str, str, StudentLevel, Sequence[EvidenceSpan]]],
    ) -> tuple[DraftResult, ...]:
        return tuple(
            self.generate_draft(
                question_id=question_id,
                topic_id=topic_id,
                topic_registry_version=registry_version,
                difficulty=difficulty,
                evidence_anchors=anchors,
            )
            for question_id, topic_id, registry_version, difficulty, anchors in candidates
        )
