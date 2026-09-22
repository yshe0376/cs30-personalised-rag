"""Join M6 retrieval rows and Gold mapping into Member 7 experiment cases."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Literal

from cs30.contracts import RetrievalResult, StudentLevel
from cs30.profile import Week1ProfileProvider

from .lambda_search import InputStatus, load_expected_question_count, sha256_file

TargetSplit = Literal["dev", "test"]


def _gold_chunk_ids(path: Path) -> dict[str, set[str]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    entries = payload.get("entries")
    if not isinstance(entries, list):
        raise ValueError("Gold mapping must contain an entries list")
    by_question: dict[str, set[str]] = defaultdict(set)
    for index, entry in enumerate(entries):
        try:
            question_id = str(entry["question_id"]).strip()
            chunk_ids = entry["matching_chunk_ids"]
        except (KeyError, TypeError) as exc:
            raise ValueError(f"invalid Gold mapping entry {index}: {exc}") from exc
        if not question_id or not isinstance(chunk_ids, list):
            raise ValueError(f"invalid Gold mapping entry {index}")
        by_question[question_id].update(str(chunk_id) for chunk_id in chunk_ids)
    return dict(by_question)


def prepare_cases(
    retrieval_runs_path: Path,
    retrieval_manifest_path: Path,
    gold_mapping_path: Path,
    *,
    target_split: TargetSplit,
    input_status: InputStatus,
    profile_prefix: str = "member7",
    split_manifest_path: Path | None = None,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    source_manifest = json.loads(retrieval_manifest_path.read_text(encoding="utf-8"))
    source_split = str(source_manifest.get("split", "")).strip()
    source_reportable = source_manifest.get("reportable") is True
    source_execution_mode = source_manifest.get("execution_mode")
    source_manifest_sha256 = sha256_file(retrieval_manifest_path)
    if source_execution_mode != "retrieval_only":
        raise ValueError("M6 source manifest execution_mode must be retrieval_only")
    if input_status == "formal" and (
        source_split != target_split or not source_reportable
    ):
        raise ValueError(
            "formal case preparation requires a reportable M6 manifest whose split "
            "matches the target split"
        )

    relevant_by_question = _gold_chunk_ids(gold_mapping_path)
    provider = Week1ProfileProvider(profile_prefix=profile_prefix)
    rows: list[dict[str, object]] = []
    seen_questions: set[str] = set()
    for line_number, raw in enumerate(
        retrieval_runs_path.read_text(encoding="utf-8").splitlines(), 1
    ):
        if not raw.strip():
            continue
        try:
            payload = json.loads(raw)
            question_id = str(payload["question_id"]).strip()
            if payload["execution_mode"] != "retrieval_only":
                raise ValueError("execution_mode must be retrieval_only")
            if payload["status"] != "retrieved":
                raise ValueError("status must be retrieved")
            retrieval = RetrievalResult.model_validate(payload["retrieval"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(
                f"invalid M6 retrieval row at {retrieval_runs_path}:{line_number}: {exc}"
            ) from exc
        if not question_id:
            raise ValueError(f"empty question_id at {retrieval_runs_path}:{line_number}")
        if question_id in seen_questions:
            raise ValueError(f"duplicate M6 question_id: {question_id}")
        seen_questions.add(question_id)
        relevant = relevant_by_question.get(question_id)
        if not relevant:
            raise ValueError(f"Gold mapping has no matching chunks for {question_id}")

        for level in StudentLevel:
            rows.append(
                {
                    "schema_version": "1.0",
                    "question_id": question_id,
                    "split": target_split,
                    "source_split": source_split,
                    "source_reportable": source_reportable,
                    "source_manifest_sha256": source_manifest_sha256,
                    "question": retrieval.query,
                    "profile": provider.get(level).model_dump(mode="json"),
                    "retrieval": retrieval.model_dump(mode="json"),
                    "relevant_chunk_ids": sorted(relevant),
                }
            )

    if not seen_questions:
        raise ValueError(f"no M6 retrieval rows found in {retrieval_runs_path}")

    if input_status == "formal" and split_manifest_path is None:
        raise ValueError("formal case preparation requires a split manifest")
    expected_questions = (
        load_expected_question_count(split_manifest_path, target_split)
        if split_manifest_path is not None
        else None
    )
    if (
        input_status == "formal"
        and expected_questions is not None
        and len(seen_questions) != expected_questions
    ):
        raise ValueError(
            f"formal {target_split} question count does not match the split manifest; "
            f"expected {expected_questions}, found {len(seen_questions)}"
        )
    formally_complete = (
        input_status == "formal"
        and source_reportable
        and source_split == target_split
        and len(seen_questions) == expected_questions
    )
    manifest: dict[str, object] = {
        "schema_version": "1.0",
        "result_type": "member7_prepared_condition_cases",
        "input_status": input_status,
        "target_split": target_split,
        "source_split": source_split,
        "source_reportable": source_reportable,
        "formally_complete": formally_complete,
        "question_count": len(seen_questions),
        "expected_question_count": expected_questions,
        "profile_levels": [level.value for level in StudentLevel],
        "case_count": len(rows),
        "retrieval_runs_sha256": sha256_file(retrieval_runs_path),
        "retrieval_manifest_sha256": source_manifest_sha256,
        "gold_mapping_sha256": sha256_file(gold_mapping_path),
        "split_manifest_sha256": sha256_file(split_manifest_path)
        if split_manifest_path is not None
        else None,
        "retrieval_run_id": source_manifest.get("run_id"),
        "dataset_version": source_manifest.get("dataset_version"),
        "corpus_version": source_manifest.get("corpus_version"),
        "chunk_version": source_manifest.get("chunk_version"),
        "index_version": source_manifest.get("index_version"),
    }
    return rows, manifest


def write_prepared_cases(
    cases_path: Path,
    manifest_path: Path,
    rows: list[dict[str, object]],
    manifest: dict[str, object],
) -> None:
    cases_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    cases_path.write_text(
        "".join(f"{json.dumps(row, ensure_ascii=False, sort_keys=True)}\n" for row in rows),
        encoding="utf-8",
    )
    manifest_path.write_text(
        f"{json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True)}\n",
        encoding="utf-8",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--retrieval-runs", type=Path, required=True)
    parser.add_argument("--retrieval-manifest", type=Path, required=True)
    parser.add_argument("--gold-mapping", type=Path, required=True)
    parser.add_argument(
        "--split-manifest",
        type=Path,
        help="manifest declaring the expected split size; required for formal inputs",
    )
    parser.add_argument("--target-split", choices=["dev", "test"], required=True)
    parser.add_argument(
        "--input-status",
        choices=["fixture", "provisional", "formal"],
        required=True,
    )
    parser.add_argument("--profile-prefix", default="member7")
    parser.add_argument("--output-cases", type=Path, required=True)
    parser.add_argument("--output-manifest", type=Path, required=True)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    rows, manifest = prepare_cases(
        args.retrieval_runs,
        args.retrieval_manifest,
        args.gold_mapping,
        target_split=args.target_split,
        input_status=args.input_status,
        profile_prefix=args.profile_prefix,
        split_manifest_path=args.split_manifest,
    )
    write_prepared_cases(
        args.output_cases,
        args.output_manifest,
        rows,
        manifest,
    )
    print(args.output_cases)


if __name__ == "__main__":
    main()
