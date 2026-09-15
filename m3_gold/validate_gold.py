"""Validate the M3 Gold v0.1.1 JSONL handoff with the shared evaluation loader."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

SCHEMA_PATH = Path(__file__).with_name("gold_v0_1_1.schema.json")


def _load_schema() -> dict[str, Any] | None:
    if not SCHEMA_PATH.exists():
        return None
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _validate_schema_if_available(record: Any, schema: dict[str, Any] | None) -> None:
    if schema is None:
        return
    try:
        import jsonschema
    except ImportError:
        return
    jsonschema.validate(instance=record, schema=schema)


def _validate_json_schema(path: Path) -> int:
    schema = _load_schema()
    count = 0
    with path.open(encoding="utf-8") as stream:
        for line_no, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                _validate_schema_if_available(json.loads(line), schema)
            except (json.JSONDecodeError, ValueError) as exc:
                raise ValueError(f"{path}:{line_no}: {exc}") from exc
            count += 1
    return count


def _chapter_documents(corpus: Any) -> dict[tuple[str, str], str]:
    document = corpus.document
    return {
        (document.document_id, chapter.chapter_id): document.text[
            chapter.char_start : chapter.char_end
        ]
        for chapter in document.chapters
    }


def _load_with_prepared_corpus(gold_path: Path, prepared_root: Path) -> Counter[str]:
    from cs30.evaluation import load_gold_samples, load_prepared_corpus
    from cs30.evaluation.span_resolution import resolve_span_to_corpus

    corpus = load_prepared_corpus(prepared_root)
    samples = load_gold_samples(
        gold_path,
        chapter_documents=_chapter_documents(corpus),
    )

    counts: Counter[str] = Counter()
    missing_block_ids: list[str] = []
    unresolved: list[str] = []
    for sample in samples:
        spans = [
            span
            for evidence_set in sample.gold_core_evidence_sets
            for span in evidence_set
        ] + sample.partial_evidence
        for span in spans:
            resolution = resolve_span_to_corpus(span, corpus)
            counts[resolution.status.value] += 1
            if resolution.resolved_block_id not in corpus.evidence_blocks_by_id:
                missing_block_ids.append(span.span_id)
            if resolution.status.value != "resolved":
                unresolved.append(f"{sample.question_id}:{span.span_id}:{resolution.message}")

    if missing_block_ids:
        shown = ", ".join(missing_block_ids[:5])
        raise ValueError(f"resolved block_id missing from evidence blocks: {shown}")
    if unresolved:
        shown = "; ".join(unresolved[:5])
        raise ValueError(f"unresolved spans: {shown}")
    return counts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("gold_path", type=Path)
    parser.add_argument(
        "--prepared-corpus-root",
        type=Path,
        help=(
            "Optional shared M4 prepared corpus directory containing "
            "openstax_document.json, corpus_manifest.json, and "
            "evidence_source_blocks.jsonl."
        ),
    )
    args = parser.parse_args()

    try:
        from cs30.evaluation import load_gold_samples

        count = _validate_json_schema(args.gold_path)
        if args.prepared_corpus_root is None:
            load_gold_samples(args.gold_path)
            resolution_counts: Counter[str] | None = None
        else:
            resolution_counts = _load_with_prepared_corpus(
                args.gold_path,
                args.prepared_corpus_root,
            )
    except Exception as exc:
        print(f"FAIL {args.gold_path}: {exc}", file=sys.stderr)
        return 1

    if resolution_counts is None:
        print(f"OK {args.gold_path}: {count} records")
    else:
        print(
            f"OK {args.gold_path}: {count} records; "
            f"resolved={resolution_counts['resolved']} "
            f"stale={resolution_counts['stale']} "
            f"ambiguous={resolution_counts['ambiguous']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
