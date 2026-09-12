import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from cs30.evaluation import (
    AnnotationStatus,
    EvaluationSplit,
    GoldSample,
    SourceSplit,
    load_gold_samples,
)


def _m3_payload() -> dict[str, object]:
    return {
        "question_id": "sciq-test-00001",
        "source_split": "test",
        "question": "Which option is supported?",
        "options": {
            "A": {"text": "wrong", "source_field": "distractor1"},
            "B": {"text": "right", "source_field": "correct_answer"},
            "C": {"text": "wrong two", "source_field": "distractor2"},
            "D": {"text": "wrong three", "source_field": "distractor3"},
        },
        "gold_answer": "B",
        "gold_answer_text": "right",
        "answerable": True,
        "gold_core_evidence_sets": [
            [
                {
                    "span_id": "span-1",
                    "block_id": "block-1",
                    "document_id": "book-1",
                    "chapter_id": "18",
                    "char_start": 0,
                    "char_end": 13,
                    "verbatim_text": "Evidence text",
                    "sufficiency": "core_sufficient",
                    "annotation_note": "Directly supports the answer.",
                }
            ]
        ],
        "partial_evidence": [],
        "question_difficulty": "medium",
        "question_type": "identification",
        "concept_group": "concept-1",
        "personalisation_eligibility": "none",
        "eligibility_reason": "The item is direct.",
        "split": "proposed_test",
        "corpus_version": "book-1",
        "parser_version": "1.2.0",
        "gold_annotation_version": "m3_gold_v0.1",
        "annotation_status": "m3_initial",
        "review_record_id": "m3_review_sciq-test-00001",
        "source": {
            "dataset": "SciQ standardized",
            "source_question_id": "sciq-test-00001",
            "support": "Evidence text",
        },
    }


def test_m3_record_preserves_the_published_gold_contract() -> None:
    sample = GoldSample.model_validate(_m3_payload())

    assert sample.source_split is SourceSplit.TEST
    assert sample.split is EvaluationSplit.PROPOSED_TEST
    assert sample.annotation_status is AnnotationStatus.M3_INITIAL
    assert sample.options["B"].text == "right"
    assert sample.options["B"].source_field == "correct_answer"
    assert sample.gold_answer_text == "right"
    assert sample.source is not None
    assert sample.source.dataset == "SciQ standardized"
    span = sample.gold_core_evidence_sets[0][0]
    assert span.chapter_id == "18"
    assert span.block_id == "block-1"
    assert span.sufficiency.value == "core_sufficient"


def test_m3_loader_replays_chapter_local_coordinates(tmp_path: Path) -> None:
    path = tmp_path / "gold_v0_1.jsonl"
    path.write_text(json.dumps(_m3_payload()) + "\n", encoding="utf-8")

    samples = load_gold_samples(
        path,
        chapter_documents={("book-1", "18"): "Evidence text"},
    )

    assert samples[0].question_id == "sciq-test-00001"


def test_m3_loader_requires_the_matching_chapter_document(tmp_path: Path) -> None:
    path = tmp_path / "gold_v0_1.jsonl"
    path.write_text(json.dumps(_m3_payload()) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="chapter_id=18"):
        load_gold_samples(
            path,
            chapter_documents={("book-1", "17"): "Evidence text"},
        )


def test_legacy_gold_options_remain_supported() -> None:
    payload = _m3_payload()
    payload.pop("source_split")
    payload.pop("gold_answer_text")
    payload.pop("source")
    payload["options"] = {key: value["text"] for key, value in payload["options"].items()}
    payload["split"] = "dev"
    payload["annotation_status"] = "reviewed"
    for evidence_set in payload["gold_core_evidence_sets"]:
        for span in evidence_set:
            for key in ("block_id", "chapter_id", "sufficiency", "annotation_note"):
                span.pop(key)

    sample = GoldSample.model_validate(payload)

    assert sample.options["B"].text == "right"


def test_m3_metadata_is_not_silently_partial() -> None:
    payload = _m3_payload()
    payload.pop("source")

    with pytest.raises(ValidationError, match="source"):
        GoldSample.model_validate(payload)
