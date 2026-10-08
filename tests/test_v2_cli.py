"""CLI exit-code and output semantics for the v2 M1 entry point."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from cs30.v2.catalog import REQUIRED_TEXTBOOK_IDS
from cs30.v2.cli import _config_with_overrides, _real_build, build_parser
from cs30.v2.config import V2Config, load_v2_config
from cs30.v2.errors import InputError

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "build_v2_corpus.py"


def write_inputs(tmp_path: Path, count: int) -> list[str]:
    values: list[str] = []
    for index, textbook_id in enumerate(REQUIRED_TEXTBOOK_IDS[:count], start=1):
        source = tmp_path / f"book-{index}.txt"
        source.write_bytes(
            f"Book {index} explains force and motion.\n[[FORMULA:f=ma]]".encode()
        )
        values.append(f"{textbook_id}={source}")
    return values


def test_cli_builds_a_development_diagnostic_corpus(tmp_path: Path) -> None:
    output_dir = tmp_path / "artifacts" / "v2" / "cli-development"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--config",
            "development",
            "--output-dir",
            str(output_dir),
            *sum((["--input", value] for value in write_inputs(tmp_path, 3)), []),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert summary["reportable"] is False
    assert (output_dir / "records.jsonl").is_file()
    assert (output_dir / "manifest.json").is_file()


def test_cli_official_passes_the_m4_gate_and_stops_on_the_missing_provider(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "artifacts" / "v2" / "cli-official"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--config",
            "staging",
            "--output-dir",
            str(output_dir),
            "--sources-dir",
            str(tmp_path / "sources"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 4
    assert "REQUIRED_PROVIDER_MISSING" in result.stderr
    assert not output_dir.exists()


def test_real_build_reads_m2_parsed_json_and_configures_the_index(tmp_path: Path) -> None:
    config = V2Config.model_validate(
        {
            **load_v2_config("real-development").model_dump(),
            "sources_dir": tmp_path / "sources",
            "output_dir": tmp_path / "artifacts" / "v2" / "real",
            "embedding_model": "sentence-transformers/all-MiniLM-L6-v2",
            "index_batch_size": 8,
        }
    )

    inputs, deps = _real_build(config, [])

    assert [input.textbook_id for input in inputs] == list(REQUIRED_TEXTBOOK_IDS)
    assert [input.source_path for input in inputs] == [
        tmp_path / "sources" / f"{textbook_id}.json"
        for textbook_id in REQUIRED_TEXTBOOK_IDS
    ]
    # Real builds carry the catalogue's pins and chapter selection: the parse
    # is pinned by its own hash and must still name the pinned PDF.
    assert {input.source_format for input in inputs} == {"parsed"}
    assert all(input.expected_parsed_sha256 for input in inputs)
    assert all(input.expected_source_sha256 for input in inputs)
    assert inputs[0].selected_chapters == tuple(str(n) for n in range(1, 35))
    assert type(deps.parser_registry.parser_for(REQUIRED_TEXTBOOK_IDS[0])).__name__ == (
        "OpenStaxParsedParser"
    )
    assert deps.index_builder is not None
    assert deps.index_builder.batch_size == 8
    assert deps.chunker.is_fixture is False
    assert type(deps.chunker).__name__ == "V2ProductionChunker"
    # The model is only named here; it is loaded on the first build.
    assert deps.index_builder._encoder is None


def test_real_build_can_still_reparse_the_pinned_pdfs(tmp_path: Path) -> None:
    config = V2Config.model_validate(
        {
            **load_v2_config("real-development").model_dump(),
            "source_format": "raw",
            "output_dir": tmp_path / "artifacts" / "v2" / "real-raw",
        }
    )

    inputs, deps = _real_build(config, [])

    # Without an explicit sources_dir each format reads its install directory.
    assert [input.source_path for input in inputs] == [
        Path("data/raw/v2") / f"{textbook_id}.pdf" for textbook_id in REQUIRED_TEXTBOOK_IDS
    ]
    assert {input.source_format for input in inputs} == {"raw"}
    assert not any(input.expected_parsed_sha256 for input in inputs)
    assert type(deps.parser_registry.parser_for(REQUIRED_TEXTBOOK_IDS[0])).__name__ == (
        "OpenStaxPdfParser"
    )


def test_real_profiles_read_the_parsed_install_directory() -> None:
    for profile in ("real-development", "staging"):
        config = load_v2_config(profile)

        assert config.source_format == "parsed"
        assert config.resolved_sources_dir == Path("data/parsed/v2")


def test_cli_source_format_overrides_the_profile() -> None:
    args = build_parser().parse_args(
        ["--config", "real-development", "--source-format", "raw"]
    )

    config = _config_with_overrides(args)

    assert config.source_format == "raw"
    assert config.resolved_sources_dir == Path("data/raw/v2")


def test_cli_corpus_version_overrides_the_profile() -> None:
    profile = load_v2_config("real-development")
    args = build_parser().parse_args(
        ["--config", "real-development", "--corpus-version", "2.0.0-dev.m4-structure-v2"]
    )

    config = _config_with_overrides(args)

    assert config.corpus_version == "2.0.0-dev.m4-structure-v2"
    assert config.model_dump(exclude={"corpus_version"}) == profile.model_dump(
        exclude={"corpus_version"}
    )


def test_cli_rejects_an_empty_corpus_version() -> None:
    args = build_parser().parse_args(["--config", "real-development", "--corpus-version", ""])

    with pytest.raises(ValueError, match="corpus_version"):
        _config_with_overrides(args)


def test_cli_writes_the_overridden_corpus_version_to_the_manifest(tmp_path: Path) -> None:
    output_dir = tmp_path / "artifacts" / "v2" / "cli-versioned"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--config",
            "development",
            "--output-dir",
            str(output_dir),
            "--corpus-version",
            "2.0.0-dev.handoff-1",
            *sum((["--input", value] for value in write_inputs(tmp_path, 3)), []),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["corpus_version"] == "2.0.0-dev.handoff-1"


def test_real_build_without_an_embedding_model_configures_no_index(tmp_path: Path) -> None:
    config = V2Config.model_validate(
        {
            **load_v2_config("real-development").model_dump(),
            "output_dir": tmp_path / "artifacts" / "v2" / "real-no-index",
            "embedding_model": None,
        }
    )

    _, deps = _real_build(config, [])

    assert deps.index_builder is None


def test_real_build_rejects_an_input_outside_the_catalogue(tmp_path: Path) -> None:
    config = load_v2_config("real-development")

    with pytest.raises(InputError, match="outside the catalogue"):
        _real_build(config, [f"ck12_peoples_physics_basic={tmp_path / 'book.pdf'}"])


def test_cli_rejects_an_unknown_textbook_as_input_error(tmp_path: Path) -> None:
    source = tmp_path / "unknown.txt"
    source.write_bytes(b"unknown source")
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--config",
            "development",
            "--output-dir",
            str(tmp_path / "artifacts" / "v2" / "unknown"),
            "--input",
            f"unknown={source}",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "UNKNOWN_TEXTBOOK" in result.stderr


def test_cli_revalidates_an_output_override_instead_of_bypassing_config_rules(
    tmp_path: Path,
) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--config",
            "development",
            "--output-dir",
            str(tmp_path / "data" / "index"),
            "--input",
            "openstax_college_physics_2e=" + str(tmp_path / "missing.txt"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "v2 output" in result.stderr
