"""Real M7 content plus synthetic review records; no human approval is fabricated."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cs30.contracts import StudentLevel
from cs30.evaluation.level_adaptation import build_adaptation_request
from cs30.evaluation.level_discrimination import build_discrimination_request
from cs30.evaluation.level_profiles import (
    load_profile_checklist_package,
    profile_package_content_sha256,
)
from cs30.evaluation.profile_authoring import (
    DraftProfileChecklistPackage,
    ProfileReviewRecord,
    check_non_gold_anchors,
    freeze_reviewed_draft,
    load_draft,
    main,
)
from cs30.evaluation.v2_generation_models import (
    ApprovalStatus,
    GenerationEvaluationInput,
    JudgeConfiguration,
)

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_DIR = ROOT / "docs/evaluation/level-profile-v1"
DRAFT_PATH = PACKAGE_DIR / "profile_checklist.draft.json"
GOLD = ROOT / "m3_gold/gold_v0_1_1.jsonl"


def _synthetic_review(draft: DraftProfileChecklistPackage) -> dict:
    """Test-only identities and approvals, never a real team sign-off."""
    return {
        "draft_package_sha256": draft.package_sha256,
        "reviews": [
            {
                "role": role,
                "reviewer_id": f"synthetic-{role}",
                "status": "approved",
                "review_record_id": f"synthetic-test-record-{role}",
                "reviewed_at": "2026-10-21T00:00:00+00:00",
                "notes": "Synthetic approval for an offline integration test only.",
            }
            for role in ("leader", "physics")
        ],
    }


def _write(path: Path, payload: object) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_real_draft_is_complete_and_cannot_enter_m8_frozen_loader() -> None:
    draft = load_draft(DRAFT_PATH)
    assert not draft.frozen
    assert draft.author_ids == ["M7"]
    assert draft.physics_reviewer_ids == []
    assert sum(len(item.criteria) for item in draft.checklists) == 11
    assert {profile.level for profile in draft.profiles} == set(StudentLevel)
    assert all(len(profile.anchor_examples) == 3 for profile in draft.profiles)
    assert draft.generation_guidance_consistency == "mismatch_recorded"
    with pytest.raises(ValueError, match="invalid profile/checklist package"):
        load_profile_checklist_package(DRAFT_PATH)
    record = ProfileReviewRecord.model_validate_json(
        (PACKAGE_DIR / "review_record.template.json").read_text(encoding="utf-8")
    )
    assert record.draft_package_sha256 == draft.package_sha256
    assert all(review.status == "pending" for review in record.reviews)
    with pytest.raises(ValueError, match="Leader must approve"):
        freeze_reviewed_draft(draft, record)


@pytest.mark.parametrize("mutation", ["text", "duplicate_criterion", "different_anchor"])
def test_tampered_or_inconsistent_draft_is_rejected(mutation: str) -> None:
    payload = json.loads(DRAFT_PATH.read_text(encoding="utf-8"))
    if mutation == "text":
        payload["profiles"][0]["student_positioning"] = "Tampered content."
    elif mutation == "duplicate_criterion":
        payload["checklists"][0]["criteria"].append(payload["checklists"][0]["criteria"][0])
        payload["package_sha256"] = profile_package_content_sha256(payload)
    else:
        payload["profiles"][1]["anchor_examples"][0]["question"] = "A different question?"
        payload["package_sha256"] = profile_package_content_sha256(payload)
    with pytest.raises(ValueError):
        DraftProfileChecklistPackage.model_validate(payload)


@pytest.mark.parametrize("case", ["stale_hash", "pending", "rejected", "same_identity"])
def test_freeze_rejects_missing_or_unbound_approvals(case: str) -> None:
    draft = load_draft(DRAFT_PATH)
    payload = _synthetic_review(draft)
    if case == "stale_hash":
        payload["draft_package_sha256"] = "a" * 64
    elif case == "same_identity":
        payload["reviews"][1]["reviewer_id"] = payload["reviews"][0]["reviewer_id"]
    else:
        payload["reviews"][1]["status"] = case
    record = ProfileReviewRecord.model_validate(payload)
    with pytest.raises(ValueError):
        freeze_reviewed_draft(draft, record)


@pytest.mark.parametrize("field", ["reviewer_id", "review_record_id", "reviewed_at", "notes"])
def test_approved_review_requires_a_complete_record(field: str) -> None:
    payload = _synthetic_review(load_draft(DRAFT_PATH))
    payload["reviews"][1][field] = None
    with pytest.raises(ValueError, match="approved reviews require"):
        ProfileReviewRecord.model_validate(payload)


def test_approved_review_requires_timezone_and_both_roles() -> None:
    payload = _synthetic_review(load_draft(DRAFT_PATH))
    payload["reviews"][1]["reviewed_at"] = "2026-10-21T00:00:00"
    with pytest.raises(ValueError, match="timezone"):
        ProfileReviewRecord.model_validate(payload)
    payload = _synthetic_review(load_draft(DRAFT_PATH))
    payload["reviews"][1]["role"] = "leader"
    with pytest.raises(ValueError, match="one Leader review"):
        ProfileReviewRecord.model_validate(payload)


def test_freeze_rechecks_mutable_content_at_the_export_boundary() -> None:
    draft = load_draft(DRAFT_PATH)
    record = ProfileReviewRecord.model_validate(_synthetic_review(draft))
    draft.profiles[0].student_positioning = "Changed after the synthetic review."
    with pytest.raises(ValueError, match="hash mismatch"):
        freeze_reviewed_draft(draft, record)


def test_freeze_rechecks_mutable_review_at_the_export_boundary() -> None:
    draft = load_draft(DRAFT_PATH)
    record = ProfileReviewRecord.model_validate(_synthetic_review(draft))
    record.reviews[1].review_record_id = None
    with pytest.raises(ValueError, match="approved reviews require"):
        freeze_reviewed_draft(draft, record)


@pytest.mark.parametrize("collision", ["id", "question", "punctuation_and_case"])
def test_non_gold_check_rejects_question_or_identifier_collision(
    tmp_path: Path, collision: str
) -> None:
    draft = load_draft(DRAFT_PATH)
    anchor = draft.profiles[0].anchor_examples[0]
    row = {"question_id": "synthetic-gold", "question": "An unrelated question?"}
    if collision == "id":
        row["question_id"] = anchor.anchor_id
    elif collision == "question":
        row["question"] = anchor.question
    else:
        row["question"] = anchor.question.upper().replace(".", "!")
    with pytest.raises(ValueError, match="collides with a Gold"):
        check_non_gold_anchors(draft, [_write(tmp_path / "gold.jsonl", row)])


@pytest.mark.parametrize("content", ["", "[]", '{"question": 42}'])
def test_non_gold_check_rejects_empty_or_malformed_sources(tmp_path: Path, content: str) -> None:
    path = tmp_path / "gold.jsonl"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(ValueError):
        check_non_gold_anchors(load_draft(DRAFT_PATH), [path])


def test_cli_pending_review_creates_no_output(tmp_path: Path) -> None:
    output = tmp_path / "frozen.json"
    with pytest.raises(SystemExit) as error:
        main([
            str(DRAFT_PATH), "--gold", str(GOLD), "--review-record",
            str(PACKAGE_DIR / "review_record.template.json"), "--output", str(output),
        ])
    assert error.value.code == 2
    assert not output.exists()
    assert not output.with_suffix(".review.json").exists()


def test_cli_exports_hash_bound_m8_input_and_preserves_review_provenance(tmp_path: Path) -> None:
    draft = load_draft(DRAFT_PATH)
    review_path = _write(tmp_path / "synthetic-review.json", _synthetic_review(draft))
    output = tmp_path / "frozen.json"
    arguments = [
        str(DRAFT_PATH), "--gold", str(GOLD), "--review-record", str(review_path),
        "--output", str(output),
    ]
    assert main(arguments) == 0
    package = load_profile_checklist_package(output)
    assert package.frozen
    assert package.package_sha256 != draft.package_sha256
    assert package.physics_reviewer_ids == ["synthetic-physics"]
    assert package.author_ids == ["M7", "synthetic-leader"]
    receipt = json.loads(output.with_suffix(".review.json").read_text(encoding="utf-8"))
    assert receipt["draft_package_sha256"] == draft.package_sha256
    assert receipt["package_sha256"] == package.package_sha256
    assert receipt["reportable"] is False
    assert receipt["review_record"]["reviews"][0]["review_record_id"].startswith("synthetic-")
    original = output.read_bytes()
    with pytest.raises(SystemExit):
        main(arguments)
    assert output.read_bytes() == original

    config = JudgeConfiguration(
        config_version="synthetic-judge-config", provider="local", model_family="other-family",
        model_revision="synthetic-r1", temperature=0, seed=7, prompt_version="synthetic-v1",
        output_schema_version="1.0", local_model=True, data_approval=ApprovalStatus.NOT_REQUIRED,
    )
    for profile, checklist in zip(package.profiles, package.checklists, strict=True):
        anchor = profile.anchor_examples[0]
        item = GenerationEvaluationInput(
            evaluation_id=f"synthetic-{profile.level}", run_id=f"synthetic-{profile.level}",
            question_id=anchor.anchor_id, question=anchor.question, answer=anchor.answer,
            target_level=profile.level, condition="P1R1_combined", lambda_weight=0.2,
            generation_model_family="gpt-oss", generation_model_revision="20b",
            eligibility="full", source_artifact_sha256="a" * 64,
        )
        request = build_adaptation_request(item, profile, checklist, config)
        assert len(request.payload["checklist"]) == len(checklist.criteria)
        discrimination = build_discrimination_request(item, package.profiles, config)
        assert len(discrimination.payload["profiles"]) == 3
        for payload in (request.payload, discrimination.payload):
            assert "P1R1_combined" not in json.dumps(payload)
            assert "gpt-oss" not in json.dumps(payload)
            assert "target_level" not in payload


def _synthetic_waiver(draft: DraftProfileChecklistPackage) -> dict:
    """Test-only Leader approval with a waived physics review."""
    payload = _synthetic_review(draft)
    payload["reviews"][1] = {
        "role": "physics",
        "reviewer_id": None,
        "status": "waived",
        "review_record_id": None,
        "reviewed_at": None,
        "notes": "Synthetic Leader waiver for an offline integration test only.",
    }
    return payload


def test_leader_waiver_freezes_without_a_physics_reviewer(tmp_path: Path) -> None:
    draft = load_draft(DRAFT_PATH)
    review_path = _write(tmp_path / "synthetic-waiver.json", _synthetic_waiver(draft))
    output = tmp_path / "frozen.json"
    arguments = [
        str(DRAFT_PATH), "--gold", str(GOLD), "--review-record", str(review_path),
        "--output", str(output),
    ]
    assert main(arguments) == 0
    package = load_profile_checklist_package(output)
    assert package.physics_reviewer_ids == []
    assert package.physics_review_waiver is not None
    assert package.physics_review_waiver.waived_by == "synthetic-leader"
    assert package.physics_review_waiver.decision_record == "synthetic-test-record-leader"
    assert package.physics_review_waiver.reason.startswith("Synthetic Leader waiver")
    assert package.author_ids == ["M7", "synthetic-leader"]


@pytest.mark.parametrize("case", ["leader_pending", "named_reviewer", "no_reason", "leader_waived"])
def test_waiver_requires_leader_approval_and_names_no_reviewer(case: str) -> None:
    draft = load_draft(DRAFT_PATH)
    payload = _synthetic_waiver(draft)
    if case == "leader_pending":
        payload["reviews"][0]["status"] = "pending"
        record = ProfileReviewRecord.model_validate(payload)
        with pytest.raises(ValueError, match="Leader must approve"):
            freeze_reviewed_draft(draft, record)
        return
    if case == "named_reviewer":
        payload["reviews"][1]["reviewer_id"] = "synthetic-physics"
    elif case == "no_reason":
        payload["reviews"][1]["notes"] = None
    else:
        payload["reviews"][0] = {**payload["reviews"][1], "role": "leader"}
    with pytest.raises(ValueError):
        ProfileReviewRecord.model_validate(payload)


@pytest.mark.parametrize("case", ["neither", "both"])
def test_frozen_contract_requires_exactly_one_physics_assurance(case: str) -> None:
    draft = load_draft(DRAFT_PATH)
    package = freeze_reviewed_draft(
        draft, ProfileReviewRecord.model_validate(_synthetic_waiver(draft))
    )
    payload = package.model_dump(mode="json")
    if case == "neither":
        payload["physics_review_waiver"] = None
    else:
        payload["physics_reviewer_ids"] = ["synthetic-physics"]
    payload["package_sha256"] = profile_package_content_sha256(payload)
    with pytest.raises(ValueError, match="physics reviewer IDs or a Leader waiver"):
        type(package).model_validate(payload)


def test_waiver_field_leaves_existing_package_digests_unchanged() -> None:
    draft = load_draft(DRAFT_PATH)
    payload = draft.model_dump(mode="json")
    assert payload["physics_review_waiver"] is None
    raw = json.loads(DRAFT_PATH.read_text(encoding="utf-8"))
    assert "physics_review_waiver" not in raw
    assert profile_package_content_sha256(payload) == draft.package_sha256
