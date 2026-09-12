"""Personalised generation with strict parsing, citation checks, and retries."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field

from cs30.citation import resolve_and_validate, validate_citations
from cs30.contracts import EvidenceBundle, GeneratedAnswer, StudentProfile
from cs30.errors import CitationIntegrityError, GenerationError

from .client import LLMClient, TokenUsage
from .evidence import GenerationEvidence, evidence_items
from .exceptions import LLMOutputValidationError
from .prompt import PromptBuilder
from .schema import openai_text_format, parse_answer_payload

_NO_EVIDENCE = (
    "The retrieved evidence does not cover this question, so no grounded answer "
    "can be given from the available material."
)


@dataclass(frozen=True)
class GenerationAttemptTrace:
    """One provider attempt, including the raw output M8 needs to rescore it."""

    attempt: int
    is_repair: bool
    status: str
    raw_output: str | None
    model: str
    usage: TokenUsage = field(default_factory=TokenUsage)
    response_id: str | None = None
    failure_type: str | None = None
    error: str | None = None

    def model_dump(self) -> dict[str, object]:
        return {
            "attempt": self.attempt,
            "is_repair": self.is_repair,
            "status": self.status,
            "raw_output": self.raw_output,
            "model": self.model,
            "usage": {
                "input_tokens": self.usage.input_tokens,
                "output_tokens": self.usage.output_tokens,
                "total_tokens": self.usage.total_tokens,
            },
            "response_id": self.response_id,
            "failure_type": self.failure_type,
            "error": self.error,
        }


@dataclass(frozen=True)
class GenerationTrace:
    model: str
    temperature: float | None
    attempts: int
    latency_ms: float
    usage: TokenUsage = field(default_factory=TokenUsage)
    failure_types: tuple[str, ...] = ()
    response_id: str | None = None
    abstained: bool = False
    raw_model_output: str | None = None
    repaired_model_output: str | None = None
    prompt_evidence_chunk_ids: tuple[str, ...] = ()
    prompt_version: str = PromptBuilder.prompt_version
    prompt_sha256: str | None = None
    prompt_personalised: bool = True
    profile_snapshot: dict[str, object] = field(default_factory=dict)
    attempt_records: tuple[GenerationAttemptTrace, ...] = ()

    def to_metadata(self) -> dict[str, str]:
        return {
            "generation_model": self.model,
            "generation_temperature": (
                "provider-default" if self.temperature is None else str(self.temperature)
            ),
            "generation_attempts": str(self.attempts),
            "generation_ms": f"{self.latency_ms:.1f}",
            "input_tokens": str(self.usage.input_tokens),
            "output_tokens": str(self.usage.output_tokens),
            "total_tokens": str(self.usage.total_tokens),
            "generation_failures": ",".join(self.failure_types) or "none",
            "generation_response_id": self.response_id or "none",
            "generation_abstained": str(self.abstained).lower(),
            "generation_raw_output_present": str(self.raw_model_output is not None).lower(),
            "generation_repaired_output_present": str(
                self.repaired_model_output is not None
            ).lower(),
            "prompt_evidence_chunk_ids": ",".join(self.prompt_evidence_chunk_ids),
            "prompt_sha256": self.prompt_sha256 or "none",
            "generation_prompt_version": self.prompt_version,
            "generation_prompt_sha256": self.prompt_sha256 or "none",
            "generation_prompt_personalised": str(self.prompt_personalised).lower(),
        }

    def model_dump(self) -> dict[str, object]:
        """Structured trace for saved runs, retaining the legacy metadata keys."""

        return {
            **self.to_metadata(),
            "raw_model_output": self.raw_model_output,
            "repaired_model_output": self.repaired_model_output,
            "prompt_evidence_chunk_ids": list(self.prompt_evidence_chunk_ids),
            "prompt_sha256": self.prompt_sha256,
            "profile_snapshot": self.profile_snapshot,
            "attempt_records": [record.model_dump() for record in self.attempt_records],
        }


class PersonalisedAnswerGenerator:
    """Real task-7 AnswerGenerator implementation behind the frozen Protocol."""

    def __init__(
        self,
        client: LLMClient,
        *,
        max_retries: int = 2,
        prompt_builder: PromptBuilder | None = None,
    ) -> None:
        if max_retries < 0:
            raise ValueError("max_retries must be non-negative")
        self.client = client
        self.max_retries = max_retries
        self.prompt_builder = prompt_builder or PromptBuilder()
        self.last_trace: GenerationTrace | None = None

    def generate(
        self,
        question: str,
        profile: StudentProfile,
        retrieval: GenerationEvidence,
        *,
        personalise_prompt: bool = True,
    ) -> GeneratedAnswer:
        self.last_trace = None
        started = time.perf_counter()
        profile_snapshot = profile.model_dump(mode="json")
        prompt_version = self.prompt_builder.version(personalise=personalise_prompt)
        if not evidence_items(retrieval):
            answer = GeneratedAnswer(explanation=_NO_EVIDENCE, abstained=True)
            self.last_trace = GenerationTrace(
                model=self.client.model,
                temperature=self.client.temperature,
                attempts=0,
                latency_ms=(time.perf_counter() - started) * 1000,
                abstained=True,
                prompt_version=prompt_version,
                prompt_personalised=personalise_prompt,
                profile_snapshot=profile_snapshot,
            )
            return answer

        original_prompt = self.prompt_builder.build(
            question,
            profile,
            retrieval,
            personalise=personalise_prompt,
        )
        prompt_sha256 = hashlib.sha256(original_prompt.encode("utf-8")).hexdigest()
        prompt = original_prompt
        prompt_evidence_chunk_ids = tuple(item.chunk_id for item in evidence_items(retrieval))
        total_usage = TokenUsage()
        failure_types: list[str] = []
        attempt_records: list[GenerationAttemptTrace] = []
        last_error: Exception | None = None
        last_response_id: str | None = None
        first_model_output: str | None = None
        repaired_model_output: str | None = None
        is_repair_prompt = False

        for attempt in range(1, self.max_retries + 2):
            invalid_output = ""
            call_is_repair = is_repair_prompt
            try:
                response = self.client.complete(prompt, openai_text_format())
                last_response_id = response.response_id
                total_usage += response.usage
                invalid_output = response.text
                if first_model_output is None:
                    first_model_output = response.text
                if call_is_repair:
                    repaired_model_output = response.text
                payload = parse_answer_payload(response.text)
                answer = GeneratedAnswer(
                    final_choice=payload.final_choice,
                    explanation=payload.explanation,
                    citations=payload.citations,
                )
                self._validate_citations(answer, retrieval)
                attempt_records.append(
                    GenerationAttemptTrace(
                        attempt=attempt,
                        is_repair=is_repair_prompt,
                        status="completed",
                        raw_output=response.text,
                        model=response.model,
                        usage=response.usage,
                        response_id=response.response_id,
                    )
                )
                self.last_trace = GenerationTrace(
                    model=response.model,
                    temperature=self.client.temperature,
                    attempts=attempt,
                    latency_ms=(time.perf_counter() - started) * 1000,
                    usage=total_usage,
                    failure_types=tuple(failure_types),
                    response_id=response.response_id,
                    raw_model_output=first_model_output,
                    repaired_model_output=repaired_model_output,
                    prompt_evidence_chunk_ids=prompt_evidence_chunk_ids,
                    prompt_sha256=prompt_sha256,
                    prompt_version=prompt_version,
                    prompt_personalised=personalise_prompt,
                    profile_snapshot=profile_snapshot,
                    attempt_records=tuple(attempt_records),
                )
                return answer
            except (LLMOutputValidationError, CitationIntegrityError) as exc:
                last_error = exc
                failure_types.append(type(exc).__name__)
                attempt_records.append(
                    GenerationAttemptTrace(
                        attempt=attempt,
                        is_repair=is_repair_prompt,
                        status="rejected",
                        raw_output=invalid_output,
                        model=response.model,
                        usage=response.usage,
                        response_id=response.response_id,
                        failure_type=type(exc).__name__,
                        error=str(exc),
                    )
                )
                prompt = self.prompt_builder.build_repair(
                    original_prompt,
                    invalid_output,
                    exc,
                    retrieval,
                )
                is_repair_prompt = True
            except GenerationError as exc:
                last_error = exc
                failure_types.append(type(exc).__name__)
                attempt_records.append(
                    GenerationAttemptTrace(
                        attempt=attempt,
                        is_repair=is_repair_prompt,
                        status="provider_failed",
                        raw_output=None,
                        model=self.client.model,
                        failure_type=type(exc).__name__,
                        error=str(exc),
                    )
                )
                prompt = original_prompt
                is_repair_prompt = False

        self.last_trace = GenerationTrace(
            model=self.client.model,
            temperature=self.client.temperature,
            attempts=self.max_retries + 1,
            latency_ms=(time.perf_counter() - started) * 1000,
            usage=total_usage,
            failure_types=tuple(failure_types),
            response_id=last_response_id,
            raw_model_output=first_model_output,
            repaired_model_output=repaired_model_output,
            prompt_evidence_chunk_ids=prompt_evidence_chunk_ids,
            prompt_sha256=prompt_sha256,
            prompt_version=prompt_version,
            prompt_personalised=personalise_prompt,
            profile_snapshot=profile_snapshot,
            attempt_records=tuple(attempt_records),
        )
        raise GenerationError(
            f"generation failed after {self.max_retries + 1} attempts: {last_error}"
        ) from last_error

    @staticmethod
    def _validate_citations(
        answer: GeneratedAnswer,
        retrieval: GenerationEvidence,
    ) -> None:
        if isinstance(retrieval, EvidenceBundle):
            resolve_and_validate(answer, retrieval)
        else:
            validate_citations(answer, retrieval)
