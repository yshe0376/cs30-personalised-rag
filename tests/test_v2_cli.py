"""CLI exit-code and output semantics for the v2 M1 entry point."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from cs30.v2.catalog import REQUIRED_TEXTBOOK_IDS

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


def test_cli_official_refuses_fixture_provider_until_real_providers_are_configured(
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
            *sum((["--input", value] for value in write_inputs(tmp_path, 2)), []),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "REAL_BUILD_NOT_CONFIGURED" in result.stderr
    assert not output_dir.exists()


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
