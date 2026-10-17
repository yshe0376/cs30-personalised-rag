"""M7 generation adapter that consumes one governed v2 EvidenceBundle."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from time import perf_counter

from pydantic import ValidationError

from cs30.generation.client import LLMClient, TokenUsage
from cs30.generation.exceptions import LLMOutputValidationError
from cs30.generation.schema import openai_text_format, parse_answer_payload
from cs30.v2.contracts import (
    EvidenceBundle,
    GeneratedAnswer,
    GenerationQuestion,
    GoldQuestion,
    LearnerContextSnapshot,
    StudentLevel,
    StudentProfile,
)
from cs30.v2.generation_prompt import V2PromptAdapter, generation_question

_NO_EVIDENCE = "The available evidence does not support a grounded answer."


@dataclass(frozen=True)
class V2GenerationAttempt:
    number: int
    status: str
    raw_output: str | None
    error: str | None = None
    failure_type: str | None = None
    usage: TokenUsage = field(default_factory=TokenUsage)
    latency_ms: float = 0.0
    response_id: str | None = None
    provider_latency_ms: float | None = None
    done_reason: str | None = None


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
    usage: TokenUsage = field(default_factory=TokenUsage)
    latency_ms: float = 0.0
    response_id: str | None = None
    prompt_version: str | None = None
    prompt_personalised: bool = False
    effective_level: StudentLevel | None = None
    citation_id_map: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class V2BatchResult:
    answer: GeneratedAnswer | None
    trace: V2GenerationTrace
    error: str | None = None


class V2GenerationFailure(Exception):
    def __init__(self, message: str, trace: V2GenerationTrace) -> None:
        super().__init__(message)
        self.trace = trace


class V2OutputTruncated(ValueError):
    """The provider ran out of output tokens; this is not a service outage."""


class V2CitationFailure(ValueError):
    """A structurally valid answer cited evidence outside the supplied bundle."""


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
        question: str | GenerationQuestion | GoldQuestion,
        profile: StudentProfile | LearnerContextSnapshot,
        evidence: EvidenceBundle,
        *,
        personalise_prompt: bool = True,
    ) -> GeneratedAnswer:
        self.last_trace = None
        snapshot = profile if isinstance(profile, LearnerContextSnapshot) else None
        student = snapshot.profile if snapshot else profile
        profile_source = snapshot.profile_source.value if snapshot else "static_profile"
        provenance = evidence.retrieval_provenance
        chunk_ids = tuple(item.chunk_id for item in evidence.evidence_items)
        adapter = V2PromptAdapter(student, evidence)

        def trace(
            attempts: tuple[V2GenerationAttempt, ...],
            *,
            prompt_sha256: str | None = None,
            abstained: bool = False,
        ) -> V2GenerationTrace:
            usage = TokenUsage()
            for attempt in attempts:
                usage += attempt.usage
            return V2GenerationTrace(
                model=self.client.model,
                citation_id_map=dict(adapter.citation_ids),
                prompt_sha256=prompt_sha256,
                profile_source=profile_source,
                corpus_version=provenance.corpus_version if provenance else None,
                corpus_hash=provenance.corpus_hash if provenance else None,
                evidence_chunk_ids=chunk_ids,
                attempts=attempts,
                abstained=abstained,
                usage=usage,
                latency_ms=sum(attempt.latency_ms for attempt in attempts),
                response_id=next(
                    (attempt.response_id for attempt in reversed(attempts) if attempt.response_id),
                    None,
                ),
                prompt_version=adapter.version(personalise=personalise_prompt)
                if prompt_sha256
                else None,
                prompt_personalised=personalise_prompt and prompt_sha256 is not None,
                effective_level=student.level if personalise_prompt and prompt_sha256 else None,
            )

        try:
            if isinstance(question, str) and not question.strip():
                raise ValueError("question must not be empty")
            request = generation_question(question)
        except (ValueError, TypeError) as exc:
            self.last_trace = trace(
                (V2GenerationAttempt(0, "input_failure", None, str(exc), type(exc).__name__),)
            )
            raise V2GenerationFailure(str(exc), self.last_trace) from exc
        if not chunk_ids:
            answer = GeneratedAnswer(explanation=_NO_EVIDENCE, abstained=True)
            self.last_trace = trace((), abstained=True)
            return answer
        original_prompt = adapter.build_prompt(request, personalise=personalise_prompt)
        prompt = original_prompt
        prompt_hash = hashlib.sha256(original_prompt.encode("utf-8")).hexdigest()
        records: list[V2GenerationAttempt] = []
        allowed = set(adapter.citation_ids)
        for number in range(1, self.max_retries + 2):
            started = perf_counter()
            try:
                response = self.client.complete(prompt, openai_text_format())
            except Exception as exc:
                records.append(
                    V2GenerationAttempt(
                        number,
                        "provider_failure",
                        None,
                        str(exc),
                        type(exc).__name__,
                        latency_ms=(perf_counter() - started) * 1000,
                    )
                )
                prompt = original_prompt
                continue
            elapsed_ms = (perf_counter() - started) * 1000
            raw = response.text
            try:
                if getattr(response, "done_reason", None) == "length":
                    raise V2OutputTruncated("provider exhausted the output token budget")
                payload = parse_answer_payload(raw)
                if not set(payload.citations).issubset(allowed):
                    raise V2CitationFailure("answer cited an ID outside the input evidence E1-En")
                if request.kind == "multiple_choice" and payload.final_choice is None:
                    raise LLMOutputValidationError(
                        "multiple-choice answers require final_choice A-D"
                    )
                answer = GeneratedAnswer(
                    final_choice=payload.final_choice,
                    explanation=payload.explanation,
                    citations=tuple(adapter.citation_ids[c] for c in payload.citations),
                )
                records.append(
                    V2GenerationAttempt(
                        number,
                        "completed",
                        raw,
                        usage=response.usage,
                        latency_ms=elapsed_ms,
                        provider_latency_ms=response.latency_ms,
                        response_id=response.response_id,
                        done_reason=getattr(response, "done_reason", None),
                    )
                )
                self.last_trace = trace(tuple(records), prompt_sha256=prompt_hash)
                return answer
            except (
                LLMOutputValidationError,
                V2CitationFailure,
                V2OutputTruncated,
                ValidationError,
            ) as exc:
                status = (
                    "output_truncated"
                    if isinstance(exc, V2OutputTruncated)
                    else "citation_failure"
                    if isinstance(exc, V2CitationFailure)
                    else "invalid_output"
                )
                records.append(
                    V2GenerationAttempt(
                        number,
                        status,
                        raw,
                        str(exc),
                        type(exc).__name__,
                        usage=response.usage,
                        latency_ms=elapsed_ms,
                        provider_latency_ms=response.latency_ms,
                        response_id=response.response_id,
                        done_reason=getattr(response, "done_reason", None),
                    )
                )
                if number <= self.max_retries:
                    prompt = adapter.repair_prompt(original_prompt, raw, exc)
        self.last_trace = trace(tuple(records), prompt_sha256=prompt_hash)
        raise V2GenerationFailure("generation failed after bounded retries", self.last_trace)

    def generate_batch(
        self,
        cases: tuple[
            tuple[
                str | GenerationQuestion | GoldQuestion,
                StudentProfile | LearnerContextSnapshot,
                EvidenceBundle,
            ],
            ...,
        ],
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
