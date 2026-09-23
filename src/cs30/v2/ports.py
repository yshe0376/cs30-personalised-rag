"""Dependency-injection ports and batch reports for v2 M1."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol, runtime_checkable

from cs30.v2.contracts import (
    Chunk,
    ConceptCheckEvent,
    ConceptCheckGrade,
    ConceptCheckQuestion,
    ConceptCheckQuestionRelease,
    EvidenceBundle,
    GeneratedAnswer,
    IndexArtifact,
    LearnerContextSnapshot,
    LearnerState,
    RetrievalResult,
    StudentProfile,
    TextbookDocument,
    TopicResolution,
    ValidatedAnswer,
)
from cs30.v2.corpus.manifest import CorpusManifest, CorpusManifestDraft


@dataclass(frozen=True)
class TextbookInput:
    textbook_id: str
    source_path: Path
    source_name: str
    source_version: str
    source_uri: str | None = None
    selected_chapters: tuple[str, ...] = ()
    expected_source_sha256: str | None = None


@dataclass(frozen=True)
class MaterialFailure:
    textbook_id: str
    source_path: Path
    stage: Literal["input", "parse", "clean", "chunk", "manifest", "index"]
    error_code: str
    error_type: str
    message: str


@dataclass(frozen=True)
class ParseBatchReport:
    documents: tuple[TextbookDocument, ...]
    failures: tuple[MaterialFailure, ...]


@dataclass(frozen=True)
class ChunkBatchReport:
    chunks: tuple[Chunk, ...]
    failures: tuple[MaterialFailure, ...]


@runtime_checkable
class DocumentParser(Protocol):
    def parse(self, input: TextbookInput) -> TextbookDocument: ...


@runtime_checkable
class ParserRegistry(Protocol):
    def parser_for(self, textbook_id: str) -> DocumentParser: ...


@runtime_checkable
class Chunker(Protocol):
    @property
    def config_hash(self) -> str: ...

    @property
    def version(self) -> str: ...

    def chunk(self, document: TextbookDocument) -> Sequence[Chunk]: ...


@runtime_checkable
class CorpusManifestBuilder(Protocol):
    def build(
        self,
        documents: Sequence[TextbookDocument],
        chunks: Sequence[Chunk],
        *,
        corpus_version: str,
        chunk_config_hash: str,
        required_textbook_ids: Sequence[str],
        mode: Literal["development", "official"],
        failed_textbook_ids: Sequence[str] = (),
    ) -> CorpusManifestDraft: ...


@runtime_checkable
class IndexBuilder(Protocol):
    def build(
        self,
        chunks: Sequence[Chunk],
        manifest: CorpusManifest,
        *,
        output_dir: Path,
    ) -> IndexArtifact: ...


@runtime_checkable
class RetrievalService(Protocol):
    """M6 retrieval seam for the v2 answer path."""

    def retrieve(self, query: str, *, top_k: int) -> RetrievalResult: ...


@runtime_checkable
class EvidenceBundleBuilder(Protocol):
    """M8 seam that turns retrieval hits into prompt/display evidence."""

    def build(
        self,
        retrieval: RetrievalResult,
        *,
        token_budget: int | None = None,
    ) -> EvidenceBundle: ...


@runtime_checkable
class AnswerGenerator(Protocol):
    """M7 seam for a grounded, profile-aware answer."""

    def generate(
        self,
        question: str,
        profile: StudentProfile | LearnerContextSnapshot,
        evidence: EvidenceBundle,
    ) -> GeneratedAnswer: ...


@runtime_checkable
class CitationValidator(Protocol):
    """M8 seam for validating answer citations against one evidence bundle."""

    def validate(
        self,
        answer: GeneratedAnswer,
        evidence: EvidenceBundle,
    ) -> ValidatedAnswer: ...


@runtime_checkable
class TopicResolver(Protocol):
    """M7 adapter seam for retrieval-topic and cited-topic resolution."""

    def resolve_retrieval_topic(self, retrieval: RetrievalResult) -> TopicResolution: ...

    def resolve_cited_topic(self, citations: Sequence[str]) -> TopicResolution: ...


@runtime_checkable
class LearnerStateSnapshotBuilder(Protocol):
    """Pure snapshot seam shared by reranking and generation."""

    def build(
        self,
        static_profile: StudentProfile,
        *,
        enabled: bool,
        learner_state: LearnerState | None = None,
        topic_resolution: TopicResolution | None = None,
    ) -> LearnerContextSnapshot: ...


@runtime_checkable
class ConceptCheckQuestionProvider(Protocol):
    """M7 fixture/production provider for published practice questions."""

    def select(
        self,
        *,
        topic_id: str,
        level: str,
        excluded_question_ids: Sequence[str] = (),
    ) -> ConceptCheckQuestion | None: ...


@runtime_checkable
class ConceptCheckValidator(Protocol):
    """Publication gate for question structure, provenance, and bindings."""

    def validate(self, release: ConceptCheckQuestionRelease) -> None: ...


@runtime_checkable
class ConceptCheckGrader(Protocol):
    """Deterministic grader; implementations must not call an LLM."""

    def grade(
        self,
        question: ConceptCheckQuestion,
        *,
        attempt_id: str,
        selected_choice: Literal["A", "B", "C", "D"] | None,
    ) -> ConceptCheckGrade: ...


@runtime_checkable
class ConceptCheckEventStore(Protocol):
    """Single-writer append-only event log seam."""

    def append(self, event: ConceptCheckEvent) -> ConceptCheckEvent: ...

    def events(self, profile_id: str) -> Sequence[ConceptCheckEvent]: ...


@runtime_checkable
class LearnerStateReplayer(Protocol):
    """Replay seam; the event stream remains the source of truth."""

    def replay(self, events: Sequence[ConceptCheckEvent]) -> LearnerState: ...
