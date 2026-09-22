"""Command-line entry point for the v2 M1 corpus builder."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from cs30.v2.catalog import get_textbook_spec
from cs30.v2.chunking import V2BlockChunker
from cs30.v2.config import V2Config, load_v2_config
from cs30.v2.errors import BuildGateError, InputError, V2Error
from cs30.v2.fixture import TextFixtureParser
from cs30.v2.pipeline import (
    BuildDeps,
    MappingParserRegistry,
    MultiTextbookBuildSpec,
    run_build_pipeline,
)
from cs30.v2.ports import TextbookInput


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
        "--input",
        action="append",
        default=[],
        metavar="TEXTBOOK_ID=PATH",
        help="repeat once per textbook; M1 accepts UTF-8 synthetic text inputs",
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
    if not updates:
        return config
    return V2Config.model_validate({**config.model_dump(), **updates})


def run(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = _config_with_overrides(args)
        if not config.fixture_mode:
            raise InputError(
                "real v2 parser and chunker providers are not configured for this CLI",
                code="REAL_BUILD_NOT_CONFIGURED",
            )
        if not args.input:
            raise InputError("at least one --input is required", code="INPUT_REQUIRED")

        inputs: list[TextbookInput] = []
        parsers = {}
        for raw_input in args.input:
            textbook_id, source_path = _parse_input(raw_input)
            try:
                spec = get_textbook_spec(textbook_id)
            except ValueError as exc:
                raise InputError(str(exc), code="UNKNOWN_TEXTBOOK") from exc
            inputs.append(
                TextbookInput(
                    textbook_id=textbook_id,
                    source_path=source_path,
                    # This is a catalog-defined logical name, not a local filename.
                    source_name=spec.source_name,
                    source_uri=spec.source_uri,
                    source_version=spec.source_version,
                    # This CLI only runs fixture builds over synthetic text, so the
                    # catalog's pinned source hash and chapter selection, which
                    # describe the real textbook file, do not apply to its inputs.
                    selected_chapters=(),
                    expected_source_sha256=None,
                )
            )
            parsers[textbook_id] = TextFixtureParser(spec)

        outcome = run_build_pipeline(
            inputs,
            BuildDeps(
                parser_registry=MappingParserRegistry(parsers),
                chunker=V2BlockChunker.from_config(config.chunk_config),
            ),
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
