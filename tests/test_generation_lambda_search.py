import hashlib
import json
import sys
from pathlib import Path

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
    load_expected_question_count,
    load_role_label_package,
    load_role_labels,
    search_lambda,
    validate_formal_role_label_scope,
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
            RetrievalHit(
                chunk_id="boundary",
                text="The relation has limits outside a constant-mass model.",
                chapter_id="forces",
                source="fixture://lambda-search",
                score=0.1,
                rank=4,
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
        "boundary": RoleLabel.single(EvidenceRole.BOUNDARY, source="m3-v1"),
    }


def _write_role_package(
    directory: Path,
    labels: dict[str, RoleLabel] | None = None,
    *,
    taxonomy_version: str = "evidence-role-v1",
) -> Path:
    role_labels = labels or _labels()
    labels_path = directory / "roles.jsonl"
    labels_text = "".join(
        json.dumps(
            {
                "schema_version": "role-labels-v1",
                "chunk_id": chunk_id,
                "role": label.roles[0].value,
            }
        )
        + "\n"
        for chunk_id, label in role_labels.items()
    )
    labels_path.write_bytes(labels_text.encode("utf-8"))
    manifest_path = directory / "roles.manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "0.1",
                "role_schema_version": "role-labels-v1",
                "role_taxonomy_version": taxonomy_version,
                "annotation_version": "m3-role-v1",
                "corpus_version": "corpus-v1",
                "parser_version": "parser-v1",
                "annotation_date": "2026-09-22",
                "annotator_ids": ["m3-owner"],
                "double_annotated": False,
                "labels_file": labels_path.name,
                "labels_sha256": hashlib.sha256(labels_text.encode()).hexdigest(),
                "declared_record_count": len(role_labels),
                "reference_id_field": "chunk_id",
                "reference_type": "chunk",
                "reference_universe": "gold_mapping",
                "role_field": "role",
                "record_schema_version_field": "schema_version",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return manifest_path


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
        taxonomy_version="evidence-role-v1",
        taxonomy_status="frozen",
        input_status="formal",
        candidate_lambdas=(0.0, 0.5, 1.0),
        metric_k=3,
        cases_sha256="a" * 64,
        role_labels_sha256="b" * 64,
        split_manifest_sha256="c" * 64,
        expected_question_count=60,
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
        metric_k=3,
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
            metric_k=3,
        )


def test_selected_config_detects_tampering() -> None:
    result = search_lambda(
        [_case()],
        _labels(),
        taxonomy_version="fixture-v1",
        taxonomy_status="fixture",
        input_status="fixture",
        candidate_lambdas=(0.0, 1.0),
        metric_k=3,
    )
    payload = result.selected.model_dump()
    payload["objective"] = "tampered"

    with pytest.raises(ValueError, match="config_id does not match"):
        SelectedLambdaConfig.model_validate(payload)


def test_lambda_search_cli_writes_hash_bound_result(tmp_path, monkeypatch) -> None:
    cases_path = tmp_path / "cases.jsonl"
    manifest_path = _write_role_package(tmp_path)
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
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "cs30.generation.lambda_search",
            "--cases",
            str(cases_path),
            "--role-label-manifest",
            str(manifest_path),
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

    output_bytes = output_path.read_bytes()
    assert b"\r\n" not in output_bytes
    assert output_bytes.endswith(b"\n")
    payload = json.loads(output_bytes)
    selected = payload["selected_config"]
    assert selected["lambda_weight"] == 0.5
    assert selected["cases_sha256"]
    assert selected["role_labels_sha256"]
    assert selected["selection_status"] == "provisional"
    assert selected["taxonomy_version"] == "evidence-role-v1"
    assert payload["role_label_coverage"]["complete"] is True


def test_role_manifest_must_declare_matching_taxonomy_version(tmp_path) -> None:
    manifest_path = _write_role_package(tmp_path)

    with pytest.raises(ValueError, match="role_taxonomy_version does not match"):
        load_role_labels(manifest_path, expected_taxonomy_version="evidence-role-v2")


def test_loader_reads_the_merged_m3_manifest_contract() -> None:
    manifest_path = Path("m3_role_labels/role_labels_v1_provenance_manifest.json")

    labels = load_role_labels(
        manifest_path,
        expected_taxonomy_version="evidence-role-v1",
    )

    assert len(labels) == 20
    assert {label.source for label in labels.values()} == {"m3-role-v1"}
    assert all(len(label.roles) == 1 for label in labels.values())


def test_formal_run_rejects_gold_only_role_label_scope(tmp_path) -> None:
    package = load_role_label_package(_write_role_package(tmp_path))

    with pytest.raises(ValueError, match="covers gold_mapping only"):
        validate_formal_role_label_scope(package)


def test_role_manifest_detects_label_file_tampering(tmp_path) -> None:
    manifest_path = _write_role_package(tmp_path)
    (tmp_path / "roles.jsonl").write_bytes(b"{}\n")

    with pytest.raises(ValueError, match="labels_sha256 does not match"):
        load_role_labels(manifest_path)


def test_search_reports_incomplete_role_coverage() -> None:
    labels = {"definition": _labels()["definition"]}

    result = search_lambda(
        [_case()],
        labels,
        taxonomy_version="evidence-role-v1",
        taxonomy_status="frozen",
        input_status="provisional",
        candidate_lambdas=(0.0, 1.0),
        metric_k=3,
    )

    coverage = result.role_label_coverage.model_dump()
    assert coverage["labeled_candidate_count"] == 1
    assert coverage["total_candidate_count"] == 4
    assert coverage["interpretation_status"] == "not_interpretable"
    assert coverage["warning"]
    assert result.selected.reportable is False


def test_candidate_pool_must_be_larger_than_metric_k() -> None:
    with pytest.raises(ValueError, match="candidate pool must be larger"):
        search_lambda(
            [_case()],
            _labels(),
            taxonomy_version="evidence-role-v1",
            taxonomy_status="frozen",
            input_status="provisional",
            candidate_lambdas=(0.0, 1.0),
            metric_k=4,
        )


def test_split_manifest_supplies_question_count(tmp_path) -> None:
    manifest_path = tmp_path / "split.json"
    manifest_path.write_text(
        json.dumps({"splits": {"dev": {"question_count": 42}}}),
        encoding="utf-8",
    )

    assert load_expected_question_count(manifest_path, "dev") == 42
