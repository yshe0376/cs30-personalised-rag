"""Conservatively triage alternative Topic definitions with the local Ollama model.

This creates recommendations only. It never freezes the registry or marks M3 review
complete for items classified as uncertain.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PACKET = ROOT / "artifacts" / "v2" / "topics" / "topic_registry_review_packet_v0.json"
DEFAULT_OUTPUT = ROOT / "artifacts" / "v2" / "topics" / "topic_definition_reconciliation_v0.json"
MODEL = "qwen3:8b"
OLLAMA_URL = "http://127.0.0.1:11434/api/generate"

PROMPT = """You are doing a conservative pre-review of physics Topic definitions.
The input is a list of Topic objects. Each object is one Topic and its candidates array
contains alternative definitions for that same Topic. Compare all candidates collectively.
Return one integer for each Topic, in input order, in a JSON array. Each integer is the
zero-based index of the best accurate existing candidate. Use -1 only when a material
concept/scope conflict, a candidate that clearly defines another concept, or uncertainty
about which meaning is intended requires human review. Minor paraphrases, examples, or
differences in detail are compatible. If a
candidate is merely less complete or less polished, select the best accurate candidate. If
there is only one candidate, decide whether it clearly and accurately defines the Topic title.
Use only the supplied title and definitions; do not add outside facts. Do not rewrite a
candidate. Return exactly as many integers as there are input Topic objects. The output
array position already identifies the Topic; never return a Topic number or input-list
position as a candidate index. For a Topic with one candidate, return 0 if it fits or -1
if it needs review. Candidate positions are explicitly zero-based: the first candidate
is 0. Do not add explanations.

INPUT:
"""


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    temporary.replace(path)


def call_model(rows: list[dict[str, Any]], timeout: int) -> Any:
    payload = {
        "model": MODEL,
        "prompt": PROMPT + json.dumps(rows, ensure_ascii=False, separators=(",", ":")),
        "stream": False,
        "format": {
            "type": "array",
            "items": {"type": "integer"},
            "minItems": len(rows),
            "maxItems": len(rows),
        },
        "think": False,
        "options": {
            "temperature": 0,
            "num_ctx": 8192,
            "num_predict": 200,
        },
    }
    request = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = json.loads(response.read())
    return json.loads(body["response"])


def parse_batch(
    response: Any,
    batch: list[dict[str, Any]],
    topics_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    by_index: dict[int, list[list[Any]]] = {}
    normalized_input_indices: set[int] = set()
    if isinstance(response, list) and all(isinstance(item, int) for item in response):
        for input_index, candidate_index in enumerate(response):
            if (
                input_index < len(batch)
                and len(topics_by_id[batch[input_index]["topic_id"]]["definitions"]) == 1
                and candidate_index == 1
            ):
                candidate_index = 0
                normalized_input_indices.add(input_index)
            action = "A" if candidate_index >= 0 else "R"
            by_index[input_index] = [[input_index, action, candidate_index]]
    for item in response.get("decisions", []) if isinstance(response, dict) else []:
        if isinstance(item, dict) and isinstance(item.get("i"), int):
            input_index = item["i"]
            row = [input_index, item.get("action"), item.get("candidate_index")]
            by_index.setdefault(input_index, []).append(row)
        elif isinstance(item, str):
            fields = item.split("|", 4)
            try:
                input_index = int(fields[0])
            except (ValueError, IndexError):
                continue
            if len(fields) >= 3 and fields[1].upper() == "A":
                row: list[Any] = [input_index, "A", int(fields[2]), 3, "same_meaning", ""]
            elif len(fields) >= 4 and fields[1].upper() == "R":
                row = [input_index, "R", -1, 1, fields[2], fields[3]]
            else:
                row = [input_index]
            by_index.setdefault(input_index, []).append(row)
        elif isinstance(item, list) and item and isinstance(item[0], int):
            by_index.setdefault(item[0], []).append(item)

    decisions: list[dict[str, Any]] = []
    for index, source in enumerate(batch):
        topic_id = source["topic_id"]
        topic = topics_by_id[topic_id]
        indexed_rows = by_index.get(index, [])
        raw = indexed_rows[0] if len(indexed_rows) == 1 else None
        action = "needs_user_review"
        selected_index: int | None = None
        confidence = "low"
        reason_code = "uncertain"
        review_note = "The local review model did not return a usable decision."
        if raw is not None and len(raw) >= 3:
            raw_action = str(raw[1]).upper()
            if raw_action == "A":
                raw_selected = raw[2]
                if (
                    isinstance(raw_selected, int)
                    and 0 <= raw_selected < len(topic["definitions"])
                ):
                    action = "assistant_auto_resolve_candidate"
                    selected_index = raw_selected
                    confidence = "high"
                    reason_code = "same_meaning"
                    review_note = ""
                else:
                    reason_code = "uncertain"
                    review_note = "The model selected an invalid definition candidate."
            else:
                if len(raw) == 3 and raw[2] == -1:
                    reason_code = "uncertain"
                    review_note = (
                        "The local review model marked this candidate set for human "
                        "review."
                    )
                elif isinstance(raw[2], int) and len(raw) > 3:
                    reason_code = str(raw[3])
                    review_note = (
                        str(raw[4])
                        if len(raw) > 4
                        else "The model marked this candidate set for review."
                    )
                else:
                    reason_code = str(raw[2]) if len(raw) > 2 else "uncertain"
                    review_note = (
                        str(raw[3])
                        if len(raw) > 3
                        else "The model marked this candidate set for review."
                    )
                reason_code = reason_code if reason_code in {
                    "scope", "conflict", "off_topic", "incomplete", "uncertain"
                } else "uncertain"

        selected_definition = (
            topic["definitions"][selected_index]["definition"]
            if selected_index is not None
            else None
        )
        decisions.append(
            {
                "topic_id": topic_id,
                "title": topic["title"],
                "decision_type": action,
                "confidence": confidence,
                "reason_code": reason_code,
                "selected_candidate_index": selected_index,
                "selected_definition": selected_definition,
                "review_note": review_note,
                "candidate_count": len(topic["definitions"]),
                "decision_protocol": "compact_integer_array_v4",
                "candidate_index_normalized_from_one_based": index in normalized_input_indices,
            }
        )
    return decisions


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet", type=Path, default=DEFAULT_PACKET)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Process at most this many unreviewed Topics.",
    )
    parser.add_argument(
        "--include-single",
        action="store_true",
        help="Also review Topics with only one definition candidate for title fit and correctness.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    packet = read_json(args.packet)
    topic_rows = packet.get("topics", [])
    topics_by_id = {str(row["topic_id"]): row for row in topic_rows}
    packet_hash = hashlib.sha256(args.packet.read_bytes()).hexdigest()

    if args.output.exists():
        result = read_json(args.output)
        if result.get("source_packet_sha256") != packet_hash:
            raise ValueError("existing reconciliation file belongs to a different review packet")
    else:
        result = {
            "schema_version": "topic-definition-reconciliation-v0",
            "status": "in_progress",
            "source_packet": str(args.packet.relative_to(ROOT)),
            "source_packet_sha256": packet_hash,
            "model": MODEL,
            "review_method": "local_offline_conservative_candidate_equivalence_triage",
            "generated_date": date.today().isoformat(),
            "decisions": [],
        }

    completed = {row["topic_id"] for row in result["decisions"]}
    target_rows = [
        row for row in topic_rows
        if row.get("definition_review_status") != "user_confirmed"
        and (args.include_single or len(row.get("definitions", [])) > 1)
    ]
    total_target = len(target_rows)
    eligible = [row for row in target_rows if row["topic_id"] not in completed]
    if args.limit:
        eligible = eligible[: args.limit]

    batches = [eligible[i : i + args.batch_size] for i in range(0, len(eligible), args.batch_size)]
    for batch_number, batch in enumerate(batches, start=1):
        compact_rows = [
            {
                "title": row["title"],
                "candidates": [definition["definition"] for definition in row["definitions"]],
            }
            for row in batch
        ]
        response: dict[str, Any] = {}
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                response = call_model(compact_rows, args.timeout)
                last_error = None
                break
            except (urllib.error.URLError, TimeoutError, ValueError, KeyError) as error:
                last_error = error
                if attempt < 2:
                    time.sleep(2 + attempt * 3)
        if last_error is not None:
            print(f"Batch {batch_number}/{len(batches)} failed: {last_error}", flush=True)
            response = {}

        parsed_batch = parse_batch(response, batch, topics_by_id)
        for _retry in range(1):
            if not any(
                row["review_note"] in {
                    "The local review model did not return a usable decision.",
                    "The model selected an invalid definition candidate.",
                }
                for row in parsed_batch
            ):
                break
            try:
                response = call_model(compact_rows, args.timeout)
                parsed_batch = parse_batch(response, batch, topics_by_id)
            except (urllib.error.URLError, TimeoutError, ValueError, KeyError):
                break
        result["decisions"].extend(parsed_batch)
        result["summary"] = {
            "topics_processed": len(result["decisions"]),
            "topics_auto_resolved_high_confidence": sum(
                row["decision_type"] == "assistant_auto_resolve_candidate"
                for row in result["decisions"]
            ),
            "topics_needing_user_review": sum(
                row["decision_type"] == "needs_user_review"
                for row in result["decisions"]
            ),
            "topics_remaining": total_target - len(result["decisions"]),
        }
        write_json(args.output, result)
        print(
            f"Batch {batch_number}/{len(batches)} saved; "
            f"{result['summary']['topics_processed']} processed, "
            f"{result['summary']['topics_auto_resolved_high_confidence']} auto-resolved, "
            f"{result['summary']['topics_needing_user_review']} need review.",
            flush=True,
        )

    result["status"] = "complete" if len(result["decisions"]) == total_target else "in_progress"
    result["summary"]["topics_remaining"] = total_target - len(result["decisions"])
    result["summary"]["review_scope"] = (
        "all_non_user_confirmed_topics" if args.include_single else "multi_candidate_topics"
    )
    write_json(args.output, result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
