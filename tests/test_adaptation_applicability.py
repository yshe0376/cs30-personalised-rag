from __future__ import annotations

import copy
import json
import runpy
from pathlib import Path

import pytest

from cs30.evaluation.adaptation_applicability import (
    FROZEN_PACKAGE_SHA256,
    always_assessed_ids,
    make_applicability_binding,
)
from cs30.evaluation.judge_runtime import CachedJudgeRunner, validate_output_against_request
from cs30.evaluation.level_adaptation import build_adaptation_request, validate_adaptation_output
from cs30.evaluation.level_profiles import (
    load_profile_checklist_package,
    profile_package_content_sha256,
)
from cs30.evaluation.v2_generation_cli import main
from cs30.evaluation.v2_generation_models import (
    ApprovalStatus,
    GenerationEvaluationInput,
    JudgeConfiguration,
)

ROOT = Path(__file__).parents[1]


def case(level="beginner", *, bound=True, reverse=False):
    package = load_profile_checklist_package(
        ROOT / "docs/evaluation/level-profile-v1/profile_checklist.frozen.json"
    )
    profile = next(row for row in package.profiles if row.level.value == level)
    checklist = next(row for row in package.checklists if row.level.value == level)
    item = GenerationEvaluationInput(
        evaluation_id="e-1",
        run_id="r-1",
        question_id="q-1",
        question="Name the concept.",
        answer="A clear answer.",
        target_level=level,
        condition="P1R1_combined",
        lambda_weight=0.1,
        generation_model_family="gpt-oss",
        generation_model_revision="20b",
        eligibility="full",
        source_artifact_sha256="a" * 64,
    )
    configuration = JudgeConfiguration(
        config_version="test",
        provider="local",
        model_family="independent",
        model_revision="r1",
        temperature=0,
        prompt_version="test",
        output_schema_version="1.0",
        local_model=True,
        data_approval="not_required",
    )
    order = [row.criterion_id for row in checklist.criteria]
    request = build_adaptation_request(
        item,
        profile,
        checklist,
        configuration,
        profile_package=package if bound else None,
        criterion_order=list(reversed(order)) if reverse else order,
    )
    raw = {
        "schema_version": "1.0",
        "request_id": request.request_id,
        "criteria": [
            {
                "criterion_id": row.criterion_id,
                "verdict": "pass",
                "exact_quote": item.answer,
                "reason": "Fixture verdict.",
            }
            for row in checklist.criteria
        ],
    }
    return package, checklist, configuration, request, raw


def set_na(raw, criterion):
    next(row for row in raw["criteria"] if row["criterion_id"] == criterion).update(
        verdict="not_applicable", exact_quote=None
    )


@pytest.mark.parametrize("criterion", ["B1", "B2", "B4", "I1", "I2", "I3", "A1", "A4"])
def test_all_eight_always_assessed_criteria_reject_na_in_both_layers(criterion):
    level = {"B": "beginner", "I": "intermediate", "A": "advanced"}[criterion[0]]
    _, checklist, _, request, raw = case(level)
    set_na(raw, criterion)
    with pytest.raises(ValueError, match=f"always-assessed.*{criterion}"):
        validate_output_against_request(raw, request)
    with pytest.raises(ValueError, match=f"always-assessed.*{criterion}"):
        validate_adaptation_output(
            raw, request=request, answer="A clear answer.", checklist=checklist
        )


@pytest.mark.parametrize("criterion", ["B3", "A2", "A3"])
def test_optional_criteria_still_allow_na(criterion):
    _, checklist, _, request, raw = case("beginner" if criterion == "B3" else "advanced")
    set_na(raw, criterion)
    assert validate_output_against_request(raw, request)
    assert validate_adaptation_output(
        raw, request=request, answer="A clear answer.", checklist=checklist
    )


@pytest.mark.parametrize("repairs", [False, True])
def test_invalid_na_uses_existing_retry_and_stays_unresolved_if_not_repaired(tmp_path, repairs):
    _, _, configuration, request, valid = case()
    calls = []

    def provider(attempt_request, config):
        calls.append(attempt_request.system_instruction)
        raw = copy.deepcopy(valid)
        if len(calls) == 1 or not repairs:
            set_na(raw, "B4")
        return raw

    cache = tmp_path / "cache.jsonl"
    result = CachedJudgeRunner(cache, judge_execution_id="policy-test", max_attempts=2).run(
        request, configuration, provider, lambda raw: validate_output_against_request(raw, request)
    )
    assert len(calls) == 2
    assert "always-assessed" in calls[1]
    assert result.unresolved is (not repairs)
    if not repairs:
        assert result.output is None
        assert not cache.exists()
        assert (
            next(row for row in result.raw_output["criteria"] if row["criterion_id"] == "B4")[
                "verdict"
            ]
            == "not_applicable"
        )
    else:
        assert cache.exists()


def test_binding_changes_request_identity_and_cannot_be_reused_for_another_package():
    package, checklist, _, request, _ = case()
    _, _, _, legacy, _ = case(bound=False)
    assert package.package_sha256 == FROZEN_PACKAGE_SHA256
    assert request.request_id != legacy.request_id
    assert request.input_sha256 != legacy.input_sha256
    with pytest.raises(ValueError, match="package-bound"):
        always_assessed_ids(legacy)
    changed = package.model_copy(update={"package_version": "another-package"})
    changed = changed.model_copy(
        update={"package_sha256": profile_package_content_sha256(changed.model_dump(mode="json"))}
    )
    profile = next(row for row in changed.profiles if row.level == checklist.level)
    with pytest.raises(ValueError, match="no reviewed"):
        make_applicability_binding(changed, profile, checklist)
    tampered = copy.deepcopy(request.payload)
    tampered["applicability_policy"]["profile_package_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="no reviewed"):
        always_assessed_ids(request.model_copy(update={"payload": tampered}))


@pytest.mark.parametrize("field", ["checklist", "target_profile"])
def test_binding_checks_exact_frozen_content_not_only_criterion_ids(field):
    _, _, _, request, _ = case()
    payload = copy.deepcopy(request.payload)
    if field == "checklist":
        payload[field][0]["description"] += " Changed."
    else:
        payload[field]["student_positioning"] += " Changed."
    with pytest.raises(ValueError, match="does not match the bound frozen"):
        always_assessed_ids(request.model_copy(update={"payload": payload}))


def test_reverse_criterion_order_keeps_the_same_bound_policy():
    _, _, _, request, _ = case(reverse=True)
    assert always_assessed_ids(request) == frozenset({"B1", "B2", "B4"})


def test_unbound_real_checklist_is_rejected_before_api_client_construction(tmp_path, monkeypatch):
    import cs30.evaluation.v2_generation_cli as module

    _, _, config, request, _ = case(bound=False)
    config = config.model_copy(
        update={
            "provider": "gemini",
            "model_family": "gemini",
            "thinking_level": "low",
            "local_model": False,
            "data_approval": ApprovalStatus.APPROVED,
        }
    )
    requests = tmp_path / "requests.jsonl"
    requests.write_text(request.model_dump_json() + "\n", encoding="utf-8")
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config.model_dump(mode="json")), encoding="utf-8")

    def forbidden(*args, **kwargs):
        pytest.fail("invalid policy must be rejected before constructing an API client")

    monkeypatch.setattr(module, "GeminiJudgeClient", forbidden)
    with pytest.raises(SystemExit) as exc:
        main(
            [
                "run-judge-requests",
                "--requests",
                str(requests),
                "--judge-config",
                str(config_path),
                "--cache",
                str(tmp_path / "cache"),
                "--output",
                str(tmp_path / "output"),
                "--judge-execution-id",
                "unbound-test",
            ]
        )
    assert exc.value.code == 2


def test_saved_trial_replay_is_file_only_and_preserves_originals(tmp_path, monkeypatch):
    from cs30.evaluation.gemini_judge_client import GeminiJudgeClient

    def forbidden(*args, **kwargs):
        pytest.fail("Offline adaptation replay cannot construct an API client")

    monkeypatch.setattr(GeminiJudgeClient, "__init__", forbidden)
    namespace = runpy.run_path(str(ROOT / "scripts/revalidate_adaptation_trial.py"))
    root = ROOT / "docs/results/m8_judge_trial_20261027"
    profiles = ROOT / "docs/evaluation/level-profile-v1/profile_checklist.frozen.json"
    report = namespace["replay"](root, profiles)
    assert report["api_calls"] == report["retry_calls"] == report["new_cost_usd"] == 0
    assert report["summary"]["high"] == {
        "requests": 30,
        "would_be_rejected": 6,
        "always_assessed_verdicts": 80,
        "invalid_verdicts": {"B4": 6},
    }
    assert report["summary"]["low"] == {
        "requests": 30,
        "would_be_rejected": 5,
        "always_assessed_verdicts": 80,
        "invalid_verdicts": {"B4": 5},
    }
    assert report["profile_package_sha256"] == FROZEN_PACKAGE_SHA256
    with pytest.raises(SystemExit):
        namespace["main"](
            [
                "--trial-root",
                str(root),
                "--profiles",
                str(profiles),
                "--out",
                str(root / "overwrite"),
            ]
        )


def test_prepare_cli_threads_frozen_package_binding_into_real_requests(tmp_path, monkeypatch):
    import cs30.evaluation.v2_generation_cli as module

    def forbidden(*args, **kwargs):
        pytest.fail("Request preparation cannot construct an API client")

    monkeypatch.setattr(module, "GeminiJudgeClient", forbidden)
    trial = ROOT / "docs/results/m8_judge_trial_20261027"
    output = tmp_path / "requests.jsonl"
    assert (
        main(
            [
                "prepare-judge-requests",
                "--inputs",
                str(trial / "subset/llama/inputs.jsonl"),
                "--profiles",
                str(ROOT / "docs/evaluation/level-profile-v1/profile_checklist.frozen.json"),
                "--judge-config",
                str(trial / "thinking-low/judge-config.json"),
                "--task",
                "adaptation",
                "--output",
                str(output),
            ]
        )
        == 0
    )
    from cs30.evaluation.v2_generation_models import JudgeRequest

    rows = [
        JudgeRequest.model_validate_json(line)
        for line in output.read_text(encoding="utf-8").splitlines()
    ]
    assert rows
    for row in rows:
        assert (
            row.payload["applicability_policy"]["profile_package_sha256"] == FROZEN_PACKAGE_SHA256
        )
        assert always_assessed_ids(row)
