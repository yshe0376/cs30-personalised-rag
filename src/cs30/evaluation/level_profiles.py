"""Load and validate frozen level profiles, checklists, and eligibility sidecars."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from cs30.contracts import StudentLevel

from .models import PersonalisationEligibility
from .v2_generation_models import (
    EligibilityPackage,
    EligibilityRecord,
    EvaluationEvidence,
    ProfileChecklistPackage,
)

PREFERRED_ROLES: dict[StudentLevel, frozenset[str]] = {
    StudentLevel.BEGINNER: frozenset({"definition", "example"}),
    StudentLevel.INTERMEDIATE: frozenset({"comparison", "application"}),
    StudentLevel.ADVANCED: frozenset({"derivation", "boundary"}),
}


def canonical_json_sha256(payload: object) -> str:
    """Hash JSON data with stable keys and separators."""

    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def profile_package_content_sha256(payload: Mapping[str, Any]) -> str:
    """Hash a profile package without its self-declared digest field."""

    content = dict(payload)
    content.pop("package_sha256", None)
    return canonical_json_sha256(content)


def load_profile_checklist_package(path: Path) -> ProfileChecklistPackage:
    """Load a frozen package and verify its declared content hash."""

    if not path.is_file():
        raise FileNotFoundError(path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path}: invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: expected one JSON object")
    expected = profile_package_content_sha256(payload)
    declared = payload.get("package_sha256")
    if declared != expected:
        raise ValueError(
            f"{path}: profile/checklist package hash mismatch: "
            f"declared={declared!r}, actual={expected!r}"
        )
    try:
        return ProfileChecklistPackage.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"{path}: invalid profile/checklist package: {exc}") from exc


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise FileNotFoundError(path)
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSON: {exc}") from exc
            if not isinstance(row, dict):
                raise ValueError(f"{path}:{line_number}: expected a JSON object")
            rows.append(row)
    return rows


def load_eligibility_package(
    path: Path,
    *,
    package_version: str,
    gold_version: str,
    gold_sha256: str,
    calibration_question_count: int,
    leader_calibration_record_sha256: str,
    label_provenance_record_sha256: str,
    expected_question_ids: Iterable[str] | None = None,
    require_resolved: bool = False,
) -> EligibilityPackage:
    """Load M3 labels without changing Gold or accepting silent coverage gaps."""

    try:
        records = [EligibilityRecord.model_validate(row) for row in _read_jsonl(path)]
        package = EligibilityPackage(
            package_version=package_version,
            gold_version=gold_version,
            gold_sha256=gold_sha256,
            calibration_question_count=calibration_question_count,
            leader_calibration_record_sha256=leader_calibration_record_sha256,
            label_provenance_record_sha256=label_provenance_record_sha256,
            records=records,
        )
    except ValidationError as exc:
        raise ValueError(f"{path}: invalid eligibility package: {exc}") from exc

    if expected_question_ids is not None:
        expected = set(expected_question_ids)
        actual = {record.question_id for record in package.records}
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        if missing or extra:
            raise ValueError(
                f"{path}: eligibility coverage mismatch: missing={missing}, extra={extra}"
            )
    if require_resolved:
        pending = sorted(
            record.question_id
            for record in package.records
            if record.eligibility is PersonalisationEligibility.PENDING
        )
        if pending:
            raise ValueError(f"{path}: reportable eligibility contains pending IDs: {pending}")
    return package


def eligible_levels(
    eligibility: PersonalisationEligibility,
) -> frozenset[StudentLevel]:
    """Return levels entering the main adaptation denominator.

    ``endpoint_only`` describes the expected separation between endpoint answers;
    it does not remove the intermediate-level observation from the main result.
    """

    if eligibility in {
        PersonalisationEligibility.FULL,
        PersonalisationEligibility.ENDPOINT_ONLY,
    }:
        return frozenset(StudentLevel)
    return frozenset()


def candidate_role_richness(
    rows: Iterable[tuple[str, StudentLevel, Sequence[EvaluationEvidence]]],
    *,
    top_k: int = 20,
) -> dict[str, Any]:
    """Check whether each frozen candidate pool contains a preferred level Role."""

    if top_k < 1:
        raise ValueError("top_k must be positive")
    details: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    seen: set[tuple[str, StudentLevel]] = set()
    for question_id, level, evidence in rows:
        key = (question_id, level)
        if key in seen:
            raise ValueError(
                "candidate richness requires one row per question/level: "
                f"{question_id}/{level.value}"
            )
        seen.add(key)
        preferred = PREFERRED_ROLES[level]
        top = sorted(evidence, key=lambda item: item.rank)[:top_k]
        matched = [item.evidence_id for item in top if item.role in preferred]
        available = bool(matched)
        counts[f"{level.value}_total"] += 1
        counts[f"{level.value}_available"] += int(available)
        details.append(
            {
                "question_id": question_id,
                "student_level": level.value,
                "preferred_roles": sorted(preferred),
                "candidate_count": len(top),
                "preferred_role_available": available,
                "matching_evidence_ids": matched,
            }
        )

    summary: dict[str, Any] = {}
    for level in StudentLevel:
        total = counts[f"{level.value}_total"]
        available = counts[f"{level.value}_available"]
        summary[level.value] = {
            "available": available,
            "total": total,
            "rate": available / total if total else None,
        }
    return {"top_k": top_k, "summary": summary, "records": details}
