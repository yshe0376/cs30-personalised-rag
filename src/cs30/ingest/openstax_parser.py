#!/usr/bin/env python3
"""Parse selected OpenStax College Physics 2e chapters for a RAG pipeline.

The parser uses the PDF outline for stable chapter/section boundaries and the
Tagged-PDF structure tree for reading order.  OpenStax renders many equations
as vector figures, so ordinary ``page.get_text()`` calls omit them.  This
parser recovers those equations from their accessibility ``alt_text`` instead
of silently dropping them or applying unreliable OCR.

Outputs
-------
openstax_document.json
    Strict ``models.py`` v1.0 contract: document metadata, one text source of
    truth, chapter spans, and text-block spans.  It contains no extra fields.
blocks.jsonl
    The same contract-compatible ``TextBlock`` objects, one per line.
records.jsonl
    Extended parser/debug records retained for backward compatibility.
metadata.json
    Source/version/hash/parser information and corpus statistics.
qa_report.json
    Deterministic samples and an explicit manual-review checklist.
known_issues.json
    Formula/table/figure and extraction limitations found during parsing.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

try:
    import fitz  # PyMuPDF
    import pdfplumber
    from pdfplumber.utils import extract_text
except ImportError as exc:  # pragma: no cover - exercised by the CLI
    raise SystemExit(
        "Missing dependency. Run: python -m pip install PyMuPDF pdfplumber"
    ) from exc


PARSER_VERSION = "1.2.0"
SCHEMA_VERSION = "1.0"
DOCUMENT_SEPARATOR = "\n\n"
DEFAULT_SOURCE_URL = "https://openstax.org/details/books/college-physics-2e"

TEXT_BLOCK_TYPES = {
    "P",
    "H",
    "H1",
    "H2",
    "H3",
    "H4",
    "H5",
    "H6",
    "Caption",
    "Note",
    "Quote",
    "LI",
    "LBody",
    "TD",
    "TH",
}
CONTAINER_TYPES = {"Document", "Part", "Art", "Sect", "Div", "L", "TR"}
RUNNING_TEXT = {
    "Access for free at openstax.org",
    "Access for free at OpenStax.org",
}
MATH_TERMS = re.compile(
    r"\b(equals?|fraction|numerator|denominator|sub|sup|triangle|delta|"
    r"squared|power|plus|minus|negative|slash|over|root|integral|sigma|"
    r"theta|lambda|alpha|beta|gamma|omega|constant)\b",
    re.IGNORECASE,
)
DESCRIPTIVE_FIGURE_TERMS = re.compile(
    r"\b(photo|photograph|diagram|graph|chart|illustration|image|drawing|"
    r"map|view|inset|person|people|man|woman|men|women|professor|passenger|"
    r"cars?|trains?|airplanes?|object|arrow|axis|axes|shows?|displaying|"
    r"labeled|depicts?)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class OutlineEntry:
    level: int
    title: str
    pdf_page: int


@dataclass
class OpenStaxRecord:
    record_id: str
    chunk_source_id: str
    document_id: str
    chapter_id: str
    chapter_title: str
    section_id: str | None
    section_title: str | None
    section_type: str
    record_type: str
    text: str
    pdf_page: int
    printed_page: int | None
    page_block_index: int
    page_text_index: int
    bbox: list[float] | None
    source: str
    char_start: int = 0
    char_end: int = 0
    formula_alt_text: str | None = None
    formula_display: str | None = None
    extraction_method: str = "tagged_pdf"


@dataclass
class OpenStaxDocument:
    document_id: str
    title: str
    edition: str
    source: str
    source_file: str
    source_format: str
    download_date: str
    document_hash: str
    parser_version: str
    selected_chapters: list[str]
    text_separator: str
    text: str
    records: list[OpenStaxRecord]
    known_issues: list[dict[str, Any]] = field(default_factory=list)


def sha256_file(path: Path, buffer_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(buffer_size):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_unicode(text: str) -> str:
    return unicodedata.normalize("NFKC", text).replace("\u00ad", "")


def normalize_prose(text: str) -> str:
    """Normalize prose without applying formula-destructive whitespace rules."""
    text = normalize_unicode(text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"(?<=\w)-\s*\n\s*(?=[a-z])", "", text)
    text = re.sub(r"\s*\n\s*", " ", text)
    text = re.sub(r"[\t ]+", " ", text)
    return text.strip()


def _replace_decimal_words(text: str) -> str:
    pattern = re.compile(r"\b(\d+)\s+(?:point|period)\s+(\d+)\b", re.I)
    while pattern.search(text):
        text = pattern.sub(r"\1.\2", text)
    return text


def _replace_spoken_fractions(text: str) -> tuple[str, bool]:
    """Convert simple OpenStax spoken fractions to readable linear notation."""
    changed = False
    pattern = re.compile(
        r"the fraction with numerator (.+?) and denominator "
        r"(.+?)(?=\s+equals\s+|\s+times\s+open paren\s+constant\b|"
        r"\s+(?:comma|period)\b|$)",
        re.IGNORECASE,
    )
    for _ in range(8):
        match = pattern.search(text)
        if not match:
            break
        numerator = match.group(1).strip()
        denominator = match.group(2).strip()
        text = text[: match.start()] + f"({numerator})/({denominator})" + text[match.end() :]
        changed = True
    return text, changed


def spoken_math_to_display(alt_text: str) -> tuple[str, str]:
    """Return a conservative display form and a confidence label.

    The original accessibility text is always retained separately.  The
    display conversion intentionally handles only recurring, low-risk OpenStax
    phrases; it never replaces the source alt text.
    """
    text = normalize_prose(alt_text)
    text = _replace_decimal_words(text)
    # Some accessibility spans verbalize a spacing dash before a unit as
    # "minus" even when the visible equation is simply, for example, 4.0 m.
    text = re.sub(
        r"\b(\d+(?:\.\d+)?)\s+minus\s+(m|s|kg|N|J|W|Pa)\b",
        r"\1 \2",
        text,
        flags=re.IGNORECASE,
    )
    text, fraction_changed = _replace_spoken_fractions(text)

    replacements = [
        (r"\btriangle\s+([A-Za-z])\b", r"Δ\1"),
        (r"\bdelta\s+([A-Za-z])\b", r"Δ\1"),
        (r"\b([A-Za-zΔ]+)\s+sub\s+([A-Za-z0-9]+)\b", r"\1_\2"),
        (r"\b([A-Za-zΔ]+)\s+sup\s+([A-Za-z0-9]+)\b", r"\1^\2"),
        (r"\b([A-Za-z])\s+prime_([A-Za-z0-9]+)\b", r"\1′_\2"),
        (r"\bprime\b", "′"),
        (r"\btriangle\b", "Δ"),
        (r"\bdelta\b", "Δ"),
        # Prince's accessibility text calls an overbar "minus".  Limit the
        # replacement to contexts that denote an average so subtraction such
        # as "v minus v sub 0" remains subtraction.
        (r"\bv\s+minus(?=\s+equals\b|\s+squared\b|\s+t\b|\s*(?:[,.;]|$))", "v̄"),
        (r"\ba\s+minus(?=\s+equals\b|\s+squared\b|\s*(?:[,.;]|$))", "ā"),
        (r"\bto the second power\b", "²"),
        (r"\bto the third power\b", "³"),
        (r"\bsquared\b", "²"),
        (r"\bcubed\b", "³"),
        (r"\bopen paren\b", "("),
        (r"\bclose paren\b", ")"),
        (r"\bplus or minus\b", "±"),
        (r"\bnegative\b", "−"),
        (r"\bpositive\b", "+"),
        (r"\bequals\b", "="),
        (r"\bplus\b", "+"),
        (r"\bminus\b", "−"),
        (r"\bslash\b", "/"),
        (r"\bover\b", "/"),
        (r"\btimes\b", "×"),
        (r"\bcomma\b", ","),
        (r"\bperiod\b", "."),
        (r"\bclose brace\b", ""),
    ]
    for pattern, replacement in replacements:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

    text = re.sub(r"\s+([,.;)])", r"\1", text)
    text = re.sub(r"([(])\s+", r"\1", text)
    text = re.sub(r"\s*×\s*\(constant\s+([A-Za-z])\)", r"; constant \1", text, flags=re.I)
    text = re.sub(r"^\d+\s+lines?\s+", "", text, flags=re.I)
    text = re.sub(r"\bLine\s+\d+\s*:\s*", "; ", text, flags=re.I)
    text = text.lstrip("; ")
    text = re.sub(r"\s*([=+×/])\s*", r" \1 ", text)
    text = re.sub(r"\s*−\s*", " − ", text)
    text = re.sub(r"\s+", " ", text).strip()

    unresolved = bool(re.search(r"\b(numerator|denominator|fraction| sub | sup )\b", text, re.I))
    confidence = "low" if unresolved else ("medium" if fraction_changed else "high")
    return text, confidence


def is_formula_alt(alt_text: str, inline: bool = False) -> bool:
    text = alt_text.strip()
    if inline and len(text.split()) <= 12:
        return True
    math_score = len(MATH_TERMS.findall(text))
    descriptive = bool(DESCRIPTIVE_FIGURE_TERMS.search(text))
    natural_description = bool(re.match(r"^(?:the|a|an|view|diagram|graph|line graph)\b", text, re.I))
    return math_score >= 1 and not (
        len(text.split()) > 24 and (descriptive or natural_description)
    )


def bbox_from_pdf_coordinates(raw_bbox: Sequence[float], page_height: float) -> list[float]:
    x0, y0, x1, y1 = map(float, raw_bbox)
    return [x0, page_height - y1, x1, page_height - y0]


def union_bbox(boxes: Iterable[Sequence[float] | None]) -> list[float] | None:
    present = [list(map(float, box)) for box in boxes if box is not None]
    if not present:
        return None
    return [
        round(min(box[0] for box in present), 3),
        round(min(box[1] for box in present), 3),
        round(max(box[2] for box in present), 3),
        round(max(box[3] for box in present), 3),
    ]


def iter_nodes(nodes: Iterable[dict[str, Any]]) -> Iterator[dict[str, Any]]:
    for node in nodes:
        yield node
        yield from iter_nodes(node.get("children", []))


def node_mcids(node: dict[str, Any]) -> set[int]:
    found = {int(mcid) for mcid in node.get("mcids", [])}
    for child in node.get("children", []):
        found.update(node_mcids(child))
    return found


def child_has_text_block(node: dict[str, Any]) -> bool:
    return any(str(child.get("type", "")) in TEXT_BLOCK_TYPES for child in node.get("children", []))


def semantic_nodes(nodes: Iterable[dict[str, Any]]) -> Iterator[dict[str, Any]]:
    """Yield non-overlapping logical blocks from a page structure tree."""
    for node in nodes:
        node_type = str(node.get("type", ""))
        if node_type == "Table":
            yield node
        elif node_type == "Figure":
            yield node
        elif node_type in TEXT_BLOCK_TYPES:
            # A wrapper P/LI occasionally contains a nested heading/body.  If
            # it has no own MCIDs, recurse to avoid an empty or duplicate row.
            if node.get("mcids") or not child_has_text_block(node):
                yield node
            else:
                yield from semantic_nodes(node.get("children", []))
        elif node_type in CONTAINER_TYPES or node.get("children"):
            yield from semantic_nodes(node.get("children", []))


def _chars_for_mcid(page: Any, mcid: int) -> list[dict[str, Any]]:
    return [
        char
        for char in page.chars
        if char.get("mcid") == mcid and str(char.get("tag", "")) != "Artifact"
    ]


def _fragment_for_mcid(page: Any, mcid: int) -> dict[str, Any] | None:
    chars = _chars_for_mcid(page, mcid)
    if not chars:
        return None
    text = extract_text(chars, layout=False) or ""
    text = normalize_prose(text)
    if not text:
        return None
    box = union_bbox([[c["x0"], c["top"], c["x1"], c["bottom"]] for c in chars])
    return {"mcid": mcid, "text": text, "bbox": box, "kind": "text"}


def _figure_fragment(page: Any, node: dict[str, Any], inline: bool) -> dict[str, Any] | None:
    alt = normalize_prose(str(node.get("alt_text", "")))
    if not alt:
        return None
    attributes = node.get("attributes", {}) or {}
    raw_bbox = attributes.get("BBox")
    box = bbox_from_pdf_coordinates(raw_bbox, float(page.height)) if raw_bbox else None
    formula = is_formula_alt(alt, inline=inline)
    if formula:
        display, confidence = spoken_math_to_display(alt)
        text = f"[EQUATION: {display}]"
        kind = "formula"
    else:
        display, confidence = None, None
        text = f"[FIGURE DESCRIPTION: {alt}]"
        kind = "figure"
    mcids = node.get("mcids", [])
    return {
        "mcid": min(map(int, mcids)) if mcids else 10**9,
        "text": text,
        "bbox": box,
        "kind": kind,
        "alt_text": alt,
        "display": display,
        "confidence": confidence,
    }


def node_fragments(page: Any, node: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract text and embedded formula fragments for one logical node."""
    fragments: list[dict[str, Any]] = []
    root_type = str(node.get("type", ""))
    if root_type == "Figure":
        fragment = _figure_fragment(page, node, inline=False)
        return [fragment] if fragment else []

    figure_mcids: set[int] = set()
    for descendant in iter_nodes(node.get("children", [])):
        if str(descendant.get("type", "")) != "Figure":
            continue
        fragment = _figure_fragment(page, descendant, inline=True)
        if fragment:
            fragments.append(fragment)
            figure_mcids.update(map(int, descendant.get("mcids", [])))

    for mcid in sorted(node_mcids(node) - figure_mcids):
        fragment = _fragment_for_mcid(page, mcid)
        if fragment:
            fragments.append(fragment)

    # Within one semantic paragraph, MCIDs preserve the inline reading order
    # (including formula positions) better than overlapping fragment boxes.
    fragments.sort(key=lambda item: item["mcid"])
    return fragments


def join_fragments(fragments: Sequence[dict[str, Any]]) -> str:
    text = " ".join(fragment["text"] for fragment in fragments if fragment.get("text"))
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def record_type_for_node(node: dict[str, Any], fragments: Sequence[dict[str, Any]], text: str) -> str:
    node_type = str(node.get("type", ""))
    kinds = {fragment.get("kind") for fragment in fragments}
    if node_type == "Table":
        return "table"
    if node_type == "Figure":
        return "formula" if kinds == {"formula"} else "figure"
    if node_type.startswith("H") or node_type == "H":
        return "heading"
    if node_type == "Caption":
        return "figure_caption"
    if re.fullmatch(r"\d+\.\d+", text):
        return "equation_number"
    return "paragraph"


def should_drop_record(text: str, record_type: str) -> bool:
    if not text or text in RUNNING_TEXT:
        return True
    if re.fullmatch(r"\d{1,4}", text) and record_type != "equation_number":
        return True
    if re.fullmatch(r"\d+\s*[•|]\s*.+", text):
        return True
    if re.fullmatch(r".+\s*[•|]\s*\d+", text):
        return True
    return False


def parse_outline(pdf_path: Path) -> list[OutlineEntry]:
    with fitz.open(pdf_path) as document:
        toc = document.get_toc(simple=True)
    outline = [OutlineEntry(int(level), normalize_prose(title), int(page)) for level, title, page in toc]
    if not outline:
        raise ValueError("The PDF has no usable outline/bookmarks.")
    return outline


def chapter_number(title: str) -> str | None:
    match = re.match(r"Chapter\s+(\d+)\b", title, re.IGNORECASE)
    return match.group(1) if match else None


def chapter_specs(outline: Sequence[OutlineEntry]) -> dict[str, dict[str, Any]]:
    chapters: dict[str, dict[str, Any]] = {}
    chapter_positions = [i for i, entry in enumerate(outline) if entry.level == 1 and chapter_number(entry.title)]
    for position_index, outline_index in enumerate(chapter_positions):
        entry = outline[outline_index]
        number = chapter_number(entry.title)
        assert number is not None
        next_outline_index = (
            chapter_positions[position_index + 1]
            if position_index + 1 < len(chapter_positions)
            else len(outline)
        )
        next_page = (
            outline[chapter_positions[position_index + 1]].pdf_page
            if position_index + 1 < len(chapter_positions)
            else None
        )
        title = re.sub(r"^Chapter\s+\d+\s*", "", entry.title, flags=re.IGNORECASE).strip()
        sections = [
            candidate
            for candidate in outline[outline_index + 1 : next_outline_index]
            if candidate.level >= 2
        ]
        chapters[number] = {
            "chapter_id": number,
            "title": title,
            "start_page": entry.pdf_page,
            "end_page_exclusive": next_page,
            "sections": sections,
        }
    return chapters


def section_fields(chapter_id: str, title: str) -> tuple[str, str]:
    numbered = re.match(rf"^{re.escape(chapter_id)}\.(\d+)\s+(.+)$", title)
    if numbered:
        return f"{chapter_id}.{numbered.group(1)}", numbered.group(2).strip()
    slug = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")
    if title.lower().startswith("chapter outline"):
        slug = "chapter_outline"
    elif title.lower().startswith("introduction"):
        slug = "introduction"
    return f"{chapter_id}.{slug or 'other'}", title


def section_type_for_id(section_id: str | None) -> str:
    if not section_id:
        return "unknown"
    suffix = section_id.partition(".")[2]
    if suffix.isdigit():
        return "section"
    if suffix == "introduction":
        return "chapter_intro"
    if suffix == "chapter_outline":
        return "chapter_outline"
    return "special"


def extract_printed_page(page: Any) -> int | None:
    footer_chars = [
        char
        for char in page.chars
        if float(char.get("top", 0)) >= float(page.height) - 65
    ]
    if not footer_chars:
        return None
    footer = extract_text(footer_chars, layout=False) or ""
    values = [int(value) for value in re.findall(r"(?<!\d)\d{1,4}(?!\d)", footer)]
    return max(values) if values else None


def extract_page_records(
    page: Any,
    document_id: str,
    source: str,
    chapter: dict[str, Any],
    pdf_page: int,
) -> tuple[list[OpenStaxRecord], list[dict[str, Any]]]:
    page_records: list[OpenStaxRecord] = []
    issues: list[dict[str, Any]] = []
    printed_page = extract_printed_page(page)
    nodes = list(semantic_nodes(page.structure_tree))
    same_page_sections = [
        entry for entry in chapter["sections"] if entry.pdf_page == pdf_page
    ]
    earlier_sections = [
        entry for entry in chapter["sections"] if entry.pdf_page < pdf_page
    ]
    current_section = (
        earlier_sections[-1]
        if earlier_sections
        else (same_page_sections[0] if same_page_sections else None)
    )

    candidates: list[tuple[list[float] | None, dict[str, Any], list[dict[str, Any]], str]] = []
    for node in nodes:
        fragments = node_fragments(page, node)
        text = join_fragments(fragments)
        bbox = union_bbox(fragment.get("bbox") for fragment in fragments)
        candidates.append((bbox, node, fragments, text))

    candidates.sort(
        key=lambda item: (
            item[0][1] if item[0] else float("inf"),
            item[0][0] if item[0] else float("inf"),
            item[3],
        )
    )

    for block_index, (bbox, node, fragments, text) in enumerate(candidates):
        record_type = record_type_for_node(node, fragments, text)
        if should_drop_record(text, record_type):
            continue
        normalized_text = text.casefold()
        for entry in same_page_sections:
            if entry.title.casefold() in normalized_text:
                current_section = entry
        if current_section is None:
            section_id, section_title = None, None
        else:
            section_id, section_title = section_fields(
                chapter["chapter_id"], current_section.title
            )
        formula_fragments = [fragment for fragment in fragments if fragment.get("kind") == "formula"]
        record_id = (
            f"{document_id}_ch{int(chapter['chapter_id']):02d}_"
            f"p{pdf_page:04d}_b{block_index:03d}"
        )
        record = OpenStaxRecord(
            record_id=record_id,
            chunk_source_id=record_id,
            document_id=document_id,
            chapter_id=chapter["chapter_id"],
            chapter_title=chapter["title"],
            section_id=section_id,
            section_title=section_title,
            section_type=section_type_for_id(section_id),
            record_type=record_type,
            text=text,
            pdf_page=pdf_page,
            printed_page=printed_page,
            page_block_index=block_index,
            page_text_index=block_index,
            bbox=bbox,
            source=source,
            formula_alt_text=" | ".join(
                fragment["alt_text"] for fragment in formula_fragments
            )
            or None,
            formula_display=" | ".join(
                fragment["display"] for fragment in formula_fragments
            )
            or None,
        )
        page_records.append(record)

        for fragment in formula_fragments:
            if fragment.get("confidence") in {"low", "medium"}:
                issues.append(
                    {
                        "issue_type": "formula_conversion",
                        "severity": "review",
                        "record_id": record_id,
                        "pdf_page": pdf_page,
                        "detail": "Symbolic display is best-effort; source accessibility text is preserved.",
                        "formula_alt_text": fragment.get("alt_text"),
                        "formula_display": fragment.get("display"),
                        "confidence": fragment.get("confidence"),
                    }
                )
        if record_type in {"table", "figure"}:
            issues.append(
                {
                    "issue_type": record_type,
                    "severity": "manual_review",
                    "record_id": record_id,
                    "pdf_page": pdf_page,
                    "detail": f"Review the extracted {record_type} description against the source PDF.",
                }
            )
    return page_records, issues


def deduplicate_records(records: Sequence[OpenStaxRecord]) -> list[OpenStaxRecord]:
    """Remove only exact adjacent duplicates, preserving textbook order."""
    kept: list[OpenStaxRecord] = []
    for record in records:
        if kept and (
            record.chapter_id,
            record.section_id,
            record.record_type,
            record.text,
        ) == (
            kept[-1].chapter_id,
            kept[-1].section_id,
            kept[-1].record_type,
            kept[-1].text,
        ):
            continue
        kept.append(record)
    return kept


def build_document_text(records: Sequence[OpenStaxRecord]) -> str:
    parts: list[str] = []
    cursor = 0
    for index, record in enumerate(records):
        if index:
            parts.append(DOCUMENT_SEPARATOR)
            cursor += len(DOCUMENT_SEPARATOR)
        record.char_start = cursor
        parts.append(record.text)
        cursor += len(record.text)
        record.char_end = cursor
    return "".join(parts)


def content_type_for_record(record: OpenStaxRecord) -> str:
    """Map parser-specific records to the shared ``ContentType`` contract."""
    section = (record.section_title or "").casefold()
    text = record.text.strip().casefold()

    if record.record_type == "formula":
        return "equation"
    if record.record_type == "table":
        return "table"
    if record.record_type in {"figure", "figure_caption"}:
        return "figure_caption"
    if section == "glossary":
        return "glossary"
    if section == "section summary":
        return "summary"
    if section == "conceptual questions":
        return "conceptual_question"
    if section in {"problems & exercises", "problems and exercises"}:
        return "problem"
    if text.startswith("example "):
        return "example"
    if text.startswith("check your understanding"):
        return "check_understanding"
    if "learning objectives" in text or text.startswith("by the end of this section"):
        return "learning_objective"
    if text.startswith(
        (
            "phet explorations",
            "career connection",
            "real world connections",
            "making connections",
            "take-home investigation",
        )
    ):
        return "sidebar"
    if record.record_type == "heading":
        return "heading"
    return "body"


def _block_metadata(record: OpenStaxRecord) -> dict[str, str]:
    """Return only string values, as required by ``TextBlock.metadata``."""
    metadata = {
        "record_type": record.record_type,
        "section_type": record.section_type,
        "chapter_title": record.chapter_title,
        "page_block_index": str(record.page_block_index),
        "printed_page": "" if record.printed_page is None else str(record.printed_page),
        "extraction_method": record.extraction_method,
    }
    if record.bbox is not None:
        metadata["bbox"] = json.dumps(record.bbox, ensure_ascii=False, separators=(",", ":"))
    if record.formula_alt_text is not None:
        metadata["formula_alt_text"] = record.formula_alt_text
    if record.formula_display is not None:
        metadata["formula_display"] = record.formula_display
    return metadata


def build_contract_payload(document: OpenStaxDocument) -> dict[str, Any]:
    """Serialize exactly the strict v1 classes in the team's ``models.py``.

    No parser-only fields are emitted at the document, chapter, or block level
    because ``ContractModel`` uses ``extra='forbid'``.  Parser diagnostics stay
    in the separate metadata/records/known-issues outputs.
    """
    chapter_records: dict[str, list[OpenStaxRecord]] = defaultdict(list)
    for record in document.records:
        chapter_records[record.chapter_id].append(record)

    chapters = []
    for chapter_id in document.selected_chapters:
        records = chapter_records.get(chapter_id, [])
        if not records:
            continue
        chapters.append(
            {
                "chapter_id": chapter_id,
                "title": records[0].chapter_title,
                "char_start": records[0].char_start,
                "char_end": records[-1].char_end,
                "page_start": min(record.pdf_page for record in records),
                "page_end": max(record.pdf_page for record in records),
            }
        )

    blocks = [
        {
            "block_id": record.record_id,
            "chapter_id": record.chapter_id,
            "section_id": record.section_id,
            "section_title": record.section_title,
            "content_type": content_type_for_record(record),
            "char_start": record.char_start,
            "char_end": record.char_end,
            "page_start": record.pdf_page,
            "page_end": record.pdf_page,
            "metadata": _block_metadata(record),
        }
        for record in document.records
    ]

    return {
        "schema_version": SCHEMA_VERSION,
        "document_id": document.document_id,
        "title": document.title,
        "version": document.edition,
        "source": document.source,
        "document_hash": document.document_hash,
        "parser_version": document.parser_version,
        "text": document.text,
        "chapters": chapters,
        "blocks": blocks,
    }


def validate_contract_payload(payload: dict[str, Any]) -> list[str]:
    """Dependency-free checks mirroring the relevant ``models.py`` rules."""
    errors: list[str] = []
    document_keys = {
        "schema_version",
        "document_id",
        "title",
        "version",
        "source",
        "document_hash",
        "parser_version",
        "text",
        "chapters",
        "blocks",
    }
    chapter_keys = {"chapter_id", "title", "char_start", "char_end", "page_start", "page_end"}
    block_keys = {
        "block_id",
        "chapter_id",
        "section_id",
        "section_title",
        "content_type",
        "char_start",
        "char_end",
        "page_start",
        "page_end",
        "metadata",
    }
    valid_content_types = {
        "body",
        "heading",
        "learning_objective",
        "figure_caption",
        "table",
        "equation",
        "example",
        "check_understanding",
        "sidebar",
        "summary",
        "conceptual_question",
        "problem",
        "glossary",
        "other",
    }
    if set(payload) != document_keys:
        errors.append("OpenStaxDocument keys do not exactly match models.py")
    text = payload.get("text", "")
    chapter_spans: dict[str, tuple[int, int]] = {}
    previous_end = 0
    for chapter in payload.get("chapters", []):
        if set(chapter) != chapter_keys:
            errors.append(f"OpenStaxChapter keys differ: {chapter.get('chapter_id')}")
        start, end = chapter["char_start"], chapter["char_end"]
        if start < previous_end or end <= start or end > len(text):
            errors.append(f"invalid chapter span: {chapter['chapter_id']}")
        if chapter["chapter_id"] in chapter_spans:
            errors.append(f"duplicate chapter_id: {chapter['chapter_id']}")
        chapter_spans[chapter["chapter_id"]] = (start, end)
        previous_end = end
    previous_end = 0
    seen_blocks: set[str] = set()
    for block in payload.get("blocks", []):
        label = block.get("block_id") or "<unnamed>"
        if set(block) != block_keys:
            errors.append(f"TextBlock keys differ: {label}")
        start, end = block["char_start"], block["char_end"]
        if start < previous_end or end <= start or end > len(text):
            errors.append(f"invalid block span: {label}")
        chapter_span = chapter_spans.get(block["chapter_id"])
        if chapter_span is None or start < chapter_span[0] or end > chapter_span[1]:
            errors.append(f"block outside chapter span: {label}")
        if label in seen_blocks:
            errors.append(f"duplicate block_id: {label}")
        seen_blocks.add(label)
        if block["content_type"] not in valid_content_types:
            errors.append(f"invalid content_type: {label}")
        if not all(isinstance(key, str) and isinstance(value, str) for key, value in block["metadata"].items()):
            errors.append(f"non-string block metadata: {label}")
        previous_end = end
    if not payload.get("chapters"):
        errors.append("chapters must not be empty")
    if not payload.get("blocks"):
        errors.append("blocks must not be empty")
    return errors


def validate_document(document: OpenStaxDocument) -> list[str]:
    errors: list[str] = []
    previous_end = 0
    seen_ids: set[str] = set()
    for index, record in enumerate(document.records):
        if record.record_id in seen_ids:
            errors.append(f"duplicate record_id: {record.record_id}")
        seen_ids.add(record.record_id)
        expected_start = previous_end + (len(document.text_separator) if index else 0)
        if record.char_start != expected_start:
            errors.append(f"non-contiguous span at {record.record_id}")
        if document.text[record.char_start : record.char_end] != record.text:
            errors.append(f"span mismatch at {record.record_id}")
        if record.char_end <= record.char_start:
            errors.append(f"empty span at {record.record_id}")
        previous_end = record.char_end
    if document.records and previous_end != len(document.text):
        errors.append("last record does not end at document text length")
    if any(r.text in RUNNING_TEXT for r in document.records):
        errors.append("running footer text was not removed")
    return errors


def evenly_spaced_sample(records: Sequence[OpenStaxRecord], count: int = 10) -> list[OpenStaxRecord]:
    if len(records) <= count:
        return list(records)
    indexes = sorted({round(i * (len(records) - 1) / (count - 1)) for i in range(count)})
    return [records[index] for index in indexes]


def build_qa_report(document: OpenStaxDocument, validation_errors: Sequence[str]) -> dict[str, Any]:
    sample = evenly_spaced_sample(document.records, 10)
    return {
        "parser_version": document.parser_version,
        "document_id": document.document_id,
        "automatic_validation": {
            "status": "passed" if not validation_errors else "failed",
            "errors": list(validation_errors),
            "record_count": len(document.records),
            "formula_record_count": sum(
                1 for record in document.records if record.formula_alt_text
            ),
        },
        "manual_review_required": True,
        "manual_review_instructions": [
            "Compare each sample with the same PDF page and section.",
            "Check chapter/section assignment and reading order.",
            "Check formulas against formula_alt_text and the source page.",
            "Check tables, figures, captions, and cross-page paragraphs.",
            "Set review_status to passed/failed and add reviewer_notes.",
        ],
        "samples": [
            {
                "record_id": record.record_id,
                "chapter_id": record.chapter_id,
                "section_id": record.section_id,
                "pdf_page": record.pdf_page,
                "printed_page": record.printed_page,
                "record_type": record.record_type,
                "text_excerpt": record.text[:500],
                "char_start": record.char_start,
                "char_end": record.char_end,
                "review_status": "pending",
                "reviewer_notes": "",
            }
            for record in sample
        ],
    }


def parse_openstax(
    pdf_path: Path,
    selected_chapters: Sequence[str],
    source_url: str,
    download_date: str,
    title: str,
    edition: str,
    document_id: str | None = None,
) -> OpenStaxDocument:
    pdf_path = pdf_path.resolve()
    document_hash = sha256_file(pdf_path)
    document_id = document_id or f"openstax-cp2e-{document_hash[:16]}"
    outline = parse_outline(pdf_path)
    specs = chapter_specs(outline)

    missing = [chapter for chapter in selected_chapters if chapter not in specs]
    if missing:
        raise ValueError(
            f"Chapters not found in PDF outline: {', '.join(missing)}. "
            f"Available: {', '.join(sorted(specs, key=int))}"
        )

    records: list[OpenStaxRecord] = []
    issues: list[dict[str, Any]] = [
        {
            "issue_type": "formula_representation",
            "severity": "known_limitation",
            "detail": (
                "Equations rendered as vector figures are recovered from Tagged-PDF accessibility text. "
                "The original alt text is authoritative; formula_display is a best-effort readable conversion."
            ),
        },
        {
            "issue_type": "cross_page_text",
            "severity": "manual_review",
            "detail": "Paragraphs are retained as tagged page blocks; cross-page joins require manual QA.",
        },
    ]

    selected = sorted({str(int(chapter)) for chapter in selected_chapters}, key=int)
    with pdfplumber.open(str(pdf_path)) as pdf:
        total_pages = len(pdf.pages)
        for chapter_id in selected:
            spec = specs[chapter_id]
            start_page = int(spec["start_page"])
            end_page_exclusive = int(spec["end_page_exclusive"] or (total_pages + 1))
            for pdf_page in range(start_page, min(end_page_exclusive, total_pages + 1)):
                page_records, page_issues = extract_page_records(
                    page=pdf.pages[pdf_page - 1],
                    document_id=document_id,
                    source=source_url,
                    chapter=spec,
                    pdf_page=pdf_page,
                )
                records.extend(page_records)
                issues.extend(page_issues)

    records = deduplicate_records(records)
    full_text = build_document_text(records)
    return OpenStaxDocument(
        document_id=document_id,
        title=title,
        edition=edition,
        source=source_url,
        source_file=pdf_path.name,
        source_format="PDF",
        download_date=download_date,
        document_hash=document_hash,
        parser_version=PARSER_VERSION,
        selected_chapters=selected,
        text_separator=DOCUMENT_SEPARATOR,
        text=full_text,
        records=records,
        known_issues=issues,
    )


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def write_outputs(document: OpenStaxDocument, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    validation_errors = validate_document(document)
    if validation_errors:
        raise ValueError("Document validation failed: " + "; ".join(validation_errors[:10]))

    contract_payload = build_contract_payload(document)
    contract_errors = validate_contract_payload(contract_payload)
    if contract_errors:
        raise ValueError("models.py contract validation failed: " + "; ".join(contract_errors[:10]))
    write_json(output_dir / "openstax_document.json", contract_payload)

    with (output_dir / "blocks.jsonl").open("w", encoding="utf-8", newline="\n") as stream:
        for block in contract_payload["blocks"]:
            stream.write(json.dumps(block, ensure_ascii=False) + "\n")

    with (output_dir / "records.jsonl").open("w", encoding="utf-8", newline="\n") as stream:
        for record in document.records:
            stream.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")

    # Compatibility outputs retained from parser v1.0.0.
    with (output_dir / "all_records.jsonl").open("w", encoding="utf-8", newline="\n") as stream:
        for record in document.records:
            stream.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")
    records_by_chapter: dict[str, list[OpenStaxRecord]] = defaultdict(list)
    for record in document.records:
        records_by_chapter[record.chapter_id].append(record)
    for chapter_id, chapter_records in sorted(records_by_chapter.items(), key=lambda item: int(item[0])):
        write_json(
            output_dir / f"chapter_{chapter_id}.json",
            [asdict(record) for record in chapter_records],
        )
        with (output_dir / f"chapter_{chapter_id}.jsonl").open(
            "w", encoding="utf-8", newline="\n"
        ) as stream:
            for record in chapter_records:
                stream.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")

    type_counts = Counter(record.record_type for record in document.records)
    content_type_counts = Counter(
        block["content_type"] for block in contract_payload["blocks"]
    )
    chapter_counts = Counter(record.chapter_id for record in document.records)
    metadata = {
        "schema_version": SCHEMA_VERSION,
        "document_id": document.document_id,
        "title": document.title,
        "version": document.edition,
        "source": document.source,
        "source_file": document.source_file,
        "source_format": document.source_format,
        "download_date": document.download_date,
        "document_hash": document.document_hash,
        "parser_version": document.parser_version,
        "selected_chapters": document.selected_chapters,
        "text_separator": document.text_separator,
    }
    metadata["statistics"] = {
        "character_count": len(document.text),
        "record_count": len(document.records),
        "block_count": len(contract_payload["blocks"]),
        "record_types": dict(sorted(type_counts.items())),
        "content_types": dict(sorted(content_type_counts.items())),
        "records_by_chapter": dict(sorted(chapter_counts.items(), key=lambda item: int(item[0]))),
        "known_issue_count": len(document.known_issues),
    }
    write_json(output_dir / "metadata.json", metadata)
    write_json(output_dir / "known_issues.json", document.known_issues)
    with (output_dir / "known_issues.jsonl").open("w", encoding="utf-8", newline="\n") as stream:
        for issue in document.known_issues:
            stream.write(json.dumps(issue, ensure_ascii=False) + "\n")
    write_json(output_dir / "qa_report.json", build_qa_report(document, validation_errors))
    write_json(output_dir / "stats.json", metadata["statistics"])
    write_json(
        output_dir / "run_manifest.json",
        {
            "source_file": document.source_file,
            "document_hash": document.document_hash,
            "parser_version": document.parser_version,
            "selected_chapters": document.selected_chapters,
        },
    )


def expand_chapter_args(values: Sequence[str]) -> list[str]:
    """Accept both v1 comma/range syntax and v1.1 space-separated syntax."""
    chapters: set[int] = set()
    for value in values:
        for part in value.split(","):
            part = part.strip()
            if not part:
                continue
            if "-" in part:
                start_text, end_text = part.split("-", 1)
                start, end = int(start_text), int(end_text)
                if end < start:
                    raise ValueError(f"Invalid descending chapter range: {part}")
                chapters.update(range(start, end + 1))
            else:
                chapters.add(int(part))
    if not chapters:
        raise ValueError("At least one chapter must be selected.")
    return [str(value) for value in sorted(chapters)]


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Parse 2-3 OpenStax College Physics 2e chapters into traceable RAG records."
    )
    parser.add_argument("pdf", type=Path, help="Path to college-physics-2e PDF")
    parser.add_argument(
        "--chapters",
        nargs="+",
        default=["2", "3", "4"],
        help="Chapter numbers to parse (default: 2 3 4)",
    )
    parser.add_argument(
        "--output-dir",
        "--output",
        dest="output_dir",
        type=Path,
        default=Path("openstax_output"),
        help="Output directory (default: openstax_output)",
    )
    parser.add_argument("--source-url", default=DEFAULT_SOURCE_URL)
    parser.add_argument("--download-date", default=date.today().isoformat())
    parser.add_argument("--title", "--version", dest="title", default="College Physics 2e")
    parser.add_argument("--edition", default="2e")
    parser.add_argument(
        "--document-id",
        default=None,
        help="Optional stable document ID; default is derived from the source hash",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_argument_parser().parse_args(argv)
    if not args.pdf.is_file():
        print(f"PDF not found: {args.pdf}", file=sys.stderr)
        return 2
    try:
        selected_chapters = expand_chapter_args(args.chapters)
        document = parse_openstax(
            pdf_path=args.pdf,
            selected_chapters=selected_chapters,
            source_url=args.source_url,
            download_date=args.download_date,
            title=args.title,
            edition=args.edition,
            document_id=args.document_id,
        )
        write_outputs(document, args.output_dir)
    except Exception as exc:
        print(f"Parser failed: {exc}", file=sys.stderr)
        return 1

    print(f"Parsed chapters: {', '.join(document.selected_chapters)}")
    print(f"Records: {len(document.records)}")
    print(f"Characters: {len(document.text)}")
    print(f"Document ID: {document.document_id}")
    print(f"Output: {args.output_dir.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
