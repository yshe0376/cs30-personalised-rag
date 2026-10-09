"""Build section inventory and title-seeded Topic candidate review files."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CORPUS_DIR = (
    REPO_ROOT
    / "artifacts"
    / "v2"
    / "textbooks"
    / "2.0.0-dev.m4-structure-v2-main-3553825"
)
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "v2" / "topics"

# The prefix accepts common textbook numbering such as "2.1 Title",
# "Chapter 2: Title", and "2-1 Title" without stripping "1-Dimensional".
_NUMBERING_PREFIX = re.compile(
    r"^\s*(?:(?:chapter|section)\s+)?\d+(?:\.\d+)*(?:[-–—]\d+(?:\.\d+)*)?"
    r"(?:\s*[.)]\s*|\s*[-–—:]\s+|\s+)",
    flags=re.IGNORECASE,
)
_NUMBERING_ONLY = re.compile(
    r"^\s*(?:(?:chapter|section)\s+)?\d+(?:\.\d+)*\s*$",
    flags=re.IGNORECASE,
)
_CHAPTER_LEVEL_SECTION = re.compile(r"(?:^|\.)(?:chapter[_ ]?outline|introduction)$")
_NON_CONCEPT_TITLES = {
    "about the authors",
    "answers",
    "answers to selected exercises",
    "chapter introduction",
    "chapter objectives",
    "chapter outline",
    "chapter review",
    "chapter summary",
    "conceptual questions",
    "contents",
    "further reading",
    "introduction",
    "preface",
    "problems & exercises",
    "problems and exercises",
    "references",
    "review questions",
    "summary",
}
_QUOTE_TRANSLATION = str.maketrans(
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


def display_title(title: str) -> str:
    """Return a readable title with numbering and typography normalized."""

    normalized = unicodedata.normalize("NFKC", title).translate(_QUOTE_TRANSLATION)
    normalized = _NUMBERING_PREFIX.sub("", normalized, count=1)
    return " ".join(normalized.split())


def normalize_title(title: str) -> str:
    """Casefold the display title for exact merging across textbooks."""

    normalized = display_title(title)
    if _NUMBERING_ONLY.fullmatch(normalized):
        return ""
    return " ".join(normalized.casefold().split())


def _natural_key(value: str) -> tuple[tuple[int, int | str], ...]:
    """Sort identifiers with their numeric components in numeric order."""

    return tuple(
        (1, int(part)) if part.isdigit() else (0, part.casefold())
        for part in re.split(r"(\d+)", value)
        if part
    )


def _ordered_unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _section_row(section: dict[str, Any]) -> dict[str, Any]:
    return {
        "textbook_id": section["textbook_id"],
        "chapter_id": section["chapter_id"],
        "section_id": section["section_id"],
        "section_title": section["section_title"],
        "chunk_ids": section["chunk_ids"],
        "block_ids": section["block_ids"],
        "token_count": section["token_count"],
    }


def _exclusion_reason(section_id: str, normalized_title: str) -> str | None:
    if _CHAPTER_LEVEL_SECTION.search(section_id.casefold()):
        if section_id.casefold().endswith("chapter_outline"):
            return "chapter outline section"
        return "chapter-level introduction section"
    if normalized_title in _NON_CONCEPT_TITLES:
        return "generic navigation or assessment heading"
    return None


def build_section_rows(chunks: tuple[Any, ...]) -> list[dict[str, Any]]:
    """Aggregate chunks into one row per textbook/chapter/section identity."""

    grouped: dict[tuple[str, str, str], dict[str, Any]] = {}
    for chunk in chunks:
        key = (chunk.textbook_id, chunk.chapter_id, chunk.section_id or "")
        section = grouped.setdefault(
            key,
            {
                "textbook_id": chunk.textbook_id,
                "chapter_id": chunk.chapter_id,
                "section_id": chunk.section_id or "",
                "titles": [],
                "chunk_ids": [],
                "block_ids": [],
                "token_count": 0,
            },
        )
        if chunk.section_title:
            section["titles"].append(chunk.section_title)
        section["chunk_ids"].append(chunk.chunk_id)
        section["block_ids"].extend(span.block_id for span in chunk.spans)
        section["token_count"] += chunk.token_count

    rows: list[dict[str, Any]] = []
    for section in grouped.values():
        titles = sorted(set(section.pop("titles")), key=lambda value: (value.casefold(), value))
        section["section_title"] = " | ".join(titles)
        section["chunk_ids"] = _ordered_unique(section["chunk_ids"])
        section["block_ids"] = _ordered_unique(section["block_ids"])
        rows.append(section)

    return sorted(
        rows,
        key=lambda row: (
            row["textbook_id"],
            _natural_key(row["chapter_id"]),
            _natural_key(row["section_id"]),
            row["section_title"].casefold(),
        ),
    )


def build_candidate_review(
    section_rows: list[dict[str, Any]],
    *,
    corpus_version: str,
    corpus_hash: str,
    chunk_count: int,
) -> dict[str, Any]:
    """Merge exact normalized titles and retain section/chunk provenance."""

    candidate_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    excluded_groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    missing_title_sections = 0
    missing_title_chunks = 0
    title_section_count = 0

    for section in section_rows:
        raw_title = section["section_title"].strip()
        if not raw_title:
            missing_title_sections += 1
            missing_title_chunks += len(section["chunk_ids"])
            continue

        title_section_count += 1
        normalized_title = normalize_title(raw_title)
        reason = _exclusion_reason(section["section_id"], normalized_title)
        source = _section_row(section)
        if reason:
            excluded_groups[(normalized_title, reason)].append(source)
        elif normalized_title:
            candidate_groups[normalized_title].append(source)
        else:
            excluded_groups[(normalized_title, "number-only title")].append(source)

    candidates = []
    for normalized_title, sources in sorted(candidate_groups.items()):
        variant_counts = Counter(
            display_title(source["section_title"]) for source in sources
        )
        title_variants = sorted(variant_counts, key=lambda title: (title.casefold(), title))
        candidate_title = min(
            title_variants,
            key=lambda title: (-variant_counts[title], title.casefold(), title),
        )
        candidates.append(
            {
                "candidate_title": candidate_title,
                "normalized_title": normalized_title,
                "title_variants": title_variants,
                "source_section_count": len(sources),
                "textbook_count": len({source["textbook_id"] for source in sources}),
                "source_sections": sources,
            }
        )

    excluded_titles = [
        {
            "normalized_title": normalized_title,
            "exclusion_reason": reason,
            "source_section_count": len(sources),
            "source_sections": sources,
        }
        for (normalized_title, reason), sources in sorted(excluded_groups.items())
    ]

    candidate_source_count = sum(item["source_section_count"] for item in candidates)
    excluded_source_count = sum(item["source_section_count"] for item in excluded_titles)
    return {
        "schema_version": "1.0",
        "corpus": {
            "corpus_version": corpus_version,
            "corpus_hash": corpus_hash,
            "chunk_count": chunk_count,
        },
        "normalization": {
            "unicode": "NFKC",
            "numbering": (
                "strip leading chapter/section numbers, including dotted and hyphenated prefixes"
            ),
            "case": "casefold",
            "apostrophes_and_quotes": (
                "map typographic apostrophes and quotation marks to ASCII equivalents"
            ),
            "merge_rule": (
                "merge exact normalized titles only; keep semantic synonyms separate"
            ),
        },
        "filtering": {
            "chapter_level_sections": (
                "exclude section IDs ending in .introduction or .chapter_outline"
            ),
            "generic_headings": sorted(_NON_CONCEPT_TITLES),
            "missing_titles": "not emitted as candidates",
        },
        "summary": {
            "section_count": len(section_rows),
            "sections_with_titles": title_section_count,
            "sections_without_titles": missing_title_sections,
            "chunks_in_sections_without_titles": missing_title_chunks,
            "candidate_title_count": len(candidates),
            "candidate_source_section_count": candidate_source_count,
            "excluded_title_group_count": len(excluded_titles),
            "excluded_source_section_count": excluded_source_count,
        },
        "candidates": candidates,
        "excluded_titles": excluded_titles,
    }


def write_section_csv(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as output:
        writer = csv.DictWriter(
            output,
            fieldnames=(
                "textbook_id",
                "chapter_id",
                "section_id",
                "section_title",
                "chunk_ids",
                "block_ids",
                "token_count",
            ),
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    **row,
                    "chunk_ids": json.dumps(row["chunk_ids"], ensure_ascii=False),
                    "block_ids": json.dumps(row["block_ids"], ensure_ascii=False),
                }
            )


def write_candidate_json(review: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(review, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inventory v2 corpus sections and seed Topic candidates from titles."
    )
    parser.add_argument(
        "--corpus-dir",
        type=Path,
        default=DEFAULT_CORPUS_DIR,
        help="directory containing a validated v2 corpus manifest and records.jsonl",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="directory for the generated CSV and candidate review JSON",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source_root = str(REPO_ROOT / "src")
    if source_root not in sys.path:
        sys.path.insert(0, source_root)

    from cs30.v2.corpus import load_corpus_records

    loaded = load_corpus_records(args.corpus_dir)
    section_rows = build_section_rows(loaded.chunks)
    review = build_candidate_review(
        section_rows,
        corpus_version=loaded.manifest.corpus_version,
        corpus_hash=loaded.manifest.corpus_hash,
        chunk_count=len(loaded.chunks),
    )

    section_path = args.output_dir / "topic_sections.csv"
    candidate_path = args.output_dir / "topic_title_candidates.json"
    write_section_csv(section_rows, section_path)
    write_candidate_json(review, candidate_path)
    print(f"Section table: {section_path} ({len(section_rows)} sections)")
    print(f"Title candidates: {candidate_path}")
    print(json.dumps(review["summary"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
