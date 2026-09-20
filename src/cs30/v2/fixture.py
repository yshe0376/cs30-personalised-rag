"""Deterministic plain-text parser used only for v2 M1 synthetic builds."""

from __future__ import annotations

from cs30.v2.catalog import TextbookSpec
from cs30.v2.contracts import ContentType, TextBlock, TextbookChapter, TextbookDocument
from cs30.v2.ids import (
    canonical_json_bytes,
    make_document_id,
    sha256_bytes,
)
from cs30.v2.ports import TextbookInput


class TextFixtureParser:
    """Treat a retained UTF-8 text file as one cleaned chapter.

    This is deliberately a fixture/parser adapter, not the M2 PDF or CK-12
    parser.  It preserves every byte decoded as text and gives later modules a
    real v2 identity and span to exercise.
    """

    version = "fixture-text-v2"

    def __init__(self, spec: TextbookSpec) -> None:
        self.spec = spec

    def parse(self, input: TextbookInput) -> TextbookDocument:
        raw = input.source_path.read_bytes()
        text = raw.decode("utf-8")
        if not text:
            raise ValueError("empty source file")
        selected_chapters = input.selected_chapters or ("1",)
        source_uri = input.source_uri or self.spec.source_uri
        source_version = input.source_version or self.spec.source_version
        document_payload = {
            "provider": self.spec.provider,
            "textbook_id": input.textbook_id,
            "source_name": input.source_name,
            "source_uri": source_uri,
            "source_version": source_version,
            "parser_version": self.version,
            "selected_chapters": selected_chapters,
            "text": text,
            "cleaning_version": "fixture-clean-v2",
        }
        document_hash = sha256_bytes(canonical_json_bytes(document_payload))
        raw_hash = sha256_bytes(raw)
        document_id = make_document_id(
            textbook_id=input.textbook_id,
            raw_source_sha256=raw_hash,
            document_hash=document_hash,
            parser_version=self.version,
            selected_chapters=selected_chapters,
        )
        return TextbookDocument(
            provider=self.spec.provider,
            textbook_id=input.textbook_id,
            document_id=document_id,
            title=self.spec.title,
            raw_source_sha256=raw_hash,
            document_hash=document_hash,
            parser_version=self.version,
            source_name=input.source_name,
            source_uri=source_uri,
            source_version=source_version,
            license=self.spec.license,
            selected_chapters=selected_chapters,
            text=text,
            chapters=(
                TextbookChapter(
                    chapter_id=selected_chapters[0],
                    title=selected_chapters[0],
                    char_start=0,
                    char_end=len(text),
                ),
            ),
            blocks=(
                TextBlock(
                    block_id="fixture-block-1",
                    chapter_id=selected_chapters[0],
                    content_type=ContentType.BODY,
                    char_start=0,
                    char_end=len(text),
                    page_or_location=f"chapter-{selected_chapters[0]}",
                ),
            ),
            cleaning_version="fixture-clean-v2",
        )
