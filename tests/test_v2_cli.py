"""CLI exit-code and output semantics for the v2 M1 entry point."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from cs30.v2.catalog import REQUIRED_TEXTBOOK_IDS
from cs30.v2.cli import _real_build
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


def test_cli_official_stops_on_the_fixture_chunker_until_m4_provides_one(
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
    assert "FIXTURE_NOT_ALLOWED" in result.stderr
    assert not output_dir.exists()


def test_real_build_reads_pinned_pdfs_and_configures_the_index(tmp_path: Path) -> None:
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
        tmp_path / "sources" / f"{textbook_id}.pdf"
        for textbook_id in REQUIRED_TEXTBOOK_IDS
    ]
    # Real builds carry the catalogue's pins and chapter selection.
    assert all(input.expected_source_sha256 for input in inputs)
    assert inputs[0].selected_chapters == tuple(str(n) for n in range(1, 35))
    assert type(deps.parser_registry.parser_for(REQUIRED_TEXTBOOK_IDS[0])).__name__ == (
        "OpenStaxPdfParser"
    )
    assert deps.index_builder is not None
    assert deps.index_builder.batch_size == 8
    # The model is only named here; it is loaded on the first build.
    assert deps.index_builder._encoder is None


def test_real_build_without_an_embedding_model_configures_no_index(tmp_path: Path) -> None:
    config = V2Config.model_validate(
        {
            **load_v2_config("real-development").model_dump(),
            "output_dir": tmp_path / "artifacts" / "v2" / "real-no-index",
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
