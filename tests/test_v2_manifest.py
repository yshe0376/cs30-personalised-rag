"""Manifest and canonical-hash tests for v2 M1."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_v2_contracts import make_document

from cs30.v2.catalog import REQUIRED_TEXTBOOK_IDS
from cs30.v2.chunking import V2BlockChunker
from cs30.v2.contracts import TextbookDocument
from cs30.v2.corpus.canonical import canonical_corpus_bytes
from cs30.v2.corpus.manifest import (
    build_manifest_draft,
    finalize_manifest,
    load_corpus_manifest,
    write_corpus_manifest,
)
from cs30.v2.ids import sha256_text


def make_documents(count: int = 3) -> tuple[TextbookDocument, ...]:
    return tuple(
        make_document(
            REQUIRED_TEXTBOOK_IDS[index],
            provider="openstax" if index == 0 else "ck12",
        )
        for index in range(count)
    )


def make_full_manifest(mode: str = "official"):
    documents = make_documents()
    chunks = tuple(chunk for document in documents for chunk in V2BlockChunker().chunk(document))
    draft = build_manifest_draft(
        documents,
        chunks,
        corpus_version="2.0.0-dev.1",
        chunk_config_hash=chunks[0].chunk_config_hash,
        required_textbook_ids=REQUIRED_TEXTBOOK_IDS,
        mode=mode,
    )
    return draft, finalize_manifest(draft), documents, chunks


def test_manifest_uses_draft_then_finalize_hash_lifecycle() -> None:
    draft, manifest, _, _ = make_full_manifest()

    assert not hasattr(draft, "manifest_hash")
    assert manifest.manifest_hash.startswith("sha256:")
    assert manifest.reportable is True
    assert manifest.required_textbook_ids == REQUIRED_TEXTBOOK_IDS
    assert manifest.included_textbook_ids == REQUIRED_TEXTBOOK_IDS
    assert manifest.failed_textbook_ids == ()


def test_development_manifest_is_never_reportable_even_when_complete() -> None:
    _, manifest, _, _ = make_full_manifest(mode="development")

    assert manifest.reportable is False
    assert "development" in manifest.validation_errors[0]


def test_official_missing_book_is_diagnostic_not_a_fake_complete_manifest() -> None:
    documents = make_documents(2)
    chunks = tuple(chunk for document in documents for chunk in V2BlockChunker().chunk(document))
    draft = build_manifest_draft(
        documents,
        chunks,
        corpus_version="2.0.0-dev.1",
        chunk_config_hash=chunks[0].chunk_config_hash,
        required_textbook_ids=REQUIRED_TEXTBOOK_IDS,
        mode="official",
        failed_textbook_ids=(REQUIRED_TEXTBOOK_IDS[2],),
    )
    manifest = finalize_manifest(draft)

    assert manifest.reportable is False
    assert manifest.included_textbook_ids == REQUIRED_TEXTBOOK_IDS[:2]
    assert manifest.failed_textbook_ids == (REQUIRED_TEXTBOOK_IDS[2],)
    assert any("included" in error for error in manifest.validation_errors)


def test_canonical_corpus_bytes_are_order_independent_and_path_independent() -> None:
    _, _, documents, chunks = make_full_manifest()
    reordered = tuple(reversed(chunks))
    assert canonical_corpus_bytes(chunks) == canonical_corpus_bytes(reordered)
    assert sha256_text(canonical_corpus_bytes(chunks).decode("utf-8")) == sha256_text(
        canonical_corpus_bytes(reordered).decode("utf-8")
    )
    assert str(Path("D:/different-machine/path")) not in canonical_corpus_bytes(chunks).decode()
    assert all(
        document.source_name in canonical_corpus_bytes(chunks).decode()
        for document in documents
    )


def test_manifest_write_and_reload_detects_tampering(tmp_path: Path) -> None:
    _, manifest, _, _ = make_full_manifest()
    path = tmp_path / "manifest.json"
    write_corpus_manifest(manifest, path)
    assert load_corpus_manifest(path) == manifest

    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["record_count"] += 1
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="manifest_hash"):
        load_corpus_manifest(path)


def test_manifest_rejects_duplicate_document_identity() -> None:
    documents = make_documents(1)
    chunks = tuple(V2BlockChunker().chunk(documents[0]))
    with pytest.raises(ValueError, match="document_id"):
        build_manifest_draft(
            (*documents, documents[0]),
            chunks,
            corpus_version="2.0.0-dev.1",
            chunk_config_hash=chunks[0].chunk_config_hash,
            required_textbook_ids=REQUIRED_TEXTBOOK_IDS,
            mode="development",
        )
