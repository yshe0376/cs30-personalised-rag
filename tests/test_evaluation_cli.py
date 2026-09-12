import json
import zipfile
from pathlib import Path

from cs30.contracts import OpenStaxChapter, OpenStaxDocument, TextBlock
from cs30.evaluation import load_normalized_gold, load_openstax_archive, write_prepared_corpus
from cs30.evaluation.cli import main
from cs30.evaluation.manifest import RunManifest

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "evaluation"


def _prepared_m3_inputs(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Create a raw M3 sample and its matching prepared OpenStax handoff."""

    document = OpenStaxDocument(
        document_id="book-1",
        title="Test book",
        version="1.0",
        source="https://example.test/book-1",
        document_hash="source-hash",
        parser_version="1.2.0",
        text="Evidence text",
        chapters=[
            OpenStaxChapter(
                chapter_id="1",
                title="Chapter 1",
                char_start=0,
                char_end=len("Evidence text"),
            )
        ],
        blocks=[
            TextBlock(
                block_id="block-1",
                chapter_id="1",
                content_type="body",
                char_start=0,
                char_end=len("Evidence text"),
            )
        ],
    )
    archive_path = tmp_path / "chapter.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(
            "parsed_openstax_ch1/openstax_document.json", document.model_dump_json()
        )
    prepared = tmp_path / "prepared"
    paths = write_prepared_corpus(load_openstax_archive(archive_path), prepared)
    raw_gold = tmp_path / "gold_v0_1.jsonl"
    raw_gold.write_text(
        json.dumps(
            {
                "schema_version": "0.1",
                "question_id": "m3-question",
                "source_split": "test",
                "question": "Which option is supported?",
                "options": {"A": "No", "B": "Yes", "C": "Maybe", "D": "Later"},
                "gold_answer": "B",
                "gold_answer_text": "Yes",
                "answerable": True,
                "gold_core_evidence_sets": [
                    [
                        {
                            "span_id": "span-1",
                            "block_id": "block-1",
                            "document_id": "book-1",
                            "chapter_id": "1",
                            "char_start": 0,
                            "char_end": len("Evidence text"),
                            "verbatim_text": "Evidence text",
                            "sufficiency": "core_sufficient",
                            "annotation_note": "Direct evidence.",
                        }
                    ]
                ],
                "partial_evidence": [],
                "question_difficulty": "easy",
                "question_type": "factual",
                "concept_group": "fixture",
                "personalisation_eligibility": "none",
                "eligibility_reason": "Direct evidence.",
                "split": "dev",
                "corpus_version": "book-1",
                "parser_version": "1.2.0",
                "gold_annotation_version": "m3_gold_v0.1",
                "annotation_status": "m3_initial",
                "review_record_id": "m3-review",
                "source": {
                    "dataset": "SciQ standardized",
                    "source_question_id": "m3-question",
                    "support": "Evidence text",
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return raw_gold, Path(paths["document"]), Path(paths["manifest"])


def _reportable_manifest(path: Path) -> Path:
    path.write_text(
        RunManifest(
            run_id="formal-run",
            condition_id="fixture_condition",
            dataset_version="dataset-v1",
            split="dev",
            corpus_version="book-1",
            chunk_version="fixture-chunks-0.1",
            parser_version="1.2.0",
            gold_annotation_version="m3_gold_v0.1",
            mapping_version="mapping-v1",
            embedding_version=None,
            index_version="index-v1",
            generation_model=None,
            prompt_version=None,
            profile="none",
            execution_mode="retrieval_only",
            retrieval_mode="bm25",
            top_k=1,
            k_values=[1],
            git_commit="clean",
            git_dirty=False,
            git_snapshot_sha256="snapshot",
        ).model_dump_json(),
        encoding="utf-8",
    )
    return path


def test_cli_run_writes_completed_jsonl_and_manifest(tmp_path: Path) -> None:
    output = tmp_path / "run.jsonl"

    exit_code = main(
        [
            "run",
            "--gold",
            str(FIXTURE_DIR / "gold_v0_1.jsonl"),
            "--output",
            str(output),
            "--fixture",
            "--allow-dirty",
            "--execution-mode",
            "retrieval_only",
            "--retrieval-mode",
            "fixture",
            "--top-k",
            "3",
            "--k-values",
            "1",
            "3",
            "--split",
            "dev",
        ]
    )

    assert exit_code == 0
    assert output.is_file()
    assert not Path(str(output) + ".inprogress").exists()
    manifest = output.with_suffix(".manifest.json")
    manifest_payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert isinstance(manifest_payload["git_dirty"], bool)
    assert manifest_payload["fixture_mode"] is True
    assert manifest_payload["reportable"] is False
    assert not (manifest_payload["git_dirty"] and manifest_payload["reportable"])


def test_cli_score_reloads_saved_run_without_a_model_call(tmp_path: Path) -> None:
    run_output = tmp_path / "run.jsonl"
    score_output = tmp_path / "score.json"
    run_exit = main(
        [
            "run",
            "--gold",
            str(FIXTURE_DIR / "gold_v0_1.jsonl"),
            "--output",
            str(run_output),
            "--fixture",
            "--allow-dirty",
            "--execution-mode",
            "retrieval_only",
            "--retrieval-mode",
            "fixture",
            "--top-k",
            "3",
            "--k-values",
            "1",
            "3",
            "--split",
            "dev",
        ]
    )

    assert run_exit == 0
    score_exit = main(
        [
            "score",
            "--gold",
            str(FIXTURE_DIR / "gold_v0_1.jsonl"),
            "--runs",
            str(run_output),
            "--mapping",
            str(FIXTURE_DIR / "mapping_v0_1.json"),
            "--manifest",
            str(run_output.with_suffix(".manifest.json")),
            "--output",
            str(score_output),
        ]
    )

    assert score_exit == 0
    assert json.loads(score_output.read_text(encoding="utf-8"))["retrieval"]["sample_count"] == 1


def test_cli_score_can_write_per_question_retrieval_scores(tmp_path: Path) -> None:
    run_output = tmp_path / "run.jsonl"
    score_output = tmp_path / "score.json"
    scores_output = tmp_path / "retrieval_scores.jsonl"
    run_exit = main(
        [
            "run",
            "--gold",
            str(FIXTURE_DIR / "gold_v0_1.jsonl"),
            "--output",
            str(run_output),
            "--fixture",
            "--allow-dirty",
            "--execution-mode",
            "retrieval_only",
            "--retrieval-mode",
            "fixture",
            "--top-k",
            "3",
            "--k-values",
            "1",
            "3",
            "--split",
            "dev",
        ]
    )

    assert run_exit == 0
    score_exit = main(
        [
            "score",
            "--gold",
            str(FIXTURE_DIR / "gold_v0_1.jsonl"),
            "--runs",
            str(run_output),
            "--mapping",
            str(FIXTURE_DIR / "mapping_v0_1.json"),
            "--manifest",
            str(run_output.with_suffix(".manifest.json")),
            "--output",
            str(score_output),
            "--scores-output",
            str(scores_output),
        ]
    )

    assert score_exit == 0
    rows = [json.loads(line) for line in scores_output.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["question_id"] == "fixture_joint"
    assert rows[0]["included"] is True


def test_cli_scores_the_one_row_per_question_fixture(tmp_path: Path) -> None:
    score_output = tmp_path / "score.json"

    assert (
        main(
            [
                "score",
                "--gold",
                str(FIXTURE_DIR / "gold_v0_1.jsonl"),
                "--runs",
                str(FIXTURE_DIR / "run_results_scorable_v0_2.jsonl"),
                "--mapping",
                str(FIXTURE_DIR / "mapping_v0_1.json"),
                "--k-values",
                "1",
                "3",
                "--output",
                str(score_output),
            ]
        )
        == 0
    )

    scored = json.loads(score_output.read_text(encoding="utf-8"))
    assert scored["retrieval"]["sample_count"] == 1
    assert scored["retrieval"]["excluded_runs"]["total"] == 1


def test_cli_rejects_synthetic_trace_outside_fixture_mode(
    tmp_path: Path, capsys
) -> None:
    exit_code = main(
        [
            "run",
            "--gold",
            str(FIXTURE_DIR / "gold_v0_1.jsonl"),
            "--output",
            str(tmp_path / "run.jsonl"),
            "--allow-dirty",
            "--allow-synthetic-trace",
            "--execution-mode",
            "retrieval_and_generation",
            "--retrieval-mode",
            "fixture",
            "--top-k",
            "3",
            "--k-values",
            "1",
            "3",
            "--split",
            "dev",
        ]
    )

    assert exit_code == 2
    assert "only allowed with --fixture" in capsys.readouterr().err


def test_cli_reports_missing_input_before_git_cleanliness(tmp_path: Path, capsys) -> None:
    exit_code = main(
        [
            "run",
            "--gold",
            str(tmp_path / "missing.jsonl"),
            "--output",
            str(tmp_path / "run.jsonl"),
            "--execution-mode",
            "retrieval_only",
            "--retrieval-mode",
            "fixture",
        ]
    )

    assert exit_code == 2
    error = capsys.readouterr().err
    assert "Gold sample file not found" in error
    assert "clean git worktree" not in error


def test_cli_score_reports_missing_run_results_file(tmp_path: Path, capsys) -> None:
    exit_code = main(
        [
            "score",
            "--gold",
            str(FIXTURE_DIR / "gold_v0_1.jsonl"),
            "--runs",
            str(tmp_path / "missing-runs.jsonl"),
            "--mapping",
            str(FIXTURE_DIR / "mapping_v0_1.json"),
            "--k-values",
            "1",
        ]
    )

    assert exit_code == 2
    assert "run results file not found" in capsys.readouterr().err


def test_cli_score_reports_missing_mapping_file(tmp_path: Path, capsys) -> None:
    exit_code = main(
        [
            "score",
            "--gold",
            str(FIXTURE_DIR / "gold_v0_1.jsonl"),
            "--runs",
            str(FIXTURE_DIR / "run_results_scorable_v0_2.jsonl"),
            "--mapping",
            str(tmp_path / "missing-mapping.json"),
            "--k-values",
            "1",
        ]
    )

    assert exit_code == 2
    assert "mapping file not found" in capsys.readouterr().err


def test_normalize_gold_cli_writes_full_corpus_version(tmp_path: Path) -> None:
    raw_gold, document, corpus_manifest = _prepared_m3_inputs(tmp_path)
    output = tmp_path / "gold_normalized.jsonl"

    assert (
        main(
            [
                "normalize-gold",
                "--gold",
                str(raw_gold),
                "--document",
                str(document),
                "--corpus-manifest",
                str(corpus_manifest),
                "--output",
                str(output),
            ]
        )
        == 0
    )

    normalized = load_normalized_gold(output)
    manifest = json.loads(corpus_manifest.read_text(encoding="utf-8"))
    assert normalized[0].schema_version == "0.2"
    assert normalized[0].corpus_version == manifest["corpus_version"]


def test_formal_run_rejects_raw_m3_gold_before_retrieval(
    tmp_path: Path, capsys
) -> None:
    raw_gold, document, _ = _prepared_m3_inputs(tmp_path)

    exit_code = main(
        [
            "run",
            "--gold",
            str(raw_gold),
            "--document",
            str(document),
            "--output",
            str(tmp_path / "run.jsonl"),
            "--retrieval-mode",
            "bm25",
            "--top-k",
            "1",
            "--k-values",
            "1",
            "--mapping-version",
            "mapping-v1",
        ]
    )

    assert exit_code == 2
    assert "normalized Gold requires schema 0.2" in capsys.readouterr().err


def test_formal_score_rejects_short_document_id_corpus_version(
    tmp_path: Path, capsys
) -> None:
    raw_gold, document, corpus_manifest = _prepared_m3_inputs(tmp_path)
    manifest = _reportable_manifest(tmp_path / "run.manifest.json")

    exit_code = main(
        [
            "score",
            "--gold",
            str(raw_gold),
            "--runs",
            str(FIXTURE_DIR / "run_results_scorable_v0_2.jsonl"),
            "--mapping",
            str(FIXTURE_DIR / "mapping_v0_1.json"),
            "--manifest",
            str(manifest),
            "--document",
            str(document),
            "--corpus-manifest",
            str(corpus_manifest),
        ]
    )

    assert exit_code == 2
    assert "normalized Gold requires schema 0.2" in capsys.readouterr().err
