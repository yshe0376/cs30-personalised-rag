"""M7 generation adapter that consumes one governed v2 EvidenceBundle."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from pydantic import ValidationError

from cs30.generation.client import LLMClient
from cs30.generation.schema import openai_text_format
from cs30.v2.contracts import (
    EvidenceBundle,
    GeneratedAnswer,
    LearnerContextSnapshot,
    StudentProfile,
)

_NO_EVIDENCE = "The available evidence does not support a grounded answer."


@dataclass(frozen=True)
class V2GenerationAttempt:
    number: int
    status: str
    raw_output: str | None
    error: str | None = None


@dataclass(frozen=True)
class V2GenerationTrace:
    model: str
    prompt_sha256: str | None
    profile_source: str
    corpus_version: str | None
    corpus_hash: str | None
    evidence_chunk_ids: tuple[str, ...]
    attempts: tuple[V2GenerationAttempt, ...]
    abstained: bool = False


@dataclass(frozen=True)
class V2BatchResult:
    answer: GeneratedAnswer | None
    trace: V2GenerationTrace
    error: str | None = None


class V2GenerationFailure(Exception):
    def __init__(self, message: str, trace: V2GenerationTrace) -> None:
        super().__init__(message)
        self.trace = trace


class V2AnswerGenerator:
    """Strict JSON, bounded retry and citation subset checks on v2 evidence."""

    def __init__(self, client: LLMClient, *, max_retries: int = 2) -> None:
        if max_retries < 0:
            raise ValueError("max_retries must be non-negative")
        self.client = client
        self.max_retries = max_retries
        self.last_trace: V2GenerationTrace | None = None

    def generate(
        self,
        question: str,
        profile: StudentProfile | LearnerContextSnapshot,
        evidence: EvidenceBundle,
    ) -> GeneratedAnswer:
        self.last_trace = None
        snapshot = profile if isinstance(profile, LearnerContextSnapshot) else None
        student = snapshot.profile if snapshot else profile
        profile_source = snapshot.profile_source.value if snapshot else "static_profile"
        provenance = evidence.retrieval_provenance
        chunk_ids = tuple(item.chunk_id for item in evidence.evidence_items)

        def trace(
            attempts: tuple[V2GenerationAttempt, ...],
            *,
            prompt_sha256: str | None = None,
            abstained: bool = False,
        ) -> V2GenerationTrace:
            return V2GenerationTrace(
                model=self.client.model,
                prompt_sha256=prompt_sha256,
                profile_source=profile_source,
                corpus_version=provenance.corpus_version if provenance else None,
                corpus_hash=provenance.corpus_hash if provenance else None,
                evidence_chunk_ids=chunk_ids,
                attempts=attempts,
                abstained=abstained,
            )

        if not chunk_ids:
            answer = GeneratedAnswer(explanation=_NO_EVIDENCE, abstained=True)
            self.last_trace = trace((), abstained=True)
            return answer
        if not question.strip():
            raise ValueError("question must not be empty")
        prompt = self._prompt(question, student, evidence)
        prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        records: list[V2GenerationAttempt] = []
        allowed = set(chunk_ids)
        for number in range(1, self.max_retries + 2):
            raw: str | None = None
            try:
                response = self.client.complete(prompt, openai_text_format())
                raw = response.text
                payload = json.loads(raw)
                if not isinstance(payload, dict) or set(payload) != {
                    "final_choice",
                    "explanation",
                    "citations",
                }:
                    raise ValueError(
                        "answer must contain exactly final_choice, explanation, citations"
                    )
                answer = GeneratedAnswer.model_validate({**payload, "abstained": False})
                if not set(answer.citations).issubset(allowed):
                    raise ValueError("answer cited a chunk outside the input EvidenceBundle")
                records.append(V2GenerationAttempt(number, "completed", raw))
                self.last_trace = trace(tuple(records), prompt_sha256=prompt_hash)
                return answer
            except (ValueError, ValidationError, TypeError) as exc:
                records.append(V2GenerationAttempt(number, "invalid_output", raw, str(exc)))
            except Exception as exc:
                records.append(V2GenerationAttempt(number, "provider_failure", raw, str(exc)))
            if number <= self.max_retries:
                prompt = self._repair_prompt(prompt, records[-1])
        self.last_trace = trace(tuple(records), prompt_sha256=prompt_hash)
        raise V2GenerationFailure("generation failed after bounded retries", self.last_trace)

    def generate_batch(
        self,
        cases: tuple[tuple[str, StudentProfile | LearnerContextSnapshot, EvidenceBundle], ...],
    ) -> tuple[V2BatchResult, ...]:
        results: list[V2BatchResult] = []
        for question, profile, evidence in cases:
            try:
                answer = self.generate(question, profile, evidence)
                assert self.last_trace is not None
                results.append(V2BatchResult(answer, self.last_trace))
            except V2GenerationFailure as exc:
                results.append(V2BatchResult(None, exc.trace, str(exc)))
            except Exception as exc:
                trace = self.last_trace or V2GenerationTrace(
                    model=self.client.model,
                    prompt_sha256=None,
                    profile_source="unknown",
                    corpus_version=None,
                    corpus_hash=None,
                    evidence_chunk_ids=(),
                    attempts=(V2GenerationAttempt(0, "input_failure", None, str(exc)),),
                )
                results.append(V2BatchResult(None, trace, str(exc)))
        return tuple(results)

    @staticmethod
    def _prompt(question: str, profile: StudentProfile, evidence: EvidenceBundle) -> str:
        items = [
            {
                "chunk_id": item.chunk_id,
                "provider": item.provider,
                "textbook_id": item.textbook_id,
                "document_id": item.document_id,
                "chapter_id": item.chapter_id,
                "source_locator": item.source_locator,
                "text": item.text,
            }
            for item in evidence.evidence_items
        ]
        return (
            "Answer the multiple-choice question using only the supplied evidence. "
            "Return strict JSON with exactly final_choice, explanation, citations. "
            "Citations must be chunk_id values from the evidence. "
            "Match explanation depth to the student's level.\n"
            + json.dumps(
                {
                    "question": question,
                    "student_level": profile.level.value,
                    "topic_levels": {
                        key: value.value for key, value in profile.topic_levels.items()
                    },
                    "evidence": items,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )

    @staticmethod
    def _repair_prompt(original: str, failed: V2GenerationAttempt) -> str:
        return (
            original
            + "\nPrevious response failed validation. Return corrected JSON only. "
            + json.dumps({"error": failed.error, "raw_output": failed.raw_output})
        )
