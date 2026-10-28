"""Behavioural regressions for offline scoring, missing data and judge reliability."""

import json

import pytest
from pydantic import ValidationError

from cs30.evaluation.open_answer_models import (
    ExpectedAnswer,
    HumanDecision,
    HumanRating,
    JudgeAssessment,
    OpenAnswerExperiment,
    OpenAnswerRubric,
    OpenAnswerRun,
)
from cs30.evaluation.open_answer_reporting import (
    apply_human_reviews,
    calibration_report,
    summarize_open_answers,
    write_open_answer_reports,
)
from cs30.evaluation.open_answer_scoring import (
    OpenAnswerScorer,
    assessment_score,
    build_judge_prompt,
    deterministic_score,
)
from cs30.generation.client import LLMResponse, TokenUsage
from cs30.v2.contracts import GeneratedAnswer, GoldQuestion

GOLD_HASH = "1" * 64


def gold():
    text = "Deceleration is acceleration opposite to velocity and reduces speed."
    return GoldQuestion(
        question_id="q1",
        question="What term describes acceleration that reduces speed?",
        gold_answer_text="deceleration",
        answerable=True,
        gold_core_evidence_sets=[
            [
                {
                    "span": {
                        "span_id": "s1",
                        "textbook_id": "book",
                        "chapter_id": "2",
                        "chapter_char_start": 0,
                        "chapter_char_end": len(text),
                        "verbatim_text": text,
                        "origin_corpus_version": "v2-test",
                    },
                    "sufficiency": "core_sufficient",
                }
            ]
        ],
        question_difficulty="easy",
        question_type="definition",
        concept_group="motion",
        personalisation_eligibility="pending",
        eligibility_reason="fixture",
        split="dev",
        corpus_version="v2-test",
        parser_version="fixture",
        gold_annotation_version="fixture",
        annotation_status="reviewed",
        review_record_id="fixture-review",
    )


def rubric(**updates):
    payload = dict(
        question_id="q1",
        gold_sha256=GOLD_HASH,
        rubric_version="rubric-1",
        review_record_id="fixture-review",
        criteria=[
            dict(
                criterion_id="term",
                description="Names deceleration.",
                core=True,
                reference_span_ids=["s1"],
            )
        ],
        required_paths=[["term"]],
        full_credit_answers=["deceleration", "Deceleration."],
    )
    return OpenAnswerRubric(**(payload | updates))


def case(number=1, **updates):
    return ExpectedAnswer(
        **(
            dict(
                run_id=f"r{number}",
                question_id="q1",
                condition_id=f"c{number}",
                student_level="beginner",
                generator_model="generator-v1",
            )
            | updates
        )
    )


def run(number=1, answer="deceleration", status="answered", **updates):
    payload = dict(**case(number).model_dump(), status=status)
    if status in {"answered", "abstained"}:
        payload["answer"] = GeneratedAnswer(
            explanation=answer,
            citations=("chunk-1",) if status == "answered" else (),
            abstained=status == "abstained",
        )
    else:
        payload["error"] = "provider failed"
    return OpenAnswerRun(**(payload | updates))


def experiment(*cases):
    return OpenAnswerExperiment(
        matrix_version="fixture-matrix",
        gold_sha256=GOLD_HASH,
        rubrics_sha256="2" * 64,
        cases=list(cases) or [case()],
    )


def assessment(verdict="met", quote="slowing down", **updates):
    return JudgeAssessment(
        **(
            dict(
                criteria=[
                    dict(
                        criterion_id="term",
                        verdict=verdict,
                        answer_quote=quote if verdict in {"met", "contradicted"} else None,
                        reason="fixture evidence assessment",
                    )
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


class JudgeClient:
    model = "judge-v1"
    temperature = 0.0

    def __init__(self, *responses):
        self.responses = list(responses)
        self.prompts = []

    def complete(self, prompt, text_format):
        assert text_format["strict"] is True
        self.prompts.append(prompt)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        text = response.model_dump_json() if isinstance(response, JudgeAssessment) else response
        return LLMResponse(text, self.model, TokenUsage(5, 3, 8), None, 10)


def score(scorer=None, saved=None, grading=None, expected=None, question=None):
    return (scorer or OpenAnswerScorer()).score(
        expected or experiment(),
        {"q1": question or gold()},
        {"q1": grading or rubric()},
        {r.run_id: r for r in ([run()] if saved is None else saved)},
    )


def test_whole_alias_is_correct_but_keyword_in_contradictory_answer_is_not_fast_accepted():
    assert score()[0].score == 2
    ambiguous = score(
        saved=[run(answer="deceleration because it accelerates in the same direction")]
    )[0]
    assert ambiguous.score is None and ambiguous.score_status == "needs_review"


def test_synonym_semantic_judge_and_core_contradiction():
    client = JudgeClient(assessment(), assessment("contradicted", "same direction"))
    scorer = OpenAnswerScorer(client)
    good = score(scorer, [run(answer="slowing down")])[0]
    bad = score(scorer, [run(answer="deceleration in the same direction")])[0]
    assert (good.score, bad.score) == (2, 0)
    assert good.scoring_source == "judge"
    assert good.judge_attempts[0].input_tokens == 5


def test_partial_credit_and_alternative_complete_paths():
    grading = rubric(
        criteria=[
            dict(criterion_id=name, description=name, reference_span_ids=["s1"])
            for name in ("term", "reason", "alternative")
        ],
        required_paths=[["term", "reason"], ["alternative"]],
    )
    observations = assessment().model_dump()
    observations["criteria"] = [
        dict(criterion_id=name, verdict=verdict, answer_quote=None, reason="fixture")
        for name, verdict in [("term", "met"), ("reason", "missing"), ("alternative", "missing")]
    ]
    assert assessment_score(JudgeAssessment(**observations), grading) == 1
    observations["criteria"][2]["verdict"] = "met"
    assert assessment_score(JudgeAssessment(**observations), grading) == 2
    observations["minor_error"] = True
    assert assessment_score(JudgeAssessment(**observations), grading) == 1


@pytest.mark.parametrize(
    "text, expected",
    [
        ("−2 m/s²", 2),
        ("-2 m/s²", 2),
        ("2 m/s²", 0),
        ("-2 m/s", 0),
        ("-2.005 m/s²", 2),
        ("-2.02 m/s²", 0),
        ("1e999 m/s²", 0),
        ("-2 m/s² but the direction is positive", None),
    ],
)
def test_numeric_rules_preserve_sign_units_tolerances_and_entire_answer(text, expected):
    grading = rubric(
        full_credit_answers=[],
        numeric_target={
            "value": -2,
            "accepted_units": ["m/s²"],
            "absolute_tolerance": 0.01,
        },
    )
    result = deterministic_score(text, grading)
    assert (result[0] if result else None) == expected


def test_numeric_unit_case_is_never_case_folded():
    grading = rubric(
        full_credit_answers=[],
        alias_case_sensitive=False,
        numeric_target={"value": 2, "accepted_units": ["V"]},
    )
    assert deterministic_score("2 V", grading)[0] == 2
    assert deterministic_score("2 v", grading)[0] == 0


def test_factual_prompt_is_blind_and_uses_gold_instead_of_retrieval_evidence():
    prompt = build_judge_prompt(gold(), rubric(), "slowing down")
    assert "Deceleration is acceleration opposite to velocity" in prompt
    for metadata in ["generator-v1", "condition_id", "student_level", "beginner", "lambda"]:
        assert metadata not in prompt
    assert "untrusted material" in prompt
    assert "ENTIRE candidate" in prompt


@pytest.mark.parametrize(
    "response",
    [
        "not json",
        assessment(quote="invented quote").model_dump_json(),
        assessment().model_dump_json().replace('"term"', '"unknown"'),
        json.dumps(assessment().model_dump() | {"score": 2}),
    ],
)
def test_invalid_judge_outputs_are_retried_without_scoring_model_wrong(response):
    client = JudgeClient(response, assessment())
    record = score(OpenAnswerScorer(client), [run(answer="slowing down")])[0]
    assert record.score == 2
    assert len(record.judge_attempts) == 2
    assert record.judge_attempts[0].error is not None
    assert client.prompts[1].startswith(client.prompts[0])


def test_exhausted_provider_error_stays_unknown_and_batch_continues():
    client = JudgeClient(TimeoutError("timeout"))
    records = score(
        OpenAnswerScorer(client, max_retries=0),
        [run(1, "slowing down"), run(2)],
        expected=experiment(case(1), case(2)),
    )
    assert records[0].score_status == "judge_error" and records[0].score is None
    assert records[1].score == 2
    metric = summarize_open_answers(records)["open_answer_full_correct_rate_e2e"]
    assert metric == dict(
        numerator=1, denominator=2, value=None, lower_bound=0.5, upper_bound=1.0, unresolved=1
    )


def test_uncertain_assessment_routes_to_review_without_becoming_zero():
    record = score(
        OpenAnswerScorer(JudgeClient(assessment("uncertain"))), [run(answer="slowing down")]
    )[0]
    assert record.score_status == "needs_review" and record.score is None


def test_missing_runs_failures_and_abstentions_keep_expected_denominator():
    expected = experiment(case(1), case(2), case(3), case(4))
    records = score(
        saved=[run(1), run(2, status="generation_error"), run(3, status="abstained")],
        expected=expected,
    )
    assert [r.score for r in records] == [2, 0, 0, None]
    summary = summarize_open_answers(records)
    assert summary["open_answer_full_correct_rate_e2e"]["denominator"] == 4
    assert summary["open_answer_full_correct_rate_e2e"]["upper_bound"] == 0.5
    assert summary["technical_failure_rate"]["value"] == 0.25
    assert summary["scoring_coverage"]["value"] == 0.75
    assert summary["open_answer_full_correct_rate_answered"]["value"] == 1


@pytest.mark.parametrize("answerable", [False, None])
def test_unanswerable_and_unresolved_gold_are_excluded(answerable):
    question = gold().model_copy(update={"answerable": answerable, "gold_core_evidence_sets": ()})
    record = score(question=question)[0]
    assert record.score_status == "excluded" and record.score is None
    assert summarize_open_answers([record])["open_answer_full_correct_rate_e2e"]["value"] is None


def test_mcq_gold_does_not_silently_enter_open_answer_accuracy():
    question = gold().model_copy(update={"options": {"A": object()}})
    assert score(question=question)[0].reason == "multiple_choice"


def test_all_matrix_inputs_are_validated_before_any_judge_call():
    client = JudgeClient()
    with pytest.raises(ValueError, match="identity"):
        score(
            OpenAnswerScorer(client),
            [run(answer="slowing down"), run(2, condition_id="wrong")],
            expected=experiment(case(), case(2)),
        )
    assert client.prompts == []


def test_invalid_provenance_unknown_references_and_same_model_are_rejected():
    with pytest.raises(ValueError, match="Gold hash"):
        score(grading=rubric(gold_sha256="3" * 64))
    broken = rubric(
        criteria=[
            dict(
                criterion_id="term",
                description="term",
                core=True,
                reference_span_ids=["unknown-span"],
            )
        ]
    )
    with pytest.raises(ValueError, match="unknown Gold"):
        score(grading=broken)
    client = JudgeClient()
    client.model = "generator-v1"
    with pytest.raises(ValueError, match="self-judge"):
        score(OpenAnswerScorer(client))


def test_cache_reuses_identical_blinded_assessments_and_versions_invalidate_it(tmp_path):
    client = JudgeClient(assessment(), assessment())
    scorer = OpenAnswerScorer(client, cache_directory=tmp_path)
    first = score(scorer, [run(answer="slowing down")])[0]
    second = score(scorer, [run(2, "slowing down")], expected=experiment(case(2)))[0]
    assert not first.cache_hit and second.cache_hit
    assert second.run_id == "r2" and len(client.prompts) == 1
    third = score(scorer, [run(answer="slowing down")], grading=rubric(rubric_version="rubric-2"))[
        0
    ]
    assert not third.cache_hit and len(client.prompts) == 2
    assert summarize_open_answers([second])["judge_calls_this_run"] == 0


def rating(record, rater, value):
    return HumanRating(
        run_id=record.run_id,
        answer_sha256=record.answer_sha256,
        rubric_sha256=record.rubric_sha256,
        rater_id=rater,
        score=value,
        note="synthetic test rating",
    )


def test_human_review_is_hash_bound_and_keeps_original_machine_observations():
    original = score(saved=[run(answer="slowing down")])[0]
    decision = HumanDecision(
        **rating(original, "human", 2).model_dump(), review_record_id="review-1"
    )
    reviewed = apply_human_reviews([original], [decision])[0]
    assert original.score is None and reviewed.score == 2
    assert reviewed.scoring_source == "human" and reviewed.review_record_id == "review-1"
    with pytest.raises(ValueError, match="hashes"):
        apply_human_reviews([original], [decision.model_copy(update={"answer_sha256": "0" * 64})])
    with pytest.raises(ValueError, match="overwrite"):
        apply_human_reviews([reviewed], [decision])


def test_calibration_preserves_human_disagreement_and_requires_real_adjudication():
    records = score(saved=[run(), run(2)], expected=experiment(case(), case(2)))
    ratings = [
        rating(records[0], "a", 2),
        rating(records[0], "b", 2),
        rating(records[1], "a", 0),
        rating(records[1], "b", 1),
    ]
    with pytest.raises(ValueError, match="adjudication"):
        calibration_report(records, ratings)
    adjudication = HumanDecision(
        **rating(records[1], "third", 0).model_dump(), review_record_id="adjudication-1"
    )
    report = calibration_report(records, ratings, [adjudication])
    assert report["raw_human_agreement"] == 0.5
    assert report["full_correct_precision"] == 0.5
    assert report["full_correct_recall"] == 1
    assert report["linear_weighted_cohen_kappa"] == pytest.approx(0.5)
    assert report["reportable"] is False


def test_single_class_kappa_is_undefined_and_duplicates_fail():
    record = score()[0]
    ratings = [rating(record, "a", 2), rating(record, "b", 2)]
    assert calibration_report([record], ratings)["linear_weighted_cohen_kappa"] is None
    with pytest.raises(ValueError, match="duplicate"):
        calibration_report([record], ratings + [ratings[0]])


def test_reports_never_promote_unvalidated_scores_or_overwrite_originals(tmp_path):
    records = score()
    output = tmp_path / "report"
    report = write_open_answer_reports(records, output, {"fixture": True})
    assert report["reportable"] is False
    assert (output / "open_answer_summary.csv").read_text(encoding="utf-8").splitlines()[
        1
    ].endswith("1.0,1.0,1.0")
    assert (output / "open_answer_review_queue.jsonl").read_text(encoding="utf-8") == ""
    with pytest.raises(FileExistsError):
        write_open_answer_reports(records, output, {})


@pytest.mark.parametrize("score_value", [True, 1.5, 3, -1])
def test_human_scores_are_strict_ordinal_integers(score_value):
    record = score()[0]
    with pytest.raises(ValidationError):
        rating(record, "a", score_value)


@pytest.mark.parametrize(
    "change",
    [
        {"required_paths": [["missing"]]},
        {"required_paths": [[]]},
        {"criteria": [dict(criterion_id="term", description="a", reference_span_ids=["s1"])] * 2},
        {"numeric_target": {"value": float("nan"), "accepted_units": ["m"]}},
    ],
)
def test_rubric_rejects_invalid_paths_duplicate_criteria_and_nonfinite_values(change):
    with pytest.raises(ValidationError):
        rubric(**change)


def test_duplicate_expected_cells_and_invalid_run_status_are_rejected():
    with pytest.raises(ValidationError, match="unique"):
        experiment(case(), case().model_copy(update={"run_id": "different"}))
    with pytest.raises(ValidationError, match="status"):
        OpenAnswerRun(
            **case().model_dump(),
            status="abstained",
            answer=GeneratedAnswer(explanation="answer", citations=("chunk",)),
        )


def test_provider_failure_after_bad_json_retries_the_original_blinded_prompt():
    client = JudgeClient("invalid-json", TimeoutError("timeout"), assessment())
    result = score(OpenAnswerScorer(client, max_retries=2), [run(answer="slowing down")])[0]
    assert result.score == 2
    assert client.prompts[2] == client.prompts[0]
    assert client.prompts[1].count("VALIDATION_REPAIR") == 1
    assert result.judge_calls_this_run == 3


def test_actual_provider_model_is_recorded_and_hidden_self_judging_requires_review():
    class AliasedClient(JudgeClient):
        def complete(self, prompt, text_format):
            response = super().complete(prompt, text_format)
            return LLMResponse(response.text, "generator-v1", response.usage, None, 1)

    result = score(OpenAnswerScorer(AliasedClient(assessment())), [run(answer="slowing down")])[0]
    assert result.score is None and result.score_status == "needs_review"
    assert result.judge_attempts[0].reported_model == "generator-v1"


def test_corrupt_cache_is_rejected_and_endpoint_credentials_are_not_exposed(tmp_path):
    client = JudgeClient(assessment())
    client.endpoint = "https://user:secret@example.com/judge?key=secret"
    scorer = OpenAnswerScorer(client, cache_directory=tmp_path)
    assert "secret" not in json.dumps(scorer.judge_config)
    score(scorer, [run(answer="slowing down")])
    path = next(tmp_path.glob("*.json"))
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["trace"]["judge_model"] = "wrong-model"
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="cache identity"):
        score(scorer, [run(answer="slowing down")])


def test_replay_of_human_review_does_not_count_historical_provider_calls_as_new_calls():
    original = score(OpenAnswerScorer(JudgeClient(assessment())), [run(answer="slowing down")])[0]
    assert original.judge_calls_this_run == 1
    decision = HumanDecision(
        **rating(original, "human", 1).model_dump(), review_record_id="review-1"
    )
    updated = apply_human_reviews([original], [decision])[0]
    assert updated.judge_calls_this_run == 0
    assert updated.human_rater_id == "human"
    assert updated.judge_attempts == original.judge_attempts


def test_bootstrap_keeps_same_question_cells_together_and_is_reproducible():
    records = score(saved=[run(), run(2)], expected=experiment(case(), case(2)))
    records[1] = records[1].model_copy(update={"question_id": "q2"})
    ratings = [
        rating(record, rater, target)
        for record, target in zip(records, (0, 2), strict=True)
        for rater in ("a", "b")
    ]
    first = calibration_report(records, ratings)
    assert first["uncertainty"] == calibration_report(records, ratings)["uncertainty"]
    assert first["question_count"] == 2
    assert first["uncertainty"]["intervals"]["raw_human_agreement"]["lower"] == 1
    assert first["uncertainty"]["intervals"]["full_correct_precision"]["lower"] == 0
    assert first["uncertainty"]["intervals"]["full_correct_precision"]["upper"] == 1


def test_export_adapter_preserves_v2_answer_and_failure_identity():
    from cs30.v2.generation import V2BatchResult, V2GenerationTrace

    trace = V2GenerationTrace(
        model="generator-v1",
        prompt_sha256=None,
        profile_source="static",
        corpus_version=None,
        corpus_hash=None,
        evidence_chunk_ids=(),
        attempts=(),
    )
    answer = run().answer
    exported = OpenAnswerRun.from_v2_result(case(), V2BatchResult(answer, trace))
    assert exported.answer == answer and exported.status == "answered"
    failed = OpenAnswerRun.from_v2_result(case(), V2BatchResult(None, trace, "provider timeout"))
    assert failed.status == "generation_error" and failed.error == "provider timeout"
    with pytest.raises(ValueError, match="model differs"):
        OpenAnswerRun.from_v2_result(case(generator_model="other"), V2BatchResult(answer, trace))


def test_numeric_rubric_cannot_bypass_unit_case_through_aliases():
    with pytest.raises(ValidationError, match="bypass unit"):
        rubric(
            full_credit_answers=["2 V"],
            alias_case_sensitive=False,
            numeric_target={"value": 2, "accepted_units": ["V"]},
        )


def test_report_provenance_cannot_override_nonreportable_status(tmp_path):
    output = tmp_path / "report"
    write_open_answer_reports(score(), output, {"reportable": True, "schema_version": "wrong"})
    manifest = json.loads((output / "run_manifest.json").read_text(encoding="utf-8"))
    assert manifest["reportable"] is False and manifest["schema_version"] == "0.1"


@pytest.mark.parametrize("invalid_text", [False, True])
def test_malformed_provider_metadata_is_isolated_as_judge_error(invalid_text):
    class BrokenClient(JudgeClient):
        def complete(self, prompt, text_format):
            return LLMResponse(
                {"unexpected": "object"} if invalid_text else assessment().model_dump_json(),
                self.model,
                TokenUsage(-1, 3, 2),
                None,
                1,
            )

    record = score(OpenAnswerScorer(BrokenClient(), max_retries=0), [run(answer="slowing down")])[0]
    assert record.score_status == "judge_error" and record.score is None
    assert record.judge_attempts[0].input_tokens is None
    assert record.judge_attempts[0].usage_available is False
