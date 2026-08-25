"""Fixture chunker used until real structure-aware chunking lands."""

from pydantic import TypeAdapter

from cs30.contracts import Chunk, OpenStaxDocument
from cs30.fixtures import load_fixture


class FixtureChunker:
    """Return the packaged chunks, ignoring the supplied document."""

    def chunk(self, document: OpenStaxDocument) -> list[Chunk]:
        return TypeAdapter(list[Chunk]).validate_python(load_fixture("chunks.json"))
