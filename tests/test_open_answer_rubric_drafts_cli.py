"""Offline rubric preparation must preserve source identity and review status."""

import json
from pathlib import Path

import pytest
from test_open_answer_scoring import case, experiment, gold, run

from cs30.evaluation.open_answer_cli import main, read_jsonl
from cs30.evaluation.open_answer_models import OpenAnswerRubric
from cs30.evaluation.open_answer_scoring import sha256_bytes
from cs30.evaluation.profile_authoring import (
    ProfileReviewRecord,
    freeze_reviewed_draft,
    load_draft,
)


def bundle_inputs(tmp_path: Path, *, with_matrix: bool = True) -> tuple[list[str], Path]:
    questions = [
        gold(),
        gold().model_copy(update={"question_id": "q2", "question": "Explain why speed changes."}),
    ]
    gold_path = tmp_path / "gold.jsonl"
    gold_path.write_text(
        "".join(item.model_dump_json() + "\n" for item in questions), encoding="utf-8"
    )
    args = ["draft-rubrics", "--gold", str(gold_path), "--output-dir", str(tmp_path / "drafts")]
    if with_matrix:
        matrix = experiment(case()).model_copy(
            update={
                "schema_version": "0.2",
                "rubrics_sha256": None,
                "gold_sha256": sha256_bytes(gold_path.read_bytes()),
            }
        )
        matrix_path = tmp_path / "expected.json"
        matrix_path.write_text(matrix.model_dump_json(), encoding="utf-8")
        args += ["--expected-manifest", str(matrix_path)]
    return args, tmp_path / "drafts"


def test_draft_command_selects_matrix_questions_and_binds_complete_gold_bytes(
    tmp_path, monkeypatch
):
    args, output = bundle_inputs(tmp_path)

    def unexpected(*_args, **_kwargs):
        raise AssertionError("offline draft preparation must never create a provider")

    monkeypatch.setattr("cs30.evaluation.open_answer_cli.GeminiJudgeClient", unexpected)

    assert main(args) == 0

    rows = read_jsonl(output / "rubrics.draft.jsonl")
    rubric = OpenAnswerRubric.model_validate(rows[0])
    assert len(rows) == 1 and rubric.question_id == "q1"
    assert rubric.gold_sha256 == sha256_bytes((tmp_path / "gold.jsonl").read_bytes())
    assert [item.criterion_id for item in rubric.criteria] == [
        "main_answer",
        "required_completeness",
    ]
    assert rubric.review_record_id is None
    manifest = json.loads((output / "rubric_manifest.json").read_bytes())
    assert manifest["reportable"] is False and manifest["api_calls"] == 0
    assert manifest["review_status"] == "pending"
    assert manifest["input_sha256"]["expected_manifest"] == sha256_bytes(
        (tmp_path / "expected.json").read_bytes()
    )
    for filename, expected_hash in manifest["output_sha256"].items():
        assert sha256_bytes((output / filename).read_bytes()) == expected_hash


def test_no_matrix_prepares_all_questions_and_exposes_review_evidence(tmp_path):
    args, output = bundle_inputs(tmp_path, with_matrix=False)
    assert main(args) == 0
    rows = read_jsonl(output / "rubric_review.jsonl")
    assert [row["question_id"] for row in rows] == ["q1", "q2"]
    assert rows[1]["triage_flags"] == ["explicit_reasoning_or_calculation_wording"]
    assert all(row["review_status"] == "pending" for row in rows)
    assert all(row["review_record_id"] is None for row in rows)
    assert rows[0]["reference_evidence"][0]["span_id"] == "s1"
    assert "generator_model" not in rows[0] and "generated_answer" not in rows[0]


@pytest.mark.parametrize("change", ["gold_hash", "unknown_question", "bound_rubrics"])
def test_invalid_matrix_does_not_create_partial_outputs(tmp_path, change):
    args, output = bundle_inputs(tmp_path)
    path = tmp_path / "expected.json"
    payload = json.loads(path.read_bytes())
    if change == "gold_hash":
        payload["gold_sha256"] = "f" * 64
    elif change == "unknown_question":
        payload["cases"][0]["question_id"] = "unknown"
    else:
        payload["schema_version"] = "0.1"
        payload["rubrics_sha256"] = "e" * 64
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert main(args) == 2
    assert not output.exists()


def test_existing_output_is_never_overwritten(tmp_path):
    args, output = bundle_inputs(tmp_path)
    assert main(args) == 0
    original = (output / "rubrics.draft.jsonl").read_bytes()
    assert main(args) == 2
    assert (output / "rubrics.draft.jsonl").read_bytes() == original


def test_draft_bundle_is_deterministic(tmp_path):
    args, output = bundle_inputs(tmp_path)
    assert main(args) == 0
    args[args.index("--output-dir") + 1] = str(tmp_path / "second")
    assert main(args) == 0
    for filename in ("rubrics.draft.jsonl", "rubric_review.jsonl", "rubric_manifest.json"):
        assert (output / filename).read_bytes() == (tmp_path / "second" / filename).read_bytes()


def test_generated_rubrics_feed_the_existing_scorer_without_profiles(tmp_path):
    args, output = bundle_inputs(tmp_path)
    assert main(args) == 0
    runs = tmp_path / "runs.jsonl"
    runs.write_text(run(answer="slowing down").model_dump_json() + "\n", encoding="utf-8")
    score_output = tmp_path / "scores"
    assert (
        main(
            [
                "score",
                "--gold",
                str(tmp_path / "gold.jsonl"),
                "--expected-manifest",
                str(tmp_path / "expected.json"),
                "--runs",
                str(runs),
                "--rubrics",
                str(output / "rubrics.draft.jsonl"),
                "--provider",
                "none",
                "--output-dir",
                str(score_output),
            ]
        )
        == 3
    )
    records = read_jsonl(score_output / "open_answer_scores.jsonl")
    assert records[0]["score_status"] == "needs_review"
    assert records[0]["judge_calls_this_run"] == 0
    assert records[0]["rubric_sha256"] is not None


def test_committed_dev_review_bundle_is_hash_bound_and_unapproved():
    repository = Path(__file__).resolve().parents[1]
    root = repository / "eval_inputs/m8/correctness-dev-rubrics-v0.1"
    manifest = json.loads((root / "rubric_manifest.json").read_bytes())
    rubrics = [
        OpenAnswerRubric.model_validate(row) for row in read_jsonl(root / "rubrics.draft.jsonl")
    ]
    reviews = read_jsonl(root / "rubric_review.jsonl")
    assert len(rubrics) == len(reviews) == manifest["rubric_count"] == 154
    assert sorted(item.question_id for item in rubrics) == manifest["question_ids"]
    assert {item.question_id for item in rubrics} == {row["question_id"] for row in reviews}
    assert manifest["reportable"] is False and manifest["review_status"] == "pending"
    for filename, expected_hash in manifest["output_sha256"].items():
        assert sha256_bytes((root / filename).read_bytes()) == expected_hash
    by_question = {row["question_id"]: row for row in reviews}
    for rubric in rubrics:
        assert rubric.gold_sha256 == manifest["input_sha256"]["gold"]
        assert rubric.review_record_id is None
        evidence = {row["span_id"] for row in by_question[rubric.question_id]["reference_evidence"]}
        assert all(set(criterion.reference_span_ids) <= evidence for criterion in rubric.criteria)
        assert by_question[rubric.question_id]["review_status"] == "pending"


def test_upstream_profile_template_cannot_freeze_the_unapproved_draft():
    repository = Path(__file__).resolve().parents[1]
    draft = load_draft(repository / "docs/evaluation/level-profile-v1/profile_checklist.draft.json")
    record = ProfileReviewRecord.model_validate_json(
        (repository / "docs/evaluation/level-profile-v1/review_record.template.json").read_bytes()
    )
    assert record.draft_package_sha256 == draft.package_sha256
    assert all(review.status == "pending" for review in record.reviews)
    with pytest.raises(ValueError, match="Leader must approve"):
        freeze_reviewed_draft(draft, record)
