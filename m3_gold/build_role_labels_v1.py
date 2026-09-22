"""Build M3 role labels from the reviewed Gold-to-source mappings.

The script intentionally does not retrieve new evidence or invent chunk IDs.
It uses each Gold span's existing ``block_id`` as the current prepared-corpus
reference. When an official M4 chunk mapping becomes available, pass it with
``--chunk-map``; the map must contain one ``block_id`` -> ``chunk_id`` entry
for every Gold span.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

ROLES = {"definition", "example", "application", "derivation", "boundary"}
DEFAULT_GOLD = Path(__file__).with_name("gold_v0_1_1.jsonl")
DEFAULT_BLOCKS = (
    Path(__file__).resolve().parents[1]
    / "m3_unified_source_corpus"
    / "source_corpus"
    / "evidence_source_blocks.jsonl"
)
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parents[1] / "m3_role_labels"

# This is an annotation map for the current reviewed 20-record M3 package.
# It is keyed by question rather than by text so that reruns are deterministic.
ROLE_BY_QUESTION = {
    "sciq-test-00770": "definition",
    "sciq-test-00536": "definition",
    "sciq-test-00646": "definition",
    "sciq-test-00246": "application",
    "sciq-test-00942": "application",
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


def read_chunk_map(path: Path | None) -> dict[str, str]:
    if path is None:
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        return {str(key): str(value) for key, value in raw.items()}
    result = {}
    for item in raw:
        result[str(item["block_id"])] = str(item["chunk_id"])
    return result


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def build_labels(
    gold_path: Path,
    blocks_path: Path,
    output_path: Path,
    manifest_path: Path,
    chunk_map_path: Path | None,
) -> dict[str, Any]:
    gold = read_jsonl(gold_path)
    blocks = {row["block_id"]: row for row in read_jsonl(blocks_path)}
    chunk_map = read_chunk_map(chunk_map_path)
    labels: list[dict[str, str]] = []
    split_counts: Counter[str] = Counter()
    role_counts: Counter[str] = Counter()
    missing_blocks: list[str] = []
    missing_map: list[str] = []

    for record in gold:
        question_id = str(record["question_id"])
        role = ROLE_BY_QUESTION.get(question_id)
        if role not in ROLES:
            raise ValueError(f"no reviewed role assignment for {question_id}")
        split_counts[str(record.get("split", "unknown"))] += 1
        for evidence_set in record.get("gold_core_evidence_sets", []):
            for span in evidence_set:
                block_id = str(span["block_id"])
                if block_id not in blocks:
                    missing_blocks.append(block_id)
                    continue
                chunk_id = chunk_map.get(block_id, block_id)
                if chunk_map_path is not None and block_id not in chunk_map:
                    missing_map.append(block_id)
                    continue
                labels.append({
                    "schema_version": "role-labels-v1",
                    "question_id": question_id,
                    "chunk_id": chunk_id,
                    "role": role,
                })
                role_counts[role] += 1

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

    corpus_manifest = json.loads((blocks_path.parent / "corpus_manifest.json").read_text(encoding="utf-8"))
    manifest = {
        "schema_version": "1.0",
        "role_schema_version": "role-labels-v1",
        "role_taxonomy_version": "evidence-role-v1",
        "annotation_version": "m3-role-v1",
        "corpus_version": corpus_manifest["corpus_version"],
        "parser_version": corpus_manifest["parser_version"],
        "split_stats": dict(split_counts),
        "annotation_stats": {
            "question_count": len(gold),
            "label_count": len(labels),
            "role_counts": dict(role_counts),
        },
        "double_annotated": False,
        "scope": "current_m3_gold_v0.1.1; proposed split, not frozen formal evaluation split",
        "labels_file": output_path.name,
        "labels_sha256": sha256(output_path),
        "declared_record_count": len(labels),
        "question_id_field": "question_id",
        "reference_id_field": "chunk_id",
        "reference_type": "chunk",
        "role_field": "role",
        "record_schema_version_field": "schema_version",
        "chunk_id_source": (
            "official M4 block-to-chunk map"
            if chunk_map_path is not None
            else "current prepared-corpus block_id; replace with official M4 chunk map before final handoff"
        ),
        "source_files": {
            "gold": str(gold_path),
            "evidence_blocks": str(blocks_path),
        },
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold", type=Path, default=DEFAULT_GOLD)
    parser.add_argument("--blocks", type=Path, default=DEFAULT_BLOCKS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--chunk-map", type=Path)
    args = parser.parse_args()
    manifest = build_labels(
        args.gold,
        args.blocks,
        args.output_dir / "role_labels_v1.jsonl",
        args.output_dir / "role_labels_v1_provenance_manifest.json",
        args.chunk_map,
    )
    print(f"labels={manifest['declared_record_count']}")
    print(f"questions={manifest['annotation_stats']['question_count']}")
    print(f"output_dir={args.output_dir}")
    print(f"chunk_id_source={manifest['chunk_id_source']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
