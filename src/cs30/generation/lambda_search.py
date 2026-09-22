"""Select one global reranking lambda on Dev data and freeze its provenance.

The search consumes an explicit Member 7 handoff format instead of guessing at
upstream schemas.  Every case contains the frozen StudentProfile, the original
M6 candidate list, and the Gold-relevant chunk IDs.  Test rows are rejected so
they cannot accidentally influence the selected value.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from cs30.contracts import RetrievalMode, RetrievalResult, StudentLevel, StudentProfile
from cs30.evaluation.extension_models import RoleLabelProvenanceManifest

from .reranking import EvidenceRole, LevelAwareReranker, RerankConfig, RoleLabel

InputStatus = Literal["fixture", "provisional", "formal"]
TaxonomyStatus = Literal["fixture", "frozen"]

DEFAULT_LAMBDAS = tuple(round(step / 10, 1) for step in range(11))


def _canonical_json(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def is_sha256(value: object) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    return all(character in "0123456789abcdef" for character in value.lower())


@dataclass(frozen=True)
class LambdaSearchCase:
    """One Dev case used to select the global lambda value."""

    question_id: str
    profile: StudentProfile
    retrieval: RetrievalResult
    relevant_chunk_ids: frozenset[str]
    split: Literal["dev"] = "dev"
    source_split: str = "fixture"
    source_reportable: bool = False
    source_manifest_sha256: str | None = None

    def __post_init__(self) -> None:
        question_id = self.question_id.strip()
        if not question_id:
            raise ValueError("question_id must not be empty")
        object.__setattr__(self, "question_id", question_id)
        object.__setattr__(self, "relevant_chunk_ids", frozenset(self.relevant_chunk_ids))
        if self.split != "dev":
            raise ValueError("lambda selection accepts Dev cases only; Test tuning is forbidden")
        if not self.relevant_chunk_ids:
            raise ValueError("relevant_chunk_ids must not be empty")
        if not self.retrieval.hits:
            raise ValueError("lambda search requires at least one retrieved candidate")
        if not self.source_split.strip():
            raise ValueError("source_split must not be empty")
        if not isinstance(self.source_reportable, bool):
            raise ValueError("source_reportable must be a boolean")
        if self.source_manifest_sha256 is not None and not is_sha256(
            self.source_manifest_sha256
        ):
            raise ValueError("source_manifest_sha256 must be a SHA-256 hex digest")

    @property
    def case_id(self) -> str:
        return f"{self.question_id}:{self.profile.profile_id}"


@dataclass(frozen=True)
class CaseMetric:
    case_id: str
    question_id: str
    profile_id: str
    level: str
    first_relevant_rank: int | None
    reciprocal_rank: float
    hit: float
    recall: float

    def model_dump(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "question_id": self.question_id,
            "profile_id": self.profile_id,
            "level": self.level,
            "first_relevant_rank": self.first_relevant_rank,
            "reciprocal_rank": self.reciprocal_rank,
            "hit": self.hit,
            "recall": self.recall,
        }


@dataclass(frozen=True)
class LambdaMetric:
    lambda_weight: float
    mean_reciprocal_rank: float
    hit_rate: float
    mean_recall: float
    cases: tuple[CaseMetric, ...]

    def model_dump(self) -> dict[str, object]:
        return {
            "lambda_weight": self.lambda_weight,
            "mean_reciprocal_rank": self.mean_reciprocal_rank,
            "hit_rate": self.hit_rate,
            "mean_recall": self.mean_recall,
            "cases": [case.model_dump() for case in self.cases],
        }


@dataclass(frozen=True)
class SelectedLambdaConfig:
    """Deterministic selected configuration; only formal inputs make it frozen."""

    config_id: str
    lambda_weight: float
    selection_status: Literal["provisional", "frozen"]
    reportable: bool
    selected_on_split: Literal["dev"]
    objective: str
    metric_k: int
    selection_rule: str
    input_status: InputStatus
    taxonomy_status: TaxonomyStatus
    taxonomy_version: str
    candidate_lambdas: tuple[float, ...]
    dev_case_ids: tuple[str, ...]
    cases_sha256: str | None
    role_labels_sha256: str | None
    split_manifest_sha256: str | None = None

    def model_dump(self) -> dict[str, object]:
        return {
            "schema_version": "1.0",
            "config_id": self.config_id,
            "lambda_weight": self.lambda_weight,
            "parameter_source": "dev",
            "selection_status": self.selection_status,
            "reportable": self.reportable,
            "selected_on_split": self.selected_on_split,
            "objective": self.objective,
            "metric_k": self.metric_k,
            "selection_rule": self.selection_rule,
            "input_status": self.input_status,
            "taxonomy_status": self.taxonomy_status,
            "taxonomy_version": self.taxonomy_version,
            "candidate_lambdas": list(self.candidate_lambdas),
            "dev_case_ids": list(self.dev_case_ids),
            "cases_sha256": self.cases_sha256,
            "role_labels_sha256": self.role_labels_sha256,
            "split_manifest_sha256": self.split_manifest_sha256,
        }

    @classmethod
    def model_validate(cls, payload: Mapping[str, object]) -> SelectedLambdaConfig:
        if payload.get("schema_version") != "1.0":
            raise ValueError("selected lambda config schema_version must be 1.0")
        if payload.get("parameter_source") != "dev":
            raise ValueError("selected lambda must come from Dev")
        candidate_lambdas = tuple(float(value) for value in payload["candidate_lambdas"])
        dev_case_ids = tuple(str(value) for value in payload["dev_case_ids"])
        reportable = payload["reportable"]
        if not isinstance(reportable, bool):
            raise ValueError("selected lambda reportable must be a boolean")
        values = {
            "config_id": str(payload["config_id"]),
            "lambda_weight": float(payload["lambda_weight"]),
            "selection_status": str(payload["selection_status"]),
            "reportable": reportable,
            "selected_on_split": str(payload["selected_on_split"]),
            "objective": str(payload["objective"]),
            "metric_k": int(payload["metric_k"]),
            "selection_rule": str(payload["selection_rule"]),
            "input_status": str(payload["input_status"]),
            "taxonomy_status": str(payload["taxonomy_status"]),
            "taxonomy_version": str(payload["taxonomy_version"]),
            "candidate_lambdas": candidate_lambdas,
            "dev_case_ids": dev_case_ids,
            "cases_sha256": payload.get("cases_sha256"),
            "role_labels_sha256": payload.get("role_labels_sha256"),
            "split_manifest_sha256": payload.get("split_manifest_sha256"),
        }
        config = cls(**values)  # type: ignore[arg-type]
        if config.selection_status not in {"provisional", "frozen"}:
            raise ValueError("selection_status must be provisional or frozen")
        if config.input_status not in {"fixture", "provisional", "formal"}:
            raise ValueError("input_status must be fixture, provisional, or formal")
        if config.taxonomy_status not in {"fixture", "frozen"}:
            raise ValueError("taxonomy_status must be fixture or frozen")
        if config.selected_on_split != "dev":
            raise ValueError("selected lambda must be selected on Dev")
        if not 0.0 <= config.lambda_weight <= 1.0:
            raise ValueError("lambda_weight must be in the interval [0, 1]")
        if config.lambda_weight not in config.candidate_lambdas:
            raise ValueError("selected lambda must be one of candidate_lambdas")
        expected = _config_id(config._identity_payload())
        if config.config_id != expected:
            raise ValueError("selected lambda config_id does not match its contents")
        if config.reportable != (config.selection_status == "frozen"):
            raise ValueError("only a frozen selected lambda config can be reportable")
        if config.selection_status == "frozen" and (
            config.input_status != "formal" or config.taxonomy_status != "frozen"
        ):
            raise ValueError("frozen lambda requires formal inputs and a frozen taxonomy")
        if config.selection_status == "frozen" and (
            not is_sha256(config.cases_sha256)
            or not is_sha256(config.role_labels_sha256)
            or not is_sha256(config.split_manifest_sha256)
        ):
            raise ValueError("frozen lambda requires SHA-256 input digests")
        return config

    def _identity_payload(self) -> dict[str, object]:
        payload = self.model_dump()
        payload.pop("config_id")
        return payload


@dataclass(frozen=True)
class LambdaSearchResult:
    selected: SelectedLambdaConfig
    metrics: tuple[LambdaMetric, ...]
    role_label_coverage: RoleLabelCoverage

    def model_dump(self) -> dict[str, object]:
        return {
            "schema_version": "1.0",
            "result_type": "member7_lambda_dev_search",
            "selected_config": self.selected.model_dump(),
            "role_label_coverage": self.role_label_coverage.model_dump(),
            "metrics": [metric.model_dump() for metric in self.metrics],
        }


@dataclass(frozen=True)
class RoleLabelCoverage:
    """Coverage of reranking candidates by the supplied M3 Role package."""

    labeled_candidate_count: int
    total_candidate_count: int
    labeled_unique_chunk_count: int
    total_unique_chunk_count: int

    @property
    def complete(self) -> bool:
        return self.labeled_candidate_count == self.total_candidate_count

    def model_dump(self) -> dict[str, object]:
        ratio = self.labeled_candidate_count / self.total_candidate_count
        return {
            "labeled_candidate_count": self.labeled_candidate_count,
            "total_candidate_count": self.total_candidate_count,
            "coverage_ratio": ratio,
            "labeled_unique_chunk_count": self.labeled_unique_chunk_count,
            "total_unique_chunk_count": self.total_unique_chunk_count,
            "complete": self.complete,
            "interpretation_status": "interpretable" if self.complete else "not_interpretable",
            "warning": None
            if self.complete
            else (
                "Role-label coverage is incomplete; lambda and personalisation-effect "
                "metrics are engineering diagnostics only and are not interpretable."
            ),
        }


@dataclass(frozen=True)
class LoadedRoleLabelPackage:
    """Validated M3 Role labels plus manifest-owned provenance."""

    labels: dict[str, RoleLabel]
    manifest: RoleLabelProvenanceManifest
    labels_path: Path


def _config_id(payload: Mapping[str, object]) -> str:
    digest = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
    return f"member7-lambda-{digest[:16]}"


def _validate_lambdas(values: Iterable[float]) -> tuple[float, ...]:
    lambdas = tuple(sorted({float(value) for value in values}))
    if not lambdas:
        raise ValueError("at least one lambda candidate is required")
    if any(value < 0.0 or value > 1.0 for value in lambdas):
        raise ValueError("lambda candidates must be in the interval [0, 1]")
    if 0.0 not in lambdas:
        raise ValueError("lambda candidates must include the lambda=0 baseline")
    return lambdas


def _score_case(
    case: LambdaSearchCase,
    ordered_chunk_ids: Sequence[str],
    *,
    k: int,
) -> CaseMetric:
    top_k = tuple(ordered_chunk_ids[:k])
    first_rank = next(
        (rank for rank, chunk_id in enumerate(top_k, 1) if chunk_id in case.relevant_chunk_ids),
        None,
    )
    relevant_found = len(set(top_k) & case.relevant_chunk_ids)
    return CaseMetric(
        case_id=case.case_id,
        question_id=case.question_id,
        profile_id=case.profile.profile_id,
        level=case.profile.level.value,
        first_relevant_rank=first_rank,
        reciprocal_rank=0.0 if first_rank is None else 1.0 / first_rank,
        hit=0.0 if first_rank is None else 1.0,
        recall=relevant_found / len(case.relevant_chunk_ids),
    )


def _validate_formal_cases(
    cases: Sequence[LambdaSearchCase],
    role_labels: Mapping[str, RoleLabel],
    *,
    expected_question_count: int,
) -> None:
    by_question: dict[str, list[LambdaSearchCase]] = {}
    for case in cases:
        by_question.setdefault(case.question_id, []).append(case)
        if case.retrieval.mode is RetrievalMode.FIXTURE or case.retrieval.provenance is None:
            raise ValueError("formal lambda search requires non-fixture retrieval provenance")
        if (
            case.source_split != "dev"
            or not case.source_reportable
            or case.source_manifest_sha256 is None
        ):
            raise ValueError(
                "formal lambda search requires a reportable Dev source manifest"
            )

    if len(by_question) != expected_question_count:
        raise ValueError(
            "formal lambda search question count does not match the split manifest; "
            f"expected {expected_question_count}, "
            f"found {len(by_question)}"
        )

    expected_levels = set(StudentLevel)
    for question_id, question_cases in by_question.items():
        levels = {case.profile.level for case in question_cases}
        if levels != expected_levels:
            raise ValueError(
                "formal lambda search requires beginner, intermediate, and advanced "
                f"profiles for every question; {question_id} has "
                f"{sorted(level.value for level in levels)}"
            )
        retrieval_payloads = {
            case.retrieval.model_dump_json(exclude_none=False) for case in question_cases
        }
        if len(retrieval_payloads) != 1:
            raise ValueError(
                "all profile levels must use the same initial candidates for "
                f"question {question_id}"
            )

    candidate_ids = {
        hit.chunk_id for case in cases for hit in case.retrieval.hits
    }
    missing = sorted(candidate_ids - role_labels.keys())
    if missing:
        preview = ", ".join(missing[:5])
        raise ValueError(f"formal lambda search is missing Role labels for: {preview}")
    invalid = sorted(
        chunk_id
        for chunk_id in candidate_ids
        if len(role_labels[chunk_id].roles) != 1 or role_labels[chunk_id].source == "fixture"
    )
    if invalid:
        preview = ", ".join(invalid[:5])
        raise ValueError(
            "formal lambda search requires one non-fixture Role label per candidate: "
            f"{preview}"
        )


def search_lambda(
    cases: Sequence[LambdaSearchCase],
    role_labels: Mapping[str, RoleLabel],
    *,
    taxonomy_version: str,
    taxonomy_status: TaxonomyStatus,
    input_status: InputStatus,
    candidate_lambdas: Iterable[float] = DEFAULT_LAMBDAS,
    metric_k: int = 5,
    cases_sha256: str | None = None,
    role_labels_sha256: str | None = None,
    split_manifest_sha256: str | None = None,
    expected_question_count: int | None = None,
) -> LambdaSearchResult:
    """Select lambda by mean MRR@k, then hit rate, recall, and smallest lambda."""

    if not cases:
        raise ValueError("lambda search requires at least one Dev case")
    if metric_k < 1:
        raise ValueError("metric_k must be at least 1")
    undersized = sorted(
        case.case_id for case in cases if len(case.retrieval.hits) <= metric_k
    )
    if undersized:
        raise ValueError(
            "candidate pool must be larger than metric_k so hit/recall can change; "
            f"first invalid case: {undersized[0]}"
        )
    if not taxonomy_version.strip():
        raise ValueError("taxonomy_version must not be empty")
    if taxonomy_status not in {"fixture", "frozen"}:
        raise ValueError("taxonomy_status must be fixture or frozen")
    if input_status not in {"fixture", "provisional", "formal"}:
        raise ValueError("input_status must be fixture, provisional, or formal")
    if input_status == "formal":
        if taxonomy_status != "frozen":
            raise ValueError("formal lambda search requires a frozen taxonomy")
        if not all(
            is_sha256(value)
            for value in (cases_sha256, role_labels_sha256, split_manifest_sha256)
        ):
            raise ValueError("formal lambda search requires SHA-256 input digests")
        if expected_question_count is None or expected_question_count < 1:
            raise ValueError(
                "formal lambda search requires a positive question count from the "
                "split manifest"
            )
        _validate_formal_cases(
            cases,
            role_labels,
            expected_question_count=expected_question_count,
        )

    case_ids = [case.case_id for case in cases]
    if len(set(case_ids)) != len(case_ids):
        raise ValueError("lambda search case_id values must be unique")
    lambdas = _validate_lambdas(candidate_lambdas)
    candidate_references = {
        (case.question_id, hit.chunk_id)
        for case in cases
        for hit in case.retrieval.hits
    }
    unique_chunk_ids = {chunk_id for _, chunk_id in candidate_references}
    role_label_coverage = RoleLabelCoverage(
        labeled_candidate_count=sum(
            chunk_id in role_labels for _, chunk_id in candidate_references
        ),
        total_candidate_count=len(candidate_references),
        labeled_unique_chunk_count=len(unique_chunk_ids & role_labels.keys()),
        total_unique_chunk_count=len(unique_chunk_ids),
    )
    metric_rows: list[LambdaMetric] = []

    for lambda_weight in lambdas:
        reranker = LevelAwareReranker(
            role_labels,
            config=RerankConfig(
                lambda_weight=lambda_weight,
                parameter_source="dev",
                taxonomy_status=taxonomy_status,
                taxonomy_version=taxonomy_version,
            ),
        )
        case_metrics: list[CaseMetric] = []
        for case in cases:
            reranked = reranker.rerank(case.retrieval, case.profile)
            ordered = [hit.chunk_id for hit in reranked.evidence.hits]
            case_metrics.append(_score_case(case, ordered, k=metric_k))

        count = len(case_metrics)
        metric_rows.append(
            LambdaMetric(
                lambda_weight=lambda_weight,
                mean_reciprocal_rank=sum(row.reciprocal_rank for row in case_metrics) / count,
                hit_rate=sum(row.hit for row in case_metrics) / count,
                mean_recall=sum(row.recall for row in case_metrics) / count,
                cases=tuple(case_metrics),
            )
        )

    selected_metric = max(
        metric_rows,
        key=lambda row: (
            row.mean_reciprocal_rank,
            row.hit_rate,
            row.mean_recall,
            -row.lambda_weight,
        ),
    )
    is_frozen = input_status == "formal" and taxonomy_status == "frozen"
    identity_payload: dict[str, object] = {
        "schema_version": "1.0",
        "lambda_weight": selected_metric.lambda_weight,
        "parameter_source": "dev",
        "selection_status": "frozen" if is_frozen else "provisional",
        "reportable": is_frozen,
        "selected_on_split": "dev",
        "objective": f"mean_reciprocal_rank@{metric_k}",
        "metric_k": metric_k,
        "selection_rule": "max_mrr_then_hit_rate_then_recall_then_smallest_lambda",
        "input_status": input_status,
        "taxonomy_status": taxonomy_status,
        "taxonomy_version": taxonomy_version,
        "candidate_lambdas": list(lambdas),
        "dev_case_ids": sorted(case_ids),
        "cases_sha256": cases_sha256,
        "role_labels_sha256": role_labels_sha256,
        "split_manifest_sha256": split_manifest_sha256,
    }
    selected = SelectedLambdaConfig(
        config_id=_config_id(identity_payload),
        lambda_weight=selected_metric.lambda_weight,
        selection_status="frozen" if is_frozen else "provisional",
        reportable=is_frozen,
        selected_on_split="dev",
        objective=f"mean_reciprocal_rank@{metric_k}",
        metric_k=metric_k,
        selection_rule="max_mrr_then_hit_rate_then_recall_then_smallest_lambda",
        input_status=input_status,
        taxonomy_status=taxonomy_status,
        taxonomy_version=taxonomy_version,
        candidate_lambdas=lambdas,
        dev_case_ids=tuple(sorted(case_ids)),
        cases_sha256=cases_sha256,
        role_labels_sha256=role_labels_sha256,
        split_manifest_sha256=split_manifest_sha256,
    )
    return LambdaSearchResult(
        selected=selected,
        metrics=tuple(metric_rows),
        role_label_coverage=role_label_coverage,
    )


def load_lambda_cases(path: Path) -> list[LambdaSearchCase]:
    cases: list[LambdaSearchCase] = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            payload = json.loads(raw)
            source_reportable = payload.get("source_reportable", False)
            if not isinstance(source_reportable, bool):
                raise ValueError("source_reportable must be a boolean")
            cases.append(
                LambdaSearchCase(
                    question_id=payload["question_id"],
                    split=payload["split"],
                    profile=StudentProfile.model_validate(payload["profile"]),
                    retrieval=RetrievalResult.model_validate(payload["retrieval"]),
                    relevant_chunk_ids=frozenset(payload["relevant_chunk_ids"]),
                    source_split=payload.get("source_split", "fixture"),
                    source_reportable=source_reportable,
                    source_manifest_sha256=payload.get("source_manifest_sha256"),
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"invalid lambda case at {path}:{line_number}: {exc}") from exc
    if not cases:
        raise ValueError(f"no lambda cases found in {path}")
    return cases


def load_role_label_package(
    manifest_path: Path,
    *,
    expected_taxonomy_version: str | None = None,
) -> LoadedRoleLabelPackage:
    """Load M3 labels through M8's shared provenance-manifest contract."""

    try:
        manifest = RoleLabelProvenanceManifest.model_validate_json(
            manifest_path.read_text(encoding="utf-8")
        )
    except (OSError, ValueError) as exc:
        raise ValueError(f"invalid Role-label manifest at {manifest_path}: {exc}") from exc
    if (
        expected_taxonomy_version is not None
        and manifest.role_taxonomy_version != expected_taxonomy_version
    ):
        raise ValueError(
            "role_taxonomy_version does not match the selected configuration: "
            f"expected {expected_taxonomy_version!r}, "
            f"found {manifest.role_taxonomy_version!r}"
        )
    labels_path = manifest.labels_file
    if not labels_path.is_absolute():
        labels_path = manifest_path.parent / labels_path
    if not labels_path.is_file():
        raise ValueError(f"Role-label file does not exist: {labels_path}")
    actual_sha256 = sha256_file(labels_path)
    if actual_sha256 != manifest.labels_sha256:
        raise ValueError(
            "labels_sha256 does not match the Role-label file: "
            f"expected {manifest.labels_sha256}, found {actual_sha256}"
        )

    labels: dict[str, RoleLabel] = {}
    record_count = 0
    for line_number, raw in enumerate(
        labels_path.read_text(encoding="utf-8").splitlines(), 1
    ):
        if not raw.strip():
            continue
        record_count += 1
        try:
            payload = json.loads(raw)
            chunk_id = str(payload[manifest.reference_id_field]).strip()
            if not chunk_id:
                raise ValueError("reference ID must not be empty")
            if chunk_id in labels:
                raise ValueError(f"duplicate chunk_id: {chunk_id}")
            record_schema_version = payload[manifest.record_schema_version_field]
            if record_schema_version != manifest.role_schema_version:
                raise ValueError(
                    "record schema version does not match the Role-label manifest"
                )
            role_value = payload[manifest.role_field]
            if not isinstance(role_value, str) or not role_value.strip():
                raise ValueError("Role value must be a non-empty string")
            labels[chunk_id] = RoleLabel(
                (EvidenceRole(role_value),),
                source=manifest.annotation_version,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(
                f"invalid role label at {labels_path}:{line_number}: {exc}"
            ) from exc
    if not labels:
        raise ValueError(f"no role labels found in {labels_path}")
    if record_count != manifest.declared_record_count:
        raise ValueError(
            "declared_record_count does not match the Role-label file: "
            f"expected {manifest.declared_record_count}, found {record_count}"
        )
    return LoadedRoleLabelPackage(
        labels=labels,
        manifest=manifest,
        labels_path=labels_path,
    )


def load_role_labels(
    manifest_path: Path,
    *,
    expected_taxonomy_version: str | None = None,
) -> dict[str, RoleLabel]:
    """Return validated labels while retaining the previous mapping-only API."""

    return load_role_label_package(
        manifest_path,
        expected_taxonomy_version=expected_taxonomy_version,
    ).labels


def validate_formal_role_label_scope(package: LoadedRoleLabelPackage) -> None:
    """Reject Gold-only Role packages before a formal candidate-pool run."""

    if package.manifest.reference_universe != "corpus_records":
        raise ValueError(
            "the supplied Role-label package covers gold_mapping only; formal "
            "reranking requires Role labels for the complete candidate pool"
        )


def load_expected_question_count(path: Path, split: Literal["dev", "test"]) -> int:
    """Read a split size without baking dataset-specific counts into M7."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"invalid split manifest at {path}: {exc}") from exc
    if not isinstance(payload, Mapping):
        raise ValueError("split manifest must contain a JSON object")

    value: object | None = None
    splits = payload.get("splits")
    if isinstance(splits, Mapping) and split in splits:
        entry = splits[split]
        if isinstance(entry, Mapping):
            for key in (
                "expected_question_count",
                "question_count",
                "sample_count",
                "record_count",
            ):
                if key in entry:
                    value = entry[key]
                    break
        else:
            value = entry
    else:
        declared_split = payload.get("target_split", payload.get("split"))
        if declared_split != split:
            raise ValueError(
                f"split manifest describes {declared_split!r}, expected {split!r}"
            )
        for key in (
            "expected_question_count",
            "question_count",
            "sample_count",
            "record_count",
        ):
            if key in payload:
                value = payload[key]
                break

    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(
            f"split manifest does not declare a positive question count for {split}"
        )
    return value


def _parse_lambdas(raw: str) -> tuple[float, ...]:
    try:
        return _validate_lambdas(float(value.strip()) for value in raw.split(","))
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument(
        "--role-label-manifest",
        "--role-labels",
        dest="role_label_manifest",
        type=Path,
        required=True,
        help="M3 Role-label provenance manifest (legacy flag retained as an alias)",
    )
    parser.add_argument(
        "--split-manifest",
        type=Path,
        help="manifest declaring the expected Dev question count; required for formal runs",
    )
    parser.add_argument(
        "--input-status",
        choices=["fixture", "provisional", "formal"],
        required=True,
    )
    parser.add_argument("--lambdas", type=_parse_lambdas, default=DEFAULT_LAMBDAS)
    parser.add_argument("--metric-k", type=int, default=5)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    cases = load_lambda_cases(args.cases)
    role_package = load_role_label_package(args.role_label_manifest)
    if args.input_status == "formal":
        validate_formal_role_label_scope(role_package)
    if args.input_status == "formal" and args.split_manifest is None:
        raise ValueError("formal lambda search requires --split-manifest")
    expected_question_count = (
        load_expected_question_count(args.split_manifest, "dev")
        if args.split_manifest is not None
        else None
    )
    result = search_lambda(
        cases,
        role_package.labels,
        taxonomy_version=role_package.manifest.role_taxonomy_version,
        taxonomy_status="frozen",
        input_status=args.input_status,
        candidate_lambdas=args.lambdas,
        metric_k=args.metric_k,
        cases_sha256=sha256_file(args.cases),
        role_labels_sha256=role_package.manifest.labels_sha256,
        split_manifest_sha256=sha256_file(args.split_manifest)
        if args.split_manifest is not None
        else None,
        expected_question_count=expected_question_count,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    result_text = (
        f"{json.dumps(result.model_dump(), ensure_ascii=False, indent=2, sort_keys=True)}\n"
    )
    args.output.write_bytes(result_text.encode("utf-8"))
    print(args.output)


if __name__ == "__main__":
    main()
