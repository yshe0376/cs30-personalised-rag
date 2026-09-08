"""Deterministic JSON, CSV, and Markdown outputs for evaluation reviews."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from .models import EvaluationRecord, EvaluationReport


def _display_value(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.4f}"


def _display_number(value: float) -> str:
    return f"{value:g}"


def _markdown(report: EvaluationReport) -> str:
    lines = [
        "# M8 Answer and Citation Evaluation Report",
        "",
        "This report scores saved run records offline. "
        "It does not call a model or rerun retrieval.",
        "",
        f"Total records: {report.total_records}",
        "",
        "## Metrics",
        "",
        "| Metric | Numerator | Denominator | Value | Excluded |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for name, metric in report.metrics.items():
        lines.append(
            f"| `{name}` | {_display_number(metric.numerator)} | "
            f"{_display_number(metric.denominator)} | "
            f"{_display_value(metric.value)} | {metric.excluded} |"
        )
    lines.extend(["", "## Metric definitions", ""])
    for name, metric in report.metrics.items():
        lines.append(f"- `{name}`: {metric.definition}")
    lines.extend(["", "## Answer outcomes", ""])
    for outcome, count in report.answer_outcome_counts.items():
        lines.append(f"- `{outcome}`: {count}")
    lines.extend(["", "## Abstention confusion", ""])
    for outcome, count in report.abstention_confusion.items():
        lines.append(f"- `{outcome}`: {count}")
    lines.extend(["", "## Reviewable failure labels", ""])
    for label, count in report.failure_label_counts.items():
        lines.append(f"- `{label.value}`: {count}")
    lines.extend(["", "## Retry and repair counts", ""])
    for name, count in report.operation_counts.items():
        lines.append(f"- `{name}`: {count}")
    lines.extend(["", "## Execution outcomes", ""])
    for status, count in report.failure_counts.items():
        lines.append(f"- `{status.value}`: {count}")
    lines.extend(["", "## Comparable groups", ""])
    lines.append(
        "Development, fixture and formal Test slices remain separate through the `split`, "
        "mode, condition, dataset and corpus identities below."
    )
    lines.append("")
    lines.append("| Mode | Condition | Dataset | Split | Corpus | Samples | Failure labels |")
    lines.append("| --- | --- | --- | --- | --- | ---: | ---: |")
    for group in report.groups:
        failures = sum(group.failure_label_counts.values())
        lines.append(
            f"| {group.mode} | {group.condition_id} | {group.dataset_version} | "
            f"{group.split} | {group.corpus_version} | {group.total_records} | {failures} |"
        )
    lines.append("")
    return "\n".join(lines)


def write_evaluation_report(
    report: EvaluationReport,
    records: list[EvaluationRecord],
    output_dir: Path,
) -> dict[str, Path]:
    """Write stable report artifacts and return their paths."""

    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / "scores.json"
    csv_path = output_dir / "scores.csv"
    markdown_path = output_dir / "report.md"
    per_question_path = output_dir / "scores.jsonl"
    failures_path = output_dir / "failures.jsonl"

    summary_path.write_text(
        report.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(_markdown(report), encoding="utf-8")

    score_by_id = {score.question_id: score for score in report.records}
    with csv_path.open("w", encoding="utf-8", newline="") as stream:
        fieldnames = [
            "question_id",
            "execution_status",
            "answer_outcome",
            "failure_labels",
            "answer_correct",
            "abstention_correct",
            "citation_valid",
            "gold_citation_hit",
            "valid_citations",
            "total_citations",
            "answerability",
            "mode",
            "condition_id",
            "split",
            "dataset_version",
            "corpus_version",
            "retry_count",
            "repair_count",
        ]
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            score = score_by_id[record.question_id]
            writer.writerow(
                {
                    "question_id": record.question_id,
                    "execution_status": record.execution_status.value,
                    "answer_outcome": score.answer_outcome,
                    "failure_labels": ",".join(label.value for label in score.failure_labels),
                    "answer_correct": score.answer_correct,
                    "abstention_correct": score.abstention_correct,
                    "citation_valid": score.citation_valid,
                    "gold_citation_hit": score.gold_citation_hit,
                    "valid_citations": sum(check.valid for check in score.citation_checks),
                    "total_citations": len(score.citation_checks),
                    "answerability": record.answerability.value,
                    "mode": record.mode or "",
                    "condition_id": record.condition_id or "",
                    "split": record.split or "",
                    "dataset_version": record.dataset_version or "",
                    "corpus_version": record.corpus_version or "",
                    "retry_count": record.retry_count,
                    "repair_count": record.repair_count,
                }
            )

    with per_question_path.open("w", encoding="utf-8", newline="\n") as stream:
        for record in records:
            score = score_by_id[record.question_id]
            row = {
                "record": record.model_dump(mode="json"),
                "score": score.model_dump(mode="json"),
            }
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")

    failures = [record for record in records if score_by_id[record.question_id].failure_labels]
    with failures_path.open("w", encoding="utf-8", newline="\n") as stream:
        for record in failures:
            score = score_by_id[record.question_id]
            row = {
                "question_id": record.question_id,
                "execution_status": record.execution_status.value,
                "failure_labels": [label.value for label in score.failure_labels],
                "error": record.error,
            }
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")

    return {
        "summary": summary_path,
        "csv": csv_path,
        "markdown": markdown_path,
        "per_question": per_question_path,
        "failures": failures_path,
    }
