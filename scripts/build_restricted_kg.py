"""Build and audit review-required Restricted KG candidates."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cs30.v2.corpus import load_corpus_records  # noqa: E402
from cs30.v2.ids import canonical_json_bytes  # noqa: E402
from cs30.v2.restricted_kg import (  # noqa: E402
    audit_restricted_kg,
    extract_restricted_kg_candidates,
    write_restricted_kg,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extract evidence-bound Restricted KG candidates for human review."
    )
    parser.add_argument("corpus_dir", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--max-concepts", type=int, default=150)
    parser.add_argument("--max-relations", type=int, default=300)
    parser.add_argument("--kg-version", default="restricted-kg-v1")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    corpus = load_corpus_records(args.corpus_dir)
    graph = extract_restricted_kg_candidates(
        corpus,
        max_concepts=args.max_concepts,
        max_relations=args.max_relations,
        kg_version=args.kg_version,
    )
    report = audit_restricted_kg(graph, corpus)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_restricted_kg(graph, args.output_dir / "restricted_kg_candidates.json")
    (args.output_dir / "audit_report.json").write_bytes(
        canonical_json_bytes(report.model_dump(mode="json"))
    )
    with (args.output_dir / "review_queue.jsonl").open("w", encoding="utf-8") as handle:
        for concept in graph.concepts:
            if concept.status != "accepted":
                handle.write(
                    json.dumps(
                        {"item_type": "concept", **concept.model_dump(mode="json")},
                        ensure_ascii=False,
                        sort_keys=True,
                    )
                    + "\n"
                )
        for relation in graph.relations:
            if relation.status != "accepted":
                handle.write(
                    json.dumps(
                        {"item_type": "relation", **relation.model_dump(mode="json")},
                        ensure_ascii=False,
                        sort_keys=True,
                    )
                    + "\n"
                )

    print(
        f"Built {len(graph.concepts)} concept and {len(graph.relations)} relation "
        f"candidates in {args.output_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
