import json
from importlib.util import find_spec
from pathlib import Path

import pytest
from pydantic import ValidationError

import cs30.evaluation as evaluation

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "evaluation"


def test_evaluation_contract_module_is_available() -> None:
    assert find_spec("cs30.evaluation") is not None


def test_gold_fixture_preserves_outer_or_and_inner_and_semantics() -> None:
    samples = evaluation.load_gold_samples(
        FIXTURE_DIR / "gold_v0_1.jsonl",
        documents={"fixture_openstax": "Alpha. Beta. Gamma. Partial."},
    )

    joint = samples[0]
    assert [[span.span_id for span in group] for group in joint.gold_core_evidence_sets] == [
        ["span_alpha", "span_beta"],
        ["span_gamma"],
    ]
    assert [span.span_id for span in joint.partial_evidence] == ["span_partial"]
    assert joint.gold_annotation_version == "gold-fixture-0.1"


def test_gold_loader_rejects_a_span_that_cannot_replay_verbatim() -> None:
    with pytest.raises(ValueError, match="span_alpha.*does not match"):
        evaluation.load_gold_samples(
            FIXTURE_DIR / "gold_v0_1.jsonl",
            documents={"fixture_openstax": "Wrong. Beta. Gamma. Partial."},
        )


def test_answerable_sample_requires_a_complete_gold_evidence_set() -> None:
    payload = _minimal_gold_payload()
    payload["gold_core_evidence_sets"] = []

    with pytest.raises(ValidationError, match="answerable samples require"):
        evaluation.GoldSample.model_validate(payload)


def test_reviewed_sample_cannot_leave_answerability_unresolved() -> None:
    payload = _minimal_gold_payload()
    payload["answerable"] = None

    with pytest.raises(ValidationError, match="reviewed samples must resolve answerable"):
        evaluation.GoldSample.model_validate(payload)


def test_unresolved_sample_uses_null_instead_of_false_answerability() -> None:
    payload = _minimal_gold_payload()
    payload.update(
        answerable=None,
        gold_core_evidence_sets=[],
        annotation_status=evaluation.AnnotationStatus.UNRESOLVED,
    )

    sample = evaluation.GoldSample.model_validate(payload)

    assert sample.answerable is None
    assert sample.annotation_status is evaluation.AnnotationStatus.UNRESOLVED


def test_hand_computable_run_fixture_covers_all_five_terminal_states() -> None:
    results = evaluation.load_run_results(FIXTURE_DIR / "run_results_v0_1.jsonl")

    assert {result.status for result in results} == set(evaluation.RunStatus)
    assert len(results) == 5


def test_technical_error_cannot_be_encoded_as_a_correct_abstention() -> None:
    payload = _abstained_run_payload()
    payload["status"] = evaluation.RunStatus.GENERATION_ERROR

    with pytest.raises(
        ValidationError,
        match="technical error runs must not contain a final answer",
    ):
        evaluation.EvaluationRunResult.model_validate(payload)


def test_normal_answer_requires_passed_or_failed_citation_validation() -> None:
    payload = _answered_run_payload()
    payload["citation_validation"] = None

    with pytest.raises(ValidationError, match="answered runs require citation validation"):
        evaluation.EvaluationRunResult.model_validate(payload)


def test_run_result_rejects_prompt_evidence_missing_from_retrieval() -> None:
    payload = _answered_run_payload()
    payload["retrieval"]["hits"][0]["chunk_id"] = "chunk_other"

    with pytest.raises(ValidationError, match="absent from retrieval hits"):
        evaluation.EvaluationRunResult.model_validate(payload)


def test_run_result_rejects_inconsistent_resolved_citations() -> None:
    payload = _answered_run_payload()
    payload["citation_validation"]["resolved_citations"] = ["chunk_other"]

    with pytest.raises(ValidationError, match="resolved citations"):
        evaluation.EvaluationRunResult.model_validate(payload)


def test_jsonl_loader_reports_the_bad_line_number(tmp_path: Path) -> None:
    path = tmp_path / "bad.jsonl"
    path.write_text(
        json.dumps(_minimal_gold_payload()) + "\n" + "{not-json}\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=r"bad\.jsonl:2"):
        evaluation.load_gold_samples(path)


def _minimal_gold_payload() -> dict[str, object]:
    return {
        "schema_version": "0.1",
        "question_id": "fixture_joint",
        "question": "Which evidence supports the answer?",
        "options": {"A": "One", "B": "Two", "C": "Three", "D": "Four"},
        "gold_answer": "B",
        "answerable": True,
        "gold_core_evidence_sets": [
            [
                {
                    "span_id": "span_alpha",
                    "document_id": "fixture_openstax",
                    "char_start": 0,
                    "char_end": 6,
                    "verbatim_text": "Alpha.",
                }
            ]
        ],
        "partial_evidence": [],
        "question_difficulty": "medium",
        "question_type": "causal",
        "concept_group": "fixture_concept",
        "personalisation_eligibility": "pending",
        "eligibility_reason": "Awaiting M5 role review.",
        "split": "dev",
        "corpus_version": "fixture-corpus-0.1",
        "parser_version": "fixture-parser-0.1",
        "gold_annotation_version": "gold-fixture-0.1",
        "annotation_status": "reviewed",
        "review_record_id": "review_fixture_joint",
    }


def _retrieval_payload(*, with_hit: bool) -> dict[str, object]:
    hits = []
    if with_hit:
        hits.append(
            {
                "chunk_id": "chunk_alpha",
                "text": "Alpha.",
                "chapter_id": "fixture_chapter",
                "source": "fixture://openstax",
                "source_locator": "[0,6)",
                "score": 1.0,
                "rank": 1,
                "retriever_type": "fixture",
            }
        )
    return {"query": "Which evidence?", "mode": "fixture", "hits": hits}


def _bundle_payload(*, with_item: bool) -> dict[str, object]:
    items: list[dict[str, object]] = []
    citation_map: dict[str, str] = {}
    if with_item:
        items.append(
            {
                "evidence_id": "E1",
                "chunk_id": "chunk_alpha",
                "text": "Alpha.",
                "chapter_id": "fixture_chapter",
                "source": "fixture://openstax",
                "source_locator": "[0,6)",
                "rank": 1,
                "score": 1.0,
                "token_count": 1,
            }
        )
        citation_map = {"E1": "chunk_alpha"}
    return {
        "query": "Which evidence?",
        "retrieval_mode": "fixture",
        "evidence_items": items,
        "prompt_context": "[chunk_alpha] Alpha." if with_item else None,
        "citation_map": citation_map,
        "token_count": 1 if with_item else 0,
    }


def _abstained_answer_payload() -> dict[str, object]:
    return {
        "final_choice": None,
        "explanation": "The retrieved evidence is insufficient.",
        "citations": [],
        "abstained": True,
    }


def _abstained_run_payload() -> dict[str, object]:
    answer = _abstained_answer_payload()
    return {
        "schema_version": "0.1",
        "run_id": "run_abstained",
        "question_id": "fixture_unanswerable",
        "condition_id": "fixture_condition",
        "status": "abstained",
        "retrieval": _retrieval_payload(with_hit=False),
        "evidence_sent_to_model": _bundle_payload(with_item=False),
        "raw_model_output": json.dumps(answer),
        "repaired_model_output": None,
        "final_answer": answer,
        "citation_validation": {
            "answer": answer,
            "resolved_citations": [],
            "citation_status": "skipped",
        },
        "error": None,
    }


def _answered_run_payload() -> dict[str, object]:
    answer = {
        "final_choice": "B",
        "explanation": "Alpha supports the answer.",
        "citations": ["chunk_alpha"],
        "abstained": False,
    }
    return {
        "schema_version": "0.1",
        "run_id": "run_answered",
        "question_id": "fixture_joint",
        "condition_id": "fixture_condition",
        "status": "answered",
        "retrieval": _retrieval_payload(with_hit=True),
        "evidence_sent_to_model": _bundle_payload(with_item=True),
        "raw_model_output": json.dumps(answer),
        "repaired_model_output": None,
        "final_answer": answer,
        "citation_validation": {
            "answer": answer,
            "resolved_citations": ["chunk_alpha"],
            "citation_status": "passed",
        },
        "error": None,
    }
