"""Reproducibility metadata and comparison guards for evaluation runs."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from cs30.contracts import RetrievalMode
from cs30.contracts.models import ContractModel, Identifier

from .models import EvaluationSplit, ExecutionMode


class RunManifest(ContractModel):
    """Metadata required to reproduce and safely compare one batch run."""

    # 0.1 manifests remain readable because they were used by the first
    # engineering fixtures.  New manifests use 0.2 and carry the evaluation
    # artifact identities needed for safe re-scoring and comparison.
    schema_version: Literal["0.1", "0.2"] = "0.2"
    run_id: Identifier
    condition_id: Identifier
    dataset_version: Identifier
    dataset_id: Identifier | None = None
    split: EvaluationSplit
    corpus_version: Identifier
    chunk_version: Identifier
    parser_version: Identifier | None = None
    gold_annotation_version: Identifier | None = None
    mapping_version: Identifier | None = None
    embedding_version: Identifier | None
    index_version: Identifier | None
    generation_model: Identifier | None
    prompt_version: Identifier | None
    profile: Identifier
    execution_mode: ExecutionMode
    retrieval_mode: RetrievalMode
    top_k: int = Field(gt=0)
    k_values: list[int] = Field(min_length=1)
    threshold: float | None = None
    git_commit: Identifier
    git_dirty: bool
    git_snapshot_sha256: Identifier
    fixture_mode: bool = False
    synthetic_trace: bool = False
    reportable: bool = True

    @model_validator(mode="after")
    def validate_k_values(self) -> RunManifest:
        if self.git_dirty and self.reportable:
            raise ValueError("dirty manifests must set reportable=False")
        if self.fixture_mode and self.reportable:
            raise ValueError("fixture manifests must set reportable=False")
        if self.synthetic_trace and self.reportable:
            raise ValueError("synthetic traces must set reportable=False")
        if self.synthetic_trace and not self.fixture_mode:
            raise ValueError("synthetic traces are only allowed in fixture mode")
        if self.synthetic_trace and self.execution_mode is ExecutionMode.RETRIEVAL_ONLY:
            raise ValueError("synthetic traces are only valid for generation runs")
        if self.reportable and self.corpus_version == "unspecified":
            raise ValueError("reportable manifests must record a prepared corpus_version")
        if any(k <= 0 for k in self.k_values):
            raise ValueError("k_values must contain only positive integers")
        if len(set(self.k_values)) != len(self.k_values):
            raise ValueError("k_values must be unique")
        if self.k_values != sorted(self.k_values):
            raise ValueError("k_values must be sorted in ascending order")
        if any(k > self.top_k for k in self.k_values):
            raise ValueError("k_values must not exceed manifest top_k")
        return self


def write_manifest(manifest: RunManifest, output_path: str | Path) -> None:
    """Publish a manifest atomically without replacing an existing artifact."""

    destination = Path(output_path)
    if destination.exists():
        raise FileExistsError(f"refusing to overwrite run manifest: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        encoded = (
            json.dumps(manifest.model_dump(mode="json"), indent=2, ensure_ascii=False)
            + "\n"
        ).encode("utf-8")
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{destination.name}.",
            suffix=".tmp",
            dir=destination.parent,
            delete=False,
        ) as stream:
            temporary_path = Path(stream.name)
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary_path, destination)
        except FileExistsError as exc:
            raise FileExistsError(
                f"refusing to overwrite run manifest: {destination}"
            ) from exc
        temporary_path.unlink()
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


@dataclass(frozen=True)
class GitState:
    """Working-tree identity used by a manifest."""

    commit: str
    dirty: bool
    snapshot_sha256: str


def _git_output(worktree: Path, *args: str) -> bytes:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=worktree,
            check=True,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeError(f"git command failed in {worktree}: {args!r}") from exc
    return completed.stdout


def capture_git_state(worktree: str | Path = ".") -> GitState:
    """Capture commit, dirty status, and a content hash including untracked files."""

    root = Path(worktree).resolve()
    try:
        repository_root = Path(
            _git_output(root, "rev-parse", "--show-toplevel").decode().strip()
        ).resolve()
    except RuntimeError:
        repository_root = root
    try:
        commit = _git_output(repository_root, "rev-parse", "HEAD").decode().strip()
    except RuntimeError:
        commit = "no-commit"

    status = _git_output(
        repository_root,
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
    )
    dirty = bool(status)
    paths = _git_output(
        repository_root,
        "ls-files",
        "-c",
        "-o",
        "--exclude-standard",
        "-z",
    )
    relative_paths = {item.decode("utf-8") for item in paths.split(b"\0") if item}
    digest = hashlib.sha256()
    for relative in sorted(relative_paths):
        path = repository_root / relative
        digest.update(relative.replace("\\", "/").encode("utf-8"))
        digest.update(b"\0")
        if path.is_file():
            digest.update(path.read_bytes())
        else:
            digest.update(b"<missing>")
        digest.update(b"\0")
    return GitState(commit=commit, dirty=dirty, snapshot_sha256=digest.hexdigest())


def assert_clean_for_report(state: GitState, *, allow_dirty: bool = False) -> None:
    """Reject a dirty working tree unless the caller explicitly allows it."""

    if state.dirty and not allow_dirty:
        raise ValueError(
            "formal evaluation requires a clean git worktree; pass allow_dirty=True "
            "only for non-reportable fixture/development runs"
        )


def _comparison_key(manifest: RunManifest) -> tuple[object, ...]:
    return (
        manifest.dataset_id,
        manifest.dataset_version,
        manifest.split,
        manifest.corpus_version,
        manifest.chunk_version,
        manifest.parser_version,
        manifest.gold_annotation_version,
        manifest.mapping_version,
        manifest.generation_model,
        manifest.prompt_version,
        manifest.profile,
        manifest.execution_mode,
        manifest.top_k,
        manifest.fixture_mode,
        manifest.synthetic_trace,
    )


def run_results_are_comparable(manifests: list[RunManifest]) -> bool:
    """Return whether manifests share the immutable comparison context."""

    if len(manifests) < 2:
        return True
    first = _comparison_key(manifests[0])
    if not all(_comparison_key(manifest) == first for manifest in manifests[1:]):
        return False
    backend_versions: dict[RetrievalMode, tuple[str | None, str | None]] = {}
    for manifest in manifests:
        backend_key = (manifest.embedding_version, manifest.index_version)
        previous = backend_versions.setdefault(manifest.retrieval_mode, backend_key)
        if previous != backend_key:
            return False
    return True


def assert_manifests_comparable(manifests: list[RunManifest]) -> None:
    """Raise instead of silently comparing incompatible evaluation runs."""

    if not run_results_are_comparable(manifests):
        raise ValueError(
            "evaluation manifests are not comparable: dataset/gold/mapping/corpus, "
            "model/prompt/profile, or execution settings differ"
        )
