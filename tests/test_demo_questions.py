"""Behaviour tests for the real SciQ Demo question provider."""

import pytest

from cs30.contracts import SciQQuestion
from cs30.fixtures import load_fixture
from cs30.ports import QuestionProvider
from cs30.questions import DemoQuestionProvider


def test_demo_provider_satisfies_question_provider() -> None:
    provider = DemoQuestionProvider()

    assert isinstance(provider, QuestionProvider)
    question = provider.get("sciq-train-00226")
    assert isinstance(question, SciQQuestion)
    assert set(question.choices) == {"A", "B", "C", "D"}
    assert question.correct_choice == "D"
    assert question.support


def test_all_demo_questions_have_valid_contracts() -> None:
    provider = DemoQuestionProvider()
    payload = load_fixture("sciq_demo_questions.json")
    question_ids = [item["question_id"] for item in payload]
    assert len(question_ids) == 24
    assert len(set(question_ids)) == 24

    for question_id in question_ids:
        question = provider.get(question_id)
        assert set(question.choices) == {"A", "B", "C", "D"}
        assert question.support


def test_unknown_demo_question_raises_key_error() -> None:
    with pytest.raises(KeyError, match="unknown SciQ demo question_id"):
        DemoQuestionProvider().get("does-not-exist")