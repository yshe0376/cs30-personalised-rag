from __future__ import annotations

from pathlib import Path

import pytest

from cs30.contracts import StudentLevel
from cs30.evaluation.evidence_support import (
    build_evidence_support_request,
    score_evidence_support,
    validate_evidence_support_output,
)
from cs30.evaluation.judge_results import assemble_judge_results
from cs30.evaluation.judge_runtime import CachedJudgeRunner, request_cache_key
from cs30.evaluation.level_adaptation import (
    adaptation_evaluation_levels,
    apply_adaptation_threshold,
    build_adaptation_request,
    score_adaptation_output,
    validate_adaptation_output,
)
from cs30.evaluation.level_discrimination import (
    build_discrimination_request,
    discrimination_summary,
    validate_discrimination_output,
)
from cs30.evaluation.v2_generation_models import (
    ApprovalStatus,
    ChecklistCriterion,
    EvaluationEvidence,
    ExperimentArm,
    GenerationEvaluationInput,
    JudgeConfiguration,
    JudgeResultEnvelope,
    LevelChecklist,
    LevelGuess,
    LevelProfile,
    ProfileChecklistPackage,
)


def _configuration() -> JudgeConfiguration:
    return JudgeConfiguration(
        config_version="judge-v1",
        provider="local",
        model_family="independent-family",
        model_revision="r1",
        temperature=0,
        seed=7,
        prompt_version="prompt-v1",
        output_schema_version="1.0",
        local_model=True,
        data_approval=ApprovalStatus.NOT_REQUIRED,
    )


def _profile(level: StudentLevel) -> LevelProfile:
    return LevelProfile.model_validate(
        {
            "profile_version": "profiles-v1",
            "level": level,
            "student_positioning": f"{level.value} learner",
            "assumed_physics_background": ["motion"],
            "assumed_mathematics_background": ["algebra"],
            "acceptable_inference_span": "one inference",
            "helpful_writing_patterns": ["clear steps"],
            "harmful_writing_patterns": ["unsupported claims"],
            "anchor_examples": [
                {
                    "anchor_id": f"{level.value}-1",
                    "question": "Q1?",
                    "answer": "A1.",
                    "rationale": "level anchor",
                },
                {
                    "anchor_id": f"{level.value}-2",
                    "question": "Q2?",
                    "answer": "A2.",
                    "rationale": "level anchor",
                },
            ],
        }
    )


def _checklist(level: StudentLevel) -> LevelChecklist:
    ids = {
        StudentLevel.BEGINNER: ["B1", "B2", "B3", "B4"],
        StudentLevel.INTERMEDIATE: ["I1", "I2", "I3"],
        StudentLevel.ADVANCED: ["A1", "A2", "A3", "A4"],
    }[level]
    return LevelChecklist(
        checklist_version="checklist-v1",
        level=level,
        criteria=[
            ChecklistCriterion(
                criterion_id=criterion_id,
                level=level,
                description=f"criterion {criterion_id}",
            )
            for criterion_id in ids
        ],
    )


def _item() -> GenerationEvaluationInput:
    return GenerationEvaluationInput(
        evaluation_id="eval-1",
        run_id="run-1",
        question_id="q-1",
        question="Why does the object accelerate?",
        answer="A net force causes acceleration because velocity changes.",
        target_level=StudentLevel.BEGINNER,
        condition="P1R1_combined",
        lambda_weight=0.2,
        generation_model_family="gpt-oss",
        generation_model_revision="20b",
        eligibility="full",
        evidence=[
            EvaluationEvidence(
                evidence_id="E1",
                text="A net force produces acceleration and changes velocity.",
                rank=1,
                role="definition",
            )
        ],
        citation_ids=["E1"],
        source_artifact_sha256="a" * 64,
    )


def test_adaptation_request_is_blinded_and_output_quotes_are_verified() -> None:
    item = _item()
    checklist = _checklist(StudentLevel.BEGINNER)
    request = build_adaptation_request(
        item,
        _profile(StudentLevel.BEGINNER),
        checklist,
        _configuration(),
    )
    payload_text = str(request.payload)
    assert "P1R1" not in payload_text
    assert "lambda" not in payload_text
    assert "gpt-oss" not in payload_text
    raw = {
        "schema_version": "1.0",
        "request_id": request.request_id,
        "criteria": [
            {
                "criterion_id": criterion.criterion_id,
                "verdict": "pass",
                "exact_quote": "A net force causes acceleration",
                "reason": "The answer explains the core relation.",
            }
            for criterion in checklist.criteria
        ],
    }
    output = validate_adaptation_output(
        raw,
        request=request,
        answer=item.answer or "",
        checklist=checklist,
    )
    score = score_adaptation_output(output)
    assert score["criterion_pass_rate"] == 1.0
    assert apply_adaptation_threshold(score, threshold=0.75)["adaptation_passed"] is True
    raw["criteria"][0]["exact_quote"] = "invented quote"
    with pytest.raises(ValueError, match="exact answer substring"):
        validate_adaptation_output(
            raw,
            request=request,
            answer=item.answer or "",
            checklist=checklist,
        )


def test_adaptation_supports_cross_level_and_randomized_criterion_order() -> None:
    item = _item()
    checklist = _checklist(StudentLevel.ADVANCED)
    reverse_order = [criterion.criterion_id for criterion in reversed(checklist.criteria)]
    request = build_adaptation_request(
        item,
        _profile(StudentLevel.ADVANCED),
        checklist,
        _configuration(),
        evaluated_level=StudentLevel.ADVANCED,
        criterion_order=reverse_order,
    )
    assert [row["criterion_id"] for row in request.payload["checklist"]] == reverse_order
    assert "target_level" not in request.payload


def test_adaptation_missing_content_can_fail_without_an_invented_quote() -> None:
    item = _item()
    checklist = _checklist(StudentLevel.BEGINNER)
    request = build_adaptation_request(
        item,
        _profile(StudentLevel.BEGINNER),
        checklist,
        _configuration(),
    )
    raw = {
        "schema_version": "1.0",
        "request_id": request.request_id,
        "criteria": [
            {
                "criterion_id": criterion.criterion_id,
                "verdict": "fail",
                "exact_quote": None,
                "reason": "The required explanation is absent.",
            }
            for criterion in checklist.criteria
        ],
    }
    output = validate_adaptation_output(
        raw,
        request=request,
        answer=item.answer or "",
        checklist=checklist,
    )
    score = score_adaptation_output(output)
    assert score["fail_count"] == len(checklist.criteria)
    assert score["not_applicable_count"] == 0


def test_p0r0_and_frozen_cross_level_samples_use_all_three_checklists() -> None:
    p0r0 = _item().model_copy(update={"condition": ExperimentArm.P0R0_PLAIN})
    assert adaptation_evaluation_levels(p0r0) == tuple(StudentLevel)
    assert adaptation_evaluation_levels(
        _item(), cross_level_evaluation_ids=frozenset({"eval-1"})
    ) == tuple(StudentLevel)
    assert adaptation_evaluation_levels(_item()) == (StudentLevel.BEGINNER,)


def test_discrimination_keeps_target_hidden_and_reports_uncertain_separately() -> None:
    item = _item()
    request = build_discrimination_request(
        item,
        [_profile(level) for level in StudentLevel],
        _configuration(),
    )
    assert "target_level" not in request.payload
    output = validate_discrimination_output(
        {
            "schema_version": "1.0",
            "request_id": request.request_id,
            "predicted_level": "beginner",
            "exact_quote": "A net force causes acceleration",
            "reason": "Explains the key term directly.",
        },
        request=request,
        answer=item.answer or "",
    )
    assert output.predicted_level is LevelGuess.BEGINNER
    summary = discrimination_summary(
        [
            (StudentLevel.BEGINNER, LevelGuess.BEGINNER),
            (StudentLevel.INTERMEDIATE, LevelGuess.UNCERTAIN),
            (StudentLevel.ADVANCED, LevelGuess.INTERMEDIATE),
        ]
    )
    assert summary["uncertain_count"] == 1
    assert summary["confusion_matrix_3x3"]["advanced"]["intermediate"] == 1


def test_evidence_support_validates_claims_citations_and_source_quotes() -> None:
    item = _item()
    request = build_evidence_support_request(item, _configuration())
    assert "target_level" not in request.payload
    assert "gold" not in str(request.payload).casefold()
    raw = {
        "schema_version": "1.0",
        "request_id": request.request_id,
        "claims": [
            {
                "claim_id": "C1",
                "claim_text": "A net force causes acceleration",
                "bundle_support": "supported",
                "citation_support": "supported",
                "supporting_evidence_ids": ["E1"],
                "evidence_quotes": {"E1": "A net force produces acceleration"},
                "reason": "The supplied and cited evidence supports the relation.",
            }
        ],
    }
    output = validate_evidence_support_output(raw, request=request, item=item)
    scored = score_evidence_support(output)
    assert scored["bundle_faithfulness"] == 1.0
    assert scored["citation_support"] == 1.0
    raw["claims"][0]["evidence_quotes"] = {"E1": "not in evidence"}
    with pytest.raises(ValueError, match="not present"):
        validate_evidence_support_output(raw, request=request, item=item)


def test_evidence_support_uses_short_judge_ids_and_restores_chunk_ids() -> None:
    chunk_id = "chunk-" + "a" * 64
    item = _item().model_copy(
        update={
            "evidence": [
                EvaluationEvidence(
                    evidence_id=chunk_id,
                    text="A net force produces acceleration and changes velocity.",
                    rank=1,
                    role="definition",
                )
            ],
            "citation_ids": [chunk_id],
        }
    )
    request = build_evidence_support_request(item, _configuration())
    assert request.payload["evidence"][0]["evidence_id"] == "E1"
    output = validate_evidence_support_output(
        {
            "schema_version": "1.0",
            "request_id": request.request_id,
            "claims": [
                {
                    "claim_id": "C1",
                    "claim_text": "A net force causes acceleration",
                    "bundle_support": "supported",
                    "citation_support": "supported",
                    "supporting_evidence_ids": ["E1"],
                    "evidence_quotes": {"E1": "A net force produces acceleration"},
                    "reason": "The cited evidence supports the claim.",
                }
            ],
        },
        request=request,
        item=item,
    )
    assert output.claims[0].supporting_evidence_ids == [chunk_id]


def test_cached_runner_reuses_identical_request_and_keeps_invalid_output_unresolved(
    tmp_path: Path,
) -> None:
    item = _item()
    checklist = _checklist(StudentLevel.BEGINNER)
    request = build_adaptation_request(
        item,
        _profile(StudentLevel.BEGINNER),
        checklist,
        _configuration(),
    )
    calls = 0

    def provider(*_args: object) -> dict[str, object]:
        nonlocal calls
        calls += 1
        return {
            "schema_version": "1.0",
            "request_id": request.request_id,
            "criteria": [
                {
                    "criterion_id": criterion.criterion_id,
                    "verdict": "pass",
                    "exact_quote": "A net force causes acceleration",
                    "reason": "supported",
                }
                for criterion in checklist.criteria
            ],
        }

    validator = lambda raw: validate_adaptation_output(  # noqa: E731
        raw,
        request=request,
        answer=item.answer or "",
        checklist=checklist,
    )
    cache_path = tmp_path / "judge-cache.jsonl"
    runner = CachedJudgeRunner(cache_path)
    first = runner.run(request, _configuration(), provider, validator)
    second = runner.run(request, _configuration(), provider, validator)
    assert first.cache_hit is False
    assert second.cache_hit is True
    assert first.model_copy(update={"cache_hit": True}) == second
    assert calls == 1

    bad_request = request.model_copy(
        update={"request_id": "adaptation-bad", "input_sha256": "b" * 64}
    )
    bad_calls = 0

    def bad_provider(*_args: object) -> dict[str, object]:
        nonlocal bad_calls
        bad_calls += 1
        return {"unexpected": True}

    bad = runner.run(
        bad_request,
        _configuration(),
        bad_provider,
        lambda raw: validate_adaptation_output(
            raw,
            request=bad_request,
            answer=item.answer or "",
            checklist=checklist,
        ),
    )
    assert bad.unresolved is True
    assert bad.raw_output == {"unexpected": True}
    assert "attempt 2" in (bad.error or "")
    with cache_path.open("a", encoding="utf-8") as stream:
        stream.write(bad.model_dump_json() + "\n")
    retried = runner.run(
        bad_request,
        _configuration(),
        bad_provider,
        lambda raw: validate_adaptation_output(
            raw,
            request=bad_request,
            answer=item.answer or "",
            checklist=checklist,
        ),
    )
    assert retried.unresolved is True
    assert bad_calls == 4


def test_assemble_judge_results_validates_and_reattaches_hidden_metadata() -> None:
    item = _item()
    configuration = _configuration()
    profiles = [_profile(level) for level in StudentLevel]
    checklists = [_checklist(level) for level in StudentLevel]
    package = ProfileChecklistPackage(
        package_version="profiles-v1",
        generation_guidance_version="guidance-v1",
        generation_guidance_consistency="consistent",
        author_ids=["leader"],
        physics_reviewer_ids=["reviewer"],
        profiles=profiles,
        checklists=checklists,
        package_sha256="d" * 64,
    )
    adaptation_request = build_adaptation_request(item, profiles[0], checklists[0], configuration)
    discrimination_request = build_discrimination_request(item, profiles, configuration)
    evidence_request = build_evidence_support_request(item, configuration)
    adaptation_output = {
        "schema_version": "1.0",
        "request_id": adaptation_request.request_id,
        "criteria": [
            {
                "criterion_id": criterion.criterion_id,
                "verdict": "pass",
                "exact_quote": "A net force causes acceleration",
                "reason": "matched",
            }
            for criterion in checklists[0].criteria
        ],
    }
    discrimination_output = {
        "schema_version": "1.0",
        "request_id": discrimination_request.request_id,
        "predicted_level": "beginner",
        "exact_quote": "A net force causes acceleration",
        "reason": "matched",
    }
    evidence_output = {
        "schema_version": "1.0",
        "request_id": evidence_request.request_id,
        "claims": [
            {
                "claim_id": "C1",
                "claim_text": "A net force causes acceleration",
                "bundle_support": "supported",
                "citation_support": "supported",
                "supporting_evidence_ids": ["E1"],
                "evidence_quotes": {"E1": "A net force produces acceleration"},
                "reason": "matched",
            }
        ],
    }
    envelopes = {
        request.request_id: JudgeResultEnvelope(
            task=request.task,
            request_id=request.request_id,
            cache_key=request_cache_key(request),
            judge_config_version=configuration.config_version,
            output=output,
            completed_at_utc="2026-10-20T00:00:00+00:00",
        )
        for request, output in (
            (adaptation_request, adaptation_output),
            (discrimination_request, discrimination_output),
            (evidence_request, evidence_output),
        )
    }
    result = assemble_judge_results([item], package, configuration, envelopes)
    assert result["unresolved"] == []
    assert result["adaptation"][0]["condition"] == "P1R1_combined"
    assert result["discrimination"][0]["predicted_level"] == "beginner"
    assert result["evidence_support"][0]["citation_support"] == 1.0
