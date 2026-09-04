import json
import urllib.error
from collections import Counter

import pytest

from cs30.config import load_config
from cs30.contracts import RetrievalHit, RetrievalMode, RetrievalResult, StudentLevel
from cs30.errors import GenerationError
from cs30.generation import (
    BatchItem,
    MockJsonLLMClient,
    OllamaChatClient,
    OpenAIResponsesClient,
    PersonalisedAnswerGenerator,
    PromptBuilder,
    build_sciq_smoke_items,
    format_sciq_question,
    generate_batch,
    load_sciq_questions,
)
from cs30.generation.client import LLMResponse, TokenUsage
from cs30.generation.demo import (
    LOCAL_SCIQ_DATASET,
    ORIGINAL_DATASET,
    TEAM_FREE_DATASET,
    TEAM_SCIQ_DATASET,
    build_all_dataset_items,
    build_demo_items,
)
from cs30.generation.exceptions import LLMProviderError
from cs30.generation.schema import parse_answer_payload
from cs30.pipeline import build_real_deps
from cs30.ports import AnswerGenerator, ProfileProvider, Retriever
from cs30.profile import Week1ProfileProvider
from cs30.questions import DemoQuestionProvider

QUESTION = """Which option describes acceleration?
A. The rate of change of velocity
B. The rate of change of position only
C. The amount of matter
D. The energy stored in an object"""


def retrieval(question: str = QUESTION) -> RetrievalResult:
    return RetrievalResult(
        query=question,
        mode=RetrievalMode.FIXTURE,
        hits=[
            RetrievalHit(
                chunk_id="chunk_acceleration",
                text="Acceleration is the rate at which velocity changes with time.",
                chapter_id="ch01",
                source="fixture://openstax/physics#ch01",
                score=0.97,
                rank=1,
                retriever_type=RetrievalMode.FIXTURE,
            ),
            RetrievalHit(
                chunk_id="chunk_velocity",
                text="Velocity describes the rate of change of position.",
                chapter_id="ch01",
                source="fixture://openstax/physics#ch01",
                score=0.81,
                rank=2,
                retriever_type=RetrievalMode.FIXTURE,
            ),
        ],
    )


class ScriptedClient:
    model = "scripted-test-model"
    temperature = 0.2

    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = 0

    def complete(self, prompt: str, text_format: dict) -> LLMResponse:
        del prompt, text_format
        self.calls += 1
        output = self.outputs.pop(0)
        if isinstance(output, Exception):
            raise output
        return LLMResponse(
            text=output,
            model=self.model,
            usage=TokenUsage(100, 20, 120),
            response_id=f"response-{self.calls}",
            latency_ms=1.0,
        )


def valid_output(citation: str = "chunk_acceleration") -> str:
    return json.dumps(
        {
            "final_choice": "A",
            "explanation": "Acceleration is the rate of change of velocity.",
            "citations": [citation],
        }
    )


def test_profile_provider_returns_all_three_levels() -> None:
    provider = Week1ProfileProvider()

    profiles = [provider.get(level) for level in StudentLevel]

    assert [profile.level for profile in profiles] == list(StudentLevel)
    assert len({profile.profile_id for profile in profiles}) == 3
    assert all(profile.confidence == 1.0 for profile in profiles)


def test_member7_real_modules_satisfy_their_protocols() -> None:
    assert isinstance(Week1ProfileProvider(), ProfileProvider)
    assert isinstance(PersonalisedAnswerGenerator(MockJsonLLMClient()), AnswerGenerator)


def test_local_rag_dependencies_keep_frozen_team_protocols() -> None:
    deps = build_real_deps(load_config("development"))

    assert isinstance(deps.profile_provider, ProfileProvider)
    assert isinstance(deps.retriever, Retriever)
    assert isinstance(deps.generator, AnswerGenerator)


def test_prompt_contains_profile_question_and_every_retrieved_chunk() -> None:
    profile = Week1ProfileProvider().get(StudentLevel.BEGINNER)

    prompt = PromptBuilder().build(QUESTION, profile, retrieval())

    assert "STUDENT_LEVEL: beginner" in prompt
    assert QUESTION in prompt
    assert "chunk_acceleration" in prompt
    assert "chunk_velocity" in prompt
    assert "untrusted source material" in prompt


def test_sciq_formatter_keeps_all_choices_for_generation() -> None:
    question = DemoQuestionProvider().get("sciq-train-00226")

    formatted = format_sciq_question(question)

    assert question.question in formatted
    for label, choice in question.choices.items():
        assert f"{label}. {choice}" in formatted


def test_week1_demo_contains_twenty_groundable_questions() -> None:
    items = build_demo_items(StudentLevel.INTERMEDIATE)

    assert len(items) == 20
    assert len({item.question_id for item in items}) == 20
    assert all(item.retrieval.hits for item in items)


def test_all_dataset_mode_combines_original_teammate_and_local_data(tmp_path) -> None:
    local_path = tmp_path / "local_sciq.json"
    local_path.write_text(
        json.dumps(
            {
                "rows": [
                    {
                        "row_idx": 7,
                        "row": {
                            "question": "What changes velocity per unit time?",
                            "distractor1": "distance",
                            "distractor2": "mass",
                            "distractor3": "energy",
                            "correct_answer": "acceleration",
                            "support": "Acceleration is the rate of change of velocity.",
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    dataset = build_all_dataset_items(
        StudentLevel.INTERMEDIATE,
        local_sciq_path=local_path,
    )

    assert len(dataset.items) == 53
    assert len({item.question_id for item in dataset.items}) == 53
    assert Counter(dataset.sources.values()) == {
        ORIGINAL_DATASET: 20,
        TEAM_SCIQ_DATASET: 24,
        TEAM_FREE_DATASET: 8,
        LOCAL_SCIQ_DATASET: 1,
    }
    assert len(dataset.gold_choices) == 25
    free_items = [
        item
        for item in dataset.items
        if dataset.sources[item.question_id] == TEAM_FREE_DATASET
    ]
    assert all(not item.retrieval.hits for item in free_items)


def test_all_dataset_mode_warns_without_ignored_local_file(tmp_path, caplog) -> None:
    missing_path = tmp_path / "missing.json"
    with caplog.at_level("WARNING", logger="cs30.generation.demo"):
        dataset = build_all_dataset_items(
            StudentLevel.INTERMEDIATE,
            local_sciq_path=missing_path,
        )

    assert len(dataset.items) == 52
    assert LOCAL_SCIQ_DATASET not in dataset.sources.values()
    assert f"local SciQ dataset not found at {missing_path}" in caplog.text
    assert "running with 3 packaged dataset sources" in caplog.text


def test_hugging_face_sciq_rows_become_grounded_smoke_items(tmp_path) -> None:
    source = tmp_path / "sciq.json"
    source.write_text(
        json.dumps(
            {
                "rows": [
                    {
                        "row_idx": 7,
                        "row": {
                            "question": "What changes velocity per unit time?",
                            "distractor1": "distance",
                            "distractor2": "mass",
                            "distractor3": "energy",
                            "correct_answer": "acceleration",
                            "support": "Acceleration is the rate of change of velocity.",
                        },
                        "truncated_cells": [],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    questions = load_sciq_questions(source)
    items = build_sciq_smoke_items(questions, StudentLevel.INTERMEDIATE)

    assert questions[0].question_id == "sciq_train_00007"
    assert questions[0].choices == {
        "A": "acceleration",
        "B": "distance",
        "C": "mass",
        "D": "energy",
    }
    assert items[0].question_id == questions[0].question_id
    assert "A. acceleration" in items[0].question
    assert items[0].retrieval.hits[0].chunk_id == "sciq_support_00007"
    assert items[0].retrieval.hits[0].source == "fixture://sciq-support/train"


def test_sciq_loader_rejects_missing_rows_list(tmp_path) -> None:
    source = tmp_path / "invalid.json"
    source.write_text('{"not_rows": []}', encoding="utf-8")

    with pytest.raises(ValueError, match="rows list"):
        load_sciq_questions(source)


def test_fixed_payload_rejects_markdown_and_extra_fields() -> None:
    with pytest.raises(GenerationError, match="not valid JSON"):
        parse_answer_payload(f"```json\n{valid_output()}\n```")

    payload = json.loads(valid_output())
    payload["confidence"] = 0.9
    with pytest.raises(GenerationError, match="Extra inputs"):
        parse_answer_payload(json.dumps(payload))


def test_generator_returns_schema_valid_grounded_answer() -> None:
    generator = PersonalisedAnswerGenerator(MockJsonLLMClient())
    profile = Week1ProfileProvider().get(StudentLevel.INTERMEDIATE)

    answer = generator.generate(QUESTION, profile, retrieval())

    assert answer.final_choice == "A"
    assert answer.citations == ["chunk_acceleration"]
    assert answer.abstained is False
    assert generator.last_trace is not None
    assert generator.last_trace.attempts == 1
    assert generator.last_trace.usage.total_tokens > 0


def test_three_levels_reach_prompt_and_change_explanation() -> None:
    generator = PersonalisedAnswerGenerator(MockJsonLLMClient())
    provider = Week1ProfileProvider()

    explanations = {
        level: generator.generate(QUESTION, provider.get(level), retrieval()).explanation
        for level in StudentLevel
    }

    assert len(set(explanations.values())) == 3


def test_empty_retrieval_abstains_without_calling_model() -> None:
    client = ScriptedClient([valid_output()])
    generator = PersonalisedAnswerGenerator(client)
    profile = Week1ProfileProvider().get(StudentLevel.BEGINNER)

    answer = generator.generate(
        "What is outside the corpus?",
        profile,
        RetrievalResult(
            query="What is outside the corpus?",
            mode=RetrievalMode.FIXTURE,
        ),
    )

    assert answer.abstained is True
    assert answer.final_choice is None
    assert answer.citations == []
    assert client.calls == 0
    assert generator.last_trace is not None
    assert generator.last_trace.attempts == 0


def test_invalid_json_is_repaired_within_finite_retry_budget() -> None:
    client = ScriptedClient(["not json", valid_output()])
    generator = PersonalisedAnswerGenerator(client, max_retries=2)
    profile = Week1ProfileProvider().get(StudentLevel.INTERMEDIATE)

    answer = generator.generate(QUESTION, profile, retrieval())

    assert answer.final_choice == "A"
    assert client.calls == 2
    assert generator.last_trace is not None
    assert generator.last_trace.attempts == 2
    assert generator.last_trace.failure_types == ("LLMOutputValidationError",)
    assert generator.last_trace.usage.total_tokens == 240


def test_unknown_citation_is_repaired_before_answer_is_returned() -> None:
    client = ScriptedClient([valid_output("invented_chunk"), valid_output()])
    generator = PersonalisedAnswerGenerator(client, max_retries=1)
    profile = Week1ProfileProvider().get(StudentLevel.ADVANCED)

    answer = generator.generate(QUESTION, profile, retrieval())

    assert answer.citations == ["chunk_acceleration"]
    assert generator.last_trace is not None
    assert generator.last_trace.failure_types == ("CitationIntegrityError",)


def test_provider_failure_stops_after_configured_attempts() -> None:
    client = ScriptedClient(
        [
            LLMProviderError("temporary failure"),
            LLMProviderError("temporary failure"),
            LLMProviderError("temporary failure"),
        ]
    )
    generator = PersonalisedAnswerGenerator(client, max_retries=2)
    profile = Week1ProfileProvider().get(StudentLevel.BEGINNER)

    with pytest.raises(GenerationError, match="failed after 3 attempts"):
        generator.generate(QUESTION, profile, retrieval())

    assert client.calls == 3
    assert generator.last_trace is not None
    assert generator.last_trace.attempts == 3
    assert generator.last_trace.failure_types == ("LLMProviderError",) * 3


def test_one_batch_failure_does_not_abort_later_questions() -> None:
    client = ScriptedClient([LLMProviderError("one failure"), valid_output()])
    generator = PersonalisedAnswerGenerator(client, max_retries=0)
    profile = Week1ProfileProvider().get(StudentLevel.INTERMEDIATE)
    items = [
        BatchItem("q-fails", QUESTION, profile, retrieval()),
        BatchItem("q-succeeds", QUESTION, profile, retrieval()),
    ]

    results = generate_batch(generator, items)

    assert [result.status for result in results] == ["failed", "completed"]
    assert results[0].error is not None
    assert results[1].answer is not None


def test_openai_client_sends_structured_output_and_reads_usage(monkeypatch) -> None:
    captured = {}

    class FakeResponse:
        headers = {"x-request-id": "request-123"}

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            del exc_type, exc, traceback

        def read(self):
            return json.dumps(
                {
                    "id": "response-123",
                    "model": "test-model-2026-01-01",
                    "output": [
                        {
                            "content": [
                                {"type": "output_text", "text": valid_output()},
                            ]
                        }
                    ],
                    "usage": {
                        "input_tokens": 12,
                        "output_tokens": 8,
                        "total_tokens": 20,
                    },
                }
            ).encode()

    def fake_urlopen(request, timeout):
        captured["body"] = json.loads(request.data)
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    client = OpenAIResponsesClient(
        "test-model",
        api_key="test-key-not-real",
        temperature=0.2,
        timeout_seconds=7,
    )

    response = client.complete("prompt", {"type": "json_schema", "schema": {}})

    assert captured["body"]["text"]["format"]["type"] == "json_schema"
    assert captured["body"]["store"] is False
    assert captured["body"]["temperature"] == 0.2
    assert captured["timeout"] == 7
    assert response.response_id == "request-123"
    assert response.usage.total_tokens == 20


def test_openai_client_classifies_timeout(monkeypatch) -> None:
    def fail(*args, **kwargs):
        del args, kwargs
        raise urllib.error.URLError(TimeoutError("timed out"))

    monkeypatch.setattr("urllib.request.urlopen", fail)
    client = OpenAIResponsesClient("test-model", api_key="test-key-not-real")

    with pytest.raises(GenerationError, match="timed out"):
        client.complete("prompt", {"type": "json_schema", "schema": {}})


def test_ollama_client_sends_local_schema_and_reads_usage(monkeypatch) -> None:
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            del exc_type, exc, traceback

        def read(self):
            return json.dumps(
                {
                    "model": "gpt-oss:20b",
                    "message": {"role": "assistant", "content": valid_output()},
                    "prompt_eval_count": 15,
                    "eval_count": 9,
                    "done": True,
                }
            ).encode()

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data)
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    client = OllamaChatClient(
        "gpt-oss:20b",
        base_url="http://127.0.0.1:11434/",
        temperature=0.0,
        timeout_seconds=12,
        max_output_tokens=500,
    )
    schema = {"type": "object", "properties": {"explanation": {"type": "string"}}}

    response = client.complete(
        "prompt",
        {"type": "json_schema", "name": "generated_answer", "schema": schema},
    )

    assert captured["url"] == "http://127.0.0.1:11434/api/chat"
    assert captured["body"]["stream"] is False
    assert captured["body"]["format"] == schema
    assert captured["body"]["options"] == {"num_predict": 500, "temperature": 0.0}
    assert captured["timeout"] == 12
    assert response.text == valid_output()
    assert response.usage == TokenUsage(input_tokens=15, output_tokens=9, total_tokens=24)


def test_ollama_client_explains_connection_failure(monkeypatch) -> None:
    def fail(*args, **kwargs):
        del args, kwargs
        raise urllib.error.URLError(ConnectionRefusedError("connection refused"))

    monkeypatch.setattr("urllib.request.urlopen", fail)
    client = OllamaChatClient("gpt-oss:20b")

    with pytest.raises(GenerationError, match="installed and running"):
        client.complete("prompt", {"type": "json_schema", "schema": {}})
