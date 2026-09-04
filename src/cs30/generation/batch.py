"""Batch helper that isolates failures so one API error does not stop the run."""

from __future__ import annotations

from dataclasses import dataclass

from cs30.contracts import GeneratedAnswer, RetrievalResult, StudentProfile
from cs30.errors import GenerationError

from .generator import GenerationTrace, PersonalisedAnswerGenerator


@dataclass(frozen=True)
class BatchItem:
    question_id: str
    question: str
    profile: StudentProfile
    retrieval: RetrievalResult


@dataclass(frozen=True)
class BatchResult:
    question_id: str
    status: str
    answer: GeneratedAnswer | None
    trace: GenerationTrace | None
    error: str | None = None

    def model_dump(self) -> dict:
        return {
            "question_id": self.question_id,
            "status": self.status,
            "answer": self.answer.model_dump(mode="json") if self.answer else None,
            "trace": self.trace.to_metadata() if self.trace else None,
            "error": self.error,
        }


def generate_batch(
    generator: PersonalisedAnswerGenerator,
    items: list[BatchItem],
) -> list[BatchResult]:
    """Generate every item, capturing expected failures per item."""

    results: list[BatchResult] = []
    for item in items:
        try:
            answer = generator.generate(item.question, item.profile, item.retrieval)
        except GenerationError as exc:
            results.append(
                BatchResult(
                    question_id=item.question_id,
                    status="failed",
                    answer=None,
                    trace=generator.last_trace,
                    error=str(exc),
                )
            )
            continue
        results.append(
            BatchResult(
                question_id=item.question_id,
                status="completed",
                answer=answer,
                trace=generator.last_trace,
            )
        )
    return results
