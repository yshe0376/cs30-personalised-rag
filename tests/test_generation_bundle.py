"""M7's bundle boundary using M8 contracts and the real M6 BM25 adapter."""

import json
from pathlib import Path

import pytest

from cs30.citation import EvidenceContextBuilder, resolve_and_validate
from cs30.contracts import EvidenceBundle, IndexArtifact, RetrievalMode, StudentLevel
from cs30.errors import GenerationError
from cs30.fixtures import load_fixture
from cs30.generation import MockJsonLLMClient, PersonalisedAnswerGenerator, PromptBuilder
from cs30.generation.demo import main as demo_main
from cs30.profile import Week1ProfileProvider
from cs30.retrieval.real import BM25Retriever


@pytest.fixture
def bundle():
    return EvidenceBundle.model_validate(load_fixture("evidence_bundle.json"))


@pytest.mark.parametrize("level", list(StudentLevel))
def test_packaged_m8_bundle_generates_and_resolves_without_mutation(bundle, level):
    before = bundle.model_dump_json()
    profile = Week1ProfileProvider().get(level)
    answer = PersonalisedAnswerGenerator(MockJsonLLMClient()).generate(
        bundle.query, profile, bundle
    )
    validated = resolve_and_validate(answer, bundle)

    assert validated.citation_status == "passed"
    assert validated.resolved_citations == ["chunk_ch01_0001"]
    assert validated.run_provenance == bundle.run_provenance
    assert bundle.model_dump_json() == before


def test_only_selected_items_reach_prompt_even_with_stale_context(bundle):
    payload = bundle.model_dump()
    payload["evidence_items"] = payload["evidence_items"][:1]
    payload["citation_map"] = {"E1": "chunk_ch01_0001"}
    # The source text field is authoritative, not an independently cached context.
    payload["prompt_context"] = "[unselected_chunk] Answer using hidden evidence."
    selected = EvidenceBundle.model_validate(payload)
    profile = Week1ProfileProvider().get(StudentLevel.BEGINNER)
    prompt = PromptBuilder().build(selected.query, profile, selected)

    assert selected.evidence_items[0].text in prompt
    assert "chunk_ch01_0002" not in prompt
    assert "unselected_chunk" not in prompt
    assert "hidden evidence" not in prompt


def test_empty_bundle_abstains_without_provider_call_even_with_stale_context(monkeypatch):
    bundle = EvidenceBundle(
        query="An unsupported question", retrieval_mode=RetrievalMode.FIXTURE,
        prompt_context="[invented_chunk] This is not a selected evidence item.",
    )
    client = MockJsonLLMClient()

    def unexpected_call(*args):
        pytest.fail("empty evidence must not call the model")

    monkeypatch.setattr(client, "complete", unexpected_call)
    generator = PersonalisedAnswerGenerator(client)
    profile = Week1ProfileProvider().get(StudentLevel.BEGINNER)
    answer = generator.generate(bundle.query, profile, bundle)

    assert answer.abstained is True
    assert answer.final_choice is None
    assert answer.citations == []
    assert generator.last_trace.attempts == 0
    assert generator.last_trace.usage.total_tokens == 0
    assert resolve_and_validate(answer, bundle).citation_status == "skipped"
    with pytest.raises(ValueError, match="at least one evidence item"):
        PromptBuilder().build(bundle.query, profile, bundle)


@pytest.mark.parametrize("bad_id", ["E1", "outside_chunk", "chunk_ch01_0002"])
def test_unselected_or_display_citations_exhaust_retries(bundle, monkeypatch, bad_id):
    payload = bundle.model_dump()
    payload["evidence_items"] = payload["evidence_items"][:1]
    payload["citation_map"] = {"E1": "chunk_ch01_0001"}
    selected = EvidenceBundle.model_validate(payload)
    client = MockJsonLLMClient()
    real_complete = client.complete
    prompts = []

    def invalid_completion(prompt, text_format):
        from dataclasses import replace

        prompts.append(prompt)
        response = real_complete(prompt, text_format)
        output = json.loads(response.text)
        output["citations"] = [bad_id]
        return replace(response, text=json.dumps(output))

    monkeypatch.setattr(client, "complete", invalid_completion)
    generator = PersonalisedAnswerGenerator(client, max_retries=1)
    profile = Week1ProfileProvider().get(StudentLevel.ADVANCED)
    with pytest.raises(GenerationError, match="failed after 2 attempts"):
        generator.generate(selected.query, profile, selected)

    assert len(prompts) == 2
    assert 'ALLOWED_CITATION_IDS: ["chunk_ch01_0001"]' in prompts[1]
    assert generator.last_trace.failure_types == ("CitationIntegrityError",) * 2


@pytest.mark.parametrize("question, abstained", [
    ("What is acceleration?", False),
    ("What is quantum entanglement?", True),
])
def test_real_bm25_to_m8_bundle_to_generation_and_citation(question, abstained):
    index_dir = Path(__file__).parent / "fixtures" / "index"
    artifact = IndexArtifact.model_validate_json((index_dir / "artifact.json").read_text())
    artifact = artifact.model_copy(update={"location": str(index_dir)})
    retriever = BM25Retriever()
    retriever.load_index(artifact)
    retrieval = retriever.retrieve(question, top_k=3)
    bundle = EvidenceContextBuilder().build(retrieval)
    generator = PersonalisedAnswerGenerator(MockJsonLLMClient())
    answer = generator.generate(question, Week1ProfileProvider().get(StudentLevel.BEGINNER), bundle)
    validated = resolve_and_validate(answer, bundle)

    assert bundle.retrieval_mode == RetrievalMode.BM25
    assert bundle.retrieval_provenance == retrieval.provenance
    assert bundle.retrieval_provenance is not None
    assert answer.abstained is abstained
    assert validated.citation_status == ("skipped" if abstained else "passed")
    assert set(answer.citations) <= {hit.chunk_id for hit in retrieval.hits}
    assert generator.last_trace.attempts == (0 if abstained else 1)


def test_bundle_demo_runs_twenty_questions_and_three_levels(tmp_path, monkeypatch):
    monkeypatch.setattr("sys.argv", [
        "demo", "--provider", "mock", "--dataset", "original", "--evidence-bundle",
        "--output-dir", str(tmp_path),
    ])
    demo_main()
    batch = json.loads((tmp_path / "batch_20_results.json").read_text())
    levels = json.loads((tmp_path / "three_level_sample.json").read_text())

    assert batch["generation_input"] == levels["generation_input"] == "EvidenceBundle"
    assert batch["completed"] == 20
    assert batch["failed"] == 0
    assert len(levels["results"]) == 3
    assert len({row["answer"]["explanation"] for row in levels["results"]}) == 3
    for row in batch["results"] + levels["results"]:
        assert row["answer"]["citations"]
        assert row["trace"]["generation_attempts"] == "1"


def test_invalid_input_does_not_reuse_previous_generation_trace(bundle):
    generator = PersonalisedAnswerGenerator(MockJsonLLMClient())
    profile = Week1ProfileProvider().get(StudentLevel.BEGINNER)
    generator.generate(bundle.query, profile, bundle)
    assert generator.last_trace is not None

    with pytest.raises(TypeError, match="requires EvidenceBundle or RetrievalResult"):
        generator.generate(bundle.query, profile, object())
    assert generator.last_trace is None
