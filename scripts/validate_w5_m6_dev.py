"""Independently validate MiniLM Dev and the single frozen Test retrieval handoff."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
M6_ROOT = ROOT / "artifacts/w5/m6"
GOLD = ROOT / "artifacts/w5/m4-v3/gold_normalized/gold_v0_2_from_m3_v0_1_1.jsonl"
MODES = ("bm25", "dense", "hybrid")
K_VALUES = (1, 3, 5)


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def assert_close(actual: float, expected: float, label: str) -> None:
    if not math.isclose(actual, expected, rel_tol=0, abs_tol=1e-12):
        raise ValueError(f"{label}: {actual} != {expected}")


def validate(require_clean: bool, require_reportable: bool, split: str) -> None:
    if split not in {"proposed_dev", "proposed_test"}:
        raise ValueError(f"Unsupported split: {split}")
    expected_count = 12 if split == "proposed_dev" else 8
    modes = MODES
    if split == "proposed_test":
        selection = json.loads((M6_ROOT / "frozen_selection.json").read_text(encoding="utf-8"))
        modes = (selection["retrieval_mode"],)
        if modes != ("bm25",):
            raise ValueError("Frozen Test must use the Dev-selected BM25 mode")
        dev_scores = (
            M6_ROOT / "proposed_dev" / selection["experiment_id"] / "bm25/scores.json"
        )
        if hashlib.sha256(dev_scores.read_bytes()).hexdigest() != selection["dev_scores_sha256"]:
            raise ValueError("Frozen Test selection is not bound to the saved Dev score")
    base = M6_ROOT / split / "w5-minilm-primary-v1"
    gold_ids = {
        row["question_id"]
        for row in load_jsonl(GOLD)
        if row["split"] == split
    }
    if len(gold_ids) != expected_count:
        raise ValueError(
            f"Expected {expected_count} unique {split} questions, found {len(gold_ids)}"
        )

    reference_provenance: tuple[str, str, str] | None = None
    print("split mode questions excluded hit@1 hit@3 hit@5 recall@5 mrr reportable")
    for mode in modes:
        directory = base / mode
        stem = f"w5-minilm-primary-v1_{mode}_{split}"
        runs = load_jsonl(directory / f"{stem}.jsonl")
        score_rows = load_jsonl(directory / "retrieval_scores.jsonl")
        score = json.loads((directory / "scores.json").read_text(encoding="utf-8"))[
            "retrieval"
        ]
        manifest = json.loads((directory / f"{stem}.manifest.json").read_text(encoding="utf-8"))

        run_ids = [row["question_id"] for row in runs]
        score_ids = [row["question_id"] for row in score_rows]
        if set(run_ids) != gold_ids or set(score_ids) != gold_ids:
            raise ValueError(f"{mode}: run/score question IDs differ from normalized Dev Gold")
        if len(run_ids) != len(set(run_ids)) or len(score_ids) != len(set(score_ids)):
            raise ValueError(f"{mode}: duplicate question IDs")
        if manifest["top_k"] != 5 or manifest["k_values"] != list(K_VALUES):
            raise ValueError(f"{mode}: inconsistent Top-K or K values")
        if manifest["split"] != split or manifest["retrieval_mode"] != mode:
            raise ValueError(f"{mode}: incorrect split or mode in run manifest")
        if require_clean and manifest["git_dirty"]:
            raise ValueError(f"{mode}: this run was made from a dirty checkout")
        if require_reportable and not manifest["reportable"]:
            raise ValueError(f"{mode}: this run is provisional, not reportable")

        for run in runs:
            if run["status"] != "retrieved" or run["error"] is not None:
                raise ValueError(f"{mode}: retrieval failed for {run['question_id']}")
            result = run["retrieval"]
            hits = result["hits"]
            if len(hits) > 5:
                raise ValueError(f"{mode}: more than five hits")
            if [hit["rank"] for hit in hits] != list(range(1, len(hits) + 1)):
                raise ValueError(f"{mode}: nonconsecutive ranks")
            if len({hit["chunk_id"] for hit in hits}) != len(hits):
                raise ValueError(f"{mode}: duplicate retrieved chunk IDs")
            if any(not hit["source"] for hit in hits):
                raise ValueError(f"{mode}: missing source")
            provenance = result["provenance"]
            identity = tuple(
                provenance[key] for key in ("corpus_hash", "chunk_config_hash", "index_version")
            )
            if reference_provenance is None:
                reference_provenance = identity
            elif identity != reference_provenance:
                raise ValueError(f"{mode}: corpus/index provenance differs across runs")

        if score["sample_count"] != expected_count or score["excluded_runs"]["total"] != 0:
            raise ValueError(f"{mode}: unexpected sample count or excluded questions")
        included = [row for row in score_rows if row["included"]]
        if len(included) != expected_count:
            raise ValueError(f"{mode}: not all score rows are included")
        assert_close(
            sum(row["first_hit_mrr"] for row in included) / expected_count,
            score["mrr"],
            f"{mode} MRR",
        )
        for k in K_VALUES:
            key = str(k)
            for metric in ("hit_at_k", "recall_at_k"):
                mean = sum(row["by_k"][key][metric] for row in included) / expected_count
                assert_close(mean, score["by_k"][key][metric], f"{mode} {metric}@{k}")

        print(
            split,
            mode,
            len(runs),
            score["excluded_runs"]["total"],
            *[f"{score['by_k'][str(k)]['hit_at_k']:.4f}" for k in K_VALUES],
            f"{score['by_k']['5']['recall_at_k']:.4f}",
            f"{score['mrr']:.4f}",
            manifest["reportable"],
        )
    print(f"Independent {split} handoff checks passed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-clean", action="store_true")
    parser.add_argument("--require-reportable", action="store_true")
    parser.add_argument(
        "--split", choices=("proposed_dev", "proposed_test"), default="proposed_dev"
    )
    args = parser.parse_args()
    validate(
        require_clean=args.require_clean,
        require_reportable=args.require_reportable,
        split=args.split,
    )
