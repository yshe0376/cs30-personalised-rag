"""M7 v2 generation consumes only the supplied evidence bundle."""

from __future__ import annotations

import json

from cs30.generation.client import LLMResponse, TokenUsage
from cs30.v2.contracts import (
    EvidenceBundle,
    EvidenceItem,
    RetrievalMode,
    StudentLevel,
    StudentProfile,
)
from cs30.v2.generation import V2AnswerGenerator
from cs30.v2.ids import source_locator


class StubClient:
    model = "fixture-model"
    temperature = 0.0

    def __init__(self, responses: list[str | Exception]) -> None:
        self.responses = responses
        self.calls = 0
        self.prompts: list[str] = []

    def complete(self, prompt: str, text_format: dict) -> LLMResponse:
        self.calls += 1
        self.prompts.append(prompt)
        assert text_format["strict"] is True
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return LLMResponse(response, self.model, TokenUsage(), None, 0.0)


def _bundle(with_evidence: bool = True) -> EvidenceBundle:
    if not with_evidence:
        return EvidenceBundle(query="What is motion?", retrieval_mode=RetrievalMode.FIXTURE)
    item = EvidenceItem(
        evidence_id="E1",
        provider="openstax",
        textbook_id="book-1",
        document_id="document-1",
        chunk_id="chunk-1",
        chapter_id="chapter-1",
        source_name="book-1",
        page_or_location="p1",
        source_locator=source_locator(
            source_name="book-1",
            textbook_id="book-1",
            chapter_id="chapter-1",
            page_or_location="p1",
            char_start=0,
            char_end=11,
        ),
        text="Motion text",
        rank=1,
        score=1.0,
        token_count=2,
    )
    return EvidenceBundle(
        query="What is motion?",
        retrieval_mode=RetrievalMode.FIXTURE,
        evidence_items=(item,),
        citation_map={"E1": "chunk-1"},
        token_count=2,
    )


def _answer(citation: str) -> str:
    return json.dumps(
        {"final_choice": "A", "explanation": "Because of motion.", "citations": [citation]}
    )


def test_no_evidence_abstains_without_model_call() -> None:
    client = StubClient([])
    generator = V2AnswerGenerator(client)
    answer = generator.generate(
        "What is motion?",
        StudentProfile(profile_id="s", level=StudentLevel.BEGINNER),
        _bundle(False),
    )
    assert answer.abstained is True
    assert client.calls == 0
    assert generator.last_trace is not None and generator.last_trace.abstained is True


def test_invalid_citation_is_repaired_with_same_evidence() -> None:
    client = StubClient([_answer("made-up"), _answer("chunk-1")])
    generator = V2AnswerGenerator(client, max_retries=1)
    answer = generator.generate(
        "What is motion?",
        StudentProfile(profile_id="s", level=StudentLevel.BEGINNER),
        _bundle(),
    )
    assert answer.citations == ("chunk-1",)
    assert [item.status for item in generator.last_trace.attempts] == [
        "invalid_output",
        "completed",
    ]
    assert "book-1" in client.prompts[0]
    assert "chunk-1" in client.prompts[1]


def test_batch_keeps_failure_separate_from_success() -> None:
    client = StubClient([RuntimeError("provider down"), _answer("chunk-1")])
    generator = V2AnswerGenerator(client, max_retries=0)
    profile = StudentProfile(profile_id="s", level=StudentLevel.BEGINNER)
    cases = (("First", profile, _bundle()), ("Second", profile, _bundle()))
    results = generator.generate_batch(cases)
    assert results[0].answer is None
    assert results[0].trace.attempts[0].status == "provider_failure"
    assert results[1].answer is not None
    assert results[1].answer.citations == ("chunk-1",)
