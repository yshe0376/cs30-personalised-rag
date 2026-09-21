"""M1 multi-textbook parse → chunk → Manifest build pipeline."""

from __future__ import annotations

import json
import shutil
import uuid
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Literal

from cs30.v2.catalog import get_textbook_spec
from cs30.v2.config import validate_v2_output_dir
from cs30.v2.contracts import Chunk, IndexArtifact, TextbookDocument
from cs30.v2.corpus.canonical import canonical_chunks, canonical_corpus_bytes
from cs30.v2.corpus.manifest import (
    CorpusManifest,
    build_manifest_draft,
    finalize_manifest,
    write_corpus_manifest,
)
from cs30.v2.corpus.publish import atomic_publish_directory
from cs30.v2.errors import (
    BuildGateError,
    ContractError,
    InputError,
    PublishConflictError,
    V2Error,
)
from cs30.v2.ids import sha256_file
from cs30.v2.ports import (
    ChunkBatchReport,
    Chunker,
    CorpusManifestBuilder,
    DocumentParser,
    IndexBuilder,
    MaterialFailure,
    ParseBatchReport,
    ParserRegistry,
    TextbookInput,
)


def _failure(
    input: TextbookInput,
    *,
    stage: str,
    code: str,
    error: Exception,
) -> MaterialFailure:
    return MaterialFailure(
        textbook_id=input.textbook_id,
        source_path=input.source_path,
        stage=stage,
        error_code=code,
        error_type=type(error).__name__,
        message=str(error),
    )


def _ensure_official_components_are_real(
    inputs: Sequence[TextbookInput],
    parser_registry: ParserRegistry,
    chunker: Chunker,
) -> None:
    """Reject explicitly marked fixture providers before an official build."""

    if getattr(chunker, "is_fixture", False):
        raise BuildGateError(
            "official v2 builds cannot use a fixture chunker",
            code="FIXTURE_NOT_ALLOWED",
        )
    for input in inputs:
        try:
            parser = parser_registry.parser_for(input.textbook_id)
        except (KeyError, LookupError):
            continue
        if getattr(parser, "is_fixture", False):
            raise BuildGateError(
                f"official v2 builds cannot use a fixture parser for {input.textbook_id}",
                code="FIXTURE_NOT_ALLOWED",
            )


def parse_material_batch(
    inputs: Sequence[TextbookInput],
    parser_registry: ParserRegistry,
    *,
    require_source_hash: bool = False,
) -> ParseBatchReport:
    """Parse each input independently while returning successes and failures."""

    seen: set[str] = set()
    documents: list[TextbookDocument] = []
    failures: list[MaterialFailure] = []
    seen_document_ids: set[str] = set()

    for input in inputs:
        if input.textbook_id in seen:
            raise InputError(
                f"duplicate textbook_id: {input.textbook_id}",
                code="DUPLICATE_TEXTBOOK_ID",
            )
        seen.add(input.textbook_id)

        try:
            catalog_source_name = get_textbook_spec(input.textbook_id).source_name
        except ValueError as exc:
            failures.append(
                _failure(input, stage="input", code="UNKNOWN_TEXTBOOK", error=exc)
            )
            continue
        if input.source_name != catalog_source_name:
            failures.append(
                _failure(
                    input,
                    stage="input",
                    code="SOURCE_NAME_MISMATCH",
                    error=ValueError(
                        f"expected catalog source_name {catalog_source_name!r}, "
                        f"received {input.source_name!r}"
                    ),
                )
            )
            continue

        if not input.source_path.is_file():
            failures.append(
                _failure(
                    input,
                    stage="input",
                    code="INPUT_NOT_FOUND",
                    error=FileNotFoundError(str(input.source_path)),
                )
            )
            continue
        if require_source_hash and not input.expected_source_sha256:
            failures.append(
                _failure(
                    input,
                    stage="input",
                    code="SOURCE_HASH_NOT_PINNED",
                    error=ValueError("official builds require an expected source SHA-256"),
                )
            )
            continue
        try:
            actual_hash = sha256_file(input.source_path)
        except OSError as exc:
            failures.append(_failure(input, stage="input", code="INPUT_NOT_FOUND", error=exc))
            continue
        if input.expected_source_sha256 and actual_hash != input.expected_source_sha256:
            failures.append(
                _failure(
                    input,
                    stage="input",
                    code="SOURCE_HASH_MISMATCH",
                    error=ValueError(
                        f"expected {input.expected_source_sha256}, received {actual_hash}"
                    ),
                )
            )
            continue

        try:
            parser: DocumentParser = parser_registry.parser_for(input.textbook_id)
        except (KeyError, LookupError) as exc:
            failures.append(
                _failure(
                    input,
                    stage="parse",
                    code="PARSER_NOT_REGISTERED",
                    error=exc,
                )
            )
            continue
        try:
            document = parser.parse(input)
            if not isinstance(document, TextbookDocument):
                raise TypeError("parser did not return a TextbookDocument")
            if document.textbook_id != input.textbook_id:
                raise ContractError(
                    f"document textbook_id {document.textbook_id!r} does not match "
                    f"input {input.textbook_id!r}",
                    code="ASSET_VERSION_MISMATCH",
                )
            if (
                document.source_name != input.source_name
                or document.source_version != input.source_version
                or (
                    input.source_uri is not None
                    and document.source_uri != input.source_uri
                )
            ):
                raise ContractError(
                    "parser source identity does not match TextbookInput",
                    code="ASSET_VERSION_MISMATCH",
                )
            if document.raw_source_sha256 != actual_hash:
                raise ContractError(
                    "document raw_source_sha256 does not match the input file",
                    code="HASH_MISMATCH",
                )
            if document.document_id in seen_document_ids:
                raise ContractError(
                    f"duplicate document_id: {document.document_id}",
                    code="DUPLICATE_DOCUMENT_ID",
                )
            seen_document_ids.add(document.document_id)
            documents.append(document)
        except V2Error as exc:
            failures.append(_failure(input, stage="parse", code=exc.code, error=exc))
        except Exception as exc:
            failures.append(_failure(input, stage="parse", code="PARSE_FAILED", error=exc))

    return ParseBatchReport(documents=tuple(documents), failures=tuple(failures))


def chunk_material_batch(
    documents: Sequence[TextbookDocument],
    inputs: Sequence[TextbookInput],
    chunker: Chunker,
) -> ChunkBatchReport:
    """Chunk documents independently so one bad textbook does not hide others."""

    inputs_by_id = {input.textbook_id: input for input in inputs}
    chunks: list[Chunk] = []
    failures: list[MaterialFailure] = []
    seen_chunk_ids: set[str] = set()

    for document in documents:
        input = inputs_by_id.get(
            document.textbook_id,
            TextbookInput(
                textbook_id=document.textbook_id,
                source_path=Path(document.source_name),
                source_name=document.source_name,
                source_version=document.source_version,
            ),
        )
        try:
            produced = tuple(chunker.chunk(document))
            if not produced:
                raise ValueError("chunker returned no chunks")
            for chunk in produced:
                if (
                    chunk.document_id != document.document_id
                    or chunk.textbook_id != document.textbook_id
                ):
                    raise ContractError(
                        f"chunk identity does not match document: {chunk.chunk_id}",
                        code="ASSET_VERSION_MISMATCH",
                    )
                if chunk.chunk_id in seen_chunk_ids:
                    raise ContractError(
                        f"duplicate chunk_id: {chunk.chunk_id}",
                        code="DUPLICATE_CHUNK_ID",
                    )
                seen_chunk_ids.add(chunk.chunk_id)
            chunks.extend(produced)
        except V2Error as exc:
            failures.append(_failure(input, stage="chunk", code=exc.code, error=exc))
        except Exception as exc:
            failures.append(_failure(input, stage="chunk", code="CHUNK_FAILED", error=exc))

    return ChunkBatchReport(chunks=tuple(chunks), failures=tuple(failures))


@dataclass(frozen=True)
class MultiTextbookBuildSpec:
    corpus_version: str
    required_textbook_ids: tuple[str, ...]
    mode: Literal["development", "official"]
    environment: Literal["development", "staging", "production"]
    output_dir: Path

    def __post_init__(self) -> None:
        if len(self.required_textbook_ids) != 3:
            raise ValueError("required_textbook_ids must contain exactly three IDs")
        if len(set(self.required_textbook_ids)) != 3:
            raise ValueError("required_textbook_ids must be unique")
        validate_v2_output_dir(self.output_dir)


@dataclass(frozen=True)
class BuildDeps:
    parser_registry: ParserRegistry
    chunker: Chunker
    manifest_builder: CorpusManifestBuilder | None = None
    index_builder: IndexBuilder | None = None


@dataclass(frozen=True)
class BuildOutcome:
    manifest: CorpusManifest | None
    artifact: IndexArtifact | None
    manifest_path: Path | None
    corpus_path: Path | None
    report_path: Path


def _failure_payload(failure: MaterialFailure) -> dict[str, object]:
    payload = asdict(failure)
    payload["source_path"] = str(failure.source_path)
    return payload


def _write_run_report(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _write_records(path: Path, chunks: Sequence[Chunk]) -> None:
    path.write_bytes(canonical_corpus_bytes(chunks))


def _validate_index_artifact(
    artifact: IndexArtifact,
    manifest: CorpusManifest,
    chunks: Sequence[Chunk],
    output_dir: Path,
) -> None:
    """Reject an index that cannot be paired with the staged corpus."""

    expected_chunk_ids = tuple(chunk.chunk_id for chunk in chunks)
    checks = (
        (artifact.corpus_version, manifest.corpus_version, "corpus_version"),
        (artifact.corpus_hash, manifest.corpus_hash, "corpus_hash"),
        (artifact.manifest_hash, manifest.manifest_hash, "manifest_hash"),
        (artifact.chunk_config_hash, manifest.chunk_config_hash, "chunk_config_hash"),
        (
            artifact.required_textbook_ids,
            manifest.required_textbook_ids,
            "required_textbook_ids",
        ),
        (
            artifact.included_textbook_ids,
            manifest.included_textbook_ids,
            "included_textbook_ids",
        ),
        (artifact.chunk_count, len(expected_chunk_ids), "chunk_count"),
        (artifact.chunk_ids, expected_chunk_ids, "chunk_ids"),
    )
    for received, expected, field in checks:
        if received != expected:
            raise ContractError(
                f"index artifact {field} does not match the staged corpus",
                code="INDEX_ARTIFACT_MISMATCH",
            )

    root = output_dir.resolve()
    for relative in artifact.asset_relpaths:
        path = PurePosixPath(relative)
        if path.is_absolute() or ".." in path.parts:
            raise ContractError(
                f"index artifact asset escapes the staging directory: {relative}",
                code="INDEX_ARTIFACT_PATH_INVALID",
            )
        candidate = (output_dir / Path(*path.parts)).resolve()
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise ContractError(
                f"index artifact asset escapes the staging directory: {relative}",
                code="INDEX_ARTIFACT_PATH_INVALID",
            ) from exc
        if not candidate.is_file():
            raise ContractError(
                f"index artifact asset was not written: {relative}",
                code="INDEX_ARTIFACT_ASSET_MISSING",
            )


def run_build_pipeline(
    inputs: Sequence[TextbookInput],
    deps: BuildDeps,
    spec: MultiTextbookBuildSpec,
) -> BuildOutcome:
    """Run a versioned M1 build and publish only a complete directory."""

    required = set(spec.required_textbook_ids)
    supplied_ids = [input.textbook_id for input in inputs]
    unknown_ids = set(supplied_ids) - required
    if unknown_ids:
        raise InputError(
            f"inputs contain non-required textbook IDs: {sorted(unknown_ids)}",
            code="UNKNOWN_TEXTBOOK",
        )

    if spec.mode == "official":
        _ensure_official_components_are_real(
            inputs,
            deps.parser_registry,
            deps.chunker,
        )

    parse_report = parse_material_batch(
        inputs,
        deps.parser_registry,
        require_source_hash=spec.mode == "official",
    )
    chunk_report = chunk_material_batch(parse_report.documents, inputs, deps.chunker)
    ordered_chunks = canonical_chunks(chunk_report.chunks)
    failed_ids = {
        failure.textbook_id
        for failure in (*parse_report.failures, *chunk_report.failures)
    }
    missing_ids = required - set(supplied_ids)
    failed_ids.update(missing_ids)
    failures = list(parse_report.failures) + list(chunk_report.failures)
    failures.extend(
        MaterialFailure(
            textbook_id=textbook_id,
            source_path=Path("<missing>"),
            stage="input",
            error_code="MISSING_REQUIRED_TEXTBOOK",
            error_type="MissingRequiredTextbook",
            message=f"required textbook was not supplied: {textbook_id}",
        )
        for textbook_id in sorted(missing_ids)
    )

    manifest_kwargs = {
        "corpus_version": spec.corpus_version,
        "chunk_config_hash": deps.chunker.config_hash,
        "required_textbook_ids": spec.required_textbook_ids,
        "mode": spec.mode,
        "failed_textbook_ids": tuple(
            textbook_id
            for textbook_id in spec.required_textbook_ids
            if textbook_id in failed_ids
        ),
    }
    if deps.manifest_builder is None:
        draft = build_manifest_draft(
            parse_report.documents,
            ordered_chunks,
            **manifest_kwargs,
        )
    else:
        draft = deps.manifest_builder.build(
            parse_report.documents,
            ordered_chunks,
            **manifest_kwargs,
        )
    if spec.mode == "official" and deps.index_builder is None:
        draft = draft.model_copy(
            update={
                "validation_errors": (
                    *draft.validation_errors,
                    "index builder is not configured for an official build",
                )
            }
        )
    manifest = finalize_manifest(draft)
    run_id = uuid.uuid4().hex[:16]
    report_payload = {
        "schema_version": "2.0",
        "run_id": run_id,
        "environment": spec.environment,
        "mode": spec.mode,
        "corpus_version": spec.corpus_version,
        "reportable": manifest.reportable,
        "required_textbook_ids": list(manifest.required_textbook_ids),
        "included_textbook_ids": list(manifest.included_textbook_ids),
        "failed_textbook_ids": list(manifest.failed_textbook_ids),
        "document_count": len(manifest.documents),
        "record_count": manifest.record_count,
        "corpus_hash": manifest.corpus_hash,
        "manifest_hash": manifest.manifest_hash,
        "validation_errors": list(manifest.validation_errors),
        "artifact_ready": deps.index_builder is not None,
        "failures": [_failure_payload(failure) for failure in failures],
    }

    output_dir = spec.output_dir.resolve()
    if output_dir.exists():
        raise PublishConflictError(f"output directory already exists: {output_dir}")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging_dir = output_dir.parent / f".{output_dir.name}.staging-{run_id}"
    staging_dir.mkdir()
    staging_records = staging_dir / "records.jsonl"
    staging_manifest = staging_dir / "manifest.json"
    staging_report = staging_dir / "run_report.json"
    try:
        _write_records(staging_records, ordered_chunks)
        write_corpus_manifest(manifest, staging_manifest)
        _write_run_report(staging_report, report_payload)

        if spec.mode == "official" and not manifest.reportable:
            diagnostics_dir = output_dir.with_name(output_dir.name + ".diagnostics")
            diagnostics_dir.mkdir(parents=True, exist_ok=True)
            _write_records(diagnostics_dir / "records.jsonl", ordered_chunks)
            write_corpus_manifest(manifest, diagnostics_dir / "manifest.json")
            diagnostics_report = diagnostics_dir / "run_report.json"
            _write_run_report(diagnostics_report, report_payload)
            raise BuildGateError(
                "official v2 build is not reportable; see diagnostics",
                code=(
                    "MISSING_REQUIRED_TEXTBOOK"
                    if missing_ids
                    else (
                        failures[0].error_code
                        if failures
                        else "INDEX_BUILDER_NOT_CONFIGURED"
                    )
                ),
                report_path=diagnostics_report,
                manifest=manifest,
            )

        artifact: IndexArtifact | None = None
        if deps.index_builder is not None:
            artifact = deps.index_builder.build(
                ordered_chunks,
                manifest,
                output_dir=staging_dir,
            )
            artifact_path = staging_dir / "artifact.json"
            artifact_path.write_text(
                artifact.model_dump_json(indent=2),
                encoding="utf-8",
            )
            _validate_index_artifact(artifact, manifest, ordered_chunks, staging_dir)
        atomic_publish_directory(staging_dir, output_dir)
    except BuildGateError:
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise
    except Exception:
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise

    return BuildOutcome(
        manifest=manifest,
        artifact=artifact,
        manifest_path=output_dir / "manifest.json",
        corpus_path=output_dir / "records.jsonl",
        report_path=output_dir / "run_report.json",
    )


class JsonDocumentParser:
    """Read an already-normalised v2 JSON document without v1 fallback."""

    def parse(self, input: TextbookInput) -> TextbookDocument:
        return TextbookDocument.model_validate_json(
            input.source_path.read_text(encoding="utf-8")
        )


class MappingParserRegistry:
    def __init__(self, parsers: dict[str, DocumentParser]) -> None:
        self._parsers = dict(parsers)

    def parser_for(self, textbook_id: str) -> DocumentParser:
        try:
            return self._parsers[textbook_id]
        except KeyError as exc:
            raise KeyError(textbook_id) from exc
