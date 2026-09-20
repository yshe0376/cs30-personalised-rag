"""Batch failure isolation and build-gate tests for v2 M1."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_v2_contracts import make_document

from cs30.v2.catalog import REQUIRED_TEXTBOOK_IDS
from cs30.v2.chunking import V2BlockChunker
from cs30.v2.contracts import TextbookDocument
from cs30.v2.errors import BuildGateError, InputError
from cs30.v2.ids import sha256_text
from cs30.v2.pipeline import (
    BuildDeps,
    MultiTextbookBuildSpec,
    chunk_material_batch,
    parse_material_batch,
    run_build_pipeline,
)
from cs30.v2.ports import TextbookInput


class StaticParser:
    def __init__(self, document: TextbookDocument, *, error: Exception | None = None) -> None:
        self.document = document
        self.error = error

    def parse(self, input: TextbookInput) -> TextbookDocument:
        if self.error is not None:
            raise self.error
        return self.document


class StaticRegistry:
    def __init__(self, parsers: dict[str, StaticParser]) -> None:
        self.parsers = parsers

    def parser_for(self, textbook_id: str) -> StaticParser:
        try:
            return self.parsers[textbook_id]
        except KeyError as exc:
            raise KeyError(textbook_id) from exc


def make_input(
    tmp_path: Path,
    textbook_id: str,
    *,
    provider: str,
) -> tuple[TextbookInput, TextbookDocument]:
    document = make_document(textbook_id, provider=provider)
    source = tmp_path / f"{textbook_id}.txt"
    source.write_bytes(document.text.encode("utf-8"))
    document = document.model_copy(update={"raw_source_sha256": sha256_text(document.text)})
    return (
        TextbookInput(
            textbook_id=textbook_id,
            source_path=source,
            source_name=document.source_name,
            source_version=document.source_version,
            source_uri=document.source_uri,
            expected_source_sha256=sha256_text(document.text),
        ),
        document,
    )


def make_build(tmp_path: Path, *, count: int = 3):
    inputs: list[TextbookInput] = []
    documents: dict[str, TextbookDocument] = {}
    parsers: dict[str, StaticParser] = {}
    for index, textbook_id in enumerate(REQUIRED_TEXTBOOK_IDS[:count]):
        input, document = make_input(
            tmp_path,
            textbook_id,
            provider="openstax" if index == 0 else "ck12",
        )
        inputs.append(input)
        documents[textbook_id] = document
        parsers[textbook_id] = StaticParser(document)
    return inputs, documents, StaticRegistry(parsers)


def test_parse_batch_keeps_successful_books_when_one_parser_fails(tmp_path: Path) -> None:
    inputs, documents, _ = make_build(tmp_path)
    failing = REQUIRED_TEXTBOOK_IDS[2]
    registry = StaticRegistry(
        {
            textbook_id: StaticParser(
                document,
                error=RuntimeError("parser exploded") if textbook_id == failing else None,
            )
            for textbook_id, document in documents.items()
        }
    )

    report = parse_material_batch(inputs, registry)

    assert {document.textbook_id for document in report.documents} == set(REQUIRED_TEXTBOOK_IDS[:2])
    assert len(report.failures) == 1
    assert report.failures[0].textbook_id == failing
    assert report.failures[0].error_code == "PARSE_FAILED"


def test_parse_batch_rejects_source_hash_mismatch_before_parser(tmp_path: Path) -> None:
    inputs, _, registry = make_build(tmp_path, count=1)
    invalid = inputs[0].__class__(
        **{
            **inputs[0].__dict__,
            "expected_source_sha256": "sha256:" + "0" * 64,
        }
    )

    report = parse_material_batch((invalid,), registry)

    assert report.documents == ()
    assert report.failures[0].error_code == "SOURCE_HASH_MISMATCH"


def test_parse_batch_duplicate_textbook_id_is_a_stable_input_error(tmp_path: Path) -> None:
    inputs, _, registry = make_build(tmp_path, count=1)

    with pytest.raises(InputError) as exc_info:
        parse_material_batch((inputs[0], inputs[0]), registry)

    assert exc_info.value.code == "DUPLICATE_TEXTBOOK_ID"
    assert exc_info.value.exit_code == 2


def test_chunk_batch_keeps_other_documents_when_one_chunker_call_fails(tmp_path: Path) -> None:
    inputs, documents, _ = make_build(tmp_path)

    class SelectiveChunker(V2BlockChunker):
        def chunk(self, document: TextbookDocument):
            if document.textbook_id == REQUIRED_TEXTBOOK_IDS[1]:
                raise RuntimeError("chunk exploded")
            return super().chunk(document)

    report = chunk_material_batch(tuple(documents.values()), inputs, SelectiveChunker())

    assert {chunk.textbook_id for chunk in report.chunks} == {
        REQUIRED_TEXTBOOK_IDS[0],
        REQUIRED_TEXTBOOK_IDS[2],
    }
    assert report.failures[0].error_code == "CHUNK_FAILED"


def test_development_build_publishes_diagnostic_manifest_and_run_report(tmp_path: Path) -> None:
    inputs, _, registry = make_build(tmp_path)
    output_dir = tmp_path / "artifacts" / "v2" / "three-textbooks" / "dev"
    outcome = run_build_pipeline(
        inputs,
        BuildDeps(parser_registry=registry, chunker=V2BlockChunker()),
        MultiTextbookBuildSpec(
            corpus_version="2.0.0-dev.1",
            required_textbook_ids=REQUIRED_TEXTBOOK_IDS,
            mode="development",
            environment="development",
            output_dir=output_dir,
        ),
    )

    assert outcome.manifest is not None
    assert outcome.manifest.reportable is False
    assert outcome.artifact is None
    assert outcome.manifest_path == output_dir / "manifest.json"
    assert outcome.corpus_path == output_dir / "records.jsonl"
    report = json.loads(outcome.report_path.read_text(encoding="utf-8"))
    assert report["reportable"] is False
    assert report["included_textbook_ids"] == list(REQUIRED_TEXTBOOK_IDS)


def test_official_build_gate_writes_diagnostics_but_never_publishes_partial_output(
    tmp_path: Path,
) -> None:
    inputs, _, registry = make_build(tmp_path, count=2)
    output_dir = tmp_path / "artifacts" / "v2" / "three-textbooks" / "official"

    with pytest.raises(BuildGateError) as exc_info:
        run_build_pipeline(
            inputs,
            BuildDeps(parser_registry=registry, chunker=V2BlockChunker()),
            MultiTextbookBuildSpec(
                corpus_version="2.0.0-rc.1",
                required_textbook_ids=REQUIRED_TEXTBOOK_IDS,
                mode="official",
                environment="staging",
                output_dir=output_dir,
            ),
        )

    error = exc_info.value
    assert error.code == "MISSING_REQUIRED_TEXTBOOK"
    assert error.report_path is not None and error.report_path.is_file()
    assert not output_dir.exists()
    diagnostics_dir = output_dir.with_name(output_dir.name + ".diagnostics")
    report = json.loads((diagnostics_dir / "run_report.json").read_text(encoding="utf-8"))
    assert REQUIRED_TEXTBOOK_IDS[2] in report["failed_textbook_ids"]


def test_build_output_records_are_stable_across_repeated_runs(tmp_path: Path) -> None:
    inputs, _, registry = make_build(tmp_path)
    first = run_build_pipeline(
        inputs,
        BuildDeps(parser_registry=registry, chunker=V2BlockChunker()),
        MultiTextbookBuildSpec(
            corpus_version="2.0.0-dev.1",
            required_textbook_ids=REQUIRED_TEXTBOOK_IDS,
            mode="development",
            environment="development",
            output_dir=tmp_path / "artifacts" / "v2" / "first",
        ),
    )
    second = run_build_pipeline(
        inputs,
        BuildDeps(parser_registry=registry, chunker=V2BlockChunker()),
        MultiTextbookBuildSpec(
            corpus_version="2.0.0-dev.1",
            required_textbook_ids=REQUIRED_TEXTBOOK_IDS,
            mode="development",
            environment="development",
            output_dir=tmp_path / "artifacts" / "v2" / "second",
        ),
    )

    assert first.manifest is not None and second.manifest is not None
    assert first.manifest.corpus_hash == second.manifest.corpus_hash
    assert first.manifest.manifest_hash == second.manifest.manifest_hash
    assert first.corpus_path.read_bytes() == second.corpus_path.read_bytes()
