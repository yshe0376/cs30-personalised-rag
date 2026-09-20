"""Configuration for the isolated v2 corpus build path."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from cs30.v2.catalog import REQUIRED_TEXTBOOK_IDS


class V2Config(BaseModel):
    model_config = ConfigDict(extra="forbid")

    environment: Literal["development", "staging", "production"]
    corpus_mode: Literal["development", "official"]
    corpus_version: str = Field(min_length=1)
    required_textbook_ids: tuple[str, ...]
    output_dir: Path
    fixture_mode: bool = False
    chunk_config: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_v2_boundary(self) -> V2Config:
        if len(self.required_textbook_ids) != 3:
            raise ValueError("required_textbook_ids must contain exactly three IDs")
        if len(set(self.required_textbook_ids)) != 3:
            raise ValueError("required_textbook_ids must be unique")
        normalised = self.output_dir.as_posix().casefold()
        if "data/index" in normalised or "/v1" in normalised:
            raise ValueError("output_dir must be a versioned v2 output directory")
        if "v2" not in normalised:
            raise ValueError("output_dir must be a versioned v2 output directory")
        return self

    @property
    def index_dir(self) -> Path:
        return self.output_dir / "index"


def _config_path(profile: str, config_dir: Path | None = None) -> Path:
    directory = config_dir
    if directory is None:
        override = os.environ.get("CS30_V2_CONFIG_DIR")
        directory = Path(override) if override else Path(__file__).parent / "configs"
    path = directory / f"{profile}.toml"
    if not path.is_file():
        raise ValueError(f"no v2 configuration profile: {path}")
    return path


def load_v2_config(profile: str, *, config_dir: Path | None = None) -> V2Config:
    path = _config_path(profile, config_dir)
    with path.open("rb") as handle:
        payload = tomllib.load(handle)
    corpus = payload.get("corpus")
    if not isinstance(corpus, dict):
        raise ValueError(f"v2 config has no [corpus] section: {path}")
    values = {
        "environment": payload.get("environment", profile),
        "fixture_mode": payload.get("fixture_mode", False),
        **corpus,
    }
    if "mode" in values:
        values.setdefault("corpus_mode", values["mode"])
        values.pop("mode")
    values["required_textbook_ids"] = tuple(values["required_textbook_ids"])
    values["output_dir"] = Path(values["output_dir"])
    return V2Config.model_validate(values)


def default_v2_config() -> V2Config:
    return V2Config(
        environment="development",
        corpus_mode="development",
        corpus_version="2.0.0-dev.1",
        required_textbook_ids=REQUIRED_TEXTBOOK_IDS,
        output_dir=Path("artifacts/v2/three-textbooks/2.0.0-dev.1"),
        fixture_mode=True,
    )
