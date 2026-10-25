"""Integrate reviewed Strong and Multi candidate CSVs into M3 Gold JSONL."""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from candidate_screening_common import SCHEMA_FIELDS
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
M3_ROOT = Path(__file__).resolve().parent
DEFAULT_STRONG = M3_ROOT / "candidate_pool_strong_v1_3_2.csv"
DEFAULT_MULTI = M3_ROOT / "candidate_pool_multi_v1_3_2.csv"
DEFAULT_SCHEMA = M3_ROOT / "gold_v0_1_3.schema.json"
DEFAULT_BLOCKS = (
    M3_ROOT / "openstax_parser_v1_3_2" / "m3_evidence" / "combined" / "evidence_source_blocks.jsonl"
)
DEFAULT_MANIFEST = DEFAULT_BLOCKS.with_name("corpus_manifest.json")
DEFAULT_CK12_BLOCKS = (
    M3_ROOT
    / "ck12_parser_v1_1_0"
    / "ck12_output_without_chapter_21"
    / "m3_adapter"
    / "evidence_source_blocks.jsonl"
)
DEFAULT_CK12_MANIFEST = DEFAULT_CK12_BLOCKS.with_name("corpus_manifest.json")
DEFAULT_OUTPUT_DIR = M3_ROOT / "final_v0_1_1"
ACCEPTED_DECISIONS = {"accept_single", "accept_multi"}
# The source manifest remains M2/parser provenance. These output values are the
# approved Gold/v2 contract metadata and are deliberately kept separate.
SOURCE_CORPUS_VERSION = "openstax-physics-combined-parser-1.3.2"
OUTPUT_GOLD_ANNOTATION_VERSION = "m3_gold_v0.1.3"
OUTPUT_CORPUS_VERSION = "2.0.0-dev.m4-structure-v2-main-3553825"
OUTPUT_PARSER_VERSION = "1.3.2"
RELEASE_EXCLUSIONS = {
    "sciq-validation-00752": (
        "The accepted evidence comes from an AP edition Chapter 9 figure annotation, "
        "associated with a block ID ending in _ch09_p0434_b002. This evidence block is "
        "unavailable in the M4 corpus."
    ),
    "sciq-train-01792": (
        "The accepted evidence comes from the CK-12 Problem Solving 1 subsection, "
        "associated with a block ID ending in _p0092_b800. The M4 corpus does not "
        "include this exercise subsection."
    ),
    "sciq-train-07669": (
        "The accepted evidence also comes from the CK-12 Problem Solving 1 subsection, "
        "associated with a block ID ending in _p0092_b800. The M4 corpus does not "
        "include this exercise subsection."
    ),
}
KNOWN_VERSION_TAG = re.compile(r"^(?P<prefix>.+)_pv1\.3\.2_(?P<suffix>ch\d+_p\d+_b\d+)$")


class IntegrationError(ValueError):
    """An accepted candidate cannot be safely converted to Gold."""


def parse_json_cell(value: str, field: str, question_id: str) -> Any:
    try:
        return json.loads(value or "null")
    except json.JSONDecodeError as exc:
        raise IntegrationError(f"{question_id}: invalid JSON in {field}: {exc.msg}") from exc


def parse_bool_cell(value: str, field: str, question_id: str) -> bool:
    normalized = value.strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise IntegrationError(f"{question_id}: {field} must be true or false")


def load_candidate_csv(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != SCHEMA_FIELDS:
            raise IntegrationError(f"{path}: header does not match SCHEMA_FIELDS")
        rows = []
        for row_number, row in enumerate(reader, start=2):
            rows.append({"source_file": str(path), "row_number": row_number, "row": row})
    return rows


def load_blocks(path: Path) -> dict[str, dict[str, Any]]:
    blocks: dict[str, dict[str, Any]] = {}
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            block = json.loads(line)
            block_id = block.get("block_id")
            if not block_id or block_id in blocks:
                raise IntegrationError(f"{path}:{line_number}: invalid or duplicate block_id")
            blocks[block_id] = block
    return blocks


def canonical_block_id(block_id: str, blocks: dict[str, dict[str, Any]]) -> str:
    """Resolve the parser-version-tagged candidate ID to the corpus ID."""
    canonical_matches = [
        item for item in blocks.values() if item.get("parser_block_id") == block_id
    ]
    if len(canonical_matches) == 1:
        return block_id
    if len(canonical_matches) > 1:
        raise IntegrationError(f"evidence block ID {block_id} has multiple canonical matches")
    block = blocks.get(block_id)
    if block is not None:
        return block.get("parser_block_id") or block_id
    match = KNOWN_VERSION_TAG.fullmatch(block_id)
    if match is None:
        raise IntegrationError(f"unknown evidence block ID {block_id}")
    candidate = f"{match.group('prefix')}_{match.group('suffix')}"
    matches = [
        item
        for item in blocks.values()
        if item.get("parser_block_id") == candidate or item.get("block_id") == candidate
    ]
    if len(matches) != 1:
        raise IntegrationError(
            f"evidence block ID {block_id} has {len(matches)} verified canonical matches"
        )
    return candidate


def canonical_block(block_id: str, blocks: dict[str, dict[str, Any]]) -> dict[str, Any]:
    canonical_id = canonical_block_id(block_id, blocks)
    for block in blocks.values():
        if block.get("parser_block_id") == canonical_id or block.get("block_id") == canonical_id:
            return block
    raise IntegrationError(f"missing canonical evidence block {canonical_id}")


def _int(value: Any, field: str, question_id: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise IntegrationError(f"{question_id}: {field} must be an integer") from exc


def validate_evidence(
    row: dict[str, str],
    blocks: dict[str, dict[str, Any]],
    manifest: dict[str, Any],
    corpus_sources: dict[tuple[str, str], tuple[dict[str, dict[str, Any]], dict[str, Any]]]
    | None = None,
) -> tuple[list[list[dict[str, Any]]], list[str]]:
    if corpus_sources is not None:
        source_key = (row["corpus_version"], row["parser_version"])
        try:
            blocks, manifest = corpus_sources[source_key]
        except KeyError as exc:
            raise IntegrationError(
                f"{row['question_id']}: no evidence corpus configured for {source_key}"
            ) from exc
    question_id = row["question_id"]
    core_sets = parse_json_cell(
        row["gold_core_evidence_sets"], "gold_core_evidence_sets", question_id
    )
    accepted_ids = parse_json_cell(
        row["accepted_evidence_ids"], "accepted_evidence_ids", question_id
    )
    if not isinstance(core_sets, list) or not all(isinstance(item, list) for item in core_sets):
        raise IntegrationError(f"{question_id}: gold_core_evidence_sets must be an array of arrays")
    if not isinstance(accepted_ids, list) or not all(
        isinstance(item, str) for item in accepted_ids
    ):
        raise IntegrationError(f"{question_id}: accepted_evidence_ids must be an array of strings")
    candidate_spans = [span for group in core_sets for span in group]
    if not accepted_ids:
        raise IntegrationError(f"{question_id}: accepted_evidence_ids is empty")
    selected_spans = []
    canonical_accepted_ids = []
    for block_id in accepted_ids:
        canonical_id = canonical_block_id(block_id, blocks)
        matches = [
            span
            for span in candidate_spans
            if canonical_block_id(str(span.get("block_id", "")), blocks) == canonical_id
        ]
        if len(matches) != 1:
            raise IntegrationError(
                f"{question_id}: accepted block {block_id} has {len(matches)} matching spans"
            )
        selected = dict(matches[0])
        selected["block_id"] = canonical_id
        selected_spans.append(selected)
        canonical_accepted_ids.append(canonical_id)

    decision = row["manual_review"]
    if decision == "accept_single":
        if len(canonical_accepted_ids) != 1:
            raise IntegrationError(f"{question_id}: accept_single requires exactly one span and ID")
        selected_spans[0]["sufficiency"] = "core_sufficient"
    elif decision == "accept_multi":
        if (
            len(canonical_accepted_ids) != 2
            or canonical_accepted_ids[0] == canonical_accepted_ids[1]
        ):
            raise IntegrationError(
                f"{question_id}: accept_multi requires two distinct spans and IDs"
            )
        for span in selected_spans:
            span["sufficiency"] = "joint_core"
        if selected_spans[0].get("document_id") != selected_spans[1].get("document_id"):
            raise IntegrationError(f"{question_id}: multi spans have different document IDs")
        if selected_spans[0].get("chapter_id") != selected_spans[1].get("chapter_id"):
            raise IntegrationError(f"{question_id}: multi spans have different chapter IDs")
    else:
        raise IntegrationError(f"{question_id}: unsupported accepted decision {decision}")

    expected_corpus = manifest.get("corpus_version")
    expected_parser = manifest.get("parser_version")
    if row["corpus_version"] != expected_corpus:
        raise IntegrationError(f"{question_id}: corpus_version does not match manifest")
    if row["parser_version"] != expected_parser:
        raise IntegrationError(f"{question_id}: parser_version does not match manifest")

    for span in selected_spans:
        block_id = span.get("block_id")
        block = canonical_block(str(block_id), blocks)
        for field in ("document_id", "chapter_id"):
            if str(span.get(field)) != str(block.get(field)):
                raise IntegrationError(f"{question_id}: {field} mismatch for {block_id}")
        for field in ("char_start", "char_end", "chapter_char_start", "chapter_char_end"):
            span_value = _int(span.get(field), field, question_id)
            if field in {"char_start", "char_end"} and "corpus_char_start" in block:
                # Existing OpenStax candidate spans store chapter-relative
                # char_start/char_end; corpus_char_* are global offsets.
                block_field = "chapter_" + field
            elif field in {"char_start", "char_end"} and field in block:
                # CK-12 adapter spans retain global char_start/char_end.
                block_field = field
            else:
                block_field = field
            block_value = _int(block.get(block_field), field, question_id)
            if span_value != block_value:
                raise IntegrationError(f"{question_id}: {field} mismatch for {block_id}")
        if span.get("verbatim_text") != block.get("text"):
            raise IntegrationError(f"{question_id}: verbatim_text mismatch for {block_id}")
        if _int(span["char_start"], "char_start", question_id) > _int(
            span["char_end"], "char_end", question_id
        ):
            raise IntegrationError(f"{question_id}: invalid character interval")
    return [selected_spans], canonical_accepted_ids


def normalize_accepted(
    row: dict[str, str],
    blocks: dict[str, dict[str, Any]],
    manifest: dict[str, Any],
    corpus_sources: dict[tuple[str, str], tuple[dict[str, dict[str, Any]], dict[str, Any]]]
    | None = None,
) -> dict[str, Any]:
    question_id = row["question_id"]
    core_sets, _accepted_ids = validate_evidence(row, blocks, manifest, corpus_sources)
    for index, span in enumerate(core_sets[0], start=1):
        span["span_id"] = f"gold:{question_id}:{index}"
        if row["parser_version"].startswith("ck12-"):
            # CK-12 source blocks expose global char_* offsets, while the Gold
            # contract uses chapter-relative offsets for exported evidence.
            span["char_start"] = span["chapter_char_start"]
            span["char_end"] = span["chapter_char_end"]
    partial = parse_json_cell(row["partial_evidence"], "partial_evidence", question_id)
    source = parse_json_cell(row["source"], "source", question_id)
    if not isinstance(partial, list) or not isinstance(source, dict):
        raise IntegrationError(f"{question_id}: invalid partial_evidence or source structure")
    is_source_corpus = row["corpus_version"] != SOURCE_CORPUS_VERSION
    return {
        "question_id": question_id,
        "source_split": row["source_split"],
        "question": row["question"],
        "gold_answer_text": row["gold_answer_text"],
        "answerable": parse_bool_cell(row["answerable"], "answerable", question_id),
        "gold_core_evidence_sets": core_sets,
        "partial_evidence": partial,
        "question_difficulty": row["question_difficulty"],
        "question_type": row["question_type"],
        "concept_group": row["concept_group"],
        "personalisation_eligibility": row["personalisation_eligibility"],
        "eligibility_reason": row["eligibility_reason"],
        "split": row["split"],
        "corpus_version": row["corpus_version"] if is_source_corpus else OUTPUT_CORPUS_VERSION,
        "parser_version": row["parser_version"] if is_source_corpus else OUTPUT_PARSER_VERSION,
        "gold_annotation_version": OUTPUT_GOLD_ANNOTATION_VERSION,
        "annotation_status": row["annotation_status"],
        "review_record_id": row["review_record_id"],
        "source": source,
    }


def _same_candidate(left: dict[str, str], right: dict[str, str]) -> bool:
    return left == right


def integrate(
    strong_path: Path = DEFAULT_STRONG,
    multi_path: Path = DEFAULT_MULTI,
    schema_path: Path = DEFAULT_SCHEMA,
    blocks_path: Path = DEFAULT_BLOCKS,
    manifest_path: Path = DEFAULT_MANIFEST,
    ck12_blocks_path: Path | None = DEFAULT_CK12_BLOCKS,
    ck12_manifest_path: Path | None = DEFAULT_CK12_MANIFEST,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, str]], dict[str, Any]]:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    blocks = load_blocks(blocks_path)
    corpus_sources = {(manifest["corpus_version"], manifest["parser_version"]): (blocks, manifest)}
    if ck12_blocks_path is not None or ck12_manifest_path is not None:
        if ck12_blocks_path is None or ck12_manifest_path is None:
            raise IntegrationError("CK-12 blocks and manifest must be provided together")
        ck12_blocks = load_blocks(ck12_blocks_path)
        ck12_manifest = json.loads(ck12_manifest_path.read_text(encoding="utf-8"))
        corpus_sources[(ck12_manifest["corpus_version"], ck12_manifest["parser_version"])] = (
            ck12_blocks,
            ck12_manifest,
        )
        blocks_for_summary = {**blocks, **ck12_blocks}
    else:
        blocks_for_summary = blocks
    envelopes = load_candidate_csv(strong_path) + load_candidate_csv(multi_path)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for envelope in envelopes:
        grouped[envelope["row"]["question_id"]].append(envelope)

    audit: list[dict[str, Any]] = []
    conflicts: list[dict[str, str]] = []
    records: list[dict[str, Any]] = []
    schema_failures = 0
    provenance_failures = 0
    duplicate_extra_count = 0
    conflict_question_ids: set[str] = set()
    canonicalized_block_count = 0
    unchanged_block_count = 0
    regenerated_span_count = 0

    for question_id, group in grouped.items():
        if question_id in RELEASE_EXCLUSIONS:
            for item in group:
                audit.append(
                    _audit_item(
                        item, "excluded", [f"release_exclusion: {RELEASE_EXCLUSIONS[question_id]}"]
                    )
                )
            continue
        duplicate = len(group) > 1
        if duplicate:
            duplicate_extra_count += len(group) - 1
            identical = all(_same_candidate(group[0]["row"], item["row"]) for item in group[1:])
            conflict_type = "duplicate_identical" if identical else "conflicting_duplicate"
            if not identical:
                conflict_question_ids.add(question_id)
            for item in group:
                conflicts.append(
                    {
                        "question_id": question_id,
                        "conflict_type": conflict_type,
                        "source_file": item["source_file"],
                        "row_number": str(item["row_number"]),
                        "manual_review": item["row"]["manual_review"],
                        "details": "duplicate records are identical"
                        if identical
                        else "duplicate records differ",
                    }
                )
        if question_id in conflict_question_ids:
            for item in group:
                audit.append(_audit_item(item, "conflict", ["conflicting_duplicate"]))
            continue

        item = group[0]
        row = item["row"]
        decision = row["manual_review"]
        if decision not in ACCEPTED_DECISIONS:
            audit.append(_audit_item(item, "excluded", [f"manual_review={decision or 'pending'}"]))
            continue
        if len(group) > 1:
            audit_status = "duplicate_deduplicated"
        else:
            audit_status = "accepted"
        try:
            record = normalize_accepted(row, blocks, manifest, corpus_sources)
            errors = sorted(error.message for error in validator.iter_errors(record))
            if errors:
                schema_failures += 1
                audit.append(_audit_item(item, "excluded", errors))
                continue
            records.append(record)
            original_ids = parse_json_cell(
                row["accepted_evidence_ids"], "accepted_evidence_ids", question_id
            )
            final_spans = [span for group in record["gold_core_evidence_sets"] for span in group]
            for original_id, span in zip(original_ids, final_spans, strict=True):
                if original_id == span["block_id"]:
                    unchanged_block_count += 1
                else:
                    canonicalized_block_count += 1
            regenerated_span_count += len(final_spans)
            audit.append(_audit_item(item, audit_status, []))
        except IntegrationError as exc:
            provenance_failures += 1
            audit.append(_audit_item(item, "excluded", [str(exc)]))

    stats = summarize(
        envelopes,
        grouped,
        audit,
        records,
        duplicate_extra_count,
        len(conflict_question_ids),
        schema_failures,
        provenance_failures,
        canonicalized_block_count,
        unchanged_block_count,
        regenerated_span_count,
        blocks_for_summary,
    )
    return records, audit, conflicts, stats


def _audit_item(item: dict[str, Any], status: str, errors: list[str]) -> dict[str, Any]:
    return {
        "source_file": item["source_file"],
        "row_number": item["row_number"],
        "question_id": item["row"]["question_id"],
        "manual_review": item["row"]["manual_review"],
        "status": status,
        "errors": errors,
        "candidate": item["row"],
    }


def summarize(
    envelopes: list[dict[str, Any]],
    grouped: dict[str, list[dict[str, Any]]],
    audit: list[dict[str, Any]],
    records: list[dict[str, Any]],
    duplicate_count: int,
    conflict_count: int,
    schema_failures: int,
    provenance_failures: int,
    canonicalized_block_count: int,
    unchanged_block_count: int,
    regenerated_span_count: int,
    blocks: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    decisions = Counter(item["row"]["manual_review"] or "pending" for item in envelopes)
    valid_records = records
    span_ids = [
        span["span_id"]
        for record in valid_records
        for group in record["gold_core_evidence_sets"]
        for span in group
    ]
    duplicate_span_id_count = len(span_ids) - len(set(span_ids))
    missing_final_block_count = sum(
        1
        for record in valid_records
        for group in record["gold_core_evidence_sets"]
        for span in group
        if not any(
            block.get("parser_block_id") == span["block_id"]
            or block.get("block_id") == span["block_id"]
            for block in blocks.values()
        )
    )
    return {
        "input_row_count_by_source": dict(
            Counter(Path(item["source_file"]).name for item in envelopes)
        ),
        "total_candidate_rows": len(envelopes),
        "unique_question_count": len(grouped),
        "reviewed_candidate_count": sum(
            decisions[d] for d in ACCEPTED_DECISIONS | {"partial", "reject"}
        ),
        "accepted_single_count": decisions["accept_single"],
        "accepted_multi_count": decisions["accept_multi"],
        "partial_count": decisions["partial"],
        "reject_count": decisions["reject"],
        "pending_count": decisions["pending"],
        "duplicate_count": duplicate_count,
        "conflict_count": conflict_count,
        "schema_validation_failures": schema_failures,
        "evidence_provenance_failures": provenance_failures,
        "canonicalized_block_id_count": canonicalized_block_count,
        "unchanged_block_id_count": unchanged_block_count,
        "regenerated_span_id_count": regenerated_span_count,
        "duplicate_span_id_count": duplicate_span_id_count,
        "missing_final_block_id_count": missing_final_block_count,
        "successfully_exported_gold_count": len(valid_records),
        "by_difficulty": dict(Counter(record["question_difficulty"] for record in valid_records)),
        "by_question_type": dict(Counter(record["question_type"] for record in valid_records)),
        "by_concept_group": dict(Counter(record["concept_group"] for record in valid_records)),
        "by_final_split": dict(Counter(record["split"] for record in valid_records)),
        "excluded_records": [
            {"question_id": item["question_id"], "status": item["status"], "errors": item["errors"]}
            for item in audit
            if item["status"] in {"excluded", "conflict"}
        ],
    }


def write_outputs(
    output_dir: Path,
    records: list[dict[str, Any]],
    audit: list[dict[str, Any]],
    conflicts: list[dict[str, str]],
    report: dict[str, Any],
    gold_filename: str = "gold_v0_1_1_integrated.jsonl",
    artifact_version: str = "v0_1_1",
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    report = dict(report)
    report["gold_annotation_version"] = OUTPUT_GOLD_ANNOTATION_VERSION
    report["gold_output_filename"] = gold_filename
    report["release_excluded_question_ids"] = sorted(RELEASE_EXCLUSIONS)

    def atomic_text(path: Path, text: str) -> None:
        fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
                stream.write(text)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp_name, path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    gold_text = "".join(
        json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n" for record in records
    )
    audit_text = "".join(
        json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n" for item in audit
    )
    atomic_text(output_dir / gold_filename, gold_text)
    atomic_text(output_dir / f"gold_review_audit_{artifact_version}.jsonl", audit_text)
    conflict_fields = [
        "question_id",
        "conflict_type",
        "source_file",
        "row_number",
        "manual_review",
        "details",
    ]
    conflict_buffer = tempfile.SpooledTemporaryFile(mode="w+", encoding="utf-8", newline="")
    try:
        writer = csv.DictWriter(conflict_buffer, fieldnames=conflict_fields)
        writer.writeheader()
        writer.writerows(conflicts)
        conflict_buffer.seek(0)
        atomic_text(
            output_dir / f"gold_integration_conflicts_{artifact_version}.csv",
            conflict_buffer.read(),
        )
    finally:
        conflict_buffer.close()
    atomic_text(
        output_dir / f"gold_validation_report_{artifact_version}.json",
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strong", type=Path, default=DEFAULT_STRONG)
    parser.add_argument("--multi", type=Path, default=DEFAULT_MULTI)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--blocks", type=Path, default=DEFAULT_BLOCKS)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--ck12-blocks", type=Path, default=DEFAULT_CK12_BLOCKS)
    parser.add_argument("--ck12-manifest", type=Path, default=DEFAULT_CK12_MANIFEST)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--gold-filename", default="gold_v0_1_3.jsonl")
    parser.add_argument("--artifact-version", default="v0_1_3")
    args = parser.parse_args()
    records, audit, conflicts, report = integrate(
        args.strong,
        args.multi,
        args.schema,
        args.blocks,
        args.manifest,
        args.ck12_blocks,
        args.ck12_manifest,
    )
    write_outputs(
        args.output_dir,
        records,
        audit,
        conflicts,
        report,
        args.gold_filename,
        args.artifact_version,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"output_dir={args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
