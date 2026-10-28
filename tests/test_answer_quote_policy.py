"""Answer-quote policy v2: formatting-only normalisation, shared by every judge task."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from cs30.contracts import StudentLevel
from cs30.evaluation.evidence_quotes import ANSWER_QUOTE_POLICY, quote_in_answer
from cs30.evaluation.evidence_support import (
    build_evidence_support_request,
    validate_evidence_support_output,
)
from cs30.evaluation.judge_runtime import (
    CachedJudgeRunner,
    request_cache_key,
    validate_output_against_request,
)
from cs30.evaluation.level_adaptation import build_adaptation_request, validate_adaptation_output
from cs30.evaluation.level_discrimination import (
    build_discrimination_request,
    validate_discrimination_output,
)
from cs30.evaluation.open_answer_models import JudgeAssessment, OpenAnswerRubric
from cs30.evaluation.open_answer_scoring import validate_assessment
from cs30.evaluation.v2_generation_models import (
    ApprovalStatus,
    ChecklistCriterion,
    EvaluationEvidence,
    GenerationEvaluationInput,
    JudgeConfiguration,
    JudgeResultEnvelope,
    LevelChecklist,
    LevelProfile,
    SupportVerdict,
)

# Typical model typography: narrow no-break space (U+202F), curly apostrophe (U+2019)
# and a non-breaking hyphen (U+2011).
ANSWER = (
    "A net force causes acceleration because the object’s velocity changes. "
    "The speed is 5 m/s and the change is non‑zero."
)
PLAIN_QUOTE = "the object's velocity changes"


@pytest.mark.parametrize(
    ("quote", "answer", "accepted"),
    [
        ("velocity changes", "velocity changes", True),  # narrow no-break space
        ("velocity changes", "velocity changes", True),  # no-break space
        ("velocity  changes", "velocity\nchanges", True),  # whitespace runs and newlines
        ("the object's mass", "the object’s mass", True),  # curly apostrophe
        ('"net force"', "“net force”", True),  # curly double quotes
        ("non-zero", "non‑zero", True),  # non-breaking hyphen
        ("café", "café", True),  # NFC composition
        ("velocity changes", "velocity changes", True),
        ("A net force ... velocity changes", "A net force causes velocity changes", False),
        ("A net force … velocity changes", "A net force causes velocity changes", False),
        ("a force makes it speed up", "A net force causes acceleration", False),  # reworded
        ("a net force", "A net force", False),  # case is not folded
        ("5 m/s", "6 m/s", False),  # numbers are not rewritten
        ("x - y", "x − y", False),  # minus sign is a math symbol, not a hyphen
        ("", "anything", False),
        ("   ", "anything", False),
    ],
)
def test_quote_in_answer_unifies_formatting_but_not_content(quote, answer, accepted):
    assert quote_in_answer(quote, answer) is accepted


def test_policy_version_is_named():
    assert ANSWER_QUOTE_POLICY == "answer-quote-v2"


# --- fixtures shared by the judge tasks ------------------------------------------------


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
                    "anchor_id": f"{level.value}-{n}",
                    "question": "Q?",
                    "answer": "A.",
                    "rationale": "level anchor",
                }
                for n in (1, 2)
            ],
        }
    )


def _checklist() -> LevelChecklist:
    return LevelChecklist(
        checklist_version="checklist-v1",
        level=StudentLevel.BEGINNER,
        criteria=[
            ChecklistCriterion(
                criterion_id=criterion_id,
                level=StudentLevel.BEGINNER,
                description=f"criterion {criterion_id}",
            )
            for criterion_id in ("B1", "B2", "B3", "B4")
        ],
    )


def _item() -> GenerationEvaluationInput:
    return GenerationEvaluationInput(
        evaluation_id="eval-1",
        run_id="run-1",
        question_id="q-1",
        question="Why does the object accelerate?",
        answer=ANSWER,
        target_level=StudentLevel.BEGINNER,
        condition="P1R1_combined",
        lambda_weight=0.2,
        generation_model_family="gpt-oss",
        generation_model_revision="20b",
        eligibility="full",
        evidence=[
            EvaluationEvidence(
                evidence_id="E1",
                text="A net force produces acceleration and changes the velocity of an object.",
                rank=1,
                role="definition",
            )
        ],
        citation_ids=["E1"],
        source_artifact_sha256="a" * 64,
    )


# --- adaptation and discrimination: both validation layers ---------------------------


def _adaptation(quote: str):
    item = _item()
    checklist = _checklist()
    request = build_adaptation_request(
        item, _profile(StudentLevel.BEGINNER), checklist, _configuration()
    )
    raw = {
        "schema_version": "1.0",
        "request_id": request.request_id,
        "criteria": [
            {
                "criterion_id": criterion.criterion_id,
                "verdict": "pass",
                "exact_quote": quote,
                "reason": "The answer states the relation plainly.",
            }
            for criterion in checklist.criteria
        ],
    }
    return item, checklist, request, raw


def test_adaptation_accepts_formatting_only_differences_in_both_layers():
    item, checklist, request, raw = _adaptation(PLAIN_QUOTE)
    validate_adaptation_output(raw, request=request, answer=ANSWER, checklist=checklist)
    validate_output_against_request(raw, request)


@pytest.mark.parametrize(
    "quote", ["A net force ... velocity changes", "5 m/s and the change is zero"]
)
def test_adaptation_still_rejects_spliced_or_changed_quotes_in_both_layers(quote):
    item, checklist, request, raw = _adaptation(quote)
    with pytest.raises(ValueError, match="exact answer substring"):
        validate_adaptation_output(raw, request=request, answer=ANSWER, checklist=checklist)
    with pytest.raises(ValueError, match="exact answer substring"):
        validate_output_against_request(raw, request)


def _discrimination(quote: str):
    request = build_discrimination_request(
        _item(), [_profile(level) for level in StudentLevel], _configuration()
    )
    raw = {
        "schema_version": "1.0",
        "request_id": request.request_id,
        "predicted_level": "beginner",
        "exact_quote": quote,
        "reason": "Plain wording.",
    }
    return request, raw


def test_discrimination_accepts_formatting_only_differences_in_both_layers():
    request, raw = _discrimination("The speed is 5 m/s and the change is non-zero.")
    validate_discrimination_output(raw, request=request, answer=ANSWER)
    validate_output_against_request(raw, request)


def test_discrimination_still_rejects_reworded_quotes_in_both_layers():
    request, raw = _discrimination("The speed is five metres per second")
    with pytest.raises(ValueError, match="exact answer substring"):
        validate_discrimination_output(raw, request=request, answer=ANSWER)
    with pytest.raises(ValueError, match="exact answer substring"):
        validate_output_against_request(raw, request)


# --- evidence support: claim text and runtime/downstream parity ----------------------


def _evidence(claim_text: str, *, bundle: str = "supported", citation: str = "supported"):
    item = _item()
    request = build_evidence_support_request(item, _configuration())
    raw = {
        "schema_version": "1.0",
        "request_id": request.request_id,
        "claims": [
            {
                "claim_id": "c1",
                "claim_text": claim_text,
                "bundle_support": bundle,
                "citation_support": citation,
                "supporting_evidence_ids": ["E1"],
                "evidence_quotes": {"E1": "A net force produces acceleration"},
                "reason": "Directly stated.",
            }
        ],
    }
    return item, request, raw


def test_evidence_claim_text_accepts_formatting_only_differences_in_both_layers():
    item, request, raw = _evidence("the object's velocity changes")
    validate_output_against_request(raw, request)
    validate_evidence_support_output(raw, request=request, item=item)


def test_evidence_claim_text_still_rejects_reworded_claims_in_both_layers():
    item, request, raw = _evidence("the object speeds up")
    with pytest.raises(ValueError, match="exact answer substring"):
        validate_output_against_request(raw, request)
    with pytest.raises(ValueError, match="exact answer substring"):
        validate_evidence_support_output(raw, request=request, item=item)


@pytest.mark.parametrize(
    "bundle", [v.value for v in SupportVerdict if v is not SupportVerdict.SUPPORTED]
)
def test_runtime_rejects_support_ids_on_non_supported_claims_like_the_assembler(bundle):
    item, request, raw = _evidence(
        "A net force causes acceleration", bundle=bundle, citation="unsupported"
    )
    with pytest.raises(ValueError, match="must not identify supporting evidence"):
        validate_evidence_support_output(copy.deepcopy(raw), request=request, item=item)
    with pytest.raises(ValueError, match="must not identify supporting evidence"):
        validate_output_against_request(raw, request)


def test_runtime_still_accepts_non_supported_claims_without_support_ids():
    item, request, raw = _evidence(
        "A net force causes acceleration", bundle="unsupported", citation="unsupported"
    )
    raw["claims"][0]["supporting_evidence_ids"] = []
    raw["claims"][0]["evidence_quotes"] = {}
    validate_output_against_request(raw, request)
    validate_evidence_support_output(raw, request=request, item=item)


# --- correctness ----------------------------------------------------------------------


def _rubric() -> OpenAnswerRubric:
    return OpenAnswerRubric(
        question_id="q1",
        gold_sha256="1" * 64,
        rubric_version="rubric-1",
        review_record_id="fixture-review",
        criteria=[
            dict(
                criterion_id="term",
                description="Names the cause.",
                core=True,
                reference_span_ids=["s1"],
            )
        ],
        required_paths=[["term"]],
        full_credit_answers=["net force"],
    )


def _assessment(quote: str, **updates) -> JudgeAssessment:
    return JudgeAssessment(
        **(
            dict(
                criteria=[
                    dict(criterion_id="term", verdict="met", answer_quote=quote, reason="fixture")
                ],
                critical_error=False,
                critical_error_quote=None,
                minor_error=False,
                minor_error_quote=None,
                needs_review=False,
                review_reason=None,
                rationale="fixture rationale",
            )
            | updates
        )
    )


def test_correctness_accepts_formatting_only_differences():
    validate_assessment(_assessment(PLAIN_QUOTE), _rubric(), ANSWER)
    validate_assessment(
        _assessment(PLAIN_QUOTE, minor_error=True, minor_error_quote="5 m/s"),
        _rubric(),
        ANSWER,
    )


@pytest.mark.parametrize("quote", ["A net force ... changes", "the speed is 6 m/s"])
def test_correctness_still_rejects_spliced_or_changed_quotes(quote):
    with pytest.raises(ValueError, match="absent from the complete original answer"):
        validate_assessment(_assessment(quote), _rubric(), ANSWER)


def test_correctness_error_flag_quotes_use_the_same_rule():
    with pytest.raises(ValueError, match="nonempty exact answer quote"):
        validate_assessment(
            _assessment(PLAIN_QUOTE, critical_error=True, critical_error_quote="6 m/s"),
            _rubric(),
            ANSWER,
        )


# --- policy metadata ------------------------------------------------------------------


def test_fresh_runner_results_record_the_policy_but_legacy_results_still_load(tmp_path: Path):
    request, raw = _discrimination("The speed is 5 m/s and the change is non-zero.")
    result = CachedJudgeRunner(tmp_path / "cache.jsonl", judge_execution_id="exec-1").run(
        request,
        _configuration(),
        lambda _request, _config: raw,
        lambda payload: validate_discrimination_output(payload, request=request, answer=ANSWER),
    )
    assert result.unresolved is False
    assert result.answer_quote_policy == ANSWER_QUOTE_POLICY

    legacy = result.model_dump(mode="json")
    legacy.pop("answer_quote_policy")
    assert JudgeResultEnvelope.model_validate(legacy).answer_quote_policy is None


def test_policy_is_not_part_of_the_request_cache_key(tmp_path: Path):
    request, raw = _discrimination("The speed is 5 m/s and the change is non-zero.")
    cache = tmp_path / "cache.jsonl"
    validator = lambda payload: validate_discrimination_output(  # noqa: E731
        payload, request=request, answer=ANSWER
    )
    first = CachedJudgeRunner(cache, judge_execution_id="exec-1").run(
        request, _configuration(), lambda *_: raw, validator
    )
    calls: list[object] = []
    second = CachedJudgeRunner(cache, judge_execution_id="exec-2").run(
        request, _configuration(), lambda *_: calls.append(1) or raw, validator
    )
    assert calls == []  # reused from cache, no provider call
    assert second.cache_key == first.cache_key and second.cache_hit is True


def test_cli_preflight_stops_on_an_outdated_cache_before_any_provider_call(
    tmp_path, monkeypatch, capsys
):
    import cs30.evaluation.v2_generation_cli as module

    config = _configuration().model_copy(update={"provider": "openai"})
    first = _item().model_copy(
        update={"run_id": "uncached", "evaluation_id": "eval-uncached", "answer": "Other text."}
    )
    uncached = build_evidence_support_request(first, config)
    _, stale, raw = _evidence(
        "A net force causes acceleration", bundle="unsupported", citation="unsupported"
    )
    stale = build_evidence_support_request(_item(), config)
    raw["request_id"] = stale.request_id
    cache = tmp_path / "cache.jsonl"
    cache.write_text(
        JudgeResultEnvelope(
            task=stale.task,
            request_id=stale.request_id,
            cache_key=request_cache_key(stale),
            judge_config_version=config.config_version,
            judge_execution_id="old-run",
            output=raw,
            completed_at_utc="2026-10-28T12:00:00+00:00",
        ).model_dump_json()
        + "\n",
        encoding="utf-8",
    )
    calls: list[int] = []

    class CountingClient:
        def __init__(self, *_args, **_kwargs):
            pass

        def complete(self, *_args):
            calls.append(1)
            raise AssertionError("the preflight must stop before any provider call")

    monkeypatch.setattr(module, "OpenAIResponsesClient", CountingClient)
    requests = tmp_path / "requests.jsonl"
    requests.write_text(
        uncached.model_dump_json() + "\n" + stale.model_dump_json() + "\n", encoding="utf-8"
    )
    config_path = tmp_path / "config.json"
    config_path.write_text(config.model_dump_json(), encoding="utf-8")
    with pytest.raises(SystemExit):
        module.main(
            [
                "run-judge-requests",
                "--requests",
                str(requests),
                "--judge-config",
                str(config_path),
                "--cache",
                str(cache),
                "--output",
                str(tmp_path / "out.jsonl"),
                "--judge-execution-id",
                "new-run",
            ]
        )
    assert "fails current validation" in capsys.readouterr().err
    assert calls == []
    assert not (tmp_path / "out.jsonl").exists()
