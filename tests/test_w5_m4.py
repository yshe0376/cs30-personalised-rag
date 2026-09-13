"""Acceptance tests for the Week 5 Member 4 delivery."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from cs30.chunking import (
    W5_CHUNKING_STRATEGY,
    W5_CONFIG_ID,
    BlockAwareChunker,
    BlockChunkingStrategy,
    GoldSpan,
    build_chunk_anomalies,
    build_evaluation_mapping,
    export_retrieval_corpus,
    map_gold_spans_to_chunks,
    verify_corpus_identity,
    verify_mapping_identity,
)
from cs30.contracts import ContentType, OpenStaxChapter, OpenStaxDocument, TextBlock


class CharacterCounter:
    name = "character-counter-test-v1"

    def count(self, text: str) -> int:
        return len(text)


def make_document() -> OpenStaxDocument:
    specs = [
        ("1", "1.1", ContentType.BODY, "Alpha evidence."),
        ("1", "1.1", ContentType.EQUATION, "F = m a."),
        ("1", "1.1", ContentType.PROBLEM, "Excluded exercise."),
        ("1", "1.2", ContentType.BODY, "Beta evidence."),
        ("2", "2.1", ContentType.BODY, "Gamma evidence."),
    ]
    text_parts: list[str] = []
    blocks: list[TextBlock] = []
    chapter_bounds: dict[str, list[int]] = {}
    cursor = 0
    for index, (chapter_id, section_id, content_type, value) in enumerate(specs, start=1):
        if text_parts:
            text_parts.append("\n\n")
            cursor += 2
        start = cursor
        text_parts.append(value)
        cursor += len(value)
        chapter_bounds.setdefault(chapter_id, [start, cursor])[1] = cursor
        blocks.append(
            TextBlock(
                block_id=f"block-{index}",
                chapter_id=chapter_id,
                section_id=section_id,
                section_title=f"Section {section_id}",
                content_type=content_type,
                char_start=start,
                char_end=cursor,
            )
        )
    text = "".join(text_parts)
    return OpenStaxDocument(
        document_id="w5-test-document",
        title="W5 test document",
        version="test-v1",
        source="fixture://w5-test",
        document_hash="sha256:w5-test-document",
        parser_version="test-parser-v1",
        text=text,
        chapters=[
            OpenStaxChapter(
                chapter_id=chapter_id,
                title=f"Chapter {chapter_id}",
                char_start=bounds[0],
                char_end=bounds[1],
            )
            for chapter_id, bounds in chapter_bounds.items()
        ],
        blocks=blocks,
    )


def make_chunks(document: OpenStaxDocument):
    strategy = BlockChunkingStrategy(
        target_tokens=20,
        min_tokens=5,
        max_tokens=24,
        candidate_id=W5_CONFIG_ID,
        include_types=W5_CHUNKING_STRATEGY.include_types,
    )
    return BlockAwareChunker(
        strategy=strategy,
        token_counter=CharacterCounter(),
    ).chunk(document)


def test_w5_configuration_is_one_fixed_non_experimental_strategy() -> None:
    assert W5_CHUNKING_STRATEGY.candidate_id == "w5-m4-official-v1"
    assert W5_CHUNKING_STRATEGY.respect_section_boundaries is True
    assert W5_CHUNKING_STRATEGY.enrich_embed_text is False
    assert ContentType.PROBLEM not in W5_CHUNKING_STRATEGY.include_types
    assert ContentType.CONCEPTUAL_QUESTION not in W5_CHUNKING_STRATEGY.include_types
    assert ContentType.EQUATION in W5_CHUNKING_STRATEGY.include_types


def test_corpus_export_publishes_qa_anomalies_and_embedding_disposition(
    tmp_path: Path,
) -> None:
    document = make_document()
    chunks = BlockAwareChunker(
        strategy=BlockChunkingStrategy(
            target_tokens=25,
            min_tokens=10,
            max_tokens=30,
            candidate_id=W5_CONFIG_ID,
            include_types=W5_CHUNKING_STRATEGY.include_types,
        ),
        token_counter=CharacterCounter(),
    ).chunk(document)
    manifest = export_retrieval_corpus(
        [document],
        chunks,
        tmp_path,
        rebuild_command="python scripts/build_w5_m4_delivery.py",
        embedding_max_tokens=12,
    )

    statistics = json.loads((tmp_path / "statistics.json").read_text(encoding="utf-8"))
    anomalies = json.loads((tmp_path / "anomalies.json").read_text(encoding="utf-8"))
    tracebacks = json.loads(
        (tmp_path / "traceback_records.json").read_text(encoding="utf-8")
    )
    assert manifest["manifest_version"] == "1.1"
    assert manifest["chunk_config_id"].startswith("sha256:")
    assert manifest["consumers"]["bm25"] == manifest["consumers"]["dense"]
    assert statistics["filter"]["filtered_content_leakage_count"] == 0
    assert statistics["filter"]["excluded_source_block_count"] == 1
    assert statistics["embedding_limit"]["status"] == "verified"
    assert statistics["embedding_limit"]["overlong_input_count"] > 0
    assert {item["type"] for item in anomalies} == {"overlong_embedding_input"}
    assert all(item["recovered_text_matches"] for item in tracebacks)
    assert any(
        "formula_or_equation" in item["selection_reasons"] for item in tracebacks
    )
    assert any("chapter_start" in item["selection_reasons"] for item in tracebacks)
    assert any("cross_block" in item["selection_reasons"] for item in tracebacks)


def test_filtered_content_leakage_is_reported() -> None:
    document = make_document()
    chunks = make_chunks(document)
    chunk = chunks[0]
    metadata = dict(chunk.metadata)
    metadata["source_block_ids"] += ",block-3"
    leaked = chunk.model_copy(update={"metadata": metadata})

    anomalies = build_chunk_anomalies([leaked, *chunks[1:]], documents=[document])
    assert [item for item in anomalies if item["type"] == "filtered_content_leakage"] == [
        {
            "type": "filtered_content_leakage",
            "chunk_id": leaked.chunk_id,
            "document_id": document.document_id,
            "block_id": "block-3",
            "content_type": "problem",
        }
    ]


def test_gold_mapping_preserves_roles_and_multi_chunk_coverage(tmp_path: Path) -> None:
    document = make_document()
    chunks = make_chunks(document)
    span = GoldSpan(
        gold_span_id="gold-1",
        question_id="question-1",
        document_id=document.document_id,
        chapter_id="1",
        char_start=chunks[0].char_start,
        char_end=chunks[1].char_end,
        text=document.text[chunks[0].char_start : chunks[1].char_end],
        coverage_role="alternative",
        alternative_group_id="alternative-set-a",
    )

    corpus_dir = tmp_path / "corpus"
    manifest = export_retrieval_corpus(
        [document],
        chunks,
        corpus_dir,
        rebuild_command="test rebuild",
    )
    mapping = map_gold_spans_to_chunks(
        [span],
        chunks,
        corpus_id=manifest["corpus_id"],
        chunk_config_id=manifest["chunk_config_id"],
        documents=[document],
    )

    entry = mapping["entries"][0]
    assert entry["matching_chunk_ids"] == [chunks[0].chunk_id, chunks[1].chunk_id]
    assert entry["coverage_role"] == "alternative"
    assert entry["alternative_group_id"] == "alternative-set-a"
    assert entry["coverage_status"] == "full"
    assert entry["coverage_ratio"] == 1.0
    assert mapping["matching_rule"]["rule_version"] == "1.0"
    assert mapping["mapping_id"].startswith("sha256:")
    evaluation_mapping = build_evaluation_mapping(
        mapping,
        corpus_version="fixture-corpus-v1",
    )
    assert evaluation_mapping["corpus_version"] == "fixture-corpus-v1"
    assert evaluation_mapping["chunk_config_hash"] == manifest["chunk_config_id"]
    assert evaluation_mapping["items"][0]["spans"] == [
        {
            "span_id": "gold-1",
            "acceptable_chunk_sets": [[chunks[0].chunk_id, chunks[1].chunk_id]],
        }
    ]


def test_gold_mapping_fails_closed_on_uncovered_span(tmp_path: Path) -> None:
    document = make_document()
    chunks = make_chunks(document)
    excluded = document.blocks[2]
    span = GoldSpan(
        gold_span_id="gold-excluded",
        question_id="question-2",
        document_id=document.document_id,
        chapter_id="1",
        char_start=excluded.char_start,
        char_end=excluded.char_end,
    )
    with pytest.raises(ValueError, match="not fully covered"):
        map_gold_spans_to_chunks(
            [span],
            chunks,
            corpus_id="sha256:corpus",
            chunk_config_id="sha256:config",
            documents=[document],
        )


def test_evaluation_mapping_skips_uncovered_spans_and_empty_questions() -> None:
    document = make_document()
    chunks = make_chunks(document)
    included = document.blocks[0]
    excluded = document.blocks[2]
    mapping = map_gold_spans_to_chunks(
        [
            GoldSpan(
                gold_span_id="gold-included",
                question_id="question-included",
                document_id=document.document_id,
                chapter_id=included.chapter_id,
                char_start=included.char_start,
                char_end=included.char_end,
            ),
            GoldSpan(
                gold_span_id="gold-excluded",
                question_id="question-excluded",
                document_id=document.document_id,
                chapter_id=excluded.chapter_id,
                char_start=excluded.char_start,
                char_end=excluded.char_end,
            ),
        ],
        chunks,
        corpus_id="sha256:corpus",
        chunk_config_id="sha256:config",
        documents=[document],
        require_full_coverage=False,
    )

    evaluation_mapping = build_evaluation_mapping(
        mapping,
        corpus_version="fixture-corpus-v1",
    )

    assert [item["question_id"] for item in evaluation_mapping["items"]] == [
        "question-included"
    ]
    assert evaluation_mapping["items"][0]["spans"][0]["span_id"] == "gold-included"


def test_identity_guards_name_changed_dimensions() -> None:
    with pytest.raises(ValueError, match="corpus_id"):
        verify_corpus_identity(
            {"corpus_id": "sha256:old"},
            {"corpus_id": "sha256:new"},
        )
    with pytest.raises(ValueError, match="mapping_id"):
        verify_mapping_identity(
            {"mapping_id": "sha256:old"},
            {"mapping_id": "sha256:new"},
        )


def test_gold_mapping_cli_writes_only_the_versioned_mapping_bundle(
    tmp_path: Path,
) -> None:
    repository_root = Path(__file__).resolve().parents[1]
    document_path = repository_root / "src" / "cs30" / "fixtures" / "openstax_document.json"
    corpus_dir = tmp_path / "corpus"
    subprocess.run(
        [
            sys.executable,
            str(repository_root / "scripts" / "build_retrieval_corpus.py"),
            "--document",
            str(document_path),
            "--output-dir",
            str(corpus_dir),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    document = OpenStaxDocument.model_validate_json(document_path.read_text(encoding="utf-8"))
    gold_path = tmp_path / "gold.jsonl"
    gold_path.write_text(
        json.dumps(
            {
                "schema_version": "0.2",
                "question_id": "fixture-question-1",
                "corpus_version": "fixture-corpus-v1",
                "annotation_status": "m3_initial",
                "gold_core_evidence_sets": [
                    [
                        {
                            "span_id": "fixture-gold-1",
                            "document_id": document.document_id,
                            "chapter_id": document.chapters[0].chapter_id,
                            "corpus_char_start": 0,
                            "corpus_char_end": 12,
                            "verbatim_text": document.text[:12],
                            "resolution_status": "resolved",
                            "resolved_block_id": document.blocks[0].block_id,
                            "sufficiency": "core_sufficient",
                        }
                    ]
                ],
                "partial_evidence": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    source_manifest_path = tmp_path / "source_corpus_manifest.json"
    source_manifest_path.write_text(
        json.dumps({"corpus_version": "fixture-corpus-v1"}),
        encoding="utf-8",
    )
    output_dir = tmp_path / "mapping"
    subprocess.run(
        [
            sys.executable,
            str(repository_root / "scripts" / "map_gold_spans.py"),
            "--gold",
            str(gold_path),
            "--corpus-dir",
            str(corpus_dir),
            "--document",
            str(document_path),
            "--output-dir",
            str(output_dir),
            "--source-corpus-manifest",
            str(source_manifest_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert sorted(path.name for path in output_dir.iterdir()) == [
        "evaluation_mapping_v0_1.json",
        "gold_to_chunk_mapping.json",
        "matching_rule.json",
    ]


def test_gold_mapping_cli_partial_delivery_lists_omitted_questions(
    tmp_path: Path,
) -> None:
    repository_root = Path(__file__).resolve().parents[1]
    document = make_document()
    document_path = tmp_path / "document.json"
    document_path.write_text(document.model_dump_json(indent=2), encoding="utf-8")
    corpus_dir = tmp_path / "corpus"
    export_retrieval_corpus(
        [document],
        make_chunks(document),
        corpus_dir,
        rebuild_command="test rebuild",
    )
    included = document.blocks[0]
    excluded = document.blocks[2]

    def record(question_id: str, span_id: str, block) -> dict[str, object]:
        return {
            "schema_version": "0.2",
            "question_id": question_id,
            "corpus_version": "fixture-corpus-v1",
            "annotation_status": "m3_initial",
            "gold_core_evidence_sets": [
                [
                    {
                        "span_id": span_id,
                        "document_id": document.document_id,
                        "chapter_id": block.chapter_id,
                        "corpus_char_start": block.char_start,
                        "corpus_char_end": block.char_end,
                        "verbatim_text": document.block_text(block),
                        "resolution_status": "resolved",
                        "resolved_block_id": block.block_id,
                        "sufficiency": "core_sufficient",
                    }
                ]
            ],
            "partial_evidence": [],
        }

    gold_path = tmp_path / "gold.jsonl"
    gold_path.write_text(
        "\n".join(
            json.dumps(item)
            for item in (
                record("question-included", "gold-included", included),
                record("question-excluded", "gold-excluded", excluded),
            )
        )
        + "\n",
        encoding="utf-8",
    )
    source_manifest_path = tmp_path / "source_corpus_manifest.json"
    source_manifest_path.write_text(
        json.dumps({"corpus_version": "fixture-corpus-v1"}),
        encoding="utf-8",
    )
    output_dir = tmp_path / "mapping"
    subprocess.run(
        [
            sys.executable,
            str(repository_root / "scripts" / "map_gold_spans.py"),
            "--gold",
            str(gold_path),
            "--corpus-dir",
            str(corpus_dir),
            "--document",
            str(document_path),
            "--output-dir",
            str(output_dir),
            "--source-corpus-manifest",
            str(source_manifest_path),
            "--allow-partial",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert sorted(path.name for path in output_dir.iterdir()) == [
        "alignment_issues.json",
        "delivery_manifest.json",
        "evaluation_mapping_v0_1.json",
        "gold_to_chunk_mapping.json",
        "matching_rule.json",
    ]
    evaluation_mapping = json.loads(
        (output_dir / "evaluation_mapping_v0_1.json").read_text(encoding="utf-8")
    )
    delivery_manifest = json.loads(
        (output_dir / "delivery_manifest.json").read_text(encoding="utf-8")
    )
    assert [item["question_id"] for item in evaluation_mapping["items"]] == [
        "question-included"
    ]
    assert delivery_manifest["evaluation_question_count"] == 1
    assert delivery_manifest["evaluation_span_count"] == 1
    assert delivery_manifest["excluded_question_count"] == 1
    assert delivery_manifest["excluded_questions"] == [
        {
            "question_id": "question-excluded",
            "gold_span_ids": ["gold-excluded"],
            "coverage_statuses": ["none"],
            "source_content_types": ["problem"],
            "reason": (
                "Gold evidence uses source content excluded by the fixed corpus "
                "filter: problem"
            ),
        }
    ]
    assert delivery_manifest["m1_exclusion_reason"] == "mapping_missing"
