import json
import sys

import pytest

from cs30.contracts import (
    EvidenceProvenance,
    RetrievalHit,
    RetrievalMode,
    RetrievalResult,
    StudentLevel,
    StudentProfile,
)
from cs30.generation import MockJsonLLMClient
from cs30.generation.exceptions import LLMProviderError
from cs30.generation.experiment import (
    ConditionExperimentCase,
    run_condition_experiment,
    write_condition_experiment,
)
from cs30.generation.experiment import main as experiment_main
from cs30.generation.lambda_search import LambdaSearchCase, search_lambda
from cs30.generation.reranking import EvidenceRole, RoleLabel


def _retrieval(*, formal: bool = False) -> RetrievalResult:
    mode = RetrievalMode.HYBRID if formal else RetrievalMode.FIXTURE
    return RetrievalResult(
        query="What is acceleration?",
        mode=mode,
        hits=[
            RetrievalHit(
                chunk_id="derivation",
                text="From F = ma, acceleration follows from net force.",
                chapter_id="forces",
                source="fixture://condition-run",
                score=1.0,
                rank=1,
                retriever_type=mode,
            ),
            RetrievalHit(
                chunk_id="definition",
                text="Acceleration is the rate of change of velocity.",
                chapter_id="motion",
                source="fixture://condition-run",
                score=0.8,
                rank=2,
                retriever_type=mode,
            ),
        ],
        provenance=EvidenceProvenance(
            corpus_hash="corpus-hash",
            chunk_config_hash="chunk-hash",
            embedding_model="embedding-model",
            index_version="index-v1",
        )
        if formal
        else None,
    )


def _profile() -> StudentProfile:
    return StudentProfile(
        profile_id="run-beginner",
        level=StudentLevel.BEGINNER,
        confidence=1.0,
    )


def _labels() -> dict[str, RoleLabel]:
    return {
        "derivation": RoleLabel.single(EvidenceRole.DERIVATION, source="m3-v1"),
        "definition": RoleLabel.single(EvidenceRole.DEFINITION, source="m3-v1"),
    }


def _selected(*, formal: bool, role_hash: str | None = None):
    if formal:
        cases = [
            LambdaSearchCase(
                question_id=f"q-{question_index:02d}",
                profile=StudentProfile(
                    profile_id=f"q-{question_index:02d}-{level.value}",
                    level=level,
                    confidence=1.0,
                ),
                retrieval=_retrieval(formal=True),
                relevant_chunk_ids=frozenset({"definition"}),
                source_split="dev",
                source_reportable=True,
                source_manifest_sha256="d" * 64,
            )
            for question_index in range(60)
            for level in StudentLevel
        ]
    else:
        cases = [
            LambdaSearchCase(
                question_id="q-1",
                profile=_profile(),
                retrieval=_retrieval(),
                relevant_chunk_ids=frozenset({"definition"}),
            )
        ]
    return search_lambda(
        cases,
        _labels(),
        taxonomy_version="m3-role-v1" if formal else "fixture-v1",
        taxonomy_status="frozen" if formal else "fixture",
        input_status="formal" if formal else "fixture",
        candidate_lambdas=(0.0, 0.5, 1.0),
        cases_sha256="a" * 64 if formal else None,
        role_labels_sha256=(role_hash or "b" * 64) if formal else role_hash,
    ).selected


def _case() -> ConditionExperimentCase:
    return ConditionExperimentCase(
        question_id="q-1",
        split="dev",
        question="What is acceleration?",
        profile=_profile(),
        retrieval=_retrieval(),
    )


def test_experiment_saves_four_attributable_rows_and_manifest(tmp_path) -> None:
    output = run_condition_experiment(
        [_case()],
        _labels(),
        _selected(formal=False),
        MockJsonLLMClient(),
        input_status="fixture",
        cases_sha256="cases-hash",
        role_labels_sha256="roles-hash",
        selected_lambda_sha256="lambda-hash",
        git_commit="abc123",
    )

    assert output.manifest["reportable"] is False
    assert output.manifest["question_count"] == 1
    assert output.manifest["row_count"] == 4
    assert len(output.rows) == 4
    assert {row["condition_id"] for row in output.rows} == {
        "P0R0_plain",
        "P1R0_prompt_only",
        "P0R1_reranking_only",
        "P1R1_combined",
    }
    assert len({tuple(row["input_candidate_ids"]) for row in output.rows}) == 1
    assert len({row["generation_trace"]["generation_model"] for row in output.rows}) == 1
    assert all(row["run_id"] == output.manifest["run_id"] for row in output.rows)

    write_condition_experiment(tmp_path, output)
    saved_rows = [
        json.loads(line)
        for line in (tmp_path / "four_condition_results.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    saved_manifest = json.loads((tmp_path / "run_manifest.json").read_text(encoding="utf-8"))
    assert len(saved_rows) == 4
    assert saved_manifest["run_id"] == output.manifest["run_id"]


def test_formal_run_rejects_provisional_lambda() -> None:
    with pytest.raises(ValueError, match="frozen lambda"):
        run_condition_experiment(
            [_case()],
            _labels(),
            _selected(formal=False),
            MockJsonLLMClient(),
            input_status="formal",
        )


def test_role_label_hash_must_match_lambda_selection() -> None:
    with pytest.raises(ValueError, match="role labels do not match"):
        run_condition_experiment(
            [_case()],
            _labels(),
            _selected(formal=True, role_hash="b" * 64),
            MockJsonLLMClient(),
            input_status="formal",
            role_labels_sha256="c" * 64,
        )


def test_mock_provider_never_produces_a_reportable_provisional_run() -> None:
    output = run_condition_experiment(
        [_case()],
        _labels(),
        _selected(formal=True),
        MockJsonLLMClient(),
        input_status="provisional",
    )

    assert output.manifest["reportable"] is False
    assert "Engineering/provisional" in str(output.manifest["warning"])


def test_formal_run_enforces_required_question_count() -> None:
    with pytest.raises(ValueError, match="exactly 60 unique questions"):
        run_condition_experiment(
            [
                ConditionExperimentCase(
                    question_id="q-1",
                    split="dev",
                    question="What is acceleration?",
                    profile=_profile(),
                    retrieval=_retrieval(formal=True),
                    source_split="dev",
                    source_reportable=True,
                    source_manifest_sha256="d" * 64,
                )
            ],
            _labels(),
            _selected(formal=True, role_hash="b" * 64),
            MockJsonLLMClient(),
            input_status="formal",
            cases_sha256="a" * 64,
            role_labels_sha256="b" * 64,
            selected_lambda_sha256="c" * 64,
        )


def test_provider_failures_are_isolated_and_saved_for_every_condition() -> None:
    class FailingClient:
        model = "failing-provider"
        temperature = 0.0

        def complete(self, prompt: str, text_format: dict):
            del prompt, text_format
            raise LLMProviderError("provider unavailable")

    output = run_condition_experiment(
        [_case()],
        _labels(),
        _selected(formal=False),
        FailingClient(),  # type: ignore[arg-type]
        input_status="fixture",
    )

    assert output.manifest["failed_row_count"] == 4
    assert output.manifest["completed_row_count"] == 0
    assert len(output.rows) == 4
    assert all(row["status"] == "failed" for row in output.rows)
    assert all(row["error"]["type"] == "GenerationError" for row in output.rows)
    assert output.rows[2]["rerank_trace"] is not None


def test_experiment_cli_writes_results_and_manifest(tmp_path, monkeypatch) -> None:
    cases_path = tmp_path / "cases.jsonl"
    labels_path = tmp_path / "roles.jsonl"
    lambda_path = tmp_path / "lambda.json"
    output_dir = tmp_path / "output"
    cases_path.write_text(
        json.dumps(
            {
                "question_id": "q-1",
                "split": "dev",
                "question": "What is acceleration?",
                "profile": _profile().model_dump(mode="json"),
                "retrieval": _retrieval().model_dump(mode="json"),
            }
        )
        + "\n",
        encoding="utf-8",
    )
    labels_path.write_text(
        "".join(
            json.dumps(
                {
                    "chunk_id": chunk_id,
                    "roles": [label.roles[0].value],
                    "source": label.source,
                }
            )
            + "\n"
            for chunk_id, label in _labels().items()
        ),
        encoding="utf-8",
    )
    lambda_path.write_text(
        json.dumps(_selected(formal=False).model_dump()) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "cs30.generation.experiment",
            "--cases",
            str(cases_path),
            "--role-labels",
            str(labels_path),
            "--selected-lambda",
            str(lambda_path),
            "--input-status",
            "fixture",
            "--provider",
            "mock",
            "--output-dir",
            str(output_dir),
        ],
    )

    experiment_main()

    assert len((output_dir / "four_condition_results.jsonl").read_text().splitlines()) == 4
    manifest = json.loads((output_dir / "run_manifest.json").read_text())
    assert manifest["reportable"] is False
    assert manifest["failed_row_count"] == 0
