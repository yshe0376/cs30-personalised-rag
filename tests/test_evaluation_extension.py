from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

from cs30.evaluation.cli import main
from cs30.evaluation.extension_models import ExperimentCondition
from cs30.evaluation.extension_reporting import (
    audit_role_label_provenance,
    write_extension_reports,
)
from cs30.evaluation.io import load_gold_samples, load_mappings

FIXTURES = Path(__file__).parent / "fixtures" / "evaluation"


def _score_record(run_id: str, question_id: str, condition_id: str, *, correct: bool) -> dict:
    return {
        "run_id": run_id,
        "question_id": question_id,
        "condition_id": condition_id,
        "mode": "hybrid",
        "data_version": "gold-v1",
        "split": "dev",
        "corpus_version": "six-textbooks-v1",
        "status": "answered",
        "gold_answerable": True,
        "failure_labels": [] if correct else ["wrong_option"],
        "model_call_count": 1,
        "repair_used": False,
        "answer_correct": correct,
        "citation_valid": correct,
        "gold_evidence_covered": correct,
        "abstention_correct": None,
        "raw_json_valid": True,
        "raw_schema_valid": True,
        "repaired_json_valid": None,
        "repaired_schema_valid": None,
    }


def _write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
    return path


def _context(
    run_id: str,
    question_id: str,
    condition_id: str,
    *,
    lambda_weight: float,
    lambda_status: str,
) -> dict:
    return {
        "schema_version": "0.1",
        "run_id": run_id,
        "question_id": question_id,
        "condition_id": condition_id,
        "comparison_id": "prompt-controlled-reranking",
        "textbook_id": "openstax_college_physics_2e",
        "student_level": "beginner",
        "lambda_weight": lambda_weight,
        "lambda_status": lambda_status,
    }


def test_baseline_context_requires_zero_lambda() -> None:
    with pytest.raises(ValueError, match="lambda_weight=0"):
        ExperimentCondition.model_validate(
            _context(
                "run-a",
                "q-a",
                "plain",
                lambda_weight=0.2,
                lambda_status="baseline",
            )
        )


def test_extension_reports_keep_automated_manual_and_provenance_outputs_separate(
    tmp_path: Path,
) -> None:
    scores = _write_jsonl(
        tmp_path / "scores.jsonl",
        [
            _score_record("run-base", "q-1", "plain", correct=False),
            _score_record("run-frozen", "q-1", "reranking-only", correct=True),
        ],
    )
    contexts = _write_jsonl(
        tmp_path / "contexts.jsonl",
        [
            _context(
                "run-base",
                "q-1",
                "plain",
                lambda_weight=0.0,
                lambda_status="baseline",
            ),
            _context(
                "run-frozen",
                "q-1",
                "reranking-only",
                lambda_weight=0.35,
                lambda_status="frozen",
            ),
        ],
    )
    ratings = _write_jsonl(
        tmp_path / "ratings.jsonl",
        [
            {
                "schema_version": "0.1",
                "rating_id": "rating-base",
                "question_id": "q-1",
                "blinded_answer_id": "answer-a",
                "assigned_level": "beginner",
                "score": 2,
                "rubric_version": "adaptation-v1",
                "rater_id": "rater-1",
            },
            {
                "schema_version": "0.1",
                "rating_id": "rating-frozen",
                "question_id": "q-1",
                "blinded_answer_id": "answer-b",
                "assigned_level": "beginner",
                "score": 4,
                "rubric_version": "adaptation-v1",
                "rater_id": "rater-1",
            },
        ],
    )
    rating_key = _write_jsonl(
        tmp_path / "rating-key.jsonl",
        [
            {
                "schema_version": "0.1",
                "blinded_answer_id": "answer-a",
                "run_id": "run-base",
            },
            {
                "schema_version": "0.1",
                "blinded_answer_id": "answer-b",
                "run_id": "run-frozen",
            },
        ],
    )
    rubric = tmp_path / "rubric.json"
    rubric.write_text(
        json.dumps(
            {
                "schema_version": "0.1",
                "rubric_version": "adaptation-v1",
                "score_min": 1,
                "score_max": 5,
            }
        ),
        encoding="utf-8",
    )

    paths = write_extension_reports(
        [scores],
        contexts,
        tmp_path / "reports",
        ratings_path=ratings,
        rating_key_path=rating_key,
        rating_rubric_path=rubric,
    )

    assert set(paths) == {
        "summary",
        "groups",
        "lambda",
        "failures",
        "adaptation",
        "role_provenance",
        "markdown",
    }
    assert all(path.is_file() for path in paths.values())
    summary = json.loads(paths["summary"].read_text(encoding="utf-8"))
    answer_comparison = next(
        row
        for row in summary["lambda_comparisons"]
        if row["metric"] == "answer_accuracy"
    )
    assert answer_comparison["baseline_value"] == 0.0
    assert answer_comparison["frozen_value"] == 1.0
    assert answer_comparison["delta"] == 1.0
    adaptation_comparison = next(
        row
        for row in summary["lambda_comparisons"]
        if row["metric"] == "level_adaptation_mean"
    )
    assert adaptation_comparison["delta"] == 2.0
    assert summary["role_label_provenance"] == {"status": "pending"}
    markdown = paths["markdown"].read_text(encoding="utf-8")
    assert "Blinded level-adaptation assessment" in markdown
    assert "Role semantic quality reviewed by M8" not in markdown
    with paths["groups"].open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert {row["textbook_id"] for row in rows} == {
        "openstax_college_physics_2e"
    }


def test_zero_denominator_is_explicitly_not_applicable(tmp_path: Path) -> None:
    scores = _write_jsonl(
        tmp_path / "scores.jsonl",
        [_score_record("run-base", "q-1", "plain", correct=True)],
    )
    contexts = _write_jsonl(
        tmp_path / "contexts.jsonl",
        [
            _context(
                "run-base",
                "q-1",
                "plain",
                lambda_weight=0.0,
                lambda_status="baseline",
            )
        ],
    )
    paths = write_extension_reports([scores], contexts, tmp_path / "reports")
    summary = json.loads(paths["summary"].read_text(encoding="utf-8"))
    abstention = summary["groups"][0]["metrics"]["abstention_accuracy"]
    assert abstention["value"] is None
    assert abstention["status"] == "not_applicable"
    assert "not_applicable" in paths["markdown"].read_text(encoding="utf-8")


def test_extension_does_not_mix_dev_and_test_groups(tmp_path: Path) -> None:
    dev = _score_record("run-dev", "q-dev", "plain", correct=True)
    test = _score_record("run-test", "q-test", "plain", correct=False)
    test["split"] = "test"
    scores = _write_jsonl(tmp_path / "scores.jsonl", [dev, test])
    contexts = _write_jsonl(
        tmp_path / "contexts.jsonl",
        [
            _context(
                "run-dev",
                "q-dev",
                "plain",
                lambda_weight=0.0,
                lambda_status="baseline",
            ),
            _context(
                "run-test",
                "q-test",
                "plain",
                lambda_weight=0.0,
                lambda_status="baseline",
            ),
        ],
    )

    paths = write_extension_reports([scores], contexts, tmp_path / "reports")
    summary = json.loads(paths["summary"].read_text(encoding="utf-8"))

    assert {group["split"] for group in summary["groups"]} == {"dev", "test"}
    assert {group["sample_count"] for group in summary["groups"]} == {1}


def test_blinded_ratings_require_a_separate_key(tmp_path: Path) -> None:
    scores = _write_jsonl(
        tmp_path / "scores.jsonl",
        [_score_record("run-base", "q-1", "plain", correct=True)],
    )
    contexts = _write_jsonl(
        tmp_path / "contexts.jsonl",
        [
            _context(
                "run-base",
                "q-1",
                "plain",
                lambda_weight=0.0,
                lambda_status="baseline",
            )
        ],
    )
    ratings = _write_jsonl(tmp_path / "ratings.jsonl", [])

    with pytest.raises(ValueError, match="ratings, rating-key, and rubric"):
        write_extension_reports(
            [scores], contexts, tmp_path / "reports", ratings_path=ratings
        )


def test_role_label_provenance_checks_versions_hash_and_references(
    tmp_path: Path,
) -> None:
    gold = load_gold_samples(FIXTURES / "gold_v0_1.jsonl")
    mapping = load_mappings(FIXTURES / "mapping_v0_1.json")
    first_item = mapping.items[0]
    first_chunk = first_item.spans[0].acceptable_chunk_sets[0][0]
    labels = _write_jsonl(
        tmp_path / "role_labels.jsonl",
        [
            {
                "schema_version": "role-schema-v1",
                "question_id": first_item.question_id,
                "chunk_id": first_chunk,
                "role": "definition",
            }
        ],
    )
    labels_hash = hashlib.sha256(labels.read_bytes()).hexdigest()
    manifest = tmp_path / "role_manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": "0.1",
                "role_schema_version": "role-schema-v1",
                "role_taxonomy_version": "role-taxonomy-v1",
                "annotation_version": "role-labels-v1",
                "corpus_version": gold[0].corpus_version,
                "annotation_date": "2026-09-16",
                "annotator_ids": ["primary-annotator"],
                "labels_file": labels.name,
                "labels_sha256": labels_hash,
                "declared_record_count": 1,
                "question_id_field": "question_id",
                "reference_id_field": "chunk_id",
                "reference_type": "chunk",
                "reference_universe": "gold_mapping",
                "role_field": "role",
            }
        ),
        encoding="utf-8",
    )

    result = audit_role_label_provenance(manifest, gold, mapping)

    assert result["status"] == "passed"
    assert result["single_annotator"] is True
    assert result["semantic_quality_reviewed"] is False
    assert result["iaa_computed"] is False
    assert result["invalid_question_ids"] == []
    assert result["invalid_reference_ids"] == []


def test_corpus_role_references_require_m4_records(tmp_path: Path) -> None:
    gold = load_gold_samples(FIXTURES / "gold_v0_1.jsonl")
    mapping = load_mappings(FIXTURES / "mapping_v0_1.json")
    labels = _write_jsonl(
        tmp_path / "role_labels.jsonl",
        [
            {
                "schema_version": "role-schema-v1",
                "question_id": gold[0].question_id,
                "chunk_id": "candidate-chunk-outside-gold-mapping",
                "role": "example",
            }
        ],
    )
    manifest = tmp_path / "role_manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": "0.1",
                "role_schema_version": "role-schema-v1",
                "role_taxonomy_version": "role-taxonomy-v1",
                "annotation_version": "role-labels-v1",
                "corpus_version": gold[0].corpus_version,
                "annotation_date": "2026-09-16",
                "annotator_ids": ["primary-annotator"],
                "labels_file": labels.name,
                "labels_sha256": hashlib.sha256(labels.read_bytes()).hexdigest(),
                "declared_record_count": 1,
                "reference_universe": "corpus_records",
            }
        ),
        encoding="utf-8",
    )

    missing_records = audit_role_label_provenance(manifest, gold, mapping)
    with_records = audit_role_label_provenance(
        manifest,
        gold,
        mapping,
        corpus_record_ids={"candidate-chunk-outside-gold-mapping"},
    )

    assert missing_records["status"] == "failed"
    assert any("requires the M4 records artifact" in item for item in missing_records["errors"])
    assert with_records["status"] == "passed"


def test_cli_writes_extension_package(tmp_path: Path) -> None:
    scores = _write_jsonl(
        tmp_path / "scores.jsonl",
        [_score_record("run-base", "q-1", "plain", correct=True)],
    )
    contexts = _write_jsonl(
        tmp_path / "contexts.jsonl",
        [
            _context(
                "run-base",
                "q-1",
                "plain",
                lambda_weight=0.0,
                lambda_status="baseline",
            )
        ],
    )
    output = tmp_path / "reports"

    exit_code = main(
        [
            "report-extension",
            "--scores",
            str(scores),
            "--contexts",
            str(contexts),
            "--output-dir",
            str(output),
        ]
    )

    assert exit_code == 0
    assert (output / "w6_evaluation_report.md").is_file()
    assert (output / "role_label_provenance_report.json").is_file()
