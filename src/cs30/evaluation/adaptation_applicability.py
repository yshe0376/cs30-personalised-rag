"""Reviewed, package-bound applicability rules for adaptation judgments."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .level_profiles import canonical_json_sha256, profile_package_content_sha256
from .v2_generation_models import (
    AdaptationJudgeOutput,
    CriterionVerdict,
    JudgeRequest,
    LevelChecklist,
    LevelProfile,
    ProfileChecklistPackage,
)

FROZEN_PACKAGE_SHA256 = "1888c3b7fb6f2f0fd52dbe06455c40cef88ff8839ab47383a76d7c29a1088238"
POLICY_VERSION = "always-assessed-v1"

# Reviewed for this exact package in Leader decision #212. New packages need a new policy.
_REVIEWED_PACKAGES = {
    FROZEN_PACKAGE_SHA256: {
        "beginner": {
            "profile": "3e146ad86ce40275352448d852584b59da552a88fa003d7b473c9d366069a7f6",
            "checklist": "41d4303775fea83e93f02793e951d0cf9acdbac5b47e08aefa57dc582e18a618",
            "always": ("B1", "B2", "B4"),
        },
        "intermediate": {
            "profile": "739c10201dfb2606ce581e019d7354f80a69747b6ebe3f0fe59b7b9e485484a8",
            "checklist": "5832ae7565ecb94688fbebb6d2acde750cd617975685091429c9820c3a2e8fbf",
            "always": ("I1", "I2", "I3"),
        },
        "advanced": {
            "profile": "81b8bfecc95e82c0eeb16dac0d9566b8441c14b59f19bbfdc5836a3ed3c76df5",
            "checklist": "3eb3484c2fdfe2f225145bd75b956502adb38d79f4639dfbb25cf09f39a4606a",
            "always": ("A1", "A4"),
        },
    }
}


def _checklist_hash(criteria: list[dict[str, Any]]) -> str:
    """Checklist-order perturbations retain the same applicability policy."""
    return canonical_json_sha256(sorted(criteria, key=lambda row: row["criterion_id"]))


def make_applicability_binding(
    package: ProfileChecklistPackage,
    profile: LevelProfile,
    checklist: LevelChecklist,
) -> dict[str, Any] | None:
    """Bind a reviewed rule set to verified package/profile/checklist content.

    Legacy synthetic checklists without always-assessed wording retain their existing
    behavior; they never inherit the eight production criterion IDs by name alone.
    """
    actual_hash = profile_package_content_sha256(package.model_dump(mode="json"))
    if package.package_sha256 != actual_hash:
        raise ValueError("adaptation applicability package hash mismatch")
    policies = _REVIEWED_PACKAGES.get(actual_hash)
    if policies is None:
        if any("always assess" in row.description.casefold() for row in checklist.criteria):
            raise ValueError("no reviewed adaptation applicability policy for this package")
        return None
    binding = {"version": POLICY_VERSION, "profile_package_sha256": actual_hash}
    _bound_ids(
        binding,
        profile.model_dump(mode="json"),
        [row.model_dump(mode="json") for row in checklist.criteria],
    )
    return binding


def _bound_ids(binding: object, profile: object, criteria: object) -> frozenset[str]:
    if not isinstance(binding, Mapping) or binding.get("version") != POLICY_VERSION:
        raise ValueError("invalid adaptation applicability policy binding")
    digest = binding.get("profile_package_sha256")
    if not isinstance(digest, str):
        raise ValueError("invalid adaptation applicability package identity")
    policies = _REVIEWED_PACKAGES.get(digest)
    if policies is None:
        raise ValueError("no reviewed adaptation applicability policy for this package")
    if (
        not isinstance(profile, Mapping)
        or not isinstance(profile.get("level"), str)
        or profile["level"] not in policies
    ):
        raise ValueError("adaptation applicability profile is missing or unknown")
    policy = policies[profile["level"]]
    if not isinstance(criteria, list) or not all(
        isinstance(row, dict) and isinstance(row.get("criterion_id"), str) for row in criteria
    ):
        raise ValueError("adaptation applicability checklist is malformed")
    if canonical_json_sha256(profile) != policy["profile"]:
        raise ValueError("adaptation profile does not match the bound frozen package")
    if _checklist_hash(criteria) != policy["checklist"]:
        raise ValueError("adaptation checklist does not match the bound frozen package")
    return frozenset(policy["always"])


def always_assessed_ids(request: JudgeRequest) -> frozenset[str]:
    """Validate the binding before provider execution or response acceptance."""
    criteria = request.payload.get("checklist")
    binding = request.payload.get("applicability_policy")
    if binding is None:
        rows = criteria if isinstance(criteria, list) else []
        if any(
            isinstance(row, Mapping)
            and "always assess" in str(row.get("description", "")).casefold()
            for row in rows
        ):
            raise ValueError("always-assessed checklist requires a package-bound policy")
        return frozenset()
    return _bound_ids(binding, request.payload.get("target_profile"), criteria)


def validate_adaptation_applicability(request: JudgeRequest, output: AdaptationJudgeOutput) -> None:
    """Reject illegal N/A; the existing runner decides retries/unresolved status."""
    always = always_assessed_ids(request)
    invalid = [
        row.criterion_id
        for row in output.criteria
        if row.criterion_id in always and row.verdict is CriterionVerdict.NOT_APPLICABLE
    ]
    if invalid:
        raise ValueError(f"always-assessed criteria cannot be not_applicable: {', '.join(invalid)}")
