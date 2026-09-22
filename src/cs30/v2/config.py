"""Configuration for the isolated v2 corpus build path."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from cs30.v2.catalog import REQUIRED_TEXTBOOK_IDS


def validate_v2_output_dir(output_dir: Path) -> None:
    """Require a resolved path below an exact ``artifacts/v2`` directory."""

    resolved = output_dir.resolve()
    parts = tuple(part.casefold() for part in resolved.parts)
    if any(
        left == "data" and right == "index"
        for left, right in zip(parts, parts[1:], strict=False)
    ) or "v1" in parts:
        raise ValueError("output_dir must be a v2 output directory, not v1 or legacy data/index")

    v2_root_index = next(
        (
            index
            for index, (left, right) in enumerate(
                zip(parts, parts[1:], strict=False)
            )
            if left == "artifacts" and right == "v2"
        ),
        None,
    )
    if v2_root_index is None or resolved == Path(*resolved.parts[: v2_root_index + 2]):
        raise ValueError("output_dir must be a versioned v2 output directory below artifacts/v2")


class V2Config(BaseModel):
    model_config = ConfigDict(extra="forbid")

    environment: Literal["development", "staging", "production"]
    corpus_mode: Literal["development", "official"]
    corpus_version: str = Field(min_length=1)
    required_textbook_ids: tuple[str, ...]
    output_dir: Path
    fixture_mode: bool = False
    chunk_config: dict[str, str] = Field(default_factory=dict)
    # Where `scripts/install_v2_sources.py` puts the pinned textbook PDFs.
    sources_dir: Path = Path("data/raw/v2")
    # No model configured means no index: an official build then stops with
    # INDEX_BUILDER_NOT_CONFIGURED instead of publishing a corpus without one.
    embedding_model: str | None = None
    embedding_revision: str | None = None
    index_batch_size: int = Field(default=32, ge=1)

    @model_validator(mode="after")
    def validate_v2_boundary(self) -> V2Config:
        # The profile must name exactly the catalogue's frozen set, in its order,
        # so a TOML edit cannot quietly add, drop, or reorder a textbook.
        if tuple(self.required_textbook_ids) != REQUIRED_TEXTBOOK_IDS:
            raise ValueError(
                "required_textbook_ids must equal the catalogue's required set: "
                f"{list(REQUIRED_TEXTBOOK_IDS)}"
            )
        if self.corpus_mode == "official" and self.fixture_mode:
            raise ValueError("official mode cannot run with fixture_mode enabled")
        validate_v2_output_dir(self.output_dir)
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
    if "sources_dir" in values:
        values["sources_dir"] = Path(values["sources_dir"])
    return V2Config.model_validate(values)


def default_v2_config() -> V2Config:
    return V2Config(
        environment="development",
        corpus_mode="development",
        corpus_version="2.0.0-dev.1",
        required_textbook_ids=REQUIRED_TEXTBOOK_IDS,
        output_dir=Path("artifacts/v2/textbooks/2.0.0-dev.1"),
        fixture_mode=True,
    )
