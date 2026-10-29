"""Offline Dev diagnostics and a human-review-only perturbation draft.

Consumes an unchanged scoring handoff and the frozen checklist. Constructs no API
client, performs no Test scoring and writes only a new supplemental output folder.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import sys
from collections import Counter, defaultdict
from pathlib import Path


def rows(path):
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def json_file(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def jsonl(path, values):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        for value in values:
            stream.write(json.dumps(value, ensure_ascii=True) + "\n")


def csv_file(path, values):
    if not values:
        return
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(values[0]))
        writer.writeheader()
        writer.writerows(values)


def build_curated_cases(source_data, criteria, rubrics, edit_package):
    """Reconstruct review-only edits from hash-bound, scored-correct Dev originals.

    Checks establish provenance, coverage and edit integrity. They do not establish
    a pedagogical violation, semantic isolation or human approval.
    """
    targets = {"B1", "B4", "A1", "I3", "correctness", "evidence_support"}
    generators = {"gpt-oss", "llama", "gemma"}
    specs = edit_package.get("cases", [])
    if edit_package.get("schema_version") != "m8-curated-perturbation-edits-2":
        raise ValueError("Unsupported curated edit package version")
    if (
        set(edit_package.get("targets", [])) != targets
        or set(edit_package.get("generators", [])) != generators
        or edit_package.get("expected_case_count") != 18
    ):
        raise ValueError("Declared target/generator coverage must match the review matrix")
    if len(specs) != 18:
        raise ValueError("The proposed matrix requires exactly 18 cases")
    pairs = [(s["target"], s["generator"]) for s in specs]
    if len(set(pairs)) != 18 or set(pairs) != {(t, g) for t in targets for g in generators}:
        raise ValueError("Require one case per target/generator pair")
    if len({s["source_question_id"] for s in specs}) != 18:
        raise ValueError("Require 18 distinct source questions")
    if len({s["case_id"] for s in specs}) != 18:
        raise ValueError("Case IDs must be unique")
    minimum_domains = max(9, edit_package.get("minimum_unique_domains", 9))
    if len({s["physics_domain"] for s in specs}) < minimum_domains:
        raise ValueError("The proposed sample requires at least nine physics domains")
    for target in targets:
        difficulties = {s["difficulty_proposal"] for s in specs if s["target"] == target}
        if difficulties != {"clear", "moderate", "subtle"}:
            raise ValueError("Each target needs a preassigned difficulty gradient")
    blocks = [s["edit"]["perturbed_span"].strip() for s in specs]
    nonempty = [s for s in blocks if s]
    if len(nonempty) != len(set(nonempty)):
        raise ValueError("Do not reuse an identical replacement block across questions")

    cases = []
    for spec in specs:
        target = spec["target"]
        batch = "dev-" + spec["generator"]
        data = source_data[batch]
        item = data["items"][spec["source_evaluation_id"]]
        for field, source_field in (
            ("source_question_id", "question_id"),
            ("source_target_level", "target_level"),
            ("source_condition", "condition"),
        ):
            if spec[field] != item[source_field]:
                raise ValueError(f"Source identity mismatch: {field}")
        answer = item["answer"]
        if not answer or item["technical_failure"] or item["abstained"]:
            raise ValueError("The base must be a substantive, successful answer")
        answer_hash = hashlib.sha256(answer.encode()).hexdigest()
        if spec["source_answer_sha256"] != answer_hash:
            raise ValueError("Source answer hash mismatch")
        score = data["correctness"][item["run_id"]]
        if score["score_status"] != "scored" or score["score"] != 2:
            raise ValueError("The base must have a fully correct saved score")
        if target in criteria:
            baseline = next(
                (
                    r
                    for r in data["adaptation"]
                    if r["evaluation_id"] == item["evaluation_id"]
                    and r["is_target_level_evaluation"]
                ),
                None,
            )
            if baseline is None or not any(
                c["criterion_id"] == target and c["verdict"] == "pass" for c in baseline["criteria"]
            ):
                raise ValueError("The target criterion must pass in the saved baseline")
            if criteria[target]["level"] != item["target_level"]:
                raise ValueError("Criterion does not belong to the source target level")
        elif target == "evidence_support":
            baseline = next(
                (r for r in data["evidence"] if r["evaluation_id"] == item["evaluation_id"]),
                None,
            )
            if (
                baseline is None
                or not baseline["claims"]
                or any(c["bundle_support"] != "supported" for c in baseline["claims"])
            ):
                raise ValueError("Evidence base claims must all be supported in saved output")
        else:
            baseline = score
        edit = spec["edit"]
        start, end = edit["start"], edit["end"]
        if (
            type(start) is not int
            or type(end) is not int
            or not 0 <= start <= end <= len(answer)
            or answer[start:end] != edit["original_span"]
        ):
            raise ValueError("Edit offsets/span do not match the original answer")
        perturbed = answer[:start] + edit["perturbed_span"] + answer[end:]
        if perturbed == answer:
            raise ValueError("An unchanged answer is not a perturbation")
        cases.append(
            {
                "case_id": spec["case_id"],
                "generator": spec["generator"],
                "target": target,
                "source_batch": batch,
                "base_evaluation_id": item["evaluation_id"],
                "base_run_id": item["run_id"],
                "question_id": item["question_id"],
                "target_level": item["target_level"],
                "condition": item["condition"],
                "question": item["question"],
                "original_answer": answer,
                "perturbed_answer": perturbed,
                "single_edit": edit,
                "original_answer_sha256": answer_hash,
                "perturbed_answer_sha256": hashlib.sha256(perturbed.encode()).hexdigest(),
                "frozen_criterion": criteria.get(target),
                "baseline_judgement": baseline,
                "correctness_reference_rubric": rubrics[item["question_id"]],
                "supplied_evidence": item["evidence"] if target == "evidence_support" else None,
                "physics_domain": spec["physics_domain"],
                "perturbation_type": spec["perturbation_type"],
                "selection_reason": spec["selection_reason"],
                "expected_response": (
                    "target criterion fail, not not_applicable"
                    if target in criteria
                    else "not fully correct under the existing rubric (score below 2)"
                    if target == "correctness"
                    else "the added factual subclaim has bundle_support unsupported"
                ),
                "proposed_non_target_invariants": spec["expected_non_target_invariants"],
                "review_focus": spec["review_focus"],
                "review_only_external_references": spec["review_only_external_references"],
                "difficulty_proposal": spec["difficulty_proposal"],
                "difficulty_rationale": spec["difficulty_rationale"],
                "difficulty_confirmed": False,
                "review_status": "pending_leader_confirmation",
                "target_violation_confirmed": False,
                "non_target_invariance_confirmed": False,
                "internal_consistency_confirmed": False,
                "criterion_isolation_verified": False,
                "single_edit_bytes_outside_span_unchanged": True,
                "reviewer": None,
                "reviewed_at": None,
                "paid_result": None,
            }
        )
    return cases


def write_curated_review(draft, cases, edit_package, edits_sha256):
    """Write a pending plan, before/after review sheet and mechanical coverage audit."""
    coverage = {
        "case_count": len(cases),
        "unique_question_count": len({c["question_id"] for c in cases}),
        "physics_domains": sorted({c["physics_domain"] for c in cases}),
        "by_generator": dict(Counter(c["generator"] for c in cases)),
        "by_target": dict(Counter(c["target"] for c in cases)),
        "by_condition": dict(Counter(c["condition"] for c in cases)),
        "by_difficulty_proposal": dict(Counter(c["difficulty_proposal"] for c in cases)),
        "human_reviews_completed": 0,
        "semantic_diversity_human_confirmed": False,
    }
    plan = {
        "plan_version": "perturbation-small-v2-draft",
        "status": "proposed_not_frozen_not_run",
        "source_profile_package_sha256": edit_package["source_profile_package_sha256"],
        "source_scoring_bundle_manifest_sha256": edit_package[
            "source_scoring_bundle_manifest_sha256"
        ],
        "curated_edits_sha256": edits_sha256,
        "selection_method": edit_package["selection_method"],
        "seed": None,
        "selection_is_random": False,
        "targets": edit_package["targets"],
        "coverage": coverage,
        "expected_case_count": 18,
        "detection_rate_proposal": 0.8,
        "per_target_minimum_detected_proposal": 1,
        "thresholds_frozen": False,
        "difficulty_design": edit_package["difficulty_design"],
        "difficulty_labels_frozen": False,
        "review_owner": "Leader",
        "scoring_owner": "M8",
        "step_4_status": "pending_leader_confirmation",
        "step_5_status": "not_run",
        "step_6_status": "not_run",
        "paid_calls": 0,
        "external_references_are_review_only": True,
        "detection_scoring_proposal": {
            "adaptation": "The selected criterion is fail; report other-criterion changes.",
            "correctness": "The existing correctness rubric yields score below 2.",
            "evidence_support": (
                "A factual claim covering the added subclaim is bundle_support unsupported. "
                "Omitting the subclaim or marking it supported/not_applicable is not detection."
            ),
            "unresolved": "Keep in the denominator as not detected and report separately.",
        },
        "interpretation": "Targeted sensitivity examples, not population judge accuracy.",
    }
    json_file(draft / "PLAN_DRAFT.json", plan)
    jsonl(draft / "cases.draft.jsonl", cases)
    json_file(
        draft / "selection_manifest.json",
        {
            "selection_method": edit_package["selection_method"],
            "seed": None,
            "case_ids": [c["case_id"] for c in cases],
            "question_ids": [c["question_id"] for c in cases],
            "draft_sha256": sha(draft / "cases.draft.jsonl"),
            "curated_edits_sha256": edits_sha256,
            "coverage": coverage,
            "frozen": False,
            "paid_calls": 0,
        },
    )
    review = [
        "# Perturbation v2: per-case review pending, not scored",
        "",
        "This replaces the rejected repeated-template v1 draft. Eighteen distinct Dev questions",
        "cover six targets and three generators. IDs are purposefully selected for coverage;",
        "the sample is not random or representative. All difficulty labels are pre-run proposals.",
        "Leader review must confirm the target violation, other-criterion effects and full-answer",
        "consistency. A mechanical single-span check does not prove semantic isolation.",
        "A saved baseline pass is a selection filter, not an independent physics endorsement.",
        "External references below are review-only; never add them to the judge evidence bundle.",
        "JSONL preserves the exact answer text; Markdown is a display of that record.",
        "",
        "| Case | Generator | Question | Target | Domain | Proposed difficulty |",
        "|---|---|---|---|---|---|",
    ]
    for case in cases:
        review.append(
            f"| {case['case_id']} | {case['generator']} | {case['question_id']} | "
            f"{case['target']} | {case['physics_domain']} | {case['difficulty_proposal']} |"
        )
    for case in cases:
        edit = case["single_edit"]
        review += [
            "",
            "## " + case["case_id"],
            "",
            "Question: " + case["question"],
            "",
            f"Source: {case['base_evaluation_id']}; {case['target_level']}; {case['condition']}.",
            "",
            "Frozen criterion: "
            + (
                case["frozen_criterion"]["description"]
                if case["frozen_criterion"]
                else "Existing correctness rubric / supplied-evidence support definition."
            ),
            "",
            "Original answer:",
            "",
            "> " + case["original_answer"].replace("\n", "\n> "),
            "",
            "Perturbed candidate:",
            "",
            "> " + case["perturbed_answer"].replace("\n", "\n> "),
            "",
            "Controlled edit (one semantic target; repeated mentions may share one span):",
            "",
            "```text",
            "BEFORE: " + json.dumps(edit["original_span"], ensure_ascii=False),
            "AFTER: " + json.dumps(edit["perturbed_span"], ensure_ascii=False),
            "```",
            "",
            "Selection reason: " + case["selection_reason"],
            "",
            "Expected response (hypothesis): " + case["expected_response"],
            "",
            "Proposed difficulty: " + case["difficulty_proposal"],
            "",
            "Difficulty reason: " + case["difficulty_rationale"],
            "",
            "Proposed invariants (not human-confirmed):",
            "",
            *["- " + value for value in case["proposed_non_target_invariants"]],
            "",
            "Review focus: " + case["review_focus"],
        ]
        if case["supplied_evidence"]:
            review += ["", "Evidence actually supplied to generation:", ""]
            for evidence in case["supplied_evidence"]:
                review += [
                    "- ID: " + evidence["evidence_id"],
                    "",
                    "> " + evidence["text"].replace("\n", "\n> "),
                    "",
                ]
        if case["review_only_external_references"]:
            review += ["", "External physics references (review-only, not judge evidence):", ""]
            for reference in case["review_only_external_references"]:
                review.append(f"- [{reference['purpose']}]({reference['url']})")
        review += [
            "",
            "Leader checks:",
            "",
            "- Intended target violation: **pending**.",
            "- Other-criterion effects / physics preservation: **pending**.",
            "- Full-answer internal consistency: **pending**.",
            "- Difficulty label confirmation: **pending**.",
            "- Accept / revise / reject and reason: **pending**.",
            "- Reviewer, date and frozen sample hash: **pending**.",
            "",
        ]
    markdown = "\n".join(line.rstrip(" \t\r") for line in "\n".join(review).split("\n"))
    (draft / "REVIEW_PENDING.md").write_text(markdown.rstrip("\n") + "\n", encoding="utf-8")
    return plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", required=True, type=Path)
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument(
        "--seed",
        type=int,
        default=5703,
        help="Legacy compatibility only; v2 uses explicit curated case IDs, not random sampling",
    )
    parser.add_argument("--perturbation-edits", type=Path)
    args = parser.parse_args()
    package, repo, out = args.package.resolve(), args.repo.resolve(), args.out.resolve()
    if out.exists():
        raise ValueError("Use a new supplemental directory; existing outputs are preserved")
    source_hashes = {
        p.relative_to(package).as_posix(): sha(p) for p in package.rglob("*") if p.is_file()
    }
    sys.path.insert(0, str(repo / "src"))
    from cs30.evaluation.judge_validity import _pearson
    from cs30.evaluation.level_profiles import load_profile_checklist_package
    from cs30.evaluation.v2_generation_reporting import answer_text_diagnostics

    frozen = load_profile_checklist_package(package / "profile_checklist.frozen.json")
    criteria = {
        c.criterion_id: c.model_dump(mode="json")
        for checklist in frozen.checklists
        for c in checklist.criteria
    }
    rubrics = {
        r["question_id"]: r
        for r in rows(repo / "eval_inputs/m8/correctness-dev-rubrics-v0.1/rubrics.draft.jsonl")
    }
    manifest = json.loads((package / "handoff_manifest.json").read_text(encoding="utf-8"))
    edits_path = args.perturbation_edits or (
        repo
        / "docs/results/m8_dev_validity_diagnostics_20261029"
        / "perturbation-draft/curated_edits.v2.json"
    )
    edit_package = json.loads(edits_path.read_text(encoding="utf-8"))
    if edit_package["source_profile_package_sha256"] != frozen.package_sha256:
        raise ValueError("Curated edits bind a different frozen profile")
    if edit_package["source_scoring_bundle_manifest_sha256"] != sha(package / "SHA256SUMS.json"):
        raise ValueError("Curated edits bind a different source scoring package")
    out.mkdir(parents=True)
    offline = out / "diagnostics"
    offline.mkdir()
    draft = out / "perturbation-draft"
    draft.mkdir()
    p0_inputs, surface, criterion_surface, na_observations, noise = [], [], [], [], {}
    source_data = {}
    for bundle in manifest["batches"]:
        batch = bundle["batch"]
        cohort, model = batch.split("-", 1)
        dest = package / Path(bundle["judge_evaluation_dir"])
        items = {r["evaluation_id"]: r for r in rows(package / Path(bundle["inputs"]))}
        adaptation = rows(dest / "adaptation_results.jsonl")
        discrimination = rows(dest / "discrimination_results.jsonl")
        evidence = rows(dest / "evidence_support_results.jsonl")
        correctness = {r["run_id"]: r for r in rows(package / Path(bundle["correctness_scores"]))}
        unresolved = rows(dest / "judge_unresolved.jsonl")
        source_data[batch] = {
            "items": items,
            "adaptation": adaptation,
            "discrimination": discrimination,
            "evidence": evidence,
            "correctness": correctness,
            "unresolved": unresolved,
        }
        if cohort != "dev":
            continue
        prediction = {r["evaluation_id"]: r["predicted_level"] for r in discrimination}
        for item in items.values():
            if (
                item["condition"] != "P0R0_plain"
                or item["answer"] is None
                or item["technical_failure"]
                or item["abstained"]
            ):
                continue
            p0_inputs.append(
                {
                    "generator": model,
                    "evaluation_id": item["evaluation_id"],
                    "question_id": item["question_id"],
                    "target_level": item["target_level"],
                    "predicted_level": prediction.get(item["evaluation_id"]),
                    "answer_sha256": item["answer_sha256"],
                }
            )
        unique_adapt = {}
        for a in adaptation:
            item = items[a["evaluation_id"]]
            unique_adapt.setdefault(a["request_id"], a)
            if not a["is_target_level_evaluation"] or a["criterion_pass_rate"] is None:
                continue
            text = answer_text_diagnostics(item["answer"])
            feature = {
                "generator": model,
                "evaluation_id": item["evaluation_id"],
                "question_id": item["question_id"],
                "target_level": item["target_level"],
                "condition": item["condition"],
                "word_count": text["word_count"],
                "formula_present": text["formula_present"],
                "criterion_pass_rate": a["criterion_pass_rate"],
            }
            surface.append(feature)
            for judgement in a["criteria"]:
                criterion_surface.append(
                    {
                        **feature,
                        "criterion_id": judgement["criterion_id"],
                        "verdict": judgement["verdict"],
                    }
                )
        for a in unique_adapt.values():
            for c in a["criteria"]:
                na_observations.append(
                    {
                        "generator": model,
                        "evaluated_level": a["evaluated_level"],
                        "criterion_id": c["criterion_id"],
                        "request_id": a["request_id"],
                        "verdict": c["verdict"],
                    }
                )
        report = json.loads(
            (package / "development_reports" / batch / "v2_generation_evaluation.json").read_text(
                encoding="utf-8"
            )
        )
        paired = report["diagnostics"]["generation_noise_floor"]["paired_repeat_batch"]
        # Independently check the saved report against the paired source-bound cell table.
        table = rows(package / "scores_by_cell.jsonl")
        base = {r["run_id"]: r for r in table if r["batch"] == batch}
        repeated = [r for r in table if r["batch"] == "repeat-" + model]
        assert len(repeated) == 360
        flips, missing = 0, 0
        for r in repeated:
            original = base[r["run_id"]]
            assert all(original[k] == r[k] for k in ["question_id", "target_level", "condition"])
            if original["correctness_score"] is None or r["correctness_score"] is None:
                missing += 1
            else:
                flips += (original["correctness_score"] == 2) != (r["correctness_score"] == 2)
        assert flips == paired["overall"]["correct_flip_count"]
        assert missing == paired["overall"]["correctness_pairs"]["not_evaluated"]
        noise[model] = {
            "native_report": paired,
            "independent_flip_check": {
                "pairs": 360,
                "known_flips": flips,
                "missing_pairs": missing,
                "flip_rate_bounds": [flips / 360, (flips + missing) / 360],
            },
            "source_report_sha256": sha(
                package / "development_reports" / batch / "v2_generation_evaluation.json"
            ),
        }
    json_file(offline / "generation_noise.json", noise)
    noise_table = []
    for model, n in noise.items():
        p = n["native_report"]
        o = p["overall"]
        floor = p["strict_correct_noise_floor"]
        noise_table.append(
            {
                "generator": model,
                "repeat_questions": 30,
                "paired_cells": 360,
                "complete_correctness_pairs": o["correctness_pairs"]["evaluated"],
                "missing_correctness_pairs": o["correctness_pairs"]["not_evaluated"],
                "known_strict_correct_flips": o["correct_flip_count"],
                "flip_rate_lower": o["correct_flip_rate_bounds"][0],
                "flip_rate_upper": o["correct_flip_rate_bounds"][1],
                "correctness_mean_absolute_difference_observed": o["correctness_score_difference"][
                    "mean_absolute_difference"
                ],
                "adaptation_evaluated_pairs": o["adaptation_pairs"]["evaluated"],
                "adaptation_mean_absolute_rate_difference_observed": o[
                    "adaptation_score_difference"
                ]["mean_absolute_difference"],
                "strict_correct_noise_floor_lower": floor["bounds"][0],
                "strict_correct_noise_floor_upper": floor["bounds"][1],
                "registered_primary_contrast": floor["main_comparison"]["contrast"],
                "delta_frozen": p["correctness_noninferiority_delta"] is not None,
            }
        )
    csv_file(offline / "generation_noise_summary.csv", noise_table)
    p0_summary = []
    for model in ("gpt-oss", "llama", "gemma"):
        group = [r for r in p0_inputs if r["generator"] == model]
        available = [r for r in group if r["predicted_level"] is not None]
        targets = Counter(r["target_level"] for r in group)
        observed_targets = Counter(r["target_level"] for r in available)
        predictions = Counter(r["predicted_level"] for r in available)
        correct = sum(r["target_level"] == r["predicted_level"] for r in available)
        n = len(group)
        missing = n - len(available)
        p0_summary.append(
            {
                "generator": model,
                "expected_answered_control_cells": n,
                "available_predictions": len(available),
                "missing_predictions": missing,
                "target_counts": dict(targets),
                "observed_target_counts": dict(observed_targets),
                "target_balance_complete": len(targets) == 3 and len(set(targets.values())) == 1,
                "observed_target_balance_complete": len(observed_targets) == 3
                and len(set(observed_targets.values())) == 1,
                "prediction_counts": dict(predictions),
                "unique_control_answers": len(
                    {(r["question_id"], r["answer_sha256"]) for r in group}
                ),
                "observed_accuracy": correct / len(available) if available else None,
                "chance_reference": 1 / 3,
                "observed_abs_deviation_from_one_third": abs(correct / len(available) - 1 / 3)
                if available
                else None,
                "accuracy_bounds_including_missing": [
                    correct / n,
                    (correct + missing) / n,
                ],
                "threshold": None,
                "passed": None,
                "status": "computed_descriptive_threshold_pending",
            }
        )
    json_file(offline / "p0r0_level_bias.json", p0_summary)
    jsonl(offline / "p0r0_observations.jsonl", p0_inputs)

    def associations(group, value_name):
        lengths = [float(r["word_count"]) for r in group]
        values = [float(r[value_name]) for r in group]
        with_formula = [float(r[value_name]) for r in group if r["formula_present"]]
        without = [float(r[value_name]) for r in group if not r["formula_present"]]
        left = sum(with_formula) / len(with_formula) if with_formula else None
        right = sum(without) / len(without) if without else None
        return {
            "sample_size": len(group),
            "length_association": _pearson(lengths, values),
            "formula_rows": len(with_formula),
            "no_formula_rows": len(without),
            "mean_with_formula": left,
            "mean_without_formula": right,
            "signed_formula_gap": left - right if left is not None and right is not None else None,
        }

    pooled = []
    by_condition = []
    for model in ("gpt-oss", "llama", "gemma"):
        for level in ("beginner", "intermediate", "advanced"):
            group = [r for r in surface if r["generator"] == model and r["target_level"] == level]
            pooled.append(
                {
                    "generator": model,
                    "target_level": level,
                    "outcome": "continuous_criterion_pass_rate",
                    **associations(group, "criterion_pass_rate"),
                }
            )
            for condition in sorted({r["condition"] for r in surface}):
                local = [r for r in group if r["condition"] == condition]
                by_condition.append(
                    {
                        "generator": model,
                        "target_level": level,
                        "condition": condition,
                        "outcome": "continuous_criterion_pass_rate",
                        **associations(local, "criterion_pass_rate"),
                    }
                )
    criterion_groups = defaultdict(list)
    for r in criterion_surface:
        if r["verdict"] != "not_applicable":
            criterion_groups[(r["generator"], r["target_level"], r["criterion_id"])].append(
                r | {"passed": int(r["verdict"] == "pass")}
            )
    criterion_assoc = [
        {
            "generator": k[0],
            "target_level": k[1],
            "criterion_id": k[2],
            "outcome": "criterion_pass_binary",
            **associations(g, "passed"),
        }
        for k, g in sorted(criterion_groups.items())
    ]
    csv_file(offline / "surface_bias_continuous_by_level.csv", pooled)
    csv_file(offline / "surface_bias_continuous_by_level_condition.csv", by_condition)
    csv_file(offline / "surface_bias_by_criterion.csv", criterion_assoc)
    json_file(
        offline / "surface_bias.json",
        {
            "status": "descriptive_computed_aggregate_pass_threshold_not_frozen",
            "aggregate_adaptation_pass_threshold": None,
            "validity_thresholds": None,
            "passed": None,
            ("notes"): (
                "Within target level only. Continuous criterion pass rates and "
                "individual binary verdicts avoid inventing an aggregate pass "
                "cutoff. Association is not proof of bias: question difficulty "
                "and legitimate physics needs can confound length/formulas."
            ),
            "by_level": pooled,
            "by_level_condition": by_condition,
            "by_criterion": criterion_assoc,
        },
    )
    jsonl(offline / "surface_observations.jsonl", surface)
    na_group = defaultdict(Counter)
    for r in na_observations:
        na_group[(r["generator"], r["evaluated_level"], r["criterion_id"])][r["verdict"]] += 1
    na = []
    for key, count in sorted(na_group.items()):
        na.append(
            {
                "generator": key[0],
                "evaluated_level": key[1],
                "criterion_id": key[2],
                "denominator_resolved_unique_requests": sum(count.values()),
                "pass_count": count["pass"],
                "fail_count": count["fail"],
                "not_applicable_count": count["not_applicable"],
                "not_applicable_rate": count["not_applicable"] / sum(count.values()),
                "optional_criterion": key[2] in ("B3", "A2", "A3"),
                "warning_threshold_x": None,
                "warning": None,
            }
        )
    assert not any(r["not_applicable_count"] for r in na if not r["optional_criterion"])
    csv_file(offline / "not_applicable_by_criterion.csv", na)
    json_file(
        offline / "not_applicable.json",
        {
            ("scope"): (
                "Dev; one observation per resolved unique adaptation request "
                "per criterion; unresolved requests are reported separately, "
                "not silently included as not_applicable"
            ),
            "threshold_x": None,
            "threshold_source": "User confirmed not decided; report counts/rates only",
            "required_criteria_na_count": 0,
            "rows": na,
        },
    )
    for filename in (
        "missingness_by_task_model_level_condition.csv",
        "missingness_by_task_model_level_condition.json",
        "adaptation_missingness_by_checklist_level.csv",
    ):
        shutil.copy2(package / filename, offline / filename)

    cases = build_curated_cases(source_data, criteria, rubrics, edit_package)
    write_curated_review(draft, cases, edit_package, sha(edits_path))
    shutil.copy2(edits_path, draft / "curated_edits.v2.json")
    json_file(
        draft / "COST_ESTIMATE_NOT_APPROVAL.json",
        {
            "plan_version": "perturbation-small-v2-draft",
            "candidate_cases": len(cases),
            "estimate_status": "pending_v2_request_preparation",
            "approved_budget": None,
            "paid_calls": 0,
            "warning": (
                "Re-estimate from the approved v2 inputs/configuration before execution. "
                "The earlier v1 average was neither a cap nor paid-launch approval."
            ),
        },
    )
    summary = {
        "api_calls": 0,
        "scope": "Dev-only supplemental diagnostics; main scores and original assets unchanged",
        "completed_computations": [
            "P0R0 descriptive level bias",
            "Within-level length/formula associations",
            "Paired generation noise extraction plus independent flips check",
            "Task/model/level/condition missingness",
            "Optional-criterion not_applicable rates",
        ],
        "frozen_pass_decisions": False,
        "pending": [
            "Leader thresholds / Test-freeze decision",
            "18 perturbation semantic-isolation reviews",
            "Leader confirmation and dataset freeze",
            "Any authorised paid scoring of perturbed answers",
        ],
        "source_manifest_sha256": sha(package / "SHA256SUMS.json"),
        "seed": None,
        "selection_method": edit_package["selection_method"],
        "threshold_x": None,
    }
    json_file(out / "summary.json", summary)
    json_file(out / "SOURCE_HASHES.json", source_hashes)
    for relative, digest in source_hashes.items():
        assert sha(package / relative) == digest, relative
    print(
        json.dumps(
            {
                "output": str(out),
                "api_calls": 0,
                "p0r0": p0_summary,
                "noise": noise_table,
                "optional_na": [r for r in na if r["optional_criterion"]],
                "perturbation_drafts": 18,
            },
            ensure_ascii=False,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
