"""Command-line entry point for offline M8 evaluation."""

from __future__ import annotations

import argparse
from pathlib import Path

from .adapter import load_evaluation_records
from .reporting import write_evaluation_report
from .scoring import evaluate_records


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Score saved CS30 runs without calling retrieval or a model."
    )
    parser.add_argument("--runs", type=Path, required=True, help="JSON or JSONL saved runs")
    parser.add_argument(
        "--gold",
        type=Path,
        help="Optional M3 JSON/JSONL joined by question_id",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Directory for scores.json, scores.csv, report.md and failures.jsonl",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    records = load_evaluation_records(args.runs, args.gold)
    report = evaluate_records(records)
    paths = write_evaluation_report(report, records, args.output_dir)
    print(f"Scored {report.total_records} saved records without model calls.")
    for label, path in paths.items():
        print(f"{label}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
