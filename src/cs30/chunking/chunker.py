"""Block-boundary-aware, traceable chunking for OpenStax documents."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Sequence
from typing import Protocol

from cs30.chunking.strategy import BlockChunkingStrategy
from cs30.contracts import Chunk, OpenStaxDocument, TextBlock


class TokenCounter(Protocol):
    """Minimal token-counting boundary required by the chunker."""

    name: str

    def count(self, text: str) -> int:
        """Return the number of tokens in ``text`` without truncation."""


class UnicodeWordPunctTokenCounter:
    """Dependency-free provisional counter with deterministic behaviour.

    Member 5 should inject the final embedding model's tokenizer before the
    production index is built. The provisional name is retained in metadata so
    fixture results cannot be mistaken for model-tokenizer results.
    """

    name = "unicode_wordpunct_v1_provisional"
    _pattern = re.compile(r"\w+|[^\w\s]", flags=re.UNICODE)

    def count(self, text: str) -> int:
        return sum(1 for _ in self._pattern.finditer(text))


class BlockAwareChunker:
    """Group whole parser blocks into chunks near one token-size target.

    Boundaries always coincide with ``TextBlock`` boundaries. Chunks never mix
    chapters and, by default, never mix sections. Character offsets address the
    complete ``OpenStaxDocument.text`` string required by the shared contract.
    """

    def __init__(
        self,
        *,
        strategy: BlockChunkingStrategy | None = None,
        token_counter: TokenCounter | None = None,
    ) -> None:
        self.strategy = strategy or BlockChunkingStrategy()
        self.token_counter = token_counter or UnicodeWordPunctTokenCounter()

    def chunk(self, document: OpenStaxDocument) -> list[Chunk]:
        """Implement ``cs30.ports.Chunker`` for a normalised document."""

        chunks: list[Chunk] = []
        chunk_index = 1
        for segment in self._segments(document.blocks):
            for block_group in self._partition_segment(document, segment):
                chunks.append(self._build_chunk(document, block_group, chunk_index))
                chunk_index += 1

        if not chunks:
            raise ValueError("document did not produce any non-empty chunks")
        self._validate_output(chunks)
        return chunks

    def _segments(self, blocks: Sequence[TextBlock]) -> list[list[TextBlock]]:
        """Create consecutive chapter/section segments from parser structure."""

        segments: list[list[TextBlock]] = []
        current: list[TextBlock] = []
        current_key: tuple[str, str | None] | None = None
        for block in blocks:
            section_key = block.section_id if self.strategy.respect_section_boundaries else None
            key = (block.chapter_id, section_key)
            if current and key != current_key:
                segments.append(current)
                current = []
            current.append(block)
            current_key = key
        if current:
            segments.append(current)
        return segments

    def _partition_segment(
        self,
        document: OpenStaxDocument,
        blocks: list[TextBlock],
    ) -> list[list[TextBlock]]:
        """Greedily choose the nearest whole-block group to the token target."""

        groups: list[list[TextBlock]] = []
        start = 0
        while start < len(blocks):
            best_end: int | None = None
            best_distance: int | None = None
            for end in range(start + 1, len(blocks) + 1):
                count = self._group_token_count(document, blocks[start:end])
                if count > self.strategy.max_tokens:
                    if best_end is None:
                        best_end = end
                    break
                if count == 0:
                    continue
                distance = abs(self.strategy.target_tokens - count)
                if best_distance is None or distance < best_distance:
                    best_end = end
                    best_distance = distance
                if count >= self.strategy.target_tokens:
                    break

            if best_end is None:
                # Remaining blocks contain no retrievable text.
                break
            groups.append(blocks[start:best_end])
            start = best_end

        self._rebalance_short_tail(document, groups)
        return [group for group in groups if self._group_token_count(document, group) > 0]

    def _rebalance_short_tail(
        self,
        document: OpenStaxDocument,
        groups: list[list[TextBlock]],
    ) -> None:
        """Merge or redistribute a short final group without splitting blocks."""

        if len(groups) < 2:
            return
        tail_count = self._group_token_count(document, groups[-1])
        if tail_count >= self.strategy.min_tokens:
            return

        merged = groups[-2] + groups[-1]
        if self._group_token_count(document, merged) <= self.strategy.max_tokens:
            groups[-2:] = [merged]
            return

        previous = groups[-2]
        tail = groups[-1]
        while (
            len(previous) > 1
            and self._group_token_count(document, tail) < self.strategy.min_tokens
        ):
            candidate_previous = previous[:-1]
            candidate_tail = previous[-1:] + tail
            previous_count = self._group_token_count(document, candidate_previous)
            tail_count = self._group_token_count(document, candidate_tail)
            if previous_count > self.strategy.max_tokens or tail_count > self.strategy.max_tokens:
                break
            previous, tail = candidate_previous, candidate_tail
        groups[-2:] = [previous, tail]

    def _group_token_count(
        self,
        document: OpenStaxDocument,
        blocks: Sequence[TextBlock],
    ) -> int:
        if not blocks:
            return 0
        text = document.text[blocks[0].char_start : blocks[-1].char_end]
        return self.token_counter.count(text)

    def _build_chunk(
        self,
        document: OpenStaxDocument,
        blocks: list[TextBlock],
        chunk_index: int,
    ) -> Chunk:
        char_start = blocks[0].char_start
        char_end = blocks[-1].char_end
        text = document.text[char_start:char_end]
        token_count = self.token_counter.count(text)
        if not text.strip() or token_count == 0:
            raise ValueError("block group produced an empty chunk")

        chapter_id = blocks[0].chapter_id
        section_ids = self._ordered_unique(block.section_id or "" for block in blocks)
        section_titles = self._ordered_unique(block.section_title or "" for block in blocks)
        content_types = self._ordered_unique(block.content_type.value for block in blocks)
        block_ids = [block.block_id for block in blocks if block.block_id is not None]
        pages = [
            page
            for block in blocks
            for page in (block.page_start, block.page_end)
            if page is not None
        ]
        text_hash = "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()
        metadata = {
            "strategy": "block_greedy_nearest_target",
            "chunker_version": self.strategy.chunker_version,
            "tokenizer_name": self.token_counter.name,
            "target_tokens": str(self.strategy.target_tokens),
            "min_tokens": str(self.strategy.min_tokens),
            "max_tokens": str(self.strategy.max_tokens),
            "respect_section_boundaries": str(
                self.strategy.respect_section_boundaries
            ).lower(),
            "section_id": section_ids[0] if len(section_ids) == 1 else "",
            "section_ids": ",".join(section_ids),
            "section_title": section_titles[0] if len(section_titles) == 1 else "",
            "section_titles": " | ".join(section_titles),
            "content_types": ",".join(content_types),
            "source_block_ids": ",".join(block_ids),
            "block_count": str(len(blocks)),
            "page_start": str(min(pages)) if pages else "",
            "page_end": str(max(pages)) if pages else "",
            "short_chunk": str(token_count < self.strategy.min_tokens).lower(),
            "oversized_chunk": str(token_count > self.strategy.max_tokens).lower(),
            "text_hash": text_hash,
            "document_hash": document.document_hash,
            "parser_version": document.parser_version,
        }
        chunk_id = (
            f"{self._safe_id(document.document_id)}_"
            f"{self._safe_id(chapter_id)}_c{chunk_index:05d}"
        )
        return Chunk(
            chunk_id=chunk_id,
            document_id=document.document_id,
            chapter_id=chapter_id,
            text=text,
            source=document.source,
            char_start=char_start,
            char_end=char_end,
            token_count=token_count,
            metadata=metadata,
            embed_text=self._embed_text(text, document, blocks),
        )

    def _embed_text(
        self,
        text: str,
        document: OpenStaxDocument,
        blocks: Sequence[TextBlock],
    ) -> str | None:
        if not self.strategy.enrich_embed_text:
            return None
        chapter = next(
            chapter for chapter in document.chapters if chapter.chapter_id == blocks[0].chapter_id
        )
        section_ids = self._ordered_unique(block.section_id or "" for block in blocks)
        section_titles = self._ordered_unique(block.section_title or "" for block in blocks)
        context = f"From chapter {chapter.chapter_id} ({chapter.title})"
        if any(section_ids):
            context += f", section {', '.join(item for item in section_ids if item)}"
        if any(section_titles):
            context += f" ({' | '.join(item for item in section_titles if item)})"
        return f"{context}:\n\n{text}"

    def _validate_output(self, chunks: Sequence[Chunk]) -> None:
        ids = [chunk.chunk_id for chunk in chunks]
        if len(ids) != len(set(ids)):
            raise ValueError("chunk_id generation produced duplicates")
        if any(not chunk.text.strip() for chunk in chunks):
            raise ValueError("empty chunk detected")
        if self.strategy.reject_duplicate_text:
            hashes = [chunk.metadata["text_hash"] for chunk in chunks]
            if len(hashes) != len(set(hashes)):
                raise ValueError("exact duplicate chunk text detected")

    @staticmethod
    def _ordered_unique(values: Iterable[str]) -> list[str]:
        return list(dict.fromkeys(values))

    @staticmethod
    def _safe_id(value: str) -> str:
        safe = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip())
        return safe.strip("-") or "unknown"
