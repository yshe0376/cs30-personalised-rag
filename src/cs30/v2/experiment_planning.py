"""M7 API planning and repeat-generation diagnostics; never calls a model/judge."""

from __future__ import annotations

import json
import math
from pathlib import Path

from cs30.v2.experiment import load_prepared
from cs30.v2.experiment_checkpoint import load_cells
from cs30.v2.experiment_models import GenerationExperiment
from cs30.v2.io import sha256_bytes


def estimate_api_cost(
    prepared_dir: Path,
    *,
    input_price: float,
    output_price: float,
    mean_input_tokens: int,
    max_output_tokens: int,
    max_api_requests: int,
) -> dict:
    """Use supplied provider prices and measured/planned inputs, without credentials."""
    if (
        any(not math.isfinite(x) or x < 0 for x in (input_price, output_price))
        or min(mean_input_tokens, max_output_tokens, max_api_requests) < 1
    ):
        raise ValueError("prices must be finite/nonnegative; token and request budgets positive")
    manifest, _, matrix, *_ = load_prepared(prepared_dir)
    per_request = (mean_input_tokens * input_price + max_output_tokens * output_price) / 1_000_000
    return {
        "reportable": False,
        "question_count": manifest["question_count"],
        "nominal_requests": len(matrix.cases),
        "max_api_requests": max_api_requests,
        "input_usd_per_million": input_price,
        "output_usd_per_million": output_price,
        "mean_input_tokens_assumption": mean_input_tokens,
        "max_output_tokens_per_request": max_output_tokens,
        "nominal_planning_usd": per_request * len(matrix.cases),
        "request_cap_planning_usd": per_request * max_api_requests,
        "limitation": "Input length and billing may vary; this is a planning estimate, not a "
        "dollar cap. Set the provider account spend limit too. All HTTP attempts, "
        "including failures/fallbacks/retries, consume max-api-requests.",
    }


def _load_run(directory: Path):
    manifest = json.loads((directory / "run_manifest.json").read_bytes())
    if manifest.get("status") != "completed":
        raise ValueError("noise-floor report requires completed generation batches")
    for name, expected in manifest["output_sha256"].items():
        if sha256_bytes((directory / name).read_bytes()) != expected:
            raise ValueError("noise-floor run output hash mismatch")
    matrix = GenerationExperiment.model_validate_json(
        (directory / "expected_experiment.json").read_bytes()
    )
    cells = load_cells(directory / "checkpoints", matrix.cases)
    if set(cells) != {cell.run_id for cell in matrix.cases}:
        raise ValueError("noise-floor run is missing expected cells")
    return manifest, cells


def noise_floor_report(baseline_dir: Path, repeat_dir: Path) -> dict:
    if baseline_dir.resolve() == repeat_dir.resolve():
        raise ValueError("noise floor requires an independent repeat directory")
    first, baseline = _load_run(baseline_dir)
    second, repeat = _load_run(repeat_dir)
    for field in ("configuration", "client", "provider", "implementation_sha256"):
        if first.get(field) != second.get(field):
            raise ValueError(f"noise-floor {field} differs between runs")
    if first["configuration"]["split"] != "dev":
        raise ValueError("noise-floor repeats are Dev-only")
    for field in ("gold.jsonl", "corpus_manifest.json", "gold_conversion.json"):
        if (
            first["prepared_inputs"]["input_sha256"][field]
            != second["prepared_inputs"]["input_sha256"][field]
        ):
            raise ValueError("noise-floor source inputs differ")
    if not set(repeat) <= set(baseline):
        raise ValueError("repeat cells must be a subset of baseline cells")
    paired, failures, mismatches, choice_changes, citation_changes = 0, 0, 0, 0, 0
    for run_id, (record, details) in repeat.items():
        previous, original = baseline[run_id]
        for field in ("evidence", "profile", "selected_candidate_ids"):
            if details[field] != original[field]:
                raise ValueError("noise-floor evidence/profile differs")
        prompt_a = (original.get("generation_trace") or {}).get("prompt_sha256")
        prompt_b = (details.get("generation_trace") or {}).get("prompt_sha256")
        if prompt_a != prompt_b:
            raise ValueError("noise-floor prompt differs")
        if record.status not in {"answered", "abstained"} or previous.status not in {
            "answered",
            "abstained",
        }:
            failures += 1
            continue
        paired += 1
        mismatches += record.answer != previous.answer
        choice_changes += record.answer.final_choice != previous.answer.final_choice
        citation_changes += set(record.answer.citations) != set(previous.answer.citations)
    return {
        "schema_version": "0.1",
        "reportable": False,
        "repeat_questions": len({r.question_id for r, _ in repeat.values()}),
        "expected_pairs": len(repeat),
        "successful_pairs": paired,
        "paired_technical_failures": failures,
        "answer_mismatches": mismatches,
        "answer_mismatch_rate": mismatches / paired if paired else None,
        "final_choice_changes": choice_changes,
        "citation_set_changes": citation_changes,
        "baseline_manifest_sha256": sha256_bytes((baseline_dir / "run_manifest.json").read_bytes()),
        "repeat_manifest_sha256": sha256_bytes((repeat_dir / "run_manifest.json").read_bytes()),
        "policy": "Compare complete structured answers exactly on independently generated Dev "
        "pairs with identical inputs. Failures reported separately; no semantic or "
        "judge score is inferred. API output is not reproducible verbatim.",
    }
