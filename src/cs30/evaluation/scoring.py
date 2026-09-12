"""Stable offline scoring seam shared with M8."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol, runtime_checkable

from .manifest import RunManifest
from .mapping import GoldChunkMapping, QuestionChunkMapping
from .metrics import compute_retrieval_metrics, validate_artifact_compatibility
from .models import (
    AnnotationStatus,
    EvaluationRunResult,
    GoldSample,
    SpanResolutionStatus,
)


@runtime_checkable
class ScoringExtension(Protocol):
    """M8-compatible plug-in for answer, refusal, format, or citation metrics."""

    name: str

    def score(
        self,
        gold_samples: Sequence[GoldSample],
        run_results: Sequence[EvaluationRunResult],
    ) -> Mapping[str, Any]: ...


def assert_reportable_gold(gold_samples: Sequence[GoldSample]) -> None:
    """Reject formal evaluation unless Gold is reviewed and corpus-bound."""

    for sample in gold_samples:
        if sample.annotation_status is not AnnotationStatus.REVIEWED:
            raise ValueError(
                "reportable Gold requires annotation_status=reviewed; "
                f"sample {sample.question_id} is not reportable"
            )
        spans = (
            span
            for evidence_set in sample.gold_core_evidence_sets
            for span in evidence_set
        )
        for span in (*spans, *sample.partial_evidence):
            if (
                span.resolution_status is not SpanResolutionStatus.RESOLVED
                or span.corpus_char_start is None
                or span.corpus_char_end is None
            ):
                raise ValueError(
                    "reportable Gold requires every span to be resolved with global "
                    f"coordinates; span {span.span_id} is not reportable"
                )


def run_scoring_extensions(
    extensions: Sequence[ScoringExtension],
    gold_samples: Sequence[GoldSample],
    run_results: Sequence[EvaluationRunResult],
) -> dict[str, Mapping[str, Any]]:
    """Run registered M8 extensions against saved results only."""

    names: set[str] = set()
    output: dict[str, Mapping[str, Any]] = {}
    for extension in extensions:
        if extension.name in names:
            raise ValueError(f"duplicate scoring extension name: {extension.name!r}")
        names.add(extension.name)
        output[extension.name] = extension.score(gold_samples, run_results)
    return output


def score_saved_run(
    gold_samples: list[GoldSample],
    run_results: list[EvaluationRunResult],
    mappings: GoldChunkMapping | dict[str, QuestionChunkMapping],
    *,
    k_values: list[int],
    top_k: int | None = None,
    extensions: Sequence[ScoringExtension] = (),
    manifest: RunManifest | None = None,
    strict_mapping: bool | None = None,
) -> dict[str, Any]:
    """Compute retrieval metrics and optional M8 metrics without model calls."""

    question_ids = {result.question_id for result in run_results}
    if manifest is not None:
        if any(
            result.condition_id != manifest.condition_id
            or result.execution_mode is not manifest.execution_mode
            for result in run_results
        ):
            raise ValueError("saved results do not match the supplied manifest")
        validate_artifact_compatibility(
            gold_samples,
            mappings,
            manifest=manifest,
            question_ids=question_ids,
        )
        if manifest.reportable and manifest.mapping_version is None:
            raise ValueError(
                "reportable manifests must record mapping_version before scoring"
            )
        if manifest.reportable:
            assert_reportable_gold(gold_samples)
    else:
        validate_artifact_compatibility(
            gold_samples,
            mappings,
            question_ids=question_ids,
        )
    if strict_mapping is None:
        strict_mapping = bool(manifest is not None and manifest.reportable)
    if top_k is None and manifest is not None:
        top_k = manifest.top_k

    retrieval = compute_retrieval_metrics(
        gold_samples,
        run_results,
        mappings,
        k_values=k_values,
        top_k=top_k,
        strict_mapping=strict_mapping,
    )
    return {
        "retrieval": retrieval.model_dump(),
        "extensions": run_scoring_extensions(extensions, gold_samples, run_results),
    }
