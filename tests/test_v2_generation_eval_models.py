from __future__ import annotations

import json
from pathlib import Path

import pytest

from cs30.contracts import StudentLevel
from cs30.evaluation.level_profiles import (
    candidate_role_richness,
    eligible_levels,
    load_eligibility_package,
    load_profile_checklist_package,
    profile_package_content_sha256,
)
from cs30.evaluation.v2_generation_models import (
    ApprovalStatus,
    EvaluationEvidence,
    EvaluationMode,
    GenerationEvaluationInput,
    JudgeConfiguration,
    PersonalisationEligibility,
    canonical_model_family,
)


def test_gemini_revisions_share_one_model_family() -> None:
    assert canonical_model_family("gemini") == "gemini"
    assert canonical_model_family("models/gemini-3.1-flash-lite") == "gemini"
    assert canonical_model_family("gemini-3.8-pro") == "gemini"


def _profile(level: str) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "profile_version": "profiles-v1",
        "level": level,
        "student_positioning": f"Frozen {level} learner position.",
        "assumed_physics_background": ["motion"],
        "assumed_mathematics_background": ["algebra"],
        "terms_allowed_without_explanation": ["force"],
        "acceptable_inference_span": "One justified inference.",
        "omittable_intermediate_steps": ["simple arithmetic"],
        "helpful_writing_patterns": ["state the governing principle"],
        "harmful_writing_patterns": ["unsupported conclusion"],
        "anchor_examples": [
            {
                "anchor_id": f"{level}-a",
                "question": "Anchor question A?",
                "answer": "Anchor answer A.",
                "rationale": "Shows the level.",
                "is_gold": False,
            },
            {
                "anchor_id": f"{level}-b",
                "question": "Anchor question B?",
                "answer": "Anchor answer B.",
                "rationale": "Shows the level.",
                "is_gold": False,
            },
        ],
    }


def _package_payload() -> dict[str, object]:
    criterion_ids = {
        "beginner": ["B1", "B2", "B3", "B4"],
        "intermediate": ["I1", "I2", "I3"],
        "advanced": ["A1", "A2", "A3", "A4"],
    }
    payload: dict[str, object] = {
        "schema_version": "1.0",
        "package_version": "level-package-v1",
        "generation_guidance_version": "generation-guidance-v1",
        "profiles_independent_of_generation_guidance": True,
        "generation_guidance_consistency": "consistent",
        "generation_guidance_mismatch_notes": None,
        "author_ids": ["leader", "generation-owner"],
        "physics_reviewer_ids": ["physics-reviewer"],
        "frozen": True,
        "profiles": [_profile(level) for level in criterion_ids],
        "checklists": [
            {
                "schema_version": "1.0",
                "checklist_version": "checklists-v1",
                "level": level,
                "criteria": [
                    {
                        "criterion_id": criterion_id,
                        "level": level,
                        "description": f"Frozen requirement {criterion_id}.",
                    }
                    for criterion_id in ids
                ],
            }
            for level, ids in criterion_ids.items()
        ],
    }
    payload["package_sha256"] = profile_package_content_sha256(payload)
    return payload


def _write_json(path: Path, payload: object) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_profile_package_loads_and_rejects_tampering(tmp_path: Path) -> None:
    payload = _package_payload()
    path = _write_json(tmp_path / "profiles.json", payload)
    package = load_profile_checklist_package(path)
    assert {profile.level.value for profile in package.profiles} == {
        "beginner",
        "intermediate",
        "advanced",
    }

    payload["profiles"][0]["student_positioning"] = "Changed after freezing."  # type: ignore[index]
    _write_json(path, payload)
    with pytest.raises(ValueError, match="hash mismatch"):
        load_profile_checklist_package(path)


def test_eligibility_sidecar_requires_exact_coverage_and_resolved_values(
    tmp_path: Path,
) -> None:
    path = tmp_path / "eligibility.jsonl"
    rows = [
        {
            "schema_version": "1.0",
            "question_id": "q-1",
            "eligibility": "full",
            "reason": "Three levels should differ.",
            "annotator_id": "m3",
            "calibration_version": "eligibility-calibration-v1",
        },
        {
            "schema_version": "1.0",
            "question_id": "q-2",
            "eligibility": "pending",
            "reason": "Needs review.",
            "annotator_id": "m3",
            "calibration_version": "eligibility-calibration-v1",
        },
    ]
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    package = load_eligibility_package(
        path,
        package_version="eligibility-v1",
        gold_version="gold-v1",
        gold_sha256="a" * 64,
        calibration_question_count=15,
        leader_calibration_record_sha256="b" * 64,
        label_provenance_record_sha256="c" * 64,
        expected_question_ids={"q-1", "q-2"},
    )
    assert len(package.records) == 2
    with pytest.raises(ValueError, match="pending IDs"):
        load_eligibility_package(
            path,
            package_version="eligibility-v1",
            gold_version="gold-v1",
            gold_sha256="a" * 64,
            calibration_question_count=15,
            leader_calibration_record_sha256="b" * 64,
            label_provenance_record_sha256="c" * 64,
            expected_question_ids={"q-1", "q-2"},
            require_resolved=True,
        )


def test_generation_evaluation_input_enforces_failure_and_citation_boundaries() -> None:
    base = {
        "schema_version": "1.0",
        "evaluation_id": "eval-1",
        "run_id": "run-1",
        "question_id": "q-1",
        "question": "Why does the object accelerate?",
        "answer": "A net force causes acceleration.",
        "target_level": "beginner",
        "condition": "P1R1_combined",
        "lambda_weight": 0.2,
        "generation_model_family": "gpt-oss",
        "generation_model_revision": "20b",
        "eligibility": "full",
        "evidence": [
            {
                "evidence_id": "E1",
                "text": "A net force produces acceleration.",
                "rank": 1,
                "role": "definition",
            }
        ],
        "citation_ids": ["E1"],
        "source_artifact_sha256": "b" * 64,
    }
    item = GenerationEvaluationInput.model_validate(base)
    assert item.answer is not None
    with pytest.raises(ValueError, match="actually sent"):
        GenerationEvaluationInput.model_validate({**base, "citation_ids": ["unknown"]})
    with pytest.raises(ValueError, match="must not contain an answer"):
        GenerationEvaluationInput.model_validate(
            {**base, "technical_failure": True, "failure_reason": "timeout"}
        )


def test_judge_configuration_blocks_unapproved_or_same_family_use() -> None:
    configuration = JudgeConfiguration(
        config_version="judge-v1",
        provider="external",
        model_family="judge-family",
        model_revision="judge-r1",
        temperature=0,
        prompt_version="prompt-v1",
        output_schema_version="1.0",
        local_model=False,
        data_approval=ApprovalStatus.PENDING,
    )
    with pytest.raises(ValueError, match="approved data transfer"):
        configuration.assert_allowed("gpt-oss", EvaluationMode.DEVELOPMENT)

    same_family = configuration.model_copy(
        update={"local_model": True, "data_approval": "not_required", "model_family": "gpt-oss"}
    )
    with pytest.raises(ValueError, match="must differ"):
        same_family.assert_allowed("gpt-oss", EvaluationMode.DEVELOPMENT)
    with pytest.raises(ValueError, match="must differ"):
        same_family.assert_allowed("gpt-oss-120b", EvaluationMode.DEVELOPMENT)

    with pytest.raises(ValueError, match="overlap requires disclosure"):
        JudgeConfiguration(
            config_version="judge-v1",
            provider="local",
            model_family="qwen",
            model_revision="r1",
            temperature=0,
            prompt_version="prompt-v1",
            output_schema_version="1.0",
            local_model=True,
            data_approval=ApprovalStatus.NOT_REQUIRED,
            role_label_model_families=["qwen"],
        )
    with pytest.raises(ValueError, match="freeze thinking_level"):
        JudgeConfiguration(
            config_version="gemini-v1",
            provider="gemini",
            model_family="gemini",
            model_revision="gemini-3.1-flash-lite",
            temperature=1,
            prompt_version="prompt-v1",
            output_schema_version="1.0",
            local_model=False,
            data_approval=ApprovalStatus.APPROVED,
        )


def test_endpoint_only_keeps_all_levels_in_main_result() -> None:
    assert eligible_levels(PersonalisationEligibility.ENDPOINT_ONLY) == frozenset(StudentLevel)


def test_candidate_role_richness_uses_top_twenty_and_level_specific_roles() -> None:
    evidence = [
        EvaluationEvidence(evidence_id="E1", text="definition", rank=1, role="definition"),
        EvaluationEvidence(evidence_id="E2", text="boundary", rank=2, role="boundary"),
    ]
    result = candidate_role_richness(
        [("q-1", level, evidence) for level in StudentLevel],
    )
    assert result["summary"]["beginner"]["available"] == 1
    assert result["summary"]["intermediate"]["available"] == 0
    assert result["summary"]["advanced"]["available"] == 1
