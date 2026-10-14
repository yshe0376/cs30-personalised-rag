"""Build a provisional Topic registry and its M3 review packet."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "v2" / "topics"
DEFAULT_AGGREGATE = DEFAULT_OUTPUT_DIR / "topic_section_concept_aggregate_merged_v23.json"
DEFAULT_TITLE_CANDIDATES = DEFAULT_OUTPUT_DIR / "topic_title_candidates.json"
DEFAULT_TITLE_DECISIONS = DEFAULT_OUTPUT_DIR / "topic_title_seed_decisions_v0.json"
DEFAULT_DEFINITION_DECISIONS = DEFAULT_OUTPUT_DIR / "topic_definition_decisions_v0.json"
DEFAULT_DEFINITION_RECONCILIATION = DEFAULT_OUTPUT_DIR / "topic_definition_reconciliation_v0.json"
DEFAULT_DEFINITION_ADJUDICATIONS = (
    DEFAULT_OUTPUT_DIR / "topic_definition_manual_adjudications_v0.json"
)
DEFAULT_PROPOSALS = DEFAULT_OUTPUT_DIR / "topic_section_proposals.jsonl"
DEFAULT_MERGE_MAP = REPO_ROOT / "docs" / "topic-registry" / "topic_merge_map_v1.json"
DEFAULT_CORPUS_MANIFEST = (
    REPO_ROOT
    / "artifacts"
    / "v2"
    / "textbooks"
    / "2.0.0-dev.m4-structure-v2-main-3553825"
    / "manifest.json"
)
REGISTRY_VERSION = "topics-0.2-draft"

_ARTICLE_RE = re.compile(r"^(?:the|a|an)\s+", re.IGNORECASE)
_TOKEN_RE = re.compile(r"[a-z0-9]+")
_COMPOSITE_TITLE_RE = re.compile(
    r",|\band\b|\bversus\b|\bvs\.?\b|\bapplications?\b|\bincluding\b|:|;",
    re.IGNORECASE,
)
_NON_TOPIC_HEADINGS = {
    "glossary",
    "key equations",
    "key terms",
    "connection for ap courses",
}


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as source:
        return [json.loads(line) for line in source if line.strip()]


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    temporary.replace(path)


def _normalized_title(value: str, normalizer: Any) -> str:
    return normalizer(value)


def _title_forms(value: str, normalizer: Any) -> dict[str, str]:
    """Return conservative article/plural variants for title-seed matching."""

    normalized = normalizer(value)
    forms = {normalized: "exact_normalized_title"}
    articleless = _ARTICLE_RE.sub("", normalized, count=1)
    if articleless != normalized:
        forms.setdefault(articleless, "leading_article_removed")

    for form, rule in tuple(forms.items()):
        words = form.split()
        if not words:
            continue
        final = words[-1]
        stems: list[str] = []
        if final.endswith("ies") and len(final) > 4:
            stems.append(final[:-3] + "y")
        if (
            final.endswith("s")
            and not final.endswith(("ss", "us", "is", "ics"))
            and len(final) > 3
        ):
            stems.append(final[:-1])
        if final.endswith(("ses", "xes", "zes", "ches", "shes")) and len(final) > 4:
            stems.append(final[:-2])
        for stem in stems:
            forms.setdefault(" ".join((*words[:-1], stem)), f"{rule}+simple_plural_normalized")
    return forms


def _slug(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_value.casefold()).strip("-")
    return slug or f"topic-{hashlib.sha256(value.encode('utf-8')).hexdigest()[:12]}"


def _contains_topic_phrase(title: str, topic_title: str, normalizer: Any) -> bool:
    title_tokens = _TOKEN_RE.findall(normalizer(title))
    topic_tokens = _TOKEN_RE.findall(normalizer(topic_title))
    if not topic_tokens or len(topic_tokens) > len(title_tokens):
        return False

    def word_forms(word: str) -> set[str]:
        forms = {word}
        if word.endswith("ies") and len(word) > 4:
            forms.add(word[:-3] + "y")
        if word.endswith(("ses", "xes", "zes", "ches", "shes")) and len(word) > 4:
            forms.add(word[:-2])
        if (
            word.endswith("s")
            and not word.endswith(("ss", "us", "is", "ics"))
            and len(word) > 3
        ):
            forms.add(word[:-1])
        return forms

    def same_word(left: str, right: str) -> bool:
        return bool(word_forms(left) & word_forms(right))

    for start in range(len(title_tokens) - len(topic_tokens) + 1):
        if all(
            same_word(title_tokens[start + offset], topic_token)
            for offset, topic_token in enumerate(topic_tokens)
        ):
            return True
    return False


def _source_reference(source: dict[str, Any], section_key: str | None = None) -> dict[str, str]:
    ref = {
        key: str(source.get(key) or "")
        for key in ("textbook_id", "chapter_id", "section_id", "section_title")
    }
    if section_key:
        ref["section_key"] = section_key
    return ref


def build_registry_draft(
    aggregate: dict[str, Any],
    title_candidates: dict[str, Any],
    title_decisions: dict[str, Any],
    proposal_records: list[dict[str, Any]],
    merge_map: Any,
    corpus_manifest: dict[str, Any],
    definition_decisions: dict[str, Any] | None = None,
    definition_reconciliation: dict[str, Any] | None = None,
    definition_adjudications: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Create a contract-shaped draft registry plus a provenance-rich review packet."""

    from cs30.v2.contracts.models import Topic, TopicRegistry
    from cs30.v2.topic_merge_map import normalize_topic_alias
    from scripts.run_topic_section_proposals import normalize_concept_title

    groups = aggregate["exact_concept_groups"]
    decisions_by_normalized_title: dict[str, dict[str, Any]] = {}
    for decision in title_decisions.get("decisions", []):
        decision_title = str(decision.get("candidate_title") or "")
        normalized_decision_title = normalize_topic_alias(decision_title)
        if not normalized_decision_title:
            raise ValueError("title-seed decision has an empty candidate_title")
        if normalized_decision_title in decisions_by_normalized_title:
            raise ValueError(f"duplicate title-seed decision: {decision_title!r}")
        decisions_by_normalized_title[normalized_decision_title] = decision
    confirmed_definitions_by_topic_id: dict[str, dict[str, Any]] = {}
    source_anomaly_resolution: dict[str, Any] | None = None
    for decision in (definition_decisions or {}).get("decisions", []):
        decision_type = str(decision.get("decision_type") or "")
        if decision_type == "user_confirmed_topic_definition":
            topic_id = str(decision.get("topic_id") or "")
            canonical_definition = str(decision.get("canonical_definition_en") or "")
            if not topic_id or not canonical_definition:
                raise ValueError(
                    "confirmed Topic definition needs topic_id and "
                    "canonical_definition_en"
                )
            if topic_id in confirmed_definitions_by_topic_id:
                raise ValueError(f"duplicate confirmed Topic definition: {topic_id}")
            confirmed_definitions_by_topic_id[topic_id] = decision
        elif decision_type == "source_anomaly_definition_routing":
            if source_anomaly_resolution is not None:
                raise ValueError("only one source anomaly resolution is currently supported")
            source_anomaly_resolution = decision
    assistant_decisions_by_topic_id: dict[str, dict[str, Any]] = {}
    uncertain_decisions_by_topic_id: dict[str, dict[str, Any]] = {}
    for decision in (definition_reconciliation or {}).get("decisions", []):
        topic_id = str(decision.get("topic_id") or "")
        decision_type = str(decision.get("decision_type") or "")
        if decision_type == "assistant_auto_resolve_candidate":
            if not topic_id or topic_id in assistant_decisions_by_topic_id:
                raise ValueError(f"duplicate or empty assistant definition decision: {topic_id}")
            assistant_decisions_by_topic_id[topic_id] = decision
        elif decision_type == "needs_user_review":
            if not topic_id or topic_id in uncertain_decisions_by_topic_id:
                raise ValueError(f"duplicate or empty uncertain definition decision: {topic_id}")
            uncertain_decisions_by_topic_id[topic_id] = decision
    adjudications_by_topic_id: dict[str, dict[str, Any]] = {}
    for adjudication in (definition_adjudications or {}).get("adjudications", []):
        topic_id = str(adjudication.get("topic_id") or "")
        if not topic_id or topic_id in adjudications_by_topic_id:
            raise ValueError(f"duplicate or empty Topic definition adjudication: {topic_id}")
        selected_definition = str(adjudication.get("selected_definition") or "")
        selected_index = adjudication.get("selected_candidate_index")
        if not selected_definition or not isinstance(selected_index, int):
            raise ValueError(f"incomplete Topic definition adjudication: {topic_id}")
        adjudications_by_topic_id[topic_id] = adjudication
        assistant_decisions_by_topic_id[topic_id] = {
            **adjudication,
            "decision_type": "assistant_auto_resolve_candidate",
        }
        uncertain_decisions_by_topic_id.pop(topic_id, None)
    group_by_id: dict[str, dict[str, Any]] = {}
    group_key_by_id: dict[str, str] = {}
    topic_ids: dict[str, str] = {}
    used_ids: dict[str, str] = {}

    # Reserve human-confirmed IDs first so an independent slug cannot take one.
    for group in groups:
        if not group.get("canonical_topic_id"):
            continue
        group_key = str(group["canonical_topic_id"])
        topic_id = group_key
        if topic_id in used_ids and used_ids[topic_id] != group_key:
            raise ValueError(f"duplicate confirmed Topic ID: {topic_id}")
        used_ids[topic_id] = group_key
        topic_ids[group_key] = topic_id
        group_by_id[topic_id] = group
        group_key_by_id[topic_id] = group_key

    for group in groups:
        if group.get("canonical_topic_id"):
            continue
        group_key = str(group["normalized_title"])
        if group_key in topic_ids:
            raise ValueError(f"duplicate aggregate Topic key: {group_key}")
        base = _slug(group_key)
        topic_id = base
        if topic_id in used_ids and used_ids[topic_id] != group_key:
            topic_id = f"{base}-{hashlib.sha256(group_key.encode()).hexdigest()[:8]}"
        while topic_id in used_ids and used_ids[topic_id] != group_key:
            topic_id = f"{base}-{hashlib.sha256((group_key + topic_id).encode()).hexdigest()[:10]}"
        used_ids[topic_id] = group_key
        topic_ids[group_key] = topic_id
        group_by_id[topic_id] = group
        group_key_by_id[topic_id] = group_key

    contextual_names = {alias for alias, _ in merge_map.contextual_aliases}
    alias_to_group_keys: dict[str, set[str]] = defaultdict(set)
    for group in groups:
        group_key = str(group.get("canonical_topic_id") or group["normalized_title"])
        aliases = {
            str(group.get("normalized_title", "")),
            *[str(title) for title in group.get("title_variants", [])],
            *[str(title) for title in group.get("source_normalized_titles", [])],
        }
        if group.get("canonical_topic_title"):
            aliases.add(str(group["canonical_topic_title"]))
        for alias in aliases:
            normalized = normalize_topic_alias(alias)
            if normalized and normalized not in contextual_names:
                alias_to_group_keys[normalized].add(group_key)

    # The map is authoritative for confirmed global aliases; context-only aliases
    # remain source-keyed and are never promoted to global title aliases here.
    for alias, target in merge_map.aliases.items():
        if target.canonical_topic_id in group_key_by_id:
            alias_to_group_keys[alias].add(group_key_by_id[target.canonical_topic_id])

    group_key_by_normalized = {
        normalize_concept_title(str(group["normalized_title"])): str(
            group.get("canonical_topic_id") or group["normalized_title"]
        )
        for group in groups
    }

    def group_key_for_concept(title: str, section_key: str) -> str:
        normalized = normalize_topic_alias(title)
        contextual = merge_map.contextual_aliases.get((normalized, section_key))
        if contextual is not None:
            target_key = group_key_by_id.get(contextual.target.canonical_topic_id)
            if target_key is not None:
                return target_key
        target = merge_map.aliases.get(normalized)
        if target is not None:
            target_key = group_key_by_id.get(target.canonical_topic_id)
            if target_key is not None:
                return target_key
        key = group_key_by_normalized.get(normalize_concept_title(title))
        if key is not None:
            return key
        exact_keys = alias_to_group_keys.get(normalized, set())
        if len(exact_keys) == 1:
            return next(iter(exact_keys))
        raise ValueError(f"Concept has no unique aggregate Topic: {title!r} in {section_key}")

    title_counts: dict[str, Counter[str]] = defaultdict(Counter)
    definition_counts: dict[str, Counter[str]] = defaultdict(Counter)
    definition_sections: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    mention_sections: dict[str, set[str]] = defaultdict(set)
    records_by_identity: dict[tuple[str, str, str], dict[str, Any]] = {}
    records_by_key: dict[str, dict[str, Any]] = {}
    for record in proposal_records:
        source = record["source"]
        identity = (
            str(source.get("textbook_id") or ""),
            str(source.get("chapter_id") or ""),
            str(source.get("section_id") or ""),
        )
        if identity in records_by_identity:
            raise ValueError(f"duplicate proposal source identity: {identity!r}")
        records_by_identity[identity] = record
        records_by_key[str(record["key"])] = record
        if record.get("status") != "ok":
            continue
        for concept in record.get("concepts", []):
            group_key = group_key_for_concept(concept["title"], str(record["key"]))
            title_counts[group_key][concept["title"]] += 1
            definition_counts[group_key][concept["definition"]] += 1
            definition_sections[group_key][concept["definition"]].add(str(record["key"]))
            mention_sections[group_key].add(str(record["key"]))

    # Resolve each exact group to its stable provisional ID and initialize provenance.
    refs_by_group: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for group in groups:
        group_key = str(group.get("canonical_topic_id") or group["normalized_title"])
        for source in group.get("sources", []):
            section_key = str(source.get("key") or "")
            if not section_key:
                continue
            refs_by_group[group_key].setdefault(
                section_key,
                {
                    **_source_reference(source, section_key),
                    "source_roles": [],
                },
            )["source_roles"].append("model_concept_proposal")

    seed_matches: list[dict[str, Any]] = []
    mapped_title_seed_groups: list[dict[str, Any]] = []
    retained_standalone_title_seed_groups: list[dict[str, Any]] = []
    added_standalone_title_seed_groups: list[dict[str, Any]] = []
    unresolved_seeds: list[dict[str, Any]] = []
    excluded_seeds: list[dict[str, Any]] = []
    seed_match_counts: Counter[str] = Counter()
    title_seed_entries_by_group: dict[str, list[dict[str, Any]]] = defaultdict(list)
    title_seed_contexts_by_group: dict[str, list[dict[str, Any]]] = defaultdict(list)
    standalone_seed_entries_by_group: dict[str, list[dict[str, Any]]] = defaultdict(list)
    standalone_updates_by_topic_id: dict[str, dict[str, Any]] = {}
    new_standalone_topic_specs: list[dict[str, Any]] = []
    applied_title_decisions: set[str] = set()
    title_decision_counts: Counter[str] = Counter()

    def candidate_group_keys(title: str) -> tuple[set[str], str]:
        normalized = normalize_topic_alias(title)
        exact = alias_to_group_keys.get(normalized, set())
        if len(exact) == 1:
            return set(exact), "exact_normalized_title_or_alias"
        if len(exact) > 1:
            return set(), "ambiguous_exact_alias"

        forms = _title_forms(title, normalize_topic_alias)
        matched: set[str] = set()
        rules: set[str] = set()
        for form, rule in forms.items():
            group_keys = alias_to_group_keys.get(form, set())
            matched.update(group_keys)
            if group_keys:
                rules.add(rule)
        if len(matched) == 1:
            used_article_rule = any("leading_article_removed" in rule for rule in rules)
            used_plural_rule = any("simple_plural_normalized" in rule for rule in rules)
            if used_article_rule and used_plural_rule:
                rule = "leading_article_and_plural_normalized"
            elif used_article_rule:
                rule = "leading_article_removed"
            elif used_plural_rule:
                rule = "simple_plural_normalized"
            else:
                rule = "normalized_title_variant"
            return matched, rule
        if len(matched) > 1:
            return set(), "ambiguous_title_variant"

        # A context-bound alias can be resolved only if every occurrence of this
        # section-title seed has the same confirmed source-specific destination.
        contextual_target_ids: set[str] = set()
        matched_context_rows = 0
        for source in seed_source_rows:
            record = records_by_identity.get(
                (
                    str(source.get("textbook_id") or ""),
                    str(source.get("chapter_id") or ""),
                    str(source.get("section_id") or ""),
                )
            )
            if record is None:
                continue
            contextual = merge_map.contextual_aliases.get((normalized, str(record["key"])) )
            if contextual is not None:
                contextual_target_ids.add(contextual.target.canonical_topic_id)
                matched_context_rows += 1
        if matched_context_rows == len(seed_source_rows) and len(contextual_target_ids) == 1:
            topic_id = next(iter(contextual_target_ids))
            group_key = group_key_by_id.get(topic_id)
            if group_key is not None:
                return {group_key}, "confirmed_source_context"
        return set(), "no_exact_topic_match"

    for seed in title_candidates.get("candidates", []):
        seed_source_rows = seed.get("source_sections", [])
        seed_title = str(seed["candidate_title"])
        matched_keys, match_rule = candidate_group_keys(seed_title)
        source_refs: list[dict[str, str]] = []
        related_group_keys: set[str] = set()
        related_group_keys_by_source: dict[str, set[str]] = defaultdict(set)
        for source in seed_source_rows:
            identity = (
                str(source.get("textbook_id") or ""),
                str(source.get("chapter_id") or ""),
                str(source.get("section_id") or ""),
            )
            record = records_by_identity.get(identity)
            section_key = str(record["key"]) if record else ""
            source_refs.append(_source_reference(source, section_key or None))
            if record and record.get("status") == "ok":
                for concept in record.get("concepts", []):
                    group_key = group_key_for_concept(concept["title"], section_key)
                    related_group_keys.add(group_key)
                    related_group_keys_by_source[section_key].add(group_key)

        normalized_seed = normalize_topic_alias(seed_title)
        candidate_row: dict[str, Any] = {
            "candidate_title": seed_title,
            "normalized_title": seed.get("normalized_title", normalized_seed),
            "source_section_count": seed.get("source_section_count", len(source_refs)),
            "source_sections": source_refs,
        }
        related_topics = [
            {
                "topic_id": topic_ids[group_key],
                "title": (
                    group_by_id[topic_ids[group_key]].get("canonical_topic_title")
                    or max(
                        title_counts[group_key],
                        key=lambda title: (title_counts[group_key][title], title.casefold()),
                    )
                ),
            }
            for group_key in sorted(related_group_keys, key=lambda key: topic_ids[key])
        ]
        heading_key = " ".join(_TOKEN_RE.findall(normalized_seed))
        if heading_key in _NON_TOPIC_HEADINGS:
            candidate_row.update(
                status="excluded_non_topic_heading",
                reason=(
                    "Document or teaching-material container title; "
                    "it is not itself a physics concept."
                ),
            )
            excluded_seeds.append(candidate_row)
            continue

        manual_decision = decisions_by_normalized_title.get(normalized_seed)
        if manual_decision is not None:
            applied_title_decisions.add(normalized_seed)
            disposition = str(manual_decision.get("disposition") or "")
            decision_source = str(
                manual_decision.get("decision_source")
                or "assistant_high_confidence_review_user_authorized"
            )
            candidate_row["decision_source"] = decision_source
            candidate_row["decision_basis"] = decision_source
            candidate_row["decision_rationale"] = str(manual_decision.get("rationale") or "")
            if not candidate_row["decision_rationale"]:
                raise ValueError(f"title-seed decision has no rationale: {seed_title!r}")
            if disposition == "map_to_existing_topic":
                target_title = normalize_topic_alias(str(manual_decision.get("topic_title") or ""))
                targets = [
                    topic
                    for topic in related_topics
                    if normalize_topic_alias(topic["title"]) == target_title
                ]
                if not target_title or len(targets) != 1:
                    raise ValueError(
                        "title-seed decision target is not a unique related Topic for "
                        f"{seed_title!r}"
                    )
                target = targets[0]
                group_key = group_key_by_id[target["topic_id"]]
                candidate_row.update(
                    status="matched_existing_topic",
                    topic_id=target["topic_id"],
                    match_rule="high_confidence_title_alias",
                )
                seed_matches.append(candidate_row)
                seed_match_counts["high_confidence_title_alias"] += 1
                title_seed_entries_by_group[group_key].append(candidate_row)
                for source_ref in source_refs:
                    section_key = source_ref.get("section_key")
                    if not section_key:
                        continue
                    ref = refs_by_group[group_key].setdefault(
                        section_key,
                        {**source_ref, "source_roles": []},
                    )
                    if "section_title_seed" not in ref["source_roles"]:
                        ref["source_roles"].append("section_title_seed")
                title_decision_counts[disposition] += 1
                continue
            if disposition == "map_to_existing_topics":
                target_ids = [str(topic_id) for topic_id in manual_decision.get("topic_ids", [])]
                map_all_source_ids = {
                    str(topic_id)
                    for topic_id in manual_decision.get("map_to_all_source_sections_topic_ids", [])
                }
                if not target_ids or len(target_ids) != len(set(target_ids)):
                    raise ValueError(
                        "multi-topic mapping must have unique topic_ids: "
                        f"{seed_title!r}"
                    )
                if not map_all_source_ids.issubset(set(target_ids)):
                    raise ValueError(
                        "all-source mapping IDs must be selected targets: "
                        f"{seed_title!r}"
                    )
                target_rows: list[dict[str, Any]] = []
                for target_id in target_ids:
                    if target_id not in group_key_by_id:
                        raise ValueError(
                            "title-seed mapping target does not exist in the draft "
                            f"registry: {target_id}"
                        )
                    group_key = group_key_by_id[target_id]
                    target_group = group_by_id[target_id]
                    target_title = str(
                        target_group.get("canonical_topic_title")
                        or max(
                            title_counts[group_key],
                            key=lambda title: (title_counts[group_key][title], title.casefold()),
                        )
                    )
                    mapped_refs: list[dict[str, str]] = []
                    for source_ref in source_refs:
                        section_key = source_ref.get("section_key", "")
                        appears_in_source = group_key in related_group_keys_by_source.get(
                            section_key, set()
                        )
                        applies_to_all_sources = target_id in map_all_source_ids
                        if not section_key or not (appears_in_source or applies_to_all_sources):
                            continue
                        mapped_refs.append(source_ref)
                        ref = refs_by_group[group_key].setdefault(
                            section_key,
                            {**source_ref, "source_roles": []},
                        )
                        if "section_title_context" not in ref["source_roles"]:
                            ref["source_roles"].append("section_title_context")
                    if not mapped_refs:
                        raise ValueError(
                            "mapping target has no source-section evidence: "
                            f"{seed_title!r} -> {target_id}"
                        )
                    context = {
                        "candidate_title": seed_title,
                        "decision_source": decision_source,
                        "rationale": candidate_row["decision_rationale"],
                        "source_sections": mapped_refs,
                    }
                    title_seed_contexts_by_group[group_key].append(context)
                    target_rows.append(
                        {
                            "topic_id": target_id,
                            "title": target_title,
                            "source_sections": mapped_refs,
                        }
                    )
                candidate_row.update(
                    status="mapped_to_existing_topics",
                    mapped_topics=target_rows,
                )
                mapped_title_seed_groups.append(candidate_row)
                title_decision_counts[disposition] += 1
                continue
            if disposition == "retain_as_standalone_existing_topic":
                target_id = str(manual_decision.get("topic_id") or "")
                if target_id not in group_key_by_id:
                    raise ValueError(
                        f"standalone Topic target does not exist in the draft registry: {target_id}"
                    )
                if target_id in standalone_updates_by_topic_id:
                    raise ValueError(f"duplicate standalone Topic update: {target_id}")
                group_key = group_key_by_id[target_id]
                for source_ref in source_refs:
                    section_key = source_ref.get("section_key", "")
                    if not section_key:
                        continue
                    ref = refs_by_group[group_key].setdefault(
                        section_key,
                        {**source_ref, "source_roles": []},
                    )
                    if "section_title_seed" not in ref["source_roles"]:
                        ref["source_roles"].append("section_title_seed")
                candidate_row.update(
                    status="retained_as_standalone_topic",
                    topic_id=target_id,
                    topic_title=manual_decision.get("topic_title"),
                )
                standalone_updates_by_topic_id[target_id] = {
                    **manual_decision,
                    "source_sections": source_refs,
                }
                standalone_seed_entries_by_group[group_key].append(candidate_row)
                retained_standalone_title_seed_groups.append(candidate_row)
                title_decision_counts[disposition] += 1
                continue
            if disposition == "add_standalone_topic":
                target_id = str(manual_decision.get("topic_id") or "")
                if not target_id or target_id in group_by_id or any(
                    row.get("topic_id") == target_id for row in new_standalone_topic_specs
                ):
                    raise ValueError(
                        "new standalone Topic ID is empty or already used: "
                        f"{target_id}"
                    )
                if not manual_decision.get("topic_title") or not manual_decision.get(
                    "draft_definition"
                ):
                    raise ValueError(
                        "new standalone Topic needs title and draft definition: "
                        f"{seed_title!r}"
                    )
                candidate_row.update(
                    status="added_standalone_topic",
                    topic_id=target_id,
                    topic_title=str(manual_decision["topic_title"]),
                    draft_definition=str(manual_decision["draft_definition"]),
                )
                new_standalone_topic_specs.append(
                    {
                        **manual_decision,
                        "source_sections": source_refs,
                        "candidate_row": candidate_row,
                    }
                )
                added_standalone_title_seed_groups.append(candidate_row)
                title_decision_counts[disposition] += 1
                continue
            if disposition in {"exclude_composite_section_title", "exclude_non_topic_heading"}:
                component_titles = {
                    normalize_topic_alias(str(title))
                    for title in manual_decision.get("component_topic_titles", [])
                }
                components = [
                    topic
                    for topic in related_topics
                    if normalize_topic_alias(topic["title"]) in component_titles
                ]
                if disposition == "exclude_composite_section_title" and (
                    len(component_titles) < 2 or len(components) != len(component_titles)
                ):
                    raise ValueError(
                        f"composite decision must name at least two related Topics: {seed_title!r}"
                    )
                candidate_row.update(
                    status=(
                        "excluded_composite_section_title"
                        if disposition == "exclude_composite_section_title"
                        else "excluded_non_topic_heading"
                    ),
                    reason=candidate_row["decision_rationale"],
                )
                if components:
                    candidate_row["related_topics"] = components
                excluded_seeds.append(candidate_row)
                title_decision_counts[disposition] += 1
                continue
            raise ValueError(f"unsupported title-seed decision {disposition!r} for {seed_title!r}")

        if len(matched_keys) == 1:
            group_key = next(iter(matched_keys))
            topic_id = topic_ids[group_key]
            candidate_row.update(
                status="matched_existing_topic",
                topic_id=topic_id,
                match_rule=match_rule,
            )
            seed_matches.append(candidate_row)
            seed_match_counts[match_rule] += 1
            title_seed_entries_by_group[group_key].append(candidate_row)
            for source_ref in source_refs:
                section_key = source_ref.get("section_key")
                if not section_key:
                    continue
                ref = refs_by_group[group_key].setdefault(
                    section_key,
                    {**source_ref, "source_roles": []},
                )
                if "section_title_seed" not in ref["source_roles"]:
                    ref["source_roles"].append("section_title_seed")
            continue

        component_topics = [
            topic
            for topic in related_topics
            if _contains_topic_phrase(seed_title, topic["title"], normalize_topic_alias)
        ]
        if len({topic["topic_id"] for topic in component_topics}) >= 2:
            candidate_row.update(
                status="excluded_composite_section_title",
                reason=(
                    "The heading explicitly lists multiple distinct Topics proposed "
                    "from its source sections; those concepts remain separate "
                    "registry entries."
                ),
                related_topics=component_topics,
            )
            excluded_seeds.append(candidate_row)
            continue
        candidate_row.update(
            status="needs_reconciliation",
            review_hint=(
                "The heading looks composite or instructional; compare it with the "
                "separate Topics proposed in its source sections."
                if _COMPOSITE_TITLE_RE.search(seed_title)
                else (
                    "No exact or simple grammatical match was found; decide whether "
                    "this title names an independent Topic or is already covered by "
                    "the source-section Topics."
                )
            ),
            related_topics=related_topics,
        )
        unresolved_seeds.append(candidate_row)

    unused_title_decisions = set(decisions_by_normalized_title) - applied_title_decisions
    if unused_title_decisions:
        raise ValueError(
            "title-seed decisions did not match any candidate: "
            + ", ".join(sorted(unused_title_decisions))
        )

    topic_rows: list[dict[str, Any]] = []
    contract_topics: list[Topic] = []
    for group in groups:
        group_key = str(group.get("canonical_topic_id") or group["normalized_title"])
        topic_id = topic_ids[group_key]
        standalone_update = standalone_updates_by_topic_id.get(topic_id)
        canonical_title = group.get("canonical_topic_title")
        title = str(
            (standalone_update or {}).get("topic_title")
            or canonical_title
            or max(
                title_counts[group_key],
                key=lambda candidate: (title_counts[group_key][candidate], candidate.casefold()),
                default=(group.get("title_variants") or [group["normalized_title"]])[0],
            )
        )
        definitions = [
            {
                "definition": definition,
                "mention_count": definition_counts[group_key][definition],
                "source_section_count": len(definition_sections[group_key][definition]),
                "source_section_keys": sorted(definition_sections[group_key][definition]),
            }
            for definition in group.get("definitions", [])
        ]
        definitions.sort(
            key=lambda item: (
                -item["mention_count"],
                -item["source_section_count"],
                item["definition"].casefold(),
            )
        )
        if not definitions:
            raise ValueError(f"Topic has no draft definition: {topic_id}")
        definition_decision = confirmed_definitions_by_topic_id.get(topic_id)
        assistant_decision = assistant_decisions_by_topic_id.get(topic_id)
        if definition_decision is not None and assistant_decision is not None:
            raise ValueError(f"Topic has both user and assistant definition decisions: {topic_id}")
        if standalone_update is not None:
            standalone_definition = str(standalone_update["draft_definition"])
            standalone_keys = sorted(
                ref.get("section_key", "")
                for ref in standalone_update["source_sections"]
                if ref.get("section_key")
            )
            if not any(row["definition"] == standalone_definition for row in definitions):
                definitions.append(
                    {
                        "definition": standalone_definition,
                        "mention_count": 0,
                        "source_section_count": len(standalone_keys),
                        "source_section_keys": standalone_keys,
                        "definition_source": (
                            "assistant_synthesized_from_user_confirmed_source_sections"
                        ),
                    }
                )
            draft_definition = standalone_definition
        else:
            draft_definition = definitions[0]["definition"]
        if definition_decision is not None:
            draft_definition = str(definition_decision["canonical_definition_en"])
        elif assistant_decision is not None:
            draft_definition = str(assistant_decision.get("selected_definition") or "")
            is_source_refinement = (
                assistant_decision.get("definition_selection_basis")
                == "source_context_refinement"
            )
            if not draft_definition or (
                draft_definition not in {row["definition"] for row in definitions}
                and not is_source_refinement
            ):
                raise ValueError(
                    "assistant-selected definition is not a current candidate: "
                    f"{topic_id}"
                )
        refs = sorted(
            refs_by_group[group_key].values(),
            key=lambda ref: (
                ref.get("textbook_id", ""),
                ref.get("chapter_id", ""),
                ref.get("section_id", ""),
                ref.get("section_key", ""),
            ),
        )
        group_row: dict[str, Any] = {
            "topic_id": topic_id,
            "title": title,
            "draft_definition": draft_definition,
            "definition_review_status": (
                "user_confirmed"
                if definition_decision is not None
                else (
                    "assistant_resolved_high_confidence"
                    if assistant_decision is not None
                    else "m3_confirmation_required"
                )
            ),
            "definition_candidate_count": len(definitions),
            "definitions": definitions,
            "source_section_count": len(refs),
            "source_sections": refs,
            "title_seed_matches": [
                {
                    "candidate_title": entry["candidate_title"],
                    "match_rule": entry["match_rule"],
                    "source_sections": entry["source_sections"],
                }
                for entry in title_seed_entries_by_group[group_key]
            ],
            "standalone_title_seed_contexts": standalone_seed_entries_by_group[group_key],
            "mapped_section_title_contexts": title_seed_contexts_by_group[group_key],
        }
        if definition_decision is not None:
            group_row["definition_decision"] = {
                "decision_id": definition_decision.get("decision_id"),
                "decision_source": "user",
                "user_definition_zh": definition_decision.get("user_definition_zh"),
                "decision_date": definition_decision.get("decision_date"),
            }
        if assistant_decision is not None:
            group_row["automated_definition_decision"] = {
                "decision_source": assistant_decision.get(
                    "decision_source", "local_offline_model_high_confidence"
                ),
                "model": (definition_reconciliation or {}).get("model"),
                "selected_candidate_index": assistant_decision.get("selected_candidate_index"),
                "reason_code": assistant_decision.get("reason_code"),
                "rationale_zh": assistant_decision.get("rationale_zh"),
                "model_review_outcome": assistant_decision.get("model_review_outcome"),
                "definition_selection_basis": assistant_decision.get("definition_selection_basis"),
                "supporting_source_citations": assistant_decision.get(
                    "supporting_source_citations", []
                ),
            }
        uncertain_decision = uncertain_decisions_by_topic_id.get(topic_id)
        if uncertain_decision is not None:
            group_row["definition_review_uncertainty"] = {
                "reason_code": uncertain_decision.get("reason_code"),
                "review_note": uncertain_decision.get("review_note"),
                "model": (definition_reconciliation or {}).get("model"),
            }
        if group.get("canonical_topic_title_zh"):
            group_row["localized_title_zh"] = group["canonical_topic_title_zh"]
        elif topic_id == "radioactive-tagging-of-compounds":
            group_row["localized_title_zh"] = "放射性标记化合物"
        topic_rows.append(group_row)
        contract_topics.append(Topic(topic_id=topic_id, title=title, description=draft_definition))

    for spec in new_standalone_topic_specs:
        topic_id = str(spec["topic_id"])
        topic_title = str(spec["topic_title"])
        definition_decision = confirmed_definitions_by_topic_id.get(topic_id)
        assistant_decision = assistant_decisions_by_topic_id.get(topic_id)
        draft_definition = str(
            definition_decision["canonical_definition_en"]
            if definition_decision is not None
            else (
                assistant_decision.get("selected_definition")
                if assistant_decision is not None
                else spec["draft_definition"]
            )
        )
        source_refs = [
            {
                **source_ref,
                "source_roles": ["section_title_seed"],
            }
            for source_ref in spec["source_sections"]
            if source_ref.get("section_key")
        ]
        source_keys = sorted(ref["section_key"] for ref in source_refs)
        topic_rows.append(
            {
                "topic_id": topic_id,
                "title": topic_title,
                "draft_definition": draft_definition,
                "definition_review_status": (
                    "user_confirmed"
                    if definition_decision is not None
                    else (
                        "assistant_resolved_high_confidence"
                        if assistant_decision is not None
                        else "m3_confirmation_required"
                    )
                ),
                "definition_candidate_count": 1,
                "definitions": [
                    {
                        "definition": draft_definition,
                        "mention_count": 0,
                        "source_section_count": len(source_keys),
                        "source_section_keys": source_keys,
                        "definition_source": (
                            "user_confirmed_definition"
                            if definition_decision is not None
                            else "assistant_synthesized_from_user_confirmed_source_sections"
                        ),
                    }
                ],
                "source_section_count": len(source_refs),
                "source_sections": source_refs,
                "title_seed_matches": [],
                "standalone_title_seed_contexts": [spec["candidate_row"]],
                "mapped_section_title_contexts": [],
                "topic_origin": "user_confirmed_standalone_section_title",
                **(
                    {
                        "definition_decision": {
                            "decision_id": definition_decision.get("decision_id"),
                            "decision_source": "user",
                            "user_definition_zh": definition_decision.get("user_definition_zh"),
                            "decision_date": definition_decision.get("decision_date"),
                        }
                    }
                    if definition_decision is not None
                    else {}
                ),
                **(
                    {
                        "automated_definition_decision": {
                            "decision_source": assistant_decision.get(
                                "decision_source", "local_offline_model_high_confidence"
                            ),
                            "model": (definition_reconciliation or {}).get("model"),
                            "selected_candidate_index": assistant_decision.get(
                                "selected_candidate_index"
                            ),
                            "reason_code": assistant_decision.get("reason_code"),
                            "rationale_zh": assistant_decision.get("rationale_zh"),
                            "model_review_outcome": assistant_decision.get("model_review_outcome"),
                            "definition_selection_basis": assistant_decision.get(
                                "definition_selection_basis"
                            ),
                            "supporting_source_citations": assistant_decision.get(
                                "supporting_source_citations", []
                            ),
                        }
                    }
                    if assistant_decision is not None
                    else {}
                ),
            }
        )
        contract_topics.append(
            Topic(
                topic_id=topic_id,
                title=topic_title,
                description=draft_definition,
            )
        )

    unapplied_definition_decisions = set(confirmed_definitions_by_topic_id) - {
        row["topic_id"]
        for row in topic_rows
        if row.get("definition_review_status") == "user_confirmed"
    }
    if unapplied_definition_decisions:
        raise ValueError(
            "confirmed Topic definitions did not match registry Topics: "
            + ", ".join(sorted(unapplied_definition_decisions))
        )
    unmatched_reconciliation_ids = (
        set(assistant_decisions_by_topic_id) | set(uncertain_decisions_by_topic_id)
    ) - {row["topic_id"] for row in topic_rows}
    if unmatched_reconciliation_ids:
        raise ValueError(
            "definition reconciliation referenced missing Topics: "
            + ", ".join(sorted(unmatched_reconciliation_ids))
        )
    unmatched_adjudications = set(adjudications_by_topic_id) - {
        row["topic_id"] for row in topic_rows
    }
    if unmatched_adjudications:
        raise ValueError(
            "definition adjudications referenced missing Topics: "
            + ", ".join(sorted(unmatched_adjudications))
        )

    resolved_title_seed_group_count = (
        len(seed_matches)
        + len(mapped_title_seed_groups)
        + len(retained_standalone_title_seed_groups)
        + len(added_standalone_title_seed_groups)
        + len(excluded_seeds)
        + len(unresolved_seeds)
    )
    if resolved_title_seed_group_count != len(title_candidates.get("candidates", [])):
        raise ValueError(
            "title-seed disposition counts do not reconcile: "
            f"{resolved_title_seed_group_count} != {len(title_candidates.get('candidates', []))}"
        )

    registry = TopicRegistry(
        topic_registry_version=REGISTRY_VERSION,
        topics=tuple(contract_topics),
    )

    definitions_with_alternatives = sum(
        1 for row in topic_rows if row["definition_candidate_count"] > 1
    )
    topics_requiring_definition_confirmation = sum(
        1 for row in topic_rows if row["definition_review_status"] == "m3_confirmation_required"
    )
    assistant_resolved_definition_count = sum(
        row["definition_review_status"] == "assistant_resolved_high_confidence"
        for row in topic_rows
    )
    resolved_anomalies = []
    if source_anomaly_resolution is not None:
        resolved_anomalies.append(
            {
                "review_id": source_anomaly_resolution.get("review_id"),
                "source_key": source_anomaly_resolution.get("source_section_key"),
                "status": "resolved_by_user",
                "topic_id": source_anomaly_resolution.get("induction_topic_id"),
                "definition_candidate_topic_id": source_anomaly_resolution.get(
                    "definition_candidate_topic_id"
                ),
                "resolution": source_anomaly_resolution.get("resolution_note_zh"),
            }
        )
    review_packet = {
        "schema_version": "topic-registry-review-packet-v0",
        "status": (
            "draft_for_m3_definition_confirmation_title_seed_reconciliation_complete"
            if not unresolved_seeds
            else "draft_for_m3_definition_confirmation_and_title_seed_reconciliation"
        ),
        "topic_registry_version": REGISTRY_VERSION,
        "registry_file": "artifacts/v2/topics/topic_registry_draft_v0.json",
        "provenance_file": "artifacts/v2/topics/topic_registry_review_packet_v0.json",
        "generated_from": {
            "aggregate_file": "artifacts/v2/topics/topic_section_concept_aggregate_merged_v23.json",
            "title_candidate_file": "artifacts/v2/topics/topic_title_candidates.json",
            "proposal_file": "artifacts/v2/topics/topic_section_proposals.jsonl",
            "merge_map_version": merge_map.mapping_version,
            "title_seed_decision_file": "artifacts/v2/topics/topic_title_seed_decisions_v0.json",
            "definition_decision_file": "artifacts/v2/topics/topic_definition_decisions_v0.json",
            "definition_reconciliation_file": (
                "artifacts/v2/topics/topic_definition_reconciliation_v0.json"
            ),
            "definition_adjudications_file": (
                "artifacts/v2/topics/topic_definition_manual_adjudications_v0.json"
            ),
            "corpus_version": corpus_manifest.get("corpus_version"),
            "corpus_hash": corpus_manifest.get("corpus_hash"),
        },
        "summary": {
            "concept_topic_count": len(topic_rows),
            "model_concept_group_count": len(groups),
            "topics_requiring_m3_definition_confirmation": topics_requiring_definition_confirmation,
            "topics_with_user_confirmed_definitions": len(confirmed_definitions_by_topic_id),
            "topics_assistant_resolved_high_confidence": assistant_resolved_definition_count,
            "topics_flagged_for_user_definition_review": len(uncertain_decisions_by_topic_id),
            "topics_with_assistant_adjudication_overrides": len(adjudications_by_topic_id),
            "source_anomaly_decisions_applied": int(source_anomaly_resolution is not None),
            "topics_with_multiple_definition_candidates": definitions_with_alternatives,
            "section_title_seed_group_count": len(title_candidates.get("candidates", [])),
            "title_seed_groups_matched_to_topics": len(seed_matches),
            "title_seed_match_rule_counts": dict(sorted(seed_match_counts.items())),
            "title_seed_decisions_applied": sum(title_decision_counts.values()),
            "title_seed_decision_disposition_counts": dict(sorted(title_decision_counts.items())),
            "title_seed_groups_mapped_to_existing_topics": len(mapped_title_seed_groups),
            "title_seed_groups_retained_as_standalone_topics": len(
                retained_standalone_title_seed_groups
            ),
            "title_seed_groups_added_as_standalone_topics": len(
                added_standalone_title_seed_groups
            ),
            "standalone_topics_added_from_section_titles": len(new_standalone_topic_specs),
            "excluded_title_seed_groups": len(excluded_seeds),
            "non_topic_heading_groups_excluded": sum(
                1 for row in excluded_seeds if row["status"] == "excluded_non_topic_heading"
            ),
            "composite_section_title_groups_excluded": sum(
                1 for row in excluded_seeds if row["status"] == "excluded_composite_section_title"
            ),
            "unresolved_title_seed_groups": len(unresolved_seeds),
            "unresolved_source_section_count": sum(
                row["source_section_count"] for row in unresolved_seeds
            ),
            "all_title_seed_dispositions_resolved": not unresolved_seeds,
            "title_seed_dispositions_total": resolved_title_seed_group_count,
            "all_concept_merge_queue_items_resolved": True,
        },
        "resolved_source_anomalies": resolved_anomalies,
        "known_source_anomalies": [] if resolved_anomalies else [
            {
                "review_id": "MC-section-0843",
                "source_key": "section-0843",
                "topic_id": "electromagnetic-induction",
                "note": (
                    "The Chapter 20 proposal's Induction definition duplicates its EMF "
                    "entry; the definition is routed to the EMF candidate Topic, not "
                    "used as an Electromagnetic Induction definition."
                ),
            }
        ],
        "topics": topic_rows,
        "topics_flagged_for_user_definition_review": [
            {
                "topic_id": row["topic_id"],
                "title": row["title"],
                "draft_definition": row["draft_definition"],
                "definitions": row["definitions"],
                "source_sections": row["source_sections"],
                "uncertainty": row["definition_review_uncertainty"],
            }
            for row in topic_rows
            if row.get("definition_review_uncertainty")
        ],
        "matched_title_seed_groups": seed_matches,
        "mapped_title_seed_groups": mapped_title_seed_groups,
        "retained_standalone_title_seed_groups": retained_standalone_title_seed_groups,
        "added_standalone_title_seed_groups": added_standalone_title_seed_groups,
        "excluded_title_seed_groups": excluded_seeds,
        "unresolved_title_seed_groups": unresolved_seeds,
    }
    return registry.model_dump(mode="json"), review_packet


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a provisional Topic registry and M3 review packet."
    )
    parser.add_argument("--aggregate", type=Path, default=DEFAULT_AGGREGATE)
    parser.add_argument("--title-candidates", type=Path, default=DEFAULT_TITLE_CANDIDATES)
    parser.add_argument("--title-decisions", type=Path, default=DEFAULT_TITLE_DECISIONS)
    parser.add_argument("--definition-decisions", type=Path, default=DEFAULT_DEFINITION_DECISIONS)
    parser.add_argument(
        "--definition-reconciliation",
        type=Path,
        default=DEFAULT_DEFINITION_RECONCILIATION,
    )
    parser.add_argument(
        "--definition-adjudications",
        type=Path,
        default=DEFAULT_DEFINITION_ADJUDICATIONS,
    )
    parser.add_argument("--proposals", type=Path, default=DEFAULT_PROPOSALS)
    parser.add_argument("--merge-map", type=Path, default=DEFAULT_MERGE_MAP)
    parser.add_argument("--corpus-manifest", type=Path, default=DEFAULT_CORPUS_MANIFEST)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source_root = str(REPO_ROOT / "src")
    if source_root not in sys.path:
        sys.path.insert(0, source_root)
    repo_root = str(REPO_ROOT)
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    from cs30.v2.topic_merge_map import load_topic_merge_map

    registry, packet = build_registry_draft(
        _read_json(args.aggregate),
        _read_json(args.title_candidates),
        _read_json(args.title_decisions) if args.title_decisions.exists() else {"decisions": []},
        _read_jsonl(args.proposals),
        load_topic_merge_map(args.merge_map),
        _read_json(args.corpus_manifest),
        _read_json(args.definition_decisions)
        if args.definition_decisions.exists()
        else {"decisions": []},
        _read_json(args.definition_reconciliation)
        if args.definition_reconciliation.exists()
        else {"decisions": []},
        _read_json(args.definition_adjudications)
        if args.definition_adjudications.exists()
        else {"adjudications": []},
    )
    registry_path = args.output_dir / "topic_registry_draft_v0.json"
    packet_path = args.output_dir / "topic_registry_review_packet_v0.json"
    _write_json(registry_path, registry)
    _write_json(packet_path, packet)
    print(
        json.dumps(
            {
                "registry_file": str(registry_path),
                "review_packet_file": str(packet_path),
                "topic_registry_version": registry["topic_registry_version"],
                "summary": packet["summary"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
