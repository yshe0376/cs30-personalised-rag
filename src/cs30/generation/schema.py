"""Fixed three-field JSON payload produced by the language model."""

import json

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from cs30.contracts.models import ChoiceLabel, Identifier, NonEmptyText

from .exceptions import LLMOutputValidationError


class AnswerPayload(BaseModel):
    """The exact model-facing JSON contract before the CS-30 wrapper is added."""

    model_config = ConfigDict(extra="forbid")

    final_choice: ChoiceLabel | None
    explanation: NonEmptyText
    citations: list[Identifier] = Field(min_length=1)

    @field_validator("citations")
    @classmethod
    def citations_are_unique(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("citations must be unique")
        return value


ANSWER_JSON_SCHEMA = AnswerPayload.model_json_schema()


def openai_text_format() -> dict:
    """Responses API Structured Outputs configuration."""

    return {
        "type": "json_schema",
        "name": "generated_answer",
        "strict": True,
        "schema": ANSWER_JSON_SCHEMA,
    }


def parse_answer_payload(raw_text: str) -> AnswerPayload:
    """Parse strict JSON and validate that it has exactly the three agreed fields."""

    if not raw_text or not raw_text.strip():
        raise LLMOutputValidationError("model returned an empty response")
    try:
        value = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise LLMOutputValidationError(f"model response is not valid JSON: {exc.msg}") from exc
    try:
        return AnswerPayload.model_validate(value)
    except ValidationError as exc:
        raise LLMOutputValidationError(f"model response failed schema validation: {exc}") from exc
