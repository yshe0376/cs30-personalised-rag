"""Freeze a fully reconciled Topic Registry as a versioned artifact.

This does not change the draft or the source decision log. It creates an
immutable registry copy, a frozen review packet, and a provenance manifest.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import date
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from cs30.v2.contracts.models import TopicRegistry  # noqa: E402


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return "sha256:" + digest.hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--draft",
        type=Path,
        default=REPOSITORY_ROOT / "artifacts/v2/topics/topic_registry_draft_v0.json",
    )
    parser.add_argument(
        "--review-packet",
        type=Path,
        default=REPOSITORY_ROOT
        / "artifacts/v2/topics/topic_registry_review_packet_v0.json",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPOSITORY_ROOT / "artifacts/v2/topics",
    )
    args = parser.parse_args()

    draft_data = json.loads(args.draft.read_text(encoding="utf-8"))
    packet = json.loads(args.review_packet.read_text(encoding="utf-8"))
    summary = packet.get("summary", {})
    blockers = {
        "M3 definition confirmations": summary.get(
            "topics_requiring_m3_definition_confirmation", 0
        ),
        "user definition reviews": summary.get(
            "topics_flagged_for_user_definition_review", 0
        ),
        "unresolved source sections": summary.get("unresolved_source_section_count", 0),
        "unresolved title seeds": summary.get("unresolved_title_seed_groups", 0),
    }
    nonzero = {name: count for name, count in blockers.items() if count != 0}
    if nonzero:
        raise SystemExit(f"registry freeze blocked by outstanding review: {nonzero}")

    draft = TopicRegistry.model_validate(draft_data)
    match = re.fullmatch(r"(.+)-draft", draft.topic_registry_version)
    if match is None:
        raise SystemExit(
            f"expected a -draft registry version, got {draft.topic_registry_version!r}"
        )
    version = match.group(1)
    file_version = "v" + version.removeprefix("topics-")
    registry_path = args.output_dir / f"topic_registry_{file_version}.json"
    packet_path = args.output_dir / f"topic_registry_review_packet_{file_version}.json"
    manifest_path = args.output_dir / f"topic_registry_freeze_manifest_{file_version}.json"
    if any(path.exists() for path in (registry_path, packet_path, manifest_path)):
        raise SystemExit(
            "a frozen artifact already exists for this version; refusing to overwrite"
        )

    frozen = draft.model_copy(update={"topic_registry_version": version})
    frozen_data = frozen.model_dump(mode="json")
    write_json(registry_path, frozen_data)

    frozen_packet = dict(packet)
    frozen_packet.update(
        {
            "status": "frozen_for_development_chunk_labeling",
            "topic_registry_version": version,
            "registry_file": registry_path.relative_to(REPOSITORY_ROOT).as_posix(),
            "frozen_at": date.today().isoformat(),
        }
    )
    write_json(packet_path, frozen_packet)

    tracked_sources = {
        "draft_registry": args.draft,
        "review_packet": args.review_packet,
        "definition_decisions": args.output_dir / "topic_definition_decisions_v0.json",
        "definition_reconciliation": args.output_dir
        / "topic_definition_reconciliation_v0.json",
        "manual_adjudications": args.output_dir
        / "topic_definition_manual_adjudications_v0.json",
        "title_seed_decisions": args.output_dir / "topic_title_seed_decisions_v0.json",
        "merge_map": REPOSITORY_ROOT / "docs/topic-registry/topic_merge_map_v1.json",
    }
    source_hashes = {
        name: sha256(path)
        for name, path in tracked_sources.items()
        if path.exists()
    }
    freeze_manifest = {
        "schema_version": "topic-registry-freeze-manifest-v1",
        "status": "frozen_for_development_chunk_labeling",
        "topic_registry_version": version,
        "registry_file": registry_path.relative_to(REPOSITORY_ROOT).as_posix(),
        "review_packet_file": packet_path.relative_to(REPOSITORY_ROOT).as_posix(),
        "frozen_at": date.today().isoformat(),
        "topic_count": len(frozen.topics),
        "review_summary": summary,
        "freeze_gate": {
            "m3_definition_confirmations_outstanding": blockers[
                "M3 definition confirmations"
            ],
            "user_definition_reviews_outstanding": blockers[
                "user definition reviews"
            ],
            "source_section_dispositions_outstanding": blockers[
                "unresolved source sections"
            ],
            "title_seed_dispositions_outstanding": blockers[
                "unresolved title seeds"
            ],
        },
        "development_corpus_scope": {
            "corpus_version": packet.get("generated_from", {}).get(
                "corpus_version"
            ),
            "corpus_hash": packet.get("generated_from", {}).get("corpus_hash"),
            "reportable": False,
            "note": (
                "This registry is eligible for development-corpus labeling. Production "
                "release requires reviewed labels on the final corpus."
            ),
        },
        "source_sha256": source_hashes,
        "registry_sha256": sha256(registry_path),
        "authorization_basis": (
            "The user authorized proceeding to the next workflow step "
            "in this conversation."
        ),
    }
    write_json(manifest_path, freeze_manifest)

    print(
        f"Froze {len(frozen.topics)} Topics as {version}; wrote "
        f"{registry_path.relative_to(REPOSITORY_ROOT).as_posix()}"
    )
    print(f"Freeze manifest: {manifest_path.relative_to(REPOSITORY_ROOT).as_posix()}")


if __name__ == "__main__":
    main()
