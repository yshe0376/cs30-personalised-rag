"""Configuration semantics for the v2 corpus mode."""

from __future__ import annotations

from pathlib import Path

import pytest

from cs30.v2.catalog import REQUIRED_TEXTBOOK_IDS
from cs30.v2.config import V2Config, load_v2_config


def test_development_config_uses_versioned_v2_output_and_separate_corpus_mode() -> None:
    config = load_v2_config("development")

    assert config.environment == "development"
    assert config.corpus_mode == "development"
    assert config.required_textbook_ids == REQUIRED_TEXTBOOK_IDS
    assert "data/index" not in str(config.output_dir)
    assert config.index_dir == config.output_dir / "index"


@pytest.mark.parametrize(
    "required_textbook_ids",
    [
        ("one", "two"),
        REQUIRED_TEXTBOOK_IDS[:-1],
        tuple(reversed(REQUIRED_TEXTBOOK_IDS)),
        (*REQUIRED_TEXTBOOK_IDS, "ck12_extra"),
    ],
)
def test_profile_must_name_exactly_the_catalogue_set(
    required_textbook_ids: tuple[str, ...],
) -> None:
    with pytest.raises(ValueError, match="catalogue's required set"):
        V2Config(
            environment="staging",
            corpus_mode="official",
            corpus_version="2.0.0-rc.1",
            required_textbook_ids=required_textbook_ids,
            output_dir=Path("artifacts/v2/test"),
        )


def test_config_rejects_fixture_mode_in_official_mode() -> None:
    with pytest.raises(ValueError, match="fixture_mode"):
        V2Config(
            environment="staging",
            corpus_mode="official",
            corpus_version="2.0.0-rc.1",
            required_textbook_ids=REQUIRED_TEXTBOOK_IDS,
            output_dir=Path("artifacts/v2/test"),
            fixture_mode=True,
        )


def test_config_rejects_v1_output_path() -> None:
    with pytest.raises(ValueError, match="v2 output"):
        V2Config(
            environment="development",
            corpus_mode="development",
            corpus_version="2.0.0-dev.1",
            required_textbook_ids=REQUIRED_TEXTBOOK_IDS,
            output_dir=Path("data/index"),
        )


def test_config_rejects_v2_substrings_and_parent_escape_paths(tmp_path: Path) -> None:
    for output_dir in (
        tmp_path / "capstone-v2-m1-three-textbooks" / "artifacts" / "w5" / "m5_latest",
        tmp_path / "artifacts" / "v2x_backup" / ".." / "w5",
    ):
        with pytest.raises(ValueError, match="v2 output"):
            V2Config(
                environment="development",
                corpus_mode="development",
                corpus_version="2.0.0-dev.1",
                required_textbook_ids=REQUIRED_TEXTBOOK_IDS,
                output_dir=output_dir,
            )


def test_config_reads_the_chunk_configuration() -> None:
    config = load_v2_config("development")

    assert config.chunk_config == {"tokenizer_name": "unicode-wordpunct-v1"}
