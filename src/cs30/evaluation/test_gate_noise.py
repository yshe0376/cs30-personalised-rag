"""Freeze the Leader-approved adaptation noise floors from Dev repeat scores only."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from statistics import mean

from cs30.contracts import StudentLevel

from .level_profiles import eligible_levels, load_profile_checklist_package
from .models import PersonalisationEligibility
from .test_gate_analysis import CONTROL, POLICY_VERSION, PROFILE_SHA, TREATMENT, main_adaptation
from .test_gate_readiness import (
    FROZEN_ELIGIBILITY_FILE_SHA,
    FROZEN_JUDGE_FILE_SHA,
    FROZEN_SPLIT_SHA,
    file_sha,
    objects,
    write_json,
)
from .v2_generation_models import GenerationEvaluationInput

REVIEW = "https://github.com/yshe0376/cs30-personalised-rag/pull/225#issuecomment-6494640705"


def adaptation_repeat_floors(baseline, repeated, baseline_scores, repeat_scores, test_counts):
    """Pool squared per-answer changes over the two arms, then scale by Test n."""

    def index(items, rows):
        by_id = {i.evaluation_id: i for i in items}
        cells = {(i.question_id, i.target_level, i.condition): i for i in items}
        if len(by_id) != len(items) or len(cells) != len(items):
            raise ValueError("duplicate Dev answer identity or cell")
        if any(
            i.source_split != "dev"
            or i.generation_model_family.casefold().rsplit("/", 1)[-1]
            not in {"gpt-oss", "gpt-oss-20b", "gpt-oss:20b"}
            for i in items
        ):
            raise ValueError("noise input must be GPT-OSS Dev only")
        scores = {}
        for row in rows:
            if not row.get("is_target_level_evaluation"):
                continue
            item = by_id.get(row["evaluation_id"])
            if item is None or item.evaluation_id in scores:
                raise ValueError("duplicate or unbound Dev adaptation row")
            if (
                row["question_id"],
                row["target_level"],
                row["evaluated_level"],
                row["condition"],
            ) != (
                item.question_id,
                item.target_level.value,
                item.target_level.value,
                item.condition.value,
            ):
                raise ValueError("Dev adaptation identity mismatch")
            scores[item.evaluation_id] = main_adaptation(row)["main_criterion_pass_rate"]
        return cells, scores

    base, base_scores = index(baseline, baseline_scores)
    repeat, repeat_scores = index(repeated, repeat_scores)
    if not set(repeat) <= set(base):
        raise ValueError("repeat cells must belong to the Dev baseline")
    details, floors = {}, {}
    for level in (StudentLevel.BEGINNER, StudentLevel.ADVANCED):
        differences, missing, nonanswer, expected = [], 0, 0, 0
        counts = {arm.value: 0 for arm in (CONTROL, TREATMENT)}
        for key, right in repeat.items():
            qid, target_level, arm = key
            if target_level != level or arm not in (CONTROL, TREATMENT):
                continue
            left = base[key]
            if (left.run_id, left.eligibility, left.generation_model_revision) != (
                right.run_id,
                right.eligibility,
                right.generation_model_revision,
            ):
                raise ValueError("Dev repeat pairing metadata differs")
            if level not in eligible_levels(left.eligibility):
                continue
            expected += 1
            if any(i.technical_failure or i.abstained for i in (left, right)):
                nonanswer += 1
                continue
            lval, rval = base_scores.get(left.evaluation_id), repeat_scores.get(right.evaluation_id)
            if lval is None or rval is None:
                missing += 1
                continue
            differences.append((rval - lval) ** 2)
            counts[arm.value] += 1
        n = test_counts[level.value]
        if type(n) is not int or n <= 0 or any(count == 0 for count in counts.values()):
            raise ValueError("positive Test n and resolved Dev pairs in both arms are required")
        mse = mean(differences)
        floors[level.value] = math.sqrt(mse / n)
        details[level.value] = {
            "test_eligible_question_pairs": n,
            "expected_repeat_cells": expected,
            "resolved_repeat_cells": len(differences),
            "resolved_by_condition": counts,
            "unscored_repeat_cells": missing,
            "non_answer_repeat_cells": nonanswer,
            "mean_squared_repeat_difference": mse,
        }
    return {"adaptation_noise_floors": floors, "details": details}


def freeze(args):
    """Use hash-verified Dev files plus frozen Test IDs/labels, never Test answers."""
    package = args.dev_package.resolve()
    inventory = json.loads((package / "SHA256SUMS.json").read_text(encoding="utf-8"))
    consumed = {}

    def verified(relative):
        path = (package / relative).resolve()
        if not path.is_relative_to(package) or inventory.get(relative) != file_sha(path):
            raise ValueError(f"Dev package hash/path mismatch: {relative}")
        consumed[relative] = file_sha(path)
        return path

    manifest_path = verified("handoff_manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("kind") != "development_scoring_with_explicit_missingness":
        raise ValueError("requires the immutable Dev scoring handoff")
    profile = load_profile_checklist_package(verified("profile_checklist.frozen.json"))
    if profile.package_sha256 != PROFILE_SHA or file_sha(verified("judge-config.low.json")) != (
        FROZEN_JUDGE_FILE_SHA
    ):
        raise ValueError("Dev profile/config differs from the frozen judge")
    batches = {b["batch"]: b for b in manifest["batches"]}
    loaded = []
    for name in ("dev-gpt-oss", "repeat-gpt-oss"):
        batch = batches[name]
        inputs_path = verified(batch["inputs"])
        items = [GenerationEvaluationInput.model_validate(r) for r in objects(inputs_path)]
        if any(i.source_run_sha256 != batch["source_run_sha256"] for i in items):
            raise ValueError("Dev source-run hash mismatch")
        judge_manifest_path = verified(
            batch["judge_evaluation_dir"] + "/judge_evaluation_manifest.json"
        )
        judge_manifest = json.loads(judge_manifest_path.read_text(encoding="utf-8"))
        provenance = judge_manifest["provenance"]
        if (
            provenance.get("evaluation_inputs_sha256") != file_sha(inputs_path)
            or provenance.get("profile_package_sha256") != PROFILE_SHA
            or provenance.get("judge_configuration_sha256") != FROZEN_JUDGE_FILE_SHA
        ):
            raise ValueError("Dev judge provenance mismatch")
        adaptation = verified(batch["judge_evaluation_dir"] + "/adaptation_results.jsonl")
        if file_sha(adaptation) != judge_manifest["output_sha256"]["adaptation"]:
            raise ValueError("Dev adaptation manifest mismatch")
        loaded.append((items, objects(adaptation)))
    if file_sha(args.split_map) != FROZEN_SPLIT_SHA:
        raise ValueError("Test split map differs from frozen IDs")
    split = json.loads(args.split_map.read_text(encoding="utf-8"))
    ids = {q for q, label in split.items() if label == "test"}
    if file_sha(args.eligibility) != FROZEN_ELIGIBILITY_FILE_SHA:
        raise ValueError("Test eligibility differs from the approved label bytes")
    labels = {r["question_id"]: r["eligibility"] for r in objects(args.eligibility)}
    if len(ids) != 187 or not ids <= labels.keys():
        raise ValueError("Test ID coverage mismatch")
    counts = {
        level.value: sum(
            level in eligible_levels(PersonalisationEligibility(labels[q])) for q in ids
        )
        for level in (StudentLevel.BEGINNER, StudentLevel.ADVANCED)
    }
    result = adaptation_repeat_floors(
        loaded[0][0], loaded[1][0], loaded[0][1], loaded[1][1], counts
    )
    result.update(
        {
            "policy": POLICY_VERSION,
            "profile_package_sha256": PROFILE_SHA,
            "generator": "gpt-oss-20b",
            "source_split": "dev",
            "scope": "generation_repeat",
            "metric": "adaptation_criterion_pass_rate",
            "decision_record": REVIEW,
            "formula": "sqrt(mean((repeat_rate - baseline_rate)^2) / Test_eligible_pair_count)",
            "source_artifact_sha256": file_sha(manifest_path),
            "source_release": manifest["original_release_url"],
            "source_files_sha256": dict(sorted(consumed.items())),
            "test_split_map_sha256": file_sha(args.split_map),
            "test_eligibility_sha256": file_sha(args.eligibility),
            "test_answers_read": False,
            "provider_calls": 0,
            "missingness_policy": (
                "available Dev repeat pairs; missing counts retained, never zero-filled"
            ),
        }
    )
    write_json(args.output, result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("dev-package", "eligibility", "split-map", "output"):
        parser.add_argument("--" + arg, type=Path, required=True)
    freeze(parser.parse_args())


if __name__ == "__main__":
    main()
