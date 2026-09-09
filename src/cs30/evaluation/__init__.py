"""Evaluation data contracts and stable JSONL loading helpers."""

from .io import load_gold_samples, load_run_results
from .models import (
    AnnotationStatus,
    ErrorStage,
    EvaluationRunError,
    EvaluationRunResult,
    EvaluationSplit,
    GoldEvidenceSpan,
    GoldSample,
    PersonalisationEligibility,
    RunStatus,
)

__all__ = [
    "AnnotationStatus",
    "ErrorStage",
    "EvaluationRunError",
    "EvaluationRunResult",
    "EvaluationSplit",
    "GoldEvidenceSpan",
    "GoldSample",
    "PersonalisationEligibility",
    "RunStatus",
    "load_gold_samples",
    "load_run_results",
]
