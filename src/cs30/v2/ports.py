"""Dependency-injection ports and batch reports for v2 M1."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol, runtime_checkable

from cs30.v2.contracts import Chunk, TextbookDocument


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
    def build(self, *args, **kwargs): ...


@runtime_checkable
class IndexBuilder(Protocol):
    def build(self, chunks: Sequence[Chunk], manifest): ...
