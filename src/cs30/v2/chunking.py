"""Small deterministic v2 chunker used by M1 fixtures and adapters."""

from __future__ import annotations

import re
from collections.abc import Mapping

from cs30.v2.contracts import Chunk, ChunkSpan, TextbookDocument
from cs30.v2.ids import chunk_config_hash, make_chunk_id, source_locator


class V2BlockChunker:
    """Emit one traceable chunk per parser block.

    M1 intentionally does not introduce a new token-size policy.  This adapter
    gives the parser/Manifest seam a deterministic chunk implementation; the
    production M4 chunker can replace it through the same port.
    """

    version = "v2-block-v1"
    is_fixture = True

    def __init__(self, *, tokenizer_name: str = "unicode-wordpunct-v1") -> None:
        self.tokenizer_name = tokenizer_name
        self._config_hash = chunk_config_hash(
            {
                "chunker_version": self.version,
                "tokenizer_name": tokenizer_name,
                "grouping": "one-block",
            }
        )

    @classmethod
    def from_config(cls, config: Mapping[str, str]) -> V2BlockChunker:
        supported = {"tokenizer_name"}
        unknown = set(config) - supported
        if unknown:
            raise ValueError(f"unsupported v2 chunk configuration: {sorted(unknown)}")
        return cls(tokenizer_name=config.get("tokenizer_name", "unicode-wordpunct-v1"))

    @property
    def config_hash(self) -> str:
        return self._config_hash

    def chunk(self, document: TextbookDocument) -> list[Chunk]:
        chunks: list[Chunk] = []
        for ordinal, block in enumerate(document.blocks, start=1):
            text = document.document_text(block)
            if not text.strip():
                raise ValueError(f"empty block cannot become a chunk: {block.block_id}")
            token_count = self._count_tokens(text)
            page_or_location = block.page_or_location or (
                f"chapter-{block.chapter_id}/block-{block.block_id}"
            )
            metadata = {
                "block_id": block.block_id,
                "chunker_version": self.version,
                "tokenizer_name": self.tokenizer_name,
            }
            if block.asset_ref:
                metadata["asset_ref"] = block.asset_ref
            chunks.append(
                Chunk(
                    chunk_id=make_chunk_id(
                        document.document_id,
                        block.chapter_id,
                        self.config_hash,
                        ordinal,
                    ),
                    provider=document.provider,
                    textbook_id=document.textbook_id,
                    document_id=document.document_id,
                    chapter_id=block.chapter_id,
                    source_name=document.source_name,
                    page_start=block.page_start,
                    page_end=block.page_end,
                    page_or_location=page_or_location,
                    section_id=block.section_id,
                    section_title=block.section_title,
                    source_locator=source_locator(
                        source_name=document.source_name,
                        textbook_id=document.textbook_id,
                        chapter_id=block.chapter_id,
                        page_or_location=page_or_location,
                        char_start=block.char_start,
                        char_end=block.char_end,
                    ),
                    text=text,
                    char_start=block.char_start,
                    char_end=block.char_end,
                    spans=(
                        ChunkSpan(
                            block_id=block.block_id,
                            chapter_id=block.chapter_id,
                            char_start=block.char_start,
                            char_end=block.char_end,
                            content_type=block.content_type,
                        ),
                    ),
                    chunker_version=self.version,
                    chunk_config_hash=self.config_hash,
                    token_count=token_count,
                    metadata=metadata,
                )
            )
        if not chunks:
            raise ValueError(f"document produced no chunks: {document.document_id}")
        return chunks

    @staticmethod
    def _count_tokens(text: str) -> int:
        return sum(1 for _ in re.finditer(r"\w+|[^\w\s]", text, flags=re.UNICODE))
