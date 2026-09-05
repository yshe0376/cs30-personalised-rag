"""Configuration loading: TOML file, then environment overrides.

Precedence, lowest to highest: built-in defaults, ``configs/<env>.toml``,
``CS30_*`` / ``LLM_*`` environment variables.
"""

from __future__ import annotations

import os
import tomllib
from importlib.resources import files
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from cs30.contracts import RetrievalMode
from cs30.errors import ConfigError

DEFAULT_ENVIRONMENT = "development"


def _load_local_env(path: Path | None = None) -> None:
    """Load simple KEY=VALUE entries from an ignored local ``.env`` file."""

    candidate = path or (Path.cwd() / ".env")
    if not candidate.is_file():
        return
    for raw_line in candidate.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        os.environ.setdefault(key, value)


class RetrievalConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    top_k: int = Field(default=5, gt=0)
    index_type: str = "IndexFlatIP"
    mode: RetrievalMode = RetrievalMode.HYBRID
    index_dir: str = "data/index"
    rrf_k: int = Field(default=60, gt=0)
    rrf_input_top_k: int = Field(default=20, gt=0)
    bm25_min_score: float = Field(default=0.0, ge=0.0)
    dense_min_similarity: float | None = Field(
        default=None,
        ge=-1.0,
        le=1.0,
    )


class GenerationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = "mock"
    model: str | None = None
    temperature: float = Field(default=0.0, ge=0.0)
    max_retries: int = Field(default=2, ge=0)


class AppConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    environment: str = DEFAULT_ENVIRONMENT
    log_level: str = "INFO"
    fixture_mode: bool = True
    retrieval: RetrievalConfig = Field(default_factory=RetrievalConfig)
    generation: GenerationConfig = Field(default_factory=GenerationConfig)


def config_dir() -> Path | None:
    """Locate an external override or the configuration bundled with the package."""

    override = os.environ.get("CS30_CONFIG_DIR")
    if override:
        path = Path(override)
        if not path.is_dir():
            raise ConfigError(f"CS30_CONFIG_DIR is not a directory: {path}")
        return path
    candidates = (
        Path.cwd() / "configs",
        Path(str(files("cs30").joinpath("configs"))),
    )
    return next((c for c in candidates if c.is_dir() and any(c.glob("*.toml"))), None)


def _read_toml(environment: str) -> dict:
    directory = config_dir()
    if directory is None:
        raise ConfigError("no bundled configuration directory is available")
    path = directory / f"{environment}.toml"
    if not path.is_file():
        raise ConfigError(f"no configuration file for environment {environment!r}: {path}")
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"invalid TOML in {path}: {exc}") from exc


def _apply_env_overrides(payload: dict) -> dict:
    def scalar(env_name: str, *keys: str) -> None:
        raw = os.environ.get(env_name)
        if raw is None or raw == "":
            return
        target = payload
        for key in keys[:-1]:
            target = target.setdefault(key, {})
        target[keys[-1]] = raw

    scalar("CS30_LOG_LEVEL", "log_level")
    scalar("CS30_TOP_K", "retrieval", "top_k")
    scalar("CS30_RETRIEVAL_MODE", "retrieval", "mode")
    scalar("CS30_INDEX_DIR", "retrieval", "index_dir")
    scalar("CS30_RRF_K", "retrieval", "rrf_k")
    scalar("CS30_RRF_INPUT_TOP_K", "retrieval", "rrf_input_top_k")
    scalar("CS30_BM25_MIN_SCORE", "retrieval", "bm25_min_score")
    scalar(
    "CS30_DENSE_MIN_SIMILARITY",
    "retrieval",
    "dense_min_similarity",
    )
    scalar("LLM_PROVIDER", "generation", "provider")
    scalar("LLM_MODEL", "generation", "model")

    fixture_mode = os.environ.get("CS30_FIXTURE_MODE")
    if fixture_mode:
        normalised = fixture_mode.strip().lower()
        true_values = {"1", "true", "yes", "on"}
        false_values = {"0", "false", "no", "off"}
        if normalised in true_values:
            payload["fixture_mode"] = True
        elif normalised in false_values:
            payload["fixture_mode"] = False
        else:
            raise ConfigError(
                "CS30_FIXTURE_MODE must be one of: "
                "1, true, yes, on, 0, false, no, off"
            )
    return payload


def load_config(environment: str | None = None) -> AppConfig:
    """Load configuration for an environment.

    Precedence for the environment name: argument, then ``CS30_ENV``, then
    ``development``.
    """

    _load_local_env()
    resolved = environment or os.environ.get("CS30_ENV") or DEFAULT_ENVIRONMENT
    payload = _read_toml(resolved)
    payload.setdefault("environment", resolved)
    payload = _apply_env_overrides(payload)
    try:
        return AppConfig.model_validate(payload)
    except ValidationError as exc:
        raise ConfigError(f"invalid configuration for environment {resolved!r}: {exc}") from exc
