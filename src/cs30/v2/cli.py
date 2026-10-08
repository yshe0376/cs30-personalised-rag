"""Command-line entry point for the v2 M1 corpus builder."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from cs30.v2.catalog import get_textbook_spec
from cs30.v2.chunking import V2BlockChunker, V2ProductionChunker
from cs30.v2.config import V2Config, load_v2_config
from cs30.v2.errors import BuildGateError, InputError, V2Error
from cs30.v2.fixture import TextFixtureParser
from cs30.v2.indexing import build_faiss_index_builder
from cs30.v2.ingest import build_parser_registry
from cs30.v2.pipeline import (
    BuildDeps,
    MappingParserRegistry,
    MultiTextbookBuildSpec,
    run_build_pipeline,
)
from cs30.v2.ports import TextbookInput
from cs30.v2.sources import asset_name, parsed_file_name


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        default="development",
        help="v2 profile: development or staging",
    )
    parser.add_argument("--mode", choices=["development", "official"], default=None)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument(
        "--corpus-version",
        default=None,
        help=(
            "corpus_version written to the manifest; set it to reproduce a "
            "delivered corpus byte for byte (the profile decides by default)"
        ),
    )
    parser.add_argument(
        "--source-format",
        choices=["parsed", "raw"],
        default=None,
        help=(
            "real builds: read M2's pinned parse (parsed) or re-parse the pinned "
            "PDFs (raw); the profile decides by default"
        ),
    )
    parser.add_argument(
        "--sources-dir",
        type=Path,
        default=None,
        help=(
            "where the pinned sources are installed (real builds; default "
            "data/parsed/v2 for parsed, data/raw/v2 for raw)"
        ),
    )
    parser.add_argument(
        "--embedding-model",
        default=None,
        help="sentence-transformers model for the dense index (real builds)",
    )
    parser.add_argument(
        "--input",
        action="append",
        default=[],
        metavar="TEXTBOOK_ID=PATH",
        help=(
            "repeat once per textbook; fixture builds take UTF-8 text files and "
            "real builds take M2's JSON or PDFs, overriding the sources directory"
        ),
    )
    return parser


def _parse_input(value: str) -> tuple[str, Path]:
    textbook_id, separator, raw_path = value.partition("=")
    if not separator or not textbook_id or not raw_path:
        raise InputError(
            f"--input must use TEXTBOOK_ID=PATH: {value}",
            code="INVALID_INPUT_SPEC",
        )
    return textbook_id, Path(raw_path)


def _config_with_overrides(args: argparse.Namespace) -> V2Config:
    config = load_v2_config(args.config)
    updates = {}
    if args.mode is not None:
        updates["corpus_mode"] = args.mode
    if args.output_dir is not None:
        updates["output_dir"] = args.output_dir
    if args.corpus_version is not None:
        updates["corpus_version"] = args.corpus_version
    if args.source_format is not None:
        updates["source_format"] = args.source_format
    if args.sources_dir is not None:
        updates["sources_dir"] = args.sources_dir
    if args.embedding_model is not None:
        updates["embedding_model"] = args.embedding_model
    if not updates:
        return config
    return V2Config.model_validate({**config.model_dump(), **updates})


def _fixture_build(
    config: V2Config, raw_inputs: list[str]
) -> tuple[list[TextbookInput], BuildDeps]:
    """Synthetic text inputs: the catalogue's real-source pins do not apply."""

    if not raw_inputs:
        raise InputError("at least one --input is required", code="INPUT_REQUIRED")
    inputs: list[TextbookInput] = []
    parsers: dict[str, object] = {}
    for raw_input in raw_inputs:
        textbook_id, source_path = _parse_input(raw_input)
        spec = _spec(textbook_id)
        inputs.append(
            TextbookInput(
                textbook_id=textbook_id,
                source_path=source_path,
                # This is a catalog-defined logical name, not a local filename.
                source_name=spec.source_name,
                source_uri=spec.source_uri,
                source_version=spec.source_version,
                selected_chapters=(),
                expected_source_sha256=None,
            )
        )
        parsers[textbook_id] = TextFixtureParser(spec)
    return inputs, BuildDeps(
        parser_registry=MappingParserRegistry(parsers),
        chunker=V2BlockChunker.from_config(config.chunk_config),
    )


def _real_build(
    config: V2Config, raw_inputs: list[str]
) -> tuple[list[TextbookInput], BuildDeps]:
    """Build M2's pinned parse or PDFs with the production M4 chunker."""

    overrides = dict(_parse_input(raw_input) for raw_input in raw_inputs)
    unknown = set(overrides) - set(config.required_textbook_ids)
    if unknown:
        raise InputError(
            f"--input names textbooks outside the catalogue set: {sorted(unknown)}",
            code="UNKNOWN_TEXTBOOK",
        )
    parsed = config.source_format == "parsed"
    inputs: list[TextbookInput] = []
    for textbook_id in config.required_textbook_ids:
        spec = _spec(textbook_id)
        file_name = parsed_file_name(textbook_id) if parsed else asset_name(textbook_id)
        source_path = overrides.get(textbook_id, config.resolved_sources_dir / file_name)
        inputs.append(
            TextbookInput(
                textbook_id=textbook_id,
                source_path=source_path,
                source_name=spec.source_name,
                source_uri=spec.source_uri,
                source_version=spec.source_version,
                selected_chapters=spec.selected_chapters,
                expected_source_sha256=spec.expected_source_sha256,
                source_format=config.source_format,
                expected_parsed_sha256=spec.expected_parsed_sha256 if parsed else None,
            )
        )
    index_builder = (
        build_faiss_index_builder(
            config.embedding_model,
            revision=config.embedding_revision,
            batch_size=config.index_batch_size,
            max_seq_length=config.embedding_max_seq_length,
        )
        if config.embedding_model
        else None
    )
    return inputs, BuildDeps(
        parser_registry=build_parser_registry(
            config.required_textbook_ids, source_format=config.source_format
        ),
        chunker=V2ProductionChunker.from_config(config.chunk_config),
        index_builder=index_builder,
    )


def _spec(textbook_id: str):
    try:
        return get_textbook_spec(textbook_id)
    except ValueError as exc:
        raise InputError(str(exc), code="UNKNOWN_TEXTBOOK") from exc


def run(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = _config_with_overrides(args)
        build = _fixture_build if config.fixture_mode else _real_build
        inputs, deps = build(config, args.input)

        outcome = run_build_pipeline(
            inputs,
            deps,
            MultiTextbookBuildSpec(
                corpus_version=config.corpus_version,
                required_textbook_ids=config.required_textbook_ids,
                mode=config.corpus_mode,
                environment=config.environment,
                output_dir=config.output_dir,
            ),
        )
    except BuildGateError as exc:
        print(f"{exc.code}: {exc}; diagnostics={exc.report_path}", file=sys.stderr)
        return exc.exit_code
    except InputError as exc:
        print(f"{exc.code}: {exc}", file=sys.stderr)
        return exc.exit_code
    except V2Error as exc:
        print(f"{exc.code}: {exc}", file=sys.stderr)
        return exc.exit_code
    except (ValueError, OSError) as exc:
        print(f"CONFIG_OR_INPUT_ERROR: {exc}", file=sys.stderr)
        return 2

    assert outcome.manifest is not None
    print(
        json.dumps(
            {
                "manifest_hash": outcome.manifest.manifest_hash,
                "corpus_hash": outcome.manifest.corpus_hash,
                "manifest_path": str(outcome.manifest_path),
                "report_path": str(outcome.report_path),
                "reportable": outcome.manifest.reportable,
                "record_count": outcome.manifest.record_count,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0
