"""Shared checkpointed screening utilities for automatic M3 candidates."""

from __future__ import annotations

import csv
import json
import math
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA = ROOT / "standardized"
DEFAULT_BLOCKS = (
    ROOT / "m3_unified_source_corpus" / "source_corpus" / "evidence_source_blocks.jsonl"
)

TOKEN_RE = re.compile(r"[a-z0-9]+")
STOPWORDS = {
    "about",
    "after",
    "again",
    "also",
    "because",
    "being",
    "between",
    "could",
    "does",
    "from",
    "have",
    "into",
    "more",
    "most",
    "other",
    "over",
    "same",
    "such",
    "than",
    "that",
    "their",
    "there",
    "these",
    "they",
    "this",
    "those",
    "through",
    "under",
    "what",
    "when",
    "where",
    "which",
    "while",
    "with",
    "would",
    "your",
    "will",
    "were",
    "been",
    "each",
    "how",
    "whose",
}
ALLOWED_TYPES = {"body", "example", "figure_caption", "glossary", "table", "equation"}

STATE_VERSION = 1
SCHEMA_FIELDS = [
    "question_id",
    "source_split",
    "question",
    "gold_answer_text",
    "answerable",
    "gold_core_evidence_sets",
    "partial_evidence",
    "question_difficulty",
    "question_type",
    "concept_group",
    "personalisation_eligibility",
    "eligibility_reason",
    "split",
    "corpus_version",
    "parser_version",
    "gold_annotation_version",
    "annotation_status",
    "review_record_id",
    "source",
    "manual_review",
    "accepted_evidence_ids",
]


def tokens(text: str) -> set[str]:
    return {
        token
        for token in TOKEN_RE.findall(text.lower())
        if len(token) > 2 and token not in STOPWORDS
    }


def load_questions(data_dir: Path) -> list[dict[str, Any]]:
    questions: list[dict[str, Any]] = []
    for path in sorted(data_dir.glob("*.jsonl")):
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                if line.strip():
                    questions.append(json.loads(line))
    return questions


def load_blocks(path: Path) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            block = json.loads(line)
            if block["content_type"] in ALLOWED_TYPES:
                block["_tokens"] = tokens(block["text"])
                blocks.append(block)
    return blocks


def option_answer(question: dict[str, Any]) -> tuple[str, str]:
    for option in question["options"]:
        if option["is_correct"]:
            return option["source_field"], option["text"]
    raise ValueError(f"{question['question_id']}: no correct option")


def query_tokens(question: dict[str, Any], answer: str) -> set[str]:
    return tokens(question["question"]) | tokens(question["support"]) | tokens(answer)


def score_block(block: dict[str, Any], query: set[str], answer: str) -> tuple[float, float, bool]:
    overlap = query & block["_tokens"]
    recall = len(overlap) / max(len(query), 1)
    precision = len(overlap) / max(len(block["_tokens"]), 1)
    answer_terms = tokens(answer)
    answer_exact = bool(answer_terms) and answer_terms <= block["_tokens"]
    answer_phrase = answer.lower() in block["text"].lower()
    score = 0.62 * recall + 0.28 * math.sqrt(precision) + (0.32 if answer_exact else 0.0)
    if answer_phrase:
        score += 0.28
    return score, len(overlap) / max(len(query), 1), answer_exact or answer_phrase


def retrieve(
    question: dict[str, Any],
    blocks: list[dict[str, Any]],
    postings: dict[str, set[int]],
    limit: int = 30,
) -> list[dict[str, Any]]:
    _, answer = option_answer(question)
    query = query_tokens(question, answer)
    candidate_ids: set[int] = set()
    answer_terms = tokens(answer)
    rare_terms = sorted(query, key=lambda token: len(postings.get(token, set())))[:12]
    active_terms = set(rare_terms) | answer_terms
    for token in active_terms:
        candidate_ids.update(postings.get(token, set()))
    ranked: list[dict[str, Any]] = []
    for index in candidate_ids:
        block = blocks[index]
        score, overlap, answer_exact = score_block(block, query, answer)
        ranked.append(
            {"block": block, "score": score, "overlap": overlap, "answer_exact": answer_exact}
        )
    ranked.sort(
        key=lambda item: (item["score"], item["overlap"], item["answer_exact"]), reverse=True
    )
    if limit >= 30:
        return ranked[:limit]
    deduplicated: list[dict[str, Any]] = []
    for item in ranked:
        block = item["block"]
        duplicate = False
        for previous in deduplicated:
            other = previous["block"]
            if str(block.get("document_id", "")) != str(other.get("document_id", "")) or str(
                block["chapter_id"]
            ) != str(other["chapter_id"]):
                continue
            start = max(int(block["chapter_char_start"]), int(other["chapter_char_start"]))
            end = min(int(block["chapter_char_end"]), int(other["chapter_char_end"]))
            overlap = max(0, end - start)
            shorter = min(
                int(block["chapter_char_end"]) - int(block["chapter_char_start"]),
                int(other["chapter_char_end"]) - int(other["chapter_char_start"]),
            )
            if shorter > 0 and overlap / shorter >= 0.85:
                duplicate = True
                break
        if not duplicate:
            deduplicated.append(item)
        if len(deduplicated) >= limit:
            break
    return deduplicated


def best_pair(
    ranked: list[dict[str, Any]],
    question: dict[str, Any],
    answer: str,
) -> dict[str, Any] | None:
    best: dict[str, Any] | None = None
    query = query_tokens(question, answer)
    for left_index, left in enumerate(ranked[:15]):
        for right in ranked[left_index + 1 : 15]:
            a = left["block"]
            b = right["block"]
            if str(a.get("document_id", "")) != str(b.get("document_id", "")) or str(
                a["chapter_id"]
            ) != str(b["chapter_id"]):
                continue
            distance = abs(int(a["chapter_char_start"]) - int(b["chapter_char_end"]))
            if distance > 1800:
                continue
            combined = a["_tokens"] | b["_tokens"]
            combined_overlap = len(query & combined) / max(len(query), 1)
            pair_score = 0.62 * combined_overlap + 0.18 * max(left["score"], right["score"])
            if best is None or pair_score > best["pair_score"]:
                best = {
                    "left": left,
                    "right": right,
                    "pair_score": pair_score,
                    "combined_overlap": combined_overlap,
                }
    return best


def preview(text: str, limit: int = 260) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 3] + "..."


def make_candidate(question: dict[str, Any], ranked: list[dict[str, Any]]) -> dict[str, Any]:
    source_field, answer = option_answer(question)
    top = ranked[0]
    pair = best_pair(ranked, question, answer)
    pair_is_useful = pair is not None and pair["combined_overlap"] > top["overlap"] + 0.08
    if pair_is_useful:
        selected = [pair["left"], pair["right"]]
        bucket = "weak_or_multi_evidence"
        path = "AND: two nearby evidence blocks"
        score = pair["pair_score"]
    else:
        selected = [top]
        bucket = "strong_single_evidence"
        path = "single evidence block"
        score = top["score"]
    blocks = [item["block"] for item in selected]
    return {
        "question_id": question["question_id"],
        "source_split": question["split"],
        "question": question["question"],
        "gold_answer_text": answer,
        "sciq_support": question["support"],
        "split": question["split"],
        "selection_bucket": bucket,
        "retrieval_score": f"{score:.4f}",
        "top_answer_exact": str(top["answer_exact"]),
        "top_chapter_id": str(top["block"]["chapter_id"]),
        "top_section_title": top["block"]["section_title"],
        "top_content_type": "+".join(block["content_type"] for block in blocks),
        "top_block_ids": ";".join(block["block_id"] for block in blocks),
        "top_char_start": ";".join(str(block["chapter_char_start"]) for block in blocks),
        "top_char_end": ";".join(str(block["chapter_char_end"]) for block in blocks),
        "top_preview_text": " || ".join(preview(block["text"]) for block in blocks),
        "support_token_overlap": f"{top['overlap']:.4f}",
        "evidence_char_length": str(
            sum(
                int(block["chapter_char_end"]) - int(block["chapter_char_start"])
                for block in blocks
            )
        ),
        "evidence_path": path,
        "multi_block_candidate": str(len(blocks) > 1),
        "manual_review_status": "pending",
        "review_notes": "",
    }


def _document_id(block_id: str) -> str:
    return block_id.split("_ch", 1)[0]


def schema_csv_row(
    candidate: dict[str, Any],
    blocks: dict[str, dict[str, Any]],
    manifest: dict[str, Any],
) -> dict[str, str]:
    """Flatten one candidate into schema-shaped CSV cells."""

    selected = [blocks[block_id] for block_id in candidate["top_block_ids"].split(";")]
    joint = len(selected) > 1
    spans = []
    for block in selected:
        start = int(block.get("char_start", block["chapter_char_start"]))
        end = int(block.get("char_end", block["chapter_char_end"]))
        chapter_start = int(block.get("chapter_char_start", start))
        chapter_end = int(block.get("chapter_char_end", end))
        spans.append(
            {
                "span_id": f"{block['block_id']}_gold_candidate",
                "document_id": block.get(
                    "document_id", manifest.get("document_id", _document_id(block["block_id"]))
                ),
                "chapter_id": str(block["chapter_id"]),
                "char_start": start,
                "char_end": end,
                "verbatim_text": block["text"],
                "sufficiency": "joint_core" if joint else "core_sufficient",
                "annotation_note": "Automatically retrieved candidate; manual review required.",
                "block_id": block["block_id"],
                "chapter_char_start": chapter_start,
                "chapter_char_end": chapter_end,
            }
        )

    schema_row: dict[str, Any] = {
        "question_id": candidate["question_id"],
        "source_split": candidate["source_split"],
        "question": candidate["question"],
        "gold_answer_text": candidate["gold_answer_text"],
        "answerable": True,
        "gold_core_evidence_sets": [spans],
        "accepted_evidence_ids": [],
        "partial_evidence": [],
        "question_difficulty": "pending",
        "question_type": "pending",
        "concept_group": "pending",
        "personalisation_eligibility": "pending",
        "eligibility_reason": "Pending manual evidence review and M1 taxonomy confirmation.",
        "split": "proposed_test" if candidate["split"] == "test" else "pending",
        "corpus_version": manifest["corpus_version"],
        "parser_version": manifest["parser_version"],
        "gold_annotation_version": "m3_gold_v0.1.1",
        "annotation_status": "draft",
        "review_record_id": f"candidate_review_{candidate['question_id']}",
        "source": {
            "dataset": "SciQ standardized",
            "source_question_id": candidate["question_id"],
            "support": candidate["sciq_support"],
        },
        "manual_review": "",
    }
    return {
        key: json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        if isinstance(value, (dict, list))
        else str(value).lower()
        if isinstance(value, bool)
        else str(value)
        for key, value in schema_row.items()
    }


def add_full_evidence(row: dict[str, Any], blocks: dict[str, dict[str, Any]]) -> dict[str, Any]:
    result = dict(row)
    selected = [blocks[block_id] for block_id in row["top_block_ids"].split(";")]
    result["evidence_count"] = str(len(selected))
    for index in range(2):
        prefix = f"evidence_{index + 1}_"
        if index < len(selected):
            block = selected[index]
            values = {
                "block_id": block["block_id"],
                "content_type": block["content_type"],
                "chapter_id": str(block["chapter_id"]),
                "char_start": str(block["chapter_char_start"]),
                "char_end": str(block["chapter_char_end"]),
                "section_title": block["section_title"],
                "text": block["text"],
            }
        else:
            values = {
                key: ""
                for key in (
                    "block_id",
                    "content_type",
                    "chapter_id",
                    "char_start",
                    "char_end",
                    "section_title",
                    "text",
                )
            }
        for key, value in values.items():
            result[prefix + key] = value
    return result


def load_state(path: Path, target: int) -> dict[str, Any]:
    if not path.exists():
        return {
            "state_version": STATE_VERSION,
            "target": target,
            "next_question_index": 0,
            "selected_ids": [],
        }
    state = json.loads(path.read_text(encoding="utf-8"))
    if state.get("state_version") != STATE_VERSION or int(state.get("target", target)) > target:
        raise ValueError(f"incompatible checkpoint: {path}; use --reset")
    state["target"] = target
    return state


def save_state(path: Path, state: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def prepare_output(path: Path, reset: bool) -> None:
    if reset:
        path.unlink(missing_ok=True)
    elif path.exists():
        return


def screen(
    *,
    target: int,
    output: Path,
    checkpoint: Path,
    predicate: Callable[[dict[str, Any]], bool],
    bucket: str,
    reset: bool = False,
    max_questions: int | None = None,
    data_dir: Path = DEFAULT_DATA,
    blocks_path: Path = DEFAULT_BLOCKS,
    quality_evaluator: Callable[
        [dict[str, Any], dict[str, Any], dict[str, dict[str, Any]]], dict[str, Any]
    ]
    | None = None,
    retrieval_limit: int = 30,
) -> None:
    if reset:
        checkpoint.unlink(missing_ok=True)
    elif output.exists() != checkpoint.exists():
        raise FileExistsError(
            "output and checkpoint must either both exist or both be absent; "
            "use --reset to start over"
        )
    prepare_output(output, reset)
    state = load_state(checkpoint, target)
    selected_ids = set(state["selected_ids"])

    questions = load_questions(data_dir)
    blocks = load_blocks(blocks_path)
    block_by_id = {block["block_id"]: block for block in blocks}
    manifest_path = blocks_path.parent / "corpus_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    postings: dict[str, set[int]] = {}
    for index, block in enumerate(blocks):
        for token in block["_tokens"]:
            postings.setdefault(token, set()).add(index)

    output_exists = output.exists() and not reset
    with output.open("a", encoding="utf-8", newline="") as stream:
        writer = None
        if not output_exists:
            writer = csv.DictWriter(stream, fieldnames=SCHEMA_FIELDS)
            writer.writeheader()
        processed_this_run = 0
        index = int(state["next_question_index"])
        while index < len(questions) and len(selected_ids) < target:
            if max_questions is not None and processed_this_run >= max_questions:
                break
            question = questions[index]
            ranked = retrieve(question, blocks, postings, limit=retrieval_limit)
            if ranked:
                candidate = make_candidate(question, ranked)
                if quality_evaluator is not None:
                    candidate["_quality"] = quality_evaluator(question, candidate, block_by_id)
                if predicate(candidate) and question["question_id"] not in selected_ids:
                    candidate["selection_bucket"] = bucket
                    if writer is None:
                        writer = csv.DictWriter(stream, fieldnames=SCHEMA_FIELDS)
                    writer.writerow(schema_csv_row(candidate, block_by_id, manifest))
                    stream.flush()
                    selected_ids.add(question["question_id"])
            index += 1
            processed_this_run += 1
            state["next_question_index"] = index
            state["selected_ids"] = sorted(selected_ids)
            save_state(checkpoint, state)

    print(f"selected={len(selected_ids)}/{target}")
    print(f"next_question_index={state['next_question_index']}")
    print(f"checkpoint={checkpoint}")
