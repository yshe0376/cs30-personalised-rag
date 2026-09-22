import json

import pytest

from cs30.contracts import (
    EvidenceProvenance,
    RetrievalHit,
    RetrievalMode,
    RetrievalResult,
)
from cs30.generation.prepare_cases import prepare_cases, write_prepared_cases


def _retrieval() -> RetrievalResult:
    return RetrievalResult(
        query="What is acceleration?",
        mode=RetrievalMode.HYBRID,
        hits=[
            RetrievalHit(
                chunk_id="chunk-1",
                text="Acceleration is the rate of change of velocity.",
                chapter_id="motion",
                source="https://example.test/textbook",
                score=0.9,
                rank=1,
                retriever_type=RetrievalMode.HYBRID,
            )
        ],
        provenance=EvidenceProvenance(
            corpus_hash="corpus-hash",
            chunk_config_hash="chunk-hash",
            embedding_model="embedding-model",
            index_version="index-v1",
        ),
    )


def _inputs(tmp_path, *, reportable: bool = False, split: str = "proposed_dev"):
    runs = tmp_path / "runs.jsonl"
    manifest = tmp_path / "retrieval_manifest.json"
    mapping = tmp_path / "mapping.json"
    runs.write_text(
        json.dumps(
            {
                "question_id": "q-1",
                "execution_mode": "retrieval_only",
                "status": "retrieved",
                "retrieval": _retrieval().model_dump(mode="json"),
            }
        )
        + "\n",
        encoding="utf-8",
    )
    manifest.write_text(
        json.dumps(
            {
                "run_id": "m6-run",
                "split": split,
                "execution_mode": "retrieval_only",
                "reportable": reportable,
                "dataset_version": "gold-v1",
                "corpus_version": "corpus-v1",
                "chunk_version": "chunk-v1",
                "index_version": "index-v1",
            }
        ),
        encoding="utf-8",
    )
    mapping.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "question_id": "q-1",
                        "matching_chunk_ids": ["chunk-1"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return runs, manifest, mapping


def test_prepare_cases_joins_m6_mapping_and_all_three_profiles(tmp_path) -> None:
    runs, source_manifest, mapping = _inputs(tmp_path)

    rows, manifest = prepare_cases(
        runs,
        source_manifest,
        mapping,
        target_split="dev",
        input_status="provisional",
    )

    assert len(rows) == 3
    assert {row["profile"]["level"] for row in rows} == {
        "beginner",
        "intermediate",
        "advanced",
    }
    assert all(row["relevant_chunk_ids"] == ["chunk-1"] for row in rows)
    assert all(row["source_split"] == "proposed_dev" for row in rows)
    assert all(row["source_reportable"] is False for row in rows)
    assert manifest["formally_complete"] is False
    assert manifest["question_count"] == 1
    assert manifest["expected_question_count"] is None
    assert manifest["case_count"] == 3

    cases_path = tmp_path / "prepared" / "cases.jsonl"
    manifest_path = tmp_path / "prepared" / "manifest.json"
    write_prepared_cases(cases_path, manifest_path, rows, manifest)
    assert len(cases_path.read_text(encoding="utf-8").splitlines()) == 3
    assert json.loads(manifest_path.read_text(encoding="utf-8"))["question_count"] == 1


def test_formal_preparation_rejects_nonreportable_source(tmp_path) -> None:
    runs, source_manifest, mapping = _inputs(tmp_path)

    with pytest.raises(ValueError, match="reportable M6 manifest"):
        prepare_cases(
            runs,
            source_manifest,
            mapping,
            target_split="dev",
            input_status="formal",
        )


def test_formal_preparation_rejects_incomplete_question_count(tmp_path) -> None:
    runs, source_manifest, mapping = _inputs(tmp_path, reportable=True, split="dev")
    split_manifest = tmp_path / "split_manifest.json"
    split_manifest.write_text(
        json.dumps({"split": "dev", "question_count": 60}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="does not match the split manifest"):
        prepare_cases(
            runs,
            source_manifest,
            mapping,
            target_split="dev",
            input_status="formal",
            split_manifest_path=split_manifest,
        )


def test_formal_preparation_uses_split_manifest_count(tmp_path) -> None:
    runs, source_manifest, mapping = _inputs(tmp_path, reportable=True, split="dev")
    split_manifest = tmp_path / "split_manifest.json"
    split_manifest.write_text(
        json.dumps({"split": "dev", "question_count": 1}),
        encoding="utf-8",
    )

    _, manifest = prepare_cases(
        runs,
        source_manifest,
        mapping,
        target_split="dev",
        input_status="formal",
        split_manifest_path=split_manifest,
    )

    assert manifest["expected_question_count"] == 1
    assert manifest["formally_complete"] is True
    assert manifest["split_manifest_sha256"]
