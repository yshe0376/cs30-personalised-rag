import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from cs30.contracts import (
    EvidenceBundle,
    GeneratedAnswer,
    RetrievalResult,
    RetrievedEvidence,
    StudentLevel,
    StudentProfile,
    ValidatedAnswer,
)
from cs30.errors import GenerationError
from cs30.evaluation import (
    AbstentionCause,
    ExecutionMode,
    GoldChunkMapping,
    GoldEvidenceSpan,
    GoldSample,
    QuestionChunkMapping,
    RunManifest,
    RunStatus,
    SpanChunkMapping,
    append_jsonl_record,
    capture_git_state,
    complete_evidence_hit_at_k,
    complete_evidence_rank,
    complete_evidence_reciprocal_rank,
    context_noise_rate_at_k,
    core_precision_at_k,
    evidence_recall_at_k,
    first_hit_reciprocal_rank,
    hit_at_k,
    load_inprogress_run_results,
    no_hit_rate_at_k,
    no_relevant_hit_rate_at_k,
    partial_evidence_count_at_k,
    recall_at_k,
    returned_count_at_k,
    run_batch,
    run_results_are_comparable,
    score_saved_run,
    write_final_jsonl,
)
from cs30.evaluation.models import EvaluationRunResult
from cs30.generation import MockJsonLLMClient, PersonalisedAnswerGenerator


def _hit(chunk_id: str, rank: int, text: str | None = None) -> RetrievedEvidence:
    return RetrievedEvidence(
        chunk_id=chunk_id,
        text=text or f"{chunk_id} text",
        chapter_id="chapter-1",
        source="fixture://corpus",
        score=1.0 / rank,
        rank=rank,
        retriever_type="fixture",
    )


def _retrieval(*chunk_ids: str) -> RetrievalResult:
    return RetrievalResult(
        query="Which evidence is relevant?",
        mode="fixture",
        hits=[_hit(chunk_id, rank) for rank, chunk_id in enumerate(chunk_ids, start=1)],
    )


def _span(span_id: str) -> GoldEvidenceSpan:
    return GoldEvidenceSpan(
        span_id=span_id,
        document_id="doc-1",
        char_start=0,
        char_end=len(span_id),
        verbatim_text=span_id,
    )


def _gold() -> GoldSample:
    return GoldSample(
        question_id="q-1",
        question="Which evidence is relevant?",
        options={"A": "one", "B": "two", "C": "three", "D": "four"},
        gold_answer="A",
        answerable=True,
        gold_core_evidence_sets=[[_span("a"), _span("b")], [_span("c")]],
        partial_evidence=[_span("p")],
        question_difficulty="medium",
        question_type="causal",
        concept_group="concept-1",
        personalisation_eligibility="pending",
        eligibility_reason="fixture",
        split="dev",
        corpus_version="corpus-1",
        parser_version="parser-1",
        gold_annotation_version="gold-1",
        annotation_status="reviewed",
        review_record_id="review-1",
    )


def _normalized_gold(*, status: str) -> GoldSample:
    payload = _gold().model_dump(mode="json")
    payload["schema_version"] = "0.2"
    for evidence_set in payload["gold_core_evidence_sets"]:
        for span in evidence_set:
            span.update(
                chapter_char_start=span["char_start"],
                chapter_char_end=span["char_end"],
                resolution_status=status,
            )
            if status == "resolved":
                span.update(
                    corpus_char_start=span["char_start"],
                    corpus_char_end=span["char_end"],
                )
    for span in payload["partial_evidence"]:
        span.update(
            chapter_char_start=span["char_start"],
            chapter_char_end=span["char_end"],
            resolution_status=status,
        )
        if status == "resolved":
            span.update(
                corpus_char_start=span["char_start"],
                corpus_char_end=span["char_end"],
            )
    return GoldSample.model_validate(payload)


def _m3_initial_normalized_gold() -> GoldSample:
    payload = _normalized_gold(status="resolved").model_dump(mode="json")
    payload.update(
        source_split="test",
        gold_answer_text="one",
        annotation_status="m3_initial",
        source={
            "dataset": "fixture dataset",
            "source_question_id": "q-1",
            "support": "fixture support",
        },
    )
    for evidence_set in payload["gold_core_evidence_sets"]:
        for span in evidence_set:
            span.update(
                chapter_id="chapter-1",
                block_id=f"block-{span['span_id']}",
                sufficiency="core_sufficient",
                annotation_note="fixture evidence",
            )
    for span in payload["partial_evidence"]:
        span.update(
            chapter_id="chapter-1",
            block_id=f"block-{span['span_id']}",
            sufficiency="partial",
            annotation_note="fixture evidence",
        )
    return GoldSample.model_validate(payload)


def _mapping() -> QuestionChunkMapping:
    return QuestionChunkMapping(
        question_id="q-1",
        corpus_version="corpus-1",
        chunk_config_hash="chunks-1",
        mapping_version="mapping-1",
        spans=[
            SpanChunkMapping(span_id="a", acceptable_chunk_sets=[["c1"]]),
            SpanChunkMapping(span_id="b", acceptable_chunk_sets=[["c3"]]),
            SpanChunkMapping(span_id="c", acceptable_chunk_sets=[["c5"]]),
            SpanChunkMapping(span_id="p", acceptable_chunk_sets=[["cp"]]),
        ],
    )


def _empty_bundle() -> EvidenceBundle:
    return EvidenceBundle(
        query="Which evidence is relevant?",
        retrieval_mode="fixture",
        evidence_items=[],
        prompt_context=None,
        citation_map={},
        token_count=0,
    )


def _abstained_answer() -> GeneratedAnswer:
    return GeneratedAnswer(
        final_choice=None,
        explanation="There is no retrieved evidence.",
        citations=[],
        abstained=True,
    )


def _validated_abstention() -> ValidatedAnswer:
    return ValidatedAnswer(
        answer=_abstained_answer(),
        resolved_citations=[],
        citation_status="skipped",
    )


def test_retrieval_only_result_has_a_distinct_terminal_state() -> None:
    result = EvaluationRunResult(
        schema_version="0.2",
        run_id="run-1",
        question_id="q-1",
        condition_id="condition-1",
        execution_mode=ExecutionMode.RETRIEVAL_ONLY,
        status=RunStatus.RETRIEVED,
        retrieval=_retrieval("c1"),
        evidence_sent_to_model=None,
        raw_model_output=None,
        repaired_model_output=None,
        final_answer=None,
        citation_validation=None,
        error=None,
        model_call_count=0,
        abstention_cause=None,
    )

    assert result.status is RunStatus.RETRIEVED
    assert result.model_invoked is False


def test_no_hit_abstention_does_not_claim_a_model_output() -> None:
    result = EvaluationRunResult(
        schema_version="0.2",
        run_id="run-2",
        question_id="q-1",
        condition_id="condition-1",
        execution_mode=ExecutionMode.RETRIEVAL_AND_GENERATION,
        status=RunStatus.ABSTAINED,
        retrieval=_retrieval(),
        evidence_sent_to_model=None,
        raw_model_output=None,
        repaired_model_output=None,
        final_answer=_abstained_answer(),
        citation_validation=_validated_abstention(),
        error=None,
        model_call_count=0,
        abstention_cause=AbstentionCause.NO_RETRIEVAL_HITS,
    )

    assert result.model_invoked is False
    assert result.abstention_cause is AbstentionCause.NO_RETRIEVAL_HITS


def test_generation_error_can_capture_a_failure_before_prompt_assembly() -> None:
    result = EvaluationRunResult(
        schema_version="0.2",
        run_id="run-before-prompt",
        question_id="q-1",
        condition_id="condition-1",
        execution_mode=ExecutionMode.RETRIEVAL_AND_GENERATION,
        status=RunStatus.GENERATION_ERROR,
        retrieval=_retrieval("c1"),
        evidence_sent_to_model=None,
        raw_model_output=None,
        repaired_model_output=None,
        final_answer=None,
        citation_validation=None,
        error={
            "stage": "generation",
            "error_type": "ProfileUnavailable",
            "message": "profile provider failed",
        },
        model_call_count=0,
        abstention_cause=None,
    )

    assert result.model_invoked is False


def test_abstention_cause_is_cross_checked() -> None:
    with pytest.raises(ValidationError, match="no_retrieval_hits"):
        EvaluationRunResult(
            schema_version="0.2",
            run_id="run-3",
            question_id="q-1",
            condition_id="condition-1",
            execution_mode="retrieval_and_generation",
            status="abstained",
            retrieval=_retrieval("c1"),
            evidence_sent_to_model=None,
            raw_model_output=None,
            repaired_model_output=None,
            final_answer=_abstained_answer(),
            citation_validation=_validated_abstention(),
            error=None,
            model_call_count=0,
            abstention_cause="no_retrieval_hits",
        )


def test_retrieval_only_and_retrieval_errors_cannot_carry_prompt_trace() -> None:
    common = dict(
        schema_version="0.2",
        run_id="run-prompt-trace",
        question_id="q-1",
        condition_id="condition-1",
        retrieval=_retrieval("c1"),
        evidence_sent_to_model=None,
        raw_model_output=None,
        repaired_model_output=None,
        final_answer=None,
        citation_validation=None,
        error=None,
        model_call_count=0,
        abstention_cause=None,
        prompt_evidence_chunk_ids=["c1"],
        prompt_sha256="a" * 64,
    )
    with pytest.raises(ValidationError, match="retrieval-only"):
        EvaluationRunResult(
            **common,
            execution_mode="retrieval_only",
            status="retrieved",
        )

    with pytest.raises(ValidationError, match="retrieval_error"):
        EvaluationRunResult(
            **{
                **common,
                "run_id": "run-retrieval-error",
                "execution_mode": "retrieval_and_generation",
                "status": "retrieval_error",
                "retrieval": None,
                "error": {
                    "stage": "retrieval",
                    "error_type": "IndexUnavailable",
                    "message": "index unavailable",
                },
            }
        )


def test_model_abstention_requires_nonempty_evidence_and_response() -> None:
    answer = _abstained_answer()
    validated = _validated_abstention()
    result = EvaluationRunResult(
        schema_version="0.2",
        run_id="run-4",
        question_id="q-1",
        condition_id="condition-1",
        execution_mode="retrieval_and_generation",
        status="abstained",
        retrieval=_retrieval("c1"),
        evidence_sent_to_model=EvidenceBundle(
            query="Which evidence is relevant?",
            retrieval_mode="fixture",
            evidence_items=[
                {
                    "evidence_id": "E1",
                    "chunk_id": "c1",
                    "text": "c1 text",
                    "chapter_id": "chapter-1",
                    "source": "fixture://corpus",
                    "rank": 1,
                    "score": 1.0,
                    "token_count": 1,
                }
            ],
            prompt_context="[c1] c1 text",
            citation_map={"E1": "c1"},
            token_count=1,
        ),
        raw_model_output=json.dumps(answer.model_dump(mode="json")),
        repaired_model_output=None,
        final_answer=answer,
        citation_validation=validated,
        error=None,
        model_call_count=1,
        abstention_cause="model_abstained_with_evidence",
    )

    assert result.model_invoked is True


def test_mapping_covers_alternative_and_partial_spans() -> None:
    mapping = _mapping()
    artifact = GoldChunkMapping(
        schema_version="0.1",
        mapping_version="mapping-1",
        corpus_version="corpus-1",
        chunk_config_hash="chunks-1",
        items=[mapping],
    )

    assert artifact.for_question("q-1").for_span("p").acceptable_chunk_sets == [["cp"]]


def test_retrieval_metrics_use_the_earliest_complete_or_path() -> None:
    gold = _gold()
    retrieval = _retrieval("c1", "noise", "c3", "cp", "c5")
    mapping = _mapping()

    assert complete_evidence_hit_at_k(gold, retrieval, mapping, 3) == 1.0
    assert hit_at_k(gold, retrieval, mapping, 1) == 1.0
    assert recall_at_k(gold, retrieval, mapping, 3) == 1.0
    assert evidence_recall_at_k(gold, retrieval, mapping, 3) == 1.0
    assert first_hit_reciprocal_rank(gold, retrieval, mapping) == 1.0
    assert complete_evidence_reciprocal_rank(gold, retrieval, mapping) == pytest.approx(1 / 3)
    assert context_noise_rate_at_k(gold, retrieval, mapping, 4) == pytest.approx(1 / 4)
    assert partial_evidence_count_at_k(gold, retrieval, mapping, 4) == 1
    assert returned_count_at_k(retrieval, 4) == 4
    assert no_hit_rate_at_k(retrieval, 4) == 0.0
    alternate_first = _retrieval("noise", "c5", "c1", "c3")
    assert complete_evidence_rank(gold, alternate_first, mapping) == 2


def test_saved_run_scoring_exposes_first_and_complete_mrr() -> None:
    run = EvaluationRunResult(
        schema_version="0.2",
        run_id="run-1",
        question_id="q-1",
        condition_id="condition-1",
        execution_mode="retrieval_only",
        status="retrieved",
        retrieval=_retrieval("c1", "noise", "c3", "cp", "c5"),
        evidence_sent_to_model=None,
        raw_model_output=None,
        repaired_model_output=None,
        final_answer=None,
        citation_validation=None,
        error=None,
        model_call_count=0,
        abstention_cause=None,
    )

    scored = score_saved_run(
        [_gold()],
        [run],
        GoldChunkMapping(
            mapping_version="mapping-1",
            corpus_version="corpus-1",
            chunk_config_hash="chunks-1",
            items=[_mapping()],
        ),
        k_values=[1, 3, 5],
    )

    assert scored["retrieval"]["first_hit_mrr"] == 1.0
    assert scored["retrieval"]["complete_evidence_mrr"] == pytest.approx(1 / 3)
    assert scored["retrieval"]["by_k"]["3"]["complete_evidence_hit_at_k"] == 1.0
    assert scored["retrieval"]["retrieval_scores"][0]["question_id"] == "q-1"
    assert scored["retrieval"]["retrieval_scores"][0]["included"] is True


def test_reportable_scoring_rejects_stale_normalized_gold_coordinates() -> None:
    run = EvaluationRunResult(
        schema_version="0.2",
        run_id="run-stale-gold",
        question_id="q-1",
        condition_id="condition-1",
        execution_mode="retrieval_only",
        status="retrieved",
        retrieval=_retrieval("c1"),
        evidence_sent_to_model=None,
        raw_model_output=None,
        repaired_model_output=None,
        final_answer=None,
        citation_validation=None,
        error=None,
        model_call_count=0,
        abstention_cause=None,
    )
    manifest = _manifest("retrieval_only").model_copy(
        update={
            "gold_annotation_version": "gold-1",
            "mapping_version": "mapping-1",
            "parser_version": "parser-1",
        }
    )

    with pytest.raises(ValueError, match="resolved.*global coordinates"):
        score_saved_run(
            [_normalized_gold(status="stale")],
            [run],
            GoldChunkMapping(
                mapping_version="mapping-1",
                corpus_version="corpus-1",
                chunk_config_hash="chunks-1",
                items=[_mapping()],
            ),
            k_values=[1],
            manifest=manifest,
        )


def test_reportable_scoring_requires_reviewed_gold() -> None:
    run = EvaluationRunResult(
        schema_version="0.2",
        run_id="run-m3-initial-gold",
        question_id="q-1",
        condition_id="condition-1",
        execution_mode="retrieval_only",
        status="retrieved",
        retrieval=_retrieval("c1"),
        evidence_sent_to_model=None,
        raw_model_output=None,
        repaired_model_output=None,
        final_answer=None,
        citation_validation=None,
        error=None,
        model_call_count=0,
        abstention_cause=None,
    )
    manifest = _manifest("retrieval_only").model_copy(
        update={
            "gold_annotation_version": "gold-1",
            "mapping_version": "mapping-1",
            "parser_version": "parser-1",
        }
    )

    with pytest.raises(ValueError, match="annotation_status=reviewed"):
        score_saved_run(
            [_m3_initial_normalized_gold()],
            [run],
            GoldChunkMapping(
                mapping_version="mapping-1",
                corpus_version="corpus-1",
                chunk_config_hash="chunks-1",
                items=[_mapping()],
            ),
            k_values=[1],
            manifest=manifest,
        )


def test_retrieval_score_rows_preserve_run_order() -> None:
    answerable_run = EvaluationRunResult(
        schema_version="0.2",
        run_id="run-order-answerable",
        question_id="q-1",
        condition_id="condition-1",
        execution_mode="retrieval_only",
        status="retrieved",
        retrieval=_retrieval("c1"),
        evidence_sent_to_model=None,
        raw_model_output=None,
        repaired_model_output=None,
        final_answer=None,
        citation_validation=None,
        error=None,
        model_call_count=0,
        abstention_cause=None,
    )
    unanswerable_run = answerable_run.model_copy(
        update={"run_id": "run-order-unanswerable", "question_id": "q-unanswerable"}
    )
    unanswerable_gold = _gold().model_copy(
        update={
            "question_id": "q-unanswerable",
            "answerable": False,
            "gold_answer": "D",
            "gold_core_evidence_sets": [],
            "partial_evidence": [],
            "annotation_status": "reviewed",
            "review_record_id": "review-2",
        }
    )

    scored = score_saved_run(
        [_gold(), unanswerable_gold],
        [answerable_run, unanswerable_run],
        {"q-1": _mapping()},
        k_values=[1],
    )

    assert [
        row["question_id"] for row in scored["retrieval"]["retrieval_scores"]
    ] == ["q-1", "q-unanswerable"]


def test_missing_mapping_is_reported_as_an_excluded_question() -> None:
    run = EvaluationRunResult(
        schema_version="0.2",
        run_id="run-missing-mapping",
        question_id="q-1",
        condition_id="condition-1",
        execution_mode="retrieval_only",
        status="retrieved",
        retrieval=_retrieval("c1"),
        evidence_sent_to_model=None,
        raw_model_output=None,
        repaired_model_output=None,
        final_answer=None,
        citation_validation=None,
        error=None,
        model_call_count=0,
        abstention_cause=None,
    )

    scored = score_saved_run([_gold()], [run], {}, k_values=[1])

    assert scored["retrieval"]["sample_count"] == 0
    assert scored["retrieval"]["excluded_runs"]["mapping_missing"] == 1
    row = scored["retrieval"]["retrieval_scores"][0]
    assert row["included"] is False
    assert row["exclusion_reason"] == "mapping_missing"


def test_gold_and_mapping_corpus_versions_must_match() -> None:
    run = EvaluationRunResult(
        schema_version="0.2",
        run_id="run-version-mismatch",
        question_id="q-1",
        condition_id="condition-1",
        execution_mode="retrieval_only",
        status="retrieved",
        retrieval=_retrieval("c1"),
        evidence_sent_to_model=None,
        raw_model_output=None,
        repaired_model_output=None,
        final_answer=None,
        citation_validation=None,
        error=None,
        model_call_count=0,
        abstention_cause=None,
    )
    mismatched_question_mapping = _mapping().model_copy(
        update={"corpus_version": "corpus-2"}
    )
    mismatched_mapping = GoldChunkMapping(
        mapping_version="mapping-1",
        corpus_version="corpus-2",
        chunk_config_hash="chunks-1",
        items=[mismatched_question_mapping],
    )

    with pytest.raises(ValueError, match="corpus_version"):
        score_saved_run([_gold()], [run], mismatched_mapping, k_values=[1])


def test_unanswerable_and_unresolved_exclusions_are_separate() -> None:
    unanswerable = GoldSample(
        question_id="q-unanswerable",
        question="Which item is absent?",
        options={"A": "one", "B": "two", "C": "three", "D": "four"},
        gold_answer="D",
        answerable=False,
        gold_core_evidence_sets=[],
        partial_evidence=[],
        question_difficulty="easy",
        question_type="factual",
        concept_group="concept-1",
        personalisation_eligibility="none",
        eligibility_reason="No evidence exists.",
        split="dev",
        corpus_version="corpus-1",
        parser_version="parser-1",
        gold_annotation_version="gold-1",
        annotation_status="reviewed",
        review_record_id="review-2",
    )
    unresolved = GoldSample(
        question_id="q-unresolved",
        question="Which item is disputed?",
        options={"A": "one", "B": "two", "C": "three", "D": "four"},
        gold_answer=None,
        answerable=None,
        gold_core_evidence_sets=[],
        partial_evidence=[],
        question_difficulty="hard",
        question_type="boundary",
        concept_group="concept-1",
        personalisation_eligibility="pending",
        eligibility_reason="Still under review.",
        split="dev",
        corpus_version="corpus-1",
        parser_version="parser-1",
        gold_annotation_version="gold-1",
        annotation_status="unresolved",
        review_record_id=None,
    )

    def retrieved_result(question_id: str) -> EvaluationRunResult:
        return EvaluationRunResult(
            schema_version="0.2",
            run_id=f"run-{question_id}",
            question_id=question_id,
            condition_id="condition-1",
            execution_mode="retrieval_only",
            status="retrieved",
            retrieval=_retrieval("noise"),
            evidence_sent_to_model=None,
            raw_model_output=None,
            repaired_model_output=None,
            final_answer=None,
            citation_validation=None,
            error=None,
            model_call_count=0,
            abstention_cause=None,
        )

    scored = score_saved_run(
        [unanswerable, unresolved],
        [retrieved_result("q-unanswerable"), retrieved_result("q-unresolved")],
        {},
        k_values=[1],
    )

    excluded = scored["retrieval"]["excluded_runs"]
    assert excluded["total"] == 2
    assert excluded["unanswerable"] == 1
    assert excluded["unresolved"] == 1
    assert sum(excluded[reason] for reason in ("unanswerable", "unresolved")) == (
        excluded["total"]
    )


def test_strict_mapping_mode_fails_before_scoring() -> None:
    run = EvaluationRunResult(
        schema_version="0.2",
        run_id="run-strict-mapping",
        question_id="q-1",
        condition_id="condition-1",
        execution_mode="retrieval_only",
        status="retrieved",
        retrieval=_retrieval("c1"),
        evidence_sent_to_model=None,
        raw_model_output=None,
        repaired_model_output=None,
        final_answer=None,
        citation_validation=None,
        error=None,
        model_call_count=0,
        abstention_cause=None,
    )

    with pytest.raises(ValueError, match="mapping_missing"):
        score_saved_run([_gold()], [run], {}, k_values=[1], strict_mapping=True)


def test_scoring_uses_manifest_top_k_when_not_explicitly_supplied() -> None:
    run = EvaluationRunResult(
        schema_version="0.2",
        run_id="run-manifest-k",
        question_id="q-1",
        condition_id="condition-1",
        execution_mode="retrieval_only",
        status="retrieved",
        retrieval=_retrieval("c1"),
        evidence_sent_to_model=None,
        raw_model_output=None,
        repaired_model_output=None,
        final_answer=None,
        citation_validation=None,
        error=None,
        model_call_count=0,
        abstention_cause=None,
    )
    manifest = _manifest("retrieval_only").model_copy(
        update={
            "gold_annotation_version": "gold-1",
            "mapping_version": "mapping-1",
            "parser_version": "parser-1",
        }
    )

    with pytest.raises(ValueError, match="top_k"):
        score_saved_run(
            [_normalized_gold(status="resolved")],
            [run],
            GoldChunkMapping(
                mapping_version="mapping-1",
                corpus_version="corpus-1",
                chunk_config_hash="chunks-1",
                items=[_mapping()],
            ),
            k_values=[5],
            manifest=manifest,
        )


def test_empty_precision_noise_and_no_relevant_hit_are_not_zero() -> None:
    gold = _gold()
    empty = _retrieval()
    assert core_precision_at_k(gold, empty, _mapping(), 1) is None
    assert context_noise_rate_at_k(gold, empty, _mapping(), 1) is None
    assert no_relevant_hit_rate_at_k(gold, empty, _mapping(), 1) is None

    irrelevant = _retrieval("noise")
    assert no_relevant_hit_rate_at_k(gold, irrelevant, _mapping(), 1) == 1.0


def test_comparability_includes_gold_and_mapping_versions() -> None:
    common = dict(
        condition_id="condition-1",
        dataset_version="dataset-1",
        split="dev",
        corpus_version="corpus-1",
        chunk_version="chunks-1",
        embedding_version="embedding-1",
        index_version="index-1",
        generation_model=None,
        prompt_version=None,
        profile="none",
        execution_mode="retrieval_only",
        retrieval_mode="bm25",
        top_k=3,
        k_values=[1, 3],
        threshold=None,
        git_commit="abc123",
        git_dirty=False,
        git_snapshot_sha256="snapshot-1",
        gold_annotation_version="gold-1",
        mapping_version="mapping-1",
    )
    left = RunManifest(run_id="left", **common)
    right = RunManifest(
        run_id="right", **{**common, "mapping_version": "mapping-2"}
    )

    assert run_results_are_comparable([left, right]) is False


def test_reportable_manifest_rejects_synthetic_trace() -> None:
    with pytest.raises(ValidationError, match="synthetic"):
        RunManifest(
            run_id="synthetic",
            condition_id="condition-1",
            dataset_version="dataset-1",
            split="dev",
            corpus_version="corpus-1",
            chunk_version="chunks-1",
            embedding_version="embedding-1",
            index_version="index-1",
            generation_model="fixture-model",
            prompt_version="prompt-1",
            profile="intermediate",
            execution_mode="retrieval_and_generation",
            retrieval_mode="fixture",
            top_k=3,
            k_values=[1, 3],
            threshold=None,
            git_commit="abc123",
            git_dirty=False,
            git_snapshot_sha256="snapshot-1",
            reportable=True,
            fixture_mode=True,
            synthetic_trace=True,
        )


def test_manifest_rejects_a_scoring_k_above_requested_top_k() -> None:
    with pytest.raises(ValidationError, match="k_values"):
        RunManifest(
            run_id="run-1",
            condition_id="condition-1",
            dataset_version="dataset-1",
            split="dev",
            corpus_version="corpus-1",
            chunk_version="chunks-1",
            embedding_version="embedding-1",
            index_version="index-1",
            generation_model=None,
            prompt_version=None,
            profile="none",
            execution_mode="retrieval_only",
            retrieval_mode="bm25",
            top_k=3,
            k_values=[1, 3, 5],
            threshold=None,
            git_commit="abc123",
            git_dirty=False,
            git_snapshot_sha256="snapshot-1",
        )


def test_dirty_manifest_cannot_be_marked_reportable() -> None:
    with pytest.raises(ValidationError, match="reportable"):
        RunManifest(
            run_id="run-1",
            condition_id="condition-1",
            dataset_version="dataset-1",
            split="dev",
            corpus_version="corpus-1",
            chunk_version="chunks-1",
            embedding_version="embedding-1",
            index_version="index-1",
            generation_model=None,
            prompt_version=None,
            profile="none",
            execution_mode="retrieval_only",
            retrieval_mode="bm25",
            top_k=3,
            k_values=[1, 3],
            threshold=None,
            git_commit="abc123",
            git_dirty=True,
            git_snapshot_sha256="snapshot-1",
            reportable=True,
        )


def test_comparability_rejects_different_corpus_versions() -> None:
    common = dict(
        condition_id="condition-1",
        dataset_version="dataset-1",
        split="dev",
        corpus_version="corpus-1",
        chunk_version="chunks-1",
        embedding_version="embedding-1",
        index_version="index-1",
        generation_model=None,
        prompt_version=None,
        profile="none",
        execution_mode="retrieval_only",
        retrieval_mode="bm25",
        top_k=3,
        k_values=[1, 3],
        threshold=None,
        git_commit="abc123",
        git_dirty=False,
        git_snapshot_sha256="snapshot-1",
    )
    left = RunManifest(run_id="left", **common)
    right = RunManifest(run_id="right", **{**common, "corpus_version": "corpus-2"})

    assert run_results_are_comparable([left, right]) is False


def test_comparability_allows_a_different_offline_scoring_k_view() -> None:
    common = dict(
        condition_id="condition-1",
        dataset_version="dataset-1",
        split="dev",
        corpus_version="corpus-1",
        chunk_version="chunks-1",
        embedding_version="embedding-1",
        index_version="index-1",
        generation_model=None,
        prompt_version=None,
        profile="none",
        execution_mode="retrieval_only",
        retrieval_mode="bm25",
        top_k=5,
        threshold=None,
        git_commit="abc123",
        git_dirty=False,
        git_snapshot_sha256="snapshot-1",
    )
    left = RunManifest(run_id="left", k_values=[1, 3], **common)
    right = RunManifest(run_id="right", k_values=[1, 5], **common)

    assert run_results_are_comparable([left, right]) is True


def test_git_snapshot_hash_includes_untracked_file_contents(tmp_path: Path) -> None:
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.email=fixture@example.invalid", "-c", "user.name=Fixture", "add", "-A"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "git",
            "-c",
            "user.email=fixture@example.invalid",
            "-c",
            "user.name=Fixture",
            "commit",
            "-m",
            "fixture",
            "--allow-empty",
        ],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    untracked = tmp_path / "untracked.py"
    untracked.write_text("answer = 1\n", encoding="utf-8")

    first = capture_git_state(tmp_path)
    untracked.write_text("answer = 2\n", encoding="utf-8")
    second = capture_git_state(tmp_path)

    assert first.dirty is True
    assert first.snapshot_sha256 != second.snapshot_sha256


def test_git_snapshot_accepts_a_subdirectory_of_the_repository(tmp_path: Path) -> None:
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    nested = tmp_path / "src"
    nested.mkdir()
    (nested / "module.py").write_text("value = 1\n", encoding="utf-8")

    state = capture_git_state(nested)
    (nested / "module.py").write_text("value = 2\n", encoding="utf-8")
    changed = capture_git_state(nested)

    assert len(state.snapshot_sha256) == 64
    assert state.snapshot_sha256 != changed.snapshot_sha256


def test_resume_discards_only_a_damaged_trailing_line(tmp_path: Path) -> None:
    path = tmp_path / "results.jsonl.inprogress"
    result = EvaluationRunResult(
        schema_version="0.2",
        run_id="run-1",
        question_id="q-1",
        condition_id="condition-1",
        execution_mode="retrieval_only",
        status="retrieved",
        retrieval=_retrieval("c1"),
        evidence_sent_to_model=None,
        raw_model_output=None,
        repaired_model_output=None,
        final_answer=None,
        citation_validation=None,
        error=None,
        model_call_count=0,
        abstention_cause=None,
    )
    append_jsonl_record(path, result)
    path.write_text(path.read_text(encoding="utf-8") + '{"schema_version":"0.2"', encoding="utf-8")

    recovered = load_inprogress_run_results(path)

    assert [item.run_id for item in recovered] == ["run-1"]
    assert path.read_bytes().endswith(b"\n")


def test_resume_records_trailing_recovery_for_audit(tmp_path: Path) -> None:
    path = tmp_path / "results.jsonl.inprogress"
    recovery_log = tmp_path / "results.recovery.json"
    result = EvaluationRunResult(
        schema_version="0.2",
        run_id="run-1",
        question_id="q-1",
        condition_id="condition-1",
        execution_mode="retrieval_only",
        status="retrieved",
        retrieval=_retrieval("c1"),
        evidence_sent_to_model=None,
        raw_model_output=None,
        repaired_model_output=None,
        final_answer=None,
        citation_validation=None,
        error=None,
        model_call_count=0,
        abstention_cause=None,
    )
    append_jsonl_record(path, result)
    path.write_text(
        path.read_text(encoding="utf-8") + '{"schema_version":"0.2"',
        encoding="utf-8",
    )

    recovered = load_inprogress_run_results(path, recovery_log=recovery_log)

    assert [item.run_id for item in recovered] == ["run-1"]
    recovery = json.loads(recovery_log.read_text(encoding="utf-8"))
    assert recovery["recovered_trailing_record"] is True
    assert recovery["line_number"] == 2


def test_resume_does_not_silently_drop_a_complete_but_invalid_record(tmp_path: Path) -> None:
    path = tmp_path / "results.jsonl.inprogress"
    path.write_text('{"schema_version":"0.2"}\n', encoding="utf-8")

    with pytest.raises(ValueError, match="results.jsonl.inprogress:1"):
        load_inprogress_run_results(path)


def test_resume_rejects_duplicate_question_records(tmp_path: Path) -> None:
    path = tmp_path / "results.jsonl.inprogress"
    result = EvaluationRunResult(
        schema_version="0.2",
        run_id="run-1",
        question_id="q-1",
        condition_id="condition-1",
        execution_mode="retrieval_only",
        status="retrieved",
        retrieval=_retrieval("c1"),
        evidence_sent_to_model=None,
        raw_model_output=None,
        repaired_model_output=None,
        final_answer=None,
        citation_validation=None,
        error=None,
        model_call_count=0,
        abstention_cause=None,
    )
    append_jsonl_record(path, result)
    append_jsonl_record(path, result.model_copy(update={"run_id": "run-2"}))

    with pytest.raises(ValueError, match="duplicate question_id"):
        load_inprogress_run_results(path)


def test_final_jsonl_refuses_to_overwrite_an_existing_file(tmp_path: Path) -> None:
    inprogress = tmp_path / "results.jsonl.inprogress"
    final = tmp_path / "results.jsonl"
    result = EvaluationRunResult(
        schema_version="0.2",
        run_id="run-1",
        question_id="q-1",
        condition_id="condition-1",
        execution_mode="retrieval_only",
        status="retrieved",
        retrieval=_retrieval("c1"),
        evidence_sent_to_model=None,
        raw_model_output=None,
        repaired_model_output=None,
        final_answer=None,
        citation_validation=None,
        error=None,
        model_call_count=0,
        abstention_cause=None,
    )
    append_jsonl_record(inprogress, result)
    final.write_text("already complete\n", encoding="utf-8")

    with pytest.raises(FileExistsError):
        write_final_jsonl(inprogress, final)


def test_final_jsonl_does_not_promote_a_damaged_checkpoint(tmp_path: Path) -> None:
    inprogress = tmp_path / "results.jsonl.inprogress"
    final = tmp_path / "results.jsonl"
    inprogress.write_text('{"schema_version":"0.2"', encoding="utf-8")

    with pytest.raises(ValueError):
        write_final_jsonl(inprogress, final)

    assert not final.exists()


def _manifest(execution_mode: str) -> RunManifest:
    return RunManifest(
        run_id="batch-1",
        condition_id="condition-1",
        dataset_version="dataset-1",
        split="dev",
        corpus_version="corpus-1",
        chunk_version="chunks-1",
        embedding_version="embedding-1",
        index_version="index-1",
        generation_model="fixture-model" if execution_mode != "retrieval_only" else None,
        prompt_version="prompt-1" if execution_mode != "retrieval_only" else None,
        profile="intermediate" if execution_mode != "retrieval_only" else "none",
        execution_mode=execution_mode,
        retrieval_mode="fixture",
        top_k=3,
        k_values=[1, 3],
        threshold=None,
        git_commit="abc123",
        git_dirty=False,
        git_snapshot_sha256="snapshot-1",
    )


def test_resume_rejects_a_changed_manifest_context(tmp_path: Path) -> None:
    output = tmp_path / "resume.jsonl"
    checkpoint = Path(str(output) + ".inprogress")
    manifest = _manifest("retrieval_only")
    result = EvaluationRunResult(
        schema_version="0.2",
        run_id="run-resume",
        question_id="q-1",
        condition_id=manifest.condition_id,
        execution_mode=manifest.execution_mode,
        status="retrieved",
        retrieval=_retrieval("c1"),
        evidence_sent_to_model=None,
        raw_model_output=None,
        repaired_model_output=None,
        final_answer=None,
        citation_validation=None,
        error=None,
        model_call_count=0,
        abstention_cause=None,
    )
    append_jsonl_record(checkpoint, result)
    Path(str(checkpoint) + ".manifest.inprogress").write_text(
        manifest.model_dump_json(), encoding="utf-8"
    )

    changed = manifest.model_copy(update={"top_k": 5, "k_values": [1, 3, 5]})
    with pytest.raises(ValueError, match="manifest"):
        run_batch(
            [_gold()],
            changed,
            _FakeRetriever(_retrieval("c1")),
            output_path=output,
            resume=True,
        )


class _GeneratorWithoutTrace:
    def generate(
        self,
        question: str,
        profile: StudentProfile,
        retrieval: RetrievalResult,
    ) -> GeneratedAnswer:
        del question, profile
        return GeneratedAnswer(
            final_choice="A",
            explanation="The first chunk supports the answer.",
            citations=[retrieval.hits[0].chunk_id],
        )


def test_synthetic_generation_trace_requires_a_non_reportable_manifest() -> None:
    with pytest.raises(ValueError, match="synthetic"):
        run_batch(
            [_gold()],
            _manifest("retrieval_and_generation"),
            _FakeRetriever(_retrieval("c1")),
            generator=_GeneratorWithoutTrace(),
            profile_provider=lambda sample: StudentProfile(
                profile_id="profile-1", level=StudentLevel.INTERMEDIATE
            ),
            require_generation_trace=False,
        )


class _FakeRetriever:
    def __init__(self, retrieval: RetrievalResult) -> None:
        self.retrieval = retrieval

    def retrieve(self, query: str, top_k: int, mode: str) -> RetrievalResult:
        return self.retrieval


class _FakeGenerator:
    def __init__(self) -> None:
        self.calls = 0
        self.last_trace = None

    def generate(
        self,
        question: str,
        profile: StudentProfile,
        retrieval: RetrievalResult,
    ) -> GeneratedAnswer:
        self.calls += 1
        answer = GeneratedAnswer(
            final_choice="A",
            explanation="The first chunk supports the answer.",
            citations=[retrieval.hits[0].chunk_id],
        )
        self.last_trace = SimpleNamespace(
            attempts=1,
            raw_model_output=answer.model_dump_json(),
            repaired_model_output=None,
            prompt_evidence_chunk_ids=[hit.chunk_id for hit in retrieval.hits],
            prompt_sha256="a" * 64,
        )
        return answer


class _ParseThenProviderFailureGenerator:
    last_trace = SimpleNamespace(
        attempts=2,
        raw_model_output="not-json",
        repaired_model_output=None,
        failure_types=("LLMOutputValidationError", "LLMProviderError"),
        prompt_evidence_chunk_ids=["c1"],
        prompt_sha256="b" * 64,
    )

    def generate(
        self,
        question: str,
        profile: StudentProfile,
        retrieval: RetrievalResult,
    ) -> GeneratedAnswer:
        del question, profile, retrieval
        raise GenerationError("provider failed after a parse retry")


class _StaleTraceGenerator:
    def __init__(self) -> None:
        self.last_trace = SimpleNamespace(
            attempts=1,
            raw_model_output="from-the-previous-question",
            repaired_model_output=None,
            failure_types=(),
            prompt_evidence_chunk_ids=["old-chunk"],
            prompt_sha256="c" * 64,
        )

    def generate(
        self,
        question: str,
        profile: StudentProfile,
        retrieval: RetrievalResult,
    ) -> GeneratedAnswer:
        del question, profile, retrieval
        raise GenerationError("failed before producing a new trace")


class _DuplicatePromptTraceGenerator:
    last_trace = None

    def generate(
        self,
        question: str,
        profile: StudentProfile,
        retrieval: RetrievalResult,
    ) -> GeneratedAnswer:
        del question, profile
        answer = GeneratedAnswer(
            final_choice="A",
            explanation="The first chunk supports the answer.",
            citations=[retrieval.hits[0].chunk_id],
        )
        self.last_trace = SimpleNamespace(
            attempts=1,
            raw_model_output=answer.model_dump_json(),
            repaired_model_output=None,
            prompt_evidence_chunk_ids=["c1", "c1"],
            prompt_sha256="d" * 64,
            failure_types=(),
        )
        return answer


class _ParseFailureWithTraceGenerator:
    last_trace = None

    def generate(
        self,
        question: str,
        profile: StudentProfile,
        retrieval: RetrievalResult,
    ) -> GeneratedAnswer:
        del question, profile, retrieval
        self.last_trace = SimpleNamespace(
            attempts=1,
            raw_model_output="not-json",
            repaired_model_output=None,
            failure_types=("LLMOutputValidationError",),
            prompt_evidence_chunk_ids=["c1"],
            prompt_sha256="e" * 64,
        )
        raise GenerationError("parse failed")


def test_batch_runner_stops_after_retrieval_in_retrieval_only_mode() -> None:
    generator = _FakeGenerator()
    results = run_batch(
        [_gold()],
        _manifest("retrieval_only"),
        _FakeRetriever(_retrieval("c1")),
        generator=generator,
        profile_provider=lambda sample: StudentProfile(
            profile_id="profile-1", level=StudentLevel.INTERMEDIATE
        ),
    )

    assert results[0].status is RunStatus.RETRIEVED
    assert generator.calls == 0


def test_batch_runner_uses_the_terminal_failure_stage() -> None:
    results = run_batch(
        [_gold()],
        _manifest("retrieval_and_generation"),
        _FakeRetriever(_retrieval("c1")),
        generator=_ParseThenProviderFailureGenerator(),
        profile_provider=lambda sample: StudentProfile(
            profile_id="profile-1", level=StudentLevel.INTERMEDIATE
        ),
    )

    assert results[0].status is RunStatus.GENERATION_ERROR


def test_batch_runner_does_not_reuse_a_previous_generation_trace() -> None:
    results = run_batch(
        [_gold()],
        _manifest("retrieval_and_generation"),
        _FakeRetriever(_retrieval("c1")),
        generator=_StaleTraceGenerator(),
        profile_provider=lambda sample: StudentProfile(
            profile_id="profile-1", level=StudentLevel.INTERMEDIATE
        ),
    )

    assert results[0].status is RunStatus.GENERATION_ERROR
    assert results[0].raw_model_output is None
    assert results[0].model_call_count == 0


def test_batch_runner_converts_profile_provider_failure_to_a_saved_error() -> None:
    def failing_profile(sample: GoldSample) -> StudentProfile:
        del sample
        raise ValueError("invalid profile fixture")

    results = run_batch(
        [_gold()],
        _manifest("retrieval_and_generation"),
        _FakeRetriever(_retrieval("c1")),
        generator=_FakeGenerator(),
        profile_provider=failing_profile,
    )

    assert results[0].status is RunStatus.GENERATION_ERROR
    assert results[0].retrieval is not None
    assert results[0].evidence_sent_to_model is not None
    assert results[0].model_call_count == 0


def test_batch_runner_converts_evidence_builder_failure_to_a_saved_error() -> None:
    def failing_evidence(retrieval: RetrievalResult) -> EvidenceBundle:
        del retrieval
        raise ValueError("invalid evidence fixture")

    results = run_batch(
        [_gold()],
        _manifest("retrieval_and_generation"),
        _FakeRetriever(_retrieval("c1")),
        generator=_FakeGenerator(),
        profile_provider=lambda sample: StudentProfile(
            profile_id="profile-1", level=StudentLevel.INTERMEDIATE
        ),
        evidence_builder=failing_evidence,
    )

    assert results[0].status is RunStatus.GENERATION_ERROR
    assert results[0].evidence_sent_to_model is None
    assert results[0].model_call_count == 0


def test_batch_runner_preserves_answer_when_only_prompt_trace_is_invalid() -> None:
    results = run_batch(
        [_gold()],
        _manifest("retrieval_and_generation"),
        _FakeRetriever(_retrieval("c1")),
        generator=_DuplicatePromptTraceGenerator(),
        profile_provider=lambda sample: StudentProfile(
            profile_id="profile-1", level=StudentLevel.INTERMEDIATE
        ),
    )

    assert results[0].status is RunStatus.ANSWERED
    assert results[0].final_answer is not None
    assert results[0].citation_validation is not None
    assert results[0].raw_model_output is not None
    assert results[0].model_call_count == 1
    assert results[0].prompt_evidence_chunk_ids is None
    assert results[0].prompt_sha256 is None


def test_batch_runner_preserves_valid_prompt_trace_on_parse_error() -> None:
    results = run_batch(
        [_gold()],
        _manifest("retrieval_and_generation"),
        _FakeRetriever(_retrieval("c1")),
        generator=_ParseFailureWithTraceGenerator(),
        profile_provider=lambda sample: StudentProfile(
            profile_id="profile-1", level=StudentLevel.INTERMEDIATE
        ),
    )

    assert results[0].status is RunStatus.PARSE_ERROR
    assert results[0].raw_model_output == "not-json"
    assert results[0].model_call_count == 1
    assert results[0].prompt_evidence_chunk_ids == ["c1"]
    assert results[0].prompt_sha256 == "e" * 64


def test_batch_runner_marks_empty_retrieval_as_a_non_model_abstention() -> None:
    generator = _FakeGenerator()
    results = run_batch(
        [_gold()],
        _manifest("retrieval_and_generation"),
        _FakeRetriever(_retrieval()),
        generator=generator,
        profile_provider=lambda sample: StudentProfile(
            profile_id="profile-1", level=StudentLevel.INTERMEDIATE
        ),
    )

    assert results[0].status is RunStatus.ABSTAINED
    assert results[0].abstention_cause is AbstentionCause.NO_RETRIEVAL_HITS
    assert results[0].model_invoked is False
    assert generator.calls == 0


def test_batch_runner_persists_generation_trace_fields() -> None:
    generator = _FakeGenerator()
    results = run_batch(
        [_gold()],
        _manifest("retrieval_and_generation"),
        _FakeRetriever(_retrieval("c1")),
        generator=generator,
        profile_provider=lambda sample: StudentProfile(
            profile_id="profile-1", level=StudentLevel.INTERMEDIATE
        ),
    )

    result = results[0]
    assert result.status is RunStatus.ANSWERED
    assert result.model_invoked is True
    assert result.prompt_evidence_chunk_ids == ["c1"]
    assert result.prompt_sha256 == "a" * 64


def test_batch_runner_accepts_the_real_generator_trace() -> None:
    generator = PersonalisedAnswerGenerator(MockJsonLLMClient())
    results = run_batch(
        [_gold()],
        _manifest("retrieval_and_generation"),
        _FakeRetriever(_retrieval("c1")),
        generator=generator,
        profile_provider=lambda sample: StudentProfile(
            profile_id="profile-1", level=StudentLevel.INTERMEDIATE
        ),
    )

    result = results[0]
    assert result.status is RunStatus.ANSWERED
    assert result.raw_model_output is not None
    assert result.prompt_evidence_chunk_ids == ["c1"]
