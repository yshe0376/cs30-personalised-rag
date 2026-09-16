import hashlib
import json
from pathlib import Path

import pytest

from cs30.contracts import ContentType, OpenStaxChapter, OpenStaxDocument, TextBlock
from cs30.evaluation import GoldEvidenceSpan, SpanResolutionStatus, resolve_span_to_corpus
from cs30.evaluation.openstax_archive import (
    load_openstax_archive,
    load_prepared_corpus,
    write_prepared_corpus,
)


def _document(content_type: ContentType) -> OpenStaxDocument:
    return OpenStaxDocument(
        document_id="policy-test-book",
        title="Policy test book",
        version="1",
        source="test",
        document_hash="sha256:test-pdf",
        parser_version="1.2.0",
        text="Evidence.",
        chapters=[OpenStaxChapter(chapter_id="1", title="One", char_start=0, char_end=9)],
        blocks=[
            TextBlock(
                block_id="block-1",
                chapter_id="1",
                content_type=content_type,
                char_start=0,
                char_end=9,
            )
        ],
    )


@pytest.mark.parametrize("content_type", [ContentType.PROBLEM, ContentType.SUMMARY])
def test_policy_gate_rejects_ineligible_final_block(content_type: ContentType) -> None:
    document = _document(content_type)
    span = GoldEvidenceSpan(
        span_id="span-1",
        document_id=document.document_id,
        chapter_id="1",
        char_start=0,
        char_end=9,
        verbatim_text="Evidence.",
        block_id="block-1",
    )

    resolution = resolve_span_to_corpus(span, document)

    assert resolution.status is SpanResolutionStatus.STALE
    assert "not eligible" in resolution.message


def test_verbatim_fallback_gates_the_fallback_block_not_original_id() -> None:
    document = _document(ContentType.PROBLEM)
    span = GoldEvidenceSpan(
        span_id="span-1",
        document_id=document.document_id,
        chapter_id="1",
        char_start=0,
        char_end=9,
        verbatim_text="Evidence.",
        block_id="stale-block-id",
    )

    resolution = resolve_span_to_corpus(span, document)

    assert resolution.status is SpanResolutionStatus.STALE
    assert "not eligible" in resolution.message


def test_chapter_offset_without_block_id_cannot_bypass_policy_gate() -> None:
    document = _document(ContentType.BODY)
    span = GoldEvidenceSpan(
        span_id="span-1",
        document_id=document.document_id,
        chapter_id="1",
        char_start=0,
        char_end=9,
        verbatim_text="Evidence.",
    )

    resolution = resolve_span_to_corpus(span, document)

    assert resolution.status is SpanResolutionStatus.RESOLVED
    assert resolution.resolved_block_id == "block-1"


def test_chapter_offset_without_block_id_rejects_ineligible_block() -> None:
    document = _document(ContentType.PROBLEM)
    span = GoldEvidenceSpan(
        span_id="span-1",
        document_id=document.document_id,
        chapter_id="1",
        char_start=0,
        char_end=9,
        verbatim_text="Evidence.",
    )

    resolution = resolve_span_to_corpus(span, document)

    assert resolution.status is SpanResolutionStatus.STALE
    assert "not eligible" in resolution.message


def test_prepared_loader_rejects_tampered_evidence_and_forged_block_id(tmp_path: Path) -> None:
    import zipfile

    source = _document(ContentType.BODY)
    archive_path = tmp_path / "data.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(
            "parsed_openstax_ch1/openstax_document.json",
            source.model_dump_json(),
        )
    corpus = load_openstax_archive(archive_path)
    output_dir = tmp_path / "prepared"
    write_prepared_corpus(corpus, output_dir)
    evidence_path = output_dir / "evidence_source_blocks.jsonl"
    original = evidence_path.read_bytes()
    evidence_path.write_bytes(original.replace(b"Evidence.", b"Changed!."))
    with pytest.raises(ValueError, match="checksum"):
        load_prepared_corpus(output_dir)

    evidence_path.write_bytes(original)
    records = [json.loads(line) for line in original.decode().splitlines()]
    records[0]["block_id"] = "forged-block"
    forged = (
        (json.dumps(records[0], ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
        .encode()
    )
    evidence_path.write_bytes(forged)
    manifest_path = output_dir / "corpus_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["evidence_blocks_sha256"] = "sha256:" + hashlib.sha256(forged).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="absent from the document"):
        load_prepared_corpus(output_dir)
