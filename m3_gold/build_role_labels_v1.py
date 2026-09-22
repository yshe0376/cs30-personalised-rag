"""Build M3 role labels from the reviewed Gold-to-source mappings.

The script intentionally does not retrieve new evidence or invent chunk IDs.
It resolves every Gold span through the official M4 gold-to-chunk mapping.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

ROLES = {
    "definition", "example", "comparison", "application", "derivation", "boundary",
}
DEFAULT_GOLD = Path(__file__).with_name("gold_v0_1_1.jsonl")
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parents[1] / "m3_role_labels"
DEFAULT_CHUNK_MAP = (
    Path(__file__).resolve().parents[1] / "eval_inputs" / "gold_to_chunk_mapping.json"
)

# This is an annotation map for the current reviewed 20-record M3 package.
# It is keyed by question rather than by text so that reruns are deterministic.
ROLE_BY_QUESTION = {
    "sciq-test-00770": "definition",
    "sciq-test-00536": "definition",
    "sciq-test-00646": "definition",
    "sciq-test-00246": "application",
    "sciq-test-00942": "comparison",
    "sciq-test-00335": "application",
    "sciq-test-00333": "application",
    "sciq-test-00465": "application",
    "sciq-test-00116": "example",
    "sciq-test-00709": "definition",
    "sciq-test-00401": "definition",
    "sciq-test-00974": "application",
    "sciq-test-00614": "application",
    "sciq-test-00315": "definition",
    "sciq-test-00540": "definition",
    "sciq-test-00620": "derivation",
    "sciq-test-00068": "definition",
    "sciq-test-00024": "definition",
    "sciq-test-00432": "application",
    "sciq-test-00955": "definition",
}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def read_chunk_map(path: Path) -> dict[str, list[str]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    entries = raw.get("entries") if isinstance(raw, dict) else raw
    if not isinstance(entries, list):
        raise ValueError("chunk map must contain an entries list")
    result: dict[str, list[str]] = {}
    for item in entries:
        metadata = item.get("source_metadata", {})
        block_id = metadata.get("resolved_block_id") or item.get("block_id")
        chunk_ids = item.get("matching_chunk_ids")
        if chunk_ids is None:
            chunk_ids = [match["chunk_id"] for match in item.get("chunk_matches", [])]
        if not block_id or not chunk_ids:
            raise ValueError(f"incomplete chunk map entry: {item!r}")
        result.setdefault(str(block_id), [])
        result[str(block_id)].extend(str(chunk_id) for chunk_id in chunk_ids)
    for block_id, chunk_ids in result.items():
        result[block_id] = sorted(set(chunk_ids))
    return result


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_labels(
    gold_path: Path,
    blocks_path: Path | None,
    output_path: Path,
    manifest_path: Path,
    chunk_map_path: Path,
) -> dict[str, Any]:
    gold = read_jsonl(gold_path)
    chunk_map = read_chunk_map(chunk_map_path)
    if blocks_path is not None and blocks_path.exists():
        available_blocks = {row["block_id"] for row in read_jsonl(blocks_path)}
    else:
        available_blocks = None
    labels: list[dict[str, str]] = []
    missing_blocks: list[str] = []
    missing_map: list[str] = []

    for record in gold:
        question_id = str(record["question_id"])
        role = ROLE_BY_QUESTION.get(question_id)
        if role not in ROLES:
            raise ValueError(f"no reviewed role assignment for {question_id}")
        for evidence_set in record.get("gold_core_evidence_sets", []):
            for span in evidence_set:
                block_id = str(span["block_id"])
                if available_blocks is not None and block_id not in available_blocks:
                    missing_blocks.append(block_id)
                    continue
                if block_id not in chunk_map:
                    missing_map.append(block_id)
                    continue
                for chunk_id in chunk_map[block_id]:
                    label = {
                        "schema_version": "role-labels-v1",
                        "question_id": question_id,
                        "chunk_id": chunk_id,
                        "role": role,
                    }
                    if not any(
                        existing["question_id"] == question_id
                        and existing["chunk_id"] == chunk_id
                        for existing in labels
                    ):
                        labels.append(label)

    if missing_blocks:
        raise ValueError(f"Gold references missing source blocks: {sorted(set(missing_blocks))}")
    if missing_map:
        raise ValueError(
            "official chunk map is incomplete for block IDs: "
            + ", ".join(sorted(set(missing_map)))
        )
    if len({(row["question_id"], row["chunk_id"]) for row in labels}) != len(labels):
        raise ValueError("duplicate (question_id, chunk_id) role label")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as stream:
        for row in labels:
            stream.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")

    corpus_version = str(gold[0].get("corpus_version", ""))
    parser_version = str(gold[0].get("parser_version", ""))
    if not corpus_version or not parser_version:
        raise ValueError("Gold must provide corpus_version and parser_version")
    manifest = {
        "schema_version": "0.1",
        "role_schema_version": "role-labels-v1",
        "role_taxonomy_version": "evidence-role-v1",
        "annotation_version": "m3-role-v1",
        "corpus_version": corpus_version,
        "parser_version": parser_version,
        "annotation_date": "2026-09-22",
        "annotator_ids": ["leahwang126"],
        "double_annotated": False,
        "labels_file": output_path.name,
        "labels_sha256": sha256(output_path),
        "declared_record_count": len(labels),
        "reference_id_field": "chunk_id",
        "reference_type": "chunk",
        "reference_universe": "gold_mapping",
        "role_field": "role",
        "record_schema_version_field": "schema_version",
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold", type=Path, default=DEFAULT_GOLD)
    parser.add_argument(
        "--blocks",
        type=Path,
        help="optional prepared evidence blocks file for an additional block-ID check",
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--chunk-map", type=Path, default=DEFAULT_CHUNK_MAP)
    args = parser.parse_args()
    manifest = build_labels(
        args.gold,
        args.blocks,
        args.output_dir / "role_labels_v1.jsonl",
        args.output_dir / "role_labels_v1_provenance_manifest.json",
        args.chunk_map,
    )
    print(f"labels={manifest['declared_record_count']}")
    print(f"questions={len(read_jsonl(args.gold))}")
    print(f"output_dir={args.output_dir}")
    print(f"chunk_map={args.chunk_map}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
