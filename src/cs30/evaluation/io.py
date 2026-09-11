"""Strict loaders and crash-safe checkpoints for W5 evaluation artifacts."""

import json
import logging
import os
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from cs30.contracts import OpenStaxDocument

from .mapping import GoldChunkMapping, QuestionChunkMapping
from .models import EvaluationRunResult, GoldEvidenceSpan, GoldSample, SpanResolutionStatus
from .normalization import NormalizationReport

ModelT = TypeVar("ModelT", bound=BaseModel)
LOGGER = logging.getLogger(__name__)


def load_gold_samples(
    path: str | Path,
    *,
    documents: dict[str, str] | None = None,
    chapter_documents: Mapping[tuple[str, str], str] | None = None,
) -> list[GoldSample]:
    """Load Gold JSONL and optionally replay spans against canonical text.

    Legacy fixtures use one ``document_id -> text`` mapping.  M3 v0.1 spans
    are chapter-local, so callers validating those records must additionally
    provide ``(document_id, chapter_id) -> chapter text``.
    """

    samples = _load_jsonl(path, GoldSample)
    ids = [sample.question_id for sample in samples]
    if len(ids) != len(set(ids)):
        raise ValueError(f"{Path(path)}: duplicate question_id values")
    if documents is not None or chapter_documents is not None:
        for line_number, sample in enumerate(samples, start=1):
            try:
                _validate_sample_spans(
                    sample,
                    documents=documents,
                    chapter_documents=chapter_documents,
                )
            except ValueError as exc:
                raise ValueError(f"{Path(path)}:{line_number}: {exc}") from exc
    return samples


def write_normalized_gold(
    samples: Sequence[GoldSample],
    report: NormalizationReport,
    output_path: str | Path,
) -> None:
    """Atomically write only fully resolved normalized Gold without overwriting."""

    if report.stale or report.ambiguous:
        raise ValueError(
            "refusing to write normalized Gold with stale or ambiguous spans: "
            f"stale={report.stale}, ambiguous={report.ambiguous}"
        )
    _validate_formal_normalized_gold(samples)

    destination = Path(output_path)
    if destination.exists():
        raise FileExistsError(f"refusing to overwrite normalized Gold artifact: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{destination.name}.",
            suffix=".tmp",
            dir=destination.parent,
            delete=False,
        ) as stream:
            temporary_path = Path(stream.name)
            for sample in samples:
                encoded = json.dumps(
                    sample.model_dump(mode="json"),
                    ensure_ascii=False,
                    separators=(",", ":"),
                ).encode("utf-8")
                stream.write(encoded + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        if destination.exists():
            raise FileExistsError(f"refusing to overwrite normalized Gold artifact: {destination}")
        os.replace(temporary_path, destination)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def load_normalized_gold(
    path: str | Path,
    *,
    document: OpenStaxDocument | None = None,
) -> list[GoldSample]:
    """Load a single-version normalized Gold artifact and optionally replay it."""

    samples = _load_jsonl(path, GoldSample)
    if not samples:
        raise ValueError(f"{Path(path)}: normalized Gold artifact is empty")
    _validate_formal_normalized_gold(samples)
    versions = {sample.corpus_version for sample in samples}
    if len(versions) != 1:
        raise ValueError(f"{Path(path)}: normalized Gold must use exactly one corpus version")
    ids = [sample.question_id for sample in samples]
    if len(ids) != len(set(ids)):
        raise ValueError(f"{Path(path)}: duplicate question_id values")
    if document is not None:
        _validate_normalized_global_spans(samples, document)
    return samples


def load_run_results(path: str | Path) -> list[EvaluationRunResult]:
    """Load strict per-question run traces from JSONL."""

    results = _load_jsonl(path, EvaluationRunResult)
    ids = [result.run_id for result in results]
    if len(ids) != len(set(ids)):
        raise ValueError(f"{Path(path)}: duplicate run_id values")
    return results


def load_mappings(path: str | Path) -> GoldChunkMapping:
    """Load one JSON mapping artifact or a JSONL collection of question mappings."""

    source = Path(path)
    text = source.read_text(encoding="utf-8")
    if not text.strip():
        raise ValueError(f"{source}: mapping file is empty")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as json_error:
        records = _load_jsonl(source, QuestionChunkMapping)
        if not records:
            raise ValueError(f"{source}: mapping file is empty") from json_error
        first = records[0]
        return GoldChunkMapping(
            mapping_version=first.mapping_version,
            corpus_version=first.corpus_version,
            chunk_config_hash=first.chunk_config_hash,
            items=records,
        )
    if isinstance(payload, list):
        records = [QuestionChunkMapping.model_validate(item) for item in payload]
        if not records:
            raise ValueError(f"{source}: mapping file is empty")
        first = records[0]
        return GoldChunkMapping(
            mapping_version=first.mapping_version,
            corpus_version=first.corpus_version,
            chunk_config_hash=first.chunk_config_hash,
            items=records,
        )
    return GoldChunkMapping.model_validate(payload)


def append_jsonl_record(path: str | Path, model: BaseModel) -> None:
    """Append one fully encoded JSON record and durably flush the line.

    A record is encoded before opening the file, then written in one call.  The
    resume loader additionally protects against the unavoidable case where a
    process dies after only part of the final write reaches disk.
    """

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(
        model.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    with destination.open("a+b") as stream:
        stream.seek(0, os.SEEK_END)
        if stream.tell():
            stream.seek(-1, os.SEEK_END)
            if stream.read(1) != b"\n":
                stream.seek(0, os.SEEK_END)
                stream.write(b"\n")
        stream.seek(0, os.SEEK_END)
        stream.write(encoded + b"\n")
        stream.flush()
        os.fsync(stream.fileno())


def load_inprogress_run_results(
    path: str | Path,
    *,
    recovery_log: str | Path | None = None,
) -> list[EvaluationRunResult]:
    """Load a checkpoint, recording any recovered trailing partial record.

    A process can die after writing only part of the final JSONL record.  That
    incomplete record is safe to discard and retry, but the recovery must be
    visible to an audit trail rather than silently mutating the checkpoint.
    """

    source = Path(path)
    if not source.name.endswith(".inprogress"):
        raise ValueError("resume input must be an .inprogress file")
    if not source.exists():
        return []
    raw = source.read_bytes()
    lines = raw.splitlines(keepends=True)
    loaded: list[EvaluationRunResult] = []
    complete_bytes = 0
    for index, line in enumerate(lines, start=1):
        if not line.strip():
            complete_bytes += len(line)
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            if index != len(lines):
                raise ValueError(f"{source}:{index}: {exc}") from exc
            recovery = {
                "recovered_trailing_record": True,
                "line_number": index,
                "discarded_bytes": len(raw) - complete_bytes,
            }
            LOGGER.warning(
                "recovering incomplete trailing JSONL record: path=%s line=%s",
                source,
                index,
            )
            if recovery_log is not None:
                _write_recovery_log(recovery_log, recovery)
            source.write_bytes(raw[:complete_bytes])
            break
        try:
            loaded.append(EvaluationRunResult.model_validate(payload))
        except ValidationError as exc:
            raise ValueError(f"{source}:{index}: {exc}") from exc
        complete_bytes += len(line)
    ids = [result.run_id for result in loaded]
    if len(ids) != len(set(ids)):
        raise ValueError(f"{source}: duplicate run_id values")
    question_ids = [result.question_id for result in loaded]
    if len(question_ids) != len(set(question_ids)):
        raise ValueError(f"{source}: duplicate question_id values")
    return loaded


def _write_recovery_log(path: str | Path, record: dict[str, object]) -> None:
    """Write a small recovery marker atomically for later audit."""

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp")
    encoded = json.dumps(record, indent=2, ensure_ascii=False) + "\n"
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, destination)


def write_final_jsonl(inprogress_path: str | Path, final_path: str | Path) -> None:
    """Validate and atomically promote an ``.inprogress`` file to its final name."""

    source = Path(inprogress_path)
    destination = Path(final_path)
    if destination.exists():
        raise FileExistsError(f"refusing to overwrite completed run file: {destination}")
    if not source.name.endswith(".inprogress"):
        raise ValueError("source must be an .inprogress file")
    # Promotion is stricter than resume: a damaged trailing line may be
    # discarded while recovering, but it must never be silently promoted as a
    # completed evaluation.
    _load_jsonl(source, EvaluationRunResult)
    load_inprogress_run_results(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    os.replace(source, destination)


def _load_jsonl(path: str | Path, model: type[ModelT]) -> list[ModelT]:
    source = Path(path)
    loaded: list[ModelT] = []
    with source.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
                loaded.append(model.model_validate(payload))
            except (json.JSONDecodeError, ValidationError) as exc:
                raise ValueError(f"{source}:{line_number}: {exc}") from exc
    return loaded


def _validate_sample_spans(
    sample: GoldSample,
    *,
    documents: Mapping[str, str] | None,
    chapter_documents: Mapping[tuple[str, str], str] | None,
) -> None:
    spans = [
        span
        for evidence_set in sample.gold_core_evidence_sets
        for span in evidence_set
    ] + sample.partial_evidence
    for span in spans:
        if span.chapter_id is not None:
            if chapter_documents is None:
                raise ValueError(
                    f"{span.span_id} has chapter_id={span.chapter_id}; "
                    "chapter_documents are required for chapter-local validation"
                )
            document = chapter_documents.get((span.document_id, span.chapter_id))
            if document is None:
                raise ValueError(
                    f"{span.span_id} references unknown chapter_id={span.chapter_id} "
                    f"for document_id={span.document_id}"
                )
        elif documents is not None:
            document = documents.get(span.document_id)
        else:
            document = None
        if document is None:
            raise ValueError(
                f"{span.span_id} references unknown document_id {span.document_id}"
            )
        if span.char_end > len(document):
            raise ValueError(f"{span.span_id} exceeds canonical document text")
        actual = document[span.char_start : span.char_end]
        if actual != span.verbatim_text:
            raise ValueError(f"{span.span_id} does not match canonical document text")


def _all_spans(
    sample: GoldSample,
) -> tuple[tuple[GoldEvidenceSpan, ...], list[GoldEvidenceSpan]]:
    return (
        tuple(
            span
            for evidence_set in sample.gold_core_evidence_sets
            for span in evidence_set
        ),
        sample.partial_evidence,
    )


def _validate_formal_normalized_gold(samples: Sequence[GoldSample]) -> None:
    for sample in samples:
        if sample.schema_version != "0.2":
            raise ValueError(
                "formal normalized Gold requires schema 0.2; "
                f"sample {sample.question_id} has schema {sample.schema_version}"
            )
        if sample.source_corpus_version is None or sample.normalizer_version is None:
            raise ValueError(
                "formal normalized Gold requires source_corpus_version and normalizer_version; "
                f"sample {sample.question_id} has incomplete provenance"
            )
        core_spans, partial_spans = _all_spans(sample)
        for span in (*core_spans, *partial_spans):
            if (
                span.resolution_status is not SpanResolutionStatus.RESOLVED
                or span.corpus_char_start is None
                or span.corpus_char_end is None
            ):
                raise ValueError(
                    "formal normalized Gold requires every span to be resolved; "
                    f"span {span.span_id} is {span.resolution_status}"
                )


def _validate_normalized_global_spans(
    samples: Sequence[GoldSample], document: OpenStaxDocument
) -> None:
    for sample in samples:
        core_spans, partial_spans = _all_spans(sample)
        for span in (*core_spans, *partial_spans):
            if span.document_id != document.document_id:
                raise ValueError(
                    f"{span.span_id} references document_id {span.document_id}, "
                    f"not {document.document_id}"
                )
            assert span.corpus_char_start is not None
            assert span.corpus_char_end is not None
            if span.corpus_char_end > len(document.text):
                raise ValueError(f"{span.span_id} exceeds canonical corpus text")
            actual = document.text[span.corpus_char_start : span.corpus_char_end]
            if actual != span.verbatim_text:
                raise ValueError(
                    f"{span.span_id} does not replay against canonical corpus text"
                )
