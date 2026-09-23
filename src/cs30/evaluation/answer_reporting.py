"""Deterministic report artifacts for M8 answer and citation scoring."""

from __future__ import annotations

import csv
import html
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

_KEY_METRICS = (
    "answer_choice_accuracy_all",
    "answer_choice_accuracy_answered",
    "abstention_accuracy",
    "abstention_f1",
    "raw_schema_validity",
    "citation_validity",
    "gold_evidence_citation_coverage",
    "per_citation_validity",
    "repair_rate",
    "technical_failure_rate",
    "provider_failure_rate",
)

_METRIC_LABELS = {
    "answer_choice_accuracy_all": "Answer accuracy (all eligible)",
    "answer_choice_accuracy_answered": "Answer accuracy (answered)",
    "abstention_accuracy": "Abstention accuracy",
    "abstention_f1": "Abstention F1",
    "raw_schema_validity": "Raw schema validity",
    "citation_validity": "Citation validity",
    "gold_evidence_citation_coverage": "Gold citation coverage",
    "per_citation_validity": "Per-citation validity",
    "repair_rate": "Repair rate",
    "technical_failure_rate": "Technical failure rate",
    "provider_failure_rate": "Provider failure rate",
}


def _display(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.4f}"


def _report_status(result: Mapping[str, Any]) -> tuple[str, str]:
    mode = str(result.get("scoring_mode", "development"))
    if result.get("reportable") is True and mode == "reportable":
        return mode, "REPORTABLE"
    return mode, "DEVELOPMENT / NOT FOR FORMAL CLAIMS"


def _latex_escape(value: object) -> str:
    text = str(value)
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(character, character) for character in text)


def _bar_chart_svg(
    title: str,
    values: Mapping[str, float | int | None],
    *,
    proportion: bool,
) -> str:
    rows = list(values.items())
    width = 920
    row_height = 38
    height = 104 + max(len(rows), 1) * row_height
    label_x = 24
    bar_x = 330
    bar_width = 500
    numeric_values = [float(value) for value in values.values() if value is not None]
    maximum = 1.0 if proportion else max(numeric_values, default=1.0)
    if maximum <= 0:
        maximum = 1.0
    mode_label = "Rate" if proportion else "Count"
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
            f'height="{height}" viewBox="0 0 {width} {height}" role="img" '
            f'aria-label="{html.escape(title, quote=True)}">'
        ),
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        (
            f'<text x="{label_x}" y="32" font-family="Arial, sans-serif" '
            f'font-size="20" font-weight="700" fill="#111827">{html.escape(title)}</text>'
        ),
        (
            f'<text x="{bar_x}" y="60" font-family="Arial, sans-serif" '
            f'font-size="12" fill="#4b5563">{mode_label}</text>'
        ),
    ]
    if not rows:
        lines.append(
            '<text x="24" y="92" font-family="Arial, sans-serif" font-size="14" '
            'fill="#6b7280">No applicable data</text>'
        )
    for index, (label, value) in enumerate(rows):
        y = 86 + index * row_height
        escaped_label = html.escape(label)
        lines.append(
            f'<text x="{label_x}" y="{y + 16}" font-family="Arial, sans-serif" '
            f'font-size="13" fill="#1f2937">{escaped_label}</text>'
        )
        lines.append(
            f'<rect x="{bar_x}" y="{y}" width="{bar_width}" height="20" '
            'rx="3" fill="#e5e7eb"/>'
        )
        if value is None:
            display = "N/A"
            filled = 0.0
        else:
            numeric = float(value)
            display = f"{numeric:.4f}" if proportion else f"{int(numeric)}"
            filled = max(0.0, min(numeric / maximum, 1.0)) * bar_width
        if filled:
            lines.append(
                f'<rect x="{bar_x}" y="{y}" width="{filled:.2f}" height="20" '
                'rx="3" fill="#2563eb"/>'
            )
        lines.append(
            f'<text x="{bar_x + bar_width + 12}" y="{y + 16}" '
            'font-family="Arial, sans-serif" font-size="13" fill="#111827">'
            f'{html.escape(display)}</text>'
        )
    lines.append("</svg>")
    return "\n".join(lines) + "\n"


def _metrics_chart(result: Mapping[str, Any]) -> str:
    metrics = result["metrics"]
    values = {
        _METRIC_LABELS[name]: metrics[name]["value"]
        for name in _KEY_METRICS
        if name in metrics
    }
    return _bar_chart_svg("Answer and citation metrics", values, proportion=True)


def _counts_chart(title: str, values: Mapping[str, int]) -> str:
    display_values = {
        name.replace("_", " ").title(): count
        for name, count in values.items()
        if count > 0
    }
    return _bar_chart_svg(title, display_values, proportion=False)


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
    scoring_mode, status = _report_status(result)
    lines = [
        "# Answer and Citation Evaluation Report",
        "",
        "This report scores saved run records offline. "
        "It does not call a model or rerun retrieval.",
        "",
        f"Report status: **{status}**",
        "",
        f"Scoring mode: `{scoring_mode}`",
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


def _latex_metric_rows(metrics: Mapping[str, Mapping[str, Any]]) -> list[str]:
    rows = []
    for name, metric in metrics.items():
        rows.append(
            "{} & {:g} & {:g} & {} & {} \\\\".format(
                _latex_escape(name),
                metric["numerator"],
                metric["denominator"],
                _latex_escape(_display(metric["value"])),
                metric["excluded"],
            )
        )
    if not rows:
        rows.append(r"No applicable metrics & -- & -- & -- & -- \\")
    return rows


def _latex_count_rows(values: Mapping[str, int]) -> list[str]:
    rows = [
        f"{_latex_escape(name)} & {count} \\\\" for name, count in values.items()
    ]
    return rows or [r"None & 0 \\"]


def _latex(result: Mapping[str, Any]) -> str:
    scoring_mode, status = _report_status(result)
    lines = [
        r"\documentclass[11pt]{article}",
        r"\usepackage[margin=2.2cm]{geometry}",
        r"\usepackage{booktabs}",
        r"\usepackage{longtable}",
        r"\usepackage[hidelinks]{hyperref}",
        r"\title{Answer and Citation Evaluation Report}",
        r"\author{CS-30 Personalised AI Learning Assistant}",
        r"\date{}",
        r"\begin{document}",
        r"\maketitle",
        r"\section*{Report status}",
        rf"\textbf{{{_latex_escape(status)}}}\\",
        rf"Scoring mode: \texttt{{{_latex_escape(scoring_mode)}}}\\",
        rf"Total records: {result['total_records']}\\",
        (
            "This report scores saved run records offline. It does not call a model "
            "or rerun retrieval."
        ),
        r"\section*{Overall diagnostic aggregate}",
        (
            "Formal comparisons use the group-specific tables below. The overall "
            "aggregate may combine distinct retrieval modes, conditions, data versions, "
            "splits, or corpus versions."
        ),
        r"\begin{longtable}{p{0.43\textwidth}rrrr}",
        r"\toprule",
        r"Metric & Numerator & Denominator & Value & Excluded \\",
        r"\midrule",
        r"\endhead",
        *_latex_metric_rows(result["metrics"]),
        r"\bottomrule",
        r"\end{longtable}",
        r"\section*{Metric definitions}",
        r"\begin{description}",
        *[
            rf"\item[\texttt{{{_latex_escape(name)}}}] {_latex_escape(definition)}"
            for name, definition in result["metric_definitions"].items()
        ],
        r"\end{description}",
        r"\section*{Answer outcomes}",
        r"\begin{tabular}{lr}",
        r"\toprule Outcome & Count \\",
        r"\midrule",
        *_latex_count_rows(result["answer_outcome_counts"]),
        r"\bottomrule",
        r"\end{tabular}",
        r"\section*{Reviewable failure labels}",
        r"\begin{tabular}{lr}",
        r"\toprule Label & Count \\",
        r"\midrule",
        *_latex_count_rows(result["failure_label_counts"]),
        r"\bottomrule",
        r"\end{tabular}",
        r"\section*{Excluded and missing runs}",
        r"\begin{tabular}{lr}",
        r"\toprule Reason & Count \\",
        r"\midrule",
        *_latex_count_rows(result["excluded_runs"]),
        f"missing\\_run\\_count & {result['missing_run_count']} \\\\",
        f"unresolved\\_count & {result['unresolved_count']} \\\\",
        r"\bottomrule",
        r"\end{tabular}",
        r"\section*{Comparable groups}",
    ]
    if not result["groups"]:
        lines.append("No comparable groups were produced.")
    for group in result["groups"]:
        heading = "{} | {} | {}".format(
            group["split"], group["mode"], group["condition_id"]
        )
        lines.extend(
            [
                rf"\subsection*{{{_latex_escape(heading)}}}",
                rf"Data version: \texttt{{{_latex_escape(group['data_version'])}}}\\",
                rf"Corpus version: \texttt{{{_latex_escape(group['corpus_version'])}}}\\",
                f"Records: {group['total_records']}",
                r"\begin{longtable}{p{0.43\textwidth}rrrr}",
                r"\toprule",
                r"Metric & Numerator & Denominator & Value & Excluded \\",
                r"\midrule",
                r"\endhead",
                *_latex_metric_rows(group["metrics"]),
                r"\bottomrule",
                r"\end{longtable}",
            ]
        )
    lines.extend(
        [
            r"\section*{Generated chart files}",
            r"The reporting command also writes deterministic SVG charts:",
            r"\begin{itemize}",
            r"\item \texttt{answer\_citation\_metrics.svg}",
            r"\item \texttt{answer\_outcomes.svg}",
            r"\item \texttt{failure\_labels.svg}",
            r"\end{itemize}",
            r"\end{document}",
            "",
        ]
    )
    return "\n".join(lines)


def write_answer_citation_reports(
    result: Mapping[str, Any], output_dir: Path
) -> dict[str, Path]:
    """Write machine-readable, narrative, chart, and LaTeX artifacts."""

    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "summary": output_dir / "answer_citation_summary.json",
        "per_question": output_dir / "answer_citation_scores.jsonl",
        "csv": output_dir / "answer_citation_summary.csv",
        "markdown": output_dir / "answer_citation_report.md",
        "latex": output_dir / "answer_citation_report.tex",
        "metrics_chart": output_dir / "answer_citation_metrics.svg",
        "outcomes_chart": output_dir / "answer_outcomes.svg",
        "failures_chart": output_dir / "failure_labels.svg",
        "failures": output_dir / "answer_citation_failures.jsonl",
    }

    summary = {key: value for key, value in result.items() if key != "records"}
    paths["summary"].write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    paths["markdown"].write_text(_markdown(result), encoding="utf-8")
    paths["latex"].write_text(_latex(result), encoding="utf-8", newline="\n")
    paths["metrics_chart"].write_text(
        _metrics_chart(result), encoding="utf-8", newline="\n"
    )
    paths["outcomes_chart"].write_text(
        _counts_chart("Answer outcomes", result["answer_outcome_counts"]),
        encoding="utf-8",
        newline="\n",
    )
    paths["failures_chart"].write_text(
        _counts_chart("Reviewable failure labels", result["failure_label_counts"]),
        encoding="utf-8",
        newline="\n",
    )

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
