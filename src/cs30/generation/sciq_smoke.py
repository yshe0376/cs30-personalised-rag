"""Temporary SciQ-to-task-7 adapter for a non-evaluation Week 1 smoke run.

The adapter deliberately lives in Member 7's module rather than the questions
or retrieval packages.  It can therefore be removed when Members 3 and 6 land
their real providers without changing the frozen cross-module contracts.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from cs30.contracts import (
    RetrievalHit,
    RetrievalMode,
    RetrievalResult,
    SciQQuestion,
    StudentLevel,
)
from cs30.fixtures import load_fixture
from cs30.profile import Week1ProfileProvider

from .batch import BatchItem
from .prompt import format_sciq_question


class _SciQFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1)
    distractor1: str = Field(min_length=1)
    distractor2: str = Field(min_length=1)
    distractor3: str = Field(min_length=1)
    correct_answer: str = Field(min_length=1)
    support: str = Field(min_length=1)


class _DatasetRow(BaseModel):
    model_config = ConfigDict(extra="ignore")

    row_idx: int = Field(ge=0)
    row: _SciQFields


class _FreeQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    free_question_id: str = Field(min_length=1)
    question: str = Field(min_length=1)
    chapter_id: str = Field(min_length=1)
    expected_focus: str = Field(min_length=1)
    usage: str = Field(min_length=1)


@dataclass(frozen=True)
class FreeQuestion:
    question_id: str
    question: str
    chapter_id: str
    expected_focus: str


def load_sciq_questions(path: Path) -> list[SciQQuestion]:
    """Load a Hugging Face dataset-server rows response into frozen contracts."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"SciQ JSON file does not exist: {path}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"SciQ JSON file is unreadable: {path}") from exc

    if not isinstance(payload, dict) or not isinstance(payload.get("rows"), list):
        raise ValueError("SciQ JSON must be a Hugging Face rows response with a rows list")
    if not payload["rows"]:
        raise ValueError("SciQ JSON rows list must not be empty")

    questions: list[SciQQuestion] = []
    seen_ids: set[str] = set()
    try:
        rows = [_DatasetRow.model_validate(item) for item in payload["rows"]]
    except ValidationError as exc:
        raise ValueError(f"SciQ JSON contains an invalid row: {exc}") from exc

    for dataset_row in rows:
        row = dataset_row.row
        question_id = f"sciq_train_{dataset_row.row_idx:05d}"
        if question_id in seen_ids:
            raise ValueError(f"SciQ JSON contains duplicate row index: {dataset_row.row_idx}")
        seen_ids.add(question_id)

        # Correct answer is A only in this temporary structural smoke adapter so
        # the deterministic mock remains grounded. It is not an evaluation order.
        questions.append(
            SciQQuestion(
                question_id=question_id,
                question=row.question,
                choices={
                    "A": row.correct_answer,
                    "B": row.distractor1,
                    "C": row.distractor2,
                    "D": row.distractor3,
                },
                correct_choice="A",
                support=row.support,
                source="HuggingFace:allenai/sciq/train",
            )
        )
    return questions


def load_packaged_sciq_questions() -> list[SciQQuestion]:
    """Load the validated SciQ demo set contributed by Member 3."""

    try:
        payload = load_fixture("sciq_demo_questions.json")
        questions = [SciQQuestion.model_validate(item) for item in payload]
    except (TypeError, ValidationError) as exc:
        raise ValueError(f"packaged SciQ demo data is invalid: {exc}") from exc
    if not questions:
        raise ValueError("packaged SciQ demo data must not be empty")
    if len({question.question_id for question in questions}) != len(questions):
        raise ValueError("packaged SciQ demo question ids must be unique")
    return questions


def load_packaged_free_questions() -> list[FreeQuestion]:
    """Load Member 3's free-form smoke questions without inventing evidence."""

    try:
        payload = load_fixture("sciq_free_questions.json")
        rows = [_FreeQuestion.model_validate(item) for item in payload]
    except (TypeError, ValidationError) as exc:
        raise ValueError(f"packaged free-question data is invalid: {exc}") from exc
    if not rows:
        raise ValueError("packaged free-question data must not be empty")
    if len({row.free_question_id for row in rows}) != len(rows):
        raise ValueError("packaged free-question ids must be unique")
    return [
        FreeQuestion(
            question_id=row.free_question_id,
            question=row.question,
            chapter_id=row.chapter_id,
            expected_focus=row.expected_focus,
        )
        for row in rows
    ]


def build_sciq_smoke_items(
    questions: list[SciQQuestion],
    level: StudentLevel,
) -> list[BatchItem]:
    """Wrap SciQ support as explicitly labelled fixture retrieval evidence."""

    profile = Week1ProfileProvider(profile_prefix="task7-sciq-smoke").get(level)
    items: list[BatchItem] = []
    for question in questions:
        formatted_question = format_sciq_question(question)
        row_suffix = question.question_id.removeprefix("sciq_train_")
        hit = RetrievalHit(
            chunk_id=f"sciq_support_{row_suffix}",
            text=question.support,
            chapter_id="sciq_support_train",
            source="fixture://sciq-support/train",
            score=1.0,
            rank=1,
            retriever_type=RetrievalMode.FIXTURE,
        )
        items.append(
            BatchItem(
                question_id=question.question_id,
                question=formatted_question,
                profile=profile,
                retrieval=RetrievalResult(
                    query=question.question,
                    mode=RetrievalMode.FIXTURE,
                    hits=[hit],
                ),
            )
        )
    return items


def build_free_question_items(
    questions: list[FreeQuestion],
    level: StudentLevel,
) -> list[BatchItem]:
    """Represent free questions honestly until matching retrieval evidence lands."""

    profile = Week1ProfileProvider(profile_prefix="task7-free-smoke").get(level)
    return [
        BatchItem(
            question_id=question.question_id,
            question=question.question,
            profile=profile,
            retrieval=RetrievalResult(
                query=question.question,
                mode=RetrievalMode.FIXTURE,
            ),
        )
        for question in questions
    ]
