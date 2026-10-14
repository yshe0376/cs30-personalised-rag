"""Adapt M2's pinned CK-12 parser output to the v2 document contract.

The CK-12 release keeps the legacy filename ``openstax_document.json`` for
compatibility, but it has its own parser and metadata. This adapter consumes
the parsed JSON only; CK-12 PDF parsing is not vendored here.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, ClassVar

from cs30.v2.catalog import TextbookSpec
from cs30.v2.contracts import ContentType, TextBlock, TextbookChapter, TextbookDocument
from cs30.v2.errors import ContractError, InputError, ParseError
from cs30.v2.ids import canonical_document_hash, make_document_id
from cs30.v2.ports import TextbookInput

ADAPTER_VERSION = "1"
SUPPORTED_SCHEMA_VERSION = "1.0"
_SHA256_HEX = re.compile(r"[0-9a-f]{64}")


def ck12_payload_to_document(
    payload: Mapping[str, Any],
    *,
    spec: TextbookSpec,
    input: TextbookInput,
) -> TextbookDocument:
    """Convert M2's CK-12 schema 1.0 payload into a validated v2 document."""

    schema_version = payload.get("schema_version")
    if schema_version != SUPPORTED_SCHEMA_VERSION:
        raise ContractError(
            f"unsupported CK-12 parser schema {schema_version!r}; "
            f"expected {SUPPORTED_SCHEMA_VERSION}",
            code="UNSUPPORTED_PARSER_SCHEMA",
        )

    source_sha256 = str(payload.get("document_hash", ""))
    if not _SHA256_HEX.fullmatch(source_sha256):
        raise ContractError(
            "CK-12 document_hash must be the source PDF's lowercase hex SHA-256",
            code="HASH_MISMATCH",
        )
    expected_source_sha256 = (spec.expected_source_sha256 or "").removeprefix("sha256:")
    if expected_source_sha256 and source_sha256 != expected_source_sha256:
        raise ContractError(
            "CK-12 parsed document names a different source PDF than the catalogue pin",
            code="SOURCE_HASH_MISMATCH",
        )

    source_version = str(payload.get("version", ""))
    if source_version != spec.source_version:
        raise ContractError(
            f"CK-12 source version {source_version!r} differs from the catalogue pin "
            f"{spec.source_version!r}",
            code="ASSET_VERSION_MISMATCH",
        )
    title = str(payload.get("title", ""))
    if title != spec.title:
        raise ContractError(
            f"CK-12 title {title!r} differs from the catalogue title {spec.title!r}",
            code="ASSET_VERSION_MISMATCH",
        )

    chapters = tuple(
        TextbookChapter.model_validate(chapter) for chapter in payload["chapters"]
    )
    selected = tuple(chapter.chapter_id for chapter in chapters)
    expected_chapters = tuple(input.selected_chapters or spec.selected_chapters)
    if expected_chapters and selected != expected_chapters:
        raise ContractError(
            f"parsed chapters {list(selected)} differ from the selection "
            f"{list(expected_chapters)}",
            code="CHAPTER_SELECTION_MISMATCH",
        )

    m2_document_id = str(payload.get("document_id", ""))
    raw_blocks = payload["blocks"]
    if not m2_document_id or any(
        not str(block.get("block_id", "")).startswith(m2_document_id + "_")
        for block in raw_blocks
    ):
        raise ContractError(
            "CK-12 block IDs must carry the parser document ID",
            code="PARSER_OUTPUT_INVALID",
        )

    blocks: list[TextBlock] = []
    for block in raw_blocks:
        metadata = {str(key): str(value) for key, value in block.get("metadata", {}).items()}
        content_type = str(block["content_type"])
        # M2 v1.1 labels section summaries by role while keeping their schema
        # content_type as body. Remap them so the v2 evidence policy excludes
        # summary material from retrieval chunks.
        if metadata.get("ck12_role") == "summary" and content_type == ContentType.BODY.value:
            content_type = ContentType.SUMMARY.value
        blocks.append(
            TextBlock.model_validate(
                {
                    "block_id": block["block_id"],
                    "chapter_id": block["chapter_id"],
                    "section_id": block["section_id"],
                    "section_title": block["section_title"],
                    "content_type": content_type,
                    "char_start": block["char_start"],
                    "char_end": block["char_end"],
                    "page_start": block["page_start"],
                    "page_end": block["page_end"],
                    "metadata": metadata,
                }
            )
        )

    m2_parser_version = str(payload.get("parser_version", ""))
    parser_version = f"{m2_parser_version}+adapter-{ADAPTER_VERSION}"
    raw_source_sha256 = "sha256:" + source_sha256
    text = str(payload["text"])
    content = {
        "provider": spec.provider,
        "textbook_id": input.textbook_id,
        "source_version": source_version,
        "parser_version": parser_version,
        "selected_chapters": list(selected),
        "text": text,
        "chapters": [chapter.model_dump(mode="json") for chapter in chapters],
        "blocks": [block.model_dump(mode="json") for block in blocks],
    }
    document_hash = canonical_document_hash(content)
    metadata = {
        "m2_schema_version": str(schema_version),
        "m2_parser_version": m2_parser_version,
        "m2_document_id": m2_document_id,
        "adapter_version": ADAPTER_VERSION,
        "source_qa_status": "manual_review_required",
    }

    return TextbookDocument(
        provider=spec.provider,
        textbook_id=input.textbook_id,
        document_id=make_document_id(
            textbook_id=input.textbook_id,
            raw_source_sha256=raw_source_sha256,
            document_hash=document_hash,
            parser_version=parser_version,
            selected_chapters=selected,
        ),
        title=title,
        raw_source_sha256=raw_source_sha256,
        document_hash=document_hash,
        parser_version=parser_version,
        source_name=input.source_name,
        source_uri=input.source_uri or spec.source_uri,
        source_version=source_version,
        license=spec.license,
        selected_chapters=selected,
        text=text,
        chapters=chapters,
        blocks=tuple(blocks),
        cleaning_version=parser_version,
        metadata=metadata,
    )


@dataclass(frozen=True)
class CK12ParsedParser:
    """Read the pinned CK-12 parse delivered by M2's release."""

    spec: TextbookSpec
    is_fixture: ClassVar[bool] = False
    requires_source_approval: ClassVar[bool] = True

    def parse(self, input: TextbookInput) -> TextbookDocument:
        if input.source_path.suffix.lower() != ".json":
            raise InputError(
                f"CK-12's delivered parse must be a JSON file: {input.source_path.name}",
                code="UNSUPPORTED_SOURCE_FORMAT",
            )
        try:
            payload = json.loads(input.source_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ParseError(
                f"CK-12's delivered parse is not valid JSON: {exc}",
                code="PARSER_OUTPUT_INVALID",
            ) from exc
        if not isinstance(payload, dict):
            raise ContractError(
                "CK-12's delivered parse must be a JSON object",
                code="PARSER_OUTPUT_INVALID",
            )
        return ck12_payload_to_document(payload, spec=self.spec, input=input)


@dataclass(frozen=True)
class CK12RawParser:
    """Fail clearly when a raw CK-12 PDF is supplied without its parser."""

    spec: TextbookSpec
    is_fixture: ClassVar[bool] = False
    requires_source_approval: ClassVar[bool] = True

    def parse(self, input: TextbookInput) -> TextbookDocument:
        raise InputError(
            "raw CK-12 parsing is not vendored; use the pinned parsed source format",
            code="UNSUPPORTED_SOURCE_FORMAT",
        )
