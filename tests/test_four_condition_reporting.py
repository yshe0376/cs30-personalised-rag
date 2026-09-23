from __future__ import annotations

import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from cs30.citation import build_evidence_bundle
from cs30.contracts import (
    GeneratedAnswer,
    RetrievalHit,
    RetrievalMode,
    RetrievalResult,
    StudentLevel,
    StudentProfile,
)
from cs30.evaluation import (
    adapt_four_condition_results,
    load_gold_samples,
    load_mappings,
    score_four_condition_results,
    write_four_condition_reports,
)
from cs30.evaluation.cli import main
from cs30.generation.prompt import PromptBuilder

FIXTURES = Path(__file__).parent / "fixtures" / "evaluation"


def _write_m7_inputs(tmp_path: Path) -> tuple[Path, Path, Path]:
    retrieval = RetrievalResult(
        query="Which evidence supports the answer?",
        mode=RetrievalMode.FIXTURE,
        hits=[
            RetrievalHit(
                chunk_id="chunk_alpha",
                text="Alpha.",
                chapter_id="fixture_chapter",
                source="fixture://openstax",
                source_locator="[0,6)",
                score=1.0,
                rank=1,
                retriever_type=RetrievalMode.FIXTURE,
            ),
            RetrievalHit(
                chunk_id="chunk_gamma",
                text="Gamma.",
                chapter_id="fixture_chapter",
                source="fixture://openstax",
                source_locator="[13,19)",
                score=0.8,
                rank=2,
                retriever_type=RetrievalMode.FIXTURE,
            ),
        ],
    )
    profile = StudentProfile(
        profile_id="fixture_joint:beginner",
        level=StudentLevel.BEGINNER,
        confidence=1.0,
    )
    question = "Which evidence supports the answer?\nA. One\nB. Two\nC. Three\nD. Four"
    case_payload = {
        "question_id": "fixture_joint",
        "split": "dev",
        "question": question,
        "profile": profile.model_dump(mode="json"),
        "retrieval": retrieval.model_dump(mode="json"),
    }
    cases_path = tmp_path / "cases.jsonl"
    cases_text = json.dumps(case_payload, sort_keys=True) + "\n"
    cases_path.write_text(cases_text, encoding="utf-8", newline="\n")
    cases_hash = hashlib.sha256(cases_text.encode()).hexdigest()

    run_id = "member7-four-condition-fixture"
    conditions = (
        ("plain", "P0R0_plain", False, False),
        ("prompt-only", "P1R0_prompt_only", True, False),
        ("reranking-only", "P0R1_reranking_only", False, True),
        ("combined", "P1R1_combined", True, True),
    )
    rows = []
    for condition, condition_id, personalise, rerank in conditions:
        output_ids = ["chunk_gamma", "chunk_alpha"] if rerank else ["chunk_alpha", "chunk_gamma"]
        by_id = {hit.chunk_id: hit for hit in retrieval.hits}
        prepared = retrieval.model_copy(
            update={
                "hits": [
                    by_id[chunk_id].model_copy(update={"rank": rank})
                    for rank, chunk_id in enumerate(output_ids, start=1)
                ]
            }
        )
        bundle = build_evidence_bundle(prepared)
        prompt = PromptBuilder().build(
            question,
            profile,
            bundle,
            personalise=personalise,
        )
        answer = GeneratedAnswer(
            final_choice="B",
            explanation="The selected evidence supports option B.",
            citations=[output_ids[0]],
        )
        raw_output = answer.model_dump_json()
        rows.append(
            {
                "schema_version": "1.0",
                "run_id": run_id,
                "question_id": "fixture_joint",
                "case_id": f"fixture_joint:{profile.profile_id}",
                "split": "dev",
                "status": "completed",
                "condition": condition,
                "condition_id": condition_id,
                "prompt_personalisation": personalise,
                "reranking": rerank,
                "profile_snapshot": profile.model_dump(mode="json"),
                "input_candidate_ids": ["chunk_alpha", "chunk_gamma"],
                "output_candidate_ids": output_ids,
                "answer": answer.model_dump(mode="json"),
                "generation_trace": {
                    "generation_attempts": "1",
                    "raw_model_output": raw_output,
                    "repaired_model_output": None,
                    "prompt_evidence_chunk_ids": output_ids,
                    "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
                    "attempt_records": [
                        {
                            "attempt": 1,
                            "is_repair": False,
                            "status": "completed",
                            "raw_output": raw_output,
                            "model": "fixture-model",
                            "failure_type": None,
                            "error": None,
                        }
                    ],
                },
                "rerank_trace": None,
                "error": None,
            }
        )
    results_path = tmp_path / "four_condition_results.jsonl"
    results_path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
        newline="\n",
    )
    manifest_path = tmp_path / "run_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "result_type": "member7_four_condition_run",
                "run_id": run_id,
                "reportable": False,
                "cases_sha256": cases_hash,
                "row_count": 4,
                "conditions": [item[1] for item in conditions],
            }
        ),
        encoding="utf-8",
    )
    return cases_path, results_path, manifest_path


def test_m7_rows_are_verified_adapted_and_reported_by_condition(tmp_path: Path) -> None:
    cases, rows, manifest_path = _write_m7_inputs(tmp_path)
    manifest, adapted = adapt_four_condition_results(cases, rows, manifest_path)

    assert len(adapted) == 4
    assert all(item.run.schema_version == "0.2" for item in adapted)
    assert {item.run.condition_id for item in adapted} == {
        "P0R0_plain",
        "P1R0_prompt_only",
        "P0R1_reranking_only",
        "P1R1_combined",
    }
    assert all(item.run.citation_validation is not None for item in adapted)

    result = score_four_condition_results(
        manifest,
        adapted,
        load_gold_samples(FIXTURES / "gold_v0_1.jsonl")[:1],
        load_mappings(FIXTURES / "mapping_v0_1.json"),
    )
    assert result["reportable"] is False
    assert len(result["groups"]) == 4
    assert len(result["comparisons"]) == 8
    coverage = next(
        row
        for row in result["comparisons"]
        if row["metric"] == "gold_evidence_citation_coverage"
    )
    assert coverage["values"]["P0R0_plain"] == 0.0
    assert coverage["values"]["P0R1_reranking_only"] == 1.0

    paths = write_four_condition_reports(result, adapted, tmp_path / "reports")
    assert set(paths) == {
        "summary",
        "comparison_csv",
        "markdown",
        "latex",
        "chart",
        "evaluation_runs",
        "failures",
    }
    assert all(path.is_file() for path in paths.values())
    ET.parse(paths["chart"])
    assert "provider\\_failure\\_rate" in paths["latex"].read_text(encoding="utf-8")
    assert len(paths["evaluation_runs"].read_text(encoding="utf-8").splitlines()) == 4


def test_adapter_rejects_cases_that_do_not_match_manifest_hash(tmp_path: Path) -> None:
    cases, rows, manifest = _write_m7_inputs(tmp_path)
    cases.write_text(cases.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="SHA-256"):
        adapt_four_condition_results(cases, rows, manifest)


def test_four_condition_cli_writes_acceptance_package(tmp_path: Path) -> None:
    cases, rows, manifest = _write_m7_inputs(tmp_path)
    output_dir = tmp_path / "cli-report"

    exit_code = main(
        [
            "report-four-conditions",
            "--gold",
            str(FIXTURES / "gold_v0_1.jsonl"),
            "--mapping",
            str(FIXTURES / "mapping_v0_1.json"),
            "--cases",
            str(cases),
            "--results",
            str(rows),
            "--run-manifest",
            str(manifest),
            "--output-dir",
            str(output_dir),
        ]
    )

    assert exit_code == 0
    assert (output_dir / "four_condition_comparison.svg").is_file()
    assert (output_dir / "evaluation_run_results_v0_2.jsonl").is_file()
