"""Native V2 experiment integration, fail-closed preparation and blind review."""

import csv
import json

import pytest
from test_v2_corpus_records import build_corpus

from cs30.generation.client import LLMResponse, TokenUsage
from cs30.v2.contracts import GoldQuestion
from cs30.v2.corpus import load_corpus_records
from cs30.v2.experiment import (
    ExperimentConfig,
    jsonl_bytes,
    load_prepared,
    load_v2_gold,
    prepare_experiment,
    run_experiment,
    select_dev_lambda,
)
from cs30.v2.experiment_cli import main
from cs30.v2.experiment_gold import bind_span, convert_m3_gold
from cs30.v2.io import sha256_bytes


def example_gold():
    text = "Deceleration is acceleration opposite to velocity and reduces speed."
    return GoldQuestion(
        question_id="q1",
        question="What term describes acceleration that reduces speed?",
        gold_answer_text="deceleration",
        answerable=True,
        gold_core_evidence_sets=[
            [
                {
                    "span": {
                        "span_id": "s1",
                        "textbook_id": "book",
                        "chapter_id": "2",
                        "chapter_char_start": 0,
                        "chapter_char_end": len(text),
                        "verbatim_text": text,
                        "origin_corpus_version": "v2-test",
                    },
                    "sufficiency": "core_sufficient",
                }
            ]
        ],
        question_difficulty="easy",
        question_type="definition",
        concept_group="motion",
        personalisation_eligibility="pending",
        eligibility_reason="fixture",
        split="dev",
        corpus_version="v2-test",
        parser_version="fixture",
        gold_annotation_version="fixture",
        annotation_status="reviewed",
        review_record_id="fixture-review",
    )


class Client:
    model = "generator-fixture"
    temperature = 0.0

    def __init__(self, fail_first=False):
        self.prompts = []
        self.fail_first = fail_first

    def complete(self, prompt, text_format):
        self.prompts.append(prompt)
        if len(self.prompts) == 1 and self.fail_first:
            raise TimeoutError("synthetic timeout")
        metadata = prompt.split("<evidence metadata=", 1)[1].split(">", 1)[0]
        chunk_id = json.loads(metadata)["chunk_id"]
        return LLMResponse(
            json.dumps(
                {"final_choice": None, "explanation": "Force and motion.", "citations": [chunk_id]}
            ),
            self.model,
            TokenUsage(10, 5, 15),
            "response-fixture",
            2.0,
        )


def inputs(tmp_path):
    _, corpus_dir = build_corpus(tmp_path)
    corpus = load_corpus_records(corpus_dir)
    chunk = corpus.chunks[0]
    block = chunk.spans[0]
    span_text = chunk.text[block.char_start - chunk.char_start : block.char_end - chunk.char_start]
    question = example_gold().model_dump(mode="json")
    question.update(
        question="What does the book explain about force?",
        gold_answer_text="GOLD_SENTINEL_FORCE_AND_MOTION",
        corpus_version=corpus.manifest.corpus_version,
    )
    span = question["gold_core_evidence_sets"][0][0]["span"]
    span.update(
        textbook_id=chunk.textbook_id,
        chapter_id=chunk.chapter_id,
        chapter_char_start=block.char_start,
        chapter_char_end=block.char_end,
        verbatim_text=span_text,
        block_id=block.block_id,
        origin_corpus_version=corpus.manifest.corpus_version,
    )
    span.pop("text_hash")
    from cs30.v2.contracts import GoldQuestion

    question = GoldQuestion.model_validate(question)
    gold_path = tmp_path / "gold.jsonl"
    data = jsonl_bytes([question])
    gold_path.write_bytes(data)
    rubric_path = tmp_path / "rubrics.jsonl"
    rubric_path.write_text("unused rubric; scoring is separate", encoding="utf-8")
    return corpus_dir, gold_path, rubric_path


def prepare(tmp_path, **updates):
    corpus_dir, gold_path, rubric_path = inputs(tmp_path)
    config = ExperimentConfig(
        generator_model=Client.model, max_retries=0, allow_missing_roles=True, **updates
    )
    destination = tmp_path / "prepared"
    prepare_experiment(
        corpus_dir=corpus_dir,
        gold_path=gold_path,
        output_dir=destination,
        config=config,
    )
    return destination


def test_native_batch_preserves_conditions_inputs_traces_and_gold_isolation(tmp_path):
    prepared = prepare(tmp_path)
    manifest, _, matrix, _, retrieval, _ = load_prepared(prepared)
    assert len(matrix.cases) == 12
    assert manifest["role_coverage_complete"] is False
    assert retrieval["q1"].retrieval.provenance.corpus_hash
    client = Client(fail_first=True)
    output = tmp_path / "run"
    runs = run_experiment(prepared, output, client, provider="synthetic")
    assert len(runs) == 12
    assert runs[0].status == "generation_error"
    assert all(r.status == "answered" for r in runs[1:])
    assert all("GOLD_SENTINEL" not in prompt for prompt in client.prompts)
    details = [
        json.loads(line)
        for line in (output / "generation_records.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert {tuple(row["input_candidate_ids"]) for row in details} == {
        tuple(h.chunk_id for h in retrieval["q1"].retrieval.hits)
    }
    for row in details:
        personalised = row["condition_id"].startswith("P1")
        assert row["generation_trace"]["prompt_personalised"] == personalised
        assert (row["rerank_trace"] is not None) == ("R1" in row["condition_id"])
        assert row["evidence"]["retrieval_provenance"]["corpus_hash"]
    summary = json.loads((output / "generation_summary.json").read_text(encoding="utf-8"))
    assert sum(g["expected"] for g in summary["groups"]) == 12
    assert sum(g["technical_failures"] for g in summary["groups"]) == 1
    assert sum(g["input_tokens"] for g in summary["groups"]) == 110
    run_manifest = json.loads((output / "run_manifest.json").read_text(encoding="utf-8"))
    assert run_manifest["status"] == "completed" and run_manifest["reportable"] is False
    assert all(
        sha256_bytes((output / name).read_bytes()) == digest
        for name, digest in run_manifest["output_sha256"].items()
    )


def test_cli_run_hands_off_without_scoring(tmp_path, monkeypatch):
    prepared = prepare(tmp_path)
    monkeypatch.setattr("cs30.v2.experiment_cli._client", lambda *args: Client())
    output = tmp_path / "run"
    assert (
        main(
            [
                "run",
                "--prepared-dir",
                str(prepared),
                "--output-dir",
                str(output),
                "--provider",
                "ollama",
            ]
        )
        == 0
    )
    assert not (output / "scoring").exists()
    matrix = json.loads((output / "expected_experiment.json").read_bytes())
    assert "rubrics_sha256" not in matrix
    assert (output / "saved_answers.jsonl").exists()
    assert (output / "generation_records.jsonl").exists()


@pytest.mark.parametrize(
    "change",
    [
        "gold.jsonl",
        "retrieval.jsonl",
        "config.json",
        "role_labels.json",
        "expected_experiment.json",
    ],
)
def test_any_changed_prepared_input_fails_before_generation(tmp_path, change):
    prepared = prepare(tmp_path)
    with (prepared / change).open("ab") as stream:
        stream.write(b" ")
    client = Client()
    with pytest.raises(ValueError, match="changed"):
        run_experiment(prepared, tmp_path / "run", client, provider="synthetic")
    assert client.prompts == [] and not (tmp_path / "run").exists()


def test_unknown_client_or_overwrite_rejected_without_calls(tmp_path):
    prepared = prepare(tmp_path)
    client = Client()
    client.model = "other-model"
    with pytest.raises(ValueError, match="model differs"):
        run_experiment(prepared, tmp_path / "run", client, provider="synthetic")
    assert not client.prompts
    output = tmp_path / "existing"
    output.mkdir()
    with pytest.raises(ValueError, match="already exists"):
        run_experiment(prepared, output, Client(), provider="synthetic")


def test_missing_roles_need_explicit_diagnostic_opt_in(tmp_path):
    corpus, gold, rubric = inputs(tmp_path)
    output = tmp_path / "prepared"
    with pytest.raises(ValueError, match="lack Role"):
        prepare_experiment(
            corpus_dir=corpus,
            gold_path=gold,
            output_dir=output,
            config=ExperimentConfig(generator_model=Client.model),
        )
    assert not output.exists()


@pytest.mark.parametrize(
    "update",
    [
        {"lambda_weight": float("nan")},
        {"profile_confidence": float("inf")},
        {"levels": ()},
        {"levels": ("beginner", "beginner")},
        {"candidate_k": 2, "evidence_k": 3},
        {"max_retries": 5},
    ],
)
def test_invalid_configuration_rejected(update):
    with pytest.raises(ValueError):
        ExperimentConfig(generator_model=Client.model, **update)


def test_stale_gold_rejected(tmp_path):
    corpus, gold, rubric = inputs(tmp_path)
    raw = json.loads(gold.read_text(encoding="utf-8"))
    raw["corpus_version"] = "old-version"
    gold.write_text(json.dumps(raw) + "\n")
    config = ExperimentConfig(generator_model=Client.model, allow_missing_roles=True)
    with pytest.raises(ValueError, match="Gold corpus_version"):
        prepare_experiment(
            corpus_dir=corpus,
            gold_path=gold,
            output_dir=tmp_path / "prepared",
            config=config,
        )
    raw["corpus_version"] = load_corpus_records(corpus).manifest.corpus_version
    gold.write_text(json.dumps(raw) + "\n")


def test_old_gold_is_not_implicitly_converted(tmp_path):
    path = tmp_path / "gold.jsonl"
    path.write_text('{"schema_version":"0.2"}\n')
    with pytest.raises(ValueError, match="native"):
        load_v2_gold(path)


def test_test_sampling_limit_is_forbidden(tmp_path):
    corpus, gold, rubric = inputs(tmp_path)
    with pytest.raises(ValueError, match="Dev-only"):
        prepare_experiment(
            corpus_dir=corpus,
            gold_path=gold,
            output_dir=tmp_path / "prepared",
            question_limit=1,
            config=ExperimentConfig(generator_model=Client.model, split="test"),
        )


def test_supplied_v2_retrieval_cannot_change_chunk_text(tmp_path):
    prepared = prepare(tmp_path)
    corpus = next(tmp_path.glob("artifacts/v2/textbooks/records"))
    records = [
        json.loads(line)
        for line in (prepared / "retrieval.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    records[0]["retrieval"]["hits"][0]["text"] = "A malicious replacement"
    path = tmp_path / "supplied.jsonl"
    path.write_text("".join(json.dumps(row) + "\n" for row in records))
    with pytest.raises(ValueError, match="published V2 chunk"):
        prepare_experiment(
            corpus_dir=corpus,
            gold_path=prepared / "gold.jsonl",
            output_dir=tmp_path / "again",
            config=ExperimentConfig(generator_model=Client.model, allow_missing_roles=True),
            retrieval_path=path,
        )


def test_role_annotation_roundtrip_binds_matching_corpus_and_candidates(tmp_path):
    corpus, gold, rubric = inputs(tmp_path)
    form = tmp_path / "roles.csv"
    assert (
        main(
            [
                "role-template",
                "--corpus-dir",
                str(corpus),
                "--gold",
                str(gold),
                "--output",
                str(form),
            ]
        )
        == 0
    )
    with form.open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert rows and all(row["role"] == "" for row in rows)
    assert (
        main(
            [
                "import-roles",
                "--corpus-dir",
                str(corpus),
                "--form",
                str(form),
                "--annotator-id",
                "synthetic-rater",
                "--output-dir",
                str(tmp_path / "roles"),
            ]
        )
        == 2
    )
    for row in rows:
        row["role"] = "definition"
    with form.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["chunk_id", "text", "role"])
        writer.writeheader()
        writer.writerows(rows)
    role_dir = tmp_path / "roles"
    assert (
        main(
            [
                "import-roles",
                "--corpus-dir",
                str(corpus),
                "--form",
                str(form),
                "--annotator-id",
                "synthetic-rater",
                "--output-dir",
                str(role_dir),
            ]
        )
        == 0
    )
    result = prepare_experiment(
        corpus_dir=corpus,
        gold_path=gold,
        output_dir=tmp_path / "prepared",
        role_manifest=role_dir / "role_manifest.json",
        config=ExperimentConfig(generator_model=Client.model),
    )
    assert result["role_coverage_complete"] is True
    assert (
        result["role_provenance"]["corpus_version"]
        == load_corpus_records(corpus).manifest.corpus_version
    )


def raw_m3(native):
    from cs30.evaluation.models import GoldSample

    data = {
        key: value
        for key, value in native.items()
        if key in GoldSample.model_fields and key != "schema_version"
    }
    data.update(
        source_split="test",
        source={
            "dataset": "synthetic-fixture",
            "source_question_id": native["question_id"],
            "support": "Synthetic support for converter regression tests.",
        },
    )

    def flatten(evidence):
        span = evidence["span"]
        return {
            "span_id": span["span_id"],
            "document_id": "original-m3-document",
            "chapter_id": span["chapter_id"],
            "block_id": span["block_id"],
            "char_start": span["chapter_char_start"],
            "char_end": span["chapter_char_end"],
            "chapter_char_start": span["chapter_char_start"],
            "chapter_char_end": span["chapter_char_end"],
            "verbatim_text": span["verbatim_text"],
            "sufficiency": evidence["sufficiency"],
            "annotation_note": evidence["annotation_note"] or "Synthetic evidence annotation.",
        }

    data["gold_core_evidence_sets"] = [
        [flatten(e) for e in group] for group in native["gold_core_evidence_sets"]
    ]
    data["partial_evidence"] = [flatten(e) for e in native["partial_evidence"]]
    return data


def test_explicit_m3_conversion_preserves_original_coordinates_and_audits_split_mapping(tmp_path):
    corpus, gold, _ = inputs(tmp_path)
    native = json.loads(gold.read_text(encoding="utf-8"))
    raw = raw_m3(native)
    raw.update(split="pending", corpus_version="original-m3-corpus")
    source = tmp_path / "raw.jsonl"
    source.write_text(json.dumps(raw) + "\n")
    before = source.read_bytes()
    output = tmp_path / "converted"
    audit = convert_m3_gold(source, corpus, output, split_mapping={"pending": "dev"})
    result = json.loads((output / "gold.jsonl").read_text(encoding="utf-8"))
    assert result["split"] == "dev" and audit["original_evaluation_splits"] == {"q1": "pending"}
    assert result["source_corpus_version"] == "original-m3-corpus"
    assert result["gold_answer_text"] == raw["gold_answer_text"]
    span = result["gold_core_evidence_sets"][0][0]["span"]
    original = raw["gold_core_evidence_sets"][0][0]
    assert (span["chapter_char_start"], span["chapter_char_end"]) == (
        original["char_start"],
        original["char_end"],
    )
    assert audit["reportable"] is False and source.read_bytes() == before
    assert audit["output_gold_sha256"] == sha256_bytes((output / "gold.jsonl").read_bytes())


def test_conversion_rejects_unknown_block_and_preserves_split_by_default(tmp_path):
    corpus, gold, _ = inputs(tmp_path)
    raw = raw_m3(json.loads(gold.read_text(encoding="utf-8")))
    raw["split"] = "pending"
    source = tmp_path / "raw.jsonl"
    source.write_text(json.dumps(raw) + "\n")
    convert_m3_gold(source, corpus, tmp_path / "converted")
    assert (
        json.loads((tmp_path / "converted/gold.jsonl").read_text(encoding="utf-8"))["split"]
        == "pending"
    )
    raw["gold_core_evidence_sets"][0][0]["block_id"] = "unknown-block"
    source.write_text(json.dumps(raw) + "\n")
    with pytest.raises(ValueError, match="unique target"):
        convert_m3_gold(source, corpus, tmp_path / "bad")
    assert not (tmp_path / "bad").exists()


def test_native_gold_cannot_bind_to_similar_or_invented_passage(tmp_path):
    corpus, gold, _ = inputs(tmp_path)
    span = load_v2_gold(gold)["q1"].gold_core_evidence_sets[0][0].span
    from cs30.v2.contracts import EvidenceSpan

    changed = EvidenceSpan.model_validate(
        span.model_dump(exclude={"text_hash"})
        | {
            "verbatim_text": "X" * len(span.verbatim_text),
        }
    )
    with pytest.raises(ValueError, match="exact locations"):
        bind_span(changed, load_corpus_records(corpus))


def annotate_roles(corpus, gold, root):
    form = root / "roles.csv"
    assert (
        main(
            [
                "role-template",
                "--corpus-dir",
                str(corpus),
                "--gold",
                str(gold),
                "--output",
                str(form),
            ]
        )
        == 0
    )
    with form.open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    with form.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["chunk_id", "text", "role"])
        writer.writeheader()
        writer.writerows(row | {"role": "definition"} for row in rows)
    destination = root / "roles"
    assert (
        main(
            [
                "import-roles",
                "--corpus-dir",
                str(corpus),
                "--form",
                str(form),
                "--annotator-id",
                "synthetic-rater",
                "--output-dir",
                str(destination),
            ]
        )
        == 0
    )
    return destination / "role_manifest.json"


def test_dev_lambda_is_reusable_on_test_without_tuning_or_crossing_input_versions(tmp_path):
    from cs30.v2.contracts import GoldQuestion

    corpus, gold_path, rubric_path = inputs(tmp_path)
    first = load_v2_gold(gold_path)["q1"]
    second = GoldQuestion.model_validate(
        first.model_dump(mode="json") | {"question_id": "q2", "split": "test"}
    )
    data = jsonl_bytes([first, second])
    gold_path.write_bytes(data)
    role_manifest = annotate_roles(corpus, gold_path, tmp_path)
    destination = tmp_path / "dev"
    prepare_experiment(
        corpus_dir=corpus,
        gold_path=gold_path,
        output_dir=destination,
        role_manifest=role_manifest,
        config=ExperimentConfig(generator_model=Client.model),
    )
    selection = select_dev_lambda(destination, [0.5, 0, 0.2])
    assert selection.lambda_weight == 0.5  # largest positive candidate within the margin
    assert selection.selected_on_split == "dev" and selection.reportable is False
    path = tmp_path / "selected.json"
    path.write_text(selection.model_dump_json())
    test_config = ExperimentConfig(
        generator_model=Client.model,
        split="test",
        lambda_weight=selection.lambda_weight,
        lambda_policy="dev_selected",
    )
    prepare_experiment(
        corpus_dir=corpus,
        gold_path=gold_path,
        output_dir=tmp_path / "test",
        role_manifest=role_manifest,
        config=test_config,
        selected_lambda_path=path,
    )
    with pytest.raises(ValueError, match="Test tuning"):
        select_dev_lambda(tmp_path / "test", [0, 0.5])
    with pytest.raises(ValueError, match="run settings"):
        prepare_experiment(
            corpus_dir=corpus,
            gold_path=gold_path,
            output_dir=tmp_path / "changed",
            role_manifest=role_manifest,
            config=test_config.model_copy(update={"profile_confidence": 0.5}),
            selected_lambda_path=path,
        )


def test_lambda_requires_zero_baseline_and_complete_roles(tmp_path):
    prepared = prepare(tmp_path)
    with pytest.raises(ValueError, match="complete candidate"):
        select_dev_lambda(prepared, [0, 0.5])
    # Use real fixture annotations only for this synthetic test.
    corpus, gold, _rubric = (
        next(tmp_path.glob("artifacts/v2/textbooks/records")),
        tmp_path / "gold.jsonl",
        tmp_path / "rubrics.jsonl",
    )
    roles = annotate_roles(corpus, gold, tmp_path)
    prepare_experiment(
        corpus_dir=corpus,
        gold_path=gold,
        output_dir=tmp_path / "complete",
        role_manifest=roles,
        config=ExperimentConfig(generator_model=Client.model),
    )
    for values in ([0.1], [0, float("nan")], [0, -1], [0, float("inf")]):
        with pytest.raises(ValueError, match="zero baseline"):
            select_dev_lambda(tmp_path / "complete", values)


def test_empty_real_retrieval_abstains_without_model_calls_and_keeps_all_cells(tmp_path):
    prepared = prepare(tmp_path)
    rows = [
        json.loads(line)
        for line in (prepared / "retrieval.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    rows[0]["retrieval"]["hits"] = []
    frozen = tmp_path / "empty.jsonl"
    frozen.write_text("".join(json.dumps(row) + "\n" for row in rows))
    destination = tmp_path / "empty-prepared"
    prepare_experiment(
        corpus_dir=next(tmp_path.glob("artifacts/v2/textbooks/records")),
        gold_path=prepared / "gold.jsonl",
        output_dir=destination,
        retrieval_path=frozen,
        config=ExperimentConfig(generator_model=Client.model),
    )
    client = Client()
    runs = run_experiment(destination, tmp_path / "empty-run", client, provider="synthetic")
    assert len(runs) == 12 and not client.prompts
    assert all(run.status == "abstained" for run in runs)


def test_malformed_provider_response_is_recorded_and_next_cells_continue(tmp_path):
    prepared = prepare(tmp_path)

    class Malformed(Client):
        def complete(self, prompt, text_format):
            if not self.prompts:
                self.prompts.append(prompt)
                return object()
            return super().complete(prompt, text_format)

    runs = run_experiment(prepared, tmp_path / "run", Malformed(), provider="synthetic")
    assert runs[0].status == "generation_error"
    assert all(run.status == "answered" for run in runs[1:])


def test_incomplete_matrix_and_wrong_role_coverage_metadata_are_rejected(tmp_path):
    prepared = prepare(tmp_path)
    path = prepared / "expected_experiment.json"
    matrix = json.loads(path.read_text(encoding="utf-8"))
    matrix["cases"].pop()
    path.write_text(json.dumps(matrix))
    manifest_path = prepared / "input_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["input_sha256"][path.name] = sha256_bytes(path.read_bytes())
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="cross product"):
        load_prepared(prepared)


def test_zero_lambda_r1_matrix_is_rejected_before_calls(tmp_path):
    prepared = prepare(tmp_path, lambda_weight=0)
    client = Client()
    with pytest.raises(ValueError, match="lambda_weight == 0"):
        run_experiment(prepared, tmp_path / "run", client, provider="synthetic")
    assert not client.prompts and not (tmp_path / "run").exists()


def test_generation_cli_does_not_import_offline_evaluator(tmp_path):
    import subprocess
    import sys

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import sys
for name in ("open_answer_scoring", "open_answer_cli",
             "open_answer_packets", "open_answer_reporting"):
    sys.modules["cs30.evaluation." + name] = None
from cs30.v2.experiment_cli import parser
assert {"rubrics", "review-packet", "import-ratings"}.isdisjoint(
    parser()._subparsers._group_actions[0].choices)
""",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_lambda_selection_refuses_a_zero_only_grid(tmp_path):
    corpus, gold, _ = inputs(tmp_path)
    roles = annotate_roles(corpus, gold, tmp_path)
    prepared = tmp_path / "complete"
    prepare_experiment(
        corpus_dir=corpus,
        gold_path=gold,
        output_dir=prepared,
        role_manifest=roles,
        config=ExperimentConfig(generator_model=Client.model),
    )
    with pytest.raises(ValueError, match="no positive lambda"):
        select_dev_lambda(prepared, [0])
