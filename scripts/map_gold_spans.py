"""Map M3 gold spans to the stable chunk IDs of one frozen M4 corpus."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from cs30.chunking import load_retrieval_corpus  # noqa: E402
from cs30.chunking.gold_mapping import (  # noqa: E402
    build_evaluation_mapping,
    load_normalized_gold_spans,
    map_gold_spans_to_chunks,
    matching_rule,
    verify_mapping_identity,
)
from cs30.contracts import OpenStaxDocument  # noqa: E402
from cs30.evaluation import load_prepared_corpus  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold", required=True, type=Path)
    parser.add_argument("--corpus-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument(
        "--prepared-corpus-dir",
        required=True,
        type=Path,
        help=(
            "M1 prepared corpus directory containing openstax_document.json, "
            "corpus_manifest.json and evidence_source_blocks.jsonl."
        ),
    )
    parser.add_argument(
        "--expected-mapping",
        type=Path,
        help="Optional prior mapping; fail if its identity changed.",
    )
    parser.add_argument(
        "--allow-partial",
        action="store_true",
        help="Diagnostic only: emit partial mappings instead of failing.",
    )
    return parser.parse_args()


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _source_content_types(
    entry: dict[str, object], documents: list[OpenStaxDocument]
) -> list[str]:
    document_id = str(entry.get("document_id", ""))
    chapter_id = str(entry.get("chapter_id", ""))
    start = entry.get("char_start")
    end = entry.get("char_end")
    if not isinstance(start, int) or not isinstance(end, int):
        return []
    for document in documents:
        if document.document_id != document_id:
            continue
        return sorted(
            {
                block.content_type.value
                for block in document.blocks
                if block.chapter_id == chapter_id
                and max(start, block.char_start) < min(end, block.char_end)
            }
        )
    return []


def _partial_delivery_manifest(
    mapping: dict[str, object],
    evaluation_mapping: dict[str, object],
    documents: list[OpenStaxDocument],
) -> dict[str, object]:
    entries = mapping["entries"]
    if not isinstance(entries, list):
        raise ValueError("detailed mapping entries must be a list")
    included_question_ids = {
        str(item["question_id"])
        for item in evaluation_mapping["items"]
        if isinstance(item, dict)
    }
    by_question: dict[str, list[dict[str, object]]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("detailed mapping entry must be an object")
        question_id = str(entry.get("question_id", ""))
        by_question.setdefault(question_id, []).append(entry)

    excluded_questions: list[dict[str, object]] = []
    for question_id, question_entries in sorted(by_question.items()):
        if question_id in included_question_ids:
            continue
        content_types = sorted(
            {
                content_type
                for entry in question_entries
                for content_type in _source_content_types(entry, documents)
            }
        )
        if content_types:
            reason = (
                "Gold evidence uses source content excluded by the fixed corpus "
                "filter: " + ", ".join(content_types)
            )
        else:
            reason = "No Gold span is fully covered by the fixed corpus"
        excluded_questions.append(
            {
                "question_id": question_id,
                "gold_span_ids": sorted(
                    str(entry["gold_span_id"]) for entry in question_entries
                ),
                "coverage_statuses": sorted(
                    {str(entry.get("coverage_status", "unknown")) for entry in question_entries}
                ),
                "source_content_types": content_types,
                "reason": reason,
            }
        )

    evaluation_items = evaluation_mapping["items"]
    evaluation_span_count = sum(
        len(item["spans"]) for item in evaluation_items if isinstance(item, dict)
    )
    return {
        "status": (
            "partial_evaluation_mapping"
            if excluded_questions
            else "complete_evaluation_mapping"
        ),
        "detailed_question_count": len(by_question),
        "detailed_span_count": len(entries),
        "evaluation_question_count": len(evaluation_items),
        "evaluation_span_count": evaluation_span_count,
        "excluded_question_count": len(excluded_questions),
        "excluded_questions": excluded_questions,
        "m1_exclusion_reason": "mapping_missing",
    }


def main() -> None:
    args = parse_args()
    manifest_path = args.corpus_dir / "manifest.json"
    records_path = args.corpus_dir / "records.jsonl"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if _sha256(records_path.read_bytes()) != manifest.get("corpus_id"):
        raise ValueError("records.jsonl does not match manifest corpus_id")
    if not manifest.get("chunk_config_id"):
        raise ValueError("manifest has no chunk_config_id; rebuild with the W5 exporter")

    prepared_corpus = load_prepared_corpus(args.prepared_corpus_dir)
    corpus_version = prepared_corpus.corpus_version
    documents = [prepared_corpus.document]
    gold_spans, gold_corpus_version = load_normalized_gold_spans(args.gold)
    if gold_corpus_version != corpus_version:
        raise ValueError("normalized Gold corpus_version does not match source manifest")
    mapping = map_gold_spans_to_chunks(
        gold_spans,
        load_retrieval_corpus(records_path),
        corpus_id=manifest["corpus_id"],
        chunk_config_id=manifest["chunk_config_id"],
        documents=documents,
        evidence_block_ids=sorted(prepared_corpus.evidence_blocks_by_id),
        require_full_coverage=not args.allow_partial,
    )
    if args.expected_mapping:
        expected = json.loads(args.expected_mapping.read_text(encoding="utf-8"))
        verify_mapping_identity(expected, mapping)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(args.output_dir / "gold_to_chunk_mapping.json", mapping)
    _write_json(args.output_dir / "matching_rule.json", matching_rule())
    incomplete = mapping["incomplete_gold_span_ids"]
    evaluation_mapping = build_evaluation_mapping(
        mapping,
        corpus_version=corpus_version,
    )
    _write_json(args.output_dir / "evaluation_mapping_v0_1.json", evaluation_mapping)
    delivery_manifest = _partial_delivery_manifest(
        mapping,
        evaluation_mapping,
        documents,
    )
    delivery_manifest["source_gold_annotation_version"] = "m3_gold_v0.1.1"
    delivery_manifest["corpus_version"] = corpus_version
    delivery_manifest["chunk_config_hash"] = manifest["chunk_config_id"]
    delivery_manifest["mapping_version"] = evaluation_mapping["mapping_version"]
    delivery_manifest["evidence_source_block_validation"] = mapping[
        "evidence_source_block_validation"
    ]
    _write_json(args.output_dir / "delivery_manifest.json", delivery_manifest)
    if incomplete:
        _write_json(
            args.output_dir / "alignment_issues.json",
            {
                "status": "partial_delivery",
                "reason": "normalized Gold spans are excluded by the fixed corpus filter",
                "incomplete_gold_span_ids": incomplete,
                "excluded_questions": delivery_manifest["excluded_questions"],
                "m1_disposition": (
                    "Questions without a covered span are omitted from the compatibility "
                    "mapping and counted as mapping_missing."
                ),
            },
        )
    print(
        f"Mapped {mapping['gold_span_count']} gold spans to corpus "
        f"{mapping['corpus_id']} as {mapping['mapping_id']}; "
        f"incomplete={len(incomplete)}."
    )


if __name__ == "__main__":
    main()
