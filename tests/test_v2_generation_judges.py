from __future__ import annotations

from pathlib import Path

import pytest

import cs30.evaluation.judge_runtime as judge_runtime
from cs30.contracts import StudentLevel
from cs30.evaluation.evidence_support import (
    build_evidence_support_request,
    score_evidence_support,
    validate_evidence_support_output,
)
from cs30.evaluation.judge_results import assemble_judge_results
from cs30.evaluation.judge_runtime import (
    _ONLINE_OUTPUT_SCHEMAS,
    CachedJudgeRunner,
    StructuredJsonJudgeProvider,
    _render_judge_prompt,
    request_cache_key,
    validate_output_against_request,
)
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
from cs30.evaluation.level_profiles import profile_package_content_sha256
from cs30.evaluation.v2_generation_models import (
    AdaptationJudgeOutput,
    ApprovalStatus,
    ChecklistCriterion,
    DiscriminationJudgeOutput,
    EvaluationEvidence,
    EvidenceSupportJudgeOutput,
    ExperimentArm,
    GenerationEvaluationInput,
    JudgeConfiguration,
    JudgeResultEnvelope,
    JudgeTask,
    LevelChecklist,
    LevelGuess,
    LevelProfile,
    ProfileChecklistPackage,
)
from cs30.generation.client import LLMResponse, TokenUsage


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


def test_online_judge_schemas_require_every_property_and_forbid_extra_fields() -> None:
    def assert_strict_objects(node: object) -> None:
        if isinstance(node, dict):
            if node.get("type") == "object":
                properties = node.get("properties")
                assert isinstance(properties, dict)
                assert node.get("required") == list(properties)
                assert node.get("additionalProperties") is False
            for value in node.values():
                assert_strict_objects(value)
        elif isinstance(node, list):
            for value in node:
                assert_strict_objects(value)

    for schema in _ONLINE_OUTPUT_SCHEMAS.values():
        assert_strict_objects(schema)
        assert "default" not in str(schema)

    adaptation_item = _ONLINE_OUTPUT_SCHEMAS[JudgeTask.ADAPTATION]["properties"][
        "criteria"
    ]["items"]
    discrimination = _ONLINE_OUTPUT_SCHEMAS[JudgeTask.DISCRIMINATION]
    evidence_claim = _ONLINE_OUTPUT_SCHEMAS[JudgeTask.EVIDENCE_SUPPORT]["properties"][
        "claims"
    ]["items"]
    assert "exact_quote" in adaptation_item["required"]
    assert "exact_quote" in discrimination["required"]
    assert "supporting_evidence_ids" in evidence_claim["required"]
    assert "evidence_quotes" in evidence_claim["required"]
    assert evidence_claim["properties"]["evidence_quotes"]["type"] == "array"


def test_online_evidence_quote_rows_are_normalized_before_local_validation() -> None:
    item = _item()
    request = build_evidence_support_request(item, _configuration())
    output = validate_output_against_request(
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
                    "evidence_quotes": [
                        {
                            "evidence_id": "E1",
                            "quote": "A net force produces acceleration",
                        }
                    ],
                    "reason": "The cited evidence supports the claim.",
                }
            ],
        },
        request,
    )
    assert output.claims[0].evidence_quotes == {
        "E1": "A net force produces acceleration"
    }


@pytest.mark.parametrize(
    ("model", "raw"),
    [
        (
            AdaptationJudgeOutput,
            {
                "schema_version": "1.0",
                "request_id": "request-1",
                "criteria": [
                    {
                        "criterion_id": "B1",
                        "verdict": "fail",
                        "reason": "The criterion was not met.",
                    }
                ],
            },
        ),
        (
            DiscriminationJudgeOutput,
            {
                "schema_version": "1.0",
                "request_id": "request-1",
                "predicted_level": "uncertain",
                "reason": "No level was clearly supported.",
            },
        ),
        (
            EvidenceSupportJudgeOutput,
            {
                "schema_version": "1.0",
                "request_id": "request-1",
                "claims": [
                    {
                        "claim_id": "C1",
                        "claim_text": "A claim.",
                        "bundle_support": "unsupported",
                        "citation_support": "unsupported",
                        "reason": "No supplied evidence supports it.",
                    }
                ],
            },
        ),
    ],
)
def test_local_models_reject_omitted_online_required_fields(model, raw) -> None:
    with pytest.raises(ValueError):
        model.model_validate(raw)


def test_online_evidence_quote_rows_preserve_multiple_excerpts_per_id() -> None:
    raw = {
        "schema_version": "1.0",
        "request_id": "request-1",
        "claims": [
            {
                "claim_id": "C1",
                "claim_text": "A claim.",
                "bundle_support": "supported",
                "citation_support": "supported",
                "supporting_evidence_ids": ["E1"],
                "evidence_quotes": [
                    {"evidence_id": "E1", "quote": "first"},
                    {"evidence_id": "E1", "quote": "second"},
                ],
                "reason": "Supported.",
            }
        ],
    }
    output = EvidenceSupportJudgeOutput.model_validate(raw)
    assert output.claims[0].evidence_quotes == {"E1": "first … second"}


def test_adaptation_rejects_a_quote_for_not_applicable() -> None:
    with pytest.raises(ValueError, match="require a null quote"):
        AdaptationJudgeOutput.model_validate(
            {
                "schema_version": "1.0",
                "request_id": "request-1",
                "criteria": [
                    {
                        "criterion_id": "B1",
                        "verdict": "not_applicable",
                        "exact_quote": "invented support",
                        "reason": "Not relevant.",
                    }
                ],
            }
        )


def test_evidence_support_rejects_support_ids_for_an_unsupported_claim() -> None:
    item = _item()
    request = build_evidence_support_request(item, _configuration())
    raw = {
        "schema_version": "1.0",
        "request_id": request.request_id,
        "claims": [
            {
                "claim_id": "C1",
                "claim_text": "A net force causes acceleration",
                "bundle_support": "unsupported",
                "citation_support": "unsupported",
                "supporting_evidence_ids": ["E1"],
                "evidence_quotes": {
                    "E1": "A net force produces acceleration",
                },
                "reason": "The evidence does not support the complete claim.",
            }
        ],
    }
    with pytest.raises(ValueError, match="must not identify supporting evidence"):
        validate_evidence_support_output(raw, request=request, item=item)


def test_structured_provider_sends_the_handwritten_strict_schema() -> None:
    request = build_discrimination_request(
        _item(),
        [_profile(level) for level in StudentLevel],
        _configuration(),
    )

    class CapturingClient:
        def __init__(self) -> None:
            self.text_format = None

        def complete(self, _prompt, text_format):
            self.text_format = text_format
            return LLMResponse(
                text=(
                    '{"schema_version":"1.0","request_id":"'
                    + request.request_id
                    + '","predicted_level":"uncertain",'
                    '"exact_quote":null,"reason":"unclear"}'
                ),
                model="independent-family",
                usage=TokenUsage(),
                response_id="response-1",
                latency_ms=1.0,
            )

    client = CapturingClient()
    result = StructuredJsonJudgeProvider(client)(request, _configuration())
    assert result.output["exact_quote"] is None
    assert client.text_format == {
        "type": "json_schema",
        "name": "discrimination_judge_output",
        "strict": True,
        "schema": _ONLINE_OUTPUT_SCHEMAS[JudgeTask.DISCRIMINATION],
    }


def test_cached_runner_adds_validation_error_to_the_retry_prompt(tmp_path: Path) -> None:
    item = _item()
    checklist = _checklist(StudentLevel.BEGINNER)
    request = build_adaptation_request(
        item,
        _profile(StudentLevel.BEGINNER),
        checklist,
        _configuration(),
    )
    prompts: list[str] = []

    def provider(attempt_request, _configuration):
        prompts.append(attempt_request.system_instruction)
        criteria = [
            {
                "criterion_id": criterion.criterion_id,
                "verdict": "pass",
                "reason": "supported",
                **(
                    {"exact_quote": "A net force causes acceleration"}
                    if len(prompts) == 2
                    else {}
                ),
            }
            for criterion in checklist.criteria
        ]
        return {
            "schema_version": "1.0",
            "request_id": request.request_id,
            "criteria": criteria,
        }

    result = CachedJudgeRunner(
        tmp_path / "cache.jsonl",
        judge_execution_id="execution-one",
        model_digest="weights-one",
        context_window=32768,
    ).run(
        request,
        _configuration(),
        provider,
        lambda raw: validate_adaptation_output(
            raw,
            request=request,
            answer=item.answer or "",
            checklist=checklist,
        ),
    )
    assert result.unresolved is False
    assert len(prompts) == 2
    assert "REPAIR_REQUEST:" not in prompts[0]
    assert "REPAIR_REQUEST:" in prompts[1]
    assert "exact_quote" in prompts[1]
    assert "PREVIOUS_OUTPUT:" in prompts[1]
    rendered_retry = _render_judge_prompt(
        request.model_copy(update={"system_instruction": prompts[1]})
    )
    assert rendered_retry.index("REQUEST_PAYLOAD_JSON:") < rendered_retry.index(
        "REPAIR_REQUEST:"
    )
    assert rendered_retry.rstrip().endswith("Return one corrected JSON object only.")


def test_cached_runner_does_not_repair_a_provider_failure(tmp_path: Path) -> None:
    request = build_discrimination_request(
        _item(),
        [_profile(level) for level in StudentLevel],
        _configuration(),
    )
    prompts: list[str] = []

    def provider(attempt_request, _configuration):
        prompts.append(attempt_request.system_instruction)
        if len(prompts) == 1:
            raise TimeoutError("temporary timeout")
        return {
            "schema_version": "1.0",
            "request_id": request.request_id,
            "predicted_level": "uncertain",
            "exact_quote": None,
            "reason": "The answer does not clearly indicate one level.",
        }

    result = CachedJudgeRunner(
        tmp_path / "cache.jsonl",
        judge_execution_id="execution-one",
    ).run(
        request,
        _configuration(),
        provider,
        lambda raw: validate_discrimination_output(
            raw,
            request=request,
            answer=_item().answer or "",
        ),
    )
    assert result.unresolved is False
    assert prompts == [request.system_instruction, request.system_instruction]


def test_cached_runner_reuses_identical_request_and_keeps_invalid_output_unresolved(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
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
    runner = CachedJudgeRunner(
        cache_path,
        judge_execution_id="execution-one",
        model_digest="weights-one",
        context_window=32768,
    )

    def reject_cache_reload(_path: Path) -> dict[str, JudgeResultEnvelope]:
        raise AssertionError("judge cache must be loaded once per runner")

    monkeypatch.setattr(judge_runtime, "_load_cache", reject_cache_reload)
    first = runner.run(request, _configuration(), provider, validator)
    second = runner.run(request, _configuration(), provider, validator)
    assert first.cache_hit is False
    assert second.cache_hit is False
    assert first == second
    assert first.judge_execution_id == "execution-one"
    assert first.model_digest == "weights-one"
    assert first.context_window == 32768
    assert calls == 1
    monkeypatch.undo()

    resumed = CachedJudgeRunner(
        cache_path,
        judge_execution_id="execution-one",
        model_digest="weights-one",
        context_window=32768,
        require_current_execution_cache=True,
    ).run(request, _configuration(), provider, validator)
    assert resumed.cache_hit is False
    assert calls == 1

    reused = CachedJudgeRunner(
        cache_path,
        judge_execution_id="execution-two",
        model_digest="weights-one",
        context_window=32768,
    ).run(request, _configuration(), provider, validator)
    assert reused.cache_hit is True
    assert reused.judge_execution_id == "execution-one"
    assert calls == 1

    with pytest.raises(ValueError, match="another or unaudited execution"):
        CachedJudgeRunner(
            cache_path,
            judge_execution_id="execution-two",
            model_digest="weights-one",
            context_window=32768,
            require_current_execution_cache=True,
        )

    with pytest.raises(ValueError, match="resume runtime differs"):
        CachedJudgeRunner(
            cache_path,
            judge_execution_id="execution-one",
            model_digest="changed-weights",
            context_window=32768,
        ).run(request, _configuration(), provider, validator)

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
    package = package.model_copy(
        update={"package_sha256": profile_package_content_sha256(package.model_dump(mode="json"))}
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
