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
from cs30.generation.lambda_search import (
    LambdaSearchCase,
    SelectedLambdaConfig,
    load_role_labels,
    search_lambda,
)
from cs30.generation.lambda_search import main as lambda_search_main
from cs30.generation.reranking import EvidenceRole, RoleLabel


def _retrieval(*, formal: bool = False) -> RetrievalResult:
    mode = RetrievalMode.HYBRID if formal else RetrievalMode.FIXTURE
    return RetrievalResult(
        query="Why does a net force accelerate an object?",
        mode=mode,
        hits=[
            RetrievalHit(
                chunk_id="derivation",
                text="From F = ma, acceleration follows from net force.",
                chapter_id="forces",
                source="fixture://lambda-search",
                score=1.0,
                rank=1,
                retriever_type=mode,
            ),
            RetrievalHit(
                chunk_id="definition",
                text="Acceleration is the rate of change of velocity.",
                chapter_id="motion",
                source="fixture://lambda-search",
                score=0.8,
                rank=2,
                retriever_type=mode,
            ),
            RetrievalHit(
                chunk_id="application",
                text="A larger net force produces a larger acceleration.",
                chapter_id="forces",
                source="fixture://lambda-search",
                score=0.2,
                rank=3,
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
        profile_id="dev-beginner",
        level=StudentLevel.BEGINNER,
        confidence=1.0,
    )


def _case() -> LambdaSearchCase:
    return LambdaSearchCase(
        question_id="q-1",
        profile=_profile(),
        retrieval=_retrieval(),
        relevant_chunk_ids=frozenset({"definition"}),
    )


def _labels() -> dict[str, RoleLabel]:
    return {
        "derivation": RoleLabel.single(EvidenceRole.DERIVATION, source="m3-v1"),
        "definition": RoleLabel.single(EvidenceRole.DEFINITION, source="m3-v1"),
        "application": RoleLabel.single(EvidenceRole.APPLICATION, source="m3-v1"),
    }


def _formal_cases() -> list[LambdaSearchCase]:
    return [
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


def test_search_selects_smallest_lambda_that_maximises_dev_mrr() -> None:
    result = search_lambda(
        _formal_cases(),
        _labels(),
        taxonomy_version="m3-role-v1",
        taxonomy_status="frozen",
        input_status="formal",
        candidate_lambdas=(0.0, 0.5, 1.0),
        metric_k=3,
        cases_sha256="a" * 64,
        role_labels_sha256="b" * 64,
    )

    assert result.selected.lambda_weight == 0.5
    assert result.selected.selection_status == "frozen"
    assert result.selected.reportable is True
    assert result.metrics[0].mean_reciprocal_rank == pytest.approx(0.5)
    assert result.metrics[1].mean_reciprocal_rank > result.metrics[0].mean_reciprocal_rank
    assert result.metrics[1].mean_reciprocal_rank == result.metrics[2].mean_reciprocal_rank
    assert SelectedLambdaConfig.model_validate(
        result.selected.model_dump()
    ) == result.selected


def test_fixture_search_is_provisional_even_with_a_frozen_taxonomy_name() -> None:
    result = search_lambda(
        [_case()],
        _labels(),
        taxonomy_version="fixture-v1",
        taxonomy_status="frozen",
        input_status="fixture",
        candidate_lambdas=(0.0, 1.0),
    )

    assert result.selected.selection_status == "provisional"
    assert result.selected.reportable is False


def test_search_rejects_test_rows_and_missing_zero_baseline() -> None:
    with pytest.raises(ValueError, match="Test tuning is forbidden"):
        LambdaSearchCase(
            question_id="q-test",
            split="test",  # type: ignore[arg-type]
            profile=_profile(),
            retrieval=_retrieval(),
            relevant_chunk_ids=frozenset({"definition"}),
        )

    with pytest.raises(ValueError, match="lambda=0 baseline"):
        search_lambda(
            [_case()],
            _labels(),
            taxonomy_version="fixture-v1",
            taxonomy_status="fixture",
            input_status="fixture",
            candidate_lambdas=(0.2, 0.4),
        )


def test_selected_config_detects_tampering() -> None:
    result = search_lambda(
        [_case()],
        _labels(),
        taxonomy_version="fixture-v1",
        taxonomy_status="fixture",
        input_status="fixture",
        candidate_lambdas=(0.0, 1.0),
    )
    payload = result.selected.model_dump()
    payload["objective"] = "tampered"

    with pytest.raises(ValueError, match="config_id does not match"):
        SelectedLambdaConfig.model_validate(payload)


def test_lambda_search_cli_writes_hash_bound_result(tmp_path, monkeypatch) -> None:
    cases_path = tmp_path / "cases.jsonl"
    labels_path = tmp_path / "roles.jsonl"
    output_path = tmp_path / "lambda_search.json"
    cases_path.write_text(
        json.dumps(
            {
                "question_id": "q-1",
                "split": "dev",
                "profile": _profile().model_dump(mode="json"),
                "retrieval": _retrieval().model_dump(mode="json"),
                "relevant_chunk_ids": ["definition"],
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
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "cs30.generation.lambda_search",
            "--cases",
            str(cases_path),
            "--role-labels",
            str(labels_path),
            "--taxonomy-version",
            "fixture-v1",
            "--taxonomy-status",
            "fixture",
            "--input-status",
            "fixture",
            "--lambdas",
            "0,0.5,1",
            "--metric-k",
            "3",
            "--output",
            str(output_path),
        ],
    )

    lambda_search_main()

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    selected = payload["selected_config"]
    assert selected["lambda_weight"] == 0.5
    assert selected["cases_sha256"]
    assert selected["role_labels_sha256"]
    assert selected["selection_status"] == "provisional"


def test_frozen_role_file_must_declare_matching_taxonomy_version(tmp_path) -> None:
    labels_path = tmp_path / "roles.jsonl"
    labels_path.write_text(
        json.dumps(
            {
                "chunk_id": "definition",
                "roles": ["definition"],
                "source": "m3-v1",
                "taxonomy_version": "m3-role-v1",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="taxonomy_version does not match"):
        load_role_labels(labels_path, expected_taxonomy_version="m3-role-v2")
