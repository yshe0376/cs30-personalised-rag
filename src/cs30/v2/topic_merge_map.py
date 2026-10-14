"""Load and apply explicitly confirmed Topic title-to-ID merge decisions."""

from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_TOPIC_MERGE_MAP = (
    REPO_ROOT / "docs" / "topic-registry" / "topic_merge_map_v1.json"
)


@dataclass(frozen=True, slots=True)
class TopicMergeTarget:
    """The canonical Topic target and review provenance for one exact alias."""

    canonical_topic_id: str
    canonical_topic_title: str
    review_ids: tuple[str, ...]
    mapping_version: str


@dataclass(frozen=True, slots=True)
class TopicContextualAlias:
    """An exact alias that resolves only for one source section."""

    target: TopicMergeTarget
    definitions: tuple[str, ...]
    inherit_source_definitions_when_empty: bool = True


@dataclass(frozen=True, slots=True)
class TopicMergeMap:
    """Human-confirmed exact aliases, plus the decision-set metadata."""

    mapping_version: str
    status: str
    registry_frozen: bool
    decision_scope: str
    aliases: dict[str, TopicMergeTarget]
    contextual_aliases: dict[tuple[str, str], TopicContextualAlias]

    def target_for_normalized_title(self, normalized_title: str) -> TopicMergeTarget | None:
        """Resolve an already-normalized title without fuzzy matching."""

        return self.aliases.get(normalized_title)


def normalize_topic_alias(title: str) -> str:
    """Normalize a title for exact alias lookup, including common numbering."""

    normalized = unicodedata.normalize("NFKC", title)
    normalized = normalized.translate(
        str.maketrans(
            {
                "‘": "'",
                "’": "'",
                "‚": "'",
                "‛": "'",
                "＇": "'",
                "“": '"',
                "”": '"',
                "„": '"',
                "‟": '"',
                "«": '"',
                "»": '"',
                "‹": '"',
                "›": '"',
                "＂": '"',
            }
        )
    )
    normalized = re.sub(
        r"^\s*(?:(?:chapter|section)\s+)?\d+(?:\.\d+)*(?:[-–—]\d+(?:\.\d+)*)?"
        r"(?:\s*[.)]\s*|\s*[-–—:]\s+|\s+)",
        "",
        normalized,
        count=1,
        flags=re.IGNORECASE,
    )
    return " ".join(normalized.casefold().split())


def load_topic_merge_map(
    path: Path = DEFAULT_TOPIC_MERGE_MAP,
    *,
    normalizer: Callable[[str], str] = normalize_topic_alias,
) -> TopicMergeMap:
    """Load confirmed merges, rejecting unresolved or conflicting decisions."""

    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != "topic-merge-map-v1":
        raise ValueError(f"Unsupported Topic merge map schema: {path}")
    mapping_version = manifest.get("mapping_version")
    if not mapping_version:
        raise ValueError(f"Missing mapping_version in Topic merge map: {path}")

    aliases: dict[str, TopicMergeTarget] = {}
    for mapping in manifest.get("mappings", []):
        if mapping.get("decision_status") != "user_confirmed_merge":
            continue
        topic_id = mapping.get("canonical_topic_id")
        topic_title = mapping.get("canonical_topic_title")
        review_id = mapping.get("review_id")
        if not topic_id or not topic_title or not review_id:
            raise ValueError(f"Incomplete confirmed mapping in {path}")
        review_ids = tuple(mapping.get("review_ids", [review_id]))
        if review_id not in review_ids:
            review_ids = (review_id, *review_ids)
        target = TopicMergeTarget(
            canonical_topic_id=topic_id,
            canonical_topic_title=topic_title,
            review_ids=review_ids,
            mapping_version=mapping_version,
        )
        source_titles = [topic_title]
        for entry in mapping.get("source_entries", []):
            source_title = entry.get("source_normalized_title")
            if source_title:
                source_titles.append(source_title)
            source_titles.extend(entry.get("title_variants", []))

        for source_title in source_titles:
            alias = normalizer(source_title)
            if not alias:
                continue
            existing = aliases.get(alias)
            if existing and existing.canonical_topic_id != topic_id:
                raise ValueError(
                    f"Topic alias {alias!r} maps to both "
                    f"{existing.canonical_topic_id!r} and {topic_id!r}"
                )
            if existing:
                target = TopicMergeTarget(
                    canonical_topic_id=topic_id,
                    canonical_topic_title=topic_title,
                    review_ids=tuple(sorted(set(existing.review_ids + review_ids))),
                    mapping_version=mapping_version,
                )
            aliases[alias] = target

    contextual_aliases: dict[tuple[str, str], TopicContextualAlias] = {}
    for mapping in manifest.get("contextual_mappings", []):
        if mapping.get("decision_status") != "user_confirmed_merge":
            continue
        topic_id = mapping.get("canonical_topic_id")
        topic_title = mapping.get("canonical_topic_title")
        source_title = mapping.get("source_normalized_title")
        review_ids = tuple(mapping.get("review_ids", []))
        if not topic_id or not topic_title or not source_title or not review_ids:
            raise ValueError(f"Incomplete confirmed contextual mapping in {path}")
        target = TopicMergeTarget(
            canonical_topic_id=topic_id,
            canonical_topic_title=topic_title,
            review_ids=review_ids,
            mapping_version=mapping_version,
        )
        normalized_source_title = normalizer(source_title)
        for entry in mapping.get("source_entries", []):
            source_key = entry.get("section_key")
            if not source_key:
                raise ValueError(f"Contextual mapping is missing section_key in {path}")
            key = (normalized_source_title, source_key)
            alias = TopicContextualAlias(
                target=target,
                definitions=tuple(entry.get("definitions", [])),
                inherit_source_definitions_when_empty=bool(
                    entry.get("inherit_source_definitions_when_empty", True)
                ),
            )
            existing = contextual_aliases.get(key)
            if existing and existing.target.canonical_topic_id != topic_id:
                raise ValueError(
                    f"Contextual Topic alias {key!r} maps to both "
                    f"{existing.target.canonical_topic_id!r} and {topic_id!r}"
                )
            contextual_aliases[key] = alias

    return TopicMergeMap(
        mapping_version=mapping_version,
        status=manifest.get("status", "unknown"),
        registry_frozen=bool(manifest.get("registry_frozen", False)),
        decision_scope=manifest.get("decision_scope", ""),
        aliases=aliases,
        contextual_aliases=contextual_aliases,
    )


def resolve_topic_title(
    title: str,
    merge_map: TopicMergeMap,
    *,
    source_key: str | None = None,
    normalizer: Callable[[str], str] = normalize_topic_alias,
) -> TopicMergeTarget | None:
    """Resolve an exact alias, using source context when a key is supplied."""

    normalized_title = normalizer(title)
    if source_key is not None:
        contextual = merge_map.contextual_aliases.get((normalized_title, source_key))
        if contextual is not None:
            return contextual.target
    return merge_map.target_for_normalized_title(normalized_title)


def apply_topic_merge_map_to_groups(
    groups: list[dict[str, object]],
    merge_map: TopicMergeMap,
    *,
    normalizer: Callable[[str], str] = normalize_topic_alias,
) -> tuple[list[dict[str, object]], int]:
    """Collapse only confirmed aliases in exact-concept-group-shaped records.

    The returned count is the number of input groups matched by the map. Source
    definitions and section references are retained when mapped groups combine.
    """

    combined: dict[tuple[str, str], dict[str, object]] = {}
    targets: dict[tuple[str, str], TopicMergeTarget] = {}
    matched_group_count = 0

    def append_target_group(
        source_group: dict[str, object],
        target: TopicMergeTarget,
        sources: list[dict[str, object]],
        definitions: list[str],
        normalized_title: str,
    ) -> None:
        key = ("topic_id", target.canonical_topic_id)
        targets[key] = target
        current = combined.get(key)
        if current is None:
            current = {
                "normalized_title": normalizer(target.canonical_topic_title),
                "title_variants": [],
                "definitions": [],
                "source_section_count": 0,
                "sources": [],
                "canonical_topic_id": target.canonical_topic_id,
                "canonical_topic_title": target.canonical_topic_title,
                "topic_merge_mapping_version": target.mapping_version,
                "topic_merge_review_ids": list(target.review_ids),
                "source_normalized_titles": [],
            }
            combined[key] = current

        current["title_variants"] = sorted(
            set(current["title_variants"])
            | set(source_group.get("title_variants", [])),
            key=str.casefold,
        )
        current["definitions"] = sorted(
            set(current["definitions"]) | set(definitions),
            key=str.casefold,
        )
        current["sources"] = [*current["sources"], *sources]
        source_aliases = set(
            source_group.get("source_normalized_titles", [normalized_title])
        )
        current["source_normalized_titles"] = sorted(
            set(current["source_normalized_titles"]) | source_aliases
        )
        current["topic_merge_review_ids"] = sorted(
            set(current["topic_merge_review_ids"]) | set(target.review_ids)
        )

    for source_group in groups:
        normalized_title = str(source_group["normalized_title"])
        normalized_alias = normalizer(normalized_title)
        context_matches: list[tuple[dict[str, object], TopicContextualAlias]] = []
        remaining_sources: list[dict[str, object]] = []
        for source in source_group.get("sources", []):
            source_key = str(source.get("key", ""))
            contextual = merge_map.contextual_aliases.get(
                (normalized_alias, source_key)
            )
            if contextual is None:
                remaining_sources.append(source)
            else:
                context_matches.append((source, contextual))

        if context_matches:
            matched_group_count += 1
            if remaining_sources:
                unmatched_group = dict(source_group)
                unmatched_group["sources"] = remaining_sources
                unmatched_group["source_section_count"] = len(
                    {source.get("key") for source in remaining_sources}
                )
                combined[("title", normalized_title)] = unmatched_group
            for source, contextual in context_matches:
                definitions = list(contextual.definitions)
                if (
                    not definitions
                    and contextual.inherit_source_definitions_when_empty
                ):
                    definitions = list(source_group.get("definitions", []))
                append_target_group(
                    source_group,
                    contextual.target,
                    [source],
                    definitions,
                    normalized_title,
                )
            continue

        target = merge_map.aliases.get(normalized_alias)
        key = (
            ("topic_id", target.canonical_topic_id)
            if target is not None
            else ("title", normalized_title)
        )
        if target is None:
            combined[key] = dict(source_group)
            continue

        matched_group_count += 1
        append_target_group(
            source_group,
            target,
            list(source_group.get("sources", [])),
            list(source_group.get("definitions", [])),
            normalized_title,
        )

    for key, target in targets.items():
        current = combined[key]
        sources = current["sources"]
        unique_sections = {
            source.get("key")
            or (
                source.get("textbook_id"),
                source.get("chapter_id"),
                source.get("section_id"),
            )
            for source in sources
        }
        current["source_section_count"] = len(unique_sections)
        current["canonical_topic_id"] = target.canonical_topic_id
        current["canonical_topic_title"] = target.canonical_topic_title

    ordered_groups = sorted(
        combined.values(),
        key=lambda group: (
            str(group.get("normalized_title", "")),
            str(group.get("canonical_topic_id", "")),
        ),
    )
    return ordered_groups, matched_group_count
