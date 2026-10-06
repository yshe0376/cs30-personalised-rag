"""Traceable fixture and production chunkers for the v2 corpus."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from cs30.v2.contracts import Chunk, ChunkSpan, ContentType, TextBlock, TextbookDocument
from cs30.v2.ids import chunk_config_hash, make_chunk_id, sha256_text, source_locator
from cs30.v2.tokenization import (
    CHUNK_TOKENIZER_NAME,
    CHUNK_TOKENIZER_REVISION,
    REGEX_TOKENIZER_NAME,
    TokenCounter,
    build_token_counter,
    is_pinned_revision,
)

V2_EVIDENCE_POLICY_ID = "v2-retrieval-evidence-v1"
V2_EVIDENCE_CONTENT_TYPES = (
    ContentType.BODY,
    ContentType.EXAMPLE,
    ContentType.FIGURE_CAPTION,
    ContentType.GLOSSARY,
    ContentType.TABLE,
    ContentType.EQUATION,
)


class V2BlockChunker:
    """Emit one traceable chunk per parser block.

    M1 intentionally does not introduce a new token-size policy.  This adapter
    gives the parser/Manifest seam a deterministic chunk implementation; the
    production M4 chunker can replace it through the same port.
    """

    version = "v2-block-v1"
    is_fixture = True

    def __init__(
        self,
        *,
        tokenizer_name: str = REGEX_TOKENIZER_NAME,
        tokenizer_revision: str | None = None,
        token_counter: TokenCounter | None = None,
    ) -> None:
        # The ruler is named in the config hash, so a corpus records which
        # tokenizer decided its chunk sizes. The revision joins the hash only
        # when set, so unpinned fixture rulers keep their existing hashes.
        self.tokenizer_name = tokenizer_name
        self.tokenizer_revision = tokenizer_revision
        self._token_counter = token_counter
        config: dict[str, str] = {
            "chunker_version": self.version,
            "tokenizer_name": tokenizer_name,
            "grouping": "one-block",
        }
        if tokenizer_revision is not None:
            config["tokenizer_revision"] = tokenizer_revision
        self._config_hash = chunk_config_hash(config)

    @classmethod
    def from_config(cls, config: Mapping[str, str]) -> V2BlockChunker:
        supported = {"tokenizer_name", "tokenizer_revision"}
        unknown = set(config) - supported
        if unknown:
            raise ValueError(f"unsupported v2 chunk configuration: {sorted(unknown)}")
        name = config.get("tokenizer_name", REGEX_TOKENIZER_NAME)
        revision = config.get("tokenizer_revision")
        # A Hugging Face ruler can change under the same name; only a commit
        # hash keeps the configured chunk sizes reproducible.
        if name != REGEX_TOKENIZER_NAME and not is_pinned_revision(revision):
            raise ValueError(
                f"chunk ruler {name!r} needs tokenizer_revision set to a full "
                f"40-character commit hash, got {revision!r}"
            )
        return cls(tokenizer_name=name, tokenizer_revision=revision)

    @property
    def token_counter(self) -> TokenCounter:
        """Load the configured ruler on first use, not when it is named."""

        if self._token_counter is None:
            self._token_counter = build_token_counter(
                self.tokenizer_name, revision=self.tokenizer_revision
            )
        return self._token_counter

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
            if self.tokenizer_revision is not None:
                metadata["tokenizer_revision"] = self.tokenizer_revision
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

    def _count_tokens(self, text: str) -> int:
        return self.token_counter.count(text)


@dataclass(frozen=True)
class V2ChunkingStrategy:
    """Frozen production policy for whole-block, structure-aware chunking."""

    tokenizer_name: str = CHUNK_TOKENIZER_NAME
    tokenizer_revision: str | None = CHUNK_TOKENIZER_REVISION
    target_tokens: int = 500
    min_tokens: int = 100
    max_tokens: int = 600
    respect_section_boundaries: bool = True
    enrich_embed_text: bool = False
    reject_duplicate_text: bool = False
    include_types: tuple[ContentType, ...] = V2_EVIDENCE_CONTENT_TYPES

    def __post_init__(self) -> None:
        if not self.tokenizer_name.strip():
            raise ValueError("tokenizer_name must not be empty")
        if self.min_tokens <= 0:
            raise ValueError("min_tokens must be positive")
        if self.target_tokens < self.min_tokens:
            raise ValueError("target_tokens must be at least min_tokens")
        if self.max_tokens < self.target_tokens:
            raise ValueError("max_tokens must be at least target_tokens")
        if not self.include_types:
            raise ValueError("include_types must contain at least one content type")
        if len(set(self.include_types)) != len(self.include_types):
            raise ValueError("include_types must not contain duplicates")

    @classmethod
    def from_config(cls, config: Mapping[str, str]) -> V2ChunkingStrategy:
        supported = {
            "tokenizer_name",
            "tokenizer_revision",
            "target_tokens",
            "min_tokens",
            "max_tokens",
            "respect_section_boundaries",
            "enrich_embed_text",
            "reject_duplicate_text",
            "include_types",
        }
        unknown = set(config) - supported
        if unknown:
            raise ValueError(f"unsupported v2 chunk configuration: {sorted(unknown)}")

        name = config.get("tokenizer_name", CHUNK_TOKENIZER_NAME)
        revision = config.get(
            "tokenizer_revision",
            CHUNK_TOKENIZER_REVISION if "tokenizer_name" not in config else None,
        )
        if name != REGEX_TOKENIZER_NAME and not is_pinned_revision(revision):
            raise ValueError(
                f"chunk ruler {name!r} needs tokenizer_revision set to a full "
                f"40-character commit hash, got {revision!r}"
            )

        include_types = V2_EVIDENCE_CONTENT_TYPES
        if "include_types" in config:
            raw_types = [item.strip() for item in config["include_types"].split(",")]
            if not all(raw_types):
                raise ValueError("include_types must be a comma-separated non-empty list")
            try:
                include_types = tuple(ContentType(item) for item in raw_types)
            except ValueError as exc:
                raise ValueError(f"unsupported include_types value: {exc}") from exc

        return cls(
            tokenizer_name=name,
            tokenizer_revision=revision,
            target_tokens=_integer(config, "target_tokens", 500),
            min_tokens=_integer(config, "min_tokens", 100),
            max_tokens=_integer(config, "max_tokens", 600),
            respect_section_boundaries=_boolean(config, "respect_section_boundaries", True),
            enrich_embed_text=_boolean(config, "enrich_embed_text", False),
            reject_duplicate_text=_boolean(config, "reject_duplicate_text", False),
            include_types=include_types,
        )

    def identity(self, *, chunker_version: str) -> dict[str, object]:
        """Return every artifact-affecting setting for the config hash."""

        identity: dict[str, object] = {
            "chunker_version": chunker_version,
            "evidence_policy_id": V2_EVIDENCE_POLICY_ID,
            "tokenizer_name": self.tokenizer_name,
            "target_tokens": self.target_tokens,
            "min_tokens": self.min_tokens,
            "max_tokens": self.max_tokens,
            "respect_section_boundaries": self.respect_section_boundaries,
            "enrich_embed_text": self.enrich_embed_text,
            "reject_duplicate_text": self.reject_duplicate_text,
            "include_types": [item.value for item in self.include_types],
            "grouping": "whole-block-nearest-target",
        }
        if self.tokenizer_revision is not None:
            identity["tokenizer_revision"] = self.tokenizer_revision
        return identity


class V2ProductionChunker:
    """Group whole parser blocks without crossing chapter or section boundaries."""

    version = "v2-structure-aware-v1"
    is_fixture = False

    def __init__(
        self,
        *,
        strategy: V2ChunkingStrategy | None = None,
        token_counter: TokenCounter | None = None,
    ) -> None:
        self.strategy = strategy or V2ChunkingStrategy()
        self.tokenizer_name = self.strategy.tokenizer_name
        self.tokenizer_revision = self.strategy.tokenizer_revision
        self._token_counter = token_counter
        self._config_hash = chunk_config_hash(self.strategy.identity(chunker_version=self.version))

    @classmethod
    def from_config(cls, config: Mapping[str, str]) -> V2ProductionChunker:
        return cls(strategy=V2ChunkingStrategy.from_config(config))

    @property
    def token_counter(self) -> TokenCounter:
        if self._token_counter is None:
            self._token_counter = build_token_counter(
                self.tokenizer_name, revision=self.tokenizer_revision
            )
        return self._token_counter

    @property
    def config_hash(self) -> str:
        return self._config_hash

    def chunk(self, document: TextbookDocument) -> list[Chunk]:
        chunks: list[Chunk] = []
        ordinal = 1
        for segment in self._segments(document.blocks):
            for block_group in self._partition_segment(document, segment):
                chunks.append(self._build_chunk(document, block_group, ordinal))
                ordinal += 1

        if not chunks:
            raise ValueError(f"document produced no retrievable chunks: {document.document_id}")
        self._validate_output(chunks)
        return chunks

    def _segments(self, blocks: Sequence[TextBlock]) -> list[list[TextBlock]]:
        included_types = set(self.strategy.include_types)
        segments: list[list[TextBlock]] = []
        current: list[TextBlock] = []
        current_key: tuple[str, str | None] | None = None
        for block in blocks:
            # An excluded block is a hard boundary. This prevents its text from
            # leaking through the document slice between two eligible blocks.
            if block.content_type not in included_types:
                if current:
                    segments.append(current)
                    current = []
                current_key = None
                continue
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
        document: TextbookDocument,
        blocks: list[TextBlock],
    ) -> list[list[TextBlock]]:
        groups: list[list[TextBlock]] = []
        start = 0
        while start < len(blocks):
            best_end: int | None = None
            best_distance: int | None = None
            for end in range(start + 1, len(blocks) + 1):
                count = self._group_token_count(document, blocks[start:end])
                if count > self.strategy.max_tokens:
                    if best_end is None:
                        # Preserve an indivisible parser block and mark its
                        # resulting chunk as oversized in metadata.
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
                break
            groups.append(blocks[start:best_end])
            start = best_end

        self._rebalance_short_tail(document, groups)
        return [group for group in groups if self._group_token_count(document, group) > 0]

    def _rebalance_short_tail(
        self,
        document: TextbookDocument,
        groups: list[list[TextBlock]],
    ) -> None:
        if len(groups) < 2:
            return
        if self._group_token_count(document, groups[-1]) >= self.strategy.min_tokens:
            return

        merged = groups[-2] + groups[-1]
        if self._group_token_count(document, merged) <= self.strategy.max_tokens:
            groups[-2:] = [merged]
            return

        previous = groups[-2]
        tail = groups[-1]
        while (
            len(previous) > 1 and self._group_token_count(document, tail) < self.strategy.min_tokens
        ):
            candidate_previous = previous[:-1]
            candidate_tail = previous[-1:] + tail
            if (
                self._group_token_count(document, candidate_previous) > self.strategy.max_tokens
                or self._group_token_count(document, candidate_tail) > self.strategy.max_tokens
            ):
                break
            previous, tail = candidate_previous, candidate_tail
        groups[-2:] = [previous, tail]

    def _group_token_count(
        self,
        document: TextbookDocument,
        blocks: Sequence[TextBlock],
    ) -> int:
        if not blocks:
            return 0
        return self.token_counter.count(document.text[blocks[0].char_start : blocks[-1].char_end])

    def _build_chunk(
        self,
        document: TextbookDocument,
        blocks: list[TextBlock],
        ordinal: int,
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
        section_id = section_ids[0] if len(section_ids) == 1 and section_ids[0] else None
        section_title = (
            section_titles[0] if len(section_titles) == 1 and section_titles[0] else None
        )
        page_start, page_end, page_or_location = self._location(blocks)
        spans = tuple(
            ChunkSpan(
                block_id=block.block_id,
                chapter_id=block.chapter_id,
                char_start=block.char_start,
                char_end=block.char_end,
                content_type=block.content_type,
            )
            for block in blocks
        )
        content_types = tuple(dict.fromkeys(span.content_type for span in spans))
        parent_blocks = self._parent_blocks(document, blocks)
        asset_refs = self._ordered_unique(block.asset_ref for block in blocks if block.asset_ref)
        embed_text = self._embed_text(text, document, blocks)
        embedding_input = embed_text or text
        metadata = {
            "strategy": "whole-block-nearest-target",
            "chunker_version": self.version,
            "evidence_policy_id": V2_EVIDENCE_POLICY_ID,
            "tokenizer_name": self.tokenizer_name,
            "target_tokens": str(self.strategy.target_tokens),
            "min_tokens": str(self.strategy.min_tokens),
            "max_tokens": str(self.strategy.max_tokens),
            "respect_section_boundaries": str(self.strategy.respect_section_boundaries).lower(),
            "enrich_embed_text": str(self.strategy.enrich_embed_text).lower(),
            "reject_duplicate_text": str(self.strategy.reject_duplicate_text).lower(),
            "include_types": ",".join(item.value for item in self.strategy.include_types),
            "source_block_ids": ",".join(block.block_id for block in blocks),
            "block_count": str(len(blocks)),
            "parent_scope": "section" if section_id else "chapter",
            "parent_char_start": str(parent_blocks[0].char_start),
            "parent_char_end": str(parent_blocks[-1].char_end),
            "parent_source_block_ids": ",".join(block.block_id for block in parent_blocks),
            "embedding_input_token_count": str(self.token_counter.count(embedding_input)),
            "short_chunk": str(token_count < self.strategy.min_tokens).lower(),
            "oversized_chunk": str(token_count > self.strategy.max_tokens).lower(),
            "text_hash": sha256_text(text),
            "document_hash": document.document_hash,
            "parser_version": document.parser_version,
        }
        if self.tokenizer_revision is not None:
            metadata["tokenizer_revision"] = self.tokenizer_revision
        if asset_refs:
            metadata["asset_refs"] = ",".join(asset_refs)

        return Chunk(
            chunk_id=make_chunk_id(
                document.document_id,
                chapter_id,
                self.config_hash,
                ordinal,
            ),
            provider=document.provider,
            textbook_id=document.textbook_id,
            document_id=document.document_id,
            chapter_id=chapter_id,
            source_name=document.source_name,
            page_start=page_start,
            page_end=page_end,
            page_or_location=page_or_location,
            section_id=section_id,
            section_title=section_title,
            source_locator=source_locator(
                source_name=document.source_name,
                textbook_id=document.textbook_id,
                chapter_id=chapter_id,
                page_or_location=page_or_location,
                char_start=char_start,
                char_end=char_end,
            ),
            text=text,
            char_start=char_start,
            char_end=char_end,
            content_types=content_types,
            spans=spans,
            chunker_version=self.version,
            chunk_config_hash=self.config_hash,
            token_count=token_count,
            embed_text=embed_text,
            metadata=metadata,
        )

    def _location(self, blocks: Sequence[TextBlock]) -> tuple[int | None, int | None, str]:
        if all(block.page_start is not None and block.page_end is not None for block in blocks):
            page_start = min(block.page_start for block in blocks if block.page_start)
            page_end = max(block.page_end for block in blocks if block.page_end)
            return (
                page_start,
                page_end,
                (f"p{page_start}" if page_start == page_end else f"p{page_start}-{page_end}"),
            )

        locations = self._ordered_unique(
            block.page_or_location for block in blocks if block.page_or_location
        )
        if len(locations) == 1:
            return None, None, locations[0]
        return (
            None,
            None,
            f"chapter-{blocks[0].chapter_id}/blocks-{blocks[0].block_id}-{blocks[-1].block_id}",
        )

    def _embed_text(
        self,
        text: str,
        document: TextbookDocument,
        blocks: Sequence[TextBlock],
    ) -> str | None:
        if not self.strategy.enrich_embed_text:
            return None
        chapter = next(
            chapter for chapter in document.chapters if chapter.chapter_id == blocks[0].chapter_id
        )
        context = f"From {document.title}, chapter {chapter.chapter_id} ({chapter.title})"
        section_titles = self._ordered_unique(
            block.section_title for block in blocks if block.section_title
        )
        if section_titles:
            context += f", section {' | '.join(section_titles)}"
        return f"{context}:\n\n{text}"

    def _parent_blocks(
        self,
        document: TextbookDocument,
        blocks: Sequence[TextBlock],
    ) -> list[TextBlock]:
        chapter_id = blocks[0].chapter_id
        section_ids = self._ordered_unique(block.section_id or "" for block in blocks)
        if len(section_ids) == 1 and section_ids[0]:
            return [
                block
                for block in document.blocks
                if block.chapter_id == chapter_id and block.section_id == section_ids[0]
            ]
        return [block for block in document.blocks if block.chapter_id == chapter_id]

    def _validate_output(self, chunks: Sequence[Chunk]) -> None:
        ids = [chunk.chunk_id for chunk in chunks]
        if len(ids) != len(set(ids)):
            raise ValueError("chunk_id generation produced duplicates")
        if self.strategy.reject_duplicate_text:
            hashes = [chunk.metadata["text_hash"] for chunk in chunks]
            if len(hashes) != len(set(hashes)):
                raise ValueError("exact duplicate chunk text detected")

    @staticmethod
    def _ordered_unique(values: Iterable[str]) -> list[str]:
        return list(dict.fromkeys(values))


def _integer(config: Mapping[str, str], key: str, default: int) -> int:
    try:
        return int(config.get(key, str(default)))
    except ValueError as exc:
        raise ValueError(f"{key} must be an integer") from exc


def _boolean(config: Mapping[str, str], key: str, default: bool) -> bool:
    value = config.get(key, str(default)).strip().lower()
    if value == "true":
        return True
    if value == "false":
        return False
    raise ValueError(f"{key} must be true or false")
