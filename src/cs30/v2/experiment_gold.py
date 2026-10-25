"""Explicit M3-to-V2 conversion and exact, corpus-bound evidence verification."""

from __future__ import annotations

import json
from pathlib import Path

from cs30.chunking.v2_span_resolver import resolve_evidence_span
from cs30.evaluation.models import GoldSample
from cs30.v2.contracts import (
    EvidenceSpan,
    EvidenceSpanBinding,
    GoldQuestion,
    SpanResolutionStatus,
)
from cs30.v2.corpus import LoadedCorpus, load_corpus_records
from cs30.v2.io import read_jsonl, sha256_bytes


def bind_span(span: EvidenceSpan, corpus: LoadedCorpus) -> EvidenceSpanBinding:
    """Require the shared M4 resolver to produce one current-corpus binding."""

    binding = resolve_evidence_span(span, corpus)
    if binding.resolution_status is not SpanResolutionStatus.RESOLVED:
        raise ValueError(
            f"Gold span {span.span_id!r} has no unique exact locations "
            f"({binding.resolution_status.value}); obtain a resolved M4 anchor "
            "instead of guessing"
        )
    return binding


def bind_questions(gold: dict[str, GoldQuestion], corpus: LoadedCorpus) -> list[dict]:
    rows = []
    for question in gold.values():
        items = [e for group in question.gold_core_evidence_sets for e in group]
        items += list(question.partial_evidence)
        for item in items:
            binding = bind_span(item.span, corpus)
            rows.append(
                {"question_id": question.question_id, "binding": binding.model_dump(mode="json")}
            )
    return rows


def convert_m3_gold(
    source: Path,
    corpus_dir: Path,
    output_dir: Path,
    *,
    source_schema: str = "0.1",
    split_mapping: dict[str, str] | None = None,
    split_map_path: Path | None = None,
) -> dict:
    """Convert only by explicit request, preserving reference answers and annotations."""
    if output_dir.exists() or source_schema not in {"0.1", "0.2"}:
        raise ValueError("conversion needs a new output and supported explicit M3 source schema")
    if split_mapping is not None and split_map_path is not None:
        raise ValueError("provide split_mapping or split_map_path, not both")
    split_bytes = split_map_path.read_bytes() if split_map_path else None
    if split_bytes is not None:

        def unique_pairs(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError(f"duplicate split-map question/label: {key}")
                result[key] = value
            return result

        split_mapping = json.loads(split_bytes, object_pairs_hook=unique_pairs)
    if split_mapping is not None and not isinstance(split_mapping, dict):
        raise ValueError("split map must be a JSON object")
    if split_bytes is not None and not split_mapping:
        raise ValueError("split map must not be empty")
    split_mapping = dict(split_mapping or {})
    label_keys = {"pending", "proposed_test", "dev", "test"}
    per_question = bool(set(split_mapping) - label_keys)
    if any(
        not isinstance(value, str)
        or value not in {"dev", "test"}
        or (not per_question and key in {"dev", "test"} and key != value)
        for key, value in split_mapping.items()
    ):
        raise ValueError("split mapping may explicitly assign provisional labels to Dev/Test only")
    source_bytes = source.read_bytes()
    corpus = load_corpus_records(corpus_dir)
    raw_rows = read_jsonl(source, source_bytes)
    if not raw_rows:
        raise ValueError("M3 Gold must not be empty")
    if per_question:
        ids = [row.get("question_id") for row in raw_rows]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate M3 question ID")
        if set(split_mapping) != set(ids):
            raise ValueError(
                "per-question split map must cover every Gold ID exactly once, no extras"
            )
    converted, original_splits = {}, {}
    for row in raw_rows:
        if row.get("schema_version", source_schema) != source_schema:
            raise ValueError("M3 schema differs from the explicitly chosen source schema")
        sample = GoldSample.model_validate({"schema_version": source_schema, **row})
        if sample.question_id in converted:
            raise ValueError("duplicate M3 question ID")
        original_splits[sample.question_id] = sample.split.value

        def convert_evidence(
            raw, origin_version=sample.source_corpus_version or sample.corpus_version
        ):
            if raw.chapter_id is None or raw.sufficiency is None:
                raise ValueError(
                    "M3 conversion requires chapter identity and annotated sufficiency"
                )
            if raw.chapter_char_start is not None and raw.chapter_char_start != raw.char_start:
                raise ValueError("M3 chapter offset differs from its original raw offset")
            if raw.chapter_char_end is not None and raw.chapter_char_end != raw.char_end:
                raise ValueError("M3 chapter offset differs from its original raw offset")
            # Old document IDs are build-specific. The source block and verbatim
            # passage establish the new textbook identity without renaming them.
            candidates = [
                c
                for c in corpus.chunks
                if c.chapter_id == raw.chapter_id
                and raw.verbatim_text in c.text
                and (raw.block_id is None or any(s.block_id == raw.block_id for s in c.spans))
            ]
            textbooks = {c.textbook_id for c in candidates}
            if len(textbooks) != 1:
                raise ValueError(f"M3 span {raw.span_id!r} has no unique target textbook")
            span = EvidenceSpan(
                span_id=raw.span_id,
                textbook_id=next(iter(textbooks)),
                chapter_id=raw.chapter_id,
                chapter_char_start=raw.char_start,
                chapter_char_end=raw.char_end,
                verbatim_text=raw.verbatim_text,
                block_id=raw.block_id,
                origin_corpus_version=origin_version,
            )
            bind_span(span, corpus)
            return {
                "span": span,
                "sufficiency": raw.sufficiency,
                "annotation_note": raw.annotation_note or None,
            }

        payload = {
            name: getattr(sample, name)
            for name in GoldQuestion.model_fields
            if name
            not in {
                "schema_version",
                "corpus_version",
                "gold_core_evidence_sets",
                "partial_evidence",
            }
            and hasattr(sample, name)
        }
        payload["source_corpus_version"] = sample.source_corpus_version or sample.corpus_version
        payload["split"] = (
            split_mapping[sample.question_id]
            if per_question
            else split_mapping.get(sample.split.value, sample.split.value)
        )
        question = GoldQuestion(
            **payload,
            corpus_version=corpus.manifest.corpus_version,
            gold_core_evidence_sets=tuple(
                tuple(convert_evidence(e) for e in group)
                for group in sample.gold_core_evidence_sets
            ),
            partial_evidence=tuple(convert_evidence(e) for e in sample.partial_evidence),
        )
        converted[question.question_id] = question
    bindings = bind_questions(converted, corpus)
    gold_bytes = "".join(q.model_dump_json() + "\n" for q in converted.values()).encode("utf-8")
    manifest = {
        "schema_version": "0.1",
        "result_type": "explicit_m3_to_v2_gold_conversion",
        "reportable": False,
        "source_schema": source_schema,
        "source_sha256": sha256_bytes(source_bytes),
        "output_gold_sha256": sha256_bytes(gold_bytes),
        "corpus_version": corpus.manifest.corpus_version,
        "corpus_hash": corpus.manifest.corpus_hash,
        "question_count": len(converted),
        "binding_count": len(bindings),
        "split_mapping": split_mapping,
        "split_mapping_mode": "question_id" if per_question else "label",
        "split_map_sha256": sha256_bytes(split_bytes) if split_bytes is not None else None,
        "split_counts": {
            split: sum(q.split.value == split for q in converted.values())
            for split in sorted({q.split.value for q in converted.values()})
        },
        "original_evaluation_splits": original_splits,
        "policy": "preserve reference answers, original chapter offsets and annotation status; "
        "derive target textbook only from unique exact chapter/block/text matches; "
        "conversion does not constitute annotation review or formal approval",
    }
    output_dir.mkdir(parents=True, exist_ok=False)
    (output_dir / "gold.jsonl").write_bytes(gold_bytes)
    (output_dir / "gold_bindings.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in bindings),
        encoding="utf-8",
    )
    (output_dir / "conversion_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest
