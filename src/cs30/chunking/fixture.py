"""Fixture chunker used until real structure-aware chunking lands."""

from pydantic import TypeAdapter

from cs30.contracts import Chunk, TextbookDocument
from cs30.fixtures import load_fixture


class FixtureChunker:
    """Return the packaged chunks, ignoring the supplied document."""

    def chunk(self, document: TextbookDocument) -> list[Chunk]:
        return TypeAdapter(list[Chunk]).validate_python(load_fixture("chunks.json"))
