"""Deterministic report artifacts for M8 answer and citation scoring."""

from __future__ import annotations

import csv
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any


def _display(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.4f}"


def _append_metric_table(
    lines: list[str], metrics: Mapping[str, Mapping[str, Any]]
) -> None:
    lines.extend(
        [
            "| Metric | Numerator | Denominator | Value | Excluded |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for name, metric in metrics.items():
        lines.append(
            f"| `{name}` | {metric['numerator']:g} | {metric['denominator']:g} | "
            f"{_display(metric['value'])} | {metric['excluded']} |"
        )


def _append_counts(lines: list[str], values: Mapping[str, int]) -> None:
    if values:
        lines.extend(f"- `{name}`: {count}" for name, count in values.items())
    else:
        lines.append("- None")


def _append_cause_table(
    lines: list[str], confusion: Mapping[str, Mapping[str, int]]
) -> None:
    lines.extend(
        [
            "| Cause | Correct abstention | Wrong abstention | Unresolved Gold |",
            "| --- | ---: | ---: | ---: |",
        ]
    )
    for cause, outcomes in confusion.items():
        lines.append(
            f"| `{cause}` | {outcomes['correct_abstention']} | "
            f"{outcomes['wrong_abstention']} | {outcomes['unresolved']} |"
        )


def _markdown(result: Mapping[str, Any]) -> str:
    lines = [
        "# Answer and Citation Evaluation Report",
        "",
        "This report scores saved run records offline. "
        "It does not call a model or rerun retrieval.",
        "",
        f"Total records: {result['total_records']}",
        "",
        "## Overall diagnostic aggregate",
        "",
        "The overall values may combine multiple comparable groups. Formal comparisons must "
        "use the group-specific results below so that retrieval mode, condition, data "
        "version, split, and corpus version remain separate.",
        "",
        "### Metrics",
        "",
    ]
    _append_metric_table(lines, result["metrics"])

    lines.extend(["", "### Metric definitions", ""])
    for name, definition in result["metric_definitions"].items():
        lines.append(f"- `{name}`: {definition}")

    sections = (
        ("Answer outcomes", "answer_outcome_counts"),
        ("Abstention confusion", "abstention_confusion"),
        ("Reviewable failure labels", "failure_label_counts"),
        ("Execution outcomes", "execution_status_counts"),
        ("Retry and repair counts", "operation_counts"),
    )
    for heading, key in sections:
        lines.extend(["", f"### {heading}", ""])
        _append_counts(lines, result[key])

    lines.extend(["", "### Abstention causes", ""])
    _append_counts(lines, result["abstention_cause_counts"])

    lines.extend(["", "### Abstention confusion by cause", ""])
    _append_cause_table(lines, result["abstention_confusion_by_cause"])

    lines.extend(["", "### Missing saved results", ""])
    lines.append(f"- `missing_run_count`: {result['missing_run_count']}")
    for question_id in result["missing_run_question_ids"]:
        lines.append(f"- `{question_id}`")

    lines.extend(["", "### Excluded runs", ""])
    _append_counts(lines, result["excluded_runs"])
    lines.append(f"- `unresolved_count`: {result['unresolved_count']}")

    lines.extend(
        [
            "",
            "## Comparable groups",
            "",
            "Development and formal Test slices remain separate by retrieval mode, condition, "
            "Gold version, split, and corpus version.",
            "",
            "| Mode | Condition | Data version | Split | Corpus | Records | Failure labels |",
            "| --- | --- | --- | --- | --- | ---: | ---: |",
        ]
    )
    for group in result["groups"]:
        lines.append(
            f"| {group['mode']} | {group['condition_id']} | "
            f"{group['data_version']} | {group['split']} | "
            f"{group['corpus_version']} | {group['total_records']} | "
            f"{sum(group['failure_label_counts'].values())} |"
        )

    for group in result["groups"]:
        lines.extend(
            [
                "",
                f"### {group['split']} | {group['mode']} | {group['condition_id']}",
                "",
                f"- `data_version`: {group['data_version']}",
                f"- `corpus_version`: {group['corpus_version']}",
                f"- `records`: {group['total_records']}",
                "",
                "#### Metrics",
                "",
            ]
        )
        _append_metric_table(lines, group["metrics"])
        lines.extend(["", "#### Abstention causes", ""])
        _append_counts(lines, group["abstention_cause_counts"])
        lines.extend(["", "#### Abstention confusion by cause", ""])
        _append_cause_table(lines, group["abstention_confusion_by_cause"])
        group_sections = (
            ("Answer outcomes", "answer_outcome_counts"),
            ("Reviewable failure labels", "failure_label_counts"),
            ("Execution outcomes", "execution_status_counts"),
            ("Retry and repair counts", "operation_counts"),
        )
        for heading, key in group_sections:
            lines.extend(["", f"#### {heading}", ""])
            _append_counts(lines, group[key])
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
                    "abstention_cause": record["abstention_cause"],
                    "failure_labels": record["failure_labels"],
                }
                stream.write(json.dumps(failure, ensure_ascii=False, sort_keys=True) + "\n")

    with paths["csv"].open("w", encoding="utf-8", newline="") as stream:
        fieldnames = [
            "metric",
            "numerator",
            "denominator",
            "value",
            "excluded",
            "definition",
            "cause",
            "outcome",
            "scope",
            "mode",
            "condition_id",
            "data_version",
            "split",
            "corpus_version",
        ]
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        summaries = [("overall", result), *[("group", group) for group in result["groups"]]]
        for scope, summary_result in summaries:
            identity = {
                "scope": scope,
                "mode": summary_result.get("mode", ""),
                "condition_id": summary_result.get("condition_id", ""),
                "data_version": summary_result.get("data_version", ""),
                "split": summary_result.get("split", ""),
                "corpus_version": summary_result.get("corpus_version", ""),
            }
            for name, metric in summary_result["metrics"].items():
                writer.writerow(
                    {
                        "metric": name,
                        "numerator": metric["numerator"],
                        "denominator": metric["denominator"],
                        "value": metric["value"],
                        "excluded": metric["excluded"],
                        "definition": result["metric_definitions"][name],
                        "cause": "",
                        "outcome": "",
                        **identity,
                    }
                )
            for cause, outcomes in summary_result[
                "abstention_confusion_by_cause"
            ].items():
                cause_total = summary_result["abstention_cause_counts"][cause]
                for outcome, count in outcomes.items():
                    writer.writerow(
                        {
                            "metric": (
                                "abstention_confusion_by_cause."
                                f"{cause}.{outcome}"
                            ),
                            "numerator": count,
                            "denominator": cause_total,
                            "value": None if cause_total == 0 else count / cause_total,
                            "excluded": summary_result["total_records"] - cause_total,
                            "definition": (
                                f"{outcome} outcomes among system abstentions whose "
                                f"abstention_cause is {cause}; excluded is records in this "
                                "scope minus abstentions with this cause."
                            ),
                            "cause": cause,
                            "outcome": outcome,
                            **identity,
                        }
                    )
    return paths
