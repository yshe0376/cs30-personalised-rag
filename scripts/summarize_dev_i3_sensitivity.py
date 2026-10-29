"""Recompute Dev intermediate rates with/without I3; never call a provider.

This is a versioned reporting supplement, not a rewrite of the frozen checklist,
judge outputs, caches, or the original scoring handoff. Test inputs are not accepted.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from statistics import mean

from cs30.contracts import StudentLevel
from cs30.evaluation.level_profiles import eligible_levels
from cs30.evaluation.models import PersonalisationEligibility

POLICY = "intermediate-i3-reference-only-v1"
DECISION = "https://github.com/yshe0376/cs30-personalised-rag/pull/223#issuecomment-6490707658"
PROFILE_SHA = "50bb9a61414268cb343b79c096bec3c380310c041eeb69deefbf51fc0ebd1b38"


def main_scope(item: dict) -> bool:
    return StudentLevel.INTERMEDIATE in eligible_levels(
        PersonalisationEligibility(item["eligibility"])
    )


def rates(record: dict) -> tuple[float, float, int]:
    """Validate a resolved intermediate record and average I1/I2/I3 versus I1/I2."""
    criteria = record["criteria"]
    verdicts = {c["criterion_id"]: c["verdict"] for c in criteria}
    if len(criteria) != 3 or set(verdicts) != {"I1", "I2", "I3"}:
        raise ValueError("expected exactly one verdict for each of I1, I2 and I3")
    if any(v not in {"pass", "fail"} for v in verdicts.values()):
        raise ValueError("always-assessed intermediate criteria must be pass or fail")
    old = sum(v == "pass" for v in verdicts.values()) / 3
    if abs(old - record["criterion_pass_rate"]) > 1e-12:
        raise ValueError("saved rate disagrees with saved criterion verdicts")
    new = sum(verdicts[k] == "pass" for k in ("I1", "I2")) / 2
    return old, new, int(verdicts["I3"] == "pass")


def summarize(inputs: list[dict], records: list[dict]) -> list[dict]:
    """Pair resolved judgements to expected cells; keep unresolved cells in counts."""
    expected = {r["evaluation_id"]: r for r in inputs if r["target_level"] == "intermediate"}
    if len({r["evaluation_id"] for r in inputs}) != len(inputs):
        raise ValueError("duplicate input evaluation ID")
    resolved = {}
    for record in records:
        if record["evaluated_level"] != "intermediate" or not record["is_target_level_evaluation"]:
            continue
        eid = record["evaluation_id"]
        if eid not in expected or eid in resolved:
            raise ValueError("unbound or duplicate target-level record")
        item = expected[eid]
        if record["condition"] != item["condition"] or record["eligibility"] != item["eligibility"]:
            raise ValueError("input and score metadata disagree")
        if record["enters_main_adaptation_result"] != main_scope(item):
            raise ValueError("intermediate main scope must match repository eligibility policy")
        resolved[eid] = rates(record)
    output = []
    for scope in ("all_target_intermediate", "main_eligible_intermediate"):
        selected = {
            eid: item
            for eid, item in expected.items()
            if scope == "all_target_intermediate" or main_scope(item)
        }
        for condition in ("all_conditions", *sorted({i["condition"] for i in expected.values()})):
            ids = [
                eid
                for eid, item in selected.items()
                if condition == "all_conditions" or item["condition"] == condition
            ]
            available = [resolved[eid] for eid in ids if eid in resolved]
            with_i3 = mean(r[0] for r in available) if available else None
            without_i3 = mean(r[1] for r in available) if available else None
            output.append(
                {
                    "scope": scope,
                    "condition": condition,
                    "expected_cells": len(ids),
                    "resolved_cells": len(available),
                    "unresolved_cells": len(ids) - len(available),
                    "mean_with_i3": with_i3,
                    "mean_without_i3": without_i3,
                    "difference_percentage_points": (
                        100 * (without_i3 - with_i3) if available else None
                    ),
                    "i3_reference_pass_rate": mean(r[2] for r in available) if available else None,
                }
            )
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    package, out = args.package.resolve(), args.out.resolve()
    if out.exists() or out.is_relative_to(package):
        raise ValueError("use a new output directory outside the immutable source package")
    checksums = json.loads((package / "SHA256SUMS.json").read_text(encoding="utf-8"))
    consumed = {}

    def verified(relative: str) -> Path:
        path = (package / relative).resolve()
        if not path.is_relative_to(package):
            raise ValueError("source path escapes the package")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if checksums.get(relative) != digest:
            raise ValueError(f"source hash mismatch: {relative}")
        consumed[relative] = digest
        return path

    manifest = json.loads(verified("handoff_manifest.json").read_text(encoding="utf-8"))
    verified("profile_checklist.frozen.json")
    if consumed["profile_checklist.frozen.json"] != PROFILE_SHA:
        raise ValueError("report policy is bound to the reviewed frozen profile")
    if manifest.get("kind") != "development_scoring_with_explicit_missingness":
        raise ValueError("only the reviewed Dev scoring package is accepted")
    batches = {b["batch"]: b for b in manifest["batches"] if b["batch"].startswith("dev-")}
    if set(batches) != {"dev-gpt-oss", "dev-llama", "dev-gemma"}:
        raise ValueError("expected the three reviewed Dev generator batches")
    summaries = {}
    for name, batch in sorted(batches.items()):

        def read_rows(relative: str) -> list[dict]:
            with verified(relative).open(encoding="utf-8") as stream:
                return [json.loads(line) for line in stream if line.strip()]

        inputs = read_rows(batch["inputs"])
        records = read_rows(batch["judge_evaluation_dir"] + "/adaptation_results.jsonl")
        summaries[name] = summarize(inputs, records)
    result = {
        "policy": POLICY,
        "decision": DECISION,
        "reportable": False,
        "description": "Paired available-cell means of answer-level criterion pass rates.",
        "limits": (
            "No aggregate pass threshold or confidence interval is inferred. Missing stays missing."
        ),
        "main_intermediate_criteria": ["I1", "I2"],
        "reference_only_criteria": ["I3"],
        "source_files_sha256": dict(sorted(consumed.items())),
        "by_batch": summaries,
    }
    out.mkdir(parents=True)
    with (out / "dev_i3_sensitivity.json").open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(result, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
