"""Deterministic report artifacts for M8 answer and citation scoring."""

from __future__ import annotations

import csv
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any


def _display(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.4f}"


def _markdown(result: Mapping[str, Any]) -> str:
    lines = [
        "# Answer and Citation Evaluation Report",
        "",
        "This report scores saved run records offline. "
        "It does not call a model or rerun retrieval.",
        "",
        f"Total records: {result['total_records']}",
        "",
        "## Metrics",
        "",
        "| Metric | Numerator | Denominator | Value | Excluded |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for name, metric in result["metrics"].items():
        lines.append(
            f"| `{name}` | {metric['numerator']:g} | {metric['denominator']:g} | "
            f"{_display(metric['value'])} | {metric['excluded']} |"
        )

    lines.extend(["", "## Metric definitions", ""])
    for name, metric in result["metrics"].items():
        lines.append(f"- `{name}`: {metric['definition']}")

    sections = (
        ("Answer outcomes", "answer_outcome_counts"),
        ("Abstention confusion", "abstention_confusion"),
        ("Reviewable failure labels", "failure_label_counts"),
        ("Execution outcomes", "execution_status_counts"),
        ("Retry and repair counts", "operation_counts"),
    )
    for heading, key in sections:
        lines.extend(["", f"## {heading}", ""])
        values = result[key]
        if values:
            lines.extend(f"- `{name}`: {count}" for name, count in values.items())
        else:
            lines.append("- None")

    lines.extend(
        [
            "",
            "## Comparable groups",
            "",
            "Development and formal Test slices remain separate by execution mode, condition, "
            "Gold version, split, and corpus version.",
            "",
            "| Mode | Condition | Gold | Split | Corpus | Records | Failure labels |",
            "| --- | --- | --- | --- | --- | ---: | ---: |",
        ]
    )
    for group in result["groups"]:
        lines.append(
            f"| {group['execution_mode']} | {group['condition_id']} | "
            f"{group['gold_annotation_version']} | {group['split']} | "
            f"{group['corpus_version']} | {group['total_records']} | "
            f"{sum(group['failure_label_counts'].values())} |"
        )
    lines.append("")
    return "\n".join(lines)


def write_answer_citation_reports(
    result: Mapping[str, Any], output_dir: Path
) -> dict[str, Path]:
    """Write aggregate, row-level, failure, CSV, and Markdown artifacts."""

    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "summary": output_dir / "answer_citation_summary.json",
        "per_question": output_dir / "answer_citation_scores.jsonl",
        "csv": output_dir / "answer_citation_summary.csv",
        "markdown": output_dir / "answer_citation_report.md",
        "failures": output_dir / "answer_citation_failures.jsonl",
    }

    summary = {key: value for key, value in result.items() if key != "records"}
    paths["summary"].write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    paths["markdown"].write_text(_markdown(result), encoding="utf-8")

    with paths["per_question"].open("w", encoding="utf-8", newline="\n") as stream:
        for record in result["records"]:
            stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")

    with paths["failures"].open("w", encoding="utf-8", newline="\n") as stream:
        for record in result["records"]:
            if record["failure_labels"]:
                failure = {
                    "question_id": record["question_id"],
                    "run_id": record["run_id"],
                    "status": record["status"],
                    "failure_labels": record["failure_labels"],
                }
                stream.write(json.dumps(failure, ensure_ascii=False, sort_keys=True) + "\n")

    with paths["csv"].open("w", encoding="utf-8", newline="") as stream:
        fieldnames = ["metric", "numerator", "denominator", "value", "excluded"]
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        for name, metric in result["metrics"].items():
            writer.writerow(
                {
                    "metric": name,
                    "numerator": metric["numerator"],
                    "denominator": metric["denominator"],
                    "value": metric["value"],
                    "excluded": metric["excluded"],
                }
            )
    return paths
