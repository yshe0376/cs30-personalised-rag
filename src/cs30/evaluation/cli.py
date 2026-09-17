"""Command-line entry points for batch evaluation and offline re-scoring."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from cs30.config import load_config
from cs30.contracts import OpenStaxDocument, RetrievalMode, StudentLevel, StudentProfile
from cs30.pipeline import (
    build_fixture_deps,
    build_real_deps,
    build_real_retrieval_deps,
)
from cs30.ports import Retriever

from .answer_metrics import AnswerCitationScorer
from .answer_reporting import write_answer_citation_reports
from .extension_reporting import (
    audit_role_label_provenance,
    load_experiment_conditions,
    seal_blind_rating_submission,
    write_blind_rating_materials,
    write_extension_reports,
)
from .io import (
    load_gold_samples,
    load_mappings,
    load_normalized_gold,
    load_run_results,
    write_normalized_gold,
)
from .manifest import (
    GitState,
    RunManifest,
    assert_clean_for_report,
    capture_git_state,
    write_manifest,
)
from .metrics import validate_artifact_compatibility
from .models import EvaluationSplit, ExecutionMode, GoldSample
from .normalization import normalize_gold_samples
from .openstax_archive import (
    load_openstax_archive,
    load_openstax_document,
    load_prepared_corpus,
    write_prepared_corpus,
)
from .runner import run_batch
from .scoring import score_saved_run


def _int_values(values: list[str]) -> list[int]:
    try:
        return [int(value) for value in values]
    except ValueError as exc:
        raise argparse.ArgumentTypeError("K values must be integers") from exc


def _add_common_manifest_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--dataset-version", default="unspecified")
    parser.add_argument("--dataset-id")
    parser.add_argument("--corpus-version", default="unspecified")
    parser.add_argument("--chunk-version", default="unspecified")
    parser.add_argument("--parser-version")
    parser.add_argument("--gold-annotation-version")
    parser.add_argument(
        "--mapping-version",
        help="version of the M4 gold-to-chunk mapping used for formal scoring",
    )
    parser.add_argument("--embedding-version", default="unspecified")
    parser.add_argument("--index-version", default="unspecified")
    parser.add_argument("--generation-model")
    parser.add_argument("--prompt-version", default="prompt-unknown")
    parser.add_argument(
        "--profile",
        default="intermediate",
        choices=[level.value for level in StudentLevel],
    )
    parser.add_argument(
        "--threshold",
        type=float,
        help=(
            "retrieval score threshold; applies to BM25 in bm25 mode and to "
            "dense candidates in dense/hybrid mode"
        ),
    )
    parser.add_argument("--allow-dirty", action="store_true")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cs30-evaluate")
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser("run", help="run a gold batch and save per-question JSONL")
    run.add_argument("--gold", required=True, type=Path)
    run.add_argument(
        "--document",
        type=Path,
        help="prepared OpenStaxDocument used to verify Gold evidence spans",
    )
    run.add_argument(
        "--corpus-manifest",
        type=Path,
        help="prepared corpus_manifest.json; required for formal runs",
    )
    run.add_argument("--output", required=True, type=Path)
    run.add_argument(
        "--execution-mode",
        choices=[mode.value for mode in ExecutionMode],
        default=ExecutionMode.RETRIEVAL_ONLY.value,
    )
    run.add_argument(
        "--retrieval-mode",
        choices=[mode.value for mode in RetrievalMode],
        default=RetrievalMode.HYBRID.value,
    )
    run.add_argument("--top-k", type=int, default=5)
    run.add_argument("--k-values", nargs="+", default=["1", "3", "5"])
    run.add_argument("--split", choices=[split.value for split in EvaluationSplit])
    run.add_argument("--resume", action="store_true")
    run.add_argument("--fixture", action="store_true")
    run.add_argument("--environment", default="development")
    run.add_argument("--manifest", type=Path)
    run.add_argument(
        "--allow-synthetic-trace",
        action="store_true",
        help="allow deterministic fixture generation without an LLM trace",
    )
    _add_common_manifest_arguments(run)

    score = commands.add_parser("score", help="re-score a saved run without calling a model")
    score.add_argument("--gold", required=True, type=Path)
    score.add_argument(
        "--document",
        type=Path,
        help="prepared OpenStaxDocument used to verify Gold evidence spans",
    )
    score.add_argument(
        "--corpus-manifest",
        type=Path,
        help="prepared corpus_manifest.json; required for formal scoring",
    )
    score.add_argument("--runs", required=True, type=Path)
    score.add_argument("--mapping", required=True, type=Path)
    score.add_argument("--output", type=Path)
    score.add_argument(
        "--scores-output",
        type=Path,
        help="write per-question retrieval scores as JSONL",
    )
    score.add_argument(
        "--answer-citation-output-dir",
        type=Path,
        help=(
            "write answer, abstention, format, citation, failure, CSV, and Markdown "
            "artifacts without rerunning retrieval or generation"
        ),
    )
    score.add_argument("--k-values", nargs="+")
    score.add_argument("--manifest", type=Path)

    extension = commands.add_parser(
        "report-extension",
        help=(
            "combine saved M8 score artifacts with textbook, level, lambda, "
            "manual-rating, and Role-label provenance inputs"
        ),
    )
    extension.add_argument(
        "--scores",
        required=True,
        nargs="+",
        type=Path,
        help="one or more answer_citation_scores.jsonl files",
    )
    extension.add_argument(
        "--contexts",
        required=True,
        type=Path,
        help="M8 experiment-context JSONL keyed by run_id",
    )
    extension.add_argument("--output-dir", required=True, type=Path)
    extension.add_argument(
        "--ratings",
        type=Path,
        help="optional blinded level-adaptation rating CSV or JSONL",
    )
    extension.add_argument(
        "--rating-key",
        type=Path,
        help="private post-rating mapping from blinded answer IDs to run IDs",
    )
    extension.add_argument(
        "--rating-rubric",
        type=Path,
        help="team-frozen level-adaptation rubric version and score range",
    )
    extension.add_argument(
        "--rating-submission-manifest",
        type=Path,
        help="sealed SHA manifest for the completed ratings, private key, and rubric",
    )
    extension.add_argument(
        "--role-manifest",
        type=Path,
        help="optional M8 provenance sidecar for the M3 Role-label package",
    )
    extension.add_argument(
        "--role-gold",
        type=Path,
        help="Gold JSONL used to validate Role-label question and span IDs",
    )
    extension.add_argument(
        "--role-mapping",
        type=Path,
        help="M4 mapping used to validate Role-label chunk IDs",
    )
    extension.add_argument(
        "--role-records",
        type=Path,
        help="optional M4 records.jsonl used as the full valid chunk-ID universe",
    )
    extension.add_argument(
        "--role-question-references",
        type=Path,
        help=(
            "normalized JSONL of valid question_id/chunk_id pairs from the "
            "frozen candidate outputs"
        ),
    )
    extension.add_argument(
        "--allow-incomplete",
        action="store_true",
        help=(
            "development only: allow experiment buckets without both lambda=0 "
            "and frozen-lambda groups, partial blind-rating coverage, or a failed "
            "Role provenance audit"
        ),
    )

    blind = commands.add_parser(
        "prepare-blind-ratings",
        help="create a single-rater anonymous level-adaptation sheet and private key",
    )
    blind.add_argument(
        "--runs",
        required=True,
        nargs="+",
        type=Path,
        help="one or more saved EvaluationRunResult JSONL files",
    )

    seal = commands.add_parser(
        "seal-blind-ratings",
        help="freeze completed single-rater files and record their SHA-256 identities",
    )
    seal.add_argument("--ratings", required=True, type=Path)
    seal.add_argument("--rating-key", required=True, type=Path)
    seal.add_argument("--rating-rubric", required=True, type=Path)
    seal.add_argument("--output", required=True, type=Path)
    blind.add_argument("--gold", required=True, type=Path)
    blind.add_argument("--contexts", required=True, type=Path)
    blind.add_argument("--output-dir", required=True, type=Path)
    blind.add_argument(
        "--seed",
        required=True,
        type=int,
        help="private deterministic randomisation seed; do not give it to the rater",
    )

    prepare = commands.add_parser(
        "prepare-corpus",
        help="validate and merge an OpenStax chapter archive into one corpus document",
    )
    prepare.add_argument("--archive", required=True, type=Path)
    prepare.add_argument("--output-dir", required=True, type=Path)
    prepare.add_argument(
        "--chapters",
        nargs="+",
        help="optional chapter ids; by default all chapters in the archive are included",
    )
    normalize = commands.add_parser(
        "normalize-gold",
        help="resolve immutable M3 Gold into corpus-bound global coordinates",
    )
    normalize.add_argument("--gold", required=True, type=Path)
    normalize.add_argument("--document", required=True, type=Path)
    normalize.add_argument("--corpus-manifest", type=Path)
    normalize.add_argument("--output", required=True, type=Path)
    return parser


def _manifest_for_run(
    args: argparse.Namespace,
    state: GitState,
    *,
    split: EvaluationSplit,
    corpus_version: str,
    corpus_is_prepared: bool,
    parser_version: str | None,
    gold_annotation_version: str | None,
) -> RunManifest:
    k_values = _int_values(args.k_values)
    if args.top_k <= 0:
        raise ValueError("top_k must be positive")
    return RunManifest(
        run_id=args.output.stem,
        condition_id=args.output.stem,
        dataset_version=args.dataset_version,
        dataset_id=args.dataset_id,
        split=split,
        corpus_version=(
            corpus_version
            if corpus_is_prepared or args.corpus_version == "unspecified"
            else args.corpus_version
        ),
        chunk_version=args.chunk_version,
        parser_version=args.parser_version or parser_version,
        gold_annotation_version=(
            args.gold_annotation_version or gold_annotation_version
        ),
        mapping_version=args.mapping_version,
        embedding_version=(
            None
            if args.retrieval_mode == RetrievalMode.BM25.value
            else args.embedding_version
        ),
        index_version=args.index_version,
        generation_model=(
            (
                args.generation_model
                or ("fixture-model" if args.fixture else "model-unknown")
            )
            if args.execution_mode == ExecutionMode.RETRIEVAL_AND_GENERATION.value
            else None
        ),
        prompt_version=(
            args.prompt_version
            if args.execution_mode == ExecutionMode.RETRIEVAL_AND_GENERATION.value
            else None
        ),
        profile=(
            args.profile
            if args.execution_mode == ExecutionMode.RETRIEVAL_AND_GENERATION.value
            else "none"
        ),
        execution_mode=args.execution_mode,
        retrieval_mode=args.retrieval_mode,
        top_k=args.top_k,
        k_values=k_values,
        threshold=args.threshold,
        git_commit=state.commit,
        git_dirty=state.dirty,
        git_snapshot_sha256=state.snapshot_sha256,
        fixture_mode=args.fixture,
        synthetic_trace=args.allow_synthetic_trace,
        reportable=(
            not state.dirty
            and not args.fixture
            and not args.allow_synthetic_trace
            and args.mapping_version is not None
        ),
    )


def _chapter_documents(document: OpenStaxDocument) -> dict[tuple[str, str], str]:
    """Build raw M3 validation text keyed by document and chapter identity."""

    return {
        (document.document_id, chapter.chapter_id): document.text[
            chapter.char_start : chapter.char_end
        ]
        for chapter in document.chapters
    }


def _assert_gold_matches_prepared_corpus(
    gold: list[GoldSample],
    *,
    corpus_version: str,
    parser_version: str,
) -> None:
    gold_corpora = {sample.corpus_version for sample in gold}
    if gold_corpora != {corpus_version}:
        raise ValueError(
            "corpus_version mismatch between prepared corpus and Gold: "
            f"{corpus_version!r} != {sorted(gold_corpora)!r}"
        )
    gold_parsers = {sample.parser_version for sample in gold}
    if gold_parsers != {parser_version}:
        raise ValueError(
            "parser_version mismatch between prepared corpus and Gold: "
            f"{parser_version!r} != {sorted(gold_parsers)!r}"
        )


def _run_command(args: argparse.Namespace) -> int:
    if args.allow_synthetic_trace and not args.fixture:
        raise ValueError("--allow-synthetic-trace is only allowed with --fixture")
    if not args.gold.is_file():
        raise FileNotFoundError(f"Gold sample file not found: {args.gold}")
    if args.document is not None and not args.document.is_file():
        raise FileNotFoundError(f"prepared document not found: {args.document}")
    prepared_corpus = None
    if args.fixture:
        documents = None
        chapter_documents = None
        if args.document is not None:
            document = load_openstax_document(args.document)
            documents = {document.document_id: document.text}
            chapter_documents = _chapter_documents(document)
        gold = load_gold_samples(
            args.gold,
            documents=documents,
            chapter_documents=chapter_documents,
        )
    else:
        if args.document is None:
            raise ValueError("formal run requires --document and a prepared corpus manifest")
        # Reject raw M3 files before checking git state or constructing retrieval dependencies.
        load_normalized_gold(args.gold)
        prepared_corpus = load_prepared_corpus(args.document, args.corpus_manifest)
        gold = load_normalized_gold(args.gold, document=prepared_corpus.document)
        _assert_gold_matches_prepared_corpus(
            gold,
            corpus_version=prepared_corpus.corpus_version,
            parser_version=prepared_corpus.document.parser_version,
        )
        if (
            args.corpus_version != "unspecified"
            and args.corpus_version != prepared_corpus.corpus_version
        ):
            raise ValueError(
                "--corpus-version must match the prepared corpus manifest for formal runs"
            )
    state = capture_git_state()
    assert_clean_for_report(state, allow_dirty=args.allow_dirty)
    if args.split is not None:
        gold = [sample for sample in gold if sample.split.value == args.split]
        if not gold:
            raise ValueError(f"no gold samples found for split {args.split!r}")
    splits = {sample.split for sample in gold}
    corpora = {sample.corpus_version for sample in gold}
    parsers = {sample.parser_version for sample in gold}
    annotations = {sample.gold_annotation_version for sample in gold}
    if len(splits) != 1:
        raise ValueError("one batch must contain exactly one evaluation split")
    if len(corpora) != 1:
        raise ValueError("one batch must contain exactly one corpus version")
    if len(parsers) != 1:
        raise ValueError("one batch must contain exactly one parser version")
    if len(annotations) != 1:
        raise ValueError("one batch must contain exactly one gold annotation version")
    manifest = _manifest_for_run(
        args,
        state,
        split=next(iter(splits)),
        corpus_version=(
            prepared_corpus.corpus_version
            if prepared_corpus is not None
            else next(iter(corpora))
        ),
        corpus_is_prepared=prepared_corpus is not None,
        parser_version=(
            prepared_corpus.document.parser_version
            if prepared_corpus is not None
            else next(iter(parsers))
        ),
        gold_annotation_version=next(iter(annotations)),
    )
    manifest_path = args.manifest or args.output.with_suffix(".manifest.json")
    if manifest_path.resolve() == args.output.resolve():
        raise ValueError("--manifest must not be the same path as --output")
    if manifest_path.exists():
        raise FileExistsError(f"refusing to overwrite run manifest: {manifest_path}")

    generation_deps = None
    if args.fixture:
        generation_deps = build_fixture_deps()
        retriever: Retriever = generation_deps.retriever
    else:
        config = load_config(args.environment)
        retrieval_updates: dict[str, object] = {
            "mode": RetrievalMode(args.retrieval_mode),
            "top_k": args.top_k,
        }
        if args.threshold is not None:
            threshold_field = (
                "bm25_min_score"
                if args.retrieval_mode == RetrievalMode.BM25.value
                else "dense_min_similarity"
            )
            retrieval_updates[threshold_field] = args.threshold
        config_payload = config.model_dump(mode="python")
        config_payload["retrieval"] = {
            **config.retrieval.model_dump(mode="python"),
            **retrieval_updates,
        }
        config = type(config).model_validate(config_payload)
        if manifest.execution_mode is ExecutionMode.RETRIEVAL_ONLY:
            retrieval_deps = build_real_retrieval_deps(config)
            if retrieval_deps.mode != "real":
                raise ValueError(
                    "evaluation run resolved to fixture dependencies; pass --fixture "
                    "explicitly for an engineering fixture run"
                )
            retriever = retrieval_deps.retriever
        else:
            generation_deps = build_real_deps(config)
            if generation_deps.mode != "real":
                raise ValueError(
                    "evaluation run resolved to fixture dependencies; pass --fixture "
                    "explicitly for an engineering fixture run"
                )
            retriever = generation_deps.retriever

    profile_provider = None
    generator = None
    if manifest.execution_mode is ExecutionMode.RETRIEVAL_AND_GENERATION:
        if generation_deps is None:
            raise RuntimeError("generation dependencies were not constructed")
        generator = generation_deps.generator
        level = StudentLevel(args.profile)

        def profile_provider(sample: GoldSample) -> StudentProfile:
            del sample
            return generation_deps.profile_provider.get(level)

    results = run_batch(
        gold,
        manifest,
        retriever,
        generator=generator,
        profile_provider=profile_provider,
        output_path=args.output,
        resume=args.resume,
        require_generation_trace=not args.allow_synthetic_trace,
    )
    write_manifest(manifest, manifest_path)
    print(
        json.dumps(
            {
                "run_file": str(args.output),
                "manifest": str(manifest_path),
                "count": len(results),
            }
        )
    )
    return 0


def _score_command(args: argparse.Namespace) -> int:
    if not args.gold.is_file():
        raise FileNotFoundError(f"Gold sample file not found: {args.gold}")
    if not args.runs.is_file():
        raise FileNotFoundError(f"run results file not found: {args.runs}")
    if not args.mapping.is_file():
        raise FileNotFoundError(f"mapping file not found: {args.mapping}")
    if args.document is not None and not args.document.is_file():
        raise FileNotFoundError(f"prepared document not found: {args.document}")
    if args.manifest is not None and not args.manifest.is_file():
        raise FileNotFoundError(f"run manifest not found: {args.manifest}")
    manifest = None
    if args.manifest:
        manifest = RunManifest.model_validate_json(
            args.manifest.read_text(encoding="utf-8")
        )
    k_values = (
        _int_values(args.k_values)
        if args.k_values is not None
        else (manifest.k_values if manifest is not None else [])
    )
    if not k_values:
        raise ValueError("score requires --k-values or --manifest")
    prepared_corpus = None
    formal = manifest is not None and manifest.reportable
    if formal:
        if args.document is None:
            raise ValueError("formal score requires --document and a prepared corpus manifest")
        # Reject raw M3 files before mapping or run-result processing.
        load_normalized_gold(args.gold)
        prepared_corpus = load_prepared_corpus(args.document, args.corpus_manifest)
        gold = load_normalized_gold(args.gold, document=prepared_corpus.document)
        _assert_gold_matches_prepared_corpus(
            gold,
            corpus_version=prepared_corpus.corpus_version,
            parser_version=prepared_corpus.document.parser_version,
        )
    else:
        documents = None
        chapter_documents = None
        if args.document is not None:
            document = load_openstax_document(args.document)
            documents = {document.document_id: document.text}
            chapter_documents = _chapter_documents(document)
        gold = load_gold_samples(
            args.gold,
            documents=documents,
            chapter_documents=chapter_documents,
        )
    runs = load_run_results(args.runs)
    mappings = load_mappings(args.mapping)
    if prepared_corpus is not None:
        validate_artifact_compatibility(
            gold,
            mappings,
            manifest=manifest,
            question_ids={result.question_id for result in runs},
            prepared_corpus_version=prepared_corpus.corpus_version,
        )
    scored = score_saved_run(
        gold,
        runs,
        mappings,
        k_values=k_values,
        top_k=manifest.top_k if manifest is not None else None,
        extensions=(
            AnswerCitationScorer(
                mappings,
                expected_split=manifest.split if manifest is not None else None,
                dataset_version=manifest.dataset_version if manifest is not None else None,
                expected_mode=manifest.retrieval_mode if manifest is not None else None,
                expected_condition=(
                    manifest.condition_id if manifest is not None else None
                ),
            ),
        ),
        manifest=manifest,
    )
    if args.output:
        aggregate_only = {
            **scored,
            "extensions": {
                name: {
                    key: value
                    for key, value in extension_result.items()
                    if key != "records"
                }
                for name, extension_result in scored["extensions"].items()
            },
        }
        encoded = json.dumps(aggregate_only, indent=2, ensure_ascii=False)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + "\n", encoding="utf-8")
    else:
        print(json.dumps(scored, indent=2, ensure_ascii=False))
    if args.scores_output:
        rows = scored["retrieval"]["retrieval_scores"]
        args.scores_output.parent.mkdir(parents=True, exist_ok=True)
        args.scores_output.write_text(
            "".join(
                json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
                for row in rows
            ),
            encoding="utf-8",
        )
    if args.answer_citation_output_dir:
        write_answer_citation_reports(
            scored["extensions"]["answer_citation"],
            args.answer_citation_output_dir,
        )
    return 0


def _normalize_gold_command(args: argparse.Namespace) -> int:
    if not args.gold.is_file():
        raise FileNotFoundError(f"Gold sample file not found: {args.gold}")
    if not args.document.is_file():
        raise FileNotFoundError(f"prepared document not found: {args.document}")
    corpus = load_prepared_corpus(args.document, args.corpus_manifest)
    raw_gold = load_gold_samples(
        args.gold,
        chapter_documents=_chapter_documents(corpus.document),
    )
    normalized, report = normalize_gold_samples(raw_gold, corpus)
    write_normalized_gold(normalized, report, args.output)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "corpus_version": corpus.corpus_version,
                "total_spans": report.total_spans,
                "resolved": report.resolved,
                "stale": report.stale,
                "ambiguous": report.ambiguous,
                "diagnostics": dict(report.diagnostics),
            },
            ensure_ascii=False,
        )
    )
    return 0


def _report_extension_command(args: argparse.Namespace) -> int:
    role_paths = (args.role_manifest, args.role_gold, args.role_mapping)
    if any(path is not None for path in role_paths) and not all(
        path is not None for path in role_paths
    ):
        raise ValueError(
            "Role provenance requires --role-manifest, --role-gold, and "
            "--role-mapping together"
        )
    role_provenance = None
    if args.role_manifest is not None:
        corpus_record_ids = None
        if args.role_records is not None:
            corpus_record_ids = set()
            with args.role_records.open(encoding="utf-8") as stream:
                for line_number, line in enumerate(stream, start=1):
                    if not line.strip():
                        continue
                    payload = json.loads(line)
                    if not isinstance(payload, dict):
                        raise ValueError(
                            f"{args.role_records}:{line_number}: expected an object"
                        )
                    chunk_id = payload.get("chunk_id")
                    if not isinstance(chunk_id, str) or not chunk_id.strip():
                        raise ValueError(
                            f"{args.role_records}:{line_number}: missing chunk_id"
                        )
                    corpus_record_ids.add(chunk_id)
        question_reference_pairs = None
        if args.role_question_references is not None:
            question_reference_pairs = set()
            with args.role_question_references.open(encoding="utf-8") as stream:
                for line_number, line in enumerate(stream, start=1):
                    if not line.strip():
                        continue
                    payload = json.loads(line)
                    if not isinstance(payload, dict):
                        raise ValueError(
                            f"{args.role_question_references}:{line_number}: "
                            "expected an object"
                        )
                    question_id = payload.get("question_id")
                    chunk_id = payload.get("chunk_id")
                    if not isinstance(question_id, str) or not question_id.strip():
                        raise ValueError(
                            f"{args.role_question_references}:{line_number}: "
                            "missing question_id"
                        )
                    if not isinstance(chunk_id, str) or not chunk_id.strip():
                        raise ValueError(
                            f"{args.role_question_references}:{line_number}: "
                            "missing chunk_id"
                        )
                    pair = (question_id, chunk_id)
                    if pair in question_reference_pairs:
                        raise ValueError(
                            f"{args.role_question_references}:{line_number}: "
                            "duplicate question/chunk relationship"
                        )
                    question_reference_pairs.add(pair)
        role_provenance = audit_role_label_provenance(
            args.role_manifest,
            load_gold_samples(args.role_gold),
            load_mappings(args.role_mapping),
            corpus_record_ids=corpus_record_ids,
            question_reference_pairs=question_reference_pairs,
        )
    paths = write_extension_reports(
        args.scores,
        args.contexts,
        args.output_dir,
        ratings_path=args.ratings,
        rating_key_path=args.rating_key,
        rating_rubric_path=args.rating_rubric,
        rating_submission_manifest_path=args.rating_submission_manifest,
        role_provenance=role_provenance,
        allow_incomplete=args.allow_incomplete,
    )
    print(
        json.dumps(
            {name: str(path) for name, path in paths.items()},
            ensure_ascii=False,
        )
    )
    return 0


def _prepare_blind_ratings_command(args: argparse.Namespace) -> int:
    runs = []
    seen_run_ids: set[str] = set()
    for path in args.runs:
        for run in load_run_results(path):
            if run.run_id in seen_run_ids:
                raise ValueError(
                    f"duplicate run_id across blind-rating inputs: {run.run_id}"
                )
            seen_run_ids.add(run.run_id)
            runs.append(run)
    paths = write_blind_rating_materials(
        runs,
        load_gold_samples(args.gold),
        load_experiment_conditions(args.contexts),
        args.output_dir,
        seed=args.seed,
    )
    print(
        json.dumps(
            {name: str(path) for name, path in paths.items()},
            ensure_ascii=False,
        )
    )
    return 0


def _seal_blind_ratings_command(args: argparse.Namespace) -> int:
    path = seal_blind_rating_submission(
        args.ratings,
        args.rating_key,
        args.rating_rubric,
        args.output,
    )
    print(json.dumps({"rating_submission_manifest": str(path)}, ensure_ascii=False))
    return 0


def _prepare_corpus_command(args: argparse.Namespace) -> int:
    corpus = load_openstax_archive(args.archive, chapters=args.chapters)
    paths = write_prepared_corpus(corpus, args.output_dir)
    print(
        json.dumps(
            {
                "corpus_version": corpus.corpus_version,
                "chapter_count": len(corpus.document.chapters),
                "character_count": len(corpus.document.text),
                "block_count": len(corpus.document.blocks),
                **paths,
            },
            ensure_ascii=False,
        )
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "run":
            return _run_command(args)
        if args.command == "score":
            return _score_command(args)
        if args.command == "report-extension":
            return _report_extension_command(args)
        if args.command == "prepare-blind-ratings":
            return _prepare_blind_ratings_command(args)
        if args.command == "seal-blind-ratings":
            return _seal_blind_ratings_command(args)
        if args.command == "normalize-gold":
            return _normalize_gold_command(args)
        return _prepare_corpus_command(args)
    except Exception as exc:
        print(f"cs30-evaluate: error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
