from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from cs30.learning.budget import BudgetedClient, PersistentRequestBudget
from cs30.learning.online_quiz import (
    AUTHOR_SCHEMA,
    OnlineQuizGenerator,
    OnlineQuizUnavailable,
    _parse_author_candidate,
)
from cs30.v2.contracts import StudentLevel


def _author_payload(**updates):
    payload = {
        "question": "Which statement follows from the evidence?",
        "options": [
            "Option one",
            "Option two",
            "Option three",
            "Option four",
        ],
        "correct_answer": "A",
        "rationale": "The passage directly supports option one.",
        "evidence_chunk_id": "chunk-1",
        "evidence_quote": "A sufficiently long verbatim textbook quote used as evidence.",
    }
    payload.update(updates)
    return payload


def test_author_candidate_maps_text_object_options_to_a_through_d():
    payload = _author_payload(
        options=[
            {"text": "Option one"},
            {"text": "Option two"},
            {"text": "Option three"},
            {"text": "Option four"},
        ]
    )

    candidate = _parse_author_candidate(payload)

    assert candidate.options == {
        "A": "Option one",
        "B": "Option two",
        "C": "Option three",
        "D": "Option four",
    }


def test_author_candidate_keeps_legacy_string_array_compatibility():
    candidate = _parse_author_candidate(_author_payload())

    assert candidate.options["A"] == "Option one"
    assert candidate.options["D"] == "Option four"


def test_author_schema_requires_every_field_and_text_object_options():
    assert set(AUTHOR_SCHEMA["required"]) == {
        "question",
        "options",
        "correct_answer",
        "rationale",
        "evidence_chunk_id",
        "evidence_quote",
    }
    assert AUTHOR_SCHEMA["properties"]["options"]["items"]["required"] == ["text"]


def test_author_candidate_rejects_text_option_objects_with_extra_fields():
    payload = _author_payload(
        options=[
            {"label": "A", "text": "Option one"},
            {"text": "Option two"},
            {"text": "Option three"},
            {"text": "Option four"},
        ]
    )

    with pytest.raises(ValueError, match="only a text field"):
        _parse_author_candidate(payload)


@pytest.mark.parametrize(
    ("options", "correct_answer", "message"),
    [
        (["Option one", "Option two", "Option three"], "A", "exactly four entries"),
        (["Same", "same", "Option three", "Option four"], "A", "distinct"),
        (["One", "Two", "Three", "Four"], "E", "A, B, C, or D"),
    ],
)
def test_author_candidate_rejects_invalid_option_sets(options, correct_answer, message):
    with pytest.raises(ValueError, match=message):
        _parse_author_candidate(
            _author_payload(options=options, correct_answer=correct_answer)
        )


def test_missing_author_fields_are_reported_after_two_budgeted_author_attempts(tmp_path):
    payload = _author_payload()
    payload.pop("rationale")
    payload.pop("evidence_chunk_id")
    payload.pop("evidence_quote")
    budget = PersistentRequestBudget(tmp_path / "request-count.json", total_cap=4)
    raw_author = _FakeClient(payload)
    raw_verifier = _FakeClient(payload)
    author = BudgetedClient(raw_author, budget)
    verifier = BudgetedClient(raw_verifier, budget)
    generator = OnlineQuizGenerator(
        author_client=author,
        verifier_client=verifier,
        corpus=SimpleNamespace(
            chunks_by_id={"chunk-1": SimpleNamespace(text="A textbook passage.")}
        ),
        topic_registry=SimpleNamespace(topic_registry_version="topic-registry-v1"),
        profile_id="learner-test",
        quiz_config=SimpleNamespace(allow_unreviewed_questions=False),
    )
    turn = SimpleNamespace(
        question="What follows from the passage?",
        validated_answer=SimpleNamespace(resolved_citations=("chunk-1",)),
    )

    with budget.operation(turn_id="turn-1", operation_id="quiz-turn-1-1", max_requests=4):
        with pytest.raises(
            OnlineQuizUnavailable,
            match=(
                "missing required fields: evidence_chunk_id, evidence_quote, rationale"
            ),
        ) as error:
            generator.generate(
                turn,
                quiz_index=1,
                topic=SimpleNamespace(topic_id="topic-1", title="Topic one"),
                target_level=StudentLevel.BEGINNER,
                cited_chunk_ids=("chunk-1",),
            )

    assert "after 2 candidate attempts" in str(error.value)
    assert "Which statement follows" not in str(error.value)
    assert raw_author.calls == 2
    assert raw_verifier.calls == 0
    assert budget.snapshot() == {"used": 2, "cap": 4, "remaining": 2}


class _FakeClient:
    model = "fake-model"

    def __init__(self, payload: dict):
        self.payload = payload
        self.calls = 0

    def complete(self, _prompt: str, _text_format: dict):
        self.calls += 1
        return SimpleNamespace(
            text=json.dumps(self.payload),
            usage=SimpleNamespace(input_tokens=1, output_tokens=1),
        )


def test_textbook_quiz_uses_author_answer_without_calling_reviewer(monkeypatch):
    from cs30.v2.contracts import EvidenceSpan

    author = _FakeClient(_author_payload())
    verifier = _FakeClient({})
    generator = OnlineQuizGenerator(
        author_client=author,
        verifier_client=verifier,
        corpus=SimpleNamespace(
            chunks_by_id={"chunk-1": SimpleNamespace(text="A textbook passage.")}
        ),
        topic_registry=SimpleNamespace(topic_registry_version="v1"),
        profile_id="learner-test",
        quiz_config=SimpleNamespace(allow_unreviewed_questions=False),
    )
    span = EvidenceSpan(
        span_id="span-1", textbook_id="book-1", chapter_id="1",
        chapter_char_start=0, chapter_char_end=len(_author_payload()["evidence_quote"]),
        verbatim_text=_author_payload()["evidence_quote"],
        origin_corpus_version="v1",
    )
    monkeypatch.setattr(generator, "_anchor", lambda *args: span)
    turn = SimpleNamespace(
        turn_id="turn-1", question="Question?",
        validated_answer=SimpleNamespace(resolved_citations=("chunk-1",)),
    )
    draft = generator.generate(
        turn, quiz_index=1, topic=SimpleNamespace(topic_id="t", title="T"),
        target_level=StudentLevel.BEGINNER, cited_chunk_ids=("chunk-1",),
    )
    assert author.calls == 1
    assert verifier.calls == 0
    assert draft.record.question.correct_answer == "A"
    assert draft.record.question.rationale == _author_payload()["rationale"]
    assert draft.record.question.evidence_anchors == (span,)
    assert draft.record.auto_check_status == "evidence_bound"


def test_question_without_locatable_textbook_quote_is_not_offered(monkeypatch):
    generator = OnlineQuizGenerator(
        author_client=_FakeClient(_author_payload()),
        corpus=SimpleNamespace(chunks_by_id={"chunk-1": SimpleNamespace(text="Passage.")}),
        topic_registry=SimpleNamespace(topic_registry_version="v1"),
        profile_id="learner-test",
        quiz_config=SimpleNamespace(allow_unreviewed_questions=False),
    )

    def reject_quote(*args):
        raise ValueError("Textbook quotation was not found")

    monkeypatch.setattr(generator, "_anchor", reject_quote)
    turn = SimpleNamespace(
        question="Question?", validated_answer=SimpleNamespace(resolved_citations=("chunk-1",))
    )
    with pytest.raises(OnlineQuizUnavailable, match="Textbook quotation was not found"):
        generator.generate(
            turn, quiz_index=1, topic=SimpleNamespace(topic_id="t", title="T"),
            target_level=StudentLevel.BEGINNER, cited_chunk_ids=("chunk-1",),
        )
