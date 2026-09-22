"""Contract-first tests for the isolated v2 M1 boundary."""

from __future__ import annotations

import pytest

from cs30.v2.catalog import (
    REQUIRED_PROVIDERS,
    REQUIRED_TEXTBOOK_IDS,
    get_textbook_spec,
    missing_required_providers,
)
from cs30.v2.chunking import V2BlockChunker
from cs30.v2.contracts import (
    Chunk,
    ChunkSpan,
    ContentType,
    EvidenceProvenance,
    EvidenceSpan,
    EvidenceSpanBinding,
    IndexArtifact,
    RetrievalMode,
    SpanResolutionMethod,
    SpanResolutionStatus,
    TextBlock,
    TextbookChapter,
    TextbookDocument,
)
from cs30.v2.fixture import TextFixtureParser
from cs30.v2.ids import (
    canonical_document_hash,
    chunk_config_hash,
    make_chunk_id,
    make_document_id,
    sha256_text,
    source_locator,
)
from cs30.v2.ports import TextbookInput


def make_document(
    textbook_id: str = REQUIRED_TEXTBOOK_IDS[0],
    *,
    provider: str = "openstax",
    parser_version: str = "fixture-parser-2.0",
    text: str = "A force changes motion.\n[[FORMULA:f=ma]]\n[[IMAGE:fig-1]]",
) -> TextbookDocument:
    formula_start = text.index("[[FORMULA:")
    image_start = text.index("[[IMAGE:")
    return TextbookDocument(
        provider=provider,
        textbook_id=textbook_id,
        document_id=make_document_id(
            textbook_id=textbook_id,
            raw_source_sha256=sha256_text(text),
            document_hash=sha256_text(text + parser_version),
            parser_version=parser_version,
            selected_chapters=("1",),
        ),
        title=f"{textbook_id} fixture",
        raw_source_sha256=sha256_text(text),
        document_hash=sha256_text(text + parser_version),
        parser_version=parser_version,
        source_name=get_textbook_spec(textbook_id).source_name,
        source_uri=f"fixture://{textbook_id}",
        source_version="fixture-2.0",
        license="CC BY 4.0",
        selected_chapters=("1",),
        text=text,
        chapters=(
            TextbookChapter(
                chapter_id="1",
                title="Motion",
                char_start=0,
                char_end=len(text),
            ),
        ),
        blocks=(
            TextBlock(
                block_id="body-1",
                chapter_id="1",
                section_id="1.1",
                section_title="Force",
                content_type=ContentType.BODY,
                char_start=0,
                char_end=formula_start,
                page_or_location="chapter-1/section-1.1",
            ),
            TextBlock(
                block_id="formula-1",
                chapter_id="1",
                section_id="1.1",
                section_title="Force",
                content_type=ContentType.EQUATION,
                char_start=formula_start,
                char_end=image_start,
                page_or_location="chapter-1/section-1.1",
                asset_ref="formula:f=ma",
            ),
            TextBlock(
                block_id="image-1",
                chapter_id="1",
                section_id="1.1",
                section_title="Force",
                content_type=ContentType.IMAGE,
                char_start=image_start,
                char_end=len(text),
                page_or_location="chapter-1/section-1.1",
                asset_ref="image:fig-1",
            ),
        ),
    )


def test_v2_document_requires_provider_neutral_identity_and_schema() -> None:
    document = make_document()

    assert document.schema_version == "2.0"
    assert document.provider == "openstax"
    assert document.textbook_id in REQUIRED_TEXTBOOK_IDS
    assert document.source_name
    assert document.source_version
    assert document.document_text(document.blocks[1]) == "[[FORMULA:f=ma]]\n"


def test_document_rejects_overlapping_or_cross_chapter_block_spans() -> None:
    document = make_document()
    with pytest.raises(ValueError, match="overlapping"):
        TextbookDocument.model_validate(
            {
                **document.model_dump(),
                "blocks": [
                    document.blocks[0].model_dump(),
                    {
                        **document.blocks[0].model_dump(),
                        "block_id": "overlap",
                        "char_start": 1,
                    },
                ],
            }
        )


def test_document_and_chunk_ids_are_stable_and_change_with_identity_inputs() -> None:
    first = make_document()
    repeated = make_document()
    changed_parser = make_document(parser_version="fixture-parser-2.1")

    assert first.document_id == repeated.document_id
    assert first.document_id != changed_parser.document_id

    config_hash = chunk_config_hash(
        {
            "chunker_version": "block-v2",
            "tokenizer": "unicode-wordpunct-v1",
            "target_tokens": 500,
        }
    )
    assert make_chunk_id(first.document_id, "1", config_hash, 1) == make_chunk_id(
        repeated.document_id, "1", config_hash, 1
    )
    assert make_chunk_id(first.document_id, "1", config_hash, 1) != make_chunk_id(
        changed_parser.document_id, "1", config_hash, 1
    )
    assert canonical_document_hash(
        {"text": first.text, "parser_version": "fixture-parser-2.0"}
    ) == (
        canonical_document_hash(
            {"parser_version": "fixture-parser-2.0", "text": first.text}
        )
    )


def test_chunk_keeps_document_global_half_open_span_and_structural_spans() -> None:
    document = make_document()
    chunker = V2BlockChunker()
    chunks = chunker.chunk(document)

    assert len(chunks) == 3
    formula_chunk = chunks[1]
    assert formula_chunk.text == document.document_text(document.blocks[1])
    assert document.text[formula_chunk.char_start : formula_chunk.char_end] == formula_chunk.text
    assert formula_chunk.spans == (
        ChunkSpan(
            block_id="formula-1",
            chapter_id="1",
            char_start=formula_chunk.char_start,
            char_end=formula_chunk.char_end,
            content_type=ContentType.EQUATION,
        ),
    )
    assert formula_chunk.source_locator.startswith("source=openstax_college_physics_2e|")
    assert formula_chunk.section_id == "1.1"
    assert formula_chunk.section_title == "Force"
    assert formula_chunk.content_types == (ContentType.EQUATION,)
    assert "section_id" not in formula_chunk.metadata
    assert "section_title" not in formula_chunk.metadata
    assert "content_type" not in formula_chunk.metadata
    assert formula_chunk.metadata["asset_ref"] == "formula:f=ma"


def test_chunker_derives_a_stable_location_when_page_data_is_unavailable() -> None:
    document = make_document()
    payload = document.model_dump()
    payload["blocks"] = [
        {**block.model_dump(), "page_or_location": None} for block in document.blocks
    ]
    without_pages = TextbookDocument.model_validate(payload)

    chunk = V2BlockChunker().chunk(without_pages)[0]

    assert chunk.page_or_location == "chapter-1/block-body-1"


def _paged_block(**overrides: object) -> dict[str, object]:
    return {
        "block_id": "b1",
        "chapter_id": "1",
        "char_start": 0,
        "char_end": 10,
        "page_start": 25,
        "page_end": 25,
        **overrides,
    }


def test_block_pages_derive_the_canonical_page_location() -> None:
    assert TextBlock.model_validate(_paged_block()).page_or_location == "p25"
    assert TextBlock.model_validate(_paged_block(page_end=26)).page_or_location == "p25-26"
    unpaged = TextBlock.model_validate(
        _paged_block(page_start=None, page_end=None, page_or_location="lesson-3")
    )
    assert unpaged.page_or_location == "lesson-3"


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"page_end": None}, "set together"),
        ({"page_start": 26, "page_end": 25}, "precede"),
        ({"page_or_location": "printed page 7"}, "must be 'p25'"),
    ],
)
def test_block_pages_reject_partial_backwards_or_mismatched_locations(
    overrides: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        TextBlock.model_validate(_paged_block(**overrides))


def test_chunker_carries_block_pages_into_the_chunk_and_its_locator() -> None:
    document = make_document()
    payload = document.model_dump()
    payload["blocks"] = [
        {**block.model_dump(), "page_start": 40, "page_end": 40, "page_or_location": None}
        for block in document.blocks
    ]
    chunk = V2BlockChunker().chunk(TextbookDocument.model_validate(payload))[0]

    assert (chunk.page_start, chunk.page_end, chunk.page_or_location) == (40, 40, "p40")
    assert "|location=p40|" in chunk.source_locator


def test_formula_is_not_a_content_type_so_maths_cannot_bypass_the_evidence_policy() -> None:
    assert "formula" not in {member.value for member in ContentType}
    with pytest.raises(ValueError, match="content_type"):
        TextBlock.model_validate(_paged_block(content_type="formula"))


def _chunk_over_all_blocks(document: TextbookDocument, **overrides: object) -> Chunk:
    blocks = document.blocks
    payload = {
        "chunk_id": "multi-block",
        "provider": document.provider,
        "textbook_id": document.textbook_id,
        "document_id": document.document_id,
        "chapter_id": "1",
        "source_name": document.source_name,
        "page_or_location": "chapter-1",
        "source_locator": source_locator(
            source_name=document.source_name,
            textbook_id=document.textbook_id,
            chapter_id="1",
            page_or_location="chapter-1",
            char_start=0,
            char_end=len(document.text),
        ),
        "text": document.text,
        "char_start": 0,
        "char_end": len(document.text),
        "spans": [
            {
                "block_id": block.block_id,
                "chapter_id": block.chapter_id,
                "char_start": block.char_start,
                "char_end": block.char_end,
                "content_type": block.content_type,
            }
            for block in blocks
        ],
        "chunker_version": "test",
        "chunk_config_hash": "sha256:config",
        "token_count": 3,
        **overrides,
    }
    return Chunk.model_validate(payload)


def test_multi_block_chunk_derives_every_content_type_from_its_spans() -> None:
    chunk = _chunk_over_all_blocks(make_document())

    assert chunk.content_types == (
        ContentType.BODY,
        ContentType.EQUATION,
        ContentType.IMAGE,
    )
    assert Chunk.model_validate(chunk.model_dump(mode="json")) == chunk


def test_chunk_rejects_content_types_that_disagree_with_its_spans() -> None:
    with pytest.raises(ValueError, match="content_types"):
        _chunk_over_all_blocks(make_document(), content_types=["body"])


def test_evidence_span_is_chapter_local_and_hashes_its_verbatim_text() -> None:
    span = EvidenceSpan(
        span_id="gold:sciq-1:1",
        textbook_id=REQUIRED_TEXTBOOK_IDS[0],
        chapter_id="4",
        chapter_char_start=100,
        chapter_char_end=105,
        verbatim_text="force",
        origin_corpus_version="2.0.0-dev.1",
    )

    assert span.text_hash == sha256_text("force")
    assert EvidenceSpan.model_validate_json(span.model_dump_json()) == span
    assert "document_id" not in EvidenceSpan.model_fields
    assert "chunk_ids" not in EvidenceSpan.model_fields


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"chapter_char_end": 106}, "length"),
        ({"text_hash": "sha256:" + "0" * 64}, "SHA-256"),
        ({"chapter_char_end": 100}, "exceed"),
    ],
)
def test_evidence_span_rejects_inconsistent_offsets_or_hash(
    overrides: dict[str, object], message: str
) -> None:
    payload = {
        "span_id": "cc:q1:1",
        "textbook_id": REQUIRED_TEXTBOOK_IDS[0],
        "chapter_id": "4",
        "chapter_char_start": 100,
        "chapter_char_end": 105,
        "verbatim_text": "force",
        "origin_corpus_version": "2.0.0-dev.1",
        **overrides,
    }
    with pytest.raises(ValueError, match=message):
        EvidenceSpan.model_validate(payload)


def test_binding_status_decides_whether_a_location_is_allowed() -> None:
    common = {
        "span_id": "gold:sciq-1:1",
        "textbook_id": REQUIRED_TEXTBOOK_IDS[0],
        "corpus_version": "2.0.0-dev.1",
        "corpus_hash": "sha256:corpus",
    }
    resolved = EvidenceSpanBinding(
        **common,
        resolution_status=SpanResolutionStatus.RESOLVED,
        resolution_method=SpanResolutionMethod.VERBATIM_UNIQUE,
        document_id="doc",
        char_start=5000,
        char_end=5005,
        chunk_ids=("chunk-1",),
    )
    assert resolved.chunk_ids == ("chunk-1",)

    with pytest.raises(ValueError, match="at least one chunk"):
        EvidenceSpanBinding(**{**resolved.model_dump(), "chunk_ids": ()})
    with pytest.raises(ValueError, match="must not carry"):
        EvidenceSpanBinding(
            **common,
            resolution_status=SpanResolutionStatus.STALE,
            chunk_ids=("chunk-1",),
        )
    stale = EvidenceSpanBinding(**common, resolution_status=SpanResolutionStatus.AMBIGUOUS)
    assert stale.document_id is None and stale.chunk_ids == ()


def test_fixture_provenance_url_does_not_change_document_identity(tmp_path) -> None:
    textbook_id = REQUIRED_TEXTBOOK_IDS[0]
    spec = get_textbook_spec(textbook_id)
    source = tmp_path / "renamed-local-file.txt"
    source.write_text("A force changes motion.", encoding="utf-8")
    parser = TextFixtureParser(spec)
    common = {
        "textbook_id": textbook_id,
        "source_path": source,
        "source_name": spec.source_name,
        "source_version": spec.source_version,
        "expected_source_sha256": sha256_text("A force changes motion."),
    }

    first = parser.parse(TextbookInput(**common, source_uri="https://example.test/one"))
    second = parser.parse(TextbookInput(**common, source_uri="https://example.test/two"))

    assert first.document_id == second.document_id
    assert first.document_hash == second.document_hash


def test_chunk_rejects_text_that_does_not_match_its_span() -> None:
    with pytest.raises(ValueError, match="text length"):
        Chunk(
            provider="openstax",
            textbook_id="book",
            document_id="doc",
            chapter_id="1",
            chunk_id="chunk",
            source_name="book.pdf",
            page_or_location="chapter-1",
            source_locator="fixture%3A%2F%2Fbook",
            text="abc",
            char_start=0,
            char_end=2,
            spans=(
                ChunkSpan(
                    block_id="b",
                    chapter_id="1",
                    char_start=0,
                    char_end=2,
                    content_type=ContentType.BODY,
                ),
            ),
            chunker_version="block-v2",
            chunk_config_hash="sha256:config",
            token_count=1,
        )


def test_chunk_rejects_the_legacy_uri_and_document_locator_format() -> None:
    document = make_document()
    payload = V2BlockChunker().chunk(document)[0].model_dump()
    payload["source_locator"] = (
        "uri=fixture%3A%2F%2Fbook|textbook=book|document=generated|"
        "chapter=1|location=chapter-1|span=0:22"
    )

    with pytest.raises(ValueError, match="source_locator"):
        Chunk.model_validate(payload)


def test_catalog_freezes_the_required_v2_textbooks_and_rejects_unknown_ids() -> None:
    assert REQUIRED_TEXTBOOK_IDS == (
        "openstax_college_physics_2e",
        "openstax_physics",
        "openstax_college_physics_ap_2e",
    )
    assert all(get_textbook_spec(book_id).enabled for book_id in REQUIRED_TEXTBOOK_IDS)
    with pytest.raises(ValueError, match="unknown textbook_id"):
        get_textbook_spec("not-a-real-v2-book")


@pytest.mark.parametrize(
    ("textbook_id", "version", "last_chapter", "pdf_sha256"),
    [
        (
            "openstax_college_physics_2e",
            "2e",
            34,
            "a052d9fae2a90e135a74d70c001a78bb49b83280be58191e108d5de577699bb6",
        ),
        (
            "openstax_physics",
            "1e",
            23,
            "a3f75487411ef13d0270c65fc801ceff2b28e6b339afed9b407fe477f7e8453e",
        ),
        (
            "openstax_college_physics_ap_2e",
            "2e",
            34,
            "de438d7a0ed13339340d3e6bb93346920ef146c99e1275e8c84ba476555943d7",
        ),
    ],
)
def test_each_openstax_book_is_pinned_to_the_pdf_m2_validated(
    textbook_id: str, version: str, last_chapter: int, pdf_sha256: str
) -> None:
    spec = get_textbook_spec(textbook_id)

    assert spec.provider == "openstax"
    assert spec.expected_source_sha256 == "sha256:" + pdf_sha256
    assert spec.selected_chapters == tuple(
        str(chapter) for chapter in range(1, last_chapter + 1)
    )
    assert spec.source_version == version


def test_ck12_is_required_but_not_yet_in_the_catalogue() -> None:
    assert "ck12" in REQUIRED_PROVIDERS
    assert missing_required_providers(REQUIRED_TEXTBOOK_IDS) == ("ck12",)
    assert missing_required_providers(REQUIRED_TEXTBOOK_IDS, ("openstax",)) == ()


@pytest.mark.parametrize(
    "source_name",
    ["openstax_college_physics_2e.json", "local_copy", "openstax_college_physics_2e/vol1.pdf"],
)
def test_catalog_source_name_is_the_textbook_id_without_a_file_extension(
    monkeypatch: pytest.MonkeyPatch, source_name: str
) -> None:
    from dataclasses import replace

    from cs30.v2 import catalog

    textbook_id = REQUIRED_TEXTBOOK_IDS[0]
    assert get_textbook_spec(textbook_id).source_name == textbook_id
    monkeypatch.setitem(
        catalog.TEXTBOOK_CATALOG,
        textbook_id,
        replace(catalog.TEXTBOOK_CATALOG[textbook_id], source_name=source_name),
    )
    with pytest.raises(ValueError, match="source_name"):
        catalog.validate_catalog()


def test_v2_document_does_not_accept_the_v1_source_alias_as_a_substitute() -> None:
    document = make_document()
    payload = document.model_dump()
    payload.pop("source_uri")
    payload["source"] = "legacy://v1-source"

    with pytest.raises(ValueError, match="source"):
        TextbookDocument.model_validate(payload)


def test_dense_provenance_and_index_artifact_expose_load_compatibility_fields() -> None:
    with pytest.raises(ValueError, match="embedding identity"):
        EvidenceProvenance(
            corpus_version="2.0.0-dev.1",
            corpus_hash="sha256:corpus",
            manifest_hash="sha256:manifest",
            chunk_config_hash="sha256:chunks",
            index_version="index-v2",
            retrieval_mode=RetrievalMode.DENSE,
            retrieval_config_hash="sha256:retrieval",
        )

    artifact = IndexArtifact(
        artifact_id="fixture-index",
        index_type="fixture",
        index_format_version="1",
        location="runtime-only",
        asset_relpaths=("index.bin", "chunk-map.json", "artifact.json"),
        corpus_version="2.0.0-dev.1",
        corpus_hash="sha256:corpus",
        manifest_hash="sha256:manifest",
        chunk_config_hash="sha256:chunks",
        required_textbook_ids=REQUIRED_TEXTBOOK_IDS,
        included_textbook_ids=REQUIRED_TEXTBOOK_IDS,
        chunk_count=1,
        chunk_ids=("chunk-1",),
        embedding_model="fixture-model",
        embedding_revision="fixture-revision",
        embedding_dimension=3,
        similarity_metric="cosine",
        normalise_embeddings=True,
        index_version="index-v2",
    )

    assert artifact.asset_relpaths == ("index.bin", "chunk-map.json", "artifact.json")
    assert artifact.manifest_hash == "sha256:manifest"
