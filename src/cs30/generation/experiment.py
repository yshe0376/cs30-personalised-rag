"""Run Member 7's four conditions from frozen candidates and save a manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from cs30.contracts import RetrievalMode, RetrievalResult, StudentLevel, StudentProfile
from cs30.errors import GenerationError

from .client import LLMClient, MockJsonLLMClient, OllamaChatClient, OpenAIResponsesClient
from .conditions import FourConditionRunner, GenerationCondition
from .evidence import evidence_items
from .generator import PersonalisedAnswerGenerator
from .lambda_search import (
    InputStatus,
    SelectedLambdaConfig,
    is_sha256,
    load_role_labels,
    sha256_file,
)
from .prompt import PromptBuilder
from .reranking import LevelAwareReranker, RerankConfig, RoleLabel


@dataclass(frozen=True)
class ConditionExperimentCase:
    question_id: str
    split: Literal["dev", "test"]
    question: str
    profile: StudentProfile
    retrieval: RetrievalResult
    source_split: str = "fixture"
    source_reportable: bool = False
    source_manifest_sha256: str | None = None

    def __post_init__(self) -> None:
        question_id = self.question_id.strip()
        question = self.question.strip()
        if not question_id:
            raise ValueError("question_id must not be empty")
        if not question:
            raise ValueError("question must not be empty")
        if self.split not in {"dev", "test"}:
            raise ValueError("condition experiment split must be dev or test")
        if not self.retrieval.hits:
            raise ValueError("condition experiment requires at least one candidate")
        if not self.source_split.strip():
            raise ValueError("source_split must not be empty")
        object.__setattr__(self, "question_id", question_id)
        object.__setattr__(self, "question", question)

    @property
    def case_id(self) -> str:
        return f"{self.question_id}:{self.profile.profile_id}"


@dataclass(frozen=True)
class ConditionExperimentOutput:
    manifest: dict[str, object]
    rows: tuple[dict[str, object], ...]


def load_condition_cases(path: Path) -> list[ConditionExperimentCase]:
    cases: list[ConditionExperimentCase] = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            payload = json.loads(raw)
            source_reportable = payload.get("source_reportable", False)
            if not isinstance(source_reportable, bool):
                raise ValueError("source_reportable must be a boolean")
            cases.append(
                ConditionExperimentCase(
                    question_id=payload["question_id"],
                    split=payload["split"],
                    question=payload["question"],
                    profile=StudentProfile.model_validate(payload["profile"]),
                    retrieval=RetrievalResult.model_validate(payload["retrieval"]),
                    source_split=payload.get("source_split", "fixture"),
                    source_reportable=source_reportable,
                    source_manifest_sha256=payload.get("source_manifest_sha256"),
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"invalid condition case at {path}:{line_number}: {exc}") from exc
    if not cases:
        raise ValueError(f"no condition cases found in {path}")
    case_ids = [case.case_id for case in cases]
    if len(set(case_ids)) != len(case_ids):
        raise ValueError("condition experiment case_id values must be unique")
    return cases


def load_selected_lambda(path: Path) -> SelectedLambdaConfig:
    payload = json.loads(path.read_text(encoding="utf-8"))
    selected = payload.get("selected_config", payload)
    if not isinstance(selected, Mapping):
        raise ValueError("selected lambda file must contain an object")
    return SelectedLambdaConfig.model_validate(selected)


def _manifest_id(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"member7-four-condition-{hashlib.sha256(encoded).hexdigest()[:16]}"


def _validate_formal_run(
    cases: Sequence[ConditionExperimentCase],
    role_labels: Mapping[str, RoleLabel],
) -> None:
    by_split: dict[str, dict[str, list[ConditionExperimentCase]]] = {}
    for case in cases:
        by_split.setdefault(case.split, {}).setdefault(case.question_id, []).append(case)
        if case.retrieval.mode is RetrievalMode.FIXTURE or case.retrieval.provenance is None:
            raise ValueError("formal condition runs require non-fixture retrieval provenance")
        if (
            case.source_split != case.split
            or not case.source_reportable
            or case.source_manifest_sha256 is None
        ):
            raise ValueError(
                "formal condition runs require a reportable matching source manifest"
            )

    required_counts = {"dev": 60, "test": 180}
    expected_levels = set(StudentLevel)
    for split, by_question in by_split.items():
        expected_count = required_counts[split]
        if len(by_question) != expected_count:
            raise ValueError(
                f"formal {split} run requires exactly {expected_count} unique questions; "
                f"found {len(by_question)}"
            )
        for question_id, question_cases in by_question.items():
            levels = {case.profile.level for case in question_cases}
            if levels != expected_levels:
                raise ValueError(
                    "formal condition runs require all three profile levels for "
                    f"{question_id}"
                )
            retrieval_payloads = {
                case.retrieval.model_dump_json(exclude_none=False) for case in question_cases
            }
            if len(retrieval_payloads) != 1:
                raise ValueError(
                    "all conditions and profile levels must start from identical candidates "
                    f"for {question_id}"
                )

    candidate_ids = {hit.chunk_id for case in cases for hit in case.retrieval.hits}
    missing = sorted(candidate_ids - role_labels.keys())
    if missing:
        preview = ", ".join(missing[:5])
        raise ValueError(f"formal condition run is missing Role labels for: {preview}")
    invalid = sorted(
        chunk_id
        for chunk_id in candidate_ids
        if len(role_labels[chunk_id].roles) != 1 or role_labels[chunk_id].source == "fixture"
    )
    if invalid:
        raise ValueError(
            "formal condition run requires one non-fixture Role label per candidate: "
            f"{', '.join(invalid[:5])}"
        )


def run_condition_experiment(
    cases: Sequence[ConditionExperimentCase],
    role_labels: Mapping[str, RoleLabel],
    selected_lambda: SelectedLambdaConfig,
    client: LLMClient,
    *,
    input_status: InputStatus,
    cases_sha256: str | None = None,
    role_labels_sha256: str | None = None,
    selected_lambda_sha256: str | None = None,
    git_commit: str | None = None,
) -> ConditionExperimentOutput:
    if not cases:
        raise ValueError("condition experiment requires at least one case")
    if input_status not in {"fixture", "provisional", "formal"}:
        raise ValueError("input_status must be fixture, provisional, or formal")
    if selected_lambda.taxonomy_version.strip() == "":
        raise ValueError("selected lambda taxonomy_version must not be empty")
    if selected_lambda.role_labels_sha256 and role_labels_sha256:
        if selected_lambda.role_labels_sha256 != role_labels_sha256:
            raise ValueError("role labels do not match the selected lambda provenance")
    if input_status == "formal" and selected_lambda.selection_status != "frozen":
        raise ValueError("formal condition runs require a frozen lambda config")
    if input_status == "formal":
        if not all(
            is_sha256(value)
            for value in (cases_sha256, role_labels_sha256, selected_lambda_sha256)
        ):
            raise ValueError("formal condition runs require SHA-256 input digests")
        _validate_formal_run(cases, role_labels)

    reranker = LevelAwareReranker(
        role_labels,
        config=RerankConfig(
            lambda_weight=selected_lambda.lambda_weight,
            parameter_source="dev",
            taxonomy_status=selected_lambda.taxonomy_status,
            taxonomy_version=selected_lambda.taxonomy_version,
        ),
    )
    runner = FourConditionRunner(PersonalisedAnswerGenerator(client), reranker)
    rows: list[dict[str, object]] = []
    for case in cases:
        for condition in GenerationCondition:
            try:
                result = runner.run(case.question, case.profile, case.retrieval, condition)
            except GenerationError as exc:
                prepared = case.retrieval
                rerank_trace = None
                if condition.reranking:
                    reranked = reranker.rerank(case.retrieval, case.profile)
                    prepared = reranked.evidence
                    rerank_trace = reranked.trace.model_dump()
                generation_trace = runner.generator.last_trace
                rows.append(
                    {
                        "schema_version": "1.0",
                        "question_id": case.question_id,
                        "case_id": case.case_id,
                        "split": case.split,
                        "status": "failed",
                        "condition": condition.value,
                        "condition_id": condition.condition_id,
                        "prompt_personalisation": condition.prompt_personalisation,
                        "reranking": condition.reranking,
                        "profile_snapshot": case.profile.model_dump(mode="json"),
                        "input_candidate_ids": [
                            item.chunk_id for item in evidence_items(case.retrieval)
                        ],
                        "output_candidate_ids": [
                            item.chunk_id for item in evidence_items(prepared)
                        ],
                        "answer": None,
                        "generation_trace": generation_trace.model_dump()
                        if generation_trace
                        else None,
                        "rerank_trace": rerank_trace,
                        "error": {
                            "type": type(exc).__name__,
                            "message": str(exc),
                        },
                    }
                )
                continue
            rows.append(
                {
                    "schema_version": "1.0",
                    "question_id": case.question_id,
                    "case_id": case.case_id,
                    "split": case.split,
                    "status": "completed",
                    **result.model_dump(),
                    "error": None,
                }
            )

    formal_provider = not isinstance(client, MockJsonLLMClient)
    reportable = (
        input_status == "formal"
        and selected_lambda.reportable
        and selected_lambda.taxonomy_status == "frozen"
        and formal_provider
    )
    failed_row_count = sum(row["status"] == "failed" for row in rows)
    identity_payload: dict[str, object] = {
        "schema_version": "1.0",
        "result_type": "member7_four_condition_run",
        "input_status": input_status,
        "reportable": reportable,
        "question_count": len(cases),
        "row_count": len(rows),
        "completed_row_count": len(rows) - failed_row_count,
        "failed_row_count": failed_row_count,
        "splits": sorted({case.split for case in cases}),
        "case_ids": sorted(case.case_id for case in cases),
        "conditions": [condition.condition_id for condition in GenerationCondition],
        "model": client.model,
        "temperature": client.temperature,
        "prompt_versions": [
            PromptBuilder.base_prompt_version,
            PromptBuilder.prompt_version,
        ],
        "selected_lambda_config_id": selected_lambda.config_id,
        "lambda_weight": selected_lambda.lambda_weight,
        "lambda_parameter_source": "dev",
        "taxonomy_status": selected_lambda.taxonomy_status,
        "taxonomy_version": selected_lambda.taxonomy_version,
        "cases_sha256": cases_sha256,
        "role_labels_sha256": role_labels_sha256,
        "selected_lambda_sha256": selected_lambda_sha256,
        "git_commit": git_commit,
    }
    manifest = {
        **identity_payload,
        "run_id": _manifest_id(identity_payload),
        "warning": None
        if reportable
        else "Engineering/provisional run; do not use as a formal model-effectiveness result.",
    }
    run_id = manifest["run_id"]
    for row in rows:
        row["run_id"] = run_id
    return ConditionExperimentOutput(manifest=manifest, rows=tuple(rows))


def write_condition_experiment(output_dir: Path, output: ConditionExperimentOutput) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows_path = output_dir / "four_condition_results.jsonl"
    manifest_path = output_dir / "run_manifest.json"
    rows_path.write_text(
        "".join(
            f"{json.dumps(row, ensure_ascii=False, sort_keys=True)}\n" for row in output.rows
        ),
        encoding="utf-8",
    )
    manifest_path.write_text(
        f"{json.dumps(output.manifest, ensure_ascii=False, indent=2, sort_keys=True)}\n",
        encoding="utf-8",
    )


def _client(provider: str, model: str | None) -> LLMClient:
    if provider == "mock":
        return MockJsonLLMClient()
    if provider == "ollama":
        return OllamaChatClient(model or "gpt-oss:20b")
    if not model:
        raise ValueError("--model is required with --provider openai")
    return OpenAIResponsesClient(model)


def _git_commit() -> str | None:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--role-labels", type=Path, required=True)
    parser.add_argument("--selected-lambda", type=Path, required=True)
    parser.add_argument(
        "--input-status",
        choices=["fixture", "provisional", "formal"],
        required=True,
    )
    parser.add_argument("--provider", choices=["mock", "ollama", "openai"], default="mock")
    parser.add_argument("--model", default=None)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    selected_lambda = load_selected_lambda(args.selected_lambda)
    role_labels = load_role_labels(
        args.role_labels,
        expected_taxonomy_version=selected_lambda.taxonomy_version
        if selected_lambda.taxonomy_status == "frozen"
        else None,
    )
    output = run_condition_experiment(
        load_condition_cases(args.cases),
        role_labels,
        selected_lambda,
        _client(args.provider, args.model),
        input_status=args.input_status,
        cases_sha256=sha256_file(args.cases),
        role_labels_sha256=sha256_file(args.role_labels),
        selected_lambda_sha256=sha256_file(args.selected_lambda),
        git_commit=_git_commit(),
    )
    write_condition_experiment(args.output_dir, output)
    print(args.output_dir)


if __name__ == "__main__":
    main()
