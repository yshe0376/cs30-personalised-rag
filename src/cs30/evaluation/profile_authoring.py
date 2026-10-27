"""M7 authoring and reviewed export; the M8 frozen-input contract stays strict."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from cs30.contracts.models import ContractModel, Identifier, NonEmptyText

from .level_profiles import profile_package_content_sha256
from .v2_generation_models import ProfileChecklistPackage


class DraftProfileChecklistPackage(ProfileChecklistPackage):
    """Reviewable content cannot be mistaken for a physics-reviewed frozen input."""

    frozen: Literal[False] = False
    physics_reviewer_ids: list[Identifier] = Field(default_factory=list, max_length=0)

    @model_validator(mode="after")
    def validate_authoring_content(self) -> DraftProfileChecklistPackage:
        if self.physics_review_waiver is not None:
            raise ValueError("a draft package cannot carry a physics review waiver")
        questions: set[tuple[str, str]] | None = None
        for profile in self.profiles:
            anchors = {(item.anchor_id, item.question) for item in profile.anchor_examples}
            if questions is not None and anchors != questions:
                raise ValueError("all levels must answer the same non-Gold anchor questions")
            questions = anchors
        for checklist in self.checklists:
            ids = [item.criterion_id for item in checklist.criteria]
            if len(ids) != len(set(ids)):
                raise ValueError("checklist criterion IDs must be unique")
        if self.package_sha256 != profile_package_content_sha256(self.model_dump(mode="json")):
            raise ValueError("draft profile/checklist package hash mismatch")
        return self


class ProfileReview(ContractModel):
    role: Literal["leader", "physics"]
    reviewer_id: Identifier | None
    status: Literal["pending", "approved", "rejected", "waived"]
    review_record_id: Identifier | None
    reviewed_at: datetime | None
    notes: NonEmptyText | None

    @model_validator(mode="after")
    def validate_approval(self) -> ProfileReview:
        if self.status == "approved":
            if not all((self.reviewer_id, self.review_record_id, self.reviewed_at, self.notes)):
                raise ValueError("approved reviews require identity, record, timestamp, and notes")
            if self.reviewed_at is not None and self.reviewed_at.utcoffset() is None:
                raise ValueError("approved review timestamps must include a timezone")
        if self.status == "waived":
            # A waiver names no physics reviewer; the Leader approval carries the decision.
            if self.role != "physics":
                raise ValueError("only the physics review can be waived")
            if self.reviewer_id is not None or self.review_record_id is not None:
                raise ValueError("a waived physics review must not name a reviewer or record")
            if self.notes is None:
                raise ValueError("a waived physics review requires the Leader's reason")
        return self


class ProfileReviewRecord(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    draft_package_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    reviews: list[ProfileReview] = Field(min_length=2, max_length=2)

    @model_validator(mode="after")
    def validate_roles(self) -> ProfileReviewRecord:
        if {review.role for review in self.reviews} != {"leader", "physics"}:
            raise ValueError("one Leader review and one M3 physics review are required")
        return self


def load_draft(path: Path) -> DraftProfileChecklistPackage:
    return DraftProfileChecklistPackage.model_validate_json(path.read_text(encoding="utf-8"))


def check_non_gold_anchors(
    draft: DraftProfileChecklistPackage, gold_paths: list[Path]
) -> dict[str, object]:
    """Check identity/text collisions only; never inspect Gold answers for authoring."""

    def normalize(value: str) -> str:
        return " ".join(re.findall(r"\w+", value.casefold()))

    anchors = draft.profiles[0].anchor_examples
    anchor_ids = {anchor.anchor_id for anchor in anchors}
    questions = {normalize(anchor.question) for anchor in anchors}
    sources = []
    for path in gold_paths:
        count = 0
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict) or not isinstance(row.get("question"), str):
                raise ValueError(f"{path}:{line_number}: expected a Gold question object")
            if row.get("question_id") in anchor_ids or normalize(row["question"]) in questions:
                raise ValueError(f"{path}:{line_number}: anchor collides with a Gold question")
            count += 1
        if not count:
            raise ValueError(f"{path}: empty Gold file")
        sources.append({
            "path": path.as_posix(),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "questions_checked": count,
        })
    return {
        "anchor_count": len(anchors),
        "gold_sources": sources,
        "exact_normalized_question_or_id_collisions": 0,
        "semantic_independence_requires_review": True,
    }


def freeze_reviewed_draft(
    draft: DraftProfileChecklistPackage, record: ProfileReviewRecord
) -> ProfileChecklistPackage:
    """Export only after actual Leader and M3 records approve this exact draft.

    The Leader may instead waive the M3 physics review. The waiver is written into
    the frozen package, so downstream reports can disclose it.
    """

    # Shared contract models are mutable, including nested lists. Recheck at the
    # export boundary so an in-memory edit cannot reuse an earlier approval.
    draft = DraftProfileChecklistPackage.model_validate(draft.model_dump(mode="json"))
    record = ProfileReviewRecord.model_validate(record.model_dump(mode="json"))
    if record.draft_package_sha256 != draft.package_sha256:
        raise ValueError("review record is bound to a different draft hash")
    reviews = {review.role: review for review in record.reviews}
    leader, physics = reviews["leader"], reviews["physics"]
    if leader.status != "approved" or physics.status not in {"approved", "waived"}:
        raise ValueError(
            "the Leader must approve, and the M3 physics review must be approved or waived, "
            "before freezing"
        )
    payload = draft.model_dump(mode="json")
    payload["frozen"] = True
    payload["author_ids"] = list(dict.fromkeys([*draft.author_ids, leader.reviewer_id]))
    if physics.status == "approved":
        if leader.reviewer_id == physics.reviewer_id:
            raise ValueError("Leader and physics review must use distinct reviewer identities")
        payload["physics_reviewer_ids"] = [physics.reviewer_id]
        payload.pop("physics_review_waiver", None)
    else:
        payload["physics_reviewer_ids"] = []
        payload["physics_review_waiver"] = {
            "waived_by": leader.reviewer_id,
            # Use the JSON form so the digest matches the serialized package.
            "decided_at": leader.model_dump(mode="json")["reviewed_at"],
            "reason": physics.notes,
            "decision_record": leader.review_record_id,
        }
    payload["package_sha256"] = profile_package_content_sha256(payload)
    return ProfileChecklistPackage.model_validate(payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("draft", type=Path)
    parser.add_argument("--gold", type=Path, nargs="+", required=True)
    parser.add_argument("--review-record", type=Path)
    parser.add_argument("--output", type=Path, help="export a reviewed frozen M8 package")
    args = parser.parse_args(argv)
    try:
        draft = load_draft(args.draft)
        collision_check = check_non_gold_anchors(draft, args.gold)
        result = {
            "package_version": draft.package_version,
            "draft_package_sha256": draft.package_sha256,
            "frozen": False,
            "reportable": False,
            "non_gold_check": collision_check,
        }
        if bool(args.output) != bool(args.review_record):
            raise ValueError("--output and --review-record must be supplied together")
        if args.output is not None:
            record = ProfileReviewRecord.model_validate_json(
                args.review_record.read_text(encoding="utf-8")
            )
            package = freeze_reviewed_draft(draft, record)
            receipt_path = args.output.with_suffix(".review.json")
            if args.output.resolve() in {
                args.draft.resolve(), args.review_record.resolve(),
                *(path.resolve() for path in args.gold),
            } or receipt_path.resolve() in {
                args.draft.resolve(), args.review_record.resolve(),
                *(path.resolve() for path in args.gold),
            }:
                raise ValueError("export must not overwrite source inputs")
            if args.output.exists() or receipt_path.exists():
                raise ValueError("export paths already exist; choose new output paths")
            receipt = {
                **result,
                "frozen": True,
                "package_sha256": package.package_sha256,
                "review_record_sha256": hashlib.sha256(args.review_record.read_bytes()).hexdigest(),
                "review_record": record.model_dump(mode="json"),
            }
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(package.model_dump_json(indent=2) + "\n", encoding="utf-8")
            receipt_path.write_text(
                json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            result = receipt
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError) as exc:
        parser.exit(2, f"error: {exc}\n")


if __name__ == "__main__":
    sys.exit(main())
