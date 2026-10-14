"""Label corpus chunks against a frozen Topic Registry using local Ollama.

The labels remain development artifacts until M1 review and M3 spot-checking.
Use --limit for a deterministic, textbook-balanced pilot. Omit it to resume or
run the full corpus. Progress is appended to a JSONL checkpoint after each
chunk, so an interrupted run can be resumed with the same arguments.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from cs30.v2.contracts.models import TopicRegistry  # noqa: E402
from cs30.v2.corpus.manifest import CorpusManifest  # noqa: E402
from cs30.v2.topics import (  # noqa: E402
    ChunkTopicAssignment,
    ChunkTopicMap,
    validate_chunk_topic_map,
    write_chunk_topic_map,
)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def append_jsonl(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, separators=(",", ":")))
        handle.write("\n")
        handle.flush()


def section_topics(packet: dict[str, Any]) -> dict[str, set[str]]:
    result: dict[str, set[str]] = defaultdict(set)

    def collect_section_keys(value: Any, topic_id: str) -> None:
        if isinstance(value, dict):
            section_key = value.get("section_key")
            if isinstance(section_key, str) and section_key:
                result[section_key].add(topic_id)
            for child in value.values():
                collect_section_keys(child, topic_id)
        elif isinstance(value, list):
            for child in value:
                collect_section_keys(child, topic_id)

    for topic in packet.get("topics", []):
        topic_id = topic["topic_id"]
        collect_section_keys(topic, topic_id)
    return result


def block_sections(proposals_path: Path) -> dict[str, set[str]]:
    result: dict[str, set[str]] = defaultdict(set)
    with proposals_path.open(encoding="utf-8") as handle:
        for line in handle:
            proposal = json.loads(line)
            key = proposal.get("key")
            for block_id in proposal.get("source", {}).get("block_ids", []):
                result[block_id].add(key)
    return result


def load_chunks(records_path: Path) -> list[dict[str, Any]]:
    with records_path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle]


def choose_pilot(chunks: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    by_textbook: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for chunk in chunks:
        by_textbook[chunk["textbook_id"]].append(chunk)
    for rows in by_textbook.values():
        rows.sort(key=lambda row: hashlib.sha256(row["chunk_id"].encode()).digest())
    selected: list[dict[str, Any]] = []
    textbook_ids = sorted(by_textbook)
    while len(selected) < limit:
        added = False
        for textbook_id in textbook_ids:
            if by_textbook[textbook_id]:
                selected.append(by_textbook[textbook_id].pop(0))
                added = True
                if len(selected) == limit:
                    break
        if not added:
            break
    return selected


def exact_quote_excerpt(quote: str, chunk_text: str) -> str | None:
    """Return an exact source substring, allowing whitespace-only formatting changes."""

    if not quote:
        return None
    if quote in chunk_text:
        return quote
    quote_words = quote.split()
    text_matches = list(re.finditer(r"\S+", chunk_text))
    text_words = [match.group(0) for match in text_matches]
    if not quote_words or len(quote_words) > len(text_words):
        return None
    width = len(quote_words)
    for word_start in range(len(text_words) - width + 1):
        if text_words[word_start : word_start + width] == quote_words:
            word_end = word_start + width - 1
            return chunk_text[
                text_matches[word_start].start() : text_matches[word_end].end()
            ]
    return None


def model_labels(
    *,
    model: str,
    candidates: list[dict[str, str]],
    chunk: dict[str, Any],
    timeout_seconds: int,
) -> tuple[dict[str, Any], str, float]:
    candidate_text = json.dumps(candidates, ensure_ascii=False, separators=(",", ":"))
    prompt = (
        "/no_think\n"
        "Decide which candidate concepts this chunk actually teaches or explains. "
        "A passing mention, heading, or incidental example alone is not enough. "
        "Do not assign a topic to activity-only instructions, interactive tasks, "
        "or activity resources when the chunk contains no explanatory teaching content. "
        "Use only candidate topic_ids. For every selected topic, give one exact "
        "verbatim quote from the chunk (maximum 180 characters) and confidence "
        "high, medium, or low. Return an empty labels array when no candidate is "
        "taught. Return JSON only: {\"labels\":[{\"topic_id\":\"...\","
        "\"quote\":\"...\",\"confidence\":\"high|medium|low\"}]}\n"
        f"Candidates: {candidate_text}\nChunk text:\n{chunk['text']}"
    )
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "think": False,
        "keep_alive": "30m",
        "options": {"temperature": 0, "num_predict": 700, "num_ctx": 8192},
    }
    request = urllib.request.Request(
        "http://localhost:11434/api/generate",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    start = time.monotonic()
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        body = json.loads(response.read())
    elapsed = time.monotonic() - start
    raw = body.get("response", "")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Ollama returned invalid JSON: {exc}") from exc
    if not isinstance(parsed, dict) or not isinstance(parsed.get("labels"), list):
        raise ValueError("Ollama response must contain a labels array")
    return parsed, raw, elapsed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--corpus-dir",
        type=Path,
        default=REPOSITORY_ROOT
        / "artifacts/v2/textbooks/2.0.0-dev.m4-structure-v2-main-3553825",
    )
    parser.add_argument(
        "--registry",
        type=Path,
        default=REPOSITORY_ROOT / "artifacts/v2/topics/topic_registry_v0.2.json",
    )
    parser.add_argument(
        "--review-packet",
        type=Path,
        default=REPOSITORY_ROOT
        / "artifacts/v2/topics/topic_registry_review_packet_v0.2.json",
    )
    parser.add_argument(
        "--proposals",
        type=Path,
        default=REPOSITORY_ROOT
        / "artifacts/v2/topics/topic_section_proposals.jsonl",
    )
    parser.add_argument("--model", default="qwen3:8b")
    parser.add_argument("--limit", type=int, help="deterministic balanced pilot size")
    parser.add_argument("--timeout-seconds", type=int, default=240)
    parser.add_argument("--progress-every", type=int, default=5)
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        raise SystemExit("--limit must be positive")

    artifact_dir = args.registry.parent
    suffix = "pilot" if args.limit is not None else "full"
    stem = f"chunk_topic_labels_{suffix}_topics-0.2"
    labels_path = artifact_dir / f"{stem}.jsonl"
    review_path = artifact_dir / f"chunk_topic_label_review_queue_{suffix}_topics-0.2.json"
    map_path = artifact_dir / f"chunk_topic_map_{suffix}_topics-0.2.json"
    run_path = artifact_dir / f"chunk_topic_label_run_{suffix}_topics-0.2.json"

    registry = TopicRegistry.model_validate_json(args.registry.read_text(encoding="utf-8"))
    packet = read_json(args.review_packet)
    if packet.get("topic_registry_version") != registry.topic_registry_version:
        raise SystemExit("review packet and frozen registry versions do not match")
    topic_by_id = {topic.topic_id: topic for topic in registry.topics}
    packet_topic_ids = {row["topic_id"] for row in packet.get("topics", [])}
    if packet_topic_ids != set(topic_by_id):
        raise SystemExit("review packet Topic IDs differ from frozen registry")

    manifest = CorpusManifest.model_validate_json(
        (args.corpus_dir / "manifest.json").read_text(encoding="utf-8")
    )
    chunks = load_chunks(args.corpus_dir / manifest.records_relpath)
    chunk_ids = [chunk["chunk_id"] for chunk in chunks]
    if len(chunk_ids) != manifest.record_count:
        raise SystemExit("records.jsonl count does not match the corpus manifest")

    topics_by_section = section_topics(packet)
    sections_by_block = block_sections(args.proposals)
    candidates_by_chunk: dict[str, list[str]] = {}
    section_by_chunk: dict[str, str | None] = {}
    for chunk in chunks:
        block_ids = {span["block_id"] for span in chunk.get("spans", [])}
        section_keys = {
            section_key
            for block_id in block_ids
            for section_key in sections_by_block.get(block_id, set())
        }
        candidate_ids = sorted(
            {
                topic_id
                for section_key in section_keys
                for topic_id in topics_by_section.get(section_key, set())
            }
        )
        if not set(candidate_ids).issubset(topic_by_id):
            raise SystemExit(f"candidate Topics absent from registry: {chunk['chunk_id']}")
        candidates_by_chunk[chunk["chunk_id"]] = candidate_ids
        section_by_chunk[chunk["chunk_id"]] = (
            sorted(section_keys)[0] if len(section_keys) == 1 else None
        )

    selected = choose_pilot(chunks, args.limit) if args.limit is not None else chunks
    selected_ids = {chunk["chunk_id"] for chunk in selected}
    done: dict[str, dict[str, Any]] = {}
    if labels_path.exists():
        with labels_path.open(encoding="utf-8") as handle:
            for line in handle:
                record = json.loads(line)
                done[record["chunk_id"]] = record

    records_by_id = {chunk["chunk_id"]: chunk for chunk in chunks}
    cache: dict[str, dict[str, Any]] = {}
    for record in done.values():
        if record.get("cache_key") and record.get("model_result") is not None:
            cache.setdefault(record["cache_key"], record["model_result"])

    labelable_topic_ids: set[str] = set()
    review_records: list[dict[str, Any]] = []
    attempts = 0
    newly_done = 0
    for chunk in selected:
        chunk_id = chunk["chunk_id"]
        if chunk_id in done:
            continue
        candidate_ids = candidates_by_chunk[chunk_id]
        source_block_ids = sorted({span["block_id"] for span in chunk.get("spans", [])})
        text_hash = sha256_text(chunk["text"])
        base_record: dict[str, Any] = {
            "schema_version": "topic-chunk-label-v1",
            "chunk_id": chunk_id,
            "corpus_version": manifest.corpus_version,
            "corpus_hash": manifest.corpus_hash,
            "topic_registry_version": registry.topic_registry_version,
            "section_key": section_by_chunk[chunk_id],
            "source_block_ids": source_block_ids,
            "text_sha256": text_hash,
            "candidate_topic_ids": candidate_ids,
            "model": args.model,
        }
        if not candidate_ids:
            record = {
                **base_record,
                "status": "no_candidate_topics",
                "labels": [],
                "model_result": None,
            }
            append_jsonl(labels_path, record)
            done[chunk_id] = record
            newly_done += 1
            continue

        cache_key = sha256_text(
            json.dumps(
                [candidate_ids, chunk["text"]], ensure_ascii=False, separators=(",", ":")
            )
        )
        cached = cache.get(cache_key)
        raw_response = None
        if cached is None:
            candidates = [
                {
                    "topic_id": topic_id,
                    "title": topic_by_id[topic_id].title,
                    "description": (topic_by_id[topic_id].description or "")[:280],
                }
                for topic_id in candidate_ids
            ]
            try:
                model_result, raw_response, elapsed = model_labels(
                    model=args.model,
                    candidates=candidates,
                    chunk=chunk,
                    timeout_seconds=args.timeout_seconds,
                )
                attempts += 1
                cached = model_result
                cache[cache_key] = model_result
                base_record["elapsed_seconds"] = round(elapsed, 3)
            except (urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
                record = {
                    **base_record,
                    "status": "model_error_review_required",
                    "error": f"{type(exc).__name__}: {exc}",
                    "labels": [],
                    "model_result": None,
                    "cache_key": cache_key,
                }
                append_jsonl(labels_path, record)
                done[chunk_id] = record
                review_records.append(record)
                newly_done += 1
                continue

        allowed = set(candidate_ids)
        verified_labels: list[dict[str, Any]] = []
        issues: list[str] = []
        for label in cached.get("labels", []):
            if not isinstance(label, dict):
                issues.append("malformed_label")
                continue
            topic_id = label.get("topic_id")
            quote = label.get("quote")
            confidence = label.get("confidence", "low")
            if topic_id not in allowed:
                issues.append("topic_id_outside_candidate_set")
                continue
            excerpt = (
                exact_quote_excerpt(quote, chunk["text"])
                if isinstance(quote, str)
                else None
            )
            verbatim = excerpt is not None
            normalized_confidence = (
                confidence if confidence in {"high", "medium", "low"} else "low"
            )
            verified_labels.append(
                {
                    "topic_id": topic_id,
                    "quote": excerpt if excerpt is not None else quote,
                    "confidence": normalized_confidence,
                    "quote_verified": verbatim,
                }
            )
            if not verbatim:
                issues.append("quote_not_verbatim")
            if normalized_confidence != "high":
                issues.append("confidence_below_high")

        status = "assistant_labeled"
        if issues:
            status = "review_required"
        if not verified_labels:
            status = "review_required"
            issues.append("no_topic_selected_with_candidate_topics")
            issues = sorted(set(issues))
        model_result = {"labels": verified_labels}
        record = {
            **base_record,
            "status": status,
            "labels": verified_labels,
            "review_reasons": sorted(set(issues)),
            "cache_key": cache_key,
            "model_result": model_result,
        }
        append_jsonl(labels_path, record)
        done[chunk_id] = record
        newly_done += 1
        if status == "review_required":
            review_records.append(record)

        if newly_done % args.progress_every == 0:
            print(
                f"processed {newly_done}; selected {len(selected)}; "
                f"model calls this run {attempts}; review flags {len(review_records)}",
                flush=True,
            )

    selected_records = [done[chunk_id] for chunk_id in selected_ids if chunk_id in done]
    # Re-validate checkpoint entries on every invocation. This lets a resumed
    # run tighten quote handling without paying for another model call.
    for record in selected_records:
        chunk_text = records_by_id[record["chunk_id"]]["text"]
        reasons = set(record.get("review_reasons", []))
        verified_labels = []
        for label in record.get("labels", []):
            quote = label.get("quote")
            excerpt = (
                exact_quote_excerpt(quote, chunk_text)
                if isinstance(quote, str)
                else None
            )
            verified = excerpt is not None
            normalized = {
                **label,
                "quote": excerpt if verified else quote,
                "quote_verified": verified,
            }
            verified_labels.append(normalized)
            if not verified:
                reasons.add("quote_not_verbatim")
            if normalized.get("confidence") != "high":
                reasons.add("confidence_below_high")
        if record.get("candidate_topic_ids") and not verified_labels:
            reasons.add("no_topic_selected_with_candidate_topics")
        if reasons:
            record["status"] = "review_required"
            record["review_reasons"] = sorted(reasons)
        elif record.get("status") not in {
            "no_candidate_topics",
            "model_error_review_required",
        }:
            record["status"] = "assistant_labeled"
            record.pop("review_reasons", None)
        record["labels"] = verified_labels

    if selected_records:
        ordered_done = [done[chunk["chunk_id"]] for chunk in chunks if chunk["chunk_id"] in done]
        labels_path.write_text(
            "".join(
                json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
                for record in ordered_done
            ),
            encoding="utf-8",
        )

    assignments = []
    for record in selected_records:
        topic_ids = sorted(
            {
                label["topic_id"]
                for label in record.get("labels", [])
                if label.get("quote_verified") and label.get("confidence") == "high"
            }
        )
        if topic_ids:
            assignments.append(
                ChunkTopicAssignment(chunk_id=record["chunk_id"], topic_ids=tuple(topic_ids))
            )
    topic_map = ChunkTopicMap(
        corpus_version=manifest.corpus_version,
        corpus_hash=manifest.corpus_hash,
        topic_registry_version=registry.topic_registry_version,
        assignments=tuple(assignments),
    )
    validate_chunk_topic_map(topic_map, manifest, chunk_ids)
    write_chunk_topic_map(topic_map, map_path)

    review = [
        record
        for record in selected_records
        if record.get("status") in {"review_required", "model_error_review_required"}
    ]
    review_path.write_text(
        json.dumps(
            {
                "schema_version": "topic-chunk-label-review-queue-v1",
                "status": "pending_m1_review_and_m3_spot_check",
                "topic_registry_version": registry.topic_registry_version,
                "corpus_version": manifest.corpus_version,
                "corpus_hash": manifest.corpus_hash,
                "review_count": len(review),
                "items": review,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    completed = len(selected_records) == len(selected)
    full_corpus = args.limit is None and len(selected) == len(chunks) and completed
    label_count = sum(len(record.get("labels", [])) for record in selected_records)
    run = {
        "schema_version": "topic-chunk-label-run-v1",
        "status": "pending_review" if full_corpus else "pilot_only_pending_full_labeling_and_review",
        "topic_registry_version": registry.topic_registry_version,
        "corpus_version": manifest.corpus_version,
        "corpus_hash": manifest.corpus_hash,
        "corpus_reportable": manifest.reportable,
        "model": args.model,
        "selected_chunk_count": len(selected),
        "completed_chunk_count": len(selected_records),
        "candidate_topic_chunk_count": sum(bool(candidates_by_chunk[row["chunk_id"]]) for row in selected_records),
        "no_candidate_chunk_count": sum(not candidates_by_chunk[row["chunk_id"]] for row in selected_records),
        "assignment_count": len(assignments),
        "label_count": label_count,
        "review_required_count": len(review),
        "model_calls_this_run": attempts,
        "chunk_label_file": labels_path.relative_to(REPOSITORY_ROOT).as_posix(),
        "review_queue_file": review_path.relative_to(REPOSITORY_ROOT).as_posix(),
        "chunk_topic_map_file": map_path.relative_to(REPOSITORY_ROOT).as_posix(),
        "map_is_full_corpus": full_corpus,
        "map_validation": "passed",
        "release_gate": "M1 label review and M3 spot-check required; corpus is development-only",
    }
    run_path.write_text(
        json.dumps(run, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"Done: {len(selected_records)}/{len(selected)} chunks, "
        f"{len(assignments)} map assignments, {len(review)} review flags. "
        f"Validated map: {map_path.relative_to(REPOSITORY_ROOT).as_posix()}"
    )


if __name__ == "__main__":
    main()
