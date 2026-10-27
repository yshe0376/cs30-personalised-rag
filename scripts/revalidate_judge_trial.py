"""Revalidate saved trial evidence outputs without constructing an API client."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import Counter
from pathlib import Path

from cs30.evaluation.evidence_support import validate_evidence_support_output
from cs30.evaluation.judge_runtime import validate_output_against_request
from cs30.evaluation.v2_generation_models import GenerationEvaluationInput, JudgeRequest


def read_rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def audit_usage(root: Path) -> dict:
    """Recompute the recorded token costs; this reads files, never a billing API."""
    summary = json.loads((root / "summary.json").read_text(encoding="utf-8"))
    selection = json.loads((root / "selection.json").read_text(encoding="utf-8"))
    with (root / "calls.csv").open(encoding="utf-8-sig", newline="") as stream:
        calls = list(csv.DictReader(stream))
    prices = summary["price_usd_per_million"]
    for row in calls:
        expected = (
            int(row["input_tokens"]) * prices["input"]
            + int(row["output_tokens"]) * prices["output_incl_thinking"]
        ) / 1_000_000
        if not math.isclose(expected, float(row["cost_usd"]), abs_tol=1e-10):
            raise ValueError("Recorded call cost does not match tokens and declared prices")
    levels = {}
    for level, tasks in summary["levels"].items():
        rows = [row for row in calls if row["thinking_level"] == level]
        total = sum(float(row["cost_usd"]) for row in rows)
        if not math.isclose(total, tasks["total_spent_usd"], abs_tol=1e-10):
            raise ValueError("Recorded summary does not match call costs")
        levels[level] = {"client_attempts": len(rows), "token_cost_usd": total}
    return {
        "cells": len(selection),
        "selection_sha256": hashlib.sha256((root / "selection.json").read_bytes()).hexdigest(),
        "generators": dict(Counter(row["_generator"] for row in selection)),
        "levels": levels,
        "total_token_cost_usd": sum(row["token_cost_usd"] for row in levels.values()),
        "provider_invoice_reconciled": False,
    }


def revalidate_trial(root: Path) -> dict:
    """Check both validation layers; preserve every original file and decision."""
    results = []
    hashes = {}
    for folder in sorted(root.glob("thinking-*")):
        level = folder.name.removeprefix("thinking-")
        for result_path in sorted((folder / "evidence_support").glob("*-results.jsonl")):
            generator = result_path.name.removesuffix("-results.jsonl")
            request_path = result_path.with_name(generator + "-requests.jsonl")
            input_path = root / "subset" / generator / "inputs.jsonl"
            requests = {row["request_id"]: row for row in read_rows(request_path)}
            items = {
                (row["question"], row["answer"]): GenerationEvaluationInput.model_validate(row)
                for row in read_rows(input_path)
            }
            for path in (result_path, request_path, input_path):
                hashes[path.relative_to(root).as_posix()] = hashlib.sha256(
                    path.read_bytes()
                ).hexdigest()
            for envelope in read_rows(result_path):
                request = JudgeRequest.model_validate(requests[envelope["request_id"]])
                item = items[(request.payload["question"], request.payload["answer"])]
                record = {
                    "level": level,
                    "generator": generator,
                    "request_id": request.request_id,
                    "question_id": item.question_id,
                    "original_unresolved": envelope["unresolved"],
                }
                try:
                    raw = envelope.get("output") or envelope.get("raw_output")
                    if raw is None:
                        raise ValueError("No saved output available; no API replay is attempted")
                    output = validate_output_against_request(raw, request)
                    validate_evidence_support_output(
                        output.model_dump(mode="json"), request=request, item=item
                    )
                except ValueError as exc:
                    record.update(revalidated=False, error=str(exc), output=None)
                else:
                    record.update(
                        revalidated=True, error=None, output=output.model_dump(mode="json")
                    )
                results.append(record)
    if not results:
        raise ValueError("No saved evidence-support results found")
    levels = {}
    for level in sorted({row["level"] for row in results}):
        rows = [row for row in results if row["level"] == level]
        levels[level] = {
            "requests": len(rows),
            "previously_unresolved": sum(row["original_unresolved"] for row in rows),
            "recovered_offline": sum(
                row["original_unresolved"] and row["revalidated"] for row in rows
            ),
            "still_unresolved": sum(not row["revalidated"] for row in rows),
            "regressions": sum(
                not row["original_unresolved"] and not row["revalidated"] for row in rows
            ),
        }
    return {
        "api_calls": 0,
        "new_cost_usd": 0,
        "levels": levels,
        "source_hashes": hashes,
        "results": results,
    }


def comparison_review(root: Path) -> str:
    """Prepare the existing semantic disagreements for human review, not rescoring."""
    lines = ["# Existing high/low disagreements — human review pending", ""]
    counts = Counter()
    for task in ("adaptation", "discrimination"):

        def records(level: str, task: str = task) -> dict:
            return {
                row["request_id"]: row
                for path in (root / f"thinking-{level}" / task).glob("*-results.jsonl")
                for row in read_rows(path)
            }

        high, low = records("high"), records("low")
        requests = {
            row["request_id"]: row
            for path in (root / "thinking-high" / task).glob("*-requests.jsonl")
            for row in read_rows(path)
        }
        for request_id in sorted(high.keys() & low.keys()):
            left, right = high[request_id].get("output"), low[request_id].get("output")
            if not left or not right:
                continue
            if task == "adaptation":
                h = {row["criterion_id"]: row for row in left["criteria"]}
                low_rows = {row["criterion_id"]: row for row in right["criteria"]}
                differences = [
                    (key, h[key], low_rows[key])
                    for key in h.keys() & low_rows.keys()
                    if h[key]["verdict"] != low_rows[key]["verdict"]
                ]
            else:
                differences = (
                    [("predicted_level", left, right)]
                    if left["predicted_level"] != right["predicted_level"]
                    else []
                )
            for key, high_row, low_row in sorted(differences):
                counts[task] += 1
                payload = requests[request_id]["payload"]
                lines += [
                    f"## {task}: {request_id} / {key}",
                    "",
                    "Question: " + payload["question"],
                    "",
                    "Answer: " + payload["answer"],
                    "",
                    "High: " + json.dumps(high_row, ensure_ascii=False),
                    "",
                    "Low: " + json.dumps(low_row, ensure_ascii=False),
                    "",
                    "Human decision and reason: **pending**",
                    "",
                ]
    lines.insert(
        2,
        f"Existing differences: {counts['adaptation']} criterion verdicts; "
        f"{counts['discrimination']} level predictions. No new API calls.\n",
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trial-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    root, out = args.trial_root.resolve(), args.out.resolve()
    if out == root or root in out.parents:
        parser.error("Use a new output directory outside the original trial")
    report = revalidate_trial(root)
    report["original_usage_audit"] = audit_usage(root)
    review = comparison_review(root)
    out.mkdir(parents=True, exist_ok=False)
    (out / "revalidation.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# Offline evidence revalidation",
        "",
        "API calls: 0. New cost: USD 0. Original results unchanged.",
        "",
    ]
    for level, values in report["levels"].items():
        lines.append(
            f"- {level}: {values['recovered_offline']} recovered; "
            f"{values['still_unresolved']} still unresolved; {values['regressions']} regressions."
        )
    lines += [
        "",
        "This is validation of saved outputs, "
        "not a fresh low/high trial or a completed human audit.",
    ]
    (out / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (out / "human_review.md").write_text(review, encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
