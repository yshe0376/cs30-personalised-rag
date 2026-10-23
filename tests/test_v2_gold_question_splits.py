"""Exact per-question split coverage and byte-level provenance."""

import json
from collections import Counter
from pathlib import Path

import pytest
from test_v2_experiment import inputs, raw_m3

from cs30.v2.experiment_gold import convert_m3_gold
from cs30.v2.io import sha256_bytes


def source_input(tmp_path):
    corpus, gold, _ = inputs(tmp_path)
    row = raw_m3(json.loads(gold.read_bytes()))
    row["split"] = "pending"
    source = tmp_path / "m3.jsonl"
    source.write_text(json.dumps(row) + "\n")
    return corpus, source


def test_question_id_mapping_and_exact_file_hash(tmp_path):
    corpus, source = source_input(tmp_path)
    splits = tmp_path / "splits.json"
    splits.write_bytes(b'{"q1": "test"}\n')
    output = tmp_path / "converted"
    audit = convert_m3_gold(source, corpus, output, split_map_path=splits)
    assert json.loads((output / "gold.jsonl").read_bytes())["split"] == "test"
    assert audit["split_mapping_mode"] == "question_id"
    assert audit["split_counts"] == {"test": 1}
    assert audit["split_map_sha256"] == sha256_bytes(splits.read_bytes())
    assert audit["original_evaluation_splits"] == {"q1": "pending"}


@pytest.mark.parametrize(
    "data",
    [
        '{"q1":"dev","q1":"test"}',
        '{"other":"dev"}',
        '{"q1":"dev","extra":"test"}',
        '{"q1":"invalid"}',
        '["q1", "dev"]',
        '{"q1":["dev"]}',
    ],
)
def test_invalid_split_map_refuses_before_publishing(tmp_path, data):
    corpus, source = source_input(tmp_path)
    splits = tmp_path / "splits.json"
    splits.write_text(data)
    output = tmp_path / "converted"
    with pytest.raises(ValueError):
        convert_m3_gold(source, corpus, output, split_map_path=splits)
    assert not output.exists()


def test_checked_in_341_question_split_is_exactly_154_187():
    path = (
        Path(__file__).resolve().parents[1]
        / "docs/examples/v2-generation-split-dev154-test187.json"
    )
    splits = json.loads(path.read_bytes())
    assert len(splits) == 341 and Counter(splits.values()) == {"dev": 154, "test": 187}
    assert (
        sha256_bytes(path.read_bytes())
        == "991d9a68d0fa256b5d418549ffa62c331c6f31c0aacbc144f064f507bfd100fb"
    )


def test_noise_subset_is_dev_only_unique_and_hashed(tmp_path):
    from cs30.v2.experiment import ExperimentConfig, prepare_experiment

    corpus, gold, _ = inputs(tmp_path)
    ids = tmp_path / "question_ids.json"
    ids.write_text('["q1"]\n')
    manifest = prepare_experiment(
        corpus_dir=corpus,
        gold_path=gold,
        output_dir=tmp_path / "prepared",
        config=ExperimentConfig(generator_model="test", allow_missing_roles=True),
        question_ids_path=ids,
    )
    assert manifest["question_count"] == 1
    assert manifest["question_ids_sha256"] == sha256_bytes(ids.read_bytes())
    for data in ('["q1", "q1"]', '["missing"]', "[]"):
        ids.write_text(data)
        with pytest.raises(ValueError, match="unique known Dev"):
            prepare_experiment(
                corpus_dir=corpus,
                gold_path=gold,
                output_dir=tmp_path / "bad",
                config=ExperimentConfig(generator_model="test", allow_missing_roles=True),
                question_ids_path=ids,
            )


def test_lambda_selection_cannot_silently_switch_candidate_source(tmp_path):
    from test_v2_experiment import Client, annotate_roles

    from cs30.v2.corpus import load_corpus_records
    from cs30.v2.experiment import (
        ExperimentConfig,
        jsonl_bytes,
        load_v2_gold,
        prepare_experiment,
        retrieve_bm25,
        select_dev_lambda,
    )

    corpus, gold, _ = inputs(tmp_path)
    roles = annotate_roles(corpus, gold, tmp_path)
    candidates = tmp_path / "m6.jsonl"
    candidates.write_bytes(
        jsonl_bytes(retrieve_bm25(load_corpus_records(corpus), load_v2_gold(gold), 20))
    )
    destination = tmp_path / "dev"
    prepare_experiment(
        corpus_dir=corpus,
        gold_path=gold,
        output_dir=destination,
        role_manifest=roles,
        retrieval_path=candidates,
        config=ExperimentConfig(generator_model=Client.model),
    )
    selection = select_dev_lambda(destination, [0, 0.2])
    assert selection.source_retrieval_sha256 == sha256_bytes(candidates.read_bytes())
    path = tmp_path / "lambda.json"
    path.write_text(selection.model_dump_json())
    config = ExperimentConfig(
        generator_model=Client.model,
        lambda_weight=selection.lambda_weight,
        lambda_policy="dev_selected",
    )
    for variant in (None, tmp_path / "changed.jsonl"):
        if variant:
            variant.write_bytes(candidates.read_bytes() + b"\n")
        with pytest.raises(ValueError, match="selected Dev lambda"):
            prepare_experiment(
                corpus_dir=corpus,
                gold_path=gold,
                output_dir=tmp_path / "bad",
                role_manifest=roles,
                retrieval_path=variant,
                config=config,
                selected_lambda_path=path,
            )
    prepare_experiment(
        corpus_dir=corpus,
        gold_path=gold,
        output_dir=tmp_path / "final",
        role_manifest=roles,
        retrieval_path=candidates,
        config=config,
        selected_lambda_path=path,
    )
