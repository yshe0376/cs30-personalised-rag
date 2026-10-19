"""Prepare, check and run native V2 four-condition generation batches."""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from datetime import date
from pathlib import Path

from cs30.generation.client import OllamaChatClient, OpenAIResponsesClient
from cs30.generation.reranking import EvidenceRole
from cs30.v2.corpus import load_corpus_records
from cs30.v2.errors import V2Error
from cs30.v2.experiment import (
    ExperimentConfig,
    LambdaSelection,
    load_prepared,
    load_v2_gold,
    prepare_experiment,
    retrieve_bm25,
    retryable_provider_failure,
    run_experiment,
    select_dev_lambda,
    write_json,
)
from cs30.v2.experiment_gold import convert_m3_gold
from cs30.v2.io import sha256_bytes


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    convert = commands.add_parser("convert-gold", help="explicit, verified M3-to-V2 conversion")
    convert.add_argument("--gold", type=Path, required=True)
    convert.add_argument("--corpus-dir", type=Path, required=True)
    convert.add_argument("--output-dir", type=Path, required=True)
    convert.add_argument("--source-schema", choices=("0.1", "0.2"), default="0.1")
    convert.add_argument(
        "--split-map",
        type=Path,
        help="explicit JSON provisional-label to Dev/Test mapping, recorded in audit",
    )
    prepare = commands.add_parser("prepare", help="freeze and validate the complete experiment")
    for name in ("corpus-dir", "gold", "output-dir"):
        prepare.add_argument(f"--{name}", type=Path, required=True)
    prepare.add_argument("--model", required=True)
    prepare.add_argument("--split", choices=("dev", "test"), default="dev")
    prepare.add_argument("--role-manifest", type=Path)
    prepare.add_argument(
        "--gold-conversion-manifest",
        type=Path,
        help="preserve the source hash and explicit provisional split mapping",
    )
    prepare.add_argument(
        "--selected-lambda",
        type=Path,
        help="saved V2 Dev selection; same corpus, Gold, Roles and settings",
    )
    prepare.add_argument(
        "--retrieval", type=Path, help="native V2 saved candidates; otherwise BM25"
    )
    prepare.add_argument("--candidate-k", type=int, default=20)
    prepare.add_argument("--evidence-k", type=int, default=5)
    prepare.add_argument("--lambda-weight", type=float, default=0.35)
    prepare.add_argument("--profile-confidence", type=float, default=1.0)
    prepare.add_argument("--max-retries", type=int, default=1)
    prepare.add_argument(
        "--limit", type=int, help="positive Dev-only question limit for smoke runs"
    )
    prepare.add_argument(
        "--allow-missing-roles",
        action="store_true",
        help="explicit diagnostic fallback; no reranking quality claim",
    )
    check = commands.add_parser("check", help="validate frozen inputs without model calls")
    check.add_argument("--prepared-dir", type=Path, required=True)
    select = commands.add_parser("select-lambda", help="Dev-only complete-evidence selection")
    select.add_argument("--prepared-dir", type=Path, required=True)
    select.add_argument("--lambdas", type=float, nargs="+", default=[0, 0.1, 0.2, 0.35, 0.5])
    select.add_argument("--output", type=Path, required=True)
    run = commands.add_parser("run", help="generate answers and traces for independent M8 scoring")
    run.add_argument("--prepared-dir", type=Path, required=True)
    run.add_argument("--output-dir", type=Path, required=True)
    run.add_argument("--provider", choices=("ollama", "openai"), required=True)
    run.add_argument("--timeout", type=float, default=120.0)
    run.add_argument("--max-output-tokens", type=int, default=2048)
    run.add_argument("--context-window", type=int, help="explicit Ollama context token capacity")
    run.add_argument(
        "--resume", action="store_true", help="verify and resume saved cell checkpoints"
    )
    run.add_argument(
        "--stop-after-errors",
        type=int,
        default=0,
        help="stop after this many consecutive new technical failures; zero disables",
    )
    run.add_argument("--seed", type=int, default=0, help="pinned Ollama random seed")
    roles = commands.add_parser("role-template", help="export candidate chunks with blank Roles")
    roles.add_argument("--corpus-dir", type=Path, required=True)
    roles.add_argument("--gold", type=Path, required=True)
    roles.add_argument("--split", choices=("dev", "test"), default="dev")
    roles.add_argument("--candidate-k", type=int, default=20)
    roles.add_argument("--output", type=Path, required=True)
    role_import = commands.add_parser("import-roles", help="package actual candidate annotations")
    role_import.add_argument("--corpus-dir", type=Path, required=True)
    role_import.add_argument("--form", type=Path, required=True)
    role_import.add_argument("--annotator-id", required=True)
    role_import.add_argument("--output-dir", type=Path, required=True)
    return result


def _new_file(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(data)


def _client(provider: str, model: str, timeout: float, max_tokens: int):
    cls = OllamaChatClient if provider == "ollama" else OpenAIResponsesClient
    return cls(model, timeout_seconds=timeout, max_output_tokens=max_tokens, temperature=0.0)


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "convert-gold":
            summary = convert_m3_gold(
                args.gold,
                args.corpus_dir,
                args.output_dir,
                source_schema=args.source_schema,
                split_mapping=json.loads(args.split_map.read_bytes()) if args.split_map else None,
            )
            print(json.dumps(summary, ensure_ascii=False))
            return 0
        if args.command == "select-lambda":
            selection = select_dev_lambda(args.prepared_dir, args.lambdas)
            _new_file(args.output, (selection.model_dump_json(indent=2) + "\n").encode())
            print(f"Dev-selected lambda: {selection.lambda_weight}; development result only.")
            return 0
        if args.command == "prepare":
            selection = (
                LambdaSelection.model_validate_json(args.selected_lambda.read_bytes())
                if args.selected_lambda
                else None
            )
            config = ExperimentConfig(
                generator_model=args.model,
                split=args.split,
                candidate_k=args.candidate_k,
                evidence_k=args.evidence_k,
                lambda_weight=selection.lambda_weight if selection else args.lambda_weight,
                lambda_policy="dev_selected" if selection else "fixed_exploratory",
                profile_confidence=args.profile_confidence,
                max_retries=args.max_retries,
                allow_missing_roles=args.allow_missing_roles,
            )
            summary = prepare_experiment(
                corpus_dir=args.corpus_dir,
                gold_path=args.gold,
                output_dir=args.output_dir,
                config=config,
                role_manifest=args.role_manifest,
                retrieval_path=args.retrieval,
                question_limit=args.limit,
                selected_lambda_path=args.selected_lambda,
                conversion_manifest_path=args.gold_conversion_manifest,
            )
            print(json.dumps(summary, ensure_ascii=False))
            return 0
        if args.command in {"check", "run"}:
            manifest, config, matrix, gold, _, _ = load_prepared(args.prepared_dir)
            if args.command == "check":
                print(
                    json.dumps(
                        {
                            "status": "ready_for_development_run",
                            "reportable": False,
                            "question_count": manifest["question_count"],
                            "expected_runs": len(matrix.cases),
                            "role_coverage_complete": manifest["role_coverage_complete"],
                            "model": config.generator_model,
                            "model_connection_checked": False,
                        },
                        ensure_ascii=False,
                    )
                )
                return 0
            if args.output_dir.exists() and not args.resume:
                raise ValueError("output directory already exists")
            if not math.isfinite(args.timeout) or args.timeout <= 0 or args.max_output_tokens < 1:
                raise ValueError("timeout and token limit must be finite and positive")
            if config.lambda_weight == 0:
                raise ValueError("lambda_weight == 0 cannot run an R1 matrix")
            client = _client(
                args.provider, config.generator_model, args.timeout, args.max_output_tokens
            )
            if args.context_window is not None:
                if args.provider != "ollama" or args.context_window <= args.max_output_tokens + 512:
                    raise ValueError("context-window requires Ollama and room for output/framing")
                client.context_window = args.context_window
            if args.provider == "ollama":
                client.seed = args.seed
            if callable(getattr(client, "pin_model", None)):
                client.pin_model()
            if args.stop_after_errors < 0:
                raise ValueError("stop-after-errors must be nonnegative")
            consecutive_errors = 0

            def progress(done, total, record, details):
                nonlocal consecutive_errors
                print(f"V2 generation {done}/{total}: {record.status}", flush=True)
                consecutive_errors = (
                    consecutive_errors + 1 if retryable_provider_failure(record, details) else 0
                )
                if args.stop_after_errors and consecutive_errors >= args.stop_after_errors:
                    raise ValueError(
                        "stopped after consecutive provider failures; inspect and resume"
                    )

            runs = run_experiment(
                args.prepared_dir,
                args.output_dir,
                client,
                provider=args.provider,
                resume=args.resume,
                progress=progress,
            )
            print(f"Saved {len(runs)} V2 cells to {args.output_dir}; hand off to M8 for scoring.")
            return 3 if any(r.status not in {"answered", "abstained"} for r in runs) else 0
        corpus = load_corpus_records(args.corpus_dir)
        if args.command == "role-template":
            if args.output.exists() or args.candidate_k < 1:
                raise ValueError("Role template output must be new and candidate_k positive")
            gold = {
                key: value
                for key, value in load_v2_gold(args.gold).items()
                if value.split.value == args.split
            }
            if not gold or any(
                q.corpus_version != corpus.manifest.corpus_version for q in gold.values()
            ):
                raise ValueError("Gold split must be nonempty and match the V2 corpus")
            retrieval = retrieve_bm25(corpus, gold, args.candidate_k)
            ids = sorted({h.chunk_id for r in retrieval for h in r.retrieval.hits})
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("x", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=["chunk_id", "text", "role"])
                writer.writeheader()
                writer.writerows(
                    {"chunk_id": key, "text": corpus.chunks_by_id[key].text, "role": ""}
                    for key in ids
                )
            print(f"Wrote {len(ids)} candidates with BLANK Role labels.")
            return 0
        if args.output_dir.exists() or not args.annotator_id.strip():
            raise ValueError("Role output must be new and annotator identity nonblank")
        rows, seen = [], set()
        with args.form.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames != ["chunk_id", "text", "role"]:
                raise ValueError("Role form must have exactly chunk_id,text,role columns")
            for row in reader:
                chunk = corpus.chunks_by_id.get(row["chunk_id"])
                if chunk is None or chunk.text != row["text"] or chunk.chunk_id in seen:
                    raise ValueError("Role form has unknown, altered, or duplicate chunks")
                seen.add(chunk.chunk_id)
                rows.append(
                    {
                        "schema_version": "role-labels-v1",
                        "chunk_id": chunk.chunk_id,
                        "role": EvidenceRole(row["role"]).value,
                    }
                )
        if not rows:
            raise ValueError("Role annotations must not be empty")
        data = ("".join(json.dumps(row) + "\n" for row in rows)).encode()
        args.output_dir.mkdir(parents=True, exist_ok=False)
        (args.output_dir / "role_labels.jsonl").write_bytes(data)
        write_json(
            args.output_dir / "role_manifest.json",
            {
                "schema_version": "0.1",
                "role_schema_version": "role-labels-v1",
                "role_taxonomy_version": "evidence-role-v1",
                "annotation_version": "supplied-v2-roles-0.1",
                "corpus_version": corpus.manifest.corpus_version,
                "parser_version": "+".join(
                    sorted({d.parser_version for d in corpus.manifest.documents})
                ),
                "annotation_date": date.today().isoformat(),
                "annotator_ids": [args.annotator_id],
                "double_annotated": False,
                "labels_file": "role_labels.jsonl",
                "labels_sha256": sha256_bytes(data),
                "declared_record_count": len(rows),
                "reference_type": "chunk",
                "reference_universe": "corpus_records",
            },
        )
        return 0
    except (ValueError, OSError, V2Error, KeyError, TypeError, csv.Error) as exc:
        print(f"cs30-experiment-v2: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
