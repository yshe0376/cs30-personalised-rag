"""Mapping M2's OpenStax parser output (schema 1.0) to the v2 document contract."""

from __future__ import annotations

import json
import os
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from cs30.v2.catalog import get_textbook_spec
from cs30.v2.contracts import ContentType
from cs30.v2.errors import ContractError, InputError
from cs30.v2.ingest import (
    ADAPTER_VERSION,
    OpenStaxPdfParser,
    build_parser_registry,
    openstax_payload_to_document,
)
from cs30.v2.ports import TextbookInput

TEXTBOOK_ID = "openstax_college_physics_2e"
PDF_SHA256 = "a052d9fae2a90e135a74d70c001a78bb49b83280be58191e108d5de577699bb6"
BODY = "Acceleration is the rate at which velocity changes with time.\n\n"
EQUATION = "a = dv/dt"


def make_payload(**overrides: Any) -> dict[str, Any]:
    text = BODY + EQUATION
    payload = {
        "schema_version": "1.0",
        "document_id": "openstax-cp2e-a052d9fae2a90e13",
        "title": "College Physics 2e",
        "version": "2e",
        "source": "https://openstax.org/details/books/college-physics-2e",
        "document_hash": PDF_SHA256,
        "parser_version": "1.3.2",
        "text": text,
        "chapters": [
            {
                "chapter_id": "1",
                "title": "Kinematics",
                "char_start": 0,
                "char_end": len(text),
                "page_start": 25,
                "page_end": 26,
            }
        ],
        "blocks": [
            {
                "block_id": "openstax-cp2e-a052d9fae2a90e13_ch01_p0025_b000",
                "chapter_id": "1",
                "section_id": "1.2",
                "section_title": "Acceleration",
                "content_type": "body",
                "char_start": 0,
                "char_end": len(BODY),
                "page_start": 25,
                "page_end": 25,
                "metadata": {"record_type": "paragraph", "printed_page": "7"},
            },
            {
                "block_id": "openstax-cp2e-a052d9fae2a90e13_ch01_p0026_b001",
                "chapter_id": "1",
                "section_id": "1.2",
                "section_title": "Acceleration",
                "content_type": "equation",
                "char_start": len(BODY),
                "char_end": len(text),
                "page_start": 26,
                "page_end": 26,
                "metadata": {"record_type": "formula", "formula_alt_text": "a equals dv dt"},
            },
        ],
    }
    payload.update(overrides)
    return payload


def make_input(
    textbook_id: str = TEXTBOOK_ID, chapters: tuple[str, ...] = ("1",)
) -> TextbookInput:
    spec = get_textbook_spec(textbook_id)
    return TextbookInput(
        textbook_id=textbook_id,
        source_path=Path(f"{textbook_id}.pdf"),
        source_name=spec.source_name,
        source_version=spec.source_version,
        source_uri=spec.source_uri,
        selected_chapters=chapters,
        expected_source_sha256=spec.expected_source_sha256,
    )


def convert(payload: dict[str, Any] | None = None) -> Any:
    return openstax_payload_to_document(
        payload if payload is not None else make_payload(),
        spec=get_textbook_spec(TEXTBOOK_ID),
        input=make_input(),
    )


def test_m2_document_hash_becomes_the_v2_raw_source_hash() -> None:
    document = convert()

    assert document.raw_source_sha256 == "sha256:" + PDF_SHA256
    # The v2 document hash covers the parsed content, not the PDF bytes.
    assert document.document_hash != document.raw_source_sha256
    assert document.document_id.startswith(TEXTBOOK_ID + "__")
    assert document.parser_version == f"openstax-1.3.2+adapter-{ADAPTER_VERSION}"
    assert document.metadata["m2_document_id"] == "openstax-cp2e-a052d9fae2a90e13"


def test_identity_comes_from_the_catalogue_not_the_parser_payload() -> None:
    spec = get_textbook_spec(TEXTBOOK_ID)
    document = convert()

    assert document.provider == spec.provider
    assert document.source_name == spec.source_name
    assert document.license == spec.license
    assert document.source_version == "2e"
    assert document.selected_chapters == ("1",)


def test_block_pages_survive_and_drive_the_location() -> None:
    document = convert()

    first, second = document.blocks
    assert (first.page_start, first.page_end, first.page_or_location) == (25, 25, "p25")
    assert second.content_type is ContentType.EQUATION
    assert second.page_or_location == "p26"
    assert first.metadata["printed_page"] == "7"
    assert document.document_text(second) == EQUATION


def test_the_same_payload_always_produces_the_same_identity() -> None:
    assert convert().document_id == convert().document_id


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"schema_version": "2.0"}, "UNSUPPORTED_PARSER_SCHEMA"),
        ({"document_hash": "not-a-hash"}, "HASH_MISMATCH"),
    ],
)
def test_unusable_payloads_are_rejected(overrides: dict[str, Any], code: str) -> None:
    with pytest.raises(ContractError) as exc_info:
        convert(make_payload(**overrides))

    assert exc_info.value.code == code


def test_a_chapter_selection_mismatch_is_rejected() -> None:
    payload = make_payload()
    payload["chapters"][0]["chapter_id"] = "2"
    payload["blocks"][0]["chapter_id"] = "2"
    payload["blocks"][1]["chapter_id"] = "2"

    with pytest.raises(ContractError) as exc_info:
        convert(payload)

    assert exc_info.value.code == "CHAPTER_SELECTION_MISMATCH"


def test_a_non_pdf_source_is_an_input_error(tmp_path: Path) -> None:
    parser = OpenStaxPdfParser(get_textbook_spec(TEXTBOOK_ID))
    source = tmp_path / "book.json"
    source.write_text("{}", encoding="utf-8")

    with pytest.raises(InputError) as exc_info:
        parser.parse(
            TextbookInput(
                textbook_id=TEXTBOOK_ID,
                source_path=source,
                source_name=get_textbook_spec(TEXTBOOK_ID).source_name,
                source_version="2e",
            )
        )

    assert exc_info.value.code == "UNSUPPORTED_SOURCE_FORMAT"


def test_only_textbooks_with_a_real_parser_are_registered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from cs30.v2 import catalog

    pending = "ck12_pending_book"
    spec = get_textbook_spec("openstax_physics")
    monkeypatch.setattr(
        catalog, "REQUIRED_TEXTBOOK_IDS", (*catalog.REQUIRED_TEXTBOOK_IDS, pending)
    )
    monkeypatch.setitem(
        catalog.TEXTBOOK_CATALOG,
        pending,
        replace(
            spec,
            textbook_id=pending,
            provider="ck12",
            source_name=pending,
            parser_name="ck12",
        ),
    )

    registry = build_parser_registry(("openstax_physics", pending))

    assert isinstance(registry.parser_for("openstax_physics"), OpenStaxPdfParser)
    # CK-12 has no parser yet, so the pipeline reports PARSER_NOT_REGISTERED.
    with pytest.raises(KeyError):
        registry.parser_for(pending)


@pytest.mark.skipif(
    not os.environ.get("CS30_M2_OPENSTAX_OUTPUT"),
    reason="set CS30_M2_OPENSTAX_OUTPUT to M2's parser output directory",
)
def test_m2_delivered_output_converts_and_matches_its_catalogue_pin() -> None:
    root = Path(os.environ["CS30_M2_OPENSTAX_OUTPUT"])
    folders = {
        "college_output": "openstax_college_physics_2e",
        "physics_output": "openstax_physics",
        "ap_output": "openstax_college_physics_ap_2e",
    }
    for folder, textbook_id in folders.items():
        payload = json.loads(
            (root / folder / "openstax_document.json").read_text(encoding="utf-8")
        )
        spec = get_textbook_spec(textbook_id)
        document = openstax_payload_to_document(
            payload, spec=spec, input=make_input(textbook_id, spec.selected_chapters)
        )
        assert document.raw_source_sha256 == spec.expected_source_sha256
        assert document.selected_chapters == spec.selected_chapters
