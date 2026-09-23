"""Auditable M7 four-condition adapter and M8 comparison reporting."""

from __future__ import annotations

import csv
import hashlib
import html
import json
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cs30.citation import build_evidence_bundle, resolve_and_validate
from cs30.contracts import GeneratedAnswer, RetrievalResult
from cs30.generation.experiment import ConditionExperimentCase, load_condition_cases
from cs30.generation.prompt import PromptBuilder

from .answer_metrics import AnswerCitationScorer
from .mapping import GoldChunkMapping, QuestionChunkMapping
from .models import (
    AbstentionCause,
    ErrorStage,
    EvaluationRunError,
    EvaluationRunResult,
    EvaluationSplit,
    ExecutionMode,
    GoldSample,
    RunStatus,
)

_CONDITIONS = (
    "P0R0_plain",
    "P1R0_prompt_only",
    "P0R1_reranking_only",
    "P1R1_combined",
)

_COMPARISON_METRICS = (
    "answer_choice_accuracy_all",
    "answer_choice_accuracy_answered",
    "abstention_accuracy",
    "citation_validity",
    "gold_evidence_citation_coverage",
    "repair_rate",
    "technical_failure_rate",
    "provider_failure_rate",
)


@dataclass(frozen=True)
class AdaptedConditionRun:
    """One M7 row converted into M8's frozen evaluation contract."""

    case_id: str
    student_level: str
    condition_id: str
    provider_failure_observed: bool
    run: EvaluationRunResult


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: {exc}") from exc
            if not isinstance(payload, dict):
                raise ValueError(f"{path}:{line_number}: expected a JSON object")
            rows.append(payload)
    if not rows:
        raise ValueError(f"{path}: four-condition result file is empty")
    return rows


def _reorder_retrieval(
    case: ConditionExperimentCase,
    output_candidate_ids: Sequence[str],
) -> RetrievalResult:
    input_ids = [hit.chunk_id for hit in case.retrieval.hits]
    output_ids = [str(chunk_id) for chunk_id in output_candidate_ids]
    if len(output_ids) != len(set(output_ids)):
        raise ValueError(f"{case.case_id}: output candidate IDs must be unique")
    if set(output_ids) != set(input_ids):
        raise ValueError(
            f"{case.case_id}: output candidates must be a permutation of input candidates"
        )
    by_id = {hit.chunk_id: hit for hit in case.retrieval.hits}
    hits = [
        by_id[chunk_id].model_copy(update={"rank": rank})
        for rank, chunk_id in enumerate(output_ids, start=1)
    ]
    return case.retrieval.model_copy(update={"hits": hits})


def _attempt_records(trace: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    attempts = trace.get("attempt_records", [])
    if not isinstance(attempts, list) or any(not isinstance(item, dict) for item in attempts):
        raise ValueError("generation_trace.attempt_records must be a list of objects")
    return attempts


def _model_call_count(trace: Mapping[str, Any]) -> int:
    attempts = _attempt_records(trace)
    if attempts:
        return len(attempts)
    value = trace.get("generation_attempts", 0)
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("generation_trace.generation_attempts must be an integer") from exc


def _technical_error(
    row: Mapping[str, Any], trace: Mapping[str, Any]
) -> tuple[RunStatus, EvaluationRunError]:
    attempts = _attempt_records(trace)
    last = attempts[-1] if attempts else {}
    last_status = last.get("status")
    if last_status == "rejected":
        status = RunStatus.PARSE_ERROR
        stage = ErrorStage.PARSING
    else:
        status = RunStatus.GENERATION_ERROR
        stage = ErrorStage.GENERATION
    outer = row.get("error")
    outer_error = outer if isinstance(outer, dict) else {}
    error_type = str(last.get("failure_type") or outer_error.get("type") or "GenerationError")
    message = str(last.get("error") or outer_error.get("message") or "generation failed")
    return status, EvaluationRunError(stage=stage, error_type=error_type, message=message)


def _adapt_row(
    row: Mapping[str, Any],
    case: ConditionExperimentCase,
    *,
    experiment_run_id: str,
) -> AdaptedConditionRun:
    condition_id = str(row.get("condition_id", ""))
    if condition_id not in _CONDITIONS:
        raise ValueError(f"{case.case_id}: unknown condition_id {condition_id!r}")
    if row.get("question_id") != case.question_id or row.get("case_id") != case.case_id:
        raise ValueError(f"{case.case_id}: result identity does not match its source case")
    if row.get("split") != case.split:
        raise ValueError(f"{case.case_id}: result split does not match its source case")
    expected_profile = case.profile.model_dump(mode="json")
    if row.get("profile_snapshot") != expected_profile:
        raise ValueError(f"{case.case_id}: result profile does not match its source case")

    input_ids = [hit.chunk_id for hit in case.retrieval.hits]
    if row.get("input_candidate_ids") != input_ids:
        raise ValueError(f"{case.case_id}: saved input candidates differ from source retrieval")
    output_ids = row.get("output_candidate_ids")
    if not isinstance(output_ids, list):
        raise ValueError(f"{case.case_id}: output_candidate_ids must be a list")
    prepared = _reorder_retrieval(case, output_ids)
    bundle = build_evidence_bundle(
        prepared,
        run_provenance={
            "member7_run_id": experiment_run_id,
            "case_id": case.case_id,
            "condition_id": condition_id,
        },
    )

    trace = row.get("generation_trace")
    if not isinstance(trace, dict):
        raise ValueError(f"{case.case_id}/{condition_id}: missing generation_trace")
    trace_ids = trace.get("prompt_evidence_chunk_ids")
    if trace_ids != output_ids:
        raise ValueError(
            f"{case.case_id}/{condition_id}: prompt evidence IDs do not match saved output order"
        )
    personalise = row.get("prompt_personalisation")
    if not isinstance(personalise, bool):
        raise ValueError(f"{case.case_id}/{condition_id}: invalid prompt_personalisation")
    prompt = PromptBuilder().build(
        case.question,
        case.profile,
        bundle,
        personalise=personalise,
    )
    prompt_sha256 = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    if trace.get("prompt_sha256") != prompt_sha256:
        raise ValueError(
            f"{case.case_id}/{condition_id}: reconstructed prompt hash does not match M7 trace"
        )

    attempts = _attempt_records(trace)
    provider_failure_observed = any(
        attempt.get("status") == "provider_failed" for attempt in attempts
    )
    raw_output = trace.get("raw_model_output")
    repaired_output = trace.get("repaired_model_output")
    model_call_count = _model_call_count(trace)
    run_status = row.get("status")
    answer = None
    validation = None
    error = None
    abstention_cause = None
    if run_status == "completed":
        answer = GeneratedAnswer.model_validate(row.get("answer"))
        validation = resolve_and_validate(answer, bundle)
        if answer.abstained:
            status = RunStatus.ABSTAINED
            abstention_cause = AbstentionCause.MODEL_ABSTAINED_WITH_EVIDENCE
        else:
            status = RunStatus.ANSWERED
    elif run_status == "failed":
        status, error = _technical_error(row, trace)
    else:
        raise ValueError(f"{case.case_id}/{condition_id}: invalid row status {run_status!r}")

    run = EvaluationRunResult(
        run_id=f"{experiment_run_id}:{case.case_id}:{condition_id}",
        question_id=case.question_id,
        condition_id=condition_id,
        execution_mode=ExecutionMode.RETRIEVAL_AND_GENERATION,
        status=status,
        retrieval=case.retrieval,
        evidence_sent_to_model=bundle,
        raw_model_output=raw_output,
        repaired_model_output=repaired_output,
        final_answer=answer,
        citation_validation=validation,
        error=error,
        model_call_count=model_call_count,
        abstention_cause=abstention_cause,
        prompt_evidence_chunk_ids=list(output_ids),
        prompt_sha256=prompt_sha256,
    )
    return AdaptedConditionRun(
        case_id=case.case_id,
        student_level=case.profile.level.value,
        condition_id=condition_id,
        provider_failure_observed=provider_failure_observed,
        run=run,
    )


def adapt_four_condition_results(
    cases_path: Path,
    results_path: Path,
    manifest_path: Path,
) -> tuple[dict[str, Any], list[AdaptedConditionRun]]:
    """Join M7 results to immutable cases and verify the exact original prompt."""

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (
        not isinstance(manifest, dict)
        or manifest.get("result_type") != "member7_four_condition_run"
    ):
        raise ValueError(f"{manifest_path}: not a Member 7 four-condition manifest")
    experiment_run_id = str(manifest.get("run_id", ""))
    if not experiment_run_id:
        raise ValueError(f"{manifest_path}: missing run_id")
    expected_cases_hash = manifest.get("cases_sha256")
    actual_cases_hash = _sha256(cases_path)
    if expected_cases_hash is not None and expected_cases_hash != actual_cases_hash:
        raise ValueError("case file SHA-256 does not match the M7 run manifest")
    if manifest.get("reportable") is True and expected_cases_hash is None:
        raise ValueError("reportable four-condition input requires cases_sha256")

    cases = load_condition_cases(cases_path)
    cases_by_id = {case.case_id: case for case in cases}
    rows = _load_jsonl(results_path)
    expected_keys = {
        (case.case_id, condition_id) for case in cases for condition_id in _CONDITIONS
    }
    observed_keys: set[tuple[str, str]] = set()
    adapted: list[AdaptedConditionRun] = []
    for row in rows:
        if row.get("run_id") != experiment_run_id:
            raise ValueError("four-condition row run_id does not match its manifest")
        key = (str(row.get("case_id", "")), str(row.get("condition_id", "")))
        if key in observed_keys:
            raise ValueError(f"duplicate four-condition row: {key}")
        observed_keys.add(key)
        case = cases_by_id.get(key[0])
        if case is None:
            raise ValueError(f"four-condition row references unknown case_id {key[0]!r}")
        adapted.append(_adapt_row(row, case, experiment_run_id=experiment_run_id))
    if observed_keys != expected_keys:
        missing = sorted(expected_keys - observed_keys)
        extra = sorted(observed_keys - expected_keys)
        raise ValueError(f"four-condition matrix mismatch; missing={missing}, extra={extra}")
    if manifest.get("row_count") != len(rows):
        raise ValueError("four-condition row count does not match its manifest")
    return manifest, adapted


def score_four_condition_results(
    manifest: Mapping[str, Any],
    adapted: Sequence[AdaptedConditionRun],
    gold_samples: Sequence[GoldSample],
    mappings: GoldChunkMapping | Mapping[str, QuestionChunkMapping],
) -> dict[str, Any]:
    """Score every split/level/condition bucket without mixing denominators."""

    scoring_mode = "reportable" if manifest.get("reportable") is True else "development"
    buckets: dict[tuple[str, str, str], list[AdaptedConditionRun]] = defaultdict(list)
    for item in adapted:
        gold = next(
            (
                sample
                for sample in gold_samples
                if sample.question_id == item.run.question_id
            ),
            None,
        )
        if gold is None:
            split = "missing_gold"
        else:
            split = gold.split.value
        buckets[(split, item.student_level, item.condition_id)].append(item)

    groups: list[dict[str, Any]] = []
    all_records: list[dict[str, Any]] = []
    for (split, level, condition_id), items in sorted(buckets.items()):
        expected_split = None if split == "missing_gold" else EvaluationSplit(split)
        score = AnswerCitationScorer(
            mappings,
            expected_split=expected_split,
            expected_condition=condition_id,
        ).score(
            gold_samples,
            [item.run for item in items],
            mode=scoring_mode,
        )
        by_question = {item.run.question_id: item for item in items}
        records = []
        for record in score.pop("records"):
            item = by_question[record["question_id"]]
            record = {
                **record,
                "case_id": item.case_id,
                "student_level": level,
                "provider_failure_observed": item.provider_failure_observed,
            }
            records.append(record)
            all_records.append(record)
        provider_observed = sum(item.provider_failure_observed for item in items)
        groups.append(
            {
                "split": split,
                "student_level": level,
                "condition_id": condition_id,
                "provider_failure_observed_count": provider_observed,
                "provider_failure_observed_rate": provider_observed / len(items),
                **score,
                "records": records,
            }
        )

    by_scope = defaultdict(dict)
    for group in groups:
        by_scope[(group["split"], group["student_level"])][group["condition_id"]] = group
    comparisons = []
    for (split, level), condition_groups in sorted(by_scope.items()):
        if set(condition_groups) != set(_CONDITIONS):
            raise ValueError(f"incomplete four-condition report scope: {split}/{level}")
        for metric in _COMPARISON_METRICS:
            values = {
                condition: condition_groups[condition]["metrics"][metric]["value"]
                for condition in _CONDITIONS
            }
            baseline = values[_CONDITIONS[0]]
            comparisons.append(
                {
                    "split": split,
                    "student_level": level,
                    "metric": metric,
                    "values": values,
                    "delta_vs_plain": {
                        condition: (
                            None
                            if baseline is None or value is None
                            else value - baseline
                        )
                        for condition, value in values.items()
                    },
                }
            )
    return {
        "schema_version": "1.0",
        "source_type": "member7_four_condition_run",
        "source_run_id": manifest["run_id"],
        "scoring_mode": scoring_mode,
        "reportable": scoring_mode == "reportable",
        "row_count": len(adapted),
        "case_count": len({item.case_id for item in adapted}),
        "conditions": list(_CONDITIONS),
        "groups": groups,
        "comparisons": comparisons,
        "records": all_records,
    }


def _display(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.4f}"


def _latex_escape(value: object) -> str:
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
    }
    return "".join(replacements.get(char, char) for char in str(value))


def _markdown(result: Mapping[str, Any]) -> str:
    status = "REPORTABLE" if result["reportable"] else "DEVELOPMENT / NOT FOR FORMAL CLAIMS"
    lines = [
        "# Four-condition evaluation report",
        "",
        f"Report status: **{status}**",
        "",
        f"Source run: `{result['source_run_id']}`",
        "",
        f"Cases: {result['case_count']}; rows: {result['row_count']}",
        "",
        "Every row was joined to its immutable source case and accepted only after the "
        "reconstructed prompt SHA-256 matched M7's saved generation trace.",
        "",
        "## Four-condition comparison",
        "",
        "| Split | Level | Metric | Plain | Prompt only | Reranking only | Combined |",
        "|---|---|---|---:|---:|---:|---:|",
    ]
    for row in result["comparisons"]:
        values = row["values"]
        lines.append(
            "| {} | {} | {} | {} | {} | {} | {} |".format(
                row["split"],
                row["student_level"],
                row["metric"],
                *(_display(values[condition]) for condition in _CONDITIONS),
            )
        )
    lines.extend(
        [
            "",
            "Rates use explicit per-scope denominators. Technical failures are not "
            "treated as abstentions, and provider failures remain separately visible.",
            "",
        ]
    )
    return "\n".join(lines)


def _latex(result: Mapping[str, Any]) -> str:
    status = "REPORTABLE" if result["reportable"] else "DEVELOPMENT / NOT FOR FORMAL CLAIMS"
    lines = [
        r"\documentclass[10pt]{article}",
        r"\usepackage[margin=1.6cm,landscape]{geometry}",
        r"\usepackage{booktabs}",
        r"\usepackage{longtable}",
        r"\begin{document}",
        r"\section*{Four-condition evaluation report}",
        rf"\textbf{{{_latex_escape(status)}}}\\",
        rf"Source run: \texttt{{{_latex_escape(result['source_run_id'])}}}\\",
        rf"Cases: {result['case_count']}; rows: {result['row_count']}\\",
        (
            "Every row was joined to its immutable source case and accepted only after "
            "the reconstructed prompt SHA-256 matched the saved M7 trace."
        ),
        r"\begin{longtable}{lllrrrr}",
        r"\toprule",
        r"Split & Level & Metric & Plain & Prompt & Rerank & Combined \\",
        r"\midrule",
        r"\endhead",
    ]
    for row in result["comparisons"]:
        values = row["values"]
        lines.append(
            "{} & {} & {} & {} & {} & {} & {} \\\\".format(
                _latex_escape(row["split"]),
                _latex_escape(row["student_level"]),
                _latex_escape(row["metric"]),
                *(_latex_escape(_display(values[condition])) for condition in _CONDITIONS),
            )
        )
    lines.extend([r"\bottomrule", r"\end{longtable}", r"\end{document}", ""])
    return "\n".join(lines)


def _svg(result: Mapping[str, Any]) -> str:
    rows = list(result["comparisons"])
    width = 1180
    row_height = 54
    height = 120 + max(1, len(rows)) * row_height
    bar_x = 390
    bar_width = 650
    colors = ("#6b7280", "#2563eb", "#f59e0b", "#10b981")
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-label="Four-condition comparison">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        '<text x="20" y="30" font-family="Arial" font-size="20" font-weight="700" '
        'fill="#111827">Four-condition comparison</text>',
    ]
    for index, (condition, color) in enumerate(zip(_CONDITIONS, colors, strict=True)):
        x = 20 + index * 270
        lines.append(f'<rect x="{x}" y="48" width="14" height="14" fill="{color}"/>')
        lines.append(
            f'<text x="{x + 20}" y="60" font-family="Arial" font-size="12" '
            f'fill="#374151">{html.escape(condition)}</text>'
        )
    for row_index, row in enumerate(rows):
        y = 92 + row_index * row_height
        label = f"{row['split']} / {row['student_level']} / {row['metric']}"
        lines.append(
            f'<text x="20" y="{y + 18}" font-family="Arial" font-size="12" '
            f'fill="#111827">{html.escape(label)}</text>'
        )
        for condition_index, (condition, color) in enumerate(
            zip(_CONDITIONS, colors, strict=True)
        ):
            value = row["values"][condition]
            bar_y = y + condition_index * 7
            filled = 0 if value is None else max(0.0, min(float(value), 1.0)) * bar_width
            lines.append(
                f'<rect x="{bar_x}" y="{bar_y}" width="{bar_width}" height="5" '
                'fill="#e5e7eb"/>'
            )
            if filled:
                lines.append(
                    f'<rect x="{bar_x}" y="{bar_y}" width="{filled:.2f}" height="5" '
                    f'fill="{color}"/>'
                )
            lines.append(
                f'<text x="{bar_x + bar_width + 10}" y="{bar_y + 6}" '
                f'font-family="Arial" font-size="10" fill="#111827">{_display(value)}</text>'
            )
    lines.append("</svg>")
    return "\n".join(lines) + "\n"


def write_four_condition_reports(
    result: Mapping[str, Any],
    adapted: Sequence[AdaptedConditionRun],
    output_dir: Path,
) -> dict[str, Path]:
    """Write the complete machine-readable and narrative comparison package."""

    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "summary": output_dir / "four_condition_summary.json",
        "comparison_csv": output_dir / "four_condition_comparison.csv",
        "markdown": output_dir / "four_condition_report.md",
        "latex": output_dir / "four_condition_report.tex",
        "chart": output_dir / "four_condition_comparison.svg",
        "evaluation_runs": output_dir / "evaluation_run_results_v0_2.jsonl",
        "failures": output_dir / "four_condition_failures.jsonl",
    }
    summary = {key: value for key, value in result.items() if key != "records"}
    summary["groups"] = [
        {key: value for key, value in group.items() if key != "records"}
        for group in result["groups"]
    ]
    paths["summary"].write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    paths["markdown"].write_text(_markdown(result), encoding="utf-8", newline="\n")
    paths["latex"].write_text(_latex(result), encoding="utf-8", newline="\n")
    paths["chart"].write_text(_svg(result), encoding="utf-8", newline="\n")
    with paths["comparison_csv"].open("w", encoding="utf-8", newline="") as stream:
        fieldnames = [
            "split",
            "student_level",
            "metric",
            *_CONDITIONS,
            *(f"delta_vs_plain.{condition}" for condition in _CONDITIONS),
        ]
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        for row in result["comparisons"]:
            writer.writerow(
                {
                    "split": row["split"],
                    "student_level": row["student_level"],
                    "metric": row["metric"],
                    **row["values"],
                    **{
                        f"delta_vs_plain.{condition}": value
                        for condition, value in row["delta_vs_plain"].items()
                    },
                }
            )
    with paths["evaluation_runs"].open("w", encoding="utf-8", newline="\n") as stream:
        for item in adapted:
            stream.write(item.run.model_dump_json() + "\n")
    with paths["failures"].open("w", encoding="utf-8", newline="\n") as stream:
        for record in result["records"]:
            if record["failure_labels"] or record["provider_failure_observed"]:
                stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    return paths
