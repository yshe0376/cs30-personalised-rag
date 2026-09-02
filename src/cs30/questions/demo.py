"""Question provider for the validated Week 1 SciQ Demo set."""

import json
from importlib.resources import files

from cs30.contracts import SciQQuestion


class DemoQuestionProvider:
    """Load and validate the packaged SciQ Demo questions by stable id."""

    def __init__(self) -> None:
        payload = json.loads(
            files("cs30.fixtures")
            .joinpath("sciq_demo_questions.json")
            .read_text(encoding="utf-8")
        )
        questions = [SciQQuestion.model_validate(item) for item in payload]
        self._questions = {question.question_id: question for question in questions}
        if len(self._questions) != len(questions):
            raise ValueError("SciQ Demo question ids must be unique")

    def get(self, question_id: str) -> SciQQuestion:
        question_id = question_id.strip()
        try:
            return self._questions[question_id]
        except KeyError as exc:
            raise KeyError(f"unknown SciQ demo question_id: {question_id}") from exc