"""Personalised generation with strict parsing, citation checks, and retries."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from cs30.citation import validate_citations
from cs30.contracts import GeneratedAnswer, RetrievalResult, StudentProfile
from cs30.errors import CitationIntegrityError, GenerationError

from .client import LLMClient, TokenUsage
from .exceptions import LLMOutputValidationError
from .prompt import PromptBuilder
from .schema import openai_text_format, parse_answer_payload

_NO_EVIDENCE = (
    "The retrieved evidence does not cover this question, so no grounded answer "
    "can be given from the available material."
)


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
        retrieval: RetrievalResult,
    ) -> GeneratedAnswer:
        started = time.perf_counter()
        if not retrieval.hits:
            answer = GeneratedAnswer(explanation=_NO_EVIDENCE, abstained=True)
            self.last_trace = GenerationTrace(
                model=self.client.model,
                temperature=self.client.temperature,
                attempts=0,
                latency_ms=(time.perf_counter() - started) * 1000,
                abstained=True,
            )
            return answer

        original_prompt = self.prompt_builder.build(question, profile, retrieval)
        prompt = original_prompt
        total_usage = TokenUsage()
        failure_types: list[str] = []
        last_error: Exception | None = None
        last_response_id: str | None = None

        for attempt in range(1, self.max_retries + 2):
            invalid_output = ""
            try:
                response = self.client.complete(prompt, openai_text_format())
                last_response_id = response.response_id
                total_usage += response.usage
                invalid_output = response.text
                payload = parse_answer_payload(response.text)
                answer = GeneratedAnswer(
                    final_choice=payload.final_choice,
                    explanation=payload.explanation,
                    citations=payload.citations,
                )
                validate_citations(answer, retrieval)
                self.last_trace = GenerationTrace(
                    model=response.model,
                    temperature=self.client.temperature,
                    attempts=attempt,
                    latency_ms=(time.perf_counter() - started) * 1000,
                    usage=total_usage,
                    failure_types=tuple(failure_types),
                    response_id=response.response_id,
                )
                return answer
            except (LLMOutputValidationError, CitationIntegrityError) as exc:
                last_error = exc
                failure_types.append(type(exc).__name__)
                prompt = self.prompt_builder.build_repair(
                    original_prompt,
                    invalid_output,
                    exc,
                    retrieval,
                )
            except GenerationError as exc:
                last_error = exc
                failure_types.append(type(exc).__name__)
                prompt = original_prompt

        self.last_trace = GenerationTrace(
            model=self.client.model,
            temperature=self.client.temperature,
            attempts=self.max_retries + 1,
            latency_ms=(time.perf_counter() - started) * 1000,
            usage=total_usage,
            failure_types=tuple(failure_types),
            response_id=last_response_id,
        )
        raise GenerationError(
            f"generation failed after {self.max_retries + 1} attempts: {last_error}"
        ) from last_error
