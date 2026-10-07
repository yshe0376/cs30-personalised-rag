"""Shared synthetic Concept Check fixture pack for M7 and M8 development.

The pack holds five hand-written practice questions, the Topic registry they
use, their bindings to a small synthetic corpus, that corpus with its manifest
and chunk-to-Topic map, and named retrieval/citation scenarios.  The corpus
text paraphrases two College Physics 2e chapters; it is not produced by
``run_build_pipeline`` and its hash is a fixture value, so a release from this
pack never matches a real corpus.  The ``fixture-review:`` IDs stand in for M3
review records: no question here has been reviewed by M3 or may be shown as a
real practice question.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from importlib.resources import files
from typing import Any

from cs30.v2.catalog import get_textbook_spec
from cs30.v2.contracts import (
    ConceptCheckQuestion,
    ConceptCheckQuestionBinding,
    ConceptCheckQuestionRelease,
    EvidenceProvenance,
    GeneratedAnswer,
    RetrievalMode,
    RetrievalResult,
    RetrievedEvidence,
    TopicRegistry,
    ValidatedAnswer,
)
from cs30.v2.corpus.manifest import (
    CorpusDocument,
    CorpusManifest,
    CorpusManifestDraft,
    finalize_manifest,
)
from cs30.v2.ids import source_locator
from cs30.v2.topics import ChunkTopicMap, LoadedChunkTopicMap

FIXTURE_CORPUS_VERSION = "2.0.0-dev.1"
FIXTURE_CORPUS_HASH = "sha256:fixture-concept-check-v1"
FIXTURE_TOPIC_REGISTRY_VERSION = "fixture-topics-v1"
FIXTURE_CHUNK_CONFIG_HASH = "fixture-paragraph-chunks-v1"

__all__ = [
    "FIXTURE_CHUNK_CONFIG_HASH",
    "FIXTURE_CORPUS_HASH",
    "FIXTURE_CORPUS_VERSION",
    "FIXTURE_TOPIC_REGISTRY_VERSION",
    "FixtureChapter",
    "FixtureChunk",
    "FixtureCorpus",
    "FixtureScenario",
    "fixture_retrieval_result",
    "load_fixture_bindings",
    "load_fixture_chunk_topic_map",
    "load_fixture_corpus",
    "load_fixture_manifest",
    "load_fixture_questions",
    "load_fixture_releases",
    "load_fixture_scenarios",
    "load_fixture_topic_registry",
]


@dataclass(frozen=True)
class FixtureChapter:
    chapter_id: str
    title: str
    char_start: int
    char_end: int


@dataclass(frozen=True)
class FixtureChunk:
    chunk_id: str
    chapter_id: str
    char_start: int
    char_end: int


@dataclass(frozen=True)
class FixtureCorpus:
    """One synthetic document; offsets are document-global and half-open."""

    corpus_version: str
    corpus_hash: str
    textbook_id: str
    document_id: str
    text: str
    chapters: tuple[FixtureChapter, ...]
    chunks: tuple[FixtureChunk, ...]

    def chapter(self, chapter_id: str) -> FixtureChapter:
        for chapter in self.chapters:
            if chapter.chapter_id == chapter_id:
                return chapter
        raise KeyError(f"unknown fixture chapter: {chapter_id}")

    def chunk(self, chunk_id: str) -> FixtureChunk:
        for chunk in self.chunks:
            if chunk.chunk_id == chunk_id:
                return chunk
        raise KeyError(f"unknown fixture chunk: {chunk_id}")

    def chunk_text(self, chunk_id: str) -> str:
        chunk = self.chunk(chunk_id)
        return self.text[chunk.char_start : chunk.char_end]


def _load_json(name: str) -> Any:
    return json.loads(files(__package__).joinpath(name).read_text(encoding="utf-8"))


def load_fixture_corpus() -> FixtureCorpus:
    payload = _load_json("corpus.json")
    return FixtureCorpus(
        corpus_version=payload["corpus_version"],
        corpus_hash=payload["corpus_hash"],
        textbook_id=payload["textbook_id"],
        document_id=payload["document_id"],
        text=payload["text"],
        chapters=tuple(FixtureChapter(**chapter) for chapter in payload["chapters"]),
        chunks=tuple(FixtureChunk(**chunk) for chunk in payload["chunks"]),
    )


def load_fixture_manifest() -> CorpusManifest:
    """Finalize a development manifest for the fixture corpus.

    The document hashes are fixture values; only the corpus identity and chunk
    counts describe real content, which is what topic-map validation checks.
    """

    corpus = load_fixture_corpus()
    spec = get_textbook_spec(corpus.textbook_id)
    document = CorpusDocument(
        provider=spec.provider,
        textbook_id=corpus.textbook_id,
        document_id=corpus.document_id,
        document_hash="sha256:fixture-concept-check-document-v1",
        raw_source_sha256="sha256:fixture-concept-check-source-v1",
        parser_version="fixture-concept-check-v1",
        source_name=spec.source_name,
        source_uri=spec.source_uri,
        source_version=spec.source_version,
        license=spec.license,
        selected_chapters=tuple(chapter.chapter_id for chapter in corpus.chapters),
        chunk_count=len(corpus.chunks),
    )
    return finalize_manifest(
        CorpusManifestDraft(
            corpus_version=corpus.corpus_version,
            corpus_hash=corpus.corpus_hash,
            chunk_config_hash=FIXTURE_CHUNK_CONFIG_HASH,
            required_textbook_ids=(corpus.textbook_id,),
            included_textbook_ids=(corpus.textbook_id,),
            documents=(document,),
            record_count=len(corpus.chunks),
            mode="development",
        )
    )


def load_fixture_chunk_topic_map() -> LoadedChunkTopicMap:
    """Load the chunk-to-Topic map, validated against the fixture manifest.

    ``fixture-cp2e-ch4-p1`` maps to two Topics and ``fixture-cp2e-ch2-p3`` to
    none, so resolvers meet a split weight and an unmapped chunk.
    """

    return LoadedChunkTopicMap.validated(
        ChunkTopicMap.model_validate(_load_json("chunk_topic_map.json")),
        manifest=load_fixture_manifest(),
        corpus_chunk_ids=tuple(chunk.chunk_id for chunk in load_fixture_corpus().chunks),
    )


def load_fixture_topic_registry() -> TopicRegistry:
    return TopicRegistry.model_validate(_load_json("topic_registry.json"))


def load_fixture_questions() -> tuple[ConceptCheckQuestion, ...]:
    return tuple(ConceptCheckQuestion.model_validate(item) for item in _load_json("questions.json"))


def load_fixture_bindings() -> tuple[ConceptCheckQuestionBinding, ...]:
    return tuple(
        ConceptCheckQuestionBinding.model_validate(item)
        for item in _load_json(f"bindings-{FIXTURE_CORPUS_VERSION}.json")
    )


def load_fixture_releases() -> tuple[ConceptCheckQuestionRelease, ...]:
    """Pair each question with its binding; the release contract checks the pair."""

    bindings = {binding.question_id: binding for binding in load_fixture_bindings()}
    questions = load_fixture_questions()
    if set(bindings) != {question.question_id for question in questions}:
        raise ValueError("fixture questions and bindings must cover the same question IDs")
    return tuple(
        ConceptCheckQuestionRelease(question=question, binding=bindings[question.question_id])
        for question in questions
    )


def fixture_retrieval_result(
    chunk_ids: Sequence[str],
    *,
    query: str = "How does net force change an object's motion?",
) -> RetrievalResult:
    """Return a fixture-mode retrieval over the given chunks, in rank order.

    Its provenance carries the fixture corpus and manifest identity, so the
    bindings and Topic map from this pack match it and those of any other
    corpus do not.
    """

    corpus = load_fixture_corpus()
    manifest = load_fixture_manifest()
    spec = get_textbook_spec(corpus.textbook_id)
    hits = []
    for rank, chunk_id in enumerate(chunk_ids, start=1):
        try:
            chunk = corpus.chunk(chunk_id)
        except KeyError as exc:
            raise ValueError(str(exc.args[0])) from exc
        hits.append(
            RetrievedEvidence(
                provider=spec.provider,
                textbook_id=corpus.textbook_id,
                document_id=corpus.document_id,
                chunk_id=chunk.chunk_id,
                chapter_id=chunk.chapter_id,
                source_name=spec.source_name,
                source_locator=source_locator(
                    source_name=spec.source_name,
                    textbook_id=corpus.textbook_id,
                    chapter_id=chunk.chapter_id,
                    page_or_location=None,
                    char_start=chunk.char_start,
                    char_end=chunk.char_end,
                ),
                text=corpus.chunk_text(chunk.chunk_id),
                score=1.0 / rank,
                rank=rank,
                retriever_type=RetrievalMode.FIXTURE,
            )
        )
    return RetrievalResult(
        query=query,
        mode=RetrievalMode.FIXTURE,
        hits=tuple(hits),
        provenance=EvidenceProvenance(
            corpus_version=corpus.corpus_version,
            corpus_hash=corpus.corpus_hash,
            manifest_hash=manifest.manifest_hash,
            chunk_config_hash=manifest.chunk_config_hash,
            index_version="fixture-index-v1",
            retrieval_mode=RetrievalMode.FIXTURE,
            retrieval_config_hash="fixture-retrieval-v1",
        ),
    )


@dataclass(frozen=True)
class FixtureScenario:
    """A previous question and answer, with the Topics the resolver should find.

    ``query`` and ``answer`` stand for the turn a Concept Check follows; the
    answer is written from the cited chunks only, as a validated answer would
    be.  An ``expected_*_topic`` of ``None`` comes with the resolver error code
    expected instead.
    """

    scenario_id: str
    title: str
    query: str
    answer: str
    retrieved_chunk_ids: tuple[str, ...]
    cited_chunk_ids: tuple[str, ...]
    expected_retrieval_topic: str | None
    expected_retrieval_error: str | None
    expected_cited_topic: str | None
    expected_cited_error: str | None

    def retrieval(self) -> RetrievalResult:
        return fixture_retrieval_result(self.retrieved_chunk_ids, query=self.query)

    def validated_answer(self) -> ValidatedAnswer:
        """A citation-validated answer with this scenario's text and cited chunks."""

        return ValidatedAnswer(
            answer=GeneratedAnswer(
                explanation=self.answer,
                citations=self.cited_chunk_ids,
            ),
            resolved_citations=self.cited_chunk_ids,
            citation_status="passed",
        )


def load_fixture_scenarios() -> tuple[FixtureScenario, ...]:
    return tuple(
        FixtureScenario(
            **{
                **item,
                "retrieved_chunk_ids": tuple(item["retrieved_chunk_ids"]),
                "cited_chunk_ids": tuple(item["cited_chunk_ids"]),
            }
        )
        for item in _load_json("scenarios.json")
    )
