"""Deterministic Concept Check grading without model calls."""

from __future__ import annotations

from typing import Literal

from cs30.v2.contracts import (
    ConceptCheckGrade,
    ConceptCheckQuestion,
    ConceptCheckResult,
)


class DeterministicGrader:
    def grade(
        self,
        question: ConceptCheckQuestion,
        *,
        attempt_id: str,
        selected_choice: Literal["A", "B", "C", "D"] | None,
    ) -> ConceptCheckGrade:
        if selected_choice is not None and selected_choice not in question.options:
            raise ValueError("selected_choice must be A, B, C, or D")
        if selected_choice is None:
            result, performance = ConceptCheckResult.SKIPPED, None
        elif selected_choice == question.correct_answer:
            result, performance = ConceptCheckResult.CORRECT, 1.0
        else:
            result, performance = ConceptCheckResult.INCORRECT, 0.0
        return ConceptCheckGrade(
            attempt_id=attempt_id,
            question_id=question.question_id,
            selected_choice=selected_choice,
            correct_answer=question.correct_answer,
            result=result,
            performance=performance,
        )
