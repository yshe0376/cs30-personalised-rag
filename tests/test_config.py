import os

import pytest

import cs30.config as config_module
from cs30.config import load_config
from cs30.errors import ConfigError


def test_development_config_is_read_from_toml() -> None:
    config = load_config("development")

    assert config.environment == "development"
    assert config.log_level == "DEBUG"
    assert config.fixture_mode is True
    assert config.retrieval.top_k == 3


def test_staging_config_disables_fixture_mode() -> None:
    config = load_config("staging")

    assert config.fixture_mode is False
    assert config.retrieval.top_k == 5


def test_environment_variables_override_the_file(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CS30_TOP_K", "11")
    monkeypatch.setenv("CS30_LOG_LEVEL", "WARNING")
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")

    config = load_config("development")

    assert config.retrieval.top_k == 11
    assert config.log_level == "WARNING"
    assert config.generation.provider == "anthropic"


def test_unknown_environment_raises_config_error() -> None:
    with pytest.raises(ConfigError, match="no configuration file"):
        load_config("does-not-exist")


def test_bundled_staging_config_is_available_outside_checkout(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """A wheel must not silently fall back to development fixture defaults."""

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        config_module,
        "__file__",
        str(tmp_path / "site-packages" / "cs30" / "config.py"),
    )

    config = load_config("staging")

    assert config.environment == "staging"
    assert config.fixture_mode is False
    assert config.retrieval.top_k == 5


def test_invalid_fixture_mode_environment_value_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CS30_FIXTURE_MODE", "tru")

    with pytest.raises(ConfigError, match="CS30_FIXTURE_MODE"):
        load_config("development")


def test_local_dotenv_supplies_defaults_without_overriding_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    (tmp_path / ".env").write_text(
        "CS30_LOG_LEVEL=WARNING\nCS30_TOP_K=9\nLLM_PROVIDER='fixture-from-dotenv'\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CS30_TOP_K", "7")

    try:
        config = load_config("development")

        assert config.log_level == "WARNING"
        assert config.retrieval.top_k == 7
        assert config.generation.provider == "fixture-from-dotenv"
    finally:
        os.environ.pop("CS30_LOG_LEVEL", None)
        os.environ.pop("LLM_PROVIDER", None)
