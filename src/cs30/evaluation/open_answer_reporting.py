"""Coverage-aware reports and auditable human review for open-answer scores."""

from __future__ import annotations

import csv
import json
import random
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path

from .open_answer_models import HumanDecision, HumanRating, OpenAnswerScore


def _metric(numerator: float, denominator: int, unresolved: int = 0) -> dict:
    return {
        "numerator": numerator,
        "denominator": denominator,
        "value": numerator / denominator if denominator and not unresolved else None,
        "lower_bound": numerator / denominator if denominator else None,
        "upper_bound": (numerator + unresolved) / denominator if denominator else None,
        "unresolved": unresolved,
    }


def summarize_open_answers(records: Sequence[OpenAnswerScore]) -> dict:
    eligible = [r for r in records if r.score_status != "excluded"]
    known = [r for r in eligible if r.score_status == "scored"]
    unresolved = len(eligible) - len(known)
    answered = [r for r in eligible if r.run_status == "answered"]
    answered_known = [r for r in answered if r.score_status == "scored"]
    correct = sum(r.score == 2 for r in known)
    credit = sum(r.score / 2 for r in known)
    return {
        "total_expected": len(records),
        "eligible": len(eligible),
        "excluded_reasons": dict(
            Counter(r.reason for r in records if r.score_status == "excluded")
        ),
        "score_status_counts": dict(Counter(r.score_status for r in records)),
        "scoring_source_counts": dict(Counter(r.scoring_source for r in records)),
        "score_counts": {str(score): sum(r.score == score for r in known) for score in (0, 1, 2)},
        "open_answer_full_correct_rate_e2e": _metric(correct, len(eligible), unresolved),
        "open_answer_mean_credit_e2e": _metric(credit, len(eligible), unresolved),
        "open_answer_full_correct_rate_answered": _metric(
            sum(r.score == 2 for r in answered_known),
            len(answered),
            len(answered) - len(answered_known),
        ),
        "scoring_coverage": _metric(len(known), len(eligible)),
        "technical_failure_rate": _metric(
            sum(
                r.run_status
                in {"retrieval_error", "generation_error", "parse_error", "output_truncated"}
                for r in eligible
            ),
            len(eligible),
        ),
        "missing_run_count": sum(r.run_status == "missing" for r in records),
        "cache_hit_count": sum(r.cache_hit for r in records),
        "judge_calls_this_run": sum(r.judge_calls_this_run for r in records),
    }


def build_open_answer_report(records: Sequence[OpenAnswerScore], provenance: Mapping) -> dict:
    if len({r.run_id for r in records}) != len(records):
        raise ValueError("duplicate score run IDs")
    groups = defaultdict(list)
    for record in records:
        key = (
            record.split,
            record.student_level.value,
            record.condition_id,
            record.generator_model,
        )
        groups[key].append(record)
    return {
        "schema_version": "0.1",
        "result_type": "open_answer_correctness_report",
        "reportable": False,
        "status": "DEVELOPMENT / RUBRIC AND JUDGE REQUIRE HUMAN VALIDATION",
        "limitations": [
            "Automatic scores are reference-based assessments, not human ground truth.",
            "No formal evaluation approval is inferred from a successful run or review record ID.",
            "Unresolved assessments keep their expected denominator and suppress point estimates.",
            "Factual correctness, citation support and level adaptation remain separate metrics.",
            "Human-subset calibration statistics do not establish population-level accuracy.",
        ],
        "score_regime": "human_reviewed_hybrid"
        if any(r.scoring_source == "human" for r in records)
        else "automatic_or_pending",
        "by_scoring_source": {
            source: summarize_open_answers([r for r in records if r.scoring_source == source])
            for source in sorted({r.scoring_source for r in records})
        },
        "provenance": dict(provenance),
        "overall": summarize_open_answers(records),
        "groups": [
            {
                "split": key[0],
                "student_level": key[1],
                "condition_id": key[2],
                "generator_model": key[3],
                **summarize_open_answers(group),
            }
            for key, group in sorted(groups.items(), key=lambda item: str(item[0]))
        ],
    }


def write_open_answer_reports(
    records: Sequence[OpenAnswerScore], output_directory: Path, provenance: Mapping
) -> dict:
    report = build_open_answer_report(records, provenance)
    output_directory.mkdir(parents=True, exist_ok=False)

    def dump(path: str, value: object) -> None:
        (output_directory / path).write_text(
            json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
            encoding="utf-8",
        )

    def jsonl(path: str, items: Sequence[OpenAnswerScore]) -> None:
        (output_directory / path).write_text(
            "".join(item.model_dump_json() + "\n" for item in items), encoding="utf-8"
        )

    dump("open_answer_summary.json", report)
    dump("run_manifest.json", {**dict(provenance), "schema_version": "0.1", "reportable": False})
    jsonl("open_answer_scores.jsonl", records)
    queue = [r for r in records if r.score_status in {"needs_review", "judge_error", "missing_run"}]
    jsonl("open_answer_review_queue.jsonl", queue)
    columns = [
        "split",
        "student_level",
        "condition_id",
        "generator_model",
        "eligible",
        "full_correct",
        "denominator",
        "unresolved",
        "value",
        "lower_bound",
        "upper_bound",
    ]
    with (output_directory / "open_answer_summary.csv").open(
        "w", newline="", encoding="utf-8"
    ) as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        for group in report["groups"]:
            metric = group["open_answer_full_correct_rate_e2e"]
            writer.writerow(
                {
                    **{k: group[k] for k in columns[:5]},
                    "full_correct": metric["numerator"],
                    **{k: metric[k] for k in columns[6:]},
                }
            )
    overall = report["overall"]
    metric = overall["open_answer_full_correct_rate_e2e"]
    lines = [
        "# Open-answer correctness report",
        "",
        report["status"],
        "",
        f"Expected runs: {overall['total_expected']}; eligible: {overall['eligible']}.",
        "",
        f"Full-correct rate: {metric['value']}; bounds: "
        f"[{metric['lower_bound']}, {metric['upper_bound']}]; "
        f"unresolved: {metric['unresolved']}.",
        "",
        "Partial credit is reported separately and is not strict correctness.",
        "",
        "| Split | Level | Condition | Model | Correct / eligible | Pending |",
        "|---|---|---|---|---:|---:|",
    ]
    for group in report["groups"]:
        m = group["open_answer_full_correct_rate_e2e"]
        cells = [
            group["split"],
            group["student_level"],
            group["condition_id"],
            group["generator_model"],
            f"{m['numerator']} / {m['denominator']}",
            m["unresolved"],
        ]
        lines.append(
            "| " + " | ".join(str(v).replace("|", "\\|").replace("\n", " ") for v in cells) + " |"
        )
    lines += ["", "## Limitations", "", *[f"- {item}" for item in report["limitations"]]]
    (output_directory / "open_answer_report.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
    return report


def _check_rating_identity(rating: HumanRating, score: OpenAnswerScore) -> None:
    if rating.answer_sha256 != score.answer_sha256 or rating.rubric_sha256 != score.rubric_sha256:
        raise ValueError("human rating must match the exact saved answer and rubric hashes")
    if score.run_status != "answered" or score.score_status == "excluded":
        raise ValueError("human correctness assessment requires an eligible original answer")


def apply_human_reviews(
    records: Sequence[OpenAnswerScore], decisions: Sequence[HumanDecision]
) -> list[OpenAnswerScore]:
    by_id = {r.run_id: r for r in records}
    if len(by_id) != len(records) or len({d.run_id for d in decisions}) != len(decisions):
        raise ValueError("review and score run IDs must be unique")
    updates = {}
    for decision in decisions:
        if decision.run_id not in by_id:
            raise ValueError("human decision references an unknown run")
        previous = by_id[decision.run_id]
        _check_rating_identity(decision, previous)
        if previous.scoring_source == "human":
            raise ValueError(
                "do not overwrite a human decision; create a separately versioned review"
            )
        payload = previous.model_dump(mode="json")
        payload.update(
            score=decision.score,
            score_status="scored",
            scoring_source="human",
            reason=decision.note,
            review_record_id=decision.review_record_id,
            human_rater_id=decision.rater_id,
            judge_calls_this_run=0,
        )
        updates[decision.run_id] = OpenAnswerScore.model_validate(payload)
    return [
        updates.get(r.run_id, r.model_copy(update={"judge_calls_this_run": 0})) for r in records
    ]


def calibration_report(
    records: Sequence[OpenAnswerScore],
    ratings: Sequence[HumanRating],
    adjudications: Sequence[HumanDecision] = (),
) -> dict:
    by_id = {r.run_id: r for r in records}
    if len(by_id) != len(records) or not ratings:
        raise ValueError("calibration requires unique scores and actual human ratings")
    paired = defaultdict(dict)
    for rating in ratings:
        if rating.run_id not in by_id:
            raise ValueError("rating references an unknown run")
        record = by_id[rating.run_id]
        _check_rating_identity(rating, record)
        if record.score_status != "scored" or record.scoring_source not in {"judge", "rule"}:
            raise ValueError("calibration requires an unchanged automatic prediction")
        if rating.rater_id in paired[rating.run_id]:
            raise ValueError("duplicate human rater for a run")
        paired[rating.run_id][rating.rater_id] = rating.score
    raters = sorted({r.rater_id for r in ratings})
    if len(raters) != 2 or any(set(group) != set(raters) for group in paired.values()):
        raise ValueError(
            "calibration requires the same two independent raters for every sampled run"
        )
    decisions = {d.run_id: d for d in adjudications}
    if len(decisions) != len(adjudications) or set(decisions) - paired.keys():
        raise ValueError("duplicate or unknown adjudication IDs")
    configurations = {
        by_id[key].judge_config_sha256 for key in paired if by_id[key].scoring_source == "judge"
    }
    if len(configurations) > 1:
        raise ValueError("calibration cannot mix judge configurations")
    rows_by_question = defaultdict(list)
    for run_id, group in paired.items():
        a, b = (group[rater] for rater in raters)
        decision = decisions.get(run_id)
        if a != b and decision is None:
            raise ValueError("human disagreement requires explicit adjudication")
        if decision is not None:
            _check_rating_identity(decision, by_id[run_id])
        target = decision.score if decision else a
        rows_by_question[by_id[run_id].question_id].append((a, b, target, by_id[run_id].score))
    rows = [row for group in rows_by_question.values() for row in group]
    return {
        "schema_version": "0.1",
        "reportable": False,
        "scope": "sample diagnostic; not a population estimate or automatic formal approval",
        "sample_count": len(rows),
        "question_count": len(rows_by_question),
        "raters": raters,
        **_calibration_statistics(rows),
        "adjudication_count": len(decisions),
        "judge_config_sha256": next(iter(configurations)) if configurations else None,
        "sample_split_counts": dict(Counter(by_id[key].split for key in paired)),
        "uncertainty": _calibration_uncertainty(rows_by_question),
    }


def _calibration_statistics(rows: Sequence[tuple[int, int, int, int]]) -> dict:
    n = len(rows)
    observed = sum(1 - abs(a - b) / 2 for a, b, _, _ in rows) / n
    a_counts = Counter(a for a, _, _, _ in rows)
    b_counts = Counter(b for _, b, _, _ in rows)
    expected = sum(
        (1 - abs(a - b) / 2) * a_counts[a] * b_counts[b] / n**2 for a in range(3) for b in range(3)
    )
    matrix = [[0] * 3 for _ in range(3)]
    for _, _, target, predicted in rows:
        matrix[target][predicted] += 1
    predicted_correct = sum(row[2] for row in matrix)
    human_correct = sum(matrix[2])
    return {
        "raw_human_agreement": sum(a == b for a, b, _, _ in rows) / n,
        "linear_weighted_cohen_kappa": (observed - expected) / (1 - expected)
        if expected < 1
        else None,
        "confusion_matrix_human_rows_prediction_columns": matrix,
        "prediction_human_agreement": sum(matrix[i][i] for i in range(3)) / n,
        "full_correct_precision": matrix[2][2] / predicted_correct if predicted_correct else None,
        "full_correct_recall": matrix[2][2] / human_correct if human_correct else None,
    }


def _calibration_uncertainty(groups: Mapping[str, list]) -> dict:
    keys = sorted(groups)
    names = [
        "raw_human_agreement",
        "linear_weighted_cohen_kappa",
        "prediction_human_agreement",
        "full_correct_precision",
        "full_correct_recall",
    ]
    if len(keys) < 2:
        return {
            "method": "question_cluster_bootstrap",
            "intervals": None,
            "reason": "fewer than two independent question clusters",
        }
    rng = random.Random(0)
    repetitions = 1000
    samples = {name: [] for name in names}
    for _ in range(repetitions):
        rows = [row for key in rng.choices(keys, k=len(keys)) for row in groups[key]]
        values = _calibration_statistics(rows)
        for name in names:
            if values[name] is not None:
                samples[name].append(values[name])

    def quantile(values: list[float], fraction: float) -> float:
        values = sorted(values)
        position = (len(values) - 1) * fraction
        index = int(position)
        return values[index] + (values[min(index + 1, len(values) - 1)] - values[index]) * (
            position - index
        )

    return {
        "method": "question_cluster_bootstrap",
        "seed": 0,
        "resamples": repetitions,
        "confidence_level": 0.95,
        "intervals": {
            name: {
                "lower": quantile(values, 0.025) if len(values) == repetitions else None,
                "upper": quantile(values, 0.975) if len(values) == repetitions else None,
                "defined_resamples": len(values),
            }
            for name, values in samples.items()
        },
        "note": "diagnostic intervals; few clusters or undefined resamples limit interpretation",
    }
