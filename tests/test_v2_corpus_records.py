"""Reading a published v2 corpus back, and refusing anything that is not it."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_v2_contracts import make_document
from test_v2_pipeline import StaticParser, StaticRegistry

from cs30.fixtures import load_fixture
from cs30.v2.catalog import REQUIRED_TEXTBOOK_IDS, get_textbook_spec
from cs30.v2.chunking import V2BlockChunker
from cs30.v2.contracts import Chunk
from cs30.v2.corpus import load_corpus_manifest, load_corpus_records
from cs30.v2.corpus.canonical import manifest_hash
from cs30.v2.corpus.manifest import write_corpus_manifest
from cs30.v2.errors import ContractError
from cs30.v2.ids import canonical_json_bytes, sha256_bytes, sha256_text
from cs30.v2.pipeline import BuildDeps, MultiTextbookBuildSpec, run_build_pipeline
from cs30.v2.ports import TextbookInput


def build_corpus(tmp_path: Path) -> tuple[object, Path]:
    inputs = []
    parsers = {}
    for position, textbook_id in enumerate(REQUIRED_TEXTBOOK_IDS, start=1):
        text = f"Book {position} explains force, motion and energy.\n[[FORMULA:f=ma]]\n[[IMAGE:f]]"
        document = make_document(
            textbook_id,
            provider=get_textbook_spec(textbook_id).provider,
            text=text,
        ).model_copy(update={"raw_source_sha256": sha256_text(text)})
        source = tmp_path / f"{textbook_id}.txt"
        source.write_bytes(text.encode("utf-8"))
        inputs.append(
            TextbookInput(
                textbook_id=textbook_id,
                source_path=source,
                source_name=document.source_name,
                source_version=document.source_version,
                source_uri=document.source_uri,
            )
        )
        parsers[textbook_id] = StaticParser(document)
    output_dir = tmp_path / "artifacts" / "v2" / "textbooks" / "records"
    outcome = run_build_pipeline(
        inputs,
        BuildDeps(parser_registry=StaticRegistry(parsers), chunker=V2BlockChunker()),
        MultiTextbookBuildSpec(
            corpus_version="2.0.0-dev.1",
            required_textbook_ids=REQUIRED_TEXTBOOK_IDS,
            mode="development",
            environment="development",
            output_dir=output_dir,
        ),
    )
    return outcome, output_dir


def record_lines(output_dir: Path) -> list[bytes]:
    return (output_dir / "records.jsonl").read_bytes().splitlines(keepends=True)


def republish(output_dir: Path, records: bytes, **manifest_updates: object) -> None:
    """Swap the records and re-seal the manifest, so only the content is wrong."""

    manifest = load_corpus_manifest(output_dir / "manifest.json")
    updated = manifest.model_copy(update={"corpus_hash": sha256_bytes(records), **manifest_updates})
    sealed = updated.model_copy(update={"manifest_hash": manifest_hash(updated)})
    (output_dir / "records.jsonl").write_bytes(records)
    write_corpus_manifest(sealed, output_dir / "manifest.json")


def load_error_code(output_dir: Path) -> str:
    with pytest.raises(ContractError) as exc_info:
        load_corpus_records(output_dir)
    return exc_info.value.code


def test_loads_the_published_chunks_in_record_order(tmp_path: Path) -> None:
    outcome, output_dir = build_corpus(tmp_path)

    loaded = load_corpus_records(output_dir)

    records = [json.loads(line) for line in record_lines(output_dir)]
    assert loaded.manifest == outcome.manifest
    assert loaded.chunk_ids == tuple(record["chunk_id"] for record in records)
    assert len(loaded.chunks) == loaded.manifest.record_count
    assert all(isinstance(chunk, Chunk) for chunk in loaded.chunks)
    first = records[0]
    assert loaded.chunks_by_id[first["chunk_id"]].text == first["text"]


def test_records_that_changed_after_publishing_are_refused(tmp_path: Path) -> None:
    _, output_dir = build_corpus(tmp_path)
    lines = record_lines(output_dir)
    (output_dir / "records.jsonl").write_bytes(b"".join(lines[:-1]))

    assert load_error_code(output_dir) == "CORPUS_HASH_MISMATCH"


def test_a_missing_records_file_is_explicit(tmp_path: Path) -> None:
    _, output_dir = build_corpus(tmp_path)
    (output_dir / "records.jsonl").unlink()

    assert load_error_code(output_dir) == "CORPUS_RECORDS_MISSING"


def test_v1_chunk_records_are_refused_even_under_a_matching_manifest(tmp_path: Path) -> None:
    _, output_dir = build_corpus(tmp_path)
    v1_chunk = load_fixture("chunks.json")[0]
    republish(output_dir, canonical_json_bytes(v1_chunk), record_count=1)

    with pytest.raises(ContractError) as exc_info:
        load_corpus_records(output_dir)

    assert exc_info.value.code == "CORPUS_RECORD_INVALID"
    assert "line 1" in str(exc_info.value)
    assert "schema_version" in str(exc_info.value)


def test_reordered_records_are_not_the_same_corpus(tmp_path: Path) -> None:
    _, output_dir = build_corpus(tmp_path)
    republish(output_dir, b"".join(reversed(record_lines(output_dir))))

    assert load_error_code(output_dir) == "CORPUS_RECORD_ORDER_INVALID"


def test_duplicate_records_are_refused(tmp_path: Path) -> None:
    _, output_dir = build_corpus(tmp_path)
    lines = record_lines(output_dir)
    republish(output_dir, b"".join([lines[0], *lines]), record_count=len(lines) + 1)

    assert load_error_code(output_dir) == "CORPUS_RECORD_INVALID"


@pytest.mark.parametrize(
    ("updates", "code"),
    [
        ({"record_count": 999}, "CORPUS_RECORD_COUNT_MISMATCH"),
        ({"chunk_config_hash": "sha256:another-chunker"}, "CHUNK_CONFIG_MISMATCH"),
        ({"documents": ()}, "CORPUS_DOCUMENT_UNKNOWN"),
    ],
)
def test_records_must_agree_with_the_manifest(
    tmp_path: Path, updates: dict[str, object], code: str
) -> None:
    _, output_dir = build_corpus(tmp_path)
    republish(output_dir, b"".join(record_lines(output_dir)), **updates)

    assert load_error_code(output_dir) == code


def test_per_document_counts_must_agree_with_the_manifest(tmp_path: Path) -> None:
    _, output_dir = build_corpus(tmp_path)
    manifest = load_corpus_manifest(output_dir / "manifest.json")
    first, second, *rest = manifest.documents
    shifted = (
        first.model_copy(update={"chunk_count": first.chunk_count + 1}),
        second.model_copy(update={"chunk_count": second.chunk_count - 1}),
        *rest,
    )
    republish(output_dir, b"".join(record_lines(output_dir)), documents=shifted)

    assert load_error_code(output_dir) == "CORPUS_RECORD_COUNT_MISMATCH"
