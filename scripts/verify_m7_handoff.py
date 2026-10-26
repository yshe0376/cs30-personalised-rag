"""Verify the published M7 Dev/repeat handoff offline, without any API calls."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from cs30.v2.experiment import load_prepared
from cs30.v2.experiment_checkpoint import load_cells


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def verify(root: Path) -> dict:
    inventory = json.loads((root / "handoff-file-inventory.json").read_text(encoding="utf-8"))
    for name, expected in inventory["files"].items():
        path = root / name
        require(path.resolve().is_relative_to(root.resolve()), "unsafe inventory path")
        require(path.is_file(), f"missing: {name}")
        require(digest(path) == expected["sha256"], f"changed: {name}")
    summary = json.loads((root / "final-generation-summary.json").read_text(encoding="utf-8"))
    totals = Counter()
    for model in summary["models"]:
        manifests = []
        for batch in model["checks"]:
            # Original paths are provenance only. Resolve by the archived basename.
            prepared = root / Path(batch["prepared_dir"]).name
            output = root / Path(batch["run_dir"]).name
            _, config, matrix, *_ = load_prepared(prepared)
            require(config.generator_model == model["model"], "model mismatch")
            require(config.split == "dev", "handoff must contain Dev only")
            manifest = json.loads((output / "run_manifest.json").read_text(encoding="utf-8"))
            require(manifest["status"] == "completed", "incomplete run")
            require(manifest["reportable"] is False, "unexpected formal-result flag")
            sha = digest(output / "run_manifest.json")
            require(sha == batch["run_manifest_sha256"], "run manifest mismatch")
            manifests.append(sha)
            for name, expected in manifest["output_sha256"].items():
                require(digest(output / name) == expected, f"output changed: {name}")
            cells = load_cells(output / "checkpoints", matrix.cases)
            answers = [json.loads(line) for line in
                       (output / "saved_answers.jsonl").read_text(encoding="utf-8").splitlines()
                       if line]
            traces = [json.loads(line) for line in
                      (output / "generation_records.jsonl").read_text(encoding="utf-8").splitlines()
                      if line]
            expected = batch["expected_cells"]
            require(len(cells) == len(answers) == len(traces) == expected, "cell count")
            require(len({r["run_id"] for r in answers}) == expected, "duplicate run ID")
            require({r["run_id"] for r in answers} == {c.run_id for c in matrix.cases},
                    "matrix mismatch")
            for answer in answers:
                require(cells[answer["run_id"]][0].model_dump(mode="json") == answer,
                        "answer differs from checkpoint")
            require(len({r["run_id"] for r in traces}) == expected, "duplicate trace")
            for trace in traces:
                require(cells[trace["run_id"]][1] == trace, "trace differs from checkpoint")
            statuses = Counter(r["status"] for r in answers)
            require(dict(statuses) == batch["statuses"], "status mismatch")
            totals.update(statuses)
        noise = json.loads(
            (root / f"{model['alias']}-text-repeat-diagnostic.json").read_text(encoding="utf-8")
        )
        require(noise["expected_pairs"] == 360, "repeat size mismatch")
        require(noise["baseline_manifest_sha256"] == manifests[0], "baseline binding")
        require(noise["repeat_manifest_sha256"] == manifests[1], "repeat binding")
        require(noise["scoring_noise_floor_status"] == "pending_m8_scoring",
                "text diagnostics must not claim scoring")
    require(sum(totals.values()) == summary["actual_primary_cells"] == 6624, "total count")
    require(totals["answered"] == summary["answered_primary_cells"] == 6540, "success count")
    require(totals["generation_error"] == summary["retained_failure_cells"] == 84,
            "failure count")
    return {"verified_files": len(inventory["files"]), "primary_cells": 6624,
            "statuses": dict(totals), "reportable": False, "api_calls": 0}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path,
                        default=Path("artifacts/m7-readiness-20261026"))
    print(json.dumps(verify(parser.parse_args().root), indent=2))
