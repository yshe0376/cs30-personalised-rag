"""Batch execution entry point for retrieval-only and generation runs."""

from __future__ import annotations

import inspect
import json
import uuid
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from cs30.citation import EvidenceContextBuilder, resolve_and_validate
from cs30.contracts import EvidenceBundle, GeneratedAnswer, RetrievalResult, StudentProfile

from .io import append_jsonl_record, load_inprogress_run_results, write_final_jsonl
from .manifest import RunManifest
from .models import (
    AbstentionCause,
    ErrorStage,
    EvaluationRunError,
    EvaluationRunResult,
    ExecutionMode,
    GoldSample,
    RunStatus,
)


def _method(target: object, name: str) -> Callable[..., Any]:
    candidate = getattr(target, name, None)
    if candidate is None:
        if callable(target):
            return target
        raise TypeError(f"runner dependency must provide {name}() or be callable")
    if not callable(candidate):
        raise TypeError(f"runner dependency {name} is not callable")
    return candidate


def _call_retriever(
    retriever: object,
    query: str,
    top_k: int,
    mode: object,
) -> RetrievalResult:
    method = _method(retriever, "retrieve")
    parameters = list(inspect.signature(method).parameters.values())
    positional = [
        parameter
        for parameter in parameters
        if parameter.kind
        in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    ]
    if any(parameter.kind is inspect.Parameter.VAR_POSITIONAL for parameter in parameters):
        return method(query, top_k, mode)
    if "mode" in inspect.signature(method).parameters:
        mode_parameter = inspect.signature(method).parameters["mode"]
        if mode_parameter.kind is inspect.Parameter.KEYWORD_ONLY:
            return method(query, top_k, mode=mode)
    if len(positional) >= 3:
        return method(query, top_k, mode)
    return method(query, top_k)


def _call_generator(
    generator: object,
    sample: GoldSample,
    profile: StudentProfile,
    retrieval: RetrievalResult,
) -> GeneratedAnswer:
    method = _method(generator, "generate")
    return method(sample.question, profile, retrieval)


def _trace_value(trace: object | None, *names: str, default: Any = None) -> Any:
    if trace is None:
        return default
    for name in names:
        value = getattr(trace, name, None)
        if value is not None:
            return value
    return default


def _safe_trace_calls(trace: object | None) -> int:
    """Read a non-negative model-call count without trusting a third-party trace."""

    value = _trace_value(trace, "attempts", "model_call_count", default=0)
    if isinstance(value, bool):
        return int(value)
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _safe_trace_text(trace: object | None, *names: str) -> str | None:
    value = _trace_value(trace, *names)
    return value if isinstance(value, str) and value else None


def _safe_trace_failures(trace: object | None) -> tuple[str, ...]:
    value = _trace_value(trace, "failure_types", default=())
    if isinstance(value, (list, tuple)):
        return tuple(str(item) for item in value)
    return ()


def _safe_prompt_trace(trace: object | None) -> tuple[list[str] | None, str | None]:
    """Keep prompt provenance only when the complete pair is structurally valid."""

    raw_ids = _trace_value(trace, "prompt_evidence_chunk_ids")
    raw_sha256 = _trace_value(trace, "prompt_sha256")
    if raw_ids is None and raw_sha256 is None:
        return None, None
    if not isinstance(raw_ids, (list, tuple)) or isinstance(raw_ids, str) or not raw_ids:
        return None, None
    prompt_ids = list(raw_ids)
    if (
        any(not isinstance(chunk_id, str) or not chunk_id.strip() for chunk_id in prompt_ids)
        or len(set(prompt_ids)) != len(prompt_ids)
    ):
        return None, None
    if (
        not isinstance(raw_sha256, str)
        or len(raw_sha256) != 64
        or any(character not in "0123456789abcdefABCDEF" for character in raw_sha256)
    ):
        return None, None
    return prompt_ids, raw_sha256


def _error(stage: ErrorStage, exc: Exception) -> EvaluationRunError:
    message = str(exc).strip() or type(exc).__name__
    return EvaluationRunError(
        stage=stage,
        error_type=type(exc).__name__,
        message=message,
    )


def _make_generation_error_result(
    *,
    run_id: str,
    sample: GoldSample,
    manifest: RunManifest,
    retrieval: RetrievalResult,
    evidence: object | None,
    trace: object | None,
    exc: Exception,
    stage: ErrorStage,
) -> EvaluationRunResult:
    """Build an error row while treating an external generator trace as untrusted."""

    safe_evidence = evidence if isinstance(evidence, EvidenceBundle) else None
    calls = _safe_trace_calls(trace)
    raw = _safe_trace_text(trace, "raw_model_output", "raw_output")
    repaired = _safe_trace_text(trace, "repaired_model_output", "repaired_output")
    prompt_ids, prompt_sha256 = _safe_prompt_trace(trace)
    if raw is None:
        repaired = None
    status = RunStatus.PARSE_ERROR if stage is ErrorStage.PARSING else RunStatus.GENERATION_ERROR
    try:
        return EvaluationRunResult(
            run_id=run_id,
            question_id=sample.question_id,
            condition_id=manifest.condition_id,
            execution_mode=manifest.execution_mode,
            status=status,
            retrieval=retrieval,
            evidence_sent_to_model=safe_evidence,
            raw_model_output=raw,
            repaired_model_output=repaired,
            final_answer=None,
            citation_validation=None,
            error=_error(stage, exc),
            model_call_count=calls,
            abstention_cause=None,
            # Malformed trace fields are discarded by _safe_prompt_trace;
            # valid prompt provenance remains useful on parse errors.
            prompt_evidence_chunk_ids=prompt_ids,
            prompt_sha256=prompt_sha256,
        )
    except Exception as validation_exc:
        # If the trace itself violates the parse-error contract (for example,
        # a non-string raw output), preserve the batch checkpoint as a minimal
        # generation error rather than raising from the error handler.
        return EvaluationRunResult(
            run_id=run_id,
            question_id=sample.question_id,
            condition_id=manifest.condition_id,
            execution_mode=manifest.execution_mode,
            status=RunStatus.GENERATION_ERROR,
            retrieval=retrieval,
            evidence_sent_to_model=None,
            raw_model_output=None,
            repaired_model_output=None,
            final_answer=None,
            citation_validation=None,
            error=_error(
                ErrorStage.GENERATION,
                RuntimeError(f"{exc}; invalid error trace: {validation_exc}"),
            ),
            model_call_count=0,
            abstention_cause=None,
            prompt_evidence_chunk_ids=None,
            prompt_sha256=None,
        )


def _empty_abstention(retrieval: RetrievalResult) -> tuple[GeneratedAnswer, object]:
    answer = GeneratedAnswer(
        explanation=(
            "The retriever returned no evidence, so a grounded answer cannot be given."
        ),
        abstained=True,
    )
    validated = resolve_and_validate(answer, EvidenceContextBuilder().build(retrieval))
    return answer, validated


def _make_run_id() -> str:
    return uuid.uuid4().hex[:12]


def _checkpoint_manifest_path(final: Path) -> Path:
    """Return the manifest sidecar used while a JSONL run is in progress."""

    return Path(str(final) + ".manifest.inprogress")


def _checkpoint_recovery_path(final: Path) -> Path:
    """Return the persistent audit marker for checkpoint recovery."""

    return Path(str(final) + ".recovery.json")


def _write_checkpoint_manifest(path: Path, manifest: RunManifest) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _load_checkpoint_manifest(path: Path) -> RunManifest:
    try:
        return RunManifest.model_validate_json(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(f"invalid checkpoint manifest: {path}") from exc


def _run_one(
    sample: GoldSample,
    manifest: RunManifest,
    retriever: object,
    *,
    generator: object | None,
    profile_provider: Callable[[GoldSample], StudentProfile] | None,
    evidence_builder: Callable[[RetrievalResult], object] | None,
    require_generation_trace: bool,
) -> EvaluationRunResult:
    run_id = _make_run_id()
    try:
        retrieval = RetrievalResult.model_validate(
            _call_retriever(
                retriever,
                sample.question,
                manifest.top_k,
                manifest.retrieval_mode,
            )
        )
    except Exception as exc:
        return EvaluationRunResult(
            run_id=run_id,
            question_id=sample.question_id,
            condition_id=manifest.condition_id,
            execution_mode=manifest.execution_mode,
            status=RunStatus.RETRIEVAL_ERROR,
            retrieval=None,
            evidence_sent_to_model=None,
            raw_model_output=None,
            repaired_model_output=None,
            final_answer=None,
            citation_validation=None,
            error=_error(ErrorStage.RETRIEVAL, exc),
            model_call_count=0,
            abstention_cause=None,
        )

    if manifest.execution_mode is ExecutionMode.RETRIEVAL_ONLY:
        return EvaluationRunResult(
            run_id=run_id,
            question_id=sample.question_id,
            condition_id=manifest.condition_id,
            execution_mode=manifest.execution_mode,
            status=RunStatus.RETRIEVED,
            retrieval=retrieval,
            evidence_sent_to_model=None,
            raw_model_output=None,
            repaired_model_output=None,
            final_answer=None,
            citation_validation=None,
            error=None,
            model_call_count=0,
            abstention_cause=None,
        )

    if generator is None or profile_provider is None:
        raise ValueError("generation runs require generator and profile_provider")
    if not retrieval.hits:
        answer, validated = _empty_abstention(retrieval)
        return EvaluationRunResult(
            run_id=run_id,
            question_id=sample.question_id,
            condition_id=manifest.condition_id,
            execution_mode=manifest.execution_mode,
            status=RunStatus.ABSTAINED,
            retrieval=retrieval,
            evidence_sent_to_model=None,
            raw_model_output=None,
            repaired_model_output=None,
            final_answer=answer,
            citation_validation=validated,
            error=None,
            model_call_count=0,
            abstention_cause=AbstentionCause.NO_RETRIEVAL_HITS,
        )

    previous_trace = getattr(generator, "last_trace", None)
    try:
        generator.last_trace = None  # type: ignore[attr-defined]
    except (AttributeError, TypeError):
        # A third-party generator may expose a read-only trace property.  The
        # identity check below still prevents reusing that property's old value.
        pass
    evidence: object | None = None
    trace: object | None = None
    try:
        evidence = (
            evidence_builder(retrieval)
            if evidence_builder is not None
            else EvidenceContextBuilder().build(retrieval)
        )
        profile = profile_provider(sample)
        answer = _call_generator(generator, sample, profile, retrieval)
        trace = getattr(generator, "last_trace", None)
        if trace is previous_trace:
            trace = None
        calls = _safe_trace_calls(trace)
        raw = _safe_trace_text(trace, "raw_model_output", "raw_output")
        repaired = _safe_trace_text(trace, "repaired_model_output", "repaired_output")
        prompt_ids, prompt_sha256 = _safe_prompt_trace(trace)
        if trace is None and require_generation_trace:
            raise RuntimeError(
                "generation dependency must expose last_trace with raw model output"
            )
        if raw is None and not require_generation_trace:
            raw = answer.model_dump_json()
            calls = max(calls, 1)
        validated = resolve_and_validate(answer, evidence)  # type: ignore[arg-type]
        return EvaluationRunResult(
            run_id=run_id,
            question_id=sample.question_id,
            condition_id=manifest.condition_id,
            execution_mode=manifest.execution_mode,
            status=RunStatus.ABSTAINED if answer.abstained else RunStatus.ANSWERED,
            retrieval=retrieval,
            evidence_sent_to_model=evidence,  # type: ignore[arg-type]
            raw_model_output=raw,
            repaired_model_output=repaired,
            final_answer=answer,
            citation_validation=validated,
            error=None,
            model_call_count=calls,
            abstention_cause=(
                AbstentionCause.MODEL_ABSTAINED_WITH_EVIDENCE if answer.abstained else None
            ),
            prompt_evidence_chunk_ids=prompt_ids,
            prompt_sha256=prompt_sha256,
        )
    except Exception as exc:
        trace = trace or getattr(generator, "last_trace", None)
        if trace is previous_trace:
            trace = None
        failures = _safe_trace_failures(trace)
        stage = (
            ErrorStage.PARSING
            if failures and failures[-1] == "LLMOutputValidationError"
            else ErrorStage.GENERATION
        )
        return _make_generation_error_result(
            run_id=run_id,
            sample=sample,
            manifest=manifest,
            retrieval=retrieval,
            evidence=evidence,
            trace=trace,
            exc=exc,
            stage=stage,
        )


def run_batch(
    gold_samples: Sequence[GoldSample],
    manifest: RunManifest,
    retriever: object,
    *,
    generator: object | None = None,
    profile_provider: Callable[[GoldSample], StudentProfile] | None = None,
    evidence_builder: Callable[[RetrievalResult], object] | None = None,
    output_path: str | Path | None = None,
    resume: bool = False,
    require_generation_trace: bool = True,
) -> list[EvaluationRunResult]:
    """Run each gold question and checkpoint after every completed question."""

    if not require_generation_trace and manifest.reportable:
        raise ValueError("synthetic generation traces require a non-reportable manifest")
    if not require_generation_trace and not manifest.synthetic_trace:
        raise ValueError(
            "synthetic generation traces require manifest.synthetic_trace=True"
        )
    if require_generation_trace and manifest.synthetic_trace:
        raise ValueError(
            "manifest.synthetic_trace=True requires require_generation_trace=False"
        )

    if manifest.reportable:
        # Keep the formal-run guard at the batch boundary as well as in the
        # offline scorer.  A caller using the Python API must not bypass the
        # reviewed, corpus-bound Gold requirement by skipping the CLI.
        from .scoring import assert_reportable_gold

        assert_reportable_gold(gold_samples)

    question_ids = [sample.question_id for sample in gold_samples]
    if len(question_ids) != len(set(question_ids)):
        raise ValueError("gold_samples contain duplicate question_id values")

    existing: list[EvaluationRunResult] = []
    checkpoint: Path | None = None
    checkpoint_manifest: Path | None = None
    checkpoint_recovery: Path | None = None
    final: Path | None = Path(output_path) if output_path is not None else None
    if final is not None:
        if final.name.endswith(".inprogress"):
            raise ValueError("output_path must name a completed run, not an .inprogress file")
        if final.exists():
            raise FileExistsError(f"completed run already exists: {final}")
        checkpoint = Path(str(final) + ".inprogress")
        checkpoint_manifest = _checkpoint_manifest_path(final)
        checkpoint_recovery = _checkpoint_recovery_path(final)
        if checkpoint.exists():
            if not resume:
                raise FileExistsError(
                    f"an unfinished run exists; pass resume=True: {checkpoint}"
                )
            if not checkpoint_manifest.exists():
                raise ValueError(
                    "cannot safely resume without the in-progress manifest sidecar"
                )
            saved_manifest = _load_checkpoint_manifest(checkpoint_manifest)
            if saved_manifest.model_dump(mode="json") != manifest.model_dump(mode="json"):
                raise ValueError("in-progress results do not match the current manifest")
            existing = load_inprogress_run_results(
                checkpoint,
                recovery_log=checkpoint_recovery,
            )
            if any(
                result.condition_id != manifest.condition_id
                or result.execution_mode is not manifest.execution_mode
                for result in existing
            ):
                raise ValueError("in-progress results do not match the current manifest")
            if any(result.question_id not in question_ids for result in existing):
                raise ValueError("in-progress results contain a question outside this batch")
        elif resume:
            raise FileNotFoundError(f"no in-progress run to resume: {checkpoint}")
        else:
            if checkpoint_manifest.exists():
                raise FileExistsError(
                    f"a stale in-progress manifest exists; inspect before reusing: "
                    f"{checkpoint_manifest}"
                )
            _write_checkpoint_manifest(checkpoint_manifest, manifest)

    completed_questions = {result.question_id for result in existing}
    results = list(existing)
    for sample in gold_samples:
        if sample.question_id in completed_questions:
            continue
        result = _run_one(
            sample,
            manifest,
            retriever,
            generator=generator,
            profile_provider=profile_provider,
            evidence_builder=evidence_builder,
            require_generation_trace=require_generation_trace,
        )
        results.append(result)
        completed_questions.add(sample.question_id)
        if checkpoint is not None:
            append_jsonl_record(checkpoint, result)

    if checkpoint is not None and final is not None:
        write_final_jsonl(checkpoint, final)
        assert checkpoint_manifest is not None
        checkpoint_manifest.unlink(missing_ok=True)
    return results


run_evaluation = run_batch
