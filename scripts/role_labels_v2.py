"""Label v2 corpus chunks with Evidence Roles: human pilot, LLM batch, package.

Run the subcommands in this order. Outputs go to artifacts/v2/role_labels/.

  sample     draw a deterministic random pilot sample of chunks
  annotate   label chunks by hand in the terminal; every answer is saved at once
  llm-label  label chunks with a local Ollama model; resumable checkpoint
  compare    agreement between two label files (Cohen's kappa, per-role P/R/F1)
  candidates list chunks that might be derivation or boundary, for a stronger reviewer
  export     write the Role-label package that Member 7's reranker loads

Role definitions live in m3_role_labels/v2/role_taxonomy_v2.json. The
terminal help and the LLM prompt both read that file, and every label records
its hash, so a definition change shows up in the outputs.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import sys
import textwrap
import time
import urllib.error
import urllib.request
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CORPUS_DIR = (
    REPOSITORY_ROOT / "artifacts/v2/textbooks/2.0.0-dev.m4-structure-v2-main-3553825"
)
DEFAULT_TAXONOMY = REPOSITORY_ROOT / "m3_role_labels/v2/role_taxonomy_v2.json"
DEFAULT_OUT_DIR = REPOSITORY_ROOT / "artifacts/v2/role_labels"
DEFAULT_SAMPLE = DEFAULT_OUT_DIR / "pilot_sample.json"

# Member 7's EvidenceRole values (src/cs30/generation/reranking.py). The taxonomy
# file may reword the definitions but must keep exactly these names and order.
ROLES = ("definition", "example", "comparison", "application", "derivation", "boundary")
CONFIDENCES = ("high", "medium", "low")
SAMPLE_SCHEMA = "role-pilot-sample-v1"
HUMAN_SCHEMA = "role-annotation-v1"
LLM_SCHEMA = "role-llm-label-v1"
PACKAGE_SCHEMA = "role-labels-v2"
PROMPT_VERSION = "role-prompt-v2"
LLM_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "evidence_quote": {"type": "string"},
        "role": {"type": "string", "enum": list(ROLES)},
        "confidence": {"type": "string", "enum": list(CONFIDENCES)},
    },
    "required": ["evidence_quote", "role", "confidence"],
}


# ---------------------------------------------------------------------------
# Files


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise SystemExit(f"{path}:{line_number}: invalid JSON: {exc}") from exc
    return rows


def append_jsonl(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n")
        handle.flush()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def slug(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-").lower()
    if not cleaned:
        raise SystemExit(f"cannot build a file name from {value!r}")
    return cleaned


def utc_now() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat()


# ---------------------------------------------------------------------------
# Corpus, taxonomy and label files


@dataclass(frozen=True)
class Corpus:
    corpus_version: str
    corpus_hash: str
    chunks: dict[str, dict[str, Any]]


def load_corpus(corpus_dir: Path) -> Corpus:
    manifest_path = corpus_dir / "manifest.json"
    if not manifest_path.is_file():
        raise SystemExit(
            f"No corpus at {corpus_dir}. Install it first:\n"
            "  gh release download v2-m4-structure-v2-dev-v1 --pattern \"*.zip\" "
            f"--dir {corpus_dir}\n  then unzip it in that folder."
        )
    manifest = read_json(manifest_path)
    records_path = corpus_dir / manifest["records_relpath"]
    if "sha256:" + sha256_file(records_path) != manifest["corpus_hash"]:
        raise SystemExit(f"{records_path} does not match corpus_hash in manifest.json")
    chunks: dict[str, dict[str, Any]] = {}
    for record in read_jsonl(records_path):
        chunks[record["chunk_id"]] = record
    if len(chunks) != manifest["record_count"]:
        raise SystemExit("records.jsonl count does not match the corpus manifest")
    return Corpus(manifest["corpus_version"], manifest["corpus_hash"], chunks)


@dataclass(frozen=True)
class Taxonomy:
    version: str
    status: str
    sha256: str
    instructions: str
    rules: tuple[str, ...]
    roles: tuple[dict[str, Any], ...]


def load_taxonomy(path: Path) -> Taxonomy:
    payload = read_json(path)
    names = tuple(role.get("role") for role in payload.get("roles", []))
    if names != ROLES:
        raise SystemExit(f"{path}: roles must be exactly {', '.join(ROLES)}, in that order")
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return Taxonomy(
        version=payload["taxonomy_version"],
        status=payload.get("status", "draft"),
        sha256=sha256_text(canonical),
        instructions=payload["instructions"],
        rules=tuple(payload.get("rules", ())),
        roles=tuple(payload["roles"]),
    )


def latest_labels(path: Path | None) -> dict[str, dict[str, Any]]:
    """Return the last row per chunk_id; a later answer replaces an earlier one."""

    if path is None or not path.exists():
        return {}
    labels: dict[str, dict[str, Any]] = {}
    for row in read_jsonl(path):
        labels[row["chunk_id"]] = row
    return labels


def usable(labels: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {chunk_id: row for chunk_id, row in labels.items() if row.get("role") in ROLES}


def resolve_scope(scope: str, corpus: Corpus) -> list[str]:
    """Return chunk IDs for 'all', a sample JSON, or a text file with one ID per line."""

    if scope == "all":
        return list(corpus.chunks)
    path = Path(scope)
    if not path.is_file():
        raise SystemExit(f"Scope file not found: {path}")
    if path.suffix == ".json":
        ids = read_json(path)["chunk_ids"]
    else:
        ids = [
            line.strip()
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
    ids = list(dict.fromkeys(ids))
    unknown = [chunk_id for chunk_id in ids if chunk_id not in corpus.chunks]
    if unknown:
        raise SystemExit(
            f"{len(unknown)} chunk IDs in {path} are not in this corpus, e.g. {unknown[0]}"
        )
    return ids


def choose_sample(chunk_ids: Iterable[str], size: int, seed: str) -> list[str]:
    """A seeded simple random sample: order by SHA-256 of seed and chunk ID."""

    ranked = sorted(
        chunk_ids, key=lambda chunk_id: sha256_text(f"{seed}\n{chunk_id}")
    )
    return ranked[:size]


# ---------------------------------------------------------------------------
# sample


def cmd_sample(args: argparse.Namespace) -> None:
    corpus = load_corpus(args.corpus_dir)
    if not 1 <= args.size <= len(corpus.chunks):
        raise SystemExit(f"--size must be between 1 and {len(corpus.chunks)}")
    if args.output.exists() and not args.force:
        raise SystemExit(
            f"{args.output} already exists. Annotations refer to it; "
            "pass --force only if you mean to start a new sample."
        )
    ids = choose_sample(corpus.chunks, args.size, args.seed)
    write_json(
        args.output,
        {
            "schema_version": SAMPLE_SCHEMA,
            "corpus_version": corpus.corpus_version,
            "corpus_hash": corpus.corpus_hash,
            "seed": args.seed,
            "size": len(ids),
            "method": "first N chunk IDs ordered by sha256(seed + newline + chunk_id)",
            "chunk_ids": ids,
        },
    )
    books = Counter(corpus.chunks[chunk_id]["textbook_id"] for chunk_id in ids)
    print(f"Wrote {len(ids)} chunk IDs to {args.output}")
    for book, count in books.most_common():
        print(f"  {book}: {count}")


# ---------------------------------------------------------------------------
# annotate


@dataclass(frozen=True)
class Answer:
    action: str  # label, back, skip, help, quit or invalid
    role: str | None = None
    unsure: bool = False
    note: str = ""
    message: str = ""


def parse_answer(text: str) -> Answer:
    """Parse '4', '4?', 'app', '4? mostly a device' and the navigation keys."""

    text = text.strip()
    lowered = text.lower()
    if lowered in {"q", "quit", "exit"}:
        return Answer("quit")
    if lowered in {"b", "back"}:
        return Answer("back")
    if lowered in {"s", "skip"}:
        return Answer("skip")
    if lowered in {"h", "help", "?"}:
        return Answer("help")
    head, _, note = text.partition(" ")
    unsure = head.endswith("?")
    head = head.rstrip("?").lower()
    role = None
    if head.isdigit() and 1 <= int(head) <= len(ROLES):
        role = ROLES[int(head) - 1]
    elif head:
        matches = [name for name in ROLES if name.startswith(head)]
        if len(matches) == 1:
            role = matches[0]
    if role is None:
        return Answer("invalid", message=f"Not understood: {text!r}. Type 1-6, or h for help.")
    return Answer("label", role=role, unsure=unsure, note=note.strip())


def print_definitions(taxonomy: Taxonomy) -> None:
    width = terminal_width()
    print(f"\nTaxonomy {taxonomy.version} ({taxonomy.status})\n")
    print(textwrap.fill(taxonomy.instructions, width))
    for rule in taxonomy.rules:
        print(textwrap.fill(rule, width, initial_indent="* ", subsequent_indent="  "))
    for number, role in enumerate(taxonomy.roles, 1):
        print(f"\n{number} {role['role']}  [{role['level']}]  {role.get('zh', '')}")
        print(textwrap.fill(role["definition"], width, initial_indent="  ",
                            subsequent_indent="  "))
        for cue in role["cues"]:
            print(textwrap.fill(cue, width, initial_indent="  + ", subsequent_indent="    "))
        print(textwrap.fill(role["not"], width, initial_indent="  - ", subsequent_indent="    "))
    print()


def terminal_width() -> int:
    return max(60, min(shutil.get_terminal_size((100, 30)).columns - 2, 110))


def render_chunk(
    chunk: dict[str, Any],
    *,
    position: int,
    total: int,
    remaining: int,
    current: dict[str, Any] | None,
    hint: dict[str, Any] | None,
    clear: bool,
) -> None:
    width = terminal_width()
    if clear:
        print("\033[2J\033[H", end="")
    rule = "-" * width
    print(f"[{position}/{total}]  {remaining} unlabelled  {chunk['chunk_id']}")
    section = f"{chunk.get('section_id', '')} {chunk.get('section_title', '')}".strip()
    print(
        f"{chunk['textbook_id']} | {section} | {chunk.get('page_or_location', '')} | "
        f"{', '.join(chunk.get('content_types', []))}"
    )
    print(rule)
    for paragraph in chunk["text"].split("\n"):
        print(textwrap.fill(paragraph, width) if paragraph.strip() else "")
    print(rule)
    if current:
        mark = "?" if current.get("unsure") else ""
        note = f"  ({current['note']})" if current.get("note") else ""
        print(f"Your label: {current['role']}{mark}{note}")
    if hint:
        print(f"LLM suggests: {hint['role']} ({hint.get('confidence', '?')})")
    print("  ".join(f"{number} {name}" for number, name in enumerate(ROLES, 1)))
    print("Add ? if unsure, then an optional note: '4? mostly a device'.  "
          "b back  s skip  h definitions  q quit")


def cmd_annotate(args: argparse.Namespace) -> None:
    corpus = load_corpus(args.corpus_dir)
    taxonomy = load_taxonomy(args.taxonomy)
    ids = resolve_scope(args.scope, corpus)
    if args.first is not None:
        ids = ids[: args.first]
    if not ids:
        raise SystemExit("The scope has no chunks to label.")
    labels_path = args.out_dir / f"human_labels_{slug(args.annotator)}.jsonl"
    labels = usable(latest_labels(labels_path))
    hints = usable(latest_labels(args.show_llm))
    if args.start is not None:
        position = min(max(args.start - 1, 0), len(ids) - 1)
    else:
        position = next((i for i, chunk_id in enumerate(ids) if chunk_id not in labels), None)
        if position is None:
            print(f"All {len(ids)} chunks are labelled in {labels_path}. "
                  "Pass --start 1 to review them.")
            return
    if args.clear and os.name == "nt":
        os.system("")  # turns on ANSI escape handling in older Windows consoles

    print(f"Saving to {labels_path}")
    while 0 <= position < len(ids):
        chunk_id = ids[position]
        chunk = corpus.chunks[chunk_id]
        render_chunk(
            chunk,
            position=position + 1,
            total=len(ids),
            remaining=sum(other not in labels for other in ids),
            current=labels.get(chunk_id),
            hint=hints.get(chunk_id),
            clear=args.clear,
        )
        try:
            answer = parse_answer(input("> "))
        except (EOFError, KeyboardInterrupt):
            answer = Answer("quit")
        if answer.action == "quit":
            break
        if answer.action == "help":
            print_definitions(taxonomy)
            try:
                input("Press Enter to go back to the chunk.")
            except (EOFError, KeyboardInterrupt):
                break
            continue
        if answer.action == "invalid":
            print(answer.message)
            time.sleep(1.2)
            continue
        if answer.action == "back":
            position = max(position - 1, 0)
            continue
        if answer.action == "skip":
            position += 1
            continue
        record = {
            "schema_version": HUMAN_SCHEMA,
            "chunk_id": chunk_id,
            "role": answer.role,
            "unsure": answer.unsure,
            "note": answer.note,
            "annotator": args.annotator,
            "taxonomy_version": taxonomy.version,
            "taxonomy_sha256": taxonomy.sha256,
            "corpus_version": corpus.corpus_version,
            "text_sha256": sha256_text(chunk["text"]),
            "labeled_at": utc_now(),
        }
        append_jsonl(labels_path, record)
        labels[chunk_id] = record
        position += 1

    done = [labels[chunk_id] for chunk_id in ids if chunk_id in labels]
    print(f"\nLabelled {len(done)}/{len(ids)}; saved in {labels_path}")
    if done:
        counts = Counter(row["role"] for row in done)
        print("  " + "  ".join(f"{role} {counts[role]}" for role in ROLES))
        print(f"  unsure {sum(bool(row.get('unsure')) for row in done)}")
    if len(done) < len(ids):
        print("Run the same command again to continue from the first unlabelled chunk.")


# ---------------------------------------------------------------------------
# llm-label


def build_prompt(taxonomy: Taxonomy, chunk: dict[str, Any]) -> str:
    role_lines = [
        f"- {role['role']}: {role['definition']} Cues: {'; '.join(role['cues'])}. "
        f"Not this role: {role['not']}"
        for role in taxonomy.roles
    ]
    section = f"{chunk.get('section_id', '')} {chunk.get('section_title', '')}".strip()
    rules = "".join(f"- {rule}\n" for rule in taxonomy.rules)
    rule_block = f"Decision rules:\n{rules}\n" if rules else ""
    return (
        "/no_think\n"
        "You label passages from introductory physics textbooks with one pedagogical "
        "evidence role.\n"
        f"{taxonomy.instructions}\n\n"
        "Roles:\n" + "\n".join(role_lines) + "\n\n"
        f"{rule_block}"
        "First copy one short exact quote (at most 160 characters) from the chunk that "
        "best shows its role. Then give the role and your confidence: high, medium or "
        "low. Return JSON only.\n\n"
        f"Section: {section}\n"
        f"Content types: {', '.join(chunk.get('content_types', []))}\n"
        f"Chunk text:\n{chunk['text']}"
    )


def quote_in_text(quote: str, text: str) -> bool:
    normalized = " ".join(quote.split())
    return bool(normalized) and normalized in " ".join(text.split())


def check_ollama(base_url: str, model: str) -> None:
    try:
        with urllib.request.urlopen(f"{base_url}/api/tags", timeout=10) as response:
            names = {item["name"] for item in json.loads(response.read())["models"]}
    except (urllib.error.URLError, TimeoutError) as exc:
        raise SystemExit(
            f"Cannot reach Ollama at {base_url} ({exc}). Start the Ollama app, then retry."
        ) from exc
    if model not in names and f"{model}:latest" not in names:
        raise SystemExit(
            f"Ollama has no model {model!r}. Installed: {', '.join(sorted(names)) or 'none'}. "
            f"Run: ollama pull {model}"
        )


def call_ollama(
    *, base_url: str, model: str, prompt: str, timeout_seconds: int, num_ctx: int
) -> tuple[dict[str, Any], float, int]:
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "format": LLM_RESPONSE_SCHEMA,
        "think": False,
        "keep_alive": "30m",
        "options": {"temperature": 0, "num_predict": 300, "num_ctx": num_ctx},
    }
    request = urllib.request.Request(
        f"{base_url}/api/generate",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    started = time.monotonic()
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        body = json.loads(response.read())
    elapsed = time.monotonic() - started
    parsed = json.loads(body.get("response", ""))
    if not isinstance(parsed, dict) or parsed.get("role") not in ROLES:
        raise ValueError(f"model returned no valid role: {str(parsed)[:200]}")
    if parsed.get("confidence") not in CONFIDENCES:
        parsed["confidence"] = "low"
    if not isinstance(parsed.get("evidence_quote"), str):
        parsed["evidence_quote"] = ""
    return parsed, elapsed, int(body.get("prompt_eval_count") or 0)


def needs_review(row: dict[str, Any] | None) -> bool:
    return (
        row is None
        or row.get("role") not in ROLES
        or row.get("confidence") != "high"
        or not row.get("quote_verified")
    )


def cmd_llm_label(args: argparse.Namespace) -> None:
    corpus = load_corpus(args.corpus_dir)
    taxonomy = load_taxonomy(args.taxonomy)
    ids = resolve_scope(args.scope, corpus)
    base_url = (args.ollama_url or os.environ.get("OLLAMA_BASE_URL")
                or "http://localhost:11434").rstrip("/")
    check_ollama(base_url, args.model)
    stem = slug(args.model)
    labels_path = args.out_dir / f"llm_labels_{stem}.jsonl"
    existing = latest_labels(labels_path)

    def current(chunk_id: str) -> bool:
        row = existing.get(chunk_id)
        return bool(
            row
            and row.get("role") in ROLES
            and row.get("model") == args.model
            and row.get("prompt_version") == PROMPT_VERSION
            and row.get("taxonomy_sha256") == taxonomy.sha256
            and row.get("text_sha256") == sha256_text(corpus.chunks[chunk_id]["text"])
        )

    todo = [chunk_id for chunk_id in ids if not current(chunk_id)]
    print(f"{len(ids) - len(todo)}/{len(ids)} chunks already labelled with this model, "
          f"prompt and taxonomy; {len(todo)} to go. Writing to {labels_path}")
    calls = errors = 0
    seconds = 0.0
    for chunk_id in todo:
        chunk = corpus.chunks[chunk_id]
        row: dict[str, Any] = {
            "schema_version": LLM_SCHEMA,
            "chunk_id": chunk_id,
            "model": args.model,
            "prompt_version": PROMPT_VERSION,
            "taxonomy_version": taxonomy.version,
            "taxonomy_sha256": taxonomy.sha256,
            "corpus_version": corpus.corpus_version,
            "text_sha256": sha256_text(chunk["text"]),
            "labeled_at": utc_now(),
        }
        try:
            result, elapsed, prompt_tokens = call_ollama(
                base_url=base_url,
                model=args.model,
                prompt=build_prompt(taxonomy, chunk),
                timeout_seconds=args.timeout_seconds,
                num_ctx=args.num_ctx,
            )
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
            row.update(role=None, status="error", error=f"HTTP {exc.code}: {detail}")
            errors += 1
        except urllib.error.URLError as exc:
            if not isinstance(exc.reason, TimeoutError):
                raise SystemExit(f"Ollama stopped responding ({exc.reason}). "
                                 "Rerun the same command to resume.") from exc
            row.update(role=None, status="error", error=f"timeout: {exc.reason}")
            errors += 1
        except (TimeoutError, ValueError) as exc:
            row.update(role=None, status="error", error=f"{type(exc).__name__}: {exc}")
            errors += 1
        else:
            calls += 1
            seconds += elapsed
            quote = result["evidence_quote"]
            row.update(
                status="ok",
                role=result["role"],
                confidence=result["confidence"],
                evidence_quote=quote,
                quote_verified=quote_in_text(quote, chunk["text"]),
                prompt_tokens=prompt_tokens,
                context_may_be_truncated=prompt_tokens >= args.num_ctx - 8,
                elapsed_seconds=round(elapsed, 3),
            )
        append_jsonl(labels_path, row)
        existing[chunk_id] = row
        finished = calls + errors
        if finished % args.progress_every == 0 or finished == len(todo):
            average = seconds / calls if calls else 0.0
            left = (len(todo) - finished) * average
            print(f"  {finished}/{len(todo)} done, {errors} errors, "
                  f"{average:.1f} s per chunk, about {left / 60:.0f} min left", flush=True)

    in_scope = [existing.get(chunk_id) for chunk_id in ids]
    review = [chunk_id for chunk_id, row in zip(ids, in_scope, strict=True) if needs_review(row)]
    review_path = args.out_dir / f"llm_review_queue_{stem}.txt"
    review_path.write_text(
        "# Chunks to check by hand: errors, confidence below high, or a quote not found\n"
        "# in the chunk. Use: annotate --scope <this file> --show-llm <llm labels file>\n"
        + "".join(f"{chunk_id}\n" for chunk_id in review),
        encoding="utf-8",
        newline="\n",
    )
    ok = [row for row in in_scope if row and row.get("role") in ROLES]
    counts = Counter(row["role"] for row in ok)
    print(f"\nLabelled {len(ok)}/{len(ids)} chunks; {len(ids) - len(ok)} still missing "
          "(rerun to retry errors).")
    print("  " + "  ".join(f"{role} {counts[role]}" for role in ROLES))
    print(f"  confidence: {dict(Counter(row['confidence'] for row in ok))}")
    print(f"Review queue: {len(review)} chunks in {review_path}")


# ---------------------------------------------------------------------------
# compare


def agreement_report(reference: Sequence[str], candidate: Sequence[str]) -> dict[str, Any]:
    """Cohen's kappa and per-role P/R/F1, treating ``reference`` as the truth."""

    if len(reference) != len(candidate) or not reference:
        raise ValueError("reference and candidate must be non-empty and the same length")
    total = len(reference)
    matrix = {row: dict.fromkeys(ROLES, 0) for row in ROLES}
    for truth, guess in zip(reference, candidate, strict=True):
        matrix[truth][guess] += 1
    ref_counts = Counter(reference)
    cand_counts = Counter(candidate)
    observed = sum(matrix[role][role] for role in ROLES) / total
    expected = sum(ref_counts[role] * cand_counts[role] for role in ROLES) / total**2
    kappa = None if expected == 1 else (observed - expected) / (1 - expected)
    per_role: dict[str, dict[str, Any]] = {}
    f1_values = []
    for role in ROLES:
        hits = matrix[role][role]
        precision = hits / cand_counts[role] if cand_counts[role] else None
        recall = hits / ref_counts[role] if ref_counts[role] else None
        if ref_counts[role] == 0 and cand_counts[role] == 0:
            f1 = None
        elif precision and recall:
            f1 = 2 * precision * recall / (precision + recall)
        else:
            f1 = 0.0
        if f1 is not None:
            f1_values.append(f1)
        per_role[role] = {
            "support": ref_counts[role],
            "predicted": cand_counts[role],
            "precision": precision,
            "recall": recall,
            "f1": f1,
        }
    return {
        "n": total,
        "accuracy": observed,
        "micro_f1": observed,
        "macro_f1": sum(f1_values) / len(f1_values) if f1_values else None,
        "cohen_kappa": kappa,
        "comparison_application_confusions": (
            matrix["comparison"]["application"] + matrix["application"]["comparison"]
        ),
        "per_role": per_role,
        "confusion_matrix": matrix,
    }


def fmt(value: float | None) -> str:
    return "  -  " if value is None else f"{value:.3f}"


def print_report(title: str, report: dict[str, Any]) -> None:
    print(f"\n{title}: n={report['n']}  accuracy={fmt(report['accuracy'])}  "
          f"kappa={fmt(report['cohen_kappa'])}  macro-F1={fmt(report['macro_f1'])}")
    print(f"{'role':<12}{'support':>8}{'pred':>6}{'P':>8}{'R':>8}{'F1':>8}")
    for role, row in report["per_role"].items():
        print(f"{role:<12}{row['support']:>8}{row['predicted']:>6}"
              f"{fmt(row['precision']):>8}{fmt(row['recall']):>8}{fmt(row['f1']):>8}")
    print("confusion (rows = reference, columns = candidate):")
    print(" " * 12 + "".join(f"{role[:4]:>6}" for role in ROLES))
    for role in ROLES:
        cells = report["confusion_matrix"][role]
        print(f"{role:<12}" + "".join(f"{cells[col]:>6}" for col in ROLES))
    print(f"comparison <-> application confusions: "
          f"{report['comparison_application_confusions']}")


def cmd_compare(args: argparse.Namespace) -> None:
    reference = usable(latest_labels(args.reference))
    candidate = usable(latest_labels(args.candidate))
    if not reference or not candidate:
        raise SystemExit("Both label files need at least one labelled chunk.")
    if args.scope:
        corpus = load_corpus(args.corpus_dir)
        order = resolve_scope(args.scope, corpus)
    else:
        corpus = None
        order = list(reference)
    common = [chunk_id for chunk_id in order if chunk_id in reference and chunk_id in candidate]
    if not common:
        raise SystemExit("The two files share no labelled chunk IDs.")
    taxonomy_hashes = {
        row.get("taxonomy_sha256") for row in (*reference.values(), *candidate.values())
    }
    if len(taxonomy_hashes) > 1:
        print("Warning: the labels were made under different taxonomy versions.")
    result: dict[str, Any] = {
        "reference_file": str(args.reference),
        "candidate_file": str(args.candidate),
        "all": agreement_report(
            [reference[c]["role"] for c in common], [candidate[c]["role"] for c in common]
        ),
    }
    print_report("All shared chunks", result["all"])
    sure = [chunk_id for chunk_id in common if not reference[chunk_id].get("unsure")]
    if 0 < len(sure) < len(common):
        result["reference_sure_only"] = agreement_report(
            [reference[c]["role"] for c in sure], [candidate[c]["role"] for c in sure]
        )
        print_report("Excluding reference labels marked unsure",
                     result["reference_sure_only"])

    stem = f"{args.reference.stem}__vs__{args.candidate.stem}"
    report_path = args.out_dir / f"compare_{stem}.json"
    write_json(report_path, result)
    disagreements = [c for c in common if reference[c]["role"] != candidate[c]["role"]]
    csv_path = args.out_dir / f"disagreements_{stem}.csv"
    if corpus is None and disagreements:
        corpus = load_corpus(args.corpus_dir)
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["chunk_id", "reference_role", "reference_unsure", "reference_note",
                         "candidate_role", "candidate_confidence", "candidate_quote",
                         "section", "text_start"])
        for chunk_id in disagreements:
            ref, cand = reference[chunk_id], candidate[chunk_id]
            chunk = corpus.chunks.get(chunk_id, {}) if corpus else {}
            writer.writerow([
                chunk_id, ref["role"], ref.get("unsure", ""), ref.get("note", ""),
                cand["role"], cand.get("confidence", ""), cand.get("evidence_quote", ""),
                f"{chunk.get('section_id', '')} {chunk.get('section_title', '')}".strip(),
                " ".join(chunk.get("text", "").split())[:300],
            ])
    print(f"\nShared chunks: {len(common)}; disagreements: {len(disagreements)}")
    print(f"Report: {report_path}\nDisagreements: {csv_path}")


# ---------------------------------------------------------------------------
# candidates

ADVANCED_ROLES = ("derivation", "boundary")
DERIVATION_CUES = re.compile(
    r"\b(substitut\w*|we (?:obtain|get|find|see that)|it follows|rearrang\w*|solving for|"
    r"deriv\w*|combining|eliminat\w*|leaving|cancel\w*|thus|therefore|hence|so that)\b",
    re.IGNORECASE,
)
BOUNDARY_CUES = re.compile(
    r"\b(valid|validity|only (?:if|when|for)|assum\w*|neglect\w*|approximat\w*|"
    r"breaks? down|does not (?:apply|hold)|not (?:valid|true|apply)|limit\w*|"
    r"much (?:less|smaller|greater|larger) than|ideal|special case|"
    r"approach(?:es)? (?:zero|infinity)|in general)\b",
    re.IGNORECASE,
)
WORKED_EXAMPLE = re.compile(r"\b(?:Solution|Strategy)\b")


def advanced_candidate(chunk: dict[str, Any], llm_role: str | None = None) -> bool:
    """Flag chunks that might be derivation or boundary, whatever the LLM said.

    The local model misses most derivations, so the text cues select chunks for a
    stronger reviewer on their own; an LLM derivation or boundary label adds more.
    """

    text = chunk["text"]
    equations = text.count("[EQUATION")
    worked = bool(WORKED_EXAMPLE.search(text))
    return (
        llm_role in ADVANCED_ROLES
        or (equations >= 2 and len(DERIVATION_CUES.findall(text)) >= 2 and not worked)
        or len(BOUNDARY_CUES.findall(text)) >= 2
        or (equations >= 10 and not worked)
    )


def cmd_candidates(args: argparse.Namespace) -> None:
    corpus = load_corpus(args.corpus_dir)
    llm = usable(latest_labels(args.llm)) if args.llm else {}
    by_text = [c for c, chunk in corpus.chunks.items() if advanced_candidate(chunk)]
    ids = [
        c for c, chunk in corpus.chunks.items()
        if advanced_candidate(chunk, llm.get(c, {}).get("role"))
    ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        "# Chunks that might be derivation or boundary, for review by a stronger labeller.\n"
        f"# {len(by_text)} from text cues; {len(ids) - len(by_text)} more from LLM labels"
        f"{f' in {args.llm.name}' if args.llm else ''}.\n"
        + "".join(f"{chunk_id}\n" for chunk_id in ids),
        encoding="utf-8",
        newline="\n",
    )
    print(f"Wrote {len(ids)} candidates ({len(by_text)} from text cues) to {args.output}")


# ---------------------------------------------------------------------------
# export


def build_package_rows(
    scope_ids: Sequence[str],
    human: dict[str, dict[str, Any]],
    llm: dict[str, dict[str, Any]],
    review: dict[str, dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Prefer a human label, then a review label, then the LLM label; list what is missing."""

    review = review or {}
    rows: list[dict[str, Any]] = []
    missing: list[str] = []
    for chunk_id in scope_ids:
        if chunk_id in human:
            role, source = human[chunk_id]["role"], "human"
        elif chunk_id in review:
            role, source = review[chunk_id]["role"], f"review:{review[chunk_id]['model']}"
        elif chunk_id in llm:
            role, source = llm[chunk_id]["role"], f"llm:{llm[chunk_id]['model']}"
        else:
            missing.append(chunk_id)
            continue
        rows.append(
            {"schema_version": PACKAGE_SCHEMA, "chunk_id": chunk_id, "role": role,
             "label_source": source}
        )
    return rows, missing


def check_with_member7_loader(manifest_path: Path, taxonomy_version: str) -> None:
    sys.path.insert(0, str(REPOSITORY_ROOT / "src"))
    try:
        from cs30.generation.lambda_search import (
            load_role_label_package,
            validate_formal_role_label_scope,
        )
    except ImportError as exc:
        print(f"Skipped the Member 7 loader check: {exc}")
        return
    package = load_role_label_package(manifest_path, expected_taxonomy_version=taxonomy_version)
    validate_formal_role_label_scope(package)
    print(f"Member 7's loader accepts the package: {len(package.labels)} labels.")


def cmd_export(args: argparse.Namespace) -> None:
    corpus = load_corpus(args.corpus_dir)
    taxonomy = load_taxonomy(args.taxonomy)
    scope_ids = resolve_scope(args.scope, corpus)
    human_rows = usable(latest_labels(args.human)) if args.human else {}
    annotator = args.annotator or next(
        (row.get("annotator") for row in human_rows.values() if row.get("annotator")), None
    )
    if not annotator:
        raise SystemExit("Pass --annotator: the manifest needs one primary annotator ID.")
    llm_all = usable(latest_labels(args.llm)) if args.llm else {}
    llm = {c: row for c, row in llm_all.items() if row.get("taxonomy_sha256") == taxonomy.sha256}
    stale_llm = len(llm_all) - len(llm)
    review_all = usable(latest_labels(args.review)) if args.review else {}
    review = {
        c: row for c, row in review_all.items() if row.get("taxonomy_sha256") == taxonomy.sha256
    }
    stale_review = len(review_all) - len(review)
    stale_human = sum(row.get("taxonomy_sha256") != taxonomy.sha256 for row in human_rows.values())

    rows, missing = build_package_rows(scope_ids, human_rows, llm, review)
    if missing and not args.allow_incomplete:
        raise SystemExit(
            f"{len(missing)} of {len(scope_ids)} chunks have no label, e.g. {missing[0]}. "
            "Rerun llm-label (it retries errors) or pass --allow-incomplete for a "
            "diagnostic package."
        )
    if not rows:
        raise SystemExit("Nothing to export.")

    labels_path = args.out_dir / f"{args.name}.jsonl"
    labels_path.parent.mkdir(parents=True, exist_ok=True)
    labels_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
                for row in rows),
        encoding="utf-8",
        newline="\n",
    )
    manifest_path = args.out_dir / f"{args.name}_provenance_manifest.json"
    write_json(
        manifest_path,
        {
            "schema_version": "0.1",
            "role_schema_version": PACKAGE_SCHEMA,
            "role_taxonomy_version": taxonomy.version,
            "annotation_version": args.annotation_version,
            "corpus_version": corpus.corpus_version,
            "parser_version": args.parser_version,
            "annotation_date": dt.date.today().isoformat(),
            "annotator_ids": [annotator],
            "double_annotated": False,
            "labels_file": labels_path.name,
            "labels_sha256": sha256_file(labels_path),
            "declared_record_count": len(rows),
            "reference_id_field": "chunk_id",
            "reference_type": "chunk",
            "reference_universe": "corpus_records",
            "role_field": "role",
            "record_schema_version_field": "schema_version",
        },
    )
    sources = Counter(row["label_source"] for row in rows)
    report = {
        "schema_version": "role-labels-v2-export-report-v1",
        "created_at_utc": utc_now(),
        "corpus_version": corpus.corpus_version,
        "corpus_hash": corpus.corpus_hash,
        "scope": args.scope,
        "scope_chunk_count": len(scope_ids),
        "exported_count": len(rows),
        "missing_count": len(missing),
        "complete": not missing,
        "label_sources": dict(sources),
        "roles": {role: sum(row["role"] == role for row in rows) for role in ROLES},
        "taxonomy_version": taxonomy.version,
        "taxonomy_status": taxonomy.status,
        "taxonomy_sha256": taxonomy.sha256,
        "llm_labels_file": str(args.llm) if args.llm else None,
        "llm_prompt_version": PROMPT_VERSION,
        "llm_labels_from_other_taxonomy_ignored": stale_llm,
        "review_labels_file": str(args.review) if args.review else None,
        "review_labels_from_other_taxonomy_ignored": stale_review,
        "human_labels_file": str(args.human) if args.human else None,
        "human_labels_from_other_taxonomy": stale_human,
        "human_labels_unsure": sum(bool(row.get("unsure")) for row in human_rows.values()),
        "missing_chunk_ids": missing[:50],
    }
    write_json(args.out_dir / f"{args.name}_export_report.json", report)
    print(f"Wrote {len(rows)} labels to {labels_path}")
    print(f"  sources: {dict(sources)}; missing: {len(missing)}")
    if stale_llm or stale_review or stale_human:
        print(f"  ignored {stale_llm} LLM and {stale_review} review labels from another "
              f"taxonomy version; {stale_human} human labels were made under another "
              "taxonomy version")
    print(f"Manifest: {manifest_path}")
    if missing:
        print("Incomplete package: Member 7's formal runs will report it as not interpretable.")
    check_with_member7_loader(manifest_path, taxonomy.version)


# ---------------------------------------------------------------------------
# CLI


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--corpus-dir", type=Path, default=DEFAULT_CORPUS_DIR)
    common.add_argument("--taxonomy", type=Path, default=DEFAULT_TAXONOMY)
    common.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    commands = parser.add_subparsers(dest="command", required=True)

    sample = commands.add_parser("sample", parents=[common], help="draw a pilot sample")
    sample.add_argument("--size", type=int, default=150)
    sample.add_argument("--seed", default="role-pilot-v1")
    sample.add_argument("--output", type=Path, default=DEFAULT_SAMPLE)
    sample.add_argument("--force", action="store_true")
    sample.set_defaults(func=cmd_sample)

    annotate = commands.add_parser("annotate", parents=[common], help="label by hand")
    annotate.add_argument("--annotator", required=True, help="your ID, e.g. your GitHub name")
    annotate.add_argument("--scope", default=str(DEFAULT_SAMPLE),
                          help="sample JSON, text file of chunk IDs, or 'all'")
    annotate.add_argument("--first", type=int, help="only the first N chunks of the scope")
    annotate.add_argument("--start", type=int, help="start at this 1-based position")
    annotate.add_argument("--show-llm", type=Path, help="show this LLM label file as hints")
    annotate.add_argument("--no-clear", dest="clear", action="store_false",
                          help="do not clear the screen between chunks")
    annotate.set_defaults(func=cmd_annotate)

    llm = commands.add_parser("llm-label", parents=[common], help="label with Ollama")
    llm.add_argument("--scope", required=True,
                     help="sample JSON, text file of chunk IDs, or 'all'")
    llm.add_argument("--model", default="qwen3:8b")
    llm.add_argument("--ollama-url", help="default: $OLLAMA_BASE_URL or localhost:11434")
    llm.add_argument("--timeout-seconds", type=int, default=240)
    llm.add_argument("--num-ctx", type=int, default=8192)
    llm.add_argument("--progress-every", type=int, default=10)
    llm.set_defaults(func=cmd_llm_label)

    compare = commands.add_parser("compare", parents=[common], help="agreement report")
    compare.add_argument("reference", type=Path, help="label file treated as the truth")
    compare.add_argument("candidate", type=Path, help="label file being checked")
    compare.add_argument("--scope", help="restrict to this sample JSON or ID file")
    compare.set_defaults(func=cmd_compare)

    candidates = commands.add_parser(
        "candidates", parents=[common], help="list chunks that might be derivation or boundary"
    )
    candidates.add_argument("--llm", type=Path, help="also add chunks this LLM file marks")
    candidates.add_argument("--output", type=Path,
                            default=DEFAULT_OUT_DIR / "advanced_candidates.txt")
    candidates.set_defaults(func=cmd_candidates)

    export = commands.add_parser("export", parents=[common], help="write the M7 package")
    export.add_argument("--llm", type=Path, help="LLM label file")
    export.add_argument("--review", type=Path,
                        help="review label file from a stronger labeller; overrides the LLM")
    export.add_argument("--human", type=Path, help="human label file; overrides everything")
    export.add_argument("--annotator", help="manifest annotator ID (default: from --human)")
    export.add_argument("--scope", default="all")
    export.add_argument("--name", default="role_labels_v2")
    export.add_argument("--annotation-version",
                        default=f"role-labels-v2-{dt.date.today():%Y%m%d}")
    export.add_argument("--parser-version", default="1.3.2")
    export.add_argument("--allow-incomplete", action="store_true")
    export.set_defaults(func=cmd_export)
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    args = build_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
