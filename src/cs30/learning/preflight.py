"""Offline retrieval-to-Topic rate measurement; never calls a generation API."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import UTC, datetime

from cs30.concept_check.topics import ChunkTopicResolver
from cs30.v2.config import ConceptCheckConfig
from cs30.v2.contracts import TopicResolutionStatus

from .assets import load_learning_assets
from .config import LearningConfig
from .retrieval import build_online_hybrid_retriever, restore_v2_retrieval_result


def run_offline_topic_preflight(config: LearningConfig) -> dict:
    assets = load_learning_assets(config)
    questions = json.loads(config.question_bank_path.read_text(encoding="utf-8"))
    if not isinstance(questions, list) or len(questions) < 10:
        raise ValueError("question bank must contain at least 10 free-text questions")
    if any(
        not isinstance(item, dict)
        or not isinstance(item.get("question"), str)
        or not item["question"].strip()
        for item in questions
    ):
        raise ValueError("each question-bank row needs a non-empty 'question'")

    retriever = build_online_hybrid_retriever(assets, config)
    resolver = ChunkTopicResolver(
        assets.topic_map,
        assets.topic_registry,
        ConceptCheckConfig(enabled=True, min_topic_support=0.5),
    )
    results = []
    statuses: Counter[str] = Counter()
    resolved_topics: Counter[str] = Counter()
    for index, item in enumerate(questions, start=1):
        question = item["question"].strip()
        legacy = retriever.retrieve(question, config.candidate_k)
        retrieval = restore_v2_retrieval_result(legacy, assets, config)
        resolution = resolver.resolve_retrieval_topic(retrieval)
        status = resolution.status.value
        statuses[status] += 1
        if resolution.status is TopicResolutionStatus.RESOLVED and resolution.topic_id:
            resolved_topics[resolution.topic_id] += 1
        results.append(
            {
                "question_id": str(item.get("question_id", f"q{index:02d}")),
                "question": question,
                "status": status,
                "topic_id": resolution.topic_id,
                "support": resolution.support,
                "error_code": resolution.error_code,
                "retrieved_chunk_ids": [hit.chunk_id for hit in retrieval.hits],
            }
        )

    resolved_count = sum(resolved_topics.values())
    question_count = len(results)
    rate = resolved_count / question_count
    report = {
        "schema_version": "1",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "corpus_version": assets.corpus.manifest.corpus_version,
        "corpus_hash": assets.corpus.manifest.corpus_hash,
        "manifest_hash": assets.corpus.manifest.manifest_hash,
        "topic_map_sha256": hashlib.sha256(config.topic_map_path.read_bytes()).hexdigest(),
        "topic_registry_version": assets.topic_registry.topic_registry_version,
        "index_sha256": hashlib.sha256(config.index_file_path.read_bytes()).hexdigest(),
        "question_bank_sha256": hashlib.sha256(config.question_bank_path.read_bytes()).hexdigest(),
        "embedding_model": config.dense_embedding_model,
        "embedding_revision": config.dense_embedding_revision,
        "retrieval": {
            "dense_weight": config.dense_weight,
            "bm25_weight": config.bm25_weight,
            "rrf_k": config.rrf_k,
            "candidate_k": config.candidate_k,
            "query_prompt_name": config.query_prompt_name,
            "query_instruction": config.query_instruction,
        },
        "summary": {
            "question_count": question_count,
            "resolved_count": resolved_count,
            "unique_topic_rate": rate,
            "status_counts": dict(sorted(statuses.items())),
        },
        "resolved_topic_ids": sorted(resolved_topics),
        "topic_counts": dict(sorted(resolved_topics.items())),
        "questions": results,
        "passed": question_count >= 10 and rate >= config.minimum_topic_resolution_rate,
        "note": (
            "Offline retrieval diagnostic only; it does not measure cited Topic "
            "or quiz success."
        ),
    }
    config.preflight_report_path.parent.mkdir(parents=True, exist_ok=True)
    config.preflight_report_path.write_text(
        json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=None)
    args = parser.parse_args()
    config = LearningConfig.load(args.config)
    report = run_offline_topic_preflight(config)
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"report: {config.preflight_report_path}")


if __name__ == "__main__":
    main()
