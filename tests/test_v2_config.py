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


def test_official_mode_requires_exactly_three_ids() -> None:
    with pytest.raises(ValueError, match="exactly three"):
        V2Config(
            environment="staging",
            corpus_mode="official",
            corpus_version="2.0.0-rc.1",
            required_textbook_ids=("one", "two"),
            output_dir=Path("artifacts/v2/test"),
        )


def test_config_does_not_treat_fixture_mode_as_official_mode() -> None:
    config = V2Config(
        environment="staging",
        corpus_mode="official",
        corpus_version="2.0.0-rc.1",
        required_textbook_ids=REQUIRED_TEXTBOOK_IDS,
        output_dir=Path("artifacts/v2/test"),
        fixture_mode=True,
    )

    assert config.fixture_mode is True
    assert config.corpus_mode == "official"


def test_config_rejects_v1_output_path() -> None:
    with pytest.raises(ValueError, match="v2 output"):
        V2Config(
            environment="development",
            corpus_mode="development",
            corpus_version="2.0.0-dev.1",
            required_textbook_ids=REQUIRED_TEXTBOOK_IDS,
            output_dir=Path("data/index"),
        )
