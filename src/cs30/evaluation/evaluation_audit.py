"""De-duplicated blinded calibration and independent human-audit materials."""

from __future__ import annotations

import hashlib
import json
import random
import re
from collections import defaultdict, deque
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any, Literal

from pydantic import model_validator

from cs30.contracts.models import ContractModel, Identifier, NonEmptyText

from .level_profiles import canonical_json_sha256
from .v2_generation_models import ExperimentArm, GenerationEvaluationInput


class HumanAuditRating(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    blinded_answer_id: Identifier
    rater_id: Identifier
    adaptation_obvious_error: bool
    discrimination_obvious_error: bool
    evidence_support_obvious_error: bool
    notes: NonEmptyText | None = None
    profile_package_sha256: str
    rubric_sha256: str

    @model_validator(mode="after")
    def validate_hashes(self) -> HumanAuditRating:
        for name, value in (
            ("profile_package_sha256", self.profile_package_sha256),
            ("rubric_sha256", self.rubric_sha256),
        ):
            if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
                raise ValueError(f"{name} must be a lowercase SHA-256 hex digest")
        return self


def normalized_answer_text(answer: str) -> str:
    """Conservative de-duplication key; evaluation itself keeps the raw text."""

    return re.sub(r"\s+", " ", answer).strip().casefold()


def answer_text_sha256(answer: str) -> str:
    return hashlib.sha256(normalized_answer_text(answer).encode("utf-8")).hexdigest()


def _deduplicate_answers(
    items: Iterable[GenerationEvaluationInput],
) -> list[GenerationEvaluationInput]:
    unique: dict[str, GenerationEvaluationInput] = {}
    for item in sorted(items, key=lambda candidate: candidate.evaluation_id):
        if item.technical_failure or item.abstained or item.answer is None:
            continue
        key = answer_text_sha256(item.answer)
        unique.setdefault(key, item)
    return list(unique.values())


def _stratified_sample(
    items: Sequence[GenerationEvaluationInput],
    *,
    size: int,
    seed: int,
) -> list[GenerationEvaluationInput]:
    if size < 1:
        raise ValueError("sample size must be positive")
    if len(items) < size:
        raise ValueError(f"requested {size} unique answers but only {len(items)} are available")
    rng = random.Random(seed)
    grouped: dict[tuple[str, str], list[GenerationEvaluationInput]] = defaultdict(list)
    for item in items:
        grouped[(item.target_level.value, item.condition.value)].append(item)
    queues: list[deque[GenerationEvaluationInput]] = []
    for key in sorted(grouped):
        rows = grouped[key]
        rng.shuffle(rows)
        queues.append(deque(rows))
    rng.shuffle(queues)
    selected: list[GenerationEvaluationInput] = []
    while len(selected) < size:
        progressed = False
        for queue in queues:
            if queue and len(selected) < size:
                selected.append(queue.popleft())
                progressed = True
        if not progressed:
            break
    if len(selected) != size:
        raise RuntimeError("stratified sampler could not satisfy requested size")
    return selected


def prepare_calibration_and_audit(
    items: Iterable[GenerationEvaluationInput],
    output_dir: Path,
    *,
    calibration_size: int = 10,
    audit_size: int = 20,
    seed: int = 5703,
) -> dict[str, Path]:
    """Write disjoint public packets and a separate private identity key."""

    unique = _deduplicate_answers(items)
    calibration = _stratified_sample(unique, size=calibration_size, seed=seed)
    calibration_ids = {item.evaluation_id for item in calibration}
    remaining = [item for item in unique if item.evaluation_id not in calibration_ids]
    audit = _stratified_sample(remaining, size=audit_size, seed=seed + 1)
    if audit_size >= 12:
        audit_levels = {item.target_level for item in audit}
        audit_conditions = {item.condition for item in audit}
        if len(audit_levels) != 3 or audit_conditions != set(ExperimentArm):
            raise ValueError(
                "independent audit must cover all three levels and four main conditions"
            )

    used_blind_ids: set[str] = set()
    rng = random.Random(seed)

    def blind_id() -> str:
        while True:
            candidate = f"answer-{rng.getrandbits(64):016x}"
            if candidate not in used_blind_ids:
                used_blind_ids.add(candidate)
                return candidate

    public_rows: dict[str, list[dict[str, Any]]] = {"calibration": [], "audit": []}
    private_rows: list[dict[str, Any]] = []
    for packet_name, packet in (("calibration", calibration), ("audit", audit)):
        for item in packet:
            assert item.answer is not None
            blinded_answer_id = blind_id()
            public_rows[packet_name].append(
                {
                    "schema_version": "1.0",
                    "blinded_answer_id": blinded_answer_id,
                    "question_id": item.question_id,
                    "question": item.question,
                    "target_level": item.target_level.value,
                    "answer": item.answer,
                    "citation_ids": item.citation_ids,
                    "evidence": [
                        {
                            "evidence_id": evidence.evidence_id,
                            "text": evidence.text,
                            "source_locator": evidence.source_locator,
                        }
                        for evidence in item.evidence
                    ],
                    "adaptation_obvious_error": None,
                    "discrimination_obvious_error": None,
                    "evidence_support_obvious_error": None,
                    "rater_id": None,
                    "notes": None,
                }
            )
            private_rows.append(
                {
                    "schema_version": "1.0",
                    "packet": packet_name,
                    "blinded_answer_id": blinded_answer_id,
                    "evaluation_id": item.evaluation_id,
                    "run_id": item.run_id,
                    "condition": item.condition.value,
                    "lambda_weight": item.lambda_weight,
                    "generation_model_family": item.generation_model_family,
                    "generation_model_revision": item.generation_model_revision,
                    "answer_text_sha256": answer_text_sha256(item.answer),
                    "source_artifact_sha256": item.source_artifact_sha256,
                    "source_run_sha256": item.source_run_sha256,
                    "exact_answer_sha256": item.answer_sha256,
                }
            )

    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "calibration": output_dir / "judge_calibration_packet.jsonl",
        "audit": output_dir / "judge_independent_audit_packet.jsonl",
        "private_key": output_dir / "judge_audit_private_key.jsonl",
        "manifest": output_dir / "judge_audit_manifest.json",
    }
    for packet_name in ("calibration", "audit"):
        paths[packet_name].write_text(
            "".join(
                json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
                for row in public_rows[packet_name]
            ),
            encoding="utf-8",
        )
    paths["private_key"].write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in private_rows),
        encoding="utf-8",
    )
    manifest = {
        "schema_version": "1.0",
        "seed": seed,
        "deduplication": "normalized answer text sha256 across all questions and conditions",
        "unique_answer_count": len(unique),
        "calibration_count": len(calibration),
        "audit_count": len(audit),
        "audit_level_coverage": sorted({item.target_level.value for item in audit}),
        "audit_condition_coverage": sorted({item.condition.value for item in audit}),
        "calibration_sha256": hashlib.sha256(paths["calibration"].read_bytes()).hexdigest(),
        "audit_sha256": hashlib.sha256(paths["audit"].read_bytes()).hexdigest(),
        "private_key_sha256": hashlib.sha256(paths["private_key"].read_bytes()).hexdigest(),
        "identity_set_sha256": canonical_json_sha256(
            sorted(row["evaluation_id"] for row in private_rows)
        ),
        "packets_overlap": False,
        "condition_lambda_model_hidden_from_public_packets": True,
    }
    paths["manifest"].write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return paths


def summarize_human_audit(ratings: Sequence[HumanAuditRating]) -> dict[str, Any]:
    """Detect obvious errors without presenting the audit as an accuracy estimate."""

    blind_ids = [rating.blinded_answer_id for rating in ratings]
    if len(blind_ids) != len(set(blind_ids)):
        raise ValueError("human audit contains duplicate blinded_answer_id values")
    dimensions = (
        "adaptation_obvious_error",
        "discrimination_obvious_error",
        "evidence_support_obvious_error",
    )
    return {
        "rating_count": len(ratings),
        "purpose": "obvious-error detection only; not a population accuracy estimate",
        "obvious_error_counts": {
            dimension: sum(bool(getattr(rating, dimension)) for rating in ratings)
            for dimension in dimensions
        },
        "rater_ids": sorted({rating.rater_id for rating in ratings}),
        "profile_package_sha256_values": sorted(
            {rating.profile_package_sha256 for rating in ratings}
        ),
        "rubric_sha256_values": sorted({rating.rubric_sha256 for rating in ratings}),
    }
