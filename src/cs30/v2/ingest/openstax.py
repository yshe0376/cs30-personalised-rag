"""Adapt M2's OpenStax PDF parser (schema 1.0 output) to the v2 document contract.

M2's parser keeps its v1-shaped output unchanged.  This adapter is the single
place that maps it to :class:`~cs30.v2.contracts.TextbookDocument`:

* M2's ``document_hash`` is the SHA-256 of the PDF, so it becomes the v2
  ``raw_source_sha256``; the v2 ``document_hash`` is recomputed from the parsed
  content, and the v2 ``document_id`` from both.
* Block page numbers are physical PDF pages; ``page_or_location`` is derived
  from them by the contract, and printed page labels stay in block metadata.
* The provider, source name, source URI, version, licence, and chapter
  selection come from the catalogue, so the output can be checked against it.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from importlib import metadata as importlib_metadata
from types import ModuleType
from typing import Any, ClassVar

from cs30.v2.catalog import TextbookSpec, get_textbook_spec
from cs30.v2.contracts import TextBlock, TextbookChapter, TextbookDocument
from cs30.v2.errors import ContractError, InputError, ParseError
from cs30.v2.ids import canonical_document_hash, make_document_id
from cs30.v2.pipeline import MappingParserRegistry
from cs30.v2.ports import DocumentParser, TextbookInput

# Bump when the mapping below changes; it is part of the v2 parser_version and
# therefore of every document and chunk ID.
ADAPTER_VERSION = "1"
SUPPORTED_SCHEMA_VERSION = "1.0"

# M2's own document-ID prefixes, so block IDs match M2's delivered outputs and a
# re-parse can be compared with them byte for byte.
_M2_DOCUMENT_PREFIXES = {
    "openstax_college_physics_2e": "openstax-cp2e",
    "openstax_physics": "openstax-physics",
    "openstax_college_physics_ap_2e": "openstax-cpap2e",
}
# The download date is only written to M2's metadata.json, which this adapter
# never produces, so a constant keeps parsing independent of the calendar.
_UNRECORDED_DOWNLOAD_DATE = "unrecorded"
_PARSE_LIBRARIES = ("PyMuPDF", "pdfplumber", "pdfminer.six")
_SHA256_HEX = re.compile(r"[0-9a-f]{64}")


def _library_versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    for name in _PARSE_LIBRARIES:
        try:
            versions[name] = importlib_metadata.version(name)
        except importlib_metadata.PackageNotFoundError:
            versions[name] = "not-installed"
    return versions


def openstax_payload_to_document(
    payload: Mapping[str, Any],
    *,
    spec: TextbookSpec,
    input: TextbookInput,
    library_versions: Mapping[str, str] | None = None,
    known_issue_count: int | None = None,
) -> TextbookDocument:
    """Convert one M2 schema 1.0 payload into a validated v2 document."""

    schema_version = payload.get("schema_version")
    if schema_version != SUPPORTED_SCHEMA_VERSION:
        raise ContractError(
            f"unsupported OpenStax parser schema {schema_version!r}; "
            f"expected {SUPPORTED_SCHEMA_VERSION}",
            code="UNSUPPORTED_PARSER_SCHEMA",
        )
    pdf_sha256 = str(payload["document_hash"])
    if not _SHA256_HEX.fullmatch(pdf_sha256):
        raise ContractError(
            "M2 document_hash must be the PDF's lowercase hex SHA-256",
            code="HASH_MISMATCH",
        )

    chapters = tuple(TextbookChapter.model_validate(chapter) for chapter in payload["chapters"])
    selected = tuple(chapter.chapter_id for chapter in chapters)
    expected = tuple(input.selected_chapters or spec.selected_chapters)
    if expected and selected != expected:
        raise ContractError(
            f"parsed chapters {list(selected)} differ from the selection {list(expected)}",
            code="CHAPTER_SELECTION_MISMATCH",
        )
    blocks = tuple(
        TextBlock.model_validate(
            {
                "block_id": block["block_id"],
                "chapter_id": block["chapter_id"],
                "section_id": block["section_id"],
                "section_title": block["section_title"],
                "content_type": block["content_type"],
                "char_start": block["char_start"],
                "char_end": block["char_end"],
                "page_start": block["page_start"],
                "page_end": block["page_end"],
                "metadata": block["metadata"],
            }
        )
        for block in payload["blocks"]
    )

    m2_parser_version = str(payload["parser_version"])
    parser_version = f"openstax-{m2_parser_version}+adapter-{ADAPTER_VERSION}"
    raw_source_sha256 = "sha256:" + pdf_sha256
    content = {
        "provider": spec.provider,
        "textbook_id": input.textbook_id,
        "source_version": str(payload["version"]),
        "parser_version": parser_version,
        "selected_chapters": list(selected),
        "text": payload["text"],
        "chapters": [chapter.model_dump(mode="json") for chapter in chapters],
        "blocks": [block.model_dump(mode="json") for block in blocks],
    }
    document_hash = canonical_document_hash(content)
    metadata = {
        "m2_schema_version": str(schema_version),
        "m2_parser_version": m2_parser_version,
        "m2_document_id": str(payload["document_id"]),
        "adapter_version": ADAPTER_VERSION,
    }
    if known_issue_count is not None:
        metadata["known_issue_count"] = str(known_issue_count)
    for name, version in (library_versions or {}).items():
        metadata[f"library.{name}"] = version

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
        title=str(payload["title"]),
        raw_source_sha256=raw_source_sha256,
        document_hash=document_hash,
        parser_version=parser_version,
        source_name=input.source_name,
        source_uri=input.source_uri or spec.source_uri,
        source_version=str(payload["version"]),
        license=spec.license,
        selected_chapters=selected,
        text=payload["text"],
        chapters=chapters,
        blocks=blocks,
        cleaning_version=f"openstax-parser-{m2_parser_version}",
        metadata=metadata,
    )


def _load_m2_parser() -> ModuleType:
    try:
        from cs30.v2.ingest import openstax_parser
    except (ImportError, SystemExit) as exc:
        # M2's module raises SystemExit when PyMuPDF or pdfplumber is missing.
        raise ParseError(
            'the OpenStax PDF parser needs pip install -e ".[parse]"',
            code="PARSER_DEPENDENCY_MISSING",
        ) from exc
    return openstax_parser


@dataclass(frozen=True)
class OpenStaxPdfParser:
    """v2 ``DocumentParser`` that runs M2's parser on a pinned OpenStax PDF."""

    spec: TextbookSpec
    is_fixture: ClassVar[bool] = False

    def parse(self, input: TextbookInput) -> TextbookDocument:
        if input.source_path.suffix.lower() != ".pdf":
            raise InputError(
                f"OpenStax sources must be PDF files: {input.source_path.name}",
                code="UNSUPPORTED_SOURCE_FORMAT",
            )
        chapters = tuple(input.selected_chapters or self.spec.selected_chapters)
        if not chapters:
            raise InputError(
                f"no chapter selection for {input.textbook_id}",
                code="CHAPTERS_REQUIRED",
            )
        parser = _load_m2_parser()
        pdf_sha256 = parser.sha256_file(input.source_path)
        prefix = _M2_DOCUMENT_PREFIXES.get(
            input.textbook_id, "openstax-" + input.textbook_id.replace("_", "-")
        )
        parsed = parser.parse_openstax(
            pdf_path=input.source_path,
            selected_chapters=list(chapters),
            source_url=self.spec.source_uri,
            download_date=_UNRECORDED_DOWNLOAD_DATE,
            title=self.spec.title,
            edition=self.spec.source_version,
            document_id=f"{prefix}-{pdf_sha256[:16]}",
        )
        payload = parser.build_contract_payload(parsed)
        problems = parser.validate_contract_payload(payload)
        if problems:
            raise ContractError(
                f"M2 parser output failed its own contract checks: {problems[:3]}",
                code="PARSER_OUTPUT_INVALID",
            )
        return openstax_payload_to_document(
            payload,
            spec=self.spec,
            input=input,
            library_versions=_library_versions(),
            known_issue_count=len(parsed.known_issues),
        )


def build_parser_registry(textbook_ids: Sequence[str]) -> MappingParserRegistry:
    """Register the real parser for each catalogue textbook that has one.

    A textbook whose ``parser_name`` has no implementation yet (CK-12, for
    now) is left out, so the pipeline reports ``PARSER_NOT_REGISTERED``.
    """

    parsers: dict[str, DocumentParser] = {}
    for textbook_id in textbook_ids:
        spec = get_textbook_spec(textbook_id)
        if spec.parser_name == "openstax":
            parsers[textbook_id] = OpenStaxPdfParser(spec)
    return MappingParserRegistry(parsers)
