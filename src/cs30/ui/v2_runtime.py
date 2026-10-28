"""UI-owned composition of existing V2 retrieval, generation and practice seams."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from uuid import uuid4

from cs30.concept_check.event_store import JsonlEventStore
from cs30.concept_check.fixtures import (
    fixture_retrieval_result,
    load_fixture_chunk_topic_map,
    load_fixture_corpus,
    load_fixture_releases,
    load_fixture_topic_registry,
)
from cs30.concept_check.learner_state import EventReplayer
from cs30.concept_check.provider import FixtureQuestionProvider
from cs30.concept_check.service import ConceptCheckService, PreparedRound
from cs30.concept_check.topics import ChunkTopicResolver
from cs30.contracts import IndexArtifact as LegacyArtifact
from cs30.generation.client import LLMClient, MockJsonLLMClient
from cs30.generation.compatible import OpenAICompatibleClient
from cs30.retrieval.real import BM25Retriever
from cs30.ui.concept_check_demo import DemoRuntime
from cs30.v2.config import ConceptCheckConfig
from cs30.v2.contracts import (
    EvidenceBundle,
    EvidenceProvenance,
    RetrievalMode,
    RetrievalResult,
    RetrievedEvidence,
    StudentProfile,
    TopicRegistry,
)
from cs30.v2.corpus.records import load_corpus_records
from cs30.v2.evidence import CitationValidatorAdapter, EvidenceBundleAdapter
from cs30.v2.generation import V2AnswerGenerator, V2GenerationTrace
from cs30.v2.io import canonical_hash
from cs30.v2.topics import LoadedChunkTopicMap, load_validated_chunk_topic_map

TEAM_MODEL = "openai/gpt-oss-20b"
TEAM_BASE_URL = "https://api.deepinfra.com/v1/openai"


@dataclass(frozen=True)
class UiCorpus:
    """Validated source identities used only by this UI composition layer."""

    hits: tuple[RetrievedEvidence, ...]
    provenance: EvidenceProvenance
    registry: TopicRegistry
    topic_map: LoadedChunkTopicMap
    synthetic: bool


@dataclass(frozen=True)
class QuestionRun:
    run_id: str
    runtime: DemoRuntime
    prepared: PreparedRound
    bundle: EvidenceBundle
    trace: V2GenerationTrace | None
    mode: str
    steps: tuple[str, ...]


def load_ui_corpus(corpus_dir: Path | None, topic_dir: Path, *, synthetic: bool) -> UiCorpus:
    """Load the existing fixture pack or hash-validated released V2 corpus."""

    if synthetic:
        corpus = load_fixture_corpus()
        result = fixture_retrieval_result([chunk.chunk_id for chunk in corpus.chunks])
        return UiCorpus(
            result.hits,
            result.provenance,
            load_fixture_topic_registry(),
            load_fixture_chunk_topic_map(),
            True,
        )
    if corpus_dir is None:
        raise ValueError("Set CS30_UI_CORPUS to the released V2 corpus directory.")
    corpus = load_corpus_records(corpus_dir)
    registry = TopicRegistry.model_validate_json(
        (topic_dir / "topic_registry_v0.2.json").read_text(encoding="utf-8")
    )
    topic_map = load_validated_chunk_topic_map(
        topic_dir / "chunk_topic_map_topics-0.2.json",
        manifest=corpus.manifest,
        corpus_chunk_ids=corpus.chunk_ids,
    )
    fields = (
        "provider",
        "textbook_id",
        "document_id",
        "chunk_id",
        "chapter_id",
        "source_name",
        "page_or_location",
        "source_locator",
        "text",
    )
    hits = tuple(
        RetrievedEvidence(
            **{name: getattr(chunk, name) for name in fields},
            score=0.0,
            rank=rank,
            retriever_type=RetrievalMode.BM25,
        )
        for rank, chunk in enumerate(corpus.chunks, 1)
    )
    manifest = corpus.manifest
    provenance = EvidenceProvenance(
        corpus_version=manifest.corpus_version,
        corpus_hash=manifest.corpus_hash,
        manifest_hash=manifest.manifest_hash,
        chunk_config_hash=manifest.chunk_config_hash,
        index_version="ui-bm25-baseline-1",
        retrieval_mode=RetrievalMode.BM25,
        retrieval_config_hash=canonical_hash({"backend": "BM25Retriever", "k1": 1.5, "b": 0.75}),
    )
    return UiCorpus(hits, provenance, registry, topic_map, False)


class UiBm25Retriever:
    """Adapt the existing BM25 backend; do not copy its scoring/tokenisation."""

    def __init__(self, corpus: UiCorpus, directory: Path) -> None:
        self.corpus = corpus
        self.by_id = {hit.chunk_id: hit for hit in corpus.hits}
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "chunks.json"
        data = json.dumps(
            [
                {
                    "position": i,
                    "chunk_id": hit.chunk_id,
                    "text": hit.text,
                    "chapter_id": hit.chapter_id,
                    "source": hit.source_name,
                }
                for i, hit in enumerate(corpus.hits)
            ],
            ensure_ascii=False,
        ).encode("utf-8")
        path.write_bytes(data)
        self.backend = BM25Retriever(cache_size=0)
        self.backend.load_index(
            LegacyArtifact(
                artifact_id="ui-bm25",
                index_type="bm25",
                location=str(directory),
                chunk_count=len(corpus.hits),
                metadata={
                    "chunk_map": str(path),
                    "chunk_map_sha256": hashlib.sha256(data).hexdigest(),
                    "corpus_hash": corpus.provenance.corpus_hash,
                    "chunk_config_hash": corpus.provenance.chunk_config_hash,
                    "index_version": "ui-bm25-baseline-1",
                },
            )
        )

    def retrieve(self, query: str, *, top_k: int = 5) -> RetrievalResult:
        result = self.backend.retrieve(query, top_k)
        mode = RetrievalMode.FIXTURE if self.corpus.synthetic else RetrievalMode.BM25
        hits = tuple(
            self.by_id[hit.chunk_id].model_copy(
                update={
                    "score": hit.score,
                    "rank": hit.rank,
                    "retriever_type": mode,
                }
            )
            for hit in result.hits
        )
        provenance = self.corpus.provenance.model_copy(
            update={
                "retrieval_mode": mode,
                "index_version": "ui-bm25-baseline-1",
                "retrieval_config_hash": canonical_hash(
                    {"backend": "BM25Retriever", "top_k": top_k}
                ),
            }
        )
        return RetrievalResult(query=result.query, mode=mode, hits=hits, provenance=provenance)


def make_service(corpus: UiCorpus, profile: StudentProfile, directory: Path, enabled: bool):
    """Compose shared state and provider without mixing fixture and real releases."""

    config = ConceptCheckConfig(enabled=enabled)
    replayer = EventReplayer(profile, corpus.registry, config)
    store = JsonlEventStore(directory, replayer)
    # Only the shared synthetic question pack is checked in. Never publish it for real data.
    releases = load_fixture_releases() if corpus.synthetic else ()
    service = ConceptCheckService(
        config=config,
        resolver=ChunkTopicResolver(corpus.topic_map, corpus.registry, config),
        provider=FixtureQuestionProvider(releases),
        event_store=store,
        replayer=replayer,
    )
    return service, store, replayer


def team_client(directory: Path, run_id: str) -> OpenAICompatibleClient:
    """Reuse M7's recorded DeepInfra settings; called only after a user submission."""

    if not os.environ.get("DEEPINFRA_API_KEY", "").strip():
        raise ValueError("DEEPINFRA_API_KEY is missing in the UI server environment.")
    client = OpenAICompatibleClient(
        TEAM_MODEL,
        base_url=TEAM_BASE_URL,
        provider_name="DeepInfra",
        model_version="public-model-alias;immutable-revision-unverified",
        api_key_env="DEEPINFRA_API_KEY",
        max_output_tokens=4096,
        structured_output="json_object",
        extra_body={"reasoning_effort": "low"},
        timeout_seconds=120,
        transport_retries=0,
        max_api_requests=2,
    )
    client.configure_run(directory)
    return client.for_cell(run_id, directory / "api_cache")


def run_question(
    question: str,
    profile: StudentProfile,
    corpus: UiCorpus,
    retriever: UiBm25Retriever,
    directory: Path,
    *,
    enabled: bool,
    live: bool,
    client: LLMClient | None = None,
    progress: Callable[[str], None] | None = None,
) -> QuestionRun:
    """Input -> retrieval -> snapshot -> bundle -> M7 generation -> citation validation."""

    if not question.strip():
        raise ValueError("Enter a physics question before running the pipeline.")
    if live and corpus.synthetic:
        raise ValueError("The team-model path requires the real V2 corpus.")
    run_id = "ui-" + uuid4().hex
    steps = []

    def step(label):
        steps.append(label)
        if progress:
            progress(label)

    step("Retrieve evidence · shared BM25 baseline")
    retrieval = retriever.retrieve(question, top_k=5)
    service, store, replayer = make_service(corpus, profile, directory / "events", enabled)
    step("Resolve retrieval Topic and build learner snapshot")
    prepared = service.prepare(retrieval, profile)
    step("Assemble V2 evidence bundle")
    bundle = EvidenceBundleAdapter(run_provenance={"run_id": run_id}).build(retrieval)
    step("Generate answer · M7 V2AnswerGenerator")
    if client is None:
        client = team_client(directory / run_id, run_id) if live else MockJsonLLMClient()
    generator = V2AnswerGenerator(client, max_retries=1)
    answer = generator.generate(question, prepared.snapshot, bundle)
    step("Validate citations against the same evidence bundle")
    validated = CitationValidatorAdapter().validate(answer, bundle)
    runtime = DemoRuntime(profile, retrieval, validated, service, store, replayer)
    step("Answer ready · optional cited-Topic Concept Check")
    return QuestionRun(
        run_id,
        runtime,
        prepared,
        bundle,
        generator.last_trace,
        "live-deepinfra" if live else "offline-integration",
        tuple(steps),
    )


def refresh_controls(run: QuestionRun, corpus: UiCorpus, directory: Path, enabled: bool):
    """Recompose the switch's service without rewriting the answer's original snapshot."""

    service, store, replayer = make_service(
        corpus, run.runtime.profile, directory / "events", enabled
    )
    return replace(run.runtime, service=service, event_store=store, replayer=replayer)
