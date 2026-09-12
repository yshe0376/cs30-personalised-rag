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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold", required=True, type=Path)
    parser.add_argument("--corpus-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument(
        "--source-corpus-manifest",
        required=True,
        type=Path,
        help="M1 prepared corpus_manifest.json that binds normalized Gold coordinates.",
    )
    parser.add_argument("--document", action="append", type=Path, default=[])
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


def main() -> None:
    args = parse_args()
    manifest_path = args.corpus_dir / "manifest.json"
    records_path = args.corpus_dir / "records.jsonl"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if _sha256(records_path.read_bytes()) != manifest.get("corpus_id"):
        raise ValueError("records.jsonl does not match manifest corpus_id")
    if not manifest.get("chunk_config_id"):
        raise ValueError("manifest has no chunk_config_id; rebuild with the W5 exporter")

    source_manifest = json.loads(args.source_corpus_manifest.read_text(encoding="utf-8"))
    corpus_version = source_manifest.get("corpus_version")
    if not isinstance(corpus_version, str) or not corpus_version:
        raise ValueError("source corpus manifest has no corpus_version")

    documents = [
        OpenStaxDocument.model_validate_json(path.read_text(encoding="utf-8"))
        for path in sorted(args.document)
    ]
    gold_spans, gold_corpus_version = load_normalized_gold_spans(args.gold)
    if gold_corpus_version != corpus_version:
        raise ValueError("normalized Gold corpus_version does not match source manifest")
    mapping = map_gold_spans_to_chunks(
        gold_spans,
        load_retrieval_corpus(records_path),
        corpus_id=manifest["corpus_id"],
        chunk_config_id=manifest["chunk_config_id"],
        documents=documents if documents else None,
        require_full_coverage=not args.allow_partial,
    )
    if args.expected_mapping:
        expected = json.loads(args.expected_mapping.read_text(encoding="utf-8"))
        verify_mapping_identity(expected, mapping)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(args.output_dir / "gold_to_chunk_mapping.json", mapping)
    _write_json(args.output_dir / "matching_rule.json", matching_rule())
    incomplete = mapping["incomplete_gold_span_ids"]
    if incomplete:
        _write_json(
            args.output_dir / "alignment_issues.json",
            {
                "status": "blocked",
                "reason": "normalized Gold spans are excluded by the fixed corpus filter",
                "incomplete_gold_span_ids": incomplete,
                "required_action": (
                    "M3 must provide reviewed evidence inside the fixed corpus filter, or the "
                    "team must approve and version a corpus-filter change."
                ),
            },
        )
    else:
        evaluation_mapping = build_evaluation_mapping(
            mapping,
            corpus_version=corpus_version,
        )
        _write_json(args.output_dir / "evaluation_mapping_v0_1.json", evaluation_mapping)
    print(
        f"Mapped {mapping['gold_span_count']} gold spans to corpus "
        f"{mapping['corpus_id']} as {mapping['mapping_id']}; "
        f"incomplete={len(incomplete)}."
    )


if __name__ == "__main__":
    main()
