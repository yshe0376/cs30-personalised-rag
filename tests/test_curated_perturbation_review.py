"""Offline guard tests for source-bound perturbation review artifacts."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts/build_dev_diagnostics.py"
_SPEC = importlib.util.spec_from_file_location("dev_diagnostics_review", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)


@pytest.fixture
def review_inputs():
    """A complete small matrix; all answers and verdicts here are test fixtures."""
    targets = ["B1", "B4", "A1", "I3", "correctness", "evidence_support"]
    generators = ["gpt-oss", "llama", "gemma"]
    levels = {"B1": "beginner", "B4": "beginner", "A1": "advanced", "I3": "intermediate"}
    criteria = {t: {"level": levels[t], "description": "Fixture criterion"} for t in levels}
    source = {
        "dev-" + g: {"items": {}, "correctness": {}, "adaptation": [], "evidence": []}
        for g in generators
    }
    edits = []
    rubrics = {}
    for target in targets:
        for index, generator in enumerate(generators):
            label = f"{target}-{generator}"
            answer = f"Saved correct answer for {label}."
            item = {
                "evaluation_id": label,
                "run_id": "run-" + label,
                "question_id": "question-" + label,
                "target_level": levels.get(target, "advanced"),
                "condition": "P1R1_combined",
                "question": "Fixture question " + label,
                "answer": answer,
                "technical_failure": False,
                "abstained": False,
                "evidence": [{"evidence_id": "e1", "text": "Fixture supplied text."}],
            }
            data = source["dev-" + generator]
            data["items"][label] = item
            data["correctness"][item["run_id"]] = {"score_status": "scored", "score": 2}
            data["adaptation"].append(
                {
                    "evaluation_id": label,
                    "is_target_level_evaluation": True,
                    "criteria": [{"criterion_id": target, "verdict": "pass"}],
                }
            )
            data["evidence"].append(
                {"evaluation_id": label, "claims": [{"bundle_support": "supported"}]}
            )
            rubrics[item["question_id"]] = {"question_id": item["question_id"]}
            start = answer.index("correct")
            edits.append(
                {
                    "case_id": label,
                    "target": target,
                    "generator": generator,
                    "source_evaluation_id": label,
                    "source_question_id": item["question_id"],
                    "source_target_level": item["target_level"],
                    "source_condition": item["condition"],
                    "source_answer_sha256": hashlib.sha256(answer.encode()).hexdigest(),
                    "physics_domain": label,
                    "edit": {
                        "start": start,
                        "end": start + 7,
                        "original_span": "correct",
                        "perturbed_span": "changed-" + label,
                    },
                    "selection_reason": "Fixture coverage",
                    "perturbation_type": "fixture-" + label,
                    "expected_non_target_invariants": ["Fixture invariant"],
                    "review_focus": "Fixture pending review",
                    "review_only_external_references": [
                        {"url": "https://example.org/review-only", "purpose": "Fixture review"}
                    ],
                    "difficulty_proposal": ["clear", "moderate", "subtle"][index],
                    "difficulty_rationale": "Fixture pre-run label",
                }
            )
    package = {
        "schema_version": "m8-curated-perturbation-edits-2",
        "expected_case_count": 18,
        "targets": targets,
        "generators": generators,
        "cases": edits,
        "source_profile_package_sha256": "fixture-profile",
        "source_scoring_bundle_manifest_sha256": "fixture-manifest",
        "selection_method": "Fixture purposeful selection",
        "difficulty_design": "Fixture one of each difficulty per target",
    }
    return source, criteria, rubrics, package


def test_reconstruction_preserves_originals_and_does_not_inherit_approval(review_inputs):
    before = copy.deepcopy(review_inputs)
    package = review_inputs[3]
    package["cases"][0]["reviewer"] = "not-an-actual-approval"
    cases = _MODULE.build_curated_cases(*review_inputs)
    assert len(cases) == 18
    for case in cases:
        edit = case["single_edit"]
        original = case["original_answer"]
        assert case["perturbed_answer"] == (
            original[: edit["start"]] + edit["perturbed_span"] + original[edit["end"] :]
        )
        assert case["reviewer"] is None
        assert not case["criterion_isolation_verified"]
        assert not case["internal_consistency_confirmed"]
        assert case["paid_result"] is None
    assert review_inputs[:3] == before[:3]
    evidence = next(c for c in cases if c["target"] == "evidence_support")
    assert evidence["supplied_evidence"] == [
        {"evidence_id": "e1", "text": "Fixture supplied text."}
    ]
    assert "https://example.org" not in json.dumps(evidence["supplied_evidence"])


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("source_answer_sha256", "outdated", "hash mismatch"),
        ("source_condition", "wrong-condition", "identity mismatch"),
        ("source_target_level", "wrong-level", "identity mismatch"),
    ],
)
def test_stale_source_bindings_are_rejected(review_inputs, field, value, message):
    review_inputs[3]["cases"][0][field] = value
    with pytest.raises(ValueError, match=message):
        _MODULE.build_curated_cases(*review_inputs)


@pytest.mark.parametrize("change", ["question", "pair", "id", "domain", "difficulty", "block"])
def test_repetitive_or_incomplete_design_is_rejected(review_inputs, change):
    edits = review_inputs[3]["cases"]
    if change == "question":
        edits[1]["source_question_id"] = edits[0]["source_question_id"]
    elif change == "pair":
        edits[1]["generator"] = edits[0]["generator"]
    elif change == "id":
        edits[1]["case_id"] = edits[0]["case_id"]
    elif change == "domain":
        for edit in edits:
            edit["physics_domain"] = "same-domain"
    elif change == "difficulty":
        edits[1]["difficulty_proposal"] = edits[0]["difficulty_proposal"]
    else:
        edits[1]["edit"]["perturbed_span"] = edits[0]["edit"]["perturbed_span"]
    with pytest.raises(ValueError):
        _MODULE.build_curated_cases(*review_inputs)


@pytest.mark.parametrize("change", ["span", "offset", "noop", "score", "target", "evidence"])
def test_invalid_edits_and_unqualified_bases_are_rejected(review_inputs, change):
    source, _, _, package = review_inputs
    edit = package["cases"][0]["edit"]
    if change == "span":
        edit["original_span"] = "wrong quoted text"
    elif change == "offset":
        edit["end"] = 999999
    elif change == "noop":
        edit["perturbed_span"] = edit["original_span"]
    elif change == "score":
        source["dev-gpt-oss"]["correctness"]["run-B1-gpt-oss"]["score"] = 1
    elif change == "target":
        source["dev-gpt-oss"]["adaptation"][0]["criteria"][0]["verdict"] = "fail"
    else:
        source["dev-gpt-oss"]["evidence"][-1]["claims"][0]["bundle_support"] = "unsupported"
    with pytest.raises(ValueError):
        _MODULE.build_curated_cases(*review_inputs)


def test_writer_keeps_every_case_pending_and_difficulty_preassigned(review_inputs, tmp_path):
    cases = _MODULE.build_curated_cases(*review_inputs)
    plan = _MODULE.write_curated_review(tmp_path, cases, review_inputs[3], "fixture-edits-hash")
    assert plan["coverage"]["unique_question_count"] == 18
    assert plan["coverage"]["by_difficulty_proposal"] == {"clear": 6, "moderate": 6, "subtle": 6}
    assert plan["coverage"]["human_reviews_completed"] == 0
    assert plan["paid_calls"] == 0
    assert not plan["thresholds_frozen"]
    assert not plan["difficulty_labels_frozen"]
    sheet = (tmp_path / "REVIEW_PENDING.md").read_text(encoding="utf-8")
    assert sheet.count("Full-answer internal consistency: **pending**.") == 18
    assert sheet.count("Other-criterion effects / physics preservation: **pending**.") == 18
