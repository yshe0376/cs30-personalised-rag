"""Cross-run reporting for textbooks, levels, lambda, and provenance."""

from __future__ import annotations

import csv
import hashlib
import json
import random
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .extension_models import (
    BlindedAnswerKey,
    BlindRatingSubmissionManifest,
    ExpectedExperimentManifest,
    ExperimentCondition,
    LevelAdaptationRating,
    LevelAdaptationRubricManifest,
    RoleLabelProvenanceManifest,
    ScoreArtifactProvenanceManifest,
)
from .io import load_run_results
from .manifest import RunManifest, assert_manifests_comparable
from .mapping import GoldChunkMapping
from .models import EvaluationRunResult, ExecutionMode, GoldSample, RunStatus

BOOLEAN_METRICS = {
    "answer_accuracy": "answer_correct",
    "citation_validity": "citation_valid",
    "gold_evidence_citation_coverage": "gold_evidence_covered",
    "abstention_accuracy": "abstention_correct",
    "raw_json_validity": "raw_json_valid",
    "raw_schema_validity": "raw_schema_valid",
    "repaired_json_validity": "repaired_json_valid",
    "repaired_schema_validity": "repaired_schema_valid",
}

GROUP_IDENTITY_FIELDS = (
    "mode",
    "execution_mode",
    "data_version",
    "split",
    "corpus_version",
    "chunk_version",
    "mapping_version",
    "index_version",
    "textbook_id",
    "student_level",
    "comparison_id",
    "condition_id",
    "lambda_weight",
    "lambda_status",
)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise FileNotFoundError(path)
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSON: {exc}") from exc
            if not isinstance(payload, dict):
                raise ValueError(f"{path}:{line_number}: expected a JSON object")
            rows.append(payload)
    return rows


def load_score_records(paths: Sequence[Path]) -> list[dict[str, Any]]:
    """Load existing M8 per-question report artifacts without re-scoring."""

    required = {
        "run_id",
        "question_id",
        "condition_id",
        "execution_mode",
        "mode",
        "data_version",
        "split",
        "corpus_version",
        "status",
        "abstention_cause",
        "gold_answerable",
        "citation_checks",
        "model_call_count",
        "repair_used",
        "answer_outcome",
        "failure_labels",
        *BOOLEAN_METRICS.values(),
    }
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for path in paths:
        for row in _read_jsonl(path):
            missing = sorted(required - row.keys())
            if missing:
                raise ValueError(f"{path}: score record is missing fields: {missing}")
            run_id = str(row["run_id"])
            if run_id in seen:
                raise ValueError(f"duplicate score run_id across inputs: {run_id}")
            try:
                ExecutionMode(str(row["execution_mode"]))
            except ValueError as exc:
                raise ValueError(
                    f"{path}: invalid execution_mode for run {run_id}: "
                    f"{row['execution_mode']!r}"
                ) from exc
            if row["execution_mode"] == ExecutionMode.RETRIEVAL_ONLY.value:
                if row["answer_outcome"] != "not_applicable":
                    raise ValueError(
                        f"{path}: retrieval_only run {run_id} must be not_applicable"
                    )
                contradictions = []
                if row["status"] not in {
                    RunStatus.RETRIEVED.value,
                    RunStatus.RETRIEVAL_ERROR.value,
                }:
                    contradictions.append(f"status={row['status']!r}")
                if row["model_call_count"] != 0:
                    contradictions.append(
                        f"model_call_count={row['model_call_count']!r}"
                    )
                if row["abstention_cause"] is not None:
                    contradictions.append("abstention_cause is present")
                if row["citation_checks"]:
                    contradictions.append("citation_checks are present")
                generation_only_metrics = {
                    name: row[field]
                    for name, field in BOOLEAN_METRICS.items()
                    if row[field] is not None
                }
                if generation_only_metrics:
                    contradictions.append(
                        f"generation metrics are present: {generation_only_metrics}"
                    )
                if row["repair_used"]:
                    contradictions.append("repair_used is true")
                if contradictions:
                    raise ValueError(
                        f"{path}: retrieval_only run {run_id} contains generation-only "
                        "state: " + "; ".join(contradictions)
                    )
            seen.add(run_id)
            records.append(row)
    if not records:
        raise ValueError("at least one per-question score record is required")
    return records


def load_experiment_conditions(path: Path) -> list[ExperimentCondition]:
    try:
        return [ExperimentCondition.model_validate(row) for row in _read_jsonl(path)]
    except ValidationError as exc:
        raise ValueError(f"{path}: invalid experiment context: {exc}") from exc


def load_expected_experiment_manifest(path: Path) -> ExpectedExperimentManifest:
    try:
        return ExpectedExperimentManifest.model_validate_json(
            path.read_text(encoding="utf-8")
        )
    except ValidationError as exc:
        raise ValueError(f"{path}: invalid expected experiment manifest: {exc}") from exc


def _normalise_path(path: Path) -> Path:
    return path.resolve()


def _run_ids_sha256(run_ids: Iterable[str]) -> str:
    payload = json.dumps(
        sorted(run_ids), ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def write_score_artifact_provenance(
    score_path: Path,
    source_runs_path: Path,
    output_path: Path,
) -> Path:
    """Seal a score JSONL to the exact saved run-results file it scores."""

    score_records = load_score_records([score_path])
    source_runs = load_run_results(source_runs_path)
    score_run_ids = {str(record["run_id"]) for record in score_records}
    source_run_ids = {run.run_id for run in source_runs}
    if score_run_ids != source_run_ids:
        raise ValueError(
            "score artifact and source run results have different run IDs: "
            f"missing_from_scores={sorted(source_run_ids - score_run_ids)}, "
            f"missing_from_source={sorted(score_run_ids - source_run_ids)}"
        )
    manifest = ScoreArtifactProvenanceManifest(
        score_file=score_path.name,
        score_sha256=hashlib.sha256(score_path.read_bytes()).hexdigest(),
        source_runs_file=source_runs_path.name,
        source_runs_sha256=hashlib.sha256(source_runs_path.read_bytes()).hexdigest(),
        score_record_count=len(score_records),
        source_run_count=len(source_runs),
        run_ids_sha256=_run_ids_sha256(score_run_ids),
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        manifest.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    return output_path


def _load_score_source_bindings(
    score_paths: Sequence[Path],
    score_source_triples: Sequence[tuple[Path, Path, Path]] | None,
    *,
    allow_incomplete: bool,
) -> dict[str, Any]:
    expected_scores = {_normalise_path(path) for path in score_paths}
    if not score_source_triples:
        if allow_incomplete:
            return {
                "status": "pending",
                "expected_score_count": len(expected_scores),
                "bound_score_count": 0,
                "missing_score_files": sorted(path.name for path in expected_scores),
                "bindings": [],
            }
        raise ValueError(
            "formal evaluation requires one --score-source binding for every "
            "score artifact"
        )

    bound_scores: set[Path] = set()
    seen_manifests: set[Path] = set()
    seen_sources: set[Path] = set()
    audit: list[dict[str, Any]] = []
    for score_path, provenance_path, source_runs_path in score_source_triples:
        resolved_score = _normalise_path(score_path)
        resolved_provenance = _normalise_path(provenance_path)
        resolved_source = _normalise_path(source_runs_path)
        if resolved_score not in expected_scores:
            raise ValueError(
                f"score-source binding references an unknown score artifact: {score_path}"
            )
        if resolved_score in bound_scores:
            raise ValueError(f"duplicate source binding for score artifact: {score_path}")
        if resolved_provenance in seen_manifests:
            raise ValueError(
                f"one score provenance manifest cannot bind multiple files: {provenance_path}"
            )
        if resolved_source in seen_sources:
            raise ValueError(
                f"one source run-results file cannot bind multiple score files: {source_runs_path}"
            )
        if not resolved_provenance.is_file():
            raise FileNotFoundError(resolved_provenance)
        if not resolved_source.is_file():
            raise FileNotFoundError(resolved_source)
        try:
            manifest = ScoreArtifactProvenanceManifest.model_validate_json(
                resolved_provenance.read_text(encoding="utf-8")
            )
        except ValidationError as exc:
            raise ValueError(
                f"{provenance_path}: invalid score provenance manifest: {exc}"
            ) from exc
        checks = {
            "score_file": (manifest.score_file.name, score_path.name),
            "source_runs_file": (manifest.source_runs_file.name, source_runs_path.name),
            "score_sha256": (
                manifest.score_sha256,
                hashlib.sha256(resolved_score.read_bytes()).hexdigest(),
            ),
            "source_runs_sha256": (
                manifest.source_runs_sha256,
                hashlib.sha256(resolved_source.read_bytes()).hexdigest(),
            ),
        }
        mismatches = [
            f"{field}={declared!r} (actual={actual!r})"
            for field, (declared, actual) in checks.items()
            if declared != actual
        ]
        if mismatches:
            raise ValueError(
                f"{provenance_path}: score-source provenance mismatch: "
                + "; ".join(mismatches)
            )
        score_records = load_score_records([resolved_score])
        source_runs = load_run_results(resolved_source)
        score_run_ids = {str(record["run_id"]) for record in score_records}
        source_run_ids = {run.run_id for run in source_runs}
        if score_run_ids != source_run_ids:
            raise ValueError(
                f"{provenance_path}: score/source run-ID coverage mismatch: "
                f"missing_from_scores={sorted(source_run_ids - score_run_ids)}, "
                f"missing_from_source={sorted(score_run_ids - source_run_ids)}"
            )
        count_checks = {
            "score_record_count": (manifest.score_record_count, len(score_records)),
            "source_run_count": (manifest.source_run_count, len(source_runs)),
            "run_ids_sha256": (manifest.run_ids_sha256, _run_ids_sha256(score_run_ids)),
        }
        count_mismatches = [
            f"{field}={declared!r} (actual={actual!r})"
            for field, (declared, actual) in count_checks.items()
            if declared != actual
        ]
        if count_mismatches:
            raise ValueError(
                f"{provenance_path}: score-source coverage mismatch: "
                + "; ".join(count_mismatches)
            )
        bound_scores.add(resolved_score)
        seen_manifests.add(resolved_provenance)
        seen_sources.add(resolved_source)
        audit.append(
            {
                "score_file": score_path.name,
                "score_sha256": manifest.score_sha256,
                "provenance_file": provenance_path.name,
                "provenance_sha256": hashlib.sha256(
                    resolved_provenance.read_bytes()
                ).hexdigest(),
                "source_runs_file": source_runs_path.name,
                "source_runs_sha256": manifest.source_runs_sha256,
                "run_count": manifest.source_run_count,
                "run_ids_sha256": manifest.run_ids_sha256,
            }
        )

    missing_paths = expected_scores - bound_scores
    if missing_paths and not allow_incomplete:
        raise ValueError(
            "formal evaluation is missing score-source bindings for: "
            + ", ".join(sorted(str(path) for path in missing_paths))
        )
    return {
        "status": "complete" if not missing_paths else "incomplete",
        "expected_score_count": len(expected_scores),
        "bound_score_count": len(bound_scores),
        "missing_score_files": sorted(path.name for path in missing_paths),
        "bindings": audit,
    }


def _load_manifest_bindings(
    score_paths: Sequence[Path],
    score_manifest_pairs: Sequence[tuple[Path, Path]] | None,
    *,
    allow_incomplete: bool,
) -> tuple[dict[Path, RunManifest], dict[str, Any]]:
    expected_scores = {_normalise_path(path) for path in score_paths}
    if not score_manifest_pairs:
        if allow_incomplete:
            return {}, {
                "status": "pending",
                "expected_score_count": len(expected_scores),
                "bound_score_count": 0,
                "missing_score_files": sorted(path.name for path in expected_scores),
                "bindings": [],
            }
        raise ValueError(
            "formal evaluation requires one --score-manifest binding for every "
            "score artifact"
        )

    manifests_by_score: dict[Path, RunManifest] = {}
    seen_manifests: set[Path] = set()
    seen_manifest_run_ids: set[str] = set()
    audit: list[dict[str, Any]] = []
    for score_path, manifest_path in score_manifest_pairs:
        resolved_score = _normalise_path(score_path)
        resolved_manifest = _normalise_path(manifest_path)
        if resolved_score not in expected_scores:
            raise ValueError(
                f"score-manifest binding references an unknown score artifact: {score_path}"
            )
        if resolved_score in manifests_by_score:
            raise ValueError(f"duplicate manifest binding for score artifact: {score_path}")
        if resolved_manifest in seen_manifests:
            raise ValueError(f"one run manifest cannot bind multiple score files: {manifest_path}")
        if not resolved_manifest.is_file():
            raise FileNotFoundError(resolved_manifest)
        try:
            manifest = RunManifest.model_validate_json(
                resolved_manifest.read_text(encoding="utf-8")
            )
        except ValidationError as exc:
            raise ValueError(f"{manifest_path}: invalid run manifest: {exc}") from exc
        if not allow_incomplete and not manifest.reportable:
            raise ValueError(
                f"formal evaluation rejects non-reportable run manifest: {manifest_path}"
            )
        if not allow_incomplete and (manifest.fixture_mode or manifest.synthetic_trace):
            raise ValueError(
                "formal evaluation rejects fixture or synthetic run manifests: "
                f"{manifest_path}"
            )
        if manifest.run_id in seen_manifest_run_ids:
            raise ValueError(
                f"duplicate run-manifest run_id across score bindings: {manifest.run_id}"
            )
        manifests_by_score[resolved_score] = manifest
        seen_manifests.add(resolved_manifest)
        seen_manifest_run_ids.add(manifest.run_id)
        audit.append(
            {
                "score_file": score_path.name,
                "score_sha256": hashlib.sha256(score_path.read_bytes()).hexdigest(),
                "manifest_file": manifest_path.name,
                "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
                "manifest_run_id": manifest.run_id,
                "reportable": manifest.reportable,
                "fixture_mode": manifest.fixture_mode,
                "synthetic_trace": manifest.synthetic_trace,
                "dataset_version": manifest.dataset_version,
                "corpus_version": manifest.corpus_version,
                "chunk_version": manifest.chunk_version,
                "mapping_version": manifest.mapping_version,
                "index_version": manifest.index_version,
                "execution_mode": manifest.execution_mode.value,
                "retrieval_mode": manifest.retrieval_mode.value,
            }
        )

    missing_paths = expected_scores - manifests_by_score.keys()
    missing = sorted(str(path) for path in missing_paths)
    if missing and not allow_incomplete:
        raise ValueError(
            "formal evaluation is missing run-manifest bindings for: " + ", ".join(missing)
        )
    formal_eligible = all(
        binding["reportable"]
        and not binding["fixture_mode"]
        and not binding["synthetic_trace"]
        for binding in audit
    )
    return manifests_by_score, {
        "status": (
            "complete" if not missing_paths and formal_eligible else "incomplete"
        ),
        "expected_score_count": len(expected_scores),
        "bound_score_count": len(manifests_by_score),
        "missing_score_files": sorted(path.name for path in missing_paths),
        "bindings": audit,
    }


def _validate_score_manifest_bindings(
    score_paths: Sequence[Path],
    manifests_by_score: Mapping[Path, RunManifest],
) -> dict[str, RunManifest]:
    manifests_by_record: dict[str, RunManifest] = {}
    for score_path in score_paths:
        manifest = manifests_by_score.get(_normalise_path(score_path))
        if manifest is None:
            continue
        for row in _read_jsonl(score_path):
            run_id = str(row.get("run_id", ""))
            checks = {
                "condition_id": (row.get("condition_id"), manifest.condition_id),
                "execution_mode": (row.get("execution_mode"), manifest.execution_mode.value),
                "mode": (row.get("mode"), manifest.retrieval_mode.value),
                "data_version": (row.get("data_version"), manifest.dataset_version),
                "split": (row.get("split"), manifest.split.value),
                "corpus_version": (row.get("corpus_version"), manifest.corpus_version),
            }
            mismatches = [
                f"{field}={actual!r} (manifest={expected!r})"
                for field, (actual, expected) in checks.items()
                if actual != expected
            ]
            if mismatches:
                raise ValueError(
                    f"{score_path}: score record {run_id} disagrees with its run "
                    "manifest: " + "; ".join(mismatches)
                )
            manifests_by_record[run_id] = manifest
    return manifests_by_record


def load_level_adaptation_ratings(path: Path) -> list[LevelAdaptationRating]:
    if path.suffix.lower() == ".csv":
        with path.open(encoding="utf-8-sig", newline="") as stream:
            rows = []
            for row in csv.DictReader(stream):
                payload = {
                    key: row.get(key)
                    for key in (
                        "schema_version",
                        "rating_id",
                        "question_id",
                        "blinded_answer_id",
                        "assigned_level",
                        "score",
                        "rubric_version",
                        "rater_id",
                        "notes",
                    )
                }
                if not payload["score"]:
                    raise ValueError(
                        f"{path}: every blind-rating row requires a score"
                    )
                if not payload["notes"]:
                    payload["notes"] = None
                rows.append(payload)
        try:
            return [LevelAdaptationRating.model_validate(row) for row in rows]
        except ValidationError as exc:
            raise ValueError(f"{path}: invalid level-adaptation rating: {exc}") from exc
    try:
        return [LevelAdaptationRating.model_validate(row) for row in _read_jsonl(path)]
    except ValidationError as exc:
        raise ValueError(f"{path}: invalid level-adaptation rating: {exc}") from exc


def load_blinded_answer_keys(path: Path) -> list[BlindedAnswerKey]:
    try:
        return [BlindedAnswerKey.model_validate(row) for row in _read_jsonl(path)]
    except ValidationError as exc:
        raise ValueError(f"{path}: invalid blinded-answer key: {exc}") from exc


def load_level_adaptation_rubric(path: Path) -> LevelAdaptationRubricManifest:
    try:
        return LevelAdaptationRubricManifest.model_validate_json(
            path.read_text(encoding="utf-8")
        )
    except ValidationError as exc:
        raise ValueError(f"{path}: invalid level-adaptation rubric: {exc}") from exc


def load_blind_rating_submission_manifest(
    path: Path,
) -> BlindRatingSubmissionManifest:
    try:
        return BlindRatingSubmissionManifest.model_validate_json(
            path.read_text(encoding="utf-8")
        )
    except ValidationError as exc:
        raise ValueError(f"{path}: invalid blind-rating submission manifest: {exc}") from exc


def seal_blind_rating_submission(
    ratings_path: Path,
    rating_key_path: Path,
    rating_rubric_path: Path,
    output_path: Path,
) -> Path:
    """Freeze completed blind-rating inputs so later report runs can verify them."""

    ratings = load_level_adaptation_ratings(ratings_path)
    keys = load_blinded_answer_keys(rating_key_path)
    rubric = load_level_adaptation_rubric(rating_rubric_path)
    if not ratings:
        raise ValueError("cannot seal an empty blind-rating file")
    rater_ids = {rating.rater_id for rating in ratings}
    if len(rater_ids) != 1:
        raise ValueError("single-rater assessment requires exactly one rater_id")
    if any(rating.rubric_version != rubric.rubric_version for rating in ratings):
        raise ValueError("blind ratings do not use the frozen rubric version")
    keyed_ids = {item.blinded_answer_id for item in keys}
    if len(keyed_ids) != len(keys):
        raise ValueError("blind-rating key contains duplicate blinded_answer_id values")
    rated_ids = {item.blinded_answer_id for item in ratings}
    if not rated_ids.issubset(keyed_ids):
        raise ValueError("blind ratings reference an ID absent from the private key")
    manifest = BlindRatingSubmissionManifest(
        ratings_sha256=hashlib.sha256(ratings_path.read_bytes()).hexdigest(),
        key_sha256=hashlib.sha256(rating_key_path.read_bytes()).hexdigest(),
        rubric_sha256=hashlib.sha256(rating_rubric_path.read_bytes()).hexdigest(),
        expected_rating_count=len(keys),
        rubric_version=rubric.rubric_version,
    )
    if output_path.exists():
        raise FileExistsError(f"refusing to overwrite blind-rating manifest: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        manifest.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )
    return output_path


def _verify_blind_rating_submission(
    manifest_path: Path,
    ratings_path: Path,
    rating_key_path: Path,
    rating_rubric_path: Path,
    *,
    rating_count: int,
    key_count: int,
    rubric_version: str,
) -> None:
    manifest = load_blind_rating_submission_manifest(manifest_path)
    checks = {
        "ratings_sha256": hashlib.sha256(ratings_path.read_bytes()).hexdigest(),
        "key_sha256": hashlib.sha256(rating_key_path.read_bytes()).hexdigest(),
        "rubric_sha256": hashlib.sha256(rating_rubric_path.read_bytes()).hexdigest(),
    }
    for field, actual in checks.items():
        if getattr(manifest, field) != actual:
            raise ValueError(f"blind-rating {field} does not match the supplied file")
    if manifest.expected_rating_count != key_count:
        raise ValueError("blind-rating manifest expected count does not match the key")
    if rating_count > manifest.expected_rating_count:
        raise ValueError("blind-rating file contains more rows than the sealed assessment")
    if manifest.rubric_version != rubric_version:
        raise ValueError("blind-rating manifest does not use the supplied rubric version")


def _metric(values: Iterable[bool | None]) -> dict[str, Any]:
    materialized = list(values)
    eligible = [value for value in materialized if value is not None]
    numerator = sum(value is True for value in eligible)
    denominator = len(eligible)
    return {
        "numerator": numerator,
        "denominator": denominator,
        "value": None if denominator == 0 else numerator / denominator,
        "status": "not_applicable" if denominator == 0 else "available",
        "excluded": len(materialized) - denominator,
    }


def _summarise_records(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    retrieval_only = all(
        record.get("execution_mode") == ExecutionMode.RETRIEVAL_ONLY.value
        for record in records
    )
    metrics = {
        name: _metric(record.get(field) for record in records)
        for name, field in BOOLEAN_METRICS.items()
    }
    decisions = [record for record in records if record.get("abstention_correct") is not None]
    predicted = [record for record in decisions if record.get("status") == "abstained"]
    gold_unanswerable = [
        record for record in decisions if record.get("gold_answerable") is False
    ]
    true_positive = sum(record.get("abstention_correct") is True for record in predicted)
    false_positive = len(predicted) - true_positive
    false_negative = len(gold_unanswerable) - true_positive
    precision_denominator = true_positive + false_positive
    recall_denominator = true_positive + false_negative
    f1_denominator = (
        (2 * true_positive) + false_positive + false_negative
        if recall_denominator > 0
        else 0
    )
    metrics.update(
        {
            "abstention_precision": {
                "numerator": true_positive,
                "denominator": precision_denominator,
                "value": (
                    None
                    if precision_denominator == 0
                    else true_positive / precision_denominator
                ),
                "status": (
                    "not_applicable" if precision_denominator == 0 else "available"
                ),
                "excluded": len(records) - len(decisions),
            },
            "abstention_recall": {
                "numerator": true_positive,
                "denominator": recall_denominator,
                "value": (
                    None
                    if recall_denominator == 0
                    else true_positive / recall_denominator
                ),
                "status": (
                    "not_applicable" if recall_denominator == 0 else "available"
                ),
                "excluded": len(records) - len(decisions),
            },
            "abstention_f1": {
                "numerator": 2 * true_positive,
                "denominator": f1_denominator,
                "value": (
                    None
                    if f1_denominator == 0
                    else (2 * true_positive) / f1_denominator
                ),
                "status": "not_applicable" if f1_denominator == 0 else "available",
                "excluded": len(records) - len(decisions),
            },
        }
    )
    citation_checks = [
        check for record in records for check in record.get("citation_checks", [])
    ]
    metrics.update(
        {
            "per_citation_validity": _metric(
                bool(check.get("valid")) for check in citation_checks
            ),
            "citation_chunk_traceability": _metric(
                bool(check.get("resolves_to_chunk")) for check in citation_checks
            ),
            "citation_source_traceability": _metric(
                bool(check.get("resolves_to_source")) for check in citation_checks
            ),
        }
    )
    if retrieval_only:
        metrics = {
            name: {
                "numerator": 0,
                "denominator": 0,
                "value": None,
                "status": "not_applicable",
                "excluded": len(records),
            }
            for name in metrics
        }
    answerability_confusion = Counter(
        {
            "correct_abstention": 0,
            "wrong_abstention": 0,
            "answered_when_unanswerable": 0,
            "answered_when_answerable": 0,
            "technical_failure": 0,
            "unresolved_answerability": 0,
            "not_applicable": 0,
        }
    )
    cause_confusion: dict[str, Counter[str]] = defaultdict(Counter)
    for record in records:
        if record.get("execution_mode") == ExecutionMode.RETRIEVAL_ONLY.value:
            answerability_confusion["not_applicable"] += 1
            continue
        gold_answerable = record.get("gold_answerable")
        abstention_correct = record.get("abstention_correct")
        status = record.get("status")
        cause = record.get("abstention_cause")
        if gold_answerable is None:
            outcome = "unresolved_answerability"
        elif abstention_correct is None:
            outcome = "technical_failure"
        elif status == "abstained":
            outcome = (
                "correct_abstention" if abstention_correct else "wrong_abstention"
            )
        else:
            outcome = (
                "answered_when_unanswerable"
                if gold_answerable is False
                else "answered_when_answerable"
            )
        answerability_confusion[outcome] += 1
        if cause is not None:
            cause_confusion[str(cause)][outcome] += 1
    return {
        "sample_count": len(records),
        "applicability": "not_applicable" if retrieval_only else "applicable",
        "question_ids": sorted(str(record["question_id"]) for record in records),
        "metrics": metrics,
        "answerability_confusion": dict(sorted(answerability_confusion.items())),
        "abstention_cause_confusion": {
            cause: dict(sorted(outcomes.items()))
            for cause, outcomes in sorted(cause_confusion.items())
        },
        "failure_label_counts": dict(
            sorted(
                Counter(
                    label
                    for record in records
                    for label in record.get("failure_labels", [])
                ).items()
            )
        ),
        "execution_status_counts": dict(
            sorted(Counter(str(record["status"]) for record in records).items())
        ),
        "operation_counts": {
            "runs_retried": sum(
                int(record.get("model_call_count", 0)) > 1 for record in records
            ),
            "retry_attempts": sum(
                max(int(record.get("model_call_count", 0)) - 1, 0)
                for record in records
            ),
            "runs_repaired": sum(
                bool(record.get("repair_used")) for record in records
            ),
        },
    }


def _join_records(
    records: Sequence[dict[str, Any]], contexts: Sequence[ExperimentCondition]
) -> list[dict[str, Any]]:
    by_run: dict[str, ExperimentCondition] = {}
    for context in contexts:
        if context.run_id in by_run:
            raise ValueError(f"duplicate experiment context run_id: {context.run_id}")
        by_run[context.run_id] = context
    record_ids = {str(record["run_id"]) for record in records}
    missing = sorted(record_ids - by_run.keys())
    extra = sorted(by_run.keys() - record_ids)
    if missing or extra:
        raise ValueError(
            "experiment context coverage mismatch: "
            f"missing={missing}, extra={extra}"
        )
    joined = []
    for record in records:
        context = by_run[str(record["run_id"])]
        if context.question_id != record["question_id"]:
            raise ValueError(f"question_id mismatch for run {context.run_id}")
        if context.condition_id != record["condition_id"]:
            raise ValueError(f"condition_id mismatch for run {context.run_id}")
        if context.execution_mode.value != record["execution_mode"]:
            raise ValueError(f"execution_mode mismatch for run {context.run_id}")
        joined.append({**record, **context.model_dump(mode="json")})
    return joined


def _validate_experiment_versions(
    records: Sequence[Mapping[str, Any]], *, allow_incomplete: bool
) -> None:
    """Reject comparisons assembled from different frozen M4/M5 artifacts."""

    logical_fields = (
        "mode",
        "data_version",
        "split",
        "corpus_version",
        "textbook_id",
        "student_level",
        "comparison_id",
    )
    version_fields = (
        "execution_mode",
        "chunk_version",
        "mapping_version",
        "index_version",
    )
    versions_by_comparison: dict[tuple[Any, ...], set[tuple[Any, ...]]] = defaultdict(set)
    for record in records:
        logical_key = tuple(record[field] for field in logical_fields)
        version_key = tuple(record[field] for field in version_fields)
        versions_by_comparison[logical_key].add(version_key)
        if not allow_incomplete and any(
            str(record[field]).strip().lower() == "unspecified"
            for field in version_fields[1:]
        ):
            raise ValueError(
                "formal evaluation requires explicit chunk_version, mapping_version, "
                f"and index_version for {logical_key}"
            )
    for logical_key, versions in versions_by_comparison.items():
        if len(versions) > 1:
            rendered = [dict(zip(version_fields, item, strict=True)) for item in sorted(versions)]
            raise ValueError(
                "experiment comparison mixes execution modes or artifact versions for "
                f"{logical_key}: {rendered}"
            )


def _manifest_version(value: str | None) -> str:
    return value if value is not None else "not_applicable"


def _validate_joined_manifest_bindings(
    records: Sequence[Mapping[str, Any]],
    manifests_by_record: Mapping[str, RunManifest],
    *,
    allow_incomplete: bool,
) -> None:
    manifests_by_comparison: dict[tuple[Any, ...], dict[str, RunManifest]] = defaultdict(dict)
    for record in records:
        run_id = str(record["run_id"])
        manifest = manifests_by_record.get(run_id)
        if manifest is None:
            if allow_incomplete:
                continue
            raise ValueError(f"formal evaluation has no bound run manifest for {run_id}")
        checks = {
            "chunk_version": (record["chunk_version"], manifest.chunk_version),
            "mapping_version": (
                record["mapping_version"],
                _manifest_version(manifest.mapping_version),
            ),
            "index_version": (
                record["index_version"],
                _manifest_version(manifest.index_version),
            ),
            "execution_mode": (
                record["execution_mode"],
                manifest.execution_mode.value,
            ),
        }
        if manifest.execution_mode is ExecutionMode.RETRIEVAL_AND_GENERATION:
            checks["student_level/profile"] = (
                record["student_level"],
                manifest.profile,
            )
        else:
            checks["retrieval_only profile"] = (manifest.profile, "none")
        mismatches = [
            f"{field}={actual!r} (manifest={expected!r})"
            for field, (actual, expected) in checks.items()
            if actual != expected
        ]
        if mismatches:
            raise ValueError(
                f"experiment context for {run_id} disagrees with its run manifest: "
                + "; ".join(mismatches)
            )
        comparison_key = (
            record["mode"],
            record["data_version"],
            record["split"],
            record["corpus_version"],
            record["textbook_id"],
            record["student_level"],
            record["comparison_id"],
        )
        manifests_by_comparison[comparison_key][manifest.run_id] = manifest

    for comparison_key, manifests in manifests_by_comparison.items():
        try:
            assert_manifests_comparable(list(manifests.values()))
        except ValueError as exc:
            raise ValueError(
                f"run manifests are not comparable for {comparison_key}: {exc}"
            ) from exc


def _validate_expected_experiment_coverage(
    groups: Sequence[Mapping[str, Any]],
    expected: ExpectedExperimentManifest | None,
    *,
    allow_incomplete: bool,
) -> dict[str, Any]:
    if expected is None:
        if allow_incomplete:
            return {"status": "pending", "matrix_version": None, "missing": []}
        raise ValueError(
            "formal evaluation requires an expected-experiment manifest"
        )
    identity_fields = (
        "mode",
        "execution_mode",
        "data_version",
        "split",
        "corpus_version",
        "chunk_version",
        "mapping_version",
        "index_version",
        "textbook_id",
        "student_level",
        "comparison_id",
        "condition_id",
        "lambda_weight",
        "lambda_status",
    )
    actual = {
        tuple(group[field] for field in identity_fields): set(group["question_ids"])
        for group in groups
    }
    expected_keys: set[tuple[Any, ...]] = set()
    errors: list[str] = []
    for cell in expected.cells:
        payload = cell.model_dump(mode="json")
        key = tuple(payload[field] for field in identity_fields)
        expected_keys.add(key)
        actual_questions = actual.get(key)
        if actual_questions is None:
            errors.append(f"missing experiment cell {key}")
            continue
        expected_questions = set(cell.expected_question_ids)
        if actual_questions != expected_questions:
            errors.append(
                f"question coverage mismatch for {key}: "
                f"missing={sorted(expected_questions - actual_questions)}, "
                f"extra={sorted(actual_questions - expected_questions)}"
            )
    extra = sorted(actual.keys() - expected_keys)
    if extra:
        errors.append(f"unexpected experiment cells: {extra}")
    if errors and not allow_incomplete:
        raise ValueError("formal experiment coverage is incomplete: " + "; ".join(errors))
    return {
        "status": "incomplete" if errors else "complete",
        "matrix_version": expected.matrix_version,
        "expected_cell_count": len(expected.cells),
        "observed_cell_count": len(actual),
        "errors": errors,
    }


def _group_records(records: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        key = tuple(record[field] for field in GROUP_IDENTITY_FIELDS)
        grouped[key].append(record)
    for key, rows in grouped.items():
        question_ids = [str(row["question_id"]) for row in rows]
        if len(question_ids) != len(set(question_ids)):
            raise ValueError(f"duplicate question_id within experiment group: {key}")
    return [
        {
            **dict(zip(GROUP_IDENTITY_FIELDS, key, strict=True)),
            **_summarise_records(rows),
        }
        for key, rows in sorted(grouped.items())
    ]


def _adaptation_summary(
    records: Sequence[dict[str, Any]],
    ratings: Sequence[LevelAdaptationRating],
    answer_keys: Sequence[BlindedAnswerKey],
    rubric: LevelAdaptationRubricManifest | None,
    *,
    ratings_supplied: bool,
    allow_incomplete: bool,
) -> dict[str, Any]:
    if not ratings_supplied:
        return {"status": "pending", "rating_count": 0, "groups": []}
    if not ratings:
        raise ValueError("a supplied blind-rating file must not be empty")
    records_by_run = {str(record["run_id"]): record for record in records}
    expected_answered_runs = {
        run_id
        for run_id, record in records_by_run.items()
        if record["status"] == "answered"
    }
    if rubric is None:
        raise ValueError("level-adaptation ratings require a frozen rubric manifest")
    keys_by_answer: dict[str, str] = {}
    keyed_runs: set[str] = set()
    for answer_key in answer_keys:
        if answer_key.blinded_answer_id in keys_by_answer:
            raise ValueError(
                "duplicate blinded_answer_id in rating key: "
                f"{answer_key.blinded_answer_id}"
            )
        if answer_key.run_id in keyed_runs:
            raise ValueError(f"duplicate run_id in rating key: {answer_key.run_id}")
        keys_by_answer[answer_key.blinded_answer_id] = answer_key.run_id
        keyed_runs.add(answer_key.run_id)
    for blinded_answer_id, run_id in keys_by_answer.items():
        record = records_by_run.get(run_id)
        if record is None:
            raise ValueError(f"rating key references unknown run_id: {run_id}")
        if record["status"] != "answered":
            raise ValueError(
                "blind-rating key must contain answered runs only: "
                f"{blinded_answer_id} -> {run_id}"
            )
    missing_key_runs = sorted(expected_answered_runs - keyed_runs)
    extra_key_runs = sorted(keyed_runs - expected_answered_runs)
    if (missing_key_runs or extra_key_runs) and not allow_incomplete:
        raise ValueError(
            "blind-rating private key does not cover all applicable answered runs: "
            f"missing={missing_key_runs}, extra={extra_key_runs}"
        )
    seen_rating_ids: set[str] = set()
    rated_answers: set[str] = set()
    grouped: dict[tuple[Any, ...], list[float]] = defaultdict(list)
    rubric_versions: set[str] = set()
    rater_ids: set[str] = set()
    for rating in ratings:
        if rating.rating_id in seen_rating_ids:
            raise ValueError(f"duplicate level-adaptation rating_id: {rating.rating_id}")
        seen_rating_ids.add(rating.rating_id)
        if rating.blinded_answer_id in rated_answers:
            raise ValueError(
                "duplicate level-adaptation rating for blinded_answer_id: "
                f"{rating.blinded_answer_id}"
            )
        rated_answers.add(rating.blinded_answer_id)
        if rating.rubric_version != rubric.rubric_version:
            raise ValueError(
                f"rating {rating.rating_id} does not use the frozen rubric version"
            )
        if not rubric.score_min <= rating.score <= rubric.score_max:
            raise ValueError(
                f"rating {rating.rating_id} falls outside the frozen score range"
            )
        run_id = keys_by_answer.get(rating.blinded_answer_id)
        if run_id is None:
            raise ValueError(
                "rating references unknown blinded_answer_id: "
                f"{rating.blinded_answer_id}"
            )
        record = records_by_run.get(run_id)
        if record is None:
            raise ValueError(f"rating key references unknown run_id: {run_id}")
        if record["status"] != "answered":
            raise ValueError(
                f"level-adaptation rating requires an answered run: {run_id}"
            )
        if rating.question_id != record["question_id"]:
            raise ValueError(f"rating question_id mismatch for run {run_id}")
        if rating.assigned_level.value != record["student_level"]:
            raise ValueError(f"rating level mismatch for run {run_id}")
        key = tuple(record[field] for field in GROUP_IDENTITY_FIELDS)
        grouped[key].append(rating.score)
        rubric_versions.add(rating.rubric_version)
        rater_ids.add(rating.rater_id)
    if len(rater_ids) != 1:
        raise ValueError("single-rater assessment requires exactly one rater_id")
    missing_ratings = sorted(keys_by_answer.keys() - rated_answers)
    if missing_ratings and not allow_incomplete:
        raise ValueError(
            "blind-rating coverage is incomplete; missing ratings for: "
            + ", ".join(missing_ratings)
        )
    groups = []
    for key, scores in sorted(grouped.items()):
        groups.append(
            {
                **dict(zip(GROUP_IDENTITY_FIELDS, key, strict=True)),
                "rating_count": len(scores),
                "mean_score": sum(scores) / len(scores),
                "min_score": min(scores),
                "max_score": max(scores),
            }
        )
    return {
        "status": (
            "incomplete"
            if missing_ratings or missing_key_runs or extra_key_runs
            else "available"
        ),
        "rating_count": len(ratings),
        "expected_rating_count": len(expected_answered_runs),
        "missing_blinded_answer_ids": missing_ratings,
        "missing_run_ids_from_private_key": missing_key_runs,
        "unexpected_run_ids_in_private_key": extra_key_runs,
        "rubric_versions": sorted(rubric_versions),
        "score_min": rubric.score_min,
        "score_max": rubric.score_max,
        "rater_count": len(rater_ids),
        "groups": groups,
    }


def _lambda_comparisons(
    groups: Sequence[Mapping[str, Any]],
    adaptation: Mapping[str, Any],
    *,
    allow_incomplete: bool,
) -> list[dict[str, Any]]:
    comparison_identity = (
        "mode",
        "execution_mode",
        "data_version",
        "split",
        "corpus_version",
        "chunk_version",
        "mapping_version",
        "index_version",
        "textbook_id",
        "student_level",
        "comparison_id",
    )
    buckets: dict[tuple[Any, ...], dict[str, Mapping[str, Any]]] = defaultdict(dict)
    for group in groups:
        key = tuple(group[field] for field in comparison_identity)
        status = str(group["lambda_status"])
        if status in buckets[key]:
            raise ValueError(
                "lambda comparison requires one aggregate baseline and one frozen group "
                f"per textbook/level; duplicate {status} for {key}"
            )
        buckets[key][status] = group
    adaptation_lookup = {
        (
            *(group[field] for field in comparison_identity),
            group["lambda_status"],
        ): group
        for group in adaptation.get("groups", [])
    }
    comparisons: list[dict[str, Any]] = []
    for key, pair in sorted(buckets.items()):
        if set(pair) != {"baseline", "frozen"}:
            if allow_incomplete:
                continue
            raise ValueError(
                "formal lambda comparison requires baseline and frozen groups for "
                f"{key}; found={sorted(pair)}"
            )
        baseline = pair["baseline"]
        frozen = pair["frozen"]
        baseline_questions = set(baseline["question_ids"])
        frozen_questions = set(frozen["question_ids"])
        if baseline_questions != frozen_questions:
            raise ValueError(
                "lambda comparison question coverage mismatch for "
                f"{key}: missing={sorted(baseline_questions - frozen_questions)}, "
                f"extra={sorted(frozen_questions - baseline_questions)}"
            )
        if baseline["metrics"].keys() != frozen["metrics"].keys():
            raise ValueError(f"lambda comparison metric mismatch for {key}")
        for metric_name in sorted(baseline["metrics"]):
            baseline_value = baseline["metrics"][metric_name]["value"]
            frozen_value = frozen["metrics"][metric_name]["value"]
            comparisons.append(
                {
                    **dict(zip(comparison_identity, key, strict=True)),
                    "metric": metric_name,
                    "baseline_condition_id": baseline["condition_id"],
                    "frozen_condition_id": frozen["condition_id"],
                    "baseline_lambda": baseline["lambda_weight"],
                    "frozen_lambda": frozen["lambda_weight"],
                    "baseline_value": baseline_value,
                    "frozen_value": frozen_value,
                    "delta": (
                        None
                        if baseline_value is None or frozen_value is None
                        else frozen_value - baseline_value
                    ),
                    "status": (
                        "not_applicable"
                        if baseline_value is None or frozen_value is None
                        else "available"
                    ),
                }
            )
        base_adaptation = adaptation_lookup.get((*key, "baseline"))
        frozen_adaptation = adaptation_lookup.get((*key, "frozen"))
        if base_adaptation is not None and frozen_adaptation is not None:
            comparisons.append(
                {
                    **dict(zip(comparison_identity, key, strict=True)),
                    "metric": "level_adaptation_mean",
                    "baseline_condition_id": baseline["condition_id"],
                    "frozen_condition_id": frozen["condition_id"],
                    "baseline_lambda": baseline["lambda_weight"],
                    "frozen_lambda": frozen["lambda_weight"],
                    "baseline_value": base_adaptation["mean_score"],
                    "frozen_value": frozen_adaptation["mean_score"],
                    "delta": (
                        frozen_adaptation["mean_score"]
                        - base_adaptation["mean_score"]
                    ),
                    "status": "available",
                }
            )
    return comparisons


def write_blind_rating_materials(
    runs: Sequence[EvaluationRunResult],
    gold_samples: Sequence[GoldSample],
    contexts: Sequence[ExperimentCondition],
    output_dir: Path,
    *,
    seed: int,
) -> dict[str, Path]:
    """Create a single-rater blind sheet and a separate private answer key."""

    run_ids = [run.run_id for run in runs]
    if len(run_ids) != len(set(run_ids)):
        raise ValueError("blind-rating inputs contain duplicate run_id values")
    contexts_by_run: dict[str, ExperimentCondition] = {}
    for context in contexts:
        if context.run_id in contexts_by_run:
            raise ValueError(f"duplicate experiment context run_id: {context.run_id}")
        contexts_by_run[context.run_id] = context
    missing_contexts = sorted(set(run_ids) - contexts_by_run.keys())
    extra_contexts = sorted(contexts_by_run.keys() - set(run_ids))
    if missing_contexts or extra_contexts:
        raise ValueError(
            "blind-rating context coverage mismatch: "
            f"missing={missing_contexts}, extra={extra_contexts}"
        )
    gold_by_question = {sample.question_id: sample for sample in gold_samples}
    if len(gold_by_question) != len(gold_samples):
        raise ValueError("blind-rating Gold contains duplicate question_id values")

    eligible = [run for run in runs if run.status is RunStatus.ANSWERED]
    if not eligible:
        raise ValueError("blind-rating preparation requires at least one answered run")
    missing_gold = sorted(
        {run.question_id for run in eligible} - gold_by_question.keys()
    )
    if missing_gold:
        raise ValueError(
            "blind-rating preparation is missing Gold questions: "
            + ", ".join(missing_gold)
        )

    rng = random.Random(seed)
    shuffled = list(eligible)
    rng.shuffle(shuffled)
    used_ids: set[str] = set()
    sheet_rows: list[dict[str, Any]] = []
    key_rows: list[dict[str, Any]] = []
    for run in shuffled:
        context = contexts_by_run[run.run_id]
        if context.question_id != run.question_id:
            raise ValueError(f"question_id mismatch for run {run.run_id}")
        while True:
            blinded_answer_id = f"answer-{rng.getrandbits(48):012x}"
            if blinded_answer_id not in used_ids:
                used_ids.add(blinded_answer_id)
                break
        gold = gold_by_question[run.question_id]
        if run.final_answer is None:
            raise ValueError(f"answered run is missing final_answer: {run.run_id}")
        sheet_rows.append(
            {
                "schema_version": "0.1",
                "rating_id": f"rating-{blinded_answer_id}",
                "question_id": run.question_id,
                "blinded_answer_id": blinded_answer_id,
                "assigned_level": context.student_level.value,
                "question": gold.question,
                "options": " | ".join(
                    f"{label}: {option.text}"
                    for label, option in sorted(gold.options.items())
                ),
                "final_choice": run.final_answer.final_choice,
                "explanation": run.final_answer.explanation,
                "score": "",
                "rubric_version": "",
                "rater_id": "",
                "notes": "",
            }
        )
        key_rows.append(
            {
                "schema_version": "0.1",
                "blinded_answer_id": blinded_answer_id,
                "run_id": run.run_id,
            }
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "sheet": output_dir / "blind_rating_sheet.csv",
        "key": output_dir / "blinded_answer_key.jsonl",
        "manifest": output_dir / "blind_rating_manifest.json",
    }
    with paths["sheet"].open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(sheet_rows[0]))
        writer.writeheader()
        writer.writerows(sheet_rows)
    with paths["key"].open("w", encoding="utf-8", newline="\n") as stream:
        for row in key_rows:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    status_counts = Counter(run.status.value for run in runs)
    manifest = {
        "schema_version": "0.1",
        "single_rater": True,
        "input_run_count": len(runs),
        "eligible_answered_count": len(eligible),
        "excluded_run_count": len(runs) - len(eligible),
        "input_status_counts": dict(sorted(status_counts.items())),
        "expected_rating_count": len(sheet_rows),
        "sheet_sha256": hashlib.sha256(paths["sheet"].read_bytes()).hexdigest(),
        "key_sha256": hashlib.sha256(paths["key"].read_bytes()).hexdigest(),
    }
    paths["manifest"].write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return paths


def audit_role_label_provenance(
    manifest_path: Path,
    gold: Sequence[GoldSample],
    mapping: GoldChunkMapping,
    *,
    corpus_record_ids: set[str] | None = None,
    question_reference_pairs: set[tuple[str, str]] | None = None,
) -> dict[str, Any]:
    """Validate identity and references without judging Role-label semantics."""

    manifest = RoleLabelProvenanceManifest.model_validate_json(
        manifest_path.read_text(encoding="utf-8")
    )
    labels_path = manifest.labels_file
    if not labels_path.is_absolute():
        labels_path = manifest_path.parent / labels_path
    if not labels_path.is_file():
        raise FileNotFoundError(labels_path)
    digest = hashlib.sha256(labels_path.read_bytes()).hexdigest()
    errors: list[str] = []
    if digest != manifest.labels_sha256:
        errors.append("labels_sha256 does not match the labels file")
    rows = _read_jsonl(labels_path)
    if len(rows) != manifest.declared_record_count:
        errors.append("declared_record_count does not match the labels file")
    question_ids = {sample.question_id for sample in gold}
    corpus_versions = {sample.corpus_version for sample in gold}
    if corpus_versions != {manifest.corpus_version}:
        errors.append(
            "Role-label corpus_version does not match the supplied Gold corpus"
        )
    parser_versions = {sample.parser_version for sample in gold}
    if parser_versions != {manifest.parser_version}:
        errors.append(
            "Role-label parser_version does not match the supplied Gold corpus"
        )
    if mapping.corpus_version != manifest.corpus_version:
        errors.append(
            "Role-label corpus_version does not match the supplied Gold mapping"
        )
    span_ids_by_question = {
        sample.question_id: {
            span.span_id
            for group in sample.gold_core_evidence_sets
            for span in group
        }
        | {span.span_id for span in sample.partial_evidence}
        for sample in gold
    }
    chunk_ids_by_question = {
        item.question_id: {
            chunk_id
            for span in item.spans
            for chunk_set in span.acceptable_chunk_sets
            for chunk_id in chunk_set
        }
        for item in mapping.items
    }
    span_ids = set().union(*span_ids_by_question.values()) if gold else set()
    chunk_ids = (
        set().union(*chunk_ids_by_question.values()) if mapping.items else set()
    )
    if manifest.reference_type == "span":
        valid_references = span_ids
        valid_pairs = {
            (question_id, reference_id)
            for question_id, references in span_ids_by_question.items()
            for reference_id in references
        }
        validation_scope = "gold_spans"
    elif manifest.reference_universe == "corpus_records":
        valid_references = corpus_record_ids or set()
        valid_pairs = question_reference_pairs or set()
        validation_scope = "corpus_records"
        if corpus_record_ids is None:
            errors.append(
                "reference_universe=corpus_records requires the M4 records artifact"
            )
        if question_reference_pairs is None:
            errors.append(
                "reference_universe=corpus_records requires a frozen "
                "question-to-chunk relationship artifact"
            )
    else:
        valid_references = chunk_ids
        valid_pairs = {
            (question_id, reference_id)
            for question_id, references in chunk_ids_by_question.items()
            for reference_id in references
        }
        validation_scope = "gold_mapping"
    invalid_question_ids: set[str] = set()
    invalid_reference_ids: set[str] = set()
    invalid_question_reference_pairs: set[tuple[str, str]] = set()
    seen_label_pairs: set[tuple[str, str]] = set()
    duplicate_label_pairs: set[tuple[str, str]] = set()
    missing_fields = 0
    invalid_role_values = 0
    for row in rows:
        required = (
            manifest.question_id_field,
            manifest.reference_id_field,
            manifest.role_field,
            manifest.record_schema_version_field,
        )
        if any(field not in row for field in required):
            missing_fields += 1
            continue
        if str(row[manifest.record_schema_version_field]) != manifest.role_schema_version:
            errors.append("a Role-label record has an unexpected schema version")
        question_id = str(row[manifest.question_id_field])
        reference_id = str(row[manifest.reference_id_field])
        role_value = row[manifest.role_field]
        if not isinstance(role_value, str) or not role_value.strip():
            invalid_role_values += 1
        label_pair = (question_id, reference_id)
        if label_pair in seen_label_pairs:
            duplicate_label_pairs.add(label_pair)
        seen_label_pairs.add(label_pair)
        if question_id not in question_ids:
            invalid_question_ids.add(question_id)
        if reference_id not in valid_references:
            invalid_reference_ids.add(reference_id)
        if (
            question_id in question_ids
            and reference_id in valid_references
            and (question_id, reference_id) not in valid_pairs
        ):
            invalid_question_reference_pairs.add((question_id, reference_id))
    if missing_fields:
        errors.append(f"{missing_fields} Role-label records are missing configured fields")
    if invalid_role_values:
        errors.append(f"{invalid_role_values} Role-label records have an empty Role value")
    if duplicate_label_pairs:
        errors.append("Role-label records contain duplicate question/evidence pairs")
    if invalid_question_ids:
        errors.append("Role labels reference unknown question IDs")
    if invalid_reference_ids:
        errors.append("Role labels reference unknown evidence IDs")
    if invalid_question_reference_pairs:
        errors.append("Role labels contain invalid question-to-evidence relationships")
    missing_expected_pairs = valid_pairs - seen_label_pairs
    unexpected_label_pairs = seen_label_pairs - valid_pairs
    if missing_expected_pairs:
        errors.append("Role-label package does not cover every expected question/evidence pair")
    if unexpected_label_pairs:
        errors.append("Role-label package contains pairs outside the expected coverage scope")
    return {
        "status": "passed" if not errors else "failed",
        "semantic_quality_reviewed": False,
        "iaa_computed": False,
        "single_annotator": len(manifest.annotator_ids) == 1,
        "role_schema_version": manifest.role_schema_version,
        "role_taxonomy_version": manifest.role_taxonomy_version,
        "annotation_version": manifest.annotation_version,
        "corpus_version": manifest.corpus_version,
        "parser_version": manifest.parser_version,
        "annotation_date": manifest.annotation_date.isoformat(),
        "annotator_count": len(manifest.annotator_ids),
        "double_annotated": manifest.double_annotated,
        "record_count": len(rows),
        "expected_record_count": len(valid_pairs),
        "labels_sha256": digest,
        "reference_type": manifest.reference_type,
        "reference_universe": manifest.reference_universe,
        "validation_scope": validation_scope,
        "invalid_question_ids": sorted(invalid_question_ids),
        "invalid_reference_ids": sorted(invalid_reference_ids),
        "invalid_question_reference_pairs": [
            {"question_id": question_id, "reference_id": reference_id}
            for question_id, reference_id in sorted(invalid_question_reference_pairs)
        ],
        "duplicate_label_pairs": [
            {"question_id": question_id, "reference_id": reference_id}
            for question_id, reference_id in sorted(duplicate_label_pairs)
        ],
        "missing_expected_pairs": [
            {"question_id": question_id, "reference_id": reference_id}
            for question_id, reference_id in sorted(missing_expected_pairs)
        ],
        "unexpected_label_pairs": [
            {"question_id": question_id, "reference_id": reference_id}
            for question_id, reference_id in sorted(unexpected_label_pairs)
        ],
        "errors": errors,
    }


def _display(value: Any) -> str:
    if value is None:
        return "not_applicable"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def _metric_display(metric: Mapping[str, Any]) -> str:
    return (
        f"{metric['numerator']}/{metric['denominator']} "
        f"({_display(metric['value'])})"
    )


def _markdown(result: Mapping[str, Any]) -> str:
    lines = [
        "# Personalisation Evaluation Report",
        "",
        "This report combines existing offline answer/citation scores with "
        "textbook, learner-level, condition, and lambda metadata. Automated "
        "metrics, blinded human ratings, and Role-label provenance remain "
        "separate evidence sources.",
        "",
        "## Experiment groups",
        "",
        "| Split | Corpus | Textbook | Level | Comparison | Condition | "
        "Lambda | Status | Samples | "
        "Answer accuracy | Citation validity | Abstention accuracy |",
        "| --- | --- | --- | --- | --- | --- | ---: | --- | ---: | ---: | ---: | ---: |",
    ]
    for group in result["groups"]:
        metrics = group["metrics"]
        lines.append(
            f"| {group['split']} | {group['corpus_version']} | "
            f"{group['textbook_id']} | {group['student_level']} | "
            f"{group['comparison_id']} | {group['condition_id']} | "
            f"{group['lambda_weight']:.4f} | "
            f"{group['lambda_status']} | {group['sample_count']} | "
            f"{_metric_display(metrics['answer_accuracy'])} | "
            f"{_metric_display(metrics['citation_validity'])} | "
            f"{_metric_display(metrics['abstention_accuracy'])} |"
        )
    lines.extend(
        [
            "",
            "### Bound execution and artifact versions",
            "",
            "| Condition | Execution mode | Chunk version | Mapping version | Index version |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for group in result["groups"]:
        lines.append(
            f"| {group['condition_id']} | {group['execution_mode']} | "
            f"{group['chunk_version']} | {group['mapping_version']} | "
            f"{group['index_version']} |"
        )
    coverage = result["experiment_coverage"]
    lines.extend(
        [
            "",
            "### Formal input integrity",
            "",
            f"- Experiment coverage: `{coverage['status']}`",
            f"- Expected matrix version: `{coverage.get('matrix_version') or 'not_supplied'}`",
        ]
    )
    binding_status = result["run_manifest_binding_status"]
    bindings = result["run_manifest_bindings"]
    lines.append(f"- Run-manifest binding: `{binding_status['status']}`")
    if binding_status["status"] == "complete":
        lines.extend(
            [
                "- Every score artifact is bound to a reportable, non-fixture run manifest.",
                "",
                "| Score file | Score SHA-256 | Manifest file | Manifest SHA-256 | "
                "Run manifest ID |",
                "| --- | --- | --- | --- | --- |",
            ]
        )
        for binding in bindings:
            lines.append(
                f"| {binding['score_file']} | `{binding['score_sha256']}` | "
                f"{binding['manifest_file']} | `{binding['manifest_sha256']}` | "
                f"{binding['manifest_run_id']} |"
            )
    elif not bindings:
        lines.append(
            "- No run manifests were supplied (development/incomplete report only)."
        )
    else:
        lines.append(
            "- Supplied bindings are incomplete or development-only and cannot support "
            "a formal report."
        )
    for missing_file in binding_status["missing_score_files"]:
        lines.append(f"- Missing run-manifest binding: {missing_file}")
    source_status = result["score_source_binding_status"]
    source_bindings = result["score_source_bindings"]
    lines.append(f"- Score-source binding: `{source_status['status']}`")
    if source_status["status"] == "complete":
        lines.extend(
            [
                "- Every score artifact is bound by SHA-256 and exact run-ID coverage "
                "to its original saved run-results file.",
                "",
                "| Score file | Provenance file | Source run-results | Source SHA-256 | Runs |",
                "| --- | --- | --- | --- | ---: |",
            ]
        )
        for binding in source_bindings:
            lines.append(
                f"| {binding['score_file']} | {binding['provenance_file']} | "
                f"{binding['source_runs_file']} | "
                f"`{binding['source_runs_sha256']}` | {binding['run_count']} |"
            )
    elif not source_bindings:
        lines.append(
            "- No score-source provenance was supplied "
            "(development/incomplete report only)."
        )
    else:
        lines.append(
            "- Score-source bindings are incomplete and cannot support a formal report."
        )
    for missing_file in source_status["missing_score_files"]:
        lines.append(f"- Missing score-source binding: {missing_file}")
    for error in coverage.get("errors", []):
        lines.append(f"- Coverage error: {error}")
    lines.extend(
        [
            "",
            "### Refusal metrics",
            "",
            "| Split | Corpus | Textbook | Level | Condition | Precision | Recall | F1 |",
            "| --- | --- | --- | --- | --- | ---: | ---: | ---: |",
        ]
    )
    for group in result["groups"]:
        metrics = group["metrics"]
        lines.append(
            f"| {group['split']} | {group['corpus_version']} | "
            f"{group['textbook_id']} | {group['student_level']} | "
            f"{group['condition_id']} | "
            f"{_metric_display(metrics['abstention_precision'])} | "
            f"{_metric_display(metrics['abstention_recall'])} | "
            f"{_metric_display(metrics['abstention_f1'])} |"
        )
    lines.extend(["", "### Abstention causes", ""])
    cause_rows = [
        (group, cause, outcome, count)
        for group in result["groups"]
        for cause, outcomes in group["abstention_cause_confusion"].items()
        for outcome, count in outcomes.items()
    ]
    if cause_rows:
        lines.extend(
            [
                "| Split | Textbook | Level | Condition | Cause | Outcome | Count |",
                "| --- | --- | --- | --- | --- | --- | ---: |",
            ]
        )
        for group, cause, outcome, count in cause_rows:
            lines.append(
                f"| {group['split']} | {group['textbook_id']} | "
                f"{group['student_level']} | {group['condition_id']} | "
                f"{cause} | {outcome} | {count} |"
            )
    else:
        lines.append("No abstention causes were recorded in the supplied scores.")
    lines.extend(["", "### Answerability outcomes", ""])
    lines.extend(
        [
            "| Split | Textbook | Level | Condition | Outcome | Count |",
            "| --- | --- | --- | --- | --- | ---: |",
        ]
    )
    for group in result["groups"]:
        for outcome, count in group["answerability_confusion"].items():
            lines.append(
                f"| {group['split']} | {group['textbook_id']} | "
                f"{group['student_level']} | {group['condition_id']} | "
                f"{outcome} | {count} |"
            )
    lines.extend(
        [
            "",
            "### Output and citation checks",
            "",
            "| Split | Textbook | Level | Condition | Raw JSON | Raw schema | "
            "Repaired JSON | Repaired schema | Per-citation validity | "
            "Chunk traceability | Source traceability | Gold-evidence coverage |",
            "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | "
            "---: | ---: | ---: |",
        ]
    )
    for group in result["groups"]:
        metrics = group["metrics"]
        lines.append(
            f"| {group['split']} | {group['textbook_id']} | "
            f"{group['student_level']} | {group['condition_id']} | "
            f"{_metric_display(metrics['raw_json_validity'])} | "
            f"{_metric_display(metrics['raw_schema_validity'])} | "
            f"{_metric_display(metrics['repaired_json_validity'])} | "
            f"{_metric_display(metrics['repaired_schema_validity'])} | "
            f"{_metric_display(metrics['per_citation_validity'])} | "
            f"{_metric_display(metrics['citation_chunk_traceability'])} | "
            f"{_metric_display(metrics['citation_source_traceability'])} | "
            f"{_metric_display(metrics['gold_evidence_citation_coverage'])} |"
        )
    lines.extend(["", "## Lambda comparison", ""])
    if result["lambda_comparisons"]:
        lines.extend(
            [
                "| Split | Corpus | Textbook | Level | Comparison | Metric | "
                "Baseline condition | Frozen condition | Lambda 0 | Frozen lambda | "
                "Baseline | Frozen | Delta |",
                "| --- | --- | --- | --- | --- | --- | --- | --- | ---: | "
                "---: | ---: | ---: | ---: |",
            ]
        )
        for row in result["lambda_comparisons"]:
            lines.append(
                f"| {row['split']} | {row['corpus_version']} | "
                f"{row['textbook_id']} | {row['student_level']} | "
                f"{row['comparison_id']} | {row['metric']} | "
                f"{row['baseline_condition_id']} | {row['frozen_condition_id']} | "
                f"{row['baseline_lambda']:.4f} | {row['frozen_lambda']:.4f} | "
                f"{_display(row['baseline_value'])} | {_display(row['frozen_value'])} | "
                f"{_display(row['delta'])} |"
            )
    else:
        lines.append("No comparable lambda=0 and frozen-lambda pairs are available.")
    lines.extend(["", "## Error analysis", ""])
    status_rows = [
        (group, status, count)
        for group in result["groups"]
        for status, count in group["execution_status_counts"].items()
    ]
    if status_rows:
        lines.extend(
            [
                "### Execution status",
                "",
                "| Split | Textbook | Level | Condition | Status | Count |",
                "| --- | --- | --- | --- | --- | ---: |",
            ]
        )
        for group, status, count in status_rows:
            lines.append(
                f"| {group['split']} | {group['textbook_id']} | "
                f"{group['student_level']} | {group['condition_id']} | "
                f"{status} | {count} |"
            )
        lines.extend(["", "### Failure labels", ""])
    failure_rows = [
        (group, label, count)
        for group in result["groups"]
        for label, count in group["failure_label_counts"].items()
    ]
    if failure_rows:
        lines.extend(
            [
                "| Split | Textbook | Level | Condition | Failure label | Count |",
                "| --- | --- | --- | --- | --- | ---: |",
            ]
        )
        for group, label, count in failure_rows:
            lines.append(
                f"| {group['split']} | {group['textbook_id']} | "
                f"{group['student_level']} | {group['condition_id']} | "
                f"{label} | {count} |"
            )
    else:
        lines.append("No failure labels were recorded in the supplied score artifacts.")
    adaptation = result["level_adaptation"]
    lines.extend(["", "## Blinded level-adaptation assessment", ""])
    if adaptation["status"] == "pending":
        lines.append("Status: pending. No blinded human ratings were supplied.")
    else:
        if adaptation["status"] == "incomplete":
            lines.append(
                "Status: incomplete. The supplied blind-rating file does not cover every "
                "sealed answer."
            )
        lines.append(
            f"Ratings: {adaptation['rating_count']}; raters: "
            f"{adaptation['rater_count']}; rubric versions: "
            f"{', '.join(adaptation['rubric_versions'])}."
        )
        lines.extend(
            [
                "",
                "| Split | Corpus | Textbook | Level | Comparison | Condition | "
                "Lambda status | Ratings | "
                "Mean | Min | Max |",
                "| --- | --- | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: |",
            ]
        )
        for group in adaptation["groups"]:
            lines.append(
                f"| {group['split']} | {group['corpus_version']} | "
                f"{group['textbook_id']} | {group['student_level']} | "
                f"{group['comparison_id']} | {group['condition_id']} | "
                f"{group['lambda_status']} | "
                f"{group['rating_count']} | {group['mean_score']:.4f} | "
                f"{group['min_score']:.4f} | {group['max_score']:.4f} |"
            )
    role = result["role_label_provenance"]
    lines.extend(["", "## Role-label provenance", ""])
    if role["status"] == "pending":
        lines.append("Status: pending. No M3 Role-label package was supplied.")
    else:
        lines.extend(
            [
                f"- Audit status: `{role['status']}`",
                f"- Role schema version: `{role['role_schema_version']}`",
                f"- Role taxonomy version: `{role['role_taxonomy_version']}`",
                f"- Annotation version: `{role['annotation_version']}`",
                f"- Corpus version: `{role['corpus_version']}`",
                f"- Parser version: `{role['parser_version']}`",
                f"- Annotation date: `{role['annotation_date']}`",
                f"- Annotator count: {role['annotator_count']}",
                f"- Double annotated: {str(role['double_annotated']).lower()}",
                f"- Expected question/evidence pairs: {role['expected_record_count']}",
                f"- Supplied Role labels: {role['record_count']}",
                "- Role semantic quality reviewed by M8: no",
                "- Evidence Role IAA computed by M8: no",
            ]
        )
        if role["errors"]:
            lines.extend(["", "### Provenance audit errors", ""])
            lines.extend(f"- {error}" for error in role["errors"])
    return "\n".join(lines) + "\n"


def write_extension_reports(
    score_paths: Sequence[Path],
    context_path: Path,
    output_dir: Path,
    *,
    ratings_path: Path | None = None,
    rating_key_path: Path | None = None,
    rating_rubric_path: Path | None = None,
    rating_submission_manifest_path: Path | None = None,
    score_manifest_pairs: Sequence[tuple[Path, Path]] | None = None,
    score_source_triples: Sequence[tuple[Path, Path, Path]] | None = None,
    expected_experiment_manifest_path: Path | None = None,
    role_provenance: Mapping[str, Any] | None = None,
    allow_incomplete: bool = False,
) -> dict[str, Path]:
    """Build the combined package without altering existing score artifacts."""

    records = load_score_records(score_paths)
    contexts = load_experiment_conditions(context_path)
    frozen_lambdas = {
        context.lambda_weight
        for context in contexts
        if context.lambda_status == "frozen"
    }
    if len(frozen_lambdas) > 1:
        raise ValueError(
            "formal comparison requires one globally frozen lambda value: "
            f"found={sorted(frozen_lambdas)}"
        )
    joined = _join_records(records, contexts)
    _validate_experiment_versions(joined, allow_incomplete=allow_incomplete)
    groups = _group_records(joined)
    rating_paths = (
        ratings_path,
        rating_key_path,
        rating_rubric_path,
        rating_submission_manifest_path,
    )
    if any(path is not None for path in rating_paths) and not all(
        path is not None for path in rating_paths
    ):
        raise ValueError(
            "blinded ratings require ratings, rating-key, rubric, and sealed submission "
            "manifest files together"
        )
    ratings = load_level_adaptation_ratings(ratings_path) if ratings_path else []
    answer_keys = load_blinded_answer_keys(rating_key_path) if rating_key_path else []
    rubric = (
        load_level_adaptation_rubric(rating_rubric_path)
        if rating_rubric_path
        else None
    )
    if ratings_path is not None:
        assert rating_key_path is not None
        assert rating_rubric_path is not None
        assert rating_submission_manifest_path is not None
        assert rubric is not None
        _verify_blind_rating_submission(
            rating_submission_manifest_path,
            ratings_path,
            rating_key_path,
            rating_rubric_path,
            rating_count=len(ratings),
            key_count=len(answer_keys),
            rubric_version=rubric.rubric_version,
        )
    adaptation = _adaptation_summary(
        joined,
        ratings,
        answer_keys,
        rubric,
        ratings_supplied=ratings_path is not None,
        allow_incomplete=allow_incomplete,
    )
    comparisons = _lambda_comparisons(
        groups, adaptation, allow_incomplete=allow_incomplete
    )
    role = dict(
        role_provenance
        or {
            "status": "pending",
            "reason": "upstream_role_package_not_supplied",
        }
    )
    if role.get("status") == "failed" and not allow_incomplete:
        raise ValueError(
            "formal evaluation rejected failed Role-label provenance: "
            + "; ".join(str(item) for item in role.get("errors", []))
        )
    manifests_by_score, manifest_audit = _load_manifest_bindings(
        score_paths,
        score_manifest_pairs,
        allow_incomplete=allow_incomplete,
    )
    manifests_by_record = _validate_score_manifest_bindings(
        score_paths, manifests_by_score
    )
    _validate_joined_manifest_bindings(
        joined,
        manifests_by_record,
        allow_incomplete=allow_incomplete,
    )
    expected_experiments = (
        load_expected_experiment_manifest(expected_experiment_manifest_path)
        if expected_experiment_manifest_path is not None
        else None
    )
    experiment_coverage = _validate_expected_experiment_coverage(
        groups,
        expected_experiments,
        allow_incomplete=allow_incomplete,
    )
    score_source_audit = _load_score_source_bindings(
        score_paths,
        score_source_triples,
        allow_incomplete=allow_incomplete,
    )
    result = {
        "schema_version": "0.1",
        "record_count": len(joined),
        "frozen_lambda": next(iter(frozen_lambdas), None),
        "run_manifest_binding_status": {
            key: value for key, value in manifest_audit.items() if key != "bindings"
        },
        "run_manifest_bindings": manifest_audit["bindings"],
        "score_source_binding_status": {
            key: value
            for key, value in score_source_audit.items()
            if key != "bindings"
        },
        "score_source_bindings": score_source_audit["bindings"],
        "experiment_coverage": experiment_coverage,
        "groups": groups,
        "lambda_comparisons": comparisons,
        "level_adaptation": adaptation,
        "role_label_provenance": role,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "summary": output_dir / "evaluation_summary.json",
        "groups": output_dir / "experiment_groups.csv",
        "lambda": output_dir / "lambda_comparison.csv",
        "failures": output_dir / "failure_analysis.csv",
        "adaptation": output_dir / "level_adaptation_scores.json",
        "role_provenance": output_dir / "role_label_provenance_report.json",
        "markdown": output_dir / "evaluation_report.md",
    }
    paths["summary"].write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    paths["adaptation"].write_text(
        json.dumps(adaptation, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    paths["role_provenance"].write_text(
        json.dumps(role, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    paths["markdown"].write_text(_markdown(result), encoding="utf-8")
    with paths["groups"].open("w", encoding="utf-8", newline="") as stream:
        fieldnames = [
            *GROUP_IDENTITY_FIELDS,
            "sample_count",
            "metric",
            "numerator",
            "denominator",
            "value",
            "status",
            "excluded",
        ]
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        for group in groups:
            identity = {key: group[key] for key in GROUP_IDENTITY_FIELDS}
            for name, metric in group["metrics"].items():
                writer.writerow({**identity, "metric": name, **metric})
    with paths["lambda"].open("w", encoding="utf-8", newline="") as stream:
        fieldnames = [
            "mode",
            "execution_mode",
            "data_version",
            "split",
            "corpus_version",
            "chunk_version",
            "mapping_version",
            "index_version",
            "textbook_id",
            "student_level",
            "comparison_id",
            "metric",
            "baseline_condition_id",
            "frozen_condition_id",
            "baseline_lambda",
            "frozen_lambda",
            "baseline_value",
            "frozen_value",
            "delta",
            "status",
        ]
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(comparisons)
    with paths["failures"].open("w", encoding="utf-8", newline="") as stream:
        fieldnames = [
            *GROUP_IDENTITY_FIELDS,
            "failure_label",
            "count",
        ]
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        for group in groups:
            identity = {key: group[key] for key in GROUP_IDENTITY_FIELDS}
            for label, count in group["failure_label_counts"].items():
                writer.writerow(
                    {**identity, "failure_label": label, "count": count}
                )
    return paths
