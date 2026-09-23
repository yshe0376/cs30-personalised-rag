"""Blocks whose text appears in more than one textbook of the same corpus.

College Physics for AP Courses 2e repeats most of College Physics 2e word for
word.  Retrieval, Gold mapping, and the Concept Check leakage gate need to know
which blocks are the same text, so the build reports them next to the corpus
they describe instead of each module re-deriving its own notion of a copy.
"""

from __future__ import annotations

import unicodedata
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from cs30.v2.contracts import ContentType, TextbookDocument
from cs30.v2.contracts.models import Identifier, V2Model
from cs30.v2.ids import canonical_json_bytes, sha256_text

DUPLICATE_NORMALIZER_VERSION = "dup-norm-v1"
# Shorter blocks (equation numbers, bare headings) repeat by coincidence.
MIN_DUPLICATE_CHARS = 40


def normalise_duplicate_text(text: str) -> str:
    """NFC, case-folded, with every whitespace run collapsed to one space."""

    return " ".join(unicodedata.normalize("NFC", text).casefold().split())


class DuplicateBlockMember(V2Model):
    textbook_id: Identifier
    document_id: Identifier
    block_id: Identifier
    chapter_id: Identifier
    content_type: ContentType


class DuplicateBlockGroup(V2Model):
    text_hash: Identifier
    members: tuple[DuplicateBlockMember, ...] = Field(min_length=2)

    @model_validator(mode="after")
    def validate_members(self) -> DuplicateBlockGroup:
        if len({member.textbook_id for member in self.members}) < 2:
            raise ValueError("a duplicate group must span at least two textbooks")
        keys = [(member.textbook_id, member.block_id) for member in self.members]
        if len(keys) != len(set(keys)):
            raise ValueError("a block may appear only once in a duplicate group")
        return self


class DuplicateBlockReport(V2Model):
    schema_version: Literal["2.0"] = "2.0"
    corpus_version: Identifier
    corpus_hash: Identifier
    normalizer_version: Identifier = DUPLICATE_NORMALIZER_VERSION
    min_chars: int = Field(default=MIN_DUPLICATE_CHARS, ge=1)
    groups: tuple[DuplicateBlockGroup, ...] = ()

    @model_validator(mode="after")
    def validate_groups(self) -> DuplicateBlockReport:
        hashes = [group.text_hash for group in self.groups]
        if hashes != sorted(set(hashes)):
            raise ValueError("duplicate groups must be unique and ordered by text_hash")
        return self


def find_cross_textbook_duplicates(
    documents: Sequence[TextbookDocument],
    *,
    corpus_version: str,
    corpus_hash: str,
    min_chars: int = MIN_DUPLICATE_CHARS,
) -> DuplicateBlockReport:
    """Group blocks whose normalised text occurs in two or more textbooks."""

    members_by_hash: dict[str, list[DuplicateBlockMember]] = defaultdict(list)
    for document in sorted(documents, key=lambda item: (item.textbook_id, item.document_id)):
        for block in document.blocks:
            text = normalise_duplicate_text(document.document_text(block))
            if len(text) < min_chars:
                continue
            members_by_hash[sha256_text(text)].append(
                DuplicateBlockMember(
                    textbook_id=document.textbook_id,
                    document_id=document.document_id,
                    block_id=block.block_id,
                    chapter_id=block.chapter_id,
                    content_type=block.content_type,
                )
            )
    groups = tuple(
        DuplicateBlockGroup(text_hash=text_hash, members=tuple(members))
        for text_hash, members in sorted(members_by_hash.items())
        if len({member.textbook_id for member in members}) >= 2
    )
    return DuplicateBlockReport(
        corpus_version=corpus_version,
        corpus_hash=corpus_hash,
        min_chars=min_chars,
        groups=groups,
    )


def write_duplicate_report(report: DuplicateBlockReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(report.model_dump(mode="json")))


def load_duplicate_report(path: Path) -> DuplicateBlockReport:
    return DuplicateBlockReport.model_validate_json(path.read_text(encoding="utf-8"))
