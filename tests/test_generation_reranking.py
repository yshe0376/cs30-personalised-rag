import json
import sys

import pytest

from cs30.citation import build_evidence_bundle, resolve_and_validate
from cs30.contracts import (
    RetrievalHit,
    RetrievalMode,
    RetrievalResult,
    StudentLevel,
    StudentProfile,
)
from cs30.generation import (
    EvidenceRole,
    FourConditionRunner,
    GenerationCondition,
    LevelAwareReranker,
    MockJsonLLMClient,
    PersonalisedAnswerGenerator,
    RerankConfig,
    RoleLabel,
)
from cs30.generation.ablation_demo import main as ablation_main
from cs30.generation.client import LLMResponse, TokenUsage
from cs30.generation.exceptions import LLMProviderError

QUESTION = "Why can an object accelerate when a net force acts on it?"


def candidates() -> RetrievalResult:
    return RetrievalResult(
        query=QUESTION,
        mode=RetrievalMode.FIXTURE,
        hits=[
            RetrievalHit(
                chunk_id="derivation",
                text="From F = ma, acceleration follows by dividing net force by mass.",
                chapter_id="forces",
                source="fixture://roles",
                score=0.95,
                rank=1,
                retriever_type=RetrievalMode.FIXTURE,
            ),
            RetrievalHit(
                chunk_id="definition",
                text="Acceleration is the rate at which velocity changes with time.",
                chapter_id="motion",
                source="fixture://roles",
                score=0.90,
                rank=2,
                retriever_type=RetrievalMode.FIXTURE,
            ),
            RetrievalHit(
                chunk_id="unlabelled",
                text="A larger net force produces a larger acceleration for fixed mass.",
                chapter_id="forces",
                source="fixture://roles",
                score=0.70,
                rank=3,
                retriever_type=RetrievalMode.FIXTURE,
            ),
        ],
    )


def labels() -> dict[str, RoleLabel]:
    return {
        "derivation": RoleLabel.single(EvidenceRole.DERIVATION),
        "definition": RoleLabel.single(EvidenceRole.DEFINITION),
    }


def profile(*, confidence: float = 1.0) -> StudentProfile:
    return StudentProfile(
        profile_id="fixture-beginner",
        level=StudentLevel.BEGINNER,
        confidence=confidence,
    )


def test_zero_lambda_restores_original_order_exactly() -> None:
    original = candidates()
    result = LevelAwareReranker(
        labels(),
        config=RerankConfig(lambda_weight=0.0),
    ).rerank(original, profile())

    assert [hit.chunk_id for hit in result.evidence.hits] == [hit.chunk_id for hit in original.hits]
    assert [hit.score for hit in result.evidence.hits] == [hit.score for hit in original.hits]
    assert result.trace.effective_lambda == 0.0


def test_level_and_confidence_drive_soft_reranking() -> None:
    reranker = LevelAwareReranker(labels(), config=RerankConfig(lambda_weight=0.8))

    full = reranker.rerank(candidates(), profile(confidence=1.0))
    partial = reranker.rerank(candidates(), profile(confidence=0.25))
    disabled = reranker.rerank(candidates(), profile(confidence=0.0))

    assert full.evidence.hits[0].chunk_id == "definition"
    assert full.trace.effective_lambda == pytest.approx(0.8)
    assert partial.trace.effective_lambda == pytest.approx(0.2)
    assert [hit.chunk_id for hit in disabled.evidence.hits] == [
        "derivation",
        "definition",
        "unlabelled",
    ]


def test_missing_and_ambiguous_labels_use_recorded_retrieval_fallback() -> None:
    role_labels = labels() | {
        "definition": RoleLabel(
            (EvidenceRole.DEFINITION, EvidenceRole.EXAMPLE),
            source="fixture-double-label",
        )
    }
    result = LevelAwareReranker(role_labels).rerank(candidates(), profile())
    traces = {row.chunk_id: row for row in result.trace.candidates}

    assert traces["definition"].fallback_reason == "ambiguous_label"
    assert traces["unlabelled"].fallback_reason == "missing_label"
    assert traces["definition"].role_match == traces["definition"].normalised_retrieval_score
    assert traces["unlabelled"].role_match == traces["unlabelled"].normalised_retrieval_score


def test_bundle_reranking_preserves_scores_citation_map_and_selected_ids() -> None:
    bundle = build_evidence_bundle(candidates())
    result = LevelAwareReranker(
        labels(),
        config=RerankConfig(lambda_weight=0.8),
    ).rerank(bundle, profile())

    assert result.evidence.evidence_items[0].chunk_id == "definition"
    assert result.evidence.citation_map == bundle.citation_map
    assert {item.chunk_id for item in result.evidence.evidence_items} == {
        item.chunk_id for item in bundle.evidence_items
    }
    assert {item.chunk_id: item.score for item in result.evidence.evidence_items} == {
        item.chunk_id: item.score for item in bundle.evidence_items
    }

    answer = PersonalisedAnswerGenerator(MockJsonLLMClient()).generate(
        QUESTION,
        profile(),
        result.evidence,
    )
    assert answer.citations == ["definition"]
    assert resolve_and_validate(answer, result.evidence).citation_status == "passed"


class RecordingClient(MockJsonLLMClient):
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def complete(self, prompt: str, text_format: dict) -> LLMResponse:
        self.prompts.append(prompt)
        return super().complete(prompt, text_format)


def test_four_conditions_share_inputs_and_keep_prompt_and_reranking_independent() -> None:
    client = RecordingClient()
    generator = PersonalisedAnswerGenerator(client)
    runner = FourConditionRunner(
        generator,
        LevelAwareReranker(labels(), config=RerankConfig(lambda_weight=0.8)),
    )

    results = runner.run_all(QUESTION, profile(), candidates())

    assert [result.condition for result in results] == list(GenerationCondition)
    assert len({result.condition.condition_id for result in results}) == 4
    assert all(result.input_candidate_ids == results[0].input_candidate_ids for result in results)
    assert results[0].output_candidate_ids == results[1].output_candidate_ids
    assert results[2].output_candidate_ids == results[3].output_candidate_ids
    assert results[0].output_candidate_ids != results[2].output_candidate_ids
    assert all(result.generation_trace.model == client.model for result in results)

    plain_prompt, prompt_only, reranking_only, combined = client.prompts
    assert "PROMPT_PERSONALISATION: disabled" in plain_prompt
    assert "You are a personalised physics learning assistant." in prompt_only
    assert "PROMPT_PERSONALISATION: disabled" in reranking_only
    assert "You are a personalised physics learning assistant." in combined
    assert "fixture-beginner" not in plain_prompt
    assert "fixture-beginner" not in reranking_only
    assert "fixture-beginner" in prompt_only
    assert "fixture-beginner" in combined


def test_saved_generation_trace_separates_rejected_and_repaired_raw_outputs() -> None:
    valid = json.dumps(
        {
            "final_choice": None,
            "explanation": "The cited evidence explains acceleration.",
            "citations": ["derivation"],
        }
    )

    class RepairClient:
        model = "repair-fixture-model"
        temperature = 0.0

        def __init__(self) -> None:
            self.outputs = ["not-json", valid]

        def complete(self, prompt: str, text_format: dict) -> LLMResponse:
            del prompt, text_format
            raw = self.outputs.pop(0)
            return LLMResponse(raw, self.model, TokenUsage(10, 5, 15), None, 1.0)

    generator = PersonalisedAnswerGenerator(RepairClient(), max_retries=1)
    generator.generate(QUESTION, profile(), candidates())
    trace = generator.last_trace

    assert trace is not None
    assert [record.status for record in trace.attempt_records] == ["rejected", "completed"]
    assert [record.raw_output for record in trace.attempt_records] == ["not-json", valid]
    assert [record.is_repair for record in trace.attempt_records] == [False, True]
    assert trace.prompt_sha256 is not None
    assert trace.profile_snapshot["profile_id"] == "fixture-beginner"


def test_provider_retry_is_not_mislabelled_as_a_repair_prompt() -> None:
    valid = json.dumps(
        {
            "final_choice": None,
            "explanation": "The evidence explains acceleration.",
            "citations": ["derivation"],
        }
    )

    class RetryClient:
        model = "retry-fixture-model"
        temperature = 0.0

        def __init__(self) -> None:
            self.calls = 0

        def complete(self, prompt: str, text_format: dict) -> LLMResponse:
            del prompt, text_format
            self.calls += 1
            if self.calls == 1:
                raise LLMProviderError("temporary fixture failure")
            return LLMResponse(valid, self.model, TokenUsage(), None, 1.0)

    generator = PersonalisedAnswerGenerator(RetryClient(), max_retries=1)
    generator.generate(QUESTION, profile(), candidates())

    assert generator.last_trace is not None
    assert [record.is_repair for record in generator.last_trace.attempt_records] == [
        False,
        False,
    ]


def test_rerank_config_rejects_test_tuning_source() -> None:
    with pytest.raises(ValueError, match="Test tuning is forbidden"):
        RerankConfig(parameter_source="test")  # type: ignore[arg-type]


def test_fixture_demo_marks_generation_evidence_and_labels_separately(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "four-conditions.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "cs30.generation.ablation_demo",
            "--provider",
            "mock",
            "--output",
            str(output),
        ],
    )

    ablation_main()

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["run_classification"] == {
        "generation": "fixture",
        "evidence": "fixture",
        "role_labels": "fixture",
        "reportable": False,
    }
    assert payload["provider"] == "mock"
    assert payload["model"] == "mock-json-generator"
