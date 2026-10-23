"""Merge reviewed Topic map sidecars and bind them to an official corpus.

The input maps may have been produced against earlier corpus versions. This
builder carries assignments forward only when every chunk exists in the target
official corpus and every topic exists in the frozen registry.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from cs30.v2.contracts.models import TopicRegistry  # noqa: E402
from cs30.v2.corpus.records import load_corpus_records  # noqa: E402
from cs30.v2.topics import (  # noqa: E402
    ChunkTopicAssignment,
    ChunkTopicMap,
    validate_chunk_topic_map,
    write_chunk_topic_map,
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return "sha256:" + digest.hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus-dir", type=Path, required=True)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--source-map", type=Path, action="append", required=True)
    parser.add_argument("--output-map", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    corpus = load_corpus_records(args.corpus_dir)
    if corpus.manifest.mode != "official" or not corpus.manifest.reportable:
        raise SystemExit("target corpus must have an official, reportable manifest")

    registry = TopicRegistry.model_validate_json(args.registry.read_text(encoding="utf-8"))
    topic_ids = {topic.topic_id for topic in registry.topics}
    chunk_ids = set(corpus.chunk_ids)
    assignments_by_id: dict[str, ChunkTopicAssignment] = {}
    source_summaries: list[dict[str, object]] = []
    source_assignment_counts: Counter[str] = Counter()

    for source_path in args.source_map:
        source_map = ChunkTopicMap.model_validate_json(
            source_path.read_text(encoding="utf-8")
        )
        if source_map.topic_registry_version != registry.topic_registry_version:
            raise SystemExit(f"registry mismatch in source map: {source_path}")

        unknown_chunks = sorted(
            assignment.chunk_id
            for assignment in source_map.assignments
            if assignment.chunk_id not in chunk_ids
        )
        if unknown_chunks:
            raise SystemExit(
                f"{source_path} has chunk IDs absent from target corpus: {unknown_chunks[:10]}"
            )

        unknown_topics = sorted(
            {
                topic_id
                for assignment in source_map.assignments
                for topic_id in assignment.topic_ids
                if topic_id not in topic_ids
            }
        )
        if unknown_topics:
            raise SystemExit(
                f"{source_path} has topic IDs absent from registry: {unknown_topics[:10]}"
            )

        source_name = source_path.name
        source_assignment_counts[source_name] = len(source_map.assignments)
        source_summaries.append(
            {
                "file": source_name,
                "sha256": sha256_file(source_path),
                "source_corpus_version": source_map.corpus_version,
                "source_corpus_hash": source_map.corpus_hash,
                "assignment_count": len(source_map.assignments),
            }
        )
        for assignment in source_map.assignments:
            if assignment.chunk_id in assignments_by_id:
                raise SystemExit(
                    f"duplicate chunk assignment across source maps: {assignment.chunk_id}"
                )
            assignments_by_id[assignment.chunk_id] = assignment

    merged = ChunkTopicMap(
        corpus_version=corpus.manifest.corpus_version,
        corpus_hash=corpus.manifest.corpus_hash,
        topic_registry_version=registry.topic_registry_version,
        assignments=tuple(assignments_by_id.values()),
    )
    validate_chunk_topic_map(merged, corpus.manifest, corpus.chunk_ids)
    write_chunk_topic_map(merged, args.output_map)

    links = sum(len(assignment.topic_ids) for assignment in merged.assignments)
    textbook_assignments = Counter(
        corpus.chunks_by_id[assignment.chunk_id].textbook_id
        for assignment in merged.assignments
    )
    report = {
        "schema_version": "topic-map-release-build-report-v1",
        "status": "validated",
        "corpus": {
            "corpus_version": corpus.manifest.corpus_version,
            "corpus_hash": corpus.manifest.corpus_hash,
            "manifest_hash": corpus.manifest.manifest_hash,
            "record_count": corpus.manifest.record_count,
            "reportable": corpus.manifest.reportable,
        },
        "topic_registry_version": registry.topic_registry_version,
        "topic_registry_topic_count": len(topic_ids),
        "source_maps": source_summaries,
        "merged_map": {
            "file": args.output_map.name,
            "sha256": sha256_file(args.output_map),
            "assignment_count": len(merged.assignments),
            "topic_link_count": links,
            "assignments_by_textbook": dict(sorted(textbook_assignments.items())),
            "source_assignment_counts": dict(sorted(source_assignment_counts.items())),
        },
        "validation": "passed",
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
