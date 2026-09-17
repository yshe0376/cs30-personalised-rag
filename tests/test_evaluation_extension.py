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
    seal_blind_rating_submission,
    write_blind_rating_materials,
    write_extension_reports,
)
from cs30.evaluation.io import load_gold_samples, load_mappings, load_run_results

FIXTURES = Path(__file__).parent / "fixtures" / "evaluation"


def _score_record(run_id: str, question_id: str, condition_id: str, *, correct: bool) -> dict:
    return {
        "run_id": run_id,
        "question_id": question_id,
        "condition_id": condition_id,
        "execution_mode": "retrieval_and_generation",
        "mode": "hybrid",
        "data_version": "gold-v1",
        "split": "dev",
        "corpus_version": "six-textbooks-v1",
        "status": "answered",
        "answer_outcome": "correct" if correct else "wrong",
        "abstention_cause": None,
        "gold_answerable": True,
        "failure_labels": [] if correct else ["wrong_option"],
        "model_call_count": 1,
        "repair_used": False,
        "answer_correct": correct,
        "citation_valid": correct,
        "citation_checks": [
            {
                "valid": correct,
                "resolves_to_chunk": correct,
                "resolves_to_source": correct,
            }
        ],
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
        "execution_mode": "retrieval_and_generation",
        "chunk_version": "chunks-v1",
        "mapping_version": "mapping-v1",
        "index_version": "index-v1",
        "lambda_weight": lambda_weight,
        "lambda_status": lambda_status,
    }


def _seal(
    tmp_path: Path, ratings: Path, rating_key: Path, rubric: Path, *, name: str = "sealed.json"
) -> Path:
    return seal_blind_rating_submission(
        ratings,
        rating_key,
        rubric,
        tmp_path / name,
    )


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
    rating_manifest = _seal(tmp_path, ratings, rating_key, rubric)

    paths = write_extension_reports(
        [scores],
        contexts,
        tmp_path / "reports",
        ratings_path=ratings,
        rating_key_path=rating_key,
        rating_rubric_path=rubric,
        rating_submission_manifest_path=rating_manifest,
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
        row for row in summary["lambda_comparisons"] if row["metric"] == "answer_accuracy"
    )
    assert answer_comparison["baseline_value"] == 0.0
    assert answer_comparison["frozen_value"] == 1.0
    assert answer_comparison["delta"] == 1.0
    assert answer_comparison["baseline_condition_id"] == "plain"
    assert answer_comparison["frozen_condition_id"] == "reranking-only"
    adaptation_comparison = next(
        row for row in summary["lambda_comparisons"] if row["metric"] == "level_adaptation_mean"
    )
    assert adaptation_comparison["delta"] == 2.0
    assert summary["role_label_provenance"] == {"status": "pending"}
    markdown = paths["markdown"].read_text(encoding="utf-8")
    assert "Blinded level-adaptation assessment" in markdown
    assert "Per-citation validity" in markdown
    assert "1/1 (1.0000)" in markdown
    assert "Role semantic quality reviewed by M8" not in markdown
    with paths["groups"].open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert {row["textbook_id"] for row in rows} == {"openstax_college_physics_2e"}


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
    paths = write_extension_reports([scores], contexts, tmp_path / "reports", allow_incomplete=True)
    summary = json.loads(paths["summary"].read_text(encoding="utf-8"))
    abstention = summary["groups"][0]["metrics"]["abstention_accuracy"]
    assert abstention["value"] is None
    assert abstention["status"] == "not_applicable"
    assert "not_applicable" in paths["markdown"].read_text(encoding="utf-8")


def test_refusal_f1_is_not_applicable_without_gold_unanswerable_samples(
    tmp_path: Path,
) -> None:
    wrong_abstention = _score_record(
        "run-wrong-abstention", "q-1", "plain", correct=False
    )
    wrong_abstention.update(
        {
            "status": "abstained",
            "abstention_cause": "model_abstained_with_evidence",
            "abstention_correct": False,
            "answer_correct": None,
        }
    )
    scores = _write_jsonl(tmp_path / "scores.jsonl", [wrong_abstention])
    contexts = _write_jsonl(
        tmp_path / "contexts.jsonl",
        [
            _context(
                "run-wrong-abstention",
                "q-1",
                "plain",
                lambda_weight=0.0,
                lambda_status="baseline",
            )
        ],
    )

    paths = write_extension_reports(
        [scores], contexts, tmp_path / "reports", allow_incomplete=True
    )
    summary = json.loads(paths["summary"].read_text(encoding="utf-8"))
    metrics = summary["groups"][0]["metrics"]

    assert metrics["abstention_precision"]["value"] == 0.0
    assert metrics["abstention_precision"]["status"] == "available"
    assert metrics["abstention_recall"]["value"] is None
    assert metrics["abstention_recall"]["status"] == "not_applicable"
    assert metrics["abstention_f1"]["value"] is None
    assert metrics["abstention_f1"]["status"] == "not_applicable"


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

    paths = write_extension_reports([scores], contexts, tmp_path / "reports", allow_incomplete=True)
    summary = json.loads(paths["summary"].read_text(encoding="utf-8"))

    assert {group["split"] for group in summary["groups"]} == {"dev", "test"}
    assert {group["sample_count"] for group in summary["groups"]} == {1}


def test_lambda_comparison_requires_identical_question_coverage(
    tmp_path: Path,
) -> None:
    scores = _write_jsonl(
        tmp_path / "scores.jsonl",
        [
            _score_record("run-base", "q-base", "plain", correct=True),
            _score_record("run-frozen", "q-frozen", "reranking-only", correct=True),
        ],
    )
    contexts = _write_jsonl(
        tmp_path / "contexts.jsonl",
        [
            _context(
                "run-base",
                "q-base",
                "plain",
                lambda_weight=0.0,
                lambda_status="baseline",
            ),
            _context(
                "run-frozen",
                "q-frozen",
                "reranking-only",
                lambda_weight=0.35,
                lambda_status="frozen",
            ),
        ],
    )

    with pytest.raises(ValueError, match="question coverage mismatch"):
        write_extension_reports([scores], contexts, tmp_path / "reports")


def test_formal_lambda_comparison_rejects_a_missing_pair(tmp_path: Path) -> None:
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

    with pytest.raises(ValueError, match="baseline and frozen groups"):
        write_extension_reports([scores], contexts, tmp_path / "reports")


def test_prepare_blind_rating_materials_excludes_non_answers_and_hides_conditions(
    tmp_path: Path,
) -> None:
    runs = load_run_results(FIXTURES / "run_results_scorable_v0_2.jsonl")[:2]
    gold = load_gold_samples(FIXTURES / "gold_v0_1.jsonl")
    contexts = [
        ExperimentCondition.model_validate(
            _context(
                run.run_id,
                run.question_id,
                run.condition_id,
                lambda_weight=0.0,
                lambda_status="baseline",
            )
        )
        for run in runs
    ]

    paths = write_blind_rating_materials(runs, gold, contexts, tmp_path / "blind", seed=5703)

    with paths["sheet"].open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 1
    assert rows[0]["question_id"] == "fixture_joint"
    assert rows[0]["assigned_level"] == "beginner"
    assert rows[0]["explanation"] == "Alpha supports the answer."
    assert "condition_id" not in rows[0]
    assert "lambda_weight" not in rows[0]
    key_rows = [json.loads(line) for line in paths["key"].read_text(encoding="utf-8").splitlines()]
    assert key_rows[0]["run_id"] == "run_scorable_answered"
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    assert manifest["single_rater"] is True
    assert manifest["expected_rating_count"] == 1
    assert manifest["excluded_run_count"] == 1

    rows[0]["score"] = "4"
    rows[0]["rubric_version"] = "adaptation-v1"
    rows[0]["rater_id"] = "member-8"
    with paths["sheet"].open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    score_path = _write_jsonl(
        tmp_path / "scores.jsonl",
        [
            _score_record(
                "run_scorable_answered",
                "fixture_joint",
                "fixture_condition",
                correct=True,
            )
        ],
    )
    context_path = _write_jsonl(
        tmp_path / "contexts.jsonl",
        [context.model_dump(mode="json") for context in contexts[:1]],
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
    rating_manifest = _seal(
        tmp_path, paths["sheet"], paths["key"], rubric, name="completed-ratings.json"
    )
    reports = write_extension_reports(
        [score_path],
        context_path,
        tmp_path / "reports",
        ratings_path=paths["sheet"],
        rating_key_path=paths["key"],
        rating_rubric_path=rubric,
        rating_submission_manifest_path=rating_manifest,
        allow_incomplete=True,
    )
    summary = json.loads(reports["summary"].read_text(encoding="utf-8"))
    assert summary["level_adaptation"]["rating_count"] == 1


def test_extension_requires_one_globally_frozen_lambda(tmp_path: Path) -> None:
    scores = _write_jsonl(
        tmp_path / "scores.jsonl",
        [
            _score_record("run-a", "q-1", "reranking-only", correct=True),
            _score_record("run-b", "q-2", "combined", correct=True),
        ],
    )
    first = _context(
        "run-a",
        "q-1",
        "reranking-only",
        lambda_weight=0.3,
        lambda_status="frozen",
    )
    second = _context(
        "run-b",
        "q-2",
        "combined",
        lambda_weight=0.4,
        lambda_status="frozen",
    )
    second["comparison_id"] = "prompt-enabled-reranking"
    contexts = _write_jsonl(tmp_path / "contexts.jsonl", [first, second])

    with pytest.raises(ValueError, match="one globally frozen lambda"):
        write_extension_reports([scores], contexts, tmp_path / "reports")


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

    with pytest.raises(ValueError, match="ratings, rating-key, rubric"):
        write_extension_reports([scores], contexts, tmp_path / "reports", ratings_path=ratings)


def test_supplied_empty_rating_file_is_not_pending(tmp_path: Path) -> None:
    scores = _write_jsonl(
        tmp_path / "scores.jsonl",
        [_score_record("run-base", "q-1", "plain", correct=True)],
    )
    contexts = _write_jsonl(
        tmp_path / "contexts.jsonl",
        [_context("run-base", "q-1", "plain", lambda_weight=0.0, lambda_status="baseline")],
    )
    ratings = _write_jsonl(tmp_path / "ratings.jsonl", [])
    rating_key = _write_jsonl(
        tmp_path / "rating-key.jsonl",
        [{"schema_version": "0.1", "blinded_answer_id": "answer-a", "run_id": "run-base"}],
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
    submission = tmp_path / "submission.json"
    submission.write_text(
        json.dumps(
            {
                "schema_version": "0.1",
                "ratings_sha256": hashlib.sha256(ratings.read_bytes()).hexdigest(),
                "key_sha256": hashlib.sha256(rating_key.read_bytes()).hexdigest(),
                "rubric_sha256": hashlib.sha256(rubric.read_bytes()).hexdigest(),
                "expected_rating_count": 1,
                "rubric_version": "adaptation-v1",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="must not be empty"):
        write_extension_reports(
            [scores],
            contexts,
            tmp_path / "reports",
            ratings_path=ratings,
            rating_key_path=rating_key,
            rating_rubric_path=rubric,
            rating_submission_manifest_path=submission,
            allow_incomplete=True,
        )


def test_single_rater_is_enforced(
    tmp_path: Path,
) -> None:
    ratings = _write_jsonl(
        tmp_path / "ratings.jsonl",
        [
            {
                "schema_version": "0.1",
                "rating_id": "rating-a",
                "question_id": "q-1",
                "blinded_answer_id": "answer-a",
                "assigned_level": "beginner",
                "score": 3,
                "rubric_version": "adaptation-v1",
                "rater_id": "rater-1",
            },
            {
                "schema_version": "0.1",
                "rating_id": "rating-b",
                "question_id": "q-2",
                "blinded_answer_id": "answer-b",
                "assigned_level": "beginner",
                "score": 4,
                "rubric_version": "adaptation-v1",
                "rater_id": "rater-2",
            },
        ],
    )
    rating_key = _write_jsonl(
        tmp_path / "rating-key.jsonl",
        [
            {"schema_version": "0.1", "blinded_answer_id": "answer-a", "run_id": "run-a"},
            {"schema_version": "0.1", "blinded_answer_id": "answer-b", "run_id": "run-b"},
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

    with pytest.raises(ValueError, match="exactly one rater_id"):
        _seal(tmp_path, ratings, rating_key, rubric)


def test_execution_mode_and_artifact_versions_are_hard_comparison_boundaries(
    tmp_path: Path,
) -> None:
    scores = _write_jsonl(
        tmp_path / "scores.jsonl",
        [
            _score_record("run-base", "q-1", "plain", correct=True),
            _score_record("run-frozen", "q-1", "reranking-only", correct=True),
        ],
    )
    baseline = _context(
        "run-base", "q-1", "plain", lambda_weight=0.0, lambda_status="baseline"
    )
    frozen = _context(
        "run-frozen",
        "q-1",
        "reranking-only",
        lambda_weight=0.35,
        lambda_status="frozen",
    )
    frozen["mapping_version"] = "mapping-v2"
    contexts = _write_jsonl(tmp_path / "contexts.jsonl", [baseline, frozen])

    with pytest.raises(ValueError, match="mixes execution modes or artifact versions"):
        write_extension_reports([scores], contexts, tmp_path / "reports")

    frozen["mapping_version"] = "mapping-v1"
    frozen["execution_mode"] = "retrieval_only"
    contexts = _write_jsonl(tmp_path / "contexts-mode.jsonl", [baseline, frozen])
    with pytest.raises(ValueError, match="execution_mode mismatch"):
        write_extension_reports([scores], contexts, tmp_path / "reports-mode")


def test_retrieval_only_extension_metrics_are_not_applicable(tmp_path: Path) -> None:
    record = _score_record("run-retrieval", "q-1", "retrieval", correct=True)
    record.update(
        execution_mode="retrieval_only",
        status="retrieved",
        answer_outcome="not_applicable",
    )
    scores = _write_jsonl(tmp_path / "scores.jsonl", [record])
    context = _context(
        "run-retrieval",
        "q-1",
        "retrieval",
        lambda_weight=0.0,
        lambda_status="baseline",
    )
    context["execution_mode"] = "retrieval_only"
    contexts = _write_jsonl(tmp_path / "contexts.jsonl", [context])

    paths = write_extension_reports(
        [scores], contexts, tmp_path / "reports", allow_incomplete=True
    )
    summary = json.loads(paths["summary"].read_text(encoding="utf-8"))

    assert summary["groups"][0]["applicability"] == "not_applicable"
    assert all(
        metric["status"] == "not_applicable"
        for metric in summary["groups"][0]["metrics"].values()
    )


def test_completed_rating_sha_and_role_provenance_fail_closed(tmp_path: Path) -> None:
    scores = _write_jsonl(
        tmp_path / "scores.jsonl",
        [
            _score_record("run-base", "q-1", "plain", correct=True),
            _score_record("run-frozen", "q-1", "reranking-only", correct=True),
        ],
    )
    contexts = _write_jsonl(
        tmp_path / "contexts.jsonl",
        [
            _context("run-base", "q-1", "plain", lambda_weight=0.0, lambda_status="baseline"),
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
                "rating_id": "rating-a",
                "question_id": "q-1",
                "blinded_answer_id": "answer-a",
                "assigned_level": "beginner",
                "score": 4,
                "rubric_version": "adaptation-v1",
                "rater_id": "rater-1",
            },
            {
                "schema_version": "0.1",
                "rating_id": "rating-b",
                "question_id": "q-1",
                "blinded_answer_id": "answer-b",
                "assigned_level": "beginner",
                "score": 5,
                "rubric_version": "adaptation-v1",
                "rater_id": "rater-1",
            },
        ],
    )
    key = _write_jsonl(
        tmp_path / "key.jsonl",
        [
            {"schema_version": "0.1", "blinded_answer_id": "answer-a", "run_id": "run-base"},
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
    submission = _seal(tmp_path, ratings, key, rubric)
    ratings.write_text(ratings.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="ratings_sha256"):
        write_extension_reports(
            [scores],
            contexts,
            tmp_path / "tampered",
            ratings_path=ratings,
            rating_key_path=key,
            rating_rubric_path=rubric,
            rating_submission_manifest_path=submission,
        )

    with pytest.raises(ValueError, match="rejected failed Role-label provenance"):
        write_extension_reports(
            [scores],
            contexts,
            tmp_path / "failed-role",
            role_provenance={"status": "failed", "errors": ["labels_sha256 mismatch"]},
        )


def test_blinded_ratings_must_cover_every_keyed_answer(tmp_path: Path) -> None:
    scores = _write_jsonl(
        tmp_path / "scores.jsonl",
        [
            _score_record("run-base", "q-1", "plain", correct=True),
            _score_record("run-frozen", "q-1", "reranking-only", correct=True),
        ],
    )
    contexts = _write_jsonl(
        tmp_path / "contexts.jsonl",
        [
            _context("run-base", "q-1", "plain", lambda_weight=0.0, lambda_status="baseline"),
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
                "rating_id": "rating-a",
                "question_id": "q-1",
                "blinded_answer_id": "answer-a",
                "assigned_level": "beginner",
                "score": 4,
                "rubric_version": "adaptation-v1",
                "rater_id": "rater-1",
            }
        ],
    )
    rating_key = _write_jsonl(
        tmp_path / "rating-key.jsonl",
        [
            {"schema_version": "0.1", "blinded_answer_id": "answer-a", "run_id": "run-base"},
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
    rating_manifest = _seal(
        tmp_path, ratings, rating_key, rubric, name="incomplete-ratings.json"
    )

    with pytest.raises(ValueError, match="coverage is incomplete"):
        write_extension_reports(
            [scores],
            contexts,
            tmp_path / "reports",
            ratings_path=ratings,
            rating_key_path=rating_key,
            rating_rubric_path=rubric,
            rating_submission_manifest_path=rating_manifest,
        )

    development = write_extension_reports(
        [scores],
        contexts,
        tmp_path / "development-reports",
        ratings_path=ratings,
        rating_key_path=rating_key,
        rating_rubric_path=rubric,
        rating_submission_manifest_path=rating_manifest,
        allow_incomplete=True,
    )
    summary = json.loads(development["summary"].read_text(encoding="utf-8"))
    assert summary["level_adaptation"]["status"] == "incomplete"
    assert summary["level_adaptation"]["missing_blinded_answer_ids"] == ["answer-b"]


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
                "parser_version": gold[0].parser_version,
                "annotation_date": "2026-09-16",
                "annotator_ids": ["primary-annotator"],
                "double_annotated": False,
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
    assert result["parser_version"] == gold[0].parser_version
    assert result["double_annotated"] is False
    assert result["semantic_quality_reviewed"] is False
    assert result["iaa_computed"] is False
    assert result["invalid_question_ids"] == []
    assert result["invalid_reference_ids"] == []
    assert result["invalid_question_reference_pairs"] == []


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
                "parser_version": gold[0].parser_version,
                "annotation_date": "2026-09-16",
                "annotator_ids": ["primary-annotator"],
                "double_annotated": False,
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
        question_reference_pairs={(gold[0].question_id, "candidate-chunk-outside-gold-mapping")},
    )

    assert missing_records["status"] == "failed"
    assert any("requires the M4 records artifact" in item for item in missing_records["errors"])
    assert with_records["status"] == "passed"


def test_role_label_provenance_checks_question_reference_relationship(
    tmp_path: Path,
) -> None:
    gold = load_gold_samples(FIXTURES / "gold_v0_1.jsonl")
    mapping = load_mappings(FIXTURES / "mapping_v0_1.json")
    question_id = mapping.items[1].question_id
    wrong_question_chunk = "chunk_beta"
    labels = _write_jsonl(
        tmp_path / "role_labels.jsonl",
        [
            {
                "schema_version": "role-schema-v1",
                "question_id": question_id,
                "chunk_id": wrong_question_chunk,
                "role": "definition",
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
                "parser_version": gold[0].parser_version,
                "annotation_date": "2026-09-16",
                "annotator_ids": ["primary-annotator"],
                "double_annotated": False,
                "labels_file": labels.name,
                "labels_sha256": hashlib.sha256(labels.read_bytes()).hexdigest(),
                "declared_record_count": 1,
                "reference_universe": "gold_mapping",
            }
        ),
        encoding="utf-8",
    )

    result = audit_role_label_provenance(manifest, gold, mapping)

    assert result["status"] == "failed"
    assert result["invalid_question_reference_pairs"] == [
        {"question_id": question_id, "reference_id": wrong_question_chunk}
    ]


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
            "--allow-incomplete",
        ]
    )

    assert exit_code == 0
    assert (output / "evaluation_report.md").is_file()
    assert (output / "role_label_provenance_report.json").is_file()
