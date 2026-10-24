"""Find preliminary Multi-evidence candidates for manual review.

This is a deterministic candidate finder, not a gold annotator. It scans SciQ
sequentially, requires two distinct same-chapter blocks with independent
question/support signals, and writes only the shared M3 schema columns.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import math
from pathlib import Path
from typing import Any

from candidate_screening_common import (
    DEFAULT_BLOCKS,
    DEFAULT_DATA,
    SCHEMA_FIELDS,
    load_blocks,
    load_questions,
    option_answer,
    retrieve,
    schema_csv_row,
    tokens,
)

DEFAULT_OUTPUT = Path(__file__).with_name("candidate_pool_multi_v1_3_2.csv")
DIAGNOSTICS_PATTERN = Path(__file__).with_name(
    "candidate_pool_multi_v1_3_2_batch_{batch:02d}_diagnostics.csv"
)
DEFAULT_CHECKPOINT = Path(__file__).with_name(
    "candidate_pool_multi_v1_3_2.checkpoint.json"
)

GENERIC_CONTEXT_TERMS = {
    "called", "term", "type", "kind", "means", "thing", "something",
    "used", "use", "does", "do", "is", "are", "what", "which", "how",
}


def overlap(left: set[str], right: set[str]) -> float:
    return len(left & right) / max(len(left), 1)


def answer_match(answer: str, text: str) -> bool:
    answer_lower = answer.strip().lower()
    answer_terms = tokens(answer)
    text_lower = text.lower()
    return bool(answer_lower and answer_lower in text_lower) or (
        bool(answer_terms) and answer_terms <= tokens(text)
    )


def block_features(
    item: dict[str, Any],
    question_tokens: set[str],
    support_tokens: set[str],
    answer_tokens: set[str],
    answer: str,
) -> dict[str, Any]:
    block = item["block"]
    block_tokens = block["_tokens"]
    question_context_tokens = question_tokens - answer_tokens - GENERIC_CONTEXT_TERMS
    support_context_tokens = support_tokens - answer_tokens
    context_tokens = question_context_tokens | support_context_tokens
    question_overlap = overlap(question_tokens, block_tokens)
    support_overlap = overlap(support_tokens, block_tokens)
    context_overlap = overlap(context_tokens, block_tokens)
    question_context_overlap = overlap(question_context_tokens, block_tokens)
    support_context_overlap = overlap(support_context_tokens, block_tokens)
    relevance = 0.35 * question_overlap + 0.35 * context_overlap + 0.30 * min(
        float(item["score"]) / 0.50, 1.0
    )
    return {
        "item": item,
        "block": block,
        "question_overlap": question_overlap,
        "support_overlap": support_overlap,
        "context_overlap": question_context_overlap,
        "question_context_overlap": question_context_overlap,
        "support_context_overlap": support_context_overlap,
        "question_context_match_count": len(question_context_tokens & block_tokens),
        "support_context_match_count": len(support_context_tokens & block_tokens),
        "answer_match": answer_match(answer, block["text"]),
        "relevance": relevance,
        "context_tokens": context_tokens,
        "question_context_tokens": question_context_tokens,
        "support_context_tokens": support_context_tokens,
    }


def supporting_block_reason(
    feature: dict[str, Any],
    min_relevance: float,
    min_score: float,
    min_context_overlap: float,
    min_non_answer_support_overlap: float,
    min_context_concepts: int,
    min_support_concepts: int,
) -> str | None:
    """Classify a block as supporting or return an interpretable rejection reason."""

    if (
        float(feature["item"]["score"]) < min_score
        or feature["relevance"] < min_relevance
        or feature["question_context_overlap"] < min_context_overlap
        or feature["support_context_overlap"] < min_non_answer_support_overlap
    ):
        return "relevance"

    context_size = len(feature["question_context_tokens"])
    required_context = min_context_concepts if context_size >= 3 else 1
    if feature["question_context_match_count"] < required_context:
        return "context_breadth"
    if feature["support_context_match_count"] < min_support_concepts:
        return "support_alignment"

    # A lightweight relationship bridge: either multiple question concepts are
    # connected, or the answer is tied to one question concept and the support
    # text supplies an additional non-answer signal.
    relationship_supported = (
        feature["question_context_match_count"] >= 2
        or (
            feature["answer_match"]
            and feature["question_context_match_count"] >= 1
            and feature["support_context_match_count"] >= 1
        )
        or (
            feature["question_context_match_count"] >= 1
            and feature["support_context_match_count"] >= 2
        )
    )
    if not relationship_supported:
        return "topic_only" if not feature["answer_match"] else "relationship_support"
    return None


def near_duplicate(left: dict[str, Any], right: dict[str, Any]) -> bool:
    a, b = left["block"], right["block"]
    if (
        str(a.get("document_id", "")) != str(b.get("document_id", ""))
        or str(a["chapter_id"]) != str(b["chapter_id"])
    ):
        return False
    start = max(int(a["chapter_char_start"]), int(b["chapter_char_start"]))
    end = min(int(a["chapter_char_end"]), int(b["chapter_char_end"]))
    shorter = min(
        int(a["chapter_char_end"]) - int(a["chapter_char_start"]),
        int(b["chapter_char_end"]) - int(b["chapter_char_start"]),
    )
    char_overlap = shorter > 0 and max(0, end - start) / shorter >= 0.85
    token_union = left["block"]["_tokens"] | right["block"]["_tokens"]
    token_jaccard = len(left["block"]["_tokens"] & right["block"]["_tokens"]) / max(
        len(token_union), 1
    )
    text_a = " ".join(a["text"].lower().split())
    text_b = " ".join(b["text"].lower().split())
    return char_overlap or token_jaccard >= 0.78 or text_a in text_b or text_b in text_a


def pair_distance(left: dict[str, Any], right: dict[str, Any]) -> int | None:
    """Return same-chapter distance, or None for invalid/duplicate pairs."""

    if near_duplicate(left, right):
        return None
    a, b = left["block"], right["block"]
    if (
        str(a.get("document_id", "")) != str(b.get("document_id", ""))
        or str(a["chapter_id"]) != str(b["chapter_id"])
    ):
        return None
    return min(
        abs(int(a["chapter_char_start"]) - int(b["chapter_char_end"])),
        abs(int(b["chapter_char_start"]) - int(a["chapter_char_end"])),
    )


def pair_is_supporting(
    left: dict[str, Any],
    right: dict[str, Any],
    min_pair_context_overlap: float,
    min_unique_context_tokens: int,
    min_unique_support_tokens: int,
    min_complementarity_gain: float,
) -> bool:
    metrics = pair_metrics(left, right)
    return (
        metrics["combined_context_overlap"] >= min_pair_context_overlap
        and metrics["left_unique_context_count"] >= min_unique_context_tokens
        and metrics["right_unique_context_count"] >= min_unique_context_tokens
        and metrics["left_unique_support_count"] >= min_unique_support_tokens
        and metrics["right_unique_support_count"] >= min_unique_support_tokens
        and metrics["complementarity_gain"] >= min_complementarity_gain
    )


def pair_metrics(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    context = left["context_tokens"]
    combined_tokens = left["block"]["_tokens"] | right["block"]["_tokens"]
    combined_overlap = overlap(context, combined_tokens)
    best_single = max(
        left["question_context_overlap"], right["question_context_overlap"]
    )
    left_unique_context = (left["block"]["_tokens"] & context) - right["block"]["_tokens"]
    right_unique_context = (right["block"]["_tokens"] & context) - left["block"]["_tokens"]
    support_context = left["support_context_tokens"]
    left_unique_support = (
        left["block"]["_tokens"] & support_context
    ) - right["block"]["_tokens"]
    right_unique_support = (
        right["block"]["_tokens"] & support_context
    ) - left["block"]["_tokens"]
    return {
        "combined_context_overlap": combined_overlap,
        "complementarity_gain": combined_overlap - best_single,
        "left_unique_context_count": len(left_unique_context),
        "right_unique_context_count": len(right_unique_context),
        "left_unique_support_count": len(left_unique_support),
        "right_unique_support_count": len(right_unique_support),
    }


def make_row(
    question: dict[str, Any],
    selected: list[dict[str, Any]],
    blocks_by_id: dict[str, dict[str, Any]],
    manifest: dict[str, Any],
) -> dict[str, str]:
    _, answer = option_answer(question)
    candidate = {
        "question_id": str(question["question_id"]),
        "source_split": str(question["split"]),
        "question": question["question"],
        "gold_answer_text": answer,
        "sciq_support": question["support"],
        "split": question["split"],
        "top_block_ids": ";".join(
            feature["block"]["block_id"] for feature in selected
        ),
    }
    return schema_csv_row(candidate, blocks_by_id, manifest)


def existing_question_ids(path: Path) -> set[str]:
    if not path.exists() or path.stat().st_size == 0:
        return set()
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != SCHEMA_FIELDS:
            raise ValueError(f"unexpected candidate CSV header: {path}")
        ids = [row["question_id"] for row in reader]
    if len(ids) != len(set(ids)):
        raise ValueError(f"duplicate question_id in cumulative Multi CSV: {path}")
    return set(ids)


def append_row_atomic(path: Path, row: dict[str, str]) -> None:
    """Append one schema row by replacing a complete temporary CSV."""

    existing = path.read_bytes() if path.exists() else b""
    if existing and not existing.endswith(b"\n"):
        existing += b"\n"
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=SCHEMA_FIELDS, lineterminator="\n")
    if not existing:
        writer.writeheader()
    writer.writerow(row)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(existing + buffer.getvalue().encode("utf-8"))
    temporary.replace(path)


DIAGNOSTIC_FIELDS = [
    "question_id", "left_block_id", "right_block_id", "left_answer_match",
    "right_answer_match", "left_context_overlap", "right_context_overlap",
    "left_support_overlap", "right_support_overlap", "combined_context_overlap",
    "complementarity_gain", "left_unique_context_count",
    "right_unique_context_count", "left_unique_support_count",
    "right_unique_support_count", "pair_distance", "pair_score",
]


def append_diagnostic(path: Path, row: dict[str, Any]) -> None:
    is_new = not path.exists() or path.stat().st_size == 0
    with path.open("a", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=DIAGNOSTIC_FIELDS)
        if is_new:
            writer.writeheader()
        writer.writerow(row)


def load_or_create_state(path: Path, target: int, reset: bool) -> dict[str, Any]:
    if reset:
        path.unlink(missing_ok=True)
    if path.exists():
        state = json.loads(path.read_text(encoding="utf-8"))
        if state.get("state_version") != 1 or state.get("target") != target:
            raise ValueError(f"incompatible checkpoint: {path}; use --reset")
        if "next_question_index" not in state:
            raise ValueError("checkpoint has no scan position; use --reset")
        return state
    return {
        "state_version": 1,
        "target": target,
        "next_question_index": 0,
        "batch_number": 0,
        "selected_ids": [],
        "stats": {},
    }


def save_state(path: Path, state: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def run(args: argparse.Namespace) -> dict[str, Any]:
    state = load_or_create_state(args.checkpoint, args.target_per_batch, args.reset)
    batch_number = 1 if args.reset else int(state["batch_number"]) + 1
    output = args.output or DEFAULT_OUTPUT
    diagnostics = args.diagnostics or Path(
        str(DIAGNOSTICS_PATTERN).format(batch=batch_number)
    )
    if args.reset:
        output.unlink(missing_ok=True)
        diagnostics.unlink(missing_ok=True)
    cumulative_ids = existing_question_ids(output)

    state.update({
        "state_version": 1,
        "batch_number": batch_number,
        "selected_ids": [],
        "stats": {
            "processed": 0,
            "rejected_relevance": 0,
            "rejected_topic_only": 0,
            "rejected_context_breadth": 0,
            "rejected_support_alignment": 0,
            "rejected_relationship_support": 0,
            "rejected_duplicate": 0,
            "rejected_pair_quality": 0,
            "missing_support": 0,
            "missing_evidence": 0,
        },
        "output": str(output),
    })
    save_state(args.checkpoint, state)

    questions = load_questions(args.data_dir)
    excluded_ids = set()
    if args.exclude_question_ids:
        excluded_ids = {
            line.strip()
            for line in args.exclude_question_ids.read_text(encoding="utf-8").splitlines()
            if line.strip()
        }
    blocks = load_blocks(args.blocks)
    blocks_by_id = {block["block_id"]: block for block in blocks}
    manifest = json.loads(
        (args.blocks.parent / "corpus_manifest.json").read_text(encoding="utf-8")
    )
    postings: dict[str, set[int]] = {}
    for index, block in enumerate(blocks):
        for token in block["_tokens"]:
            postings.setdefault(token, set()).add(index)

    selected_ids: set[str] = set()
    processed_this_run = 0
    index = int(state["next_question_index"])
    while index < len(questions) and len(selected_ids) < args.target_per_batch:
        if args.max_questions is not None and processed_this_run >= args.max_questions:
            break
        question = questions[index]
        support = question.get("support", "").strip()
        if not support:
            state["stats"]["missing_support"] += 1
        else:
            answer = option_answer(question)[1]
            ranked = retrieve(question, blocks, postings, limit=args.top_k)
            if not ranked:
                state["stats"]["missing_evidence"] += 1
            else:
                question_tokens = tokens(question["question"])
                support_tokens = tokens(support)
                answer_tokens = tokens(answer)
                features = [
                    block_features(
                        item, question_tokens, support_tokens, answer_tokens, answer
                    )
                    for item in ranked
                ]
                supporting = []
                for feature in features:
                    reason = supporting_block_reason(
                        feature,
                        args.min_relevance,
                        args.min_score,
                        args.min_context_overlap,
                        args.min_non_answer_support_overlap,
                        args.min_context_concepts,
                        args.min_support_concepts,
                    )
                    if reason is None:
                        supporting.append(feature)
                    else:
                        state["stats"][f"rejected_{reason}"] += 1
                        if reason == "relevance":
                            state["stats"]["rejected_relevance"] += 1
                best_pair = None
                best_score = -math.inf
                for left_index, left in enumerate(supporting):
                    for right in supporting[left_index + 1 :]:
                        distance = pair_distance(left, right)
                        if distance is None:
                            if near_duplicate(left, right):
                                state["stats"]["rejected_duplicate"] += 1
                            else:
                                state["stats"]["rejected_pair_quality"] += 1
                            continue
                        if not pair_is_supporting(
                            left, right, args.min_pair_context_overlap,
                            args.min_unique_context_tokens,
                            args.min_unique_support_tokens,
                            args.min_complementarity_gain,
                        ):
                            state["stats"]["rejected_pair_quality"] += 1
                            continue
                        metrics = pair_metrics(left, right)
                        distance_bonus = (
                            args.nearby_distance_bonus
                            if distance <= args.nearby_distance
                            else 0.0
                        )
                        pair_score = (
                            (left["relevance"] + right["relevance"]) / 2
                            + 0.20 * metrics["combined_context_overlap"]
                            + 0.20 * metrics["complementarity_gain"]
                            + distance_bonus
                        )
                        if pair_score > best_score:
                            best_pair, best_score = [left, right], pair_score
                question_id = str(question["question_id"])
                if (
                    best_pair is not None
                    and question_id not in selected_ids
                    and question_id not in excluded_ids
                    and question_id not in cumulative_ids
                ):
                    append_row_atomic(
                        output,
                        make_row(question, best_pair, blocks_by_id, manifest),
                    )
                    metrics = pair_metrics(best_pair[0], best_pair[1])
                    append_diagnostic(diagnostics, {
                        "question_id": question_id,
                        "left_block_id": best_pair[0]["block"]["block_id"],
                        "right_block_id": best_pair[1]["block"]["block_id"],
                        "left_answer_match": best_pair[0]["answer_match"],
                        "right_answer_match": best_pair[1]["answer_match"],
                        "left_context_overlap": f"{best_pair[0]['context_overlap']:.4f}",
                        "right_context_overlap": f"{best_pair[1]['context_overlap']:.4f}",
                        "left_support_overlap": f"{best_pair[0]['support_overlap']:.4f}",
                        "right_support_overlap": f"{best_pair[1]['support_overlap']:.4f}",
                        "combined_context_overlap": f"{metrics['combined_context_overlap']:.4f}",
                        "complementarity_gain": f"{metrics['complementarity_gain']:.4f}",
                        "left_unique_context_count": metrics["left_unique_context_count"],
                        "right_unique_context_count": metrics["right_unique_context_count"],
                        "left_unique_support_count": metrics["left_unique_support_count"],
                        "right_unique_support_count": metrics["right_unique_support_count"],
                        "pair_distance": pair_distance(best_pair[0], best_pair[1]),
                        "pair_score": f"{best_score:.4f}",
                    })
                    selected_ids.add(question_id)
                    cumulative_ids.add(question_id)

        index += 1
        processed_this_run += 1
        state["stats"]["processed"] = processed_this_run
        state["next_question_index"] = index
        state["selected_ids"] = sorted(selected_ids)
        save_state(args.checkpoint, state)

    save_state(args.checkpoint, state)
    print(f"multi_candidates={len(selected_ids)}/{args.target_per_batch}")
    print(f"processed_this_run={processed_this_run}")
    print(f"next_question_index={state['next_question_index']}")
    print(f"batch_number={batch_number}")
    print(f"output={output}")
    print(f"diagnostics={diagnostics}")
    print(f"checkpoint={args.checkpoint}")
    return state


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--checkpoint", type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--blocks", type=Path, default=DEFAULT_BLOCKS)
    parser.add_argument("--exclude-question-ids", type=Path)
    parser.add_argument("--target-per-batch", type=int, default=20)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--min-relevance", type=float, default=0.22)
    parser.add_argument("--min-score", type=float, default=0.20)
    parser.add_argument("--min-context-overlap", type=float, default=0.20)
    parser.add_argument("--min-non-answer-support-overlap", type=float, default=0.18)
    parser.add_argument("--min-pair-context-overlap", type=float, default=0.45)
    parser.add_argument("--min-unique-context-tokens", type=int, default=2)
    parser.add_argument("--min-unique-support-tokens", type=int, default=1)
    parser.add_argument("--min-context-concepts", type=int, default=2)
    parser.add_argument("--min-support-concepts", type=int, default=1)
    parser.add_argument("--min-complementarity-gain", type=float, default=0.15)
    parser.add_argument("--nearby-distance", type=int, default=2500)
    parser.add_argument("--nearby-distance-bonus", type=float, default=0.05)
    parser.add_argument("--max-questions", type=int)
    parser.add_argument("--diagnostics", type=Path)
    parser.add_argument("--reset", action="store_true", help="start a fresh scan")
    args = parser.parse_args()
    if args.top_k < 2:
        parser.error("--top-k must be at least 2")
    run(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
