"""Assess saved open answers, apply real human reviews, and audit calibration."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

from pydantic import BaseModel

from cs30.evaluation.models import GoldSample
from cs30.generation.client import OllamaChatClient, OpenAIResponsesClient
from cs30.v2.contracts import GoldQuestion

from .gemini_judge_client import GeminiJudgeClient
from .open_answer_models import (
    HumanDecision,
    HumanRating,
    OpenAnswerExperiment,
    OpenAnswerRubric,
    OpenAnswerRun,
    OpenAnswerScore,
)
from .open_answer_reporting import (
    apply_human_reviews,
    calibration_report,
    write_open_answer_reports,
)
from .open_answer_scoring import OpenAnswerScorer, sha256_bytes


def read_jsonl(path: Path, data: bytes | None = None) -> list[dict]:
    result = []
    text = (path.read_bytes() if data is None else data).decode("utf-8")
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError("each JSONL row must be an object")
        except ValueError as exc:
            raise ValueError(f"invalid JSONL at {path}:{number}: {exc}") from exc
        result.append(value)
    return result


def unique_models(rows: list[dict], model: type[BaseModel], key: str) -> dict:
    result = {}
    for payload in rows:
        value = model.model_validate(payload)
        identifier = getattr(value, key)
        if identifier in result:
            raise ValueError(f"duplicate {key}: {identifier}")
        result[identifier] = value
    return result


def load_gold(path: Path, data: bytes | None = None) -> dict:
    result = {}
    for payload in read_jsonl(path, data):
        version = payload.get("schema_version")
        if version not in {"0.1", "0.2", "2.0"}:
            raise ValueError("Gold requires an explicit supported schema_version")
        question = (GoldQuestion if version == "2.0" else GoldSample).model_validate(payload)
        if question.question_id in result:
            raise ValueError("duplicate Gold question ID")
        result[question.question_id] = question
    if not result:
        raise ValueError("Gold must not be empty")
    return result


def _fingerprint(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    score = commands.add_parser("score", help="score an explicit matrix of saved answers")
    for name in ("gold", "rubrics", "runs", "expected-manifest", "output-dir"):
        score.add_argument(f"--{name}", type=Path, required=True)
    score.add_argument(
        "--provider", choices=("none", "ollama", "openai", "gemini"), default="none"
    )
    score.add_argument(
        "--model", help="independent judge model identifier, preferably version-pinned"
    )
    score.add_argument("--cache-dir", type=Path)
    score.add_argument("--timeout", type=float, default=120.0)
    score.add_argument("--max-output-tokens", type=int, default=2048)
    score.add_argument("--max-retries", type=int, default=1)
    score.add_argument(
        "--allow-self-judge",
        action="store_true",
        help="explicit exploratory opt-in; does not permit formal claims",
    )
    review = commands.add_parser(
        "review", help="apply hash-bound human decisions into a new report"
    )
    review.add_argument("--scores", type=Path, required=True)
    review.add_argument("--decisions", type=Path, required=True)
    review.add_argument("--output-dir", type=Path, required=True)
    calibrate = commands.add_parser(
        "calibrate", help="compare actual double ratings with predictions"
    )
    calibrate.add_argument("--scores", type=Path, required=True)
    calibrate.add_argument("--ratings", type=Path, required=True)
    calibrate.add_argument("--adjudications", type=Path)
    calibrate.add_argument("--output-dir", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.output_dir.exists():
            raise ValueError("output directory already exists; keep original reports immutable")
        if args.command == "score":
            if not math.isfinite(args.timeout) or args.timeout <= 0 or args.max_output_tokens <= 0:
                raise ValueError("judge timeout and output token limit must be finite and positive")
            snapshots = {
                name: getattr(args, name).read_bytes()
                for name in ("gold", "rubrics", "runs", "expected_manifest")
            }
            input_hashes = {name: sha256_bytes(data) for name, data in snapshots.items()}
            manifest = OpenAnswerExperiment.model_validate_json(snapshots["expected_manifest"])
            if input_hashes["gold"] != manifest.gold_sha256:
                raise ValueError("Gold file hash differs from the expected experiment")
            if (
                manifest.rubrics_sha256 is not None
                and input_hashes["rubrics"] != manifest.rubrics_sha256
            ):
                raise ValueError("rubric file hash differs from the expected experiment")
            gold = load_gold(args.gold, snapshots["gold"])
            rubrics = unique_models(
                read_jsonl(args.rubrics, snapshots["rubrics"]), OpenAnswerRubric, "question_id"
            )
            runs = unique_models(read_jsonl(args.runs, snapshots["runs"]), OpenAnswerRun, "run_id")
            if args.provider != "none" and not args.model:
                raise ValueError("a live judge provider requires --model")
            if args.provider == "none" and args.model:
                raise ValueError("--model requires a live judge provider")
            client = None
            if args.provider != "none":
                client_types = {
                    "ollama": OllamaChatClient,
                    "openai": OpenAIResponsesClient,
                    "gemini": GeminiJudgeClient,
                }
                client_type = client_types[args.provider]
                client = client_type(
                    args.model,
                    timeout_seconds=args.timeout,
                    max_output_tokens=args.max_output_tokens,
                    temperature=0.0,
                )
            scorer = OpenAnswerScorer(
                client,
                max_retries=args.max_retries,
                cache_directory=args.cache_dir,
                allow_self_judge=args.allow_self_judge,
            )
            records = scorer.score(manifest, gold, rubrics, runs)
            provenance = {
                "command": "score",
                "matrix_version": manifest.matrix_version,
                "generation_matrix_schema_version": manifest.schema_version,
                "input_sha256": input_hashes,
                "provider": args.provider,
                "judge_config": scorer.judge_config,
                "judge_config_sha256": scorer.judge_config_sha256,
                "allow_self_judge": args.allow_self_judge,
                "expected_run_ids": [case.run_id for case in manifest.cases],
                "rubrics_without_review_record": sorted(
                    key for key, rubric in rubrics.items() if rubric.review_record_id is None
                ),
                "gold_not_reviewed": sorted(
                    key
                    for key, question in gold.items()
                    if question.annotation_status != "reviewed"
                ),
            }
            write_open_answer_reports(records, args.output_dir, provenance)
            return (
                3
                if any(
                    r.score_status in {"needs_review", "judge_error", "missing_run"}
                    for r in records
                )
                else 0
            )
        records = list(unique_models(read_jsonl(args.scores), OpenAnswerScore, "run_id").values())
        if args.command == "review":
            decisions = list(
                unique_models(read_jsonl(args.decisions), HumanDecision, "run_id").values()
            )
            updated = apply_human_reviews(records, decisions)
            write_open_answer_reports(
                updated,
                args.output_dir,
                {
                    "command": "review",
                    "parent_scores_sha256": _fingerprint(args.scores),
                    "decisions_sha256": _fingerprint(args.decisions),
                },
            )
            return (
                3
                if any(
                    r.score_status in {"needs_review", "judge_error", "missing_run"}
                    for r in updated
                )
                else 0
            )
        ratings = [HumanRating.model_validate(row) for row in read_jsonl(args.ratings)]
        adjudications = (
            [HumanDecision.model_validate(row) for row in read_jsonl(args.adjudications)]
            if args.adjudications
            else []
        )
        report = calibration_report(records, ratings, adjudications)
        report["input_sha256"] = {
            "scores": _fingerprint(args.scores),
            "ratings": _fingerprint(args.ratings),
            "adjudications": _fingerprint(args.adjudications) if args.adjudications else None,
        }
        args.output_dir.mkdir(parents=True, exist_ok=False)
        (args.output_dir / "calibration_summary.json").write_text(
            json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8"
        )
        return 0
    except (ValueError, OSError) as exc:
        print(f"cs30-score-open-answers: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
