"""Offline Dev diagnostics and a human-review-only perturbation draft.

Consumes an unchanged scoring handoff and the frozen checklist. Constructs no API
client, performs no Test scoring and writes only a new supplemental output folder.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", required=True, type=Path)
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--seed", type=int, default=5703)
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

    # Proposed rules precede sample generation; no perturbed verdict has been requested.
    selected_targets = ["B1", "B4", "A1", "I3", "correctness", "evidence_support"]
    plan = {
        "plan_version": "perturbation-small-v1-draft",
        "status": "proposed_not_frozen_not_run",
        "seed": args.seed,
        "source_profile_package_sha256": frozen.package_sha256,
        "source_scoring_bundle_manifest_sha256": sha(package / "SHA256SUMS.json"),
        "targets": selected_targets,
        "cases_per_target": 3,
        "generators_per_target": ["gpt-oss", "llama", "gemma"],
        "expected_case_count": 18,
        "detection_rate_proposal": 0.8,
        "per_target_minimum_detected_proposal": 1,
        "thresholds_frozen": False,
        ("answer_change_review_required"): (
            "Leader reviews and confirms semantic isolation before any judge call"
        ),
        "paid_calls": 0,
        "review_owner": "Leader",
        "scoring_owner": "M8",
        "post_scoring_report_owner": "M8",
        "step_4_status": "pending_leader_confirmation",
        "step_5_status": "not_run",
        "step_6_status": "not_run",
        "reviewer_student_substitution_allowed": False,
        ("prompt_and_thinking"): (
            "Use unchanged production prompt/model/temperature/thinking "
            "low; fresh requests/execution/cache/ledger; never add to main "
            "scores"
        ),
        ("preregistration_destination"): (
            "Record the approved plan in a versioned pre-Test decision "
            "before inspecting perturbation or relevant Test outcomes"
        ),
        ("interpretation"): (
            "Small sensitivity audit for these selected clauses, not judge "
            "accuracy, calibration or full validity approval"
        ),
        ("frozen_rule_correction"): (
            "A1 checks unnecessary introductory teaching; A4 checks rigor. "
            "Recognition-only questions must not fail solely for lacking "
            "derivation. B4 does not require a formula."
        ),
        ("selection"): (
            "Targeted eligible Dev originals with correct score2 and target"
            " verdict pass. Stable seeded SHA256 ranking within "
            "generator/target; no perturbed scoring outcomes used. This is "
            "not a representative population sample."
        ),
    }
    json_file(draft / "PLAN_DRAFT.json", plan)
    cases = []
    used = set()
    pool_sizes = {}

    def first_sentence(answer):
        m = re.search(r"(?<!\d)[.!?](?!\d)", answer)
        return answer[: m.end()] if m else None

    for target in selected_targets:
        for model in ["gpt-oss", "llama", "gemma"]:
            data = source_data["dev-" + model]
            candidates = []
            if target in ("B1", "B4", "A1", "I3"):
                for record in data["adaptation"]:
                    if not record["is_target_level_evaluation"]:
                        continue
                    item = data["items"][record["evaluation_id"]]
                    answer = item["answer"]
                    score = data["correctness"][item["run_id"]]
                    if score["score_status"] != "scored" or score["score"] != 2:
                        continue
                    verdicts = {x["criterion_id"]: x["verdict"] for x in record["criteria"]}
                    if verdicts.get(target) != "pass":
                        continue
                    span = None
                    if target in ("B1", "B4"):
                        m = re.search(r"\bspeed\b", answer, re.IGNORECASE)
                        if not m or "velocity" in item["question"].lower():
                            continue
                        if not re.search(
                            r"speed|velocity|displacement|wave|sound|motion|momentum|distance",
                            item["question"],
                            re.IGNORECASE,
                        ):
                            continue
                        replacement = (
                            "norm of the velocity vector" if target == "B1" else r"\(\|\vec{v}\|\)"
                        )
                        span = (m.start(), m.end(), replacement)
                    else:
                        # A1 and I3 explicitly prohibit needless re-teaching of the
                        # assumed core. An appended true elementary tutorial leaves
                        # the original physical answer intact; deleting a requested
                        # derivation would risk changing correctness completeness.
                        tutorial = (
                            " Here are elementary reminders for the reader. An integer is a"
                            " whole number. "
                            "Adding zero to a number leaves it unchanged. Multiplying a "
                            "number by one leaves it unchanged. "
                            "For positive integers, multiplication is repeated addition. "
                            "Two plus two equals four. "
                            "Four divided by two equals two. A metre is one hundred "
                            "centimetres. A second is a unit of time."
                        )
                        span = (len(answer), len(answer), tutorial)
                    candidates.append((item, record, span))
            elif target == "correctness":
                for item in data["items"].values():
                    score = data["correctness"][item["run_id"]]
                    if (
                        score["score_status"] != "scored"
                        or score["score"] != 2
                        or not item["answer"]
                    ):
                        continue
                    # Change a required scientific answer, not an incidental figure
                    # number or an approximate numeric range that may remain true.
                    if "displacement divided by time" not in item["question"].lower():
                        continue
                    match = re.search(r"\bvelocity\b", item["answer"], re.IGNORECASE)
                    if match:
                        candidates.append(
                            (item, score, (match.start(), match.end(), "acceleration"))
                        )
            else:
                for record in data["evidence"]:
                    item = data["items"][record["evaluation_id"]]
                    score = data["correctness"][item["run_id"]]
                    if (
                        score["score_status"] != "scored"
                        or score["score"] != 2
                        or not record["claims"]
                    ):
                        continue
                    if any(c["bundle_support"] != "supported" for c in record["claims"]):
                        continue
                    if any(
                        re.search(r"\bgold\b|\b79\b", e["text"], re.IGNORECASE)
                        for e in item["evidence"]
                    ):
                        continue
                    candidates.append(
                        (
                            item,
                            record,
                            (
                                len(item["answer"]),
                                len(item["answer"]),
                                " Gold has atomic number 79.",
                            ),
                        )
                    )
            candidates = [x for x in candidates if (model, x[0]["evaluation_id"]) not in used]
            pool_sizes[target + "/" + model] = len(candidates)
            candidates.sort(
                key=lambda x: hashlib.sha256(
                    f"{args.seed}|{model}|{target}|{x[0]['evaluation_id']}".encode()
                ).hexdigest()
            )
            if not candidates:
                raise ValueError("No eligible case for " + target + "/" + model)
            item, base, span = candidates[0]
            start, end, replacement = span
            answer = item["answer"]
            perturbed = answer[:start] + replacement + answer[end:]
            assert (
                perturbed != answer
                and perturbed[:start] == answer[:start]
                and perturbed[start + len(replacement) :] == answer[end:]
            )
            used.add((model, item["evaluation_id"]))
            warning = (
                "Leader must verify this single contiguous edit violates the "
                "target clause, preserves all other relevant criteria and "
                "leaves physical correctness unchanged unless correctness is "
                "the target."
            )
            if target in ("I3", "A1"):
                warning += (
                    " Confirm the added elementary tutorial is genuinely redundant "
                    "and obscures the requested answer for this prior; brief useful"
                    " reminders would not violate the rule. This alternative "
                    "targets redundancy, not A4/I2 reasoning depth."
                )
            if target == "correctness":
                warning += (
                    " Confirm replacing velocity with acceleration changes the "
                    "required scientific answer, not an incidental example."
                )
            if target == "evidence_support":
                warning += (
                    " Confirm the added true scientific statement is absent from "
                    "every supplied evidence passage; this is a supportedness "
                    "perturbation, not a known false fact."
                )
            cases.append(
                {
                    "case_id": f"perturb-v1-{target.lower().replace('_', '-')}-{model}",
                    "generator": model,
                    "target": target,
                    "source_batch": "dev-" + model,
                    "base_evaluation_id": item["evaluation_id"],
                    "base_run_id": item["run_id"],
                    "question_id": item["question_id"],
                    "target_level": item["target_level"],
                    "condition": item["condition"],
                    "question": item["question"],
                    "original_answer": answer,
                    "perturbed_answer": perturbed,
                    "single_edit": {
                        "start": start,
                        "end": end,
                        "original_span": answer[start:end],
                        "perturbed_span": replacement,
                    },
                    "original_answer_sha256": hashlib.sha256(answer.encode()).hexdigest(),
                    "perturbed_answer_sha256": hashlib.sha256(perturbed.encode()).hexdigest(),
                    "frozen_criterion": criteria.get(target),
                    "baseline_judgement": base,
                    "correctness_reference_rubric": rubrics[item["question_id"]],
                    "supplied_evidence": item["evidence"] if target == "evidence_support" else None,
                    "expected_response": "fail (not not_applicable)"
                    if target in criteria
                    else "detect factual error"
                    if target == "correctness"
                    else "mark added claim unsupported",
                    "review_status": "pending_leader_confirmation",
                    "review_warning": warning,
                    "single_edit_bytes_outside_span_unchanged": True,
                    "criterion_isolation_verified": False,
                    "reviewer": None,
                    "reviewed_at": None,
                    "paid_result": None,
                }
            )
    assert len(cases) == 18 and Counter(c["target"] for c in cases) == {
        t: 3 for t in selected_targets
    }
    jsonl(draft / "cases.draft.jsonl", cases)
    json_file(
        draft / "selection_manifest.json",
        {
            "seed": args.seed,
            "pool_sizes": pool_sizes,
            "case_ids": [c["case_id"] for c in cases],
            "draft_sha256": sha(draft / "cases.draft.jsonl"),
            "frozen": False,
            "paid_calls": 0,
        },
    )
    review = [
        "# Perturbation cases: review pending, not scored",
        "",
        (
            "These 18 drafts are single contiguous edits of Dev answers "
            "already scored correct with the target criterion passed. All "
            "three generators are represented in each target group. No "
            "perturbed Gemini score exists. Check semantic isolation before"
            " freezing the plan or running any paid command."
        ),
        "",
        (
            "Draft targets: B1, B4, A1, I3, correctness, evidence support. "
            "A1/I3 test needless re-teaching of the assumed core; they are "
            "a proposed alternative to derivation deletion, which can also "
            "damage correctness completeness. They do NOT test A4/I2. A1 is"
            " not relabelled as a depth criterion. The Leader must approve "
            "this target choice or request replacements before freezing or "
            "paid scoring. The 80% aggregate detection and at least one "
            "detected case per target are proposed thresholds, not yet "
            "approved decisions."
        ),
        "",
    ]
    for c in cases:
        review += [
            "## " + c["case_id"],
            "",
            (
                f"Target: {c['target']}; level: {c['target_level']}; "
                f"condition: {c['condition']}; source: {c['base_evaluation_id']}."
            ),
            "",
            "Question: " + c["question"],
            "",
            "Frozen rule: "
            + (
                c["frozen_criterion"]["description"]
                if c["frozen_criterion"]
                else (
                    "Correctness rubric / evidence supportedness, unchanged production definitions."
                )
            ),
            "",
            "Original answer:",
            "",
            "> " + c["original_answer"].replace("\n", "\n> "),
            "",
            "Perturbed draft:",
            "",
            "> " + c["perturbed_answer"].replace("\n", "\n> "),
            "",
            "Expected (hypothesis): " + c["expected_response"],
            "",
            c["review_warning"],
            "",
            "Leader decision and reason: **pending**.",
            "",
        ]
    (draft / "REVIEW_PENDING.md").write_text("\n".join(review), encoding="utf-8")
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
        "seed": args.seed,
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
