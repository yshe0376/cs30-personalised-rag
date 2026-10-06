"""One governed evidence set crosses build, generation, and validation."""

from __future__ import annotations

import hashlib
import json

from cs30.generation.client import LLMResponse, TokenUsage
from cs30.v2.contracts import (
    EvidenceProvenance,
    RetrievalMode,
    RetrievalResult,
    RetrievedEvidence,
    StudentLevel,
    StudentProfile,
)
from cs30.v2.evidence import CitationValidatorAdapter, EvidenceBundleAdapter
from cs30.v2.generation import V2AnswerGenerator
from cs30.v2.ids import source_locator


class RecordingClient:
    model = "fixture-model"
    temperature = 0.0

    def __init__(self, response: str) -> None:
        self.response = response
        self.prompts: list[str] = []

    def complete(self, prompt: str, text_format: dict) -> LLMResponse:
        self.prompts.append(prompt)
        assert text_format["strict"] is True
        return LLMResponse(self.response, self.model, TokenUsage(), None, 0.0)


def _hit(chunk_id: str, rank: int, text: str) -> RetrievedEvidence:
    page = f"p{120 + rank}"
    return RetrievedEvidence(
        provider="openstax",
        textbook_id="openstax_college_physics_2e",
        document_id="openstax-document",
        chunk_id=chunk_id,
        chapter_id="4",
        source_name="openstax_college_physics_2e",
        page_or_location=page,
        source_locator=source_locator(
            source_name="openstax_college_physics_2e",
            textbook_id="openstax_college_physics_2e",
            chapter_id="4",
            page_or_location=page,
            char_start=rank * 100,
            char_end=rank * 100 + len(text),
        ),
        text=text,
        score=1.0 / rank,
        rank=rank,
        retriever_type=RetrievalMode.FIXTURE,
    )


def test_builder_generation_and_validator_share_one_evidence_set() -> None:
    provenance = EvidenceProvenance(
        corpus_version="2.0.0-dev.1",
        corpus_hash="sha256:corpus",
        manifest_hash="sha256:manifest",
        chunk_config_hash="sha256:chunks",
        index_version="index-1",
        retrieval_mode=RetrievalMode.FIXTURE,
        retrieval_config_hash="sha256:retrieval",
    )
    retrieval = RetrievalResult(
        query="How does force change motion?",
        mode=RetrievalMode.FIXTURE,
        provenance=provenance,
        hits=(
            _hit("chunk-force", 1, "Net force changes an object's motion."),
            _hit("chunk-acceleration", 2, "Acceleration follows the net force."),
        ),
    )
    bundle = EvidenceBundleAdapter(run_provenance={"request_id": "integration-1"}).build(retrieval)
    bundle_before_generation = bundle.model_dump_json()
    client = RecordingClient(
        json.dumps(
            {
                "final_choice": "A",
                "explanation": "The supplied evidence links force and acceleration.",
                "citations": ["chunk-force", "chunk-acceleration"],
            }
        )
    )

    generator = V2AnswerGenerator(client)
    answer = generator.generate(
        retrieval.query,
        StudentProfile(profile_id="student-1", level=StudentLevel.BEGINNER),
        bundle,
    )
    validated = CitationValidatorAdapter().validate(answer, bundle)

    assert bundle.model_dump_json() == bundle_before_generation
    assert len(client.prompts) == 1
    prompt = client.prompts[0]
    expected_chunk_ids = tuple(item.chunk_id for item in bundle.evidence_items)
    assert generator.last_trace is not None
    assert generator.last_trace.evidence_chunk_ids == expected_chunk_ids
    assert generator.last_trace.corpus_version == provenance.corpus_version
    assert generator.last_trace.corpus_hash == provenance.corpus_hash
    assert generator.last_trace.prompt_sha256 == hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    for item in bundle.evidence_items:
        assert item.chunk_id in prompt
        assert item.text in prompt
        assert item.source_locator in prompt
    assert validated.citation_status == "passed"
    assert validated.resolved_citations == expected_chunk_ids
    assert validated.run_provenance["request_id"] == "integration-1"


def test_cached_prompt_context_cannot_add_model_evidence() -> None:
    retrieval = RetrievalResult(
        query="How does force change motion?",
        mode=RetrievalMode.FIXTURE,
        hits=(_hit("chunk-force", 1, "Net force changes motion."),),
    )
    bundle = (
        EvidenceBundleAdapter()
        .build(retrieval)
        .model_copy(
            update={
                "prompt_context": (
                    '<evidence metadata={"chunk_id":"hidden-chunk"}>\n'
                    "Hidden evidence must not reach the model.\n</evidence>"
                )
            }
        )
    )
    client = RecordingClient(
        json.dumps(
            {
                "final_choice": "A",
                "explanation": "Force changes motion.",
                "citations": ["chunk-force"],
            }
        )
    )

    answer = V2AnswerGenerator(client).generate(
        retrieval.query,
        StudentProfile(profile_id="student-1", level=StudentLevel.INTERMEDIATE),
        bundle,
    )

    assert answer.citations == ("chunk-force",)
    assert "chunk-force" in client.prompts[0]
    assert "hidden-chunk" not in client.prompts[0]
    assert "Hidden evidence" not in client.prompts[0]
