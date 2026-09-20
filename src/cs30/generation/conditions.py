"""Four-condition personalisation runner for controlled comparisons."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from cs30.contracts import GeneratedAnswer, StudentProfile

from .evidence import GenerationEvidence, evidence_items
from .generator import GenerationTrace, PersonalisedAnswerGenerator
from .reranking import LevelAwareReranker, RerankTrace


class GenerationCondition(StrEnum):
    PLAIN = "plain"
    PROMPT_ONLY = "prompt-only"
    RERANKING_ONLY = "reranking-only"
    COMBINED = "combined"

    @property
    def condition_id(self) -> str:
        return {
            self.PLAIN: "P0R0_plain",
            self.PROMPT_ONLY: "P1R0_prompt_only",
            self.RERANKING_ONLY: "P0R1_reranking_only",
            self.COMBINED: "P1R1_combined",
        }[self]

    @property
    def prompt_personalisation(self) -> bool:
        return self in {self.PROMPT_ONLY, self.COMBINED}

    @property
    def reranking(self) -> bool:
        return self in {self.RERANKING_ONLY, self.COMBINED}


@dataclass(frozen=True)
class ConditionResult:
    condition: GenerationCondition
    profile_snapshot: dict[str, object]
    input_candidate_ids: tuple[str, ...]
    output_candidate_ids: tuple[str, ...]
    answer: GeneratedAnswer
    generation_trace: GenerationTrace
    rerank_trace: RerankTrace | None

    def model_dump(self) -> dict[str, object]:
        return {
            "condition": self.condition.value,
            "condition_id": self.condition.condition_id,
            "prompt_personalisation": self.condition.prompt_personalisation,
            "reranking": self.condition.reranking,
            "profile_snapshot": self.profile_snapshot,
            "input_candidate_ids": list(self.input_candidate_ids),
            "output_candidate_ids": list(self.output_candidate_ids),
            "answer": self.answer.model_dump(mode="json"),
            "generation_trace": self.generation_trace.model_dump(),
            "rerank_trace": self.rerank_trace.model_dump() if self.rerank_trace else None,
        }


class FourConditionRunner:
    """Run one model and one candidate set under the four W5 conditions."""

    def __init__(
        self,
        generator: PersonalisedAnswerGenerator,
        reranker: LevelAwareReranker,
    ) -> None:
        self.generator = generator
        self.reranker = reranker

    def run(
        self,
        question: str,
        profile: StudentProfile,
        evidence: GenerationEvidence,
        condition: GenerationCondition | str,
    ) -> ConditionResult:
        condition = GenerationCondition(condition)
        input_ids = tuple(item.chunk_id for item in evidence_items(evidence))
        rerank_trace: RerankTrace | None = None
        prepared = evidence
        if condition.reranking:
            reranked = self.reranker.rerank(evidence, profile)
            prepared = reranked.evidence
            rerank_trace = reranked.trace

        answer = self.generator.generate(
            question,
            profile,
            prepared,
            personalise_prompt=condition.prompt_personalisation,
        )
        generation_trace = self.generator.last_trace
        if generation_trace is None:
            raise RuntimeError("generator completed without a generation trace")
        return ConditionResult(
            condition=condition,
            profile_snapshot=profile.model_dump(mode="json"),
            input_candidate_ids=input_ids,
            output_candidate_ids=tuple(item.chunk_id for item in evidence_items(prepared)),
            answer=answer,
            generation_trace=generation_trace,
            rerank_trace=rerank_trace,
        )

    def run_all(
        self,
        question: str,
        profile: StudentProfile,
        evidence: GenerationEvidence,
    ) -> list[ConditionResult]:
        """Run the fixed condition order against the same immutable inputs."""

        return [
            self.run(question, profile, evidence, condition) for condition in GenerationCondition
        ]
