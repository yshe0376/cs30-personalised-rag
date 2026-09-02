"""Module boundaries for the Week 1 pipeline.

Each Protocol is a computational boundary between member-owned modules. A module
is integrated by supplying an implementation of its Protocol; orchestration
functions do not change. Computational packages ship fixture implementations
that stand in until the real ones land. The UI consumes ``PipelineRun`` directly.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from cs30.contracts import (
    Chunk,
    GeneratedAnswer,
    IndexArtifact,
    OpenStaxDocument,
    RetrievalMode,
    RetrievalResult,
    SciQQuestion,
    StudentLevel,
    StudentProfile,
)


@runtime_checkable
class DocumentParser(Protocol):
    """Member 2: OpenStax parsing, cleaning, and chaptering."""

    def parse(self, source: Path) -> OpenStaxDocument: ...


@runtime_checkable
class QuestionProvider(Protocol):
    """Member 3: validated SciQ demo questions."""

    def get(self, question_id: str) -> SciQQuestion: ...


@runtime_checkable
class Chunker(Protocol):
    """Member 4: structure-aware chunking with block metadata and char spans."""

    def chunk(self, document: OpenStaxDocument) -> list[Chunk]: ...


@runtime_checkable
class IndexBuilder(Protocol):
    """Member 5: embedding generation and the FAISS dense index."""

    def build(self, chunks: list[Chunk]) -> IndexArtifact: ...

    def load(self) -> IndexArtifact: ...


@runtime_checkable
class Retriever(Protocol):
    """One retrieval backend, implemented by M5 (dense) or M6 (BM25/hybrid)."""

    def load_index(self, artifact: IndexArtifact) -> None: ...

    def retrieve(self, query: str, top_k: int) -> RetrievalResult: ...


@runtime_checkable
class RetrievalService(Protocol):
    """Member 1: the integration seam for M5 and M6 retrieval backends."""

    def retrieve(self, query: str, top_k: int, mode: RetrievalMode) -> RetrievalResult: ...


@runtime_checkable
class ProfileProvider(Protocol):
    """Member 7: the student profile for a requested level."""

    def get(self, level: StudentLevel) -> StudentProfile: ...


@runtime_checkable
class AnswerGenerator(Protocol):
    """Member 7: personalised prompt, LLM call, and fixed JSON answer."""

    def generate(
        self,
        question: str,
        profile: StudentProfile,
        retrieval: RetrievalResult,
    ) -> GeneratedAnswer: ...
