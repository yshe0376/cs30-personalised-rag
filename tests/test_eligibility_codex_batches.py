"""Tests for the Codex eligibility-labelling batch script and the committed sidecar."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cs30.evaluation.v2_generation_models import EligibilityRecord
from scripts import eligibility_codex_batches as batches

REPO = Path(__file__).resolve().parents[1]
SIDECAR = REPO / "docs" / "evaluation" / "eligibility-v1" / "personalisation_eligibility_v1.jsonl"
ANNOTATIONS = REPO / "docs" / "evaluation" / "eligibility-v1" / "annotations_v1.jsonl"


def _output(beginner: list[str], advanced: list[str], *, concern: bool = False) -> dict:
    def judgements(ids: tuple[str, ...], verdicts: list[str]) -> list[dict]:
        return [
            {"criterion_id": criterion, "note": "n", "verdict": verdict}
            for criterion, verdict in zip(ids, verdicts, strict=True)
        ]

    return {
        "question_id": "q1",
        "question_demand": "identify_or_name",
        "intermediate_reference_answer": "Answer.",
        "intermediate_check": judgements(("I1", "I2", "I3"), ["pass"] * 3),
        "beginner_criteria": judgements(batches.CRITERIA["beginner_criteria"], beginner),
        "advanced_criteria": judgements(batches.CRITERIA["advanced_criteria"], advanced),
        "gold_answer_concern": concern,
        "gold_answer_concern_note": "note" if concern else None,
        "reason": "r",
    }


PASS_A = ["pass", "not_applicable", "not_applicable", "pass"]


@pytest.mark.parametrize(
    ("beginner", "advanced", "label", "review"),
    [
        (["fail", "fail", "pass", "pass"], ["pass", "pass", "fail", "pass"], "full", []),
        (["fail", "pass", "pass", "pass"], PASS_A, "endpoint_only", []),
        (["pass", "pass", "not_applicable", "pass"], PASS_A, "none", []),
        (["uncertain", "pass", "pass", "pass"], PASS_A, "endpoint_only", ["uncertain_verdict"]),
        (
            ["fail", "pass", "pass", "pass"],
            ["pass", "uncertain", "not_applicable", "pass"],
            "endpoint_only",
            ["uncertain_verdict"],
        ),
    ],
)
def test_map_label(beginner: list[str], advanced: list[str], label: str, review: list[str]) -> None:
    output = _output(beginner, advanced)
    assert batches.validate(output) == []
    assert batches.map_label(output) == (label, review)


def test_validate_rejects_rule_violations() -> None:
    output = _output(["not_applicable", "pass", "pass", "pass"], PASS_A, concern=True)
    output["intermediate_check"][1]["verdict"] = "fail"
    output["gold_answer_concern_note"] = None
    errors = batches.validate(output)
    assert "B1: always assessed, cannot be not_applicable" in errors
    assert "I2: verdict 'fail' not allowed" in errors
    assert "gold_answer_concern requires a note" in errors


def test_committed_sidecar_matches_annotations_and_m8_contract() -> None:
    rows = [json.loads(line) for line in SIDECAR.read_text(encoding="utf-8").splitlines()]
    records = [EligibilityRecord.model_validate(row) for row in rows]
    assert len(records) == 341
    assert len({record.question_id for record in records}) == 341
    annotations = {
        row["question_id"]: row
        for row in map(json.loads, ANNOTATIONS.read_text(encoding="utf-8").splitlines())
    }
    for row in rows:
        assert batches.validate(annotations[row["question_id"]]) == []
        assert batches.map_label(annotations[row["question_id"]])[0] == row["eligibility"]
