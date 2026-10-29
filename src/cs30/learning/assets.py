"""Fail-closed checks for corpus, Topic, Role, lambda and Qwen3 assets."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from cs30.generation.lambda_search import load_role_label_package
from cs30.v2.contracts import IndexArtifact, TopicRegistry
from cs30.v2.corpus.records import LoadedCorpus, load_corpus_records
from cs30.v2.experiment import LambdaSelection
from cs30.v2.topics import (
    LoadedChunkTopicMap,
    canonical_chunk_topic_map,
    load_chunk_topic_map,
    load_validated_chunk_topic_map,
    write_chunk_topic_map,
)

from .config import LearningConfig


@dataclass(frozen=True)
class LearningAssets:
    corpus: LoadedCorpus
    topic_registry: TopicRegistry
    topic_map: LoadedChunkTopicMap
    role_package: object
    lambda_selection: LambdaSelection
    index_artifact: IndexArtifact


@dataclass(frozen=True)
class SetupCheck:
    name: str
    passed: bool
    detail: str
    blocking: bool = True


@dataclass(frozen=True)
class SetupReport:
    checks: tuple[SetupCheck, ...]

    @property
    def ready(self) -> bool:
        return all(check.passed or not check.blocking for check in self.checks)

    @property
    def blockers(self) -> tuple[SetupCheck, ...]:
        return tuple(check for check in self.checks if not check.passed and check.blocking)

    @property
    def warnings(self) -> tuple[SetupCheck, ...]:
        return tuple(check for check in self.checks if not check.passed and not check.blocking)


class LearningAssetError(ValueError):
    """A required learning-demo asset is absent or bound to another release."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare_topic_map_binding(
    source_path: Path,
    corpus_dir: Path,
    registry_path: Path,
    output_path: Path,
) -> Path:
    """Create a new, auditable map sidecar when only its version label is stale.

    The source asset is preserved. Rebinding is refused unless the source and
    target corpus hashes match and every mapped chunk exists in the target corpus.
    Strict runtime validation still checks the generated file's version and hash.
    """

    source_path, corpus_dir, registry_path, output_path = map(
        Path, (source_path, corpus_dir, registry_path, output_path)
    )
    if source_path.resolve() == output_path.resolve():
        raise LearningAssetError("the rebound Topic map must not overwrite its source")
    if (
        output_path.exists()
        or output_path.with_suffix(output_path.suffix + ".provenance.json").exists()
    ):
        raise LearningAssetError("rebound output already exists; choose a new output path")
    corpus = load_corpus_records(corpus_dir)
    source = load_chunk_topic_map(source_path)
    registry = TopicRegistry.model_validate_json(registry_path.read_bytes())
    if source.corpus_hash != corpus.manifest.corpus_hash:
        raise LearningAssetError("Topic map corpus_hash differs; refusing to rebind")
    if source.topic_registry_version != registry.topic_registry_version:
        raise LearningAssetError("Topic map and Topic registry versions differ")
    known_chunks = set(corpus.chunk_ids)
    mapped_chunks = {item.chunk_id for item in source.assignments}
    unknown = mapped_chunks - known_chunks
    if unknown:
        raise LearningAssetError(f"Topic map contains {len(unknown)} chunk IDs outside the corpus")

    rebound = canonical_chunk_topic_map(
        source.model_copy(update={"corpus_version": corpus.manifest.corpus_version})
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    write_chunk_topic_map(rebound, output_path)
    loaded = load_validated_chunk_topic_map(
        output_path,
        manifest=corpus.manifest,
        corpus_chunk_ids=corpus.chunk_ids,
    )
    if loaded.error_code is not None:
        output_path.unlink(missing_ok=True)
        raise LearningAssetError(f"rebound map failed strict validation: {loaded.error_code}")

    provenance = {
        "schema_version": "1",
        "operation": "topic-map-version-rebind",
        "source_path": str(source_path.resolve()),
        "source_sha256": _sha256(source_path),
        "output_path": str(output_path.resolve()),
        "output_sha256": _sha256(output_path),
        "source_corpus_version": source.corpus_version,
        "target_corpus_version": corpus.manifest.corpus_version,
        "corpus_hash": corpus.manifest.corpus_hash,
        "topic_registry_version": registry.topic_registry_version,
        "mapped_chunk_count": len(mapped_chunks),
        "unmapped_corpus_chunk_count": len(known_chunks - mapped_chunks),
        "unknown_chunk_count": 0,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "rule": "corpus_hash_equal_and_all_map_chunk_ids_exist; source preserved",
    }
    output_path.with_suffix(output_path.suffix + ".provenance.json").write_text(
        json.dumps(provenance, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return output_path


def _load_assets(config: LearningConfig) -> LearningAssets:
    corpus = load_corpus_records(config.corpus_dir)
    registry = TopicRegistry.model_validate_json(config.topic_registry_path.read_bytes())
    topic_map = load_validated_chunk_topic_map(
        config.topic_map_path,
        manifest=corpus.manifest,
        corpus_chunk_ids=corpus.chunk_ids,
    )
    if topic_map.error_code is not None or topic_map.topic_map is None:
        raise LearningAssetError(
            "Topic map is unavailable or mismatched. If hashes and chunk identities match, "
            "run the explicit topic-map rebind preparation first."
        )
    if topic_map.topic_map.topic_registry_version != registry.topic_registry_version:
        raise LearningAssetError("Topic map and registry versions differ")

    role_package = load_role_label_package(config.role_manifest_path)
    if role_package.manifest.corpus_version != corpus.manifest.corpus_version:
        raise LearningAssetError("Role-label corpus_version differs from the loaded corpus")
    if role_package.manifest.reference_type != "chunk":
        raise LearningAssetError("the selected Role package is not chunk-scoped")
    if set(role_package.labels) - set(corpus.chunk_ids):
        raise LearningAssetError("Role package contains chunk IDs outside the loaded corpus")
    if len(role_package.labels) != len(corpus.chunks):
        raise LearningAssetError("Role package does not cover every corpus chunk")

    selection = LambdaSelection.model_validate_json(config.lambda_selection_path.read_bytes())
    if (
        selection.corpus_hash != corpus.manifest.corpus_hash
        or selection.manifest_hash != corpus.manifest.manifest_hash
        or selection.role_labels_sha256 != role_package.manifest.labels_sha256
        or selection.lambda_weight != 0.1
        or selection.candidate_k != config.candidate_k
        or selection.evidence_k != config.evidence_k
        or selection.profile_confidence != 1.0
    ):
        raise LearningAssetError("Dev lambda selection is not bound to this corpus/Role/config")

    index = IndexArtifact.model_validate_json(config.index_artifact_path.read_bytes())
    if (
        index.corpus_version != corpus.manifest.corpus_version
        or index.corpus_hash != corpus.manifest.corpus_hash
        or index.manifest_hash != corpus.manifest.manifest_hash
        or index.chunk_config_hash != corpus.manifest.chunk_config_hash
        or index.chunk_ids != corpus.chunk_ids
        or index.embedding_model != config.dense_embedding_model
        or index.embedding_revision != config.dense_embedding_revision
    ):
        raise LearningAssetError("Qwen3 index identity differs from the selected corpus/revision")
    if not config.index_file_path.is_file():
        raise LearningAssetError(f"Qwen3 FAISS index is missing: {config.index_file_path}")
    expected_index_hash = str(index.metadata.get("index_sha256", "")).removeprefix("sha256:")
    if _sha256(config.index_file_path).casefold() != expected_index_hash.casefold():
        raise LearningAssetError("Qwen3 FAISS file hash differs from its v2 IndexArtifact")
    return LearningAssets(corpus, registry, topic_map, role_package, selection, index)


def _cached_embedding_exists(model_name: str, revision: str) -> bool:
    try:
        from huggingface_hub import snapshot_download

        snapshot_download(repo_id=model_name, revision=revision, local_files_only=True)
        return True
    except Exception:
        return False


def check_learning_setup(config: LearningConfig) -> SetupReport:
    """Check all local gates without constructing an API client or sending a call."""

    checks: list[SetupCheck] = []
    required = (
        ("corpus", config.corpus_dir / "manifest.json"),
        ("source Topic map", config.source_topic_map_path),
        ("bound Topic map", config.topic_map_path),
        ("Topic registry", config.topic_registry_path),
        ("Role manifest", config.role_manifest_path),
        ("Dev lambda selection", config.lambda_selection_path),
        ("Qwen3 index artifact", config.index_artifact_path),
        ("Qwen3 FAISS index", config.index_file_path),
        ("offline question bank", config.question_bank_path),
    )
    missing = [f"{name}: {path}" for name, path in required if not path.exists()]
    checks.append(
        SetupCheck(
            "asset paths",
            not missing,
            "All configured asset paths exist" if not missing else "Missing: " + "; ".join(missing),
        )
    )

    assets = None
    try:
        assets = _load_assets(config)
        checks.append(
            SetupCheck(
                "asset identity",
                True,
                (
                    f"{len(assets.corpus.chunks)} chunks; corpus, Topic map, Role, "
                    "lambda and index agree"
                ),
            )
        )
    except Exception as exc:
        checks.append(SetupCheck("asset identity", False, str(exc)))

    if assets is not None:
        cached = _cached_embedding_exists(
            config.dense_embedding_model, config.dense_embedding_revision
        )
        checks.append(
            SetupCheck(
                "local embedding weights",
                cached,
                "Pinned Qwen3 revision is cached locally"
                if cached
                else "Pinned Qwen3 revision is not cached; download it before live retrieval",
            )
        )

    try:
        preflight = json.loads(config.preflight_report_path.read_text(encoding="utf-8"))
        summary = preflight.get("summary", {})
        rate = float(summary.get("unique_topic_rate", 0.0))
        total = int(summary.get("question_count", 0))
        same_assets = (
            assets is not None
            and preflight.get("corpus_hash") == assets.corpus.manifest.corpus_hash
            and preflight.get("topic_map_sha256") == _sha256(config.topic_map_path)
            and preflight.get("index_sha256") == _sha256(config.index_file_path)
            and preflight.get("question_bank_sha256") == _sha256(config.question_bank_path)
        )
        passed = (
            same_assets
            and total >= 10
            and ("*" in config.demo_topic_ids or rate >= config.minimum_topic_resolution_rate)
        )
        detail = (
            f"{summary.get('resolved_count', 0)}/{total} unique Topics ({rate:.1%}); "
            "asset hashes checked; historical unique-Topic rate is not all-Topic coverage"
        )
        if not same_assets:
            detail += "; report is stale or bound to different assets"
        checks.append(SetupCheck("offline Topic preflight", passed, detail))
    except (OSError, ValueError, TypeError) as exc:
        checks.append(
            SetupCheck(
                "offline Topic preflight",
                False,
                f"No valid offline preflight report at {config.preflight_report_path}: {exc}",
            )
        )

    known_topics = (
        {topic.topic_id for topic in assets.topic_registry.topics} if assets is not None else set()
    )
    scope_valid = bool(config.demo_topic_ids) and (
        "*" in config.demo_topic_ids or set(config.demo_topic_ids).issubset(known_topics)
    )
    checks.append(SetupCheck(
        "Demo Topic scope", scope_valid,
        f"All {len(known_topics)} registered Topics enabled; cited mapped evidence required"
        if "*" in config.demo_topic_ids else ", ".join(config.demo_topic_ids),
    ))

    roles = (config.answer_api, config.quiz_api)
    missing_keys = sorted(
        {role.api_key_env for role in roles if not os.environ.get(role.api_key_env, "").strip()}
    )
    checks.append(
        SetupCheck(
            "API credentials",
            not missing_keys,
            "Configured environment variables are present"
            if not missing_keys
            else "Missing environment variables: " + ", ".join(missing_keys),
        )
    )
    checks.append(
        SetupCheck(
            "API request cap",
            config.total_request_cap > 0,
            f"Persistent cap is {config.total_request_cap} requests"
            if config.total_request_cap > 0
            else "Set a positive process-level request cap after approving the Demo budget",
        )
    )
    checks.append(
        SetupCheck(
            "live API switch",
            config.live_calls_enabled,
            "Live API calls are enabled in the local config"
            if config.live_calls_enabled
            else "Live API calls are disabled in the local config",
        )
    )
    if config.model_selection_status == "provisional":
        checks.append(
            SetupCheck(
                "model freeze",
                False,
                (
                    "API role models are provisional M7-backed Demo defaults, "
                    "not a formal model decision"
                ),
                blocking=False,
            )
        )
    return SetupReport(tuple(checks))


def load_learning_assets(config: LearningConfig) -> LearningAssets:
    """Load only assets that pass the same strict identity checks as doctor."""

    return _load_assets(config)
