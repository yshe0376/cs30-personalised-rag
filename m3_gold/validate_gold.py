"""Validate M3 Gold Evidence JSONL records."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CORPUS_ROOT = ROOT / "m3_unified_source_corpus" / "source_corpus"
LEGACY_CORPUS_ROOT = ROOT / "data" / "processed" / "openstax"
FALLBACK_CORPUS_ROOT = ROOT / "Openstax"
SCHEMA_PATH = Path(__file__).with_name("gold_v0_1.schema.json")
OPTION_IDS = ("A", "B", "C", "D")
SOURCE_SPLITS = {"train", "validation", "test"}
DIFFICULTIES = {"easy", "medium", "hard", "pending"}
QUESTION_TYPES = {
    "definition",
    "causal",
    "comparison",
    "calculation",
    "application",
    "identification",
    "other",
    "pending",
}
ELIGIBILITY = {"full", "endpoint_only", "none", "pending"}
SPLITS = {"proposed_dev", "proposed_test", "dev", "test", "holdout", "pending"}
STATUSES = {"draft", "m3_initial", "reviewed", "disputed", "unresolved"}
ALLOWED_EVIDENCE_CONTENT_TYPES = {
    "body",
    "equation",
    "example",
    "figure_caption",
    "glossary",
    "table",
}
SUFFICIENCY = {
    "core_sufficient",
    "joint_core",
    "alternative_sufficient",
    "partial",
}
REQUIRED_FIELDS = {
    "question_id",
    "source_split",
    "question",
    "options",
    "gold_answer",
    "gold_answer_text",
    "answerable",
    "gold_core_evidence_sets",
    "partial_evidence",
    "question_difficulty",
    "question_type",
    "concept_group",
    "personalisation_eligibility",
    "eligibility_reason",
    "split",
    "corpus_version",
    "parser_version",
    "gold_annotation_version",
    "annotation_status",
    "review_record_id",
    "source",
}


class ValidationError(Exception):
    pass


def load_schema() -> dict[str, Any] | None:
    if not SCHEMA_PATH.exists():
        return None
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def validate_schema_if_available(record: Any, schema: dict[str, Any] | None) -> None:
    if schema is None:
        return
    try:
        import jsonschema
    except ImportError:
        return
    try:
        jsonschema.validate(instance=record, schema=schema)
    except jsonschema.ValidationError as exc:
        raise ValidationError(str(exc)) from exc


def load_gold_samples(
    gold_path: Path | str, documents: dict[str, str] | None = None
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with Path(gold_path).open(encoding="utf-8") as input_file:
        for line_no, line in enumerate(input_file, start=1):
            if not line.strip():
                continue
            record = json.loads(line)
            if documents is not None:
                for evidence_set in record.get("gold_core_evidence_sets", []):
                    for span in evidence_set:
                        document_text = documents[span["document_id"]]
                        actual = document_text[span["char_start"] : span["char_end"]]
                        require(
                            actual == span["verbatim_text"],
                            f"line {line_no}: loader span replay failed",
                        )
            records.append(record)
    return records


def load_documents(corpus_root: Path) -> dict[tuple[str, str], dict[str, Any]]:
    if not corpus_root.exists():
        raise ValidationError(
            f"corpus not found: {corpus_root}. Pass --corpus-root or set "
            "CS30_OPENSTAX_ROOT."
        )

    documents: dict[tuple[str, str], dict[str, Any]] = {}

    unified_path = corpus_root / "openstax_document.json"
    if unified_path.exists():
        document = json.loads(unified_path.read_text(encoding="utf-8"))
        block_index = {block["block_id"]: block for block in document.get("blocks", [])}
        manifest_path = corpus_root / "corpus_manifest.json"
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            document["corpus_version"] = manifest.get("corpus_version")
        document["block_index"] = block_index
        documents[(document["document_id"], "__unified__")] = document
        return documents

    for path in corpus_root.rglob("openstax_document.json"):
        document = json.loads(path.read_text(encoding="utf-8"))
        for chapter in document.get("chapters", []):
            documents[(document["document_id"], str(chapter["chapter_id"]))] = document
    if not documents:
        raise ValidationError(
            f"corpus not found: no openstax_document.json under {corpus_root}"
        )
    return documents


def default_corpus_root() -> Path:
    env_value = os.environ.get("CS30_OPENSTAX_ROOT")
    if env_value:
        return Path(env_value)
    if DEFAULT_CORPUS_ROOT.exists():
        return DEFAULT_CORPUS_ROOT
    if LEGACY_CORPUS_ROOT.exists():
        return LEGACY_CORPUS_ROOT
    if FALLBACK_CORPUS_ROOT.exists():
        return FALLBACK_CORPUS_ROOT
    return DEFAULT_CORPUS_ROOT


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def validate_option(option_id: str, option: Any) -> None:
    require(isinstance(option, dict), f"options.{option_id} must be an object")
    require(isinstance(option.get("text"), str), f"options.{option_id}.text missing")
    require(
        isinstance(option.get("source_field"), str),
        f"options.{option_id}.source_field missing",
    )


def validate_span(
    span: Any, documents: dict[tuple[str, str], dict[str, Any]], location: str
) -> None:
    require(isinstance(span, dict), f"{location} must be an object")
    for key in (
        "span_id",
        "block_id",
        "content_type",
        "document_id",
        "chapter_id",
        "char_start",
        "char_end",
        "verbatim_text",
        "sufficiency",
        "annotation_note",
    ):
        require(key in span, f"{location}.{key} missing")

    require(span["sufficiency"] in SUFFICIENCY, f"{location}.sufficiency invalid")
    require(isinstance(span["block_id"], str), f"{location}.block_id must be str")
    require(
        span["content_type"] in ALLOWED_EVIDENCE_CONTENT_TYPES,
        f"{location}.content_type is not allowed: {span['content_type']}",
    )
    require(isinstance(span["char_start"], int), f"{location}.char_start must be int")
    require(isinstance(span["char_end"], int), f"{location}.char_end must be int")
    require(span["char_start"] < span["char_end"], f"{location} has empty span")

    document_id = span["document_id"]
    document_key = (document_id, "__unified__")
    if document_key not in documents:
        document_key = (document_id, str(span["chapter_id"]))
    require(
        document_key in documents,
        f"{location}.document_id/chapter_id not found: {document_key}",
    )
    document = documents[document_key]
    block = document.get("block_index", {}).get(span["block_id"])
    if block is not None:
        require(
            str(block["chapter_id"]) == str(span["chapter_id"]),
            f"{location}.chapter_id does not match block_id",
        )
        require(
            block["content_type"] == span["content_type"],
            f"{location}.content_type does not match block_id",
        )
        require(
            block["char_start"]
            <= span["char_start"]
            <= span["char_end"]
            <= block["char_end"],
            f"{location}.span is not contained in block_id",
        )
    text = document["text"]
    require(span["char_end"] <= len(text), f"{location}.char_end beyond document")
    actual = text[span["char_start"] : span["char_end"]]
    require(
        actual == span["verbatim_text"],
        f"{location}.verbatim_text does not match document slice",
    )


def validate_record(
    record: Any, documents: dict[tuple[str, str], dict[str, Any]], line_no: int
) -> None:
    require(isinstance(record, dict), f"line {line_no}: record must be an object")
    missing = sorted(REQUIRED_FIELDS - set(record))
    require(not missing, f"line {line_no}: missing fields: {', '.join(missing)}")

    require(record["source_split"] in SOURCE_SPLITS, f"line {line_no}: bad source_split")
    require(record["gold_answer"] in OPTION_IDS, f"line {line_no}: bad gold_answer")
    require(
        record["question_difficulty"] in DIFFICULTIES,
        f"line {line_no}: bad question_difficulty",
    )
    require(record["question_type"] in QUESTION_TYPES, f"line {line_no}: bad question_type")
    require(
        record["personalisation_eligibility"] in ELIGIBILITY,
        f"line {line_no}: bad personalisation_eligibility",
    )
    require(record["split"] in SPLITS, f"line {line_no}: bad split")
    require(record["annotation_status"] in STATUSES, f"line {line_no}: bad status")

    options = record["options"]
    require(isinstance(options, dict), f"line {line_no}: options must be object")
    require(set(options) == set(OPTION_IDS), f"line {line_no}: options must be A-D")
    for option_id in OPTION_IDS:
        validate_option(option_id, options[option_id])

    answer_text = options[record["gold_answer"]]["text"]
    require(
        answer_text == record["gold_answer_text"],
        f"line {line_no}: gold_answer_text does not match selected option",
    )

    evidence_sets = record["gold_core_evidence_sets"]
    require(isinstance(evidence_sets, list), f"line {line_no}: evidence sets must be list")
    if record["answerable"]:
        require(evidence_sets, f"line {line_no}: answerable record has no core evidence")
    for set_index, evidence_set in enumerate(evidence_sets):
        require(isinstance(evidence_set, list), f"line {line_no}: evidence set not list")
        require(evidence_set, f"line {line_no}: empty evidence set")
        for span_index, span in enumerate(evidence_set):
            validate_span(
                span,
                documents,
                f"line {line_no}: gold_core_evidence_sets[{set_index}][{span_index}]",
            )
            require(
                span["sufficiency"] != "partial",
                f"line {line_no}: partial span inside gold_core_evidence_sets",
            )

    partial = record["partial_evidence"]
    require(isinstance(partial, list), f"line {line_no}: partial_evidence must be list")
    for span_index, span in enumerate(partial):
        validate_span(span, documents, f"line {line_no}: partial_evidence[{span_index}]")
        require(
            span["sufficiency"] == "partial",
            f"line {line_no}: partial_evidence span must have sufficiency=partial",
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("gold_path", type=Path)
    parser.add_argument(
        "--corpus-root",
        type=Path,
        default=default_corpus_root(),
        help=(
            "Directory containing parsed OpenStax openstax_document.json files. "
            "Defaults to data/processed/openstax, with ./Openstax as a local "
            "fallback."
        ),
    )
    args = parser.parse_args()

    input_path = args.gold_path
    count = 0

    try:
        documents = load_documents(args.corpus_root)
    except ValidationError as exc:
        print(f"FAIL {input_path}: {exc}", file=sys.stderr)
        return 1

    schema = load_schema()
    with input_path.open(encoding="utf-8") as input_file:
        for line_no, line in enumerate(input_file, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
                validate_schema_if_available(record, schema)
                validate_record(record, documents, line_no)
            except (json.JSONDecodeError, KeyError, TypeError, ValidationError) as exc:
                print(f"FAIL {input_path}:{line_no}: {exc}", file=sys.stderr)
                return 1
            count += 1

    print(f"OK {input_path}: {count} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
