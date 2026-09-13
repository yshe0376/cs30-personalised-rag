"""Tests for the W5 M4 downstream handoff packager."""

from __future__ import annotations

import importlib.util
import json
import zipfile
from pathlib import Path


def _load_packager():
    path = Path(__file__).parents[1] / "scripts/package_w5_m4_handoffs.py"
    spec = importlib.util.spec_from_file_location("package_w5_m4_handoffs", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_fixture_artifacts(root: Path) -> None:
    source = root / "source_corpus"
    corpus = root / "corpus"
    source.mkdir(parents=True)
    corpus.mkdir()
    (source / "corpus_manifest.json").write_text(
        json.dumps({"corpus_version": "source-v1"}), encoding="utf-8"
    )
    (source / "openstax_document.json").write_text("{}\n", encoding="utf-8")
    (corpus / "manifest.json").write_text(
        json.dumps({"corpus_id": "corpus-v1", "chunk_config_id": "config-v1"}),
        encoding="utf-8",
    )
    for name in (
        "anomalies.json",
        "sample_records.jsonl",
        "schema.json",
        "statistics.json",
        "traceback_records.json",
    ):
        (corpus / name).write_text("{}\n", encoding="utf-8")
    (corpus / "records.jsonl").write_text('{"chunk_id":"c1"}\n', encoding="utf-8")


def test_package_handoffs_separates_m3_and_m5_artifacts(tmp_path: Path) -> None:
    module = _load_packager()
    artifact_root = tmp_path / "artifacts"
    output_dir = tmp_path / "handoffs"
    _write_fixture_artifacts(artifact_root)

    manifest = module.package_handoffs(
        artifact_root, output_dir, delivery_date="2026-09-13"
    )

    assert manifest["source_corpus_version"] == "source-v1"
    assert manifest["chunk_corpus_id"] == "corpus-v1"
    assert manifest["chunk_config_id"] == "config-v1"
    assert (output_dir / "handoff_manifest.json").is_file()

    with zipfile.ZipFile(output_dir / "m3_unified_source_corpus.zip") as archive:
        names = archive.namelist()
        assert "m3_unified_source_corpus/source_corpus/openstax_document.json" in names
        assert not any("records.jsonl" in name for name in names)

    with zipfile.ZipFile(output_dir / "m5_retrieval_corpus.zip") as archive:
        names = archive.namelist()
        assert "m5_retrieval_corpus/corpus/records.jsonl" in names
        assert not any("openstax_document.json" in name for name in names)


def test_package_handoffs_refuses_to_mix_with_existing_output(tmp_path: Path) -> None:
    module = _load_packager()
    artifact_root = tmp_path / "artifacts"
    output_dir = tmp_path / "handoffs"
    _write_fixture_artifacts(artifact_root)
    output_dir.mkdir()
    (output_dir / "unrelated.txt").write_text("keep", encoding="utf-8")

    try:
        module.package_handoffs(
            artifact_root, output_dir, delivery_date="2026-09-13"
        )
    except FileExistsError as exc:
        assert "not empty" in str(exc)
    else:
        raise AssertionError("expected the packager to reject a non-empty output folder")
