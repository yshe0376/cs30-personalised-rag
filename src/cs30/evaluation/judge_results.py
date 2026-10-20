"""Validate cached judge outputs and reattach hidden experiment metadata."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from cs30.contracts import StudentLevel

from .evidence_support import (
    build_evidence_support_request,
    score_evidence_support,
    validate_evidence_support_output,
)
from .judge_runtime import configuration_sha256, request_cache_key
from .level_adaptation import (
    adaptation_evaluation_levels,
    adaptation_evaluation_record,
    build_adaptation_request,
    validate_adaptation_output,
)
from .level_discrimination import (
    build_discrimination_request,
    discrimination_summary,
    validate_discrimination_output,
)
from .level_profiles import canonical_json_sha256
from .v2_generation_models import (
    EvaluationMode,
    GenerationEvaluationInput,
    JudgeConfiguration,
    JudgeResultEnvelope,
    ProfileChecklistPackage,
)


def load_judge_envelopes(path: Path) -> dict[str, JudgeResultEnvelope]:
    """Load one cache/export and reject duplicate request identities."""

    envelopes: dict[str, JudgeResultEnvelope] = {}
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                envelope = JudgeResultEnvelope.model_validate_json(line)
            except ValueError as exc:
                raise ValueError(f"{path}:{line_number}: invalid judge result: {exc}") from exc
            if envelope.request_id in envelopes:
                raise ValueError(f"{path}:{line_number}: duplicate judge request_id")
            envelopes[envelope.request_id] = envelope
    return envelopes


def _validated_envelope(
    envelope: JudgeResultEnvelope | None,
    *,
    request: Any,
    configuration: JudgeConfiguration,
) -> tuple[Mapping[str, Any] | None, str | None]:
    if envelope is None:
        return None, "judge result not supplied"
    if envelope.task is not request.task or envelope.request_id != request.request_id:
        raise ValueError(f"{request.request_id}: judge envelope identity mismatch")
    if envelope.cache_key != request_cache_key(request):
        raise ValueError(f"{request.request_id}: judge cache key mismatch")
    if envelope.judge_config_version != configuration.config_version:
        raise ValueError(f"{request.request_id}: judge configuration version mismatch")
    if request.config_sha256 != configuration_sha256(configuration):
        raise ValueError(f"{request.request_id}: request configuration hash mismatch")
    if envelope.unresolved:
        return None, envelope.error or "judge result unresolved"
    if envelope.output is None:
        raise ValueError(f"{request.request_id}: resolved judge result has no output")
    return envelope.output, None


def assemble_judge_results(
    items: Sequence[GenerationEvaluationInput],
    package: ProfileChecklistPackage,
    configuration: JudgeConfiguration,
    envelopes: Mapping[str, JudgeResultEnvelope],
    *,
    cross_level_evaluation_ids: frozenset[str] = frozenset(),
    mode: EvaluationMode = EvaluationMode.DEVELOPMENT,
    reverse_adaptation_criteria: bool = False,
) -> dict[str, Any]:
    """Validate all supplied outputs and build experiment-aware result rows."""

    profiles = {profile.level: profile for profile in package.profiles}
    checklists = {checklist.level: checklist for checklist in package.checklists}
    adaptation: list[dict[str, Any]] = []
    discrimination: list[dict[str, Any]] = []
    evidence_support: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    expected_request_ids: set[str] = set()

    for item in items:
        if item.technical_failure or item.abstained or item.answer is None:
            continue

        for evaluated_level in adaptation_evaluation_levels(
            item,
            cross_level_evaluation_ids=cross_level_evaluation_ids,
        ):
            checklist = checklists[evaluated_level]
            criterion_order = None
            if reverse_adaptation_criteria:
                criterion_order = [
                    criterion.criterion_id for criterion in reversed(checklist.criteria)
                ]
            request = build_adaptation_request(
                item,
                profiles[evaluated_level],
                checklist,
                configuration,
                evaluated_level=evaluated_level,
                criterion_order=criterion_order,
                mode=mode,
            )
            expected_request_ids.add(request.request_id)
            raw, error = _validated_envelope(
                envelopes.get(request.request_id),
                request=request,
                configuration=configuration,
            )
            if raw is None:
                unresolved.append(
                    {
                        "evaluation_id": item.evaluation_id,
                        "dimension": "adaptation",
                        "evaluated_level": evaluated_level.value,
                        "reason": error,
                    }
                )
            else:
                output = validate_adaptation_output(
                    raw,
                    request=request,
                    answer=item.answer,
                    checklist=checklist,
                )
                record = adaptation_evaluation_record(item, evaluated_level, output)
                record["output_sha256"] = canonical_json_sha256(raw)
                adaptation.append(record)

        request = build_discrimination_request(
            item,
            package.profiles,
            configuration,
            mode=mode,
        )
        expected_request_ids.add(request.request_id)
        raw, error = _validated_envelope(
            envelopes.get(request.request_id), request=request, configuration=configuration
        )
        if raw is None:
            unresolved.append(
                {
                    "evaluation_id": item.evaluation_id,
                    "dimension": "discrimination",
                    "reason": error,
                }
            )
        else:
            output = validate_discrimination_output(raw, request=request, answer=item.answer)
            discrimination.append(
                {
                    "evaluation_id": item.evaluation_id,
                    "run_id": item.run_id,
                    "question_id": item.question_id,
                    "target_level": item.target_level.value,
                    "condition": item.condition.value,
                    "eligibility": item.eligibility.value,
                    "predicted_level": output.predicted_level.value,
                    "request_id": request.request_id,
                    "output_sha256": canonical_json_sha256(raw),
                }
            )

        request = build_evidence_support_request(
            item,
            configuration,
            mode=mode,
        )
        expected_request_ids.add(request.request_id)
        raw, error = _validated_envelope(
            envelopes.get(request.request_id), request=request, configuration=configuration
        )
        if raw is None:
            unresolved.append(
                {
                    "evaluation_id": item.evaluation_id,
                    "dimension": "evidence_support",
                    "reason": error,
                }
            )
        else:
            output = validate_evidence_support_output(raw, request=request, item=item)
            record = score_evidence_support(output)
            record.update(
                {
                    "evaluation_id": item.evaluation_id,
                    "run_id": item.run_id,
                    "question_id": item.question_id,
                    "target_level": item.target_level.value,
                    "condition": item.condition.value,
                    "eligibility": item.eligibility.value,
                    "output_sha256": canonical_json_sha256(raw),
                }
            )
            evidence_support.append(record)

    extras = sorted(set(envelopes) - expected_request_ids)
    if extras:
        raise ValueError(f"judge result export contains unexpected request IDs: {extras}")

    return {
        "adaptation": adaptation,
        "discrimination": discrimination,
        "evidence_support": evidence_support,
        "unresolved": unresolved,
        "expected_request_count": len(expected_request_ids),
        "supplied_request_count": len(envelopes),
    }


def _write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(dict(row), ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def write_judge_evaluation_outputs(
    result: Mapping[str, Any],
    output_dir: Path,
    *,
    provenance: Mapping[str, Any],
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "adaptation": output_dir / "adaptation_results.jsonl",
        "discrimination": output_dir / "discrimination_results.jsonl",
        "evidence_support": output_dir / "evidence_support_results.jsonl",
        "unresolved": output_dir / "judge_unresolved.jsonl",
        "manifest": output_dir / "judge_evaluation_manifest.json",
    }
    for name in ("adaptation", "discrimination", "evidence_support", "unresolved"):
        _write_jsonl(paths[name], list(result[name]))
    manifest = {
        "schema_version": "1.0",
        "expected_request_count": result["expected_request_count"],
        "supplied_request_count": result["supplied_request_count"],
        "provenance": dict(provenance),
        "output_sha256": {
            name: hashlib.sha256(paths[name].read_bytes()).hexdigest()
            for name in ("adaptation", "discrimination", "evidence_support", "unresolved")
        },
    }
    paths["manifest"].write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return paths


def load_judge_evaluation_outputs(output_dir: Path) -> dict[str, Any]:
    manifest_path = output_dir / "judge_evaluation_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    result: dict[str, Any] = {"manifest": manifest}
    for name in ("adaptation", "discrimination", "evidence_support", "unresolved"):
        path = output_dir / f"{name if name != 'unresolved' else 'judge_unresolved'}.jsonl"
        if name == "evidence_support":
            path = output_dir / "evidence_support_results.jsonl"
        elif name == "adaptation":
            path = output_dir / "adaptation_results.jsonl"
        elif name == "discrimination":
            path = output_dir / "discrimination_results.jsonl"
        expected = manifest["output_sha256"][name]
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError(f"judge evaluation {name} hash mismatch")
        result[name] = [
            json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line
        ]
    return result


def summarize_discrimination_rows(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    from .v2_generation_models import LevelGuess

    return discrimination_summary(
        (StudentLevel(str(row["target_level"])), LevelGuess(str(row["predicted_level"])))
        for row in rows
    )


def grouped_mean(
    rows: Sequence[Mapping[str, Any]], field: str, group_fields: Sequence[str]
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, ...], list[float]] = defaultdict(list)
    totals: dict[tuple[str, ...], int] = defaultdict(int)
    for row in rows:
        key = tuple(str(row[name]) for name in group_fields)
        totals[key] += 1
        if row.get(field) is not None:
            grouped[key].append(float(row[field]))
    return [
        {
            **dict(zip(group_fields, key, strict=True)),
            "answer_count": totals[key],
            "evaluable_count": len(grouped[key]),
            f"mean_{field}": (sum(grouped[key]) / len(grouped[key]) if grouped[key] else None),
        }
        for key in sorted(totals)
    ]
