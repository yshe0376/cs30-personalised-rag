"""Local configuration for the API backed learning demo."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

OutputMode = Literal["json_schema", "json_object"]


class LearningConfigurationError(ValueError):
    """A local demo configuration is missing or inconsistent."""


def load_private_environment(path: Path) -> None:
    """Load a private KEY=VALUE file without ever logging or returning values."""

    if not path.is_file():
        return
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise LearningConfigurationError(
                f"Invalid private environment line {line_number}; expected KEY=VALUE"
            )
        name, value = line.split("=", 1)
        name, value = name.strip(), value.strip()
        if not name or any(
            char not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_"
            for char in name
        ):
            raise LearningConfigurationError(
                f"Invalid variable name on private environment line {line_number}"
            )
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        if value:
            os.environ.setdefault(name, value)


@dataclass(frozen=True)
class ApiRoleConfig:
    provider_name: str
    base_url: str
    model: str
    model_version: str
    api_key_env: str
    structured_output: OutputMode
    timeout_seconds: float
    max_output_tokens: int
    extra_body: dict[str, object]


@dataclass(frozen=True)
class LearningConfig:
    project_root: Path
    config_path: Path
    corpus_dir: Path
    source_topic_map_path: Path
    topic_map_path: Path
    topic_registry_path: Path
    role_manifest_path: Path
    lambda_selection_path: Path
    index_artifact_path: Path
    index_file_path: Path
    compatibility_index_dir: Path
    state_dir: Path
    preflight_report_path: Path
    question_bank_path: Path
    dense_embedding_model: str
    dense_embedding_revision: str
    query_instruction: str
    query_prompt_name: str | None
    dense_weight: float
    bm25_weight: float
    rrf_k: int
    candidate_k: int
    evidence_k: int
    minimum_topic_resolution_rate: float
    demo_topic_ids: tuple[str, ...]
    model_selection_status: Literal["provisional", "frozen"]
    live_calls_enabled: bool
    total_request_cap: int
    answer_api: ApiRoleConfig
    quiz_api: ApiRoleConfig
    verify_api: ApiRoleConfig

    @classmethod
    def load(cls, config_path: Path | None = None) -> LearningConfig:
        project_root = Path(__file__).resolve().parents[3]
        load_private_environment(project_root / ".env.learning.local")
        selected_path = config_path or Path(
            os.environ.get(
                "CS30_LEARNING_CONFIG", str(project_root / "configs" / "learning-demo.toml")
            )
        )
        selected_path = selected_path.expanduser().resolve()
        if not selected_path.is_file():
            example = project_root / "configs" / "learning-demo.example.toml"
            raise LearningConfigurationError(
                f"No local config at {selected_path}. Copy {example} to "
                f"{project_root / 'configs' / 'learning-demo.toml'} and set the asset paths."
            )
        try:
            with selected_path.open("rb") as stream:
                raw = tomllib.load(stream)
        except (OSError, tomllib.TOMLDecodeError) as exc:
            raise LearningConfigurationError(f"Cannot read demo config: {exc}") from exc

        def section(name: str) -> dict:
            value = raw.get(name)
            if not isinstance(value, dict):
                raise LearningConfigurationError(f"Missing [{name}] section")
            return value

        def path_value(values: dict, name: str) -> Path:
            value = values.get(name)
            if not isinstance(value, str) or not value.strip():
                raise LearningConfigurationError(f"Missing path setting {name!r}")
            expanded = os.path.expandvars(value.strip())
            path = Path(expanded).expanduser()
            return path.resolve() if path.is_absolute() else (project_root / path).resolve()

        assets = section("assets")
        retrieval = section("retrieval")
        demo = section("demo")
        api = section("api")

        def api_role(name: str) -> ApiRoleConfig:
            values = api.get(name)
            if not isinstance(values, dict):
                raise LearningConfigurationError(f"Missing [api.{name}] section")
            mode = values.get("structured_output")
            if mode not in {"json_schema", "json_object"}:
                raise LearningConfigurationError(
                    f"api.{name}.structured_output must be a fixed JSON mode"
                )
            role = ApiRoleConfig(
                provider_name=str(values.get("provider_name", "")).strip(),
                base_url=str(values.get("base_url", "")).strip(),
                model=str(values.get("model", "")).strip(),
                model_version=str(values.get("model_version", "")).strip(),
                api_key_env=str(values.get("api_key_env", "")).strip(),
                structured_output=mode,
                timeout_seconds=float(values.get("timeout_seconds", 120)),
                max_output_tokens=int(values.get("max_output_tokens", 2048)),
                extra_body=dict(values.get("extra_body", {})),
            )
            if not all(
                (
                    role.provider_name,
                    role.base_url,
                    role.model,
                    role.model_version,
                    role.api_key_env,
                )
            ):
                raise LearningConfigurationError(f"api.{name} has an empty required setting")
            if role.timeout_seconds <= 0 or role.max_output_tokens < 1:
                raise LearningConfigurationError(f"api.{name} has an invalid timeout/token cap")
            return role

        config = cls(
            project_root=project_root,
            config_path=selected_path,
            corpus_dir=path_value(assets, "corpus_dir"),
            source_topic_map_path=path_value(assets, "source_topic_map_path"),
            topic_map_path=path_value(assets, "topic_map_path"),
            topic_registry_path=path_value(assets, "topic_registry_path"),
            role_manifest_path=path_value(assets, "role_manifest_path"),
            lambda_selection_path=path_value(assets, "lambda_selection_path"),
            index_artifact_path=path_value(assets, "index_artifact_path"),
            index_file_path=path_value(assets, "index_file_path"),
            compatibility_index_dir=path_value(assets, "compatibility_index_dir"),
            state_dir=path_value(assets, "state_dir"),
            preflight_report_path=path_value(assets, "preflight_report_path"),
            question_bank_path=path_value(demo, "question_bank_path"),
            dense_embedding_model=str(retrieval.get("dense_embedding_model", "")),
            dense_embedding_revision=str(retrieval.get("dense_embedding_revision", "")),
            query_instruction=str(retrieval.get("query_instruction", "")),
            query_prompt_name=(
                str(retrieval["query_prompt_name"]) if retrieval.get("query_prompt_name") else None
            ),
            dense_weight=float(retrieval.get("dense_weight", -1)),
            bm25_weight=float(retrieval.get("bm25_weight", -1)),
            rrf_k=int(retrieval.get("rrf_k", 0)),
            candidate_k=int(retrieval.get("candidate_k", 0)),
            evidence_k=int(retrieval.get("evidence_k", 0)),
            minimum_topic_resolution_rate=float(demo.get("minimum_topic_resolution_rate", 0.8)),
            demo_topic_ids=tuple(str(value) for value in demo.get("topic_ids", [])),
            model_selection_status=str(api.get("model_selection_status", "provisional")),
            live_calls_enabled=bool(api.get("live_calls_enabled", False)),
            total_request_cap=int(api.get("total_request_cap", 0)),
            answer_api=api_role("answer"),
            quiz_api=api_role("quiz"),
            verify_api=api_role("verify") if "verify" in api else api_role("quiz"),
        )
        config.validate_frozen_retrieval()
        return config

    def validate_frozen_retrieval(self) -> None:
        if (self.dense_embedding_model, self.dense_embedding_revision) != (
            "Qwen/Qwen3-Embedding-0.6B",
            "97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3",
        ):
            raise LearningConfigurationError(
                "The learning demo is pinned to the approved Qwen3-Embedding-0.6B revision"
            )
        if (
            self.dense_weight,
            self.bm25_weight,
            self.rrf_k,
            self.candidate_k,
            self.evidence_k,
        ) != (0.1, 0.9, 60, 20, 5):
            raise LearningConfigurationError(
                "Retrieval must remain Dense 0.10 / BM25 0.90, RRF k=60, top-20, evidence-k=5"
            )
        if not 0.8 <= self.minimum_topic_resolution_rate <= 1.0:
            raise LearningConfigurationError("minimum_topic_resolution_rate must be in [0.8, 1]")
        if not self.demo_topic_ids or any(not value.strip() for value in self.demo_topic_ids):
            raise LearningConfigurationError('Choose Topic IDs or ["*"] for all Topics')
        if self.total_request_cap < 0:
            raise LearningConfigurationError("total_request_cap cannot be negative")
        if self.model_selection_status not in {"provisional", "frozen"}:
            raise LearningConfigurationError("model_selection_status must be provisional or frozen")
