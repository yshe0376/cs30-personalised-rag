"""Reference-bound rubric drafts owned by the offline evaluation workflow."""

from collections.abc import Mapping

from cs30.evaluation.open_answer_models import OpenAnswerRubric
from cs30.v2.contracts import GoldQuestion


def draft_rubrics(gold: Mapping[str, GoldQuestion], gold_hash: str) -> list[OpenAnswerRubric]:
    """Reference-bound starting points, without invented aliases or human review."""
    result = []
    for question in gold.values():
        if question.options or question.answerable is not True:
            continue
        references = [e.span.span_id for group in question.gold_core_evidence_sets for e in group]
        result.append(
            OpenAnswerRubric(
                question_id=question.question_id,
                gold_sha256=gold_hash,
                rubric_version="reference-draft-0.1",
                criteria=[
                    {
                        "criterion_id": "main_answer",
                        "description": (
                            "States the central answer correctly, allowing equivalent "
                            "wording. Do not mark a merely related fact as meeting this criterion. "
                            f"Question: {question.question}\nReference: {question.gold_answer_text}"
                        ),
                        "core": True,
                        "reference_span_ids": references,
                    },
                    {
                        "criterion_id": "required_completeness",
                        "description": (
                            "Includes every explanation, condition, reasoning step or result that "
                            "the question explicitly asks for and the reference evidence supports. "
                            "Do not demand extra details: if the question only asks for a term, "
                            "the correct term also satisfies completeness. If the main answer is "
                            "absent, mark missing. This draft needs question-specific human review."
                        ),
                        "reference_span_ids": references,
                    },
                ],
                required_paths=[["main_answer", "required_completeness"]],
            )
        )
    return result
