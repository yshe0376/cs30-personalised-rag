"""Offline PR #224 readiness and source-bound analysis. Never invokes a provider."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from .judge_results import load_judge_evaluation_outputs
from .level_profiles import canonical_json_sha256, load_profile_checklist_package
from .open_answer_models import OpenAnswerRubric
from .open_answer_scoring import canonical_hash
from .test_gate_analysis import DECISION_RECORD, POLICY_VERSION, PROFILE_SHA, registered_analysis
from .v2_generation_artifacts import load_open_answer_scores
from .v2_generation_models import (
    EligibilityReviewWaiver,
    GenerationEvaluationInput,
    JudgeConfiguration,
)

FROZEN_JUDGE_FILE_SHA = "90293ebf1248d58935490f37ffda4a11591f8265bd28125d540d45f40e11eb19"
FROZEN_SPLIT_SHA = "991d9a68d0fa256b5d418549ffa62c331c6f31c0aacbc144f064f507bfd100fb"


def file_sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def objects(path):
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def write_json(path, value):
    if path.exists():
        raise ValueError("output already exists; choose a separate new file")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps(value, indent=2, sort_keys=True) + "\n").encode())


def prepare(args):
    """Bind IDs/rubrics/configuration without opening generated Test answers."""
    profile = load_profile_checklist_package(args.profiles)
    if profile.package_sha256 != PROFILE_SHA:
        raise ValueError("PR #224 applies only to the recorded frozen profile")
    if file_sha(args.judge_config) != FROZEN_JUDGE_FILE_SHA:
        raise ValueError("use the unchanged approved full-Dev low judge configuration")
    JudgeConfiguration.model_validate_json(args.judge_config.read_bytes())
    validation = json.loads(args.input_validation.read_text(encoding="utf-8"))
    waiver = EligibilityReviewWaiver.model_validate(validation.get("eligibility_review_waiver"))
    gold_sha = file_sha(args.gold)
    if not (
        validation.get("valid") is True
        and validation.get("reportable_input_validation") is True
        and validation.get("gold_sha256") == gold_sha
        and validation.get("profile_package_sha256") == PROFILE_SHA
        and validation.get("eligibility_sha256") == waiver.eligibility_sha256
        and validation.get("eligibility_human_calibrated") is False
    ):
        raise ValueError("input-validation record does not bind the approved waiver/Gold/profile")
    ids = [
        line.strip()
        for line in args.question_ids.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if len(ids) != 187 or len(set(ids)) != 187:
        raise ValueError("the frozen Test must contain 187 unique question IDs")
    if file_sha(args.split_map) != FROZEN_SPLIT_SHA:
        raise ValueError("use the frozen Dev154/Test187 split map")
    split = json.loads(args.split_map.read_text(encoding="utf-8"))
    if set(ids) != {qid for qid, label in split.items() if label == "test"}:
        raise ValueError("Test IDs differ from the frozen full Test, not a selectable subset")
    if not set(ids) <= set(validation.get("question_ids", [])):
        raise ValueError("Test IDs are not covered by the input-validation record")
    if file_sha(args.rubrics) != args.expected_rubrics_sha256:
        raise ValueError("rubric file differs from the expected M7 source-manifest digest")
    rubrics = [OpenAnswerRubric.model_validate(row) for row in objects(args.rubrics)]
    by_question = {rubric.question_id: rubric for rubric in rubrics}
    if len(by_question) != len(rubrics) or set(by_question) != set(ids):
        raise ValueError("rubrics must cover each frozen Test question exactly once")
    if any(rubric.gold_sha256 != gold_sha for rubric in rubrics):
        raise ValueError("Test rubric is bound to different Gold")
    per_question = {
        qid: canonical_hash(rubric.model_dump(mode="json"))
        for qid, rubric in sorted(by_question.items())
    }
    rubric_set_sha = canonical_json_sha256(
        [{"question_id": qid, "rubric_sha256": digest} for qid, digest in per_question.items()]
    )
    record = {
        "schema_version": "test-readiness-224-v1",
        "policy": POLICY_VERSION,
        "decision_record": DECISION_RECORD,
        "profile_package_sha256": PROFILE_SHA,
        "judge_config_sha256": file_sha(args.judge_config),
        "gold_sha256": gold_sha,
        "eligibility_sha256": waiver.eligibility_sha256,
        "input_validation_sha256": file_sha(args.input_validation),
        "test_question_ids": sorted(ids),
        "question_ids_file_sha256": file_sha(args.question_ids),
        "split_map_sha256": file_sha(args.split_map),
        "rubric_file_sha256": file_sha(args.rubrics),
        "correctness_rubric_set_sha256": rubric_set_sha,
        "per_question_rubric_sha256": per_question,
        "rubrics_frozen_by_Leader_waiver": True,
        "rubrics_independently_reviewed": False,
        "eligibility_human_calibrated": False,
        "primary_metric": "adaptation_criterion_pass_rate",
        "primary_contrast": "P1R0-P0R0",
        "co_primary_levels": ["beginner", "advanced"],
        "multiplicity": "Holm, alpha=0.05",
        "correctness_noninferiority_delta": 0.03,
        "adapted": "every applicable main criterion passes",
        "primary_model": "gpt-oss-20b",
        "comparison_models": ["gemma-3-12b", "llama-3.1-8b"],
        "expected_cells_per_generator": 2244,
        "bootstrap_draws": 2000,
        "bootstrap_seed": 5703,
        "paid_execution_authorized": False,
        "budget_status": "separate approval required",
        "generated_answers_read_during_preparation": False,
        "provider_calls": 0,
    }
    write_json(args.output, record)
    return record


def report(args):
    """Explicit post-scoring entry; preparation never calls this function."""
    ready = json.loads(args.readiness.read_text(encoding="utf-8"))
    if (
        ready.get("schema_version") != "test-readiness-224-v1"
        or ready.get("policy") != POLICY_VERSION
    ):
        raise ValueError("unrecognised Test-readiness record")
    if ready.get("profile_package_sha256") != PROFILE_SHA:
        raise ValueError("report uses a different frozen profile")
    if (
        ready.get("judge_config_sha256") != FROZEN_JUDGE_FILE_SHA
        or ready.get("split_map_sha256") != FROZEN_SPLIT_SHA
    ):
        raise ValueError("readiness does not retain the approved judge/split hashes")
    rubric_hashes = ready["per_question_rubric_sha256"]
    if set(rubric_hashes) != set(ready["test_question_ids"]) or canonical_json_sha256(
        [
            {"question_id": qid, "rubric_sha256": digest}
            for qid, digest in sorted(rubric_hashes.items())
        ]
    ) != ready.get("correctness_rubric_set_sha256"):
        raise ValueError("readiness frozen per-question rubric set is inconsistent")
    items = [GenerationEvaluationInput.model_validate(row) for row in objects(args.inputs)]
    qids = set(ready["test_question_ids"])
    if len(qids) != 187 or len(items) != 2244 or any(i.source_split != "test" for i in items):
        raise ValueError("report requires the full 187-question Test matrix")
    actual = {(i.question_id, i.target_level.value, i.condition.value) for i in items}
    expected = {
        (q, level, arm)
        for q in qids
        for level in ("beginner", "intermediate", "advanced")
        for arm in ("P0R0_plain", "P1R0_prompt_only", "P0R1_reranking_only", "P1R1_combined")
    }
    if len(actual) != len(items) or actual != expected:
        raise ValueError("Test matrix contains missing, duplicate or extra cells")
    manifest = json.loads(args.adapter_manifest.read_text(encoding="utf-8"))
    inputs_sha = file_sha(args.inputs)
    if (
        manifest.get("output_sha256", {}).get("generation_evaluation_inputs") != inputs_sha
        or manifest.get("gold_sha256") != ready["gold_sha256"]
        or manifest.get("input_sha256", {}).get("eligibility") != ready["eligibility_sha256"]
        or any(i.source_run_sha256 != manifest.get("source_run_sha256") for i in items)
    ):
        raise ValueError("adapter/input readiness binding mismatch")
    scores = load_open_answer_scores(
        args.correctness_scores,
        items,
        gold_sha256=ready["gold_sha256"],
        binding_path=args.correctness_binding,
        evaluation_inputs_sha256=inputs_sha,
    )
    for score in scores.values():
        if score.rubric_sha256 != ready["per_question_rubric_sha256"][score.question_id]:
            raise ValueError("correctness score uses a different frozen per-question rubric")
    judged = load_judge_evaluation_outputs(args.judge_evaluation_dir)
    provenance = judged["manifest"].get("provenance", {})
    if (
        provenance.get("evaluation_inputs_sha256") != inputs_sha
        or provenance.get("source_run_sha256") != manifest.get("source_run_sha256")
        or provenance.get("profile_package_sha256") != PROFILE_SHA
        or provenance.get("judge_configuration_sha256") != ready["judge_config_sha256"]
        or provenance.get("reverse_adaptation_criteria") is not False
    ):
        raise ValueError("judge results are not bound to the frozen Test run/configuration")
    numeric = {
        eid: score.score if score.score_status == "scored" else None
        for eid, score in scores.items()
    }
    floors = None
    if args.noise_floors is not None:
        noise = json.loads(args.noise_floors.read_text(encoding="utf-8"))
        if (
            noise.get("policy") != POLICY_VERSION
            or noise.get("profile_package_sha256") != PROFILE_SHA
            or noise.get("source_split") != "dev"
            or noise.get("metric") != "adaptation_criterion_pass_rate"
            or noise.get("scope") != "generation_repeat"
            or not isinstance(noise.get("source_artifact_sha256"), str)
            or len(noise["source_artifact_sha256"]) != 64
            or any(c not in "0123456789abcdef" for c in noise["source_artifact_sha256"])
        ):
            raise ValueError("noise floors require a Dev adaptation-repeat source record")
        floors = noise["adaptation_noise_floors"]
    result = registered_analysis(
        items, numeric, judged["adaptation"], draws=2000, seed=5703, adaptation_noise_floors=floors
    )
    result.update(
        {
            "readiness_sha256": file_sha(args.readiness),
            "source_inputs_sha256": inputs_sha,
            "correctness_rubric_set_sha256": ready["correctness_rubric_set_sha256"],
            "noise_floor_record_sha256": file_sha(args.noise_floors) if args.noise_floors else None,
            "label_and_rubric_human_review_waived": True,
            "claim_boundary": "Independent judge evaluation, not verified learner outcomes.",
            "reference_outputs": {
                "discrimination": {
                    "resolved_rows": len(judged["discrimination"]),
                    "status": "reference_only",
                },
                "citation_support": {
                    "resolved_rows": len(judged["evidence_support"]),
                    "status": "reference_only; raw citation_ids unchanged",
                },
            },
            "judge_output_manifest_sha256": file_sha(
                args.judge_evaluation_dir / "judge_evaluation_manifest.json"
            ),
        }
    )
    write_json(args.output, result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prep = commands.add_parser("prepare", help="metadata/rubric preflight; no generated answers")
    for name in (
        "profiles",
        "judge-config",
        "input-validation",
        "gold",
        "rubrics",
        "question-ids",
        "split-map",
    ):
        prep.add_argument("--" + name, type=Path, required=True)
    post = commands.add_parser("report", help="after scoring only; never executed by prepare")
    prep.add_argument(
        "--expected-rubrics-sha256",
        required=True,
        help="digest from the approved M7 rubric manifest, fixed before scoring",
    )
    for name in (
        "readiness",
        "inputs",
        "adapter-manifest",
        "correctness-scores",
        "correctness-binding",
        "judge-evaluation-dir",
    ):
        post.add_argument("--" + name, type=Path, required=True)
    post.add_argument("--noise-floors", type=Path)
    for command in (prep, post):
        command.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output already exists")
    if args.command == "prepare":
        prepare(args)
    else:
        report(args)


if __name__ == "__main__":
    main()
