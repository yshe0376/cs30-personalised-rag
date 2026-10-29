"""Offline handoff integrity tests with fictional data only."""

import importlib.util
import json
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "test_handoff", Path(__file__).resolve().parents[1] / "scripts/build_test_scoring_handoff.py"
)
handoff = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(handoff)


@pytest.mark.parametrize("separator", ["\u0085", "\u2028", "\u2029"])
def test_unicode_export_preserves_values_and_source(tmp_path, separator):
    source = tmp_path / "source"
    source.mkdir()
    values = [{"reason": "one" + separator + "two", "score": None}]
    hashes = {}
    for name, filename in handoff.COMPONENTS.items():
        path = source / filename
        path.write_text(json.dumps(values[0], ensure_ascii=False) + "\n", encoding="utf-8")
        hashes[name] = handoff.sha(path)
    handoff.save(
        source / "judge_evaluation_manifest.json",
        {"output_sha256": hashes, "provenance": {"source_run_sha256": "a" * 64}},
    )
    before = handoff.inventory(source)
    target = tmp_path / "export"
    proof = handoff.compatible_export(source, target)
    assert handoff.inventory(source) == before
    for filename in handoff.COMPONENTS.values():
        assert handoff.read_rows(target / filename) == values
        assert [json.loads(x) for x in (target / filename).read_text().splitlines()] == values
        assert proof[filename]["decoded_values_identical"]
    assert handoff.read_json(target / "judge_evaluation_manifest.json")["provenance"] == {
        "source_run_sha256": "a" * 64
    }


@pytest.mark.parametrize("path", ["../escape", "/absolute", "C:/absolute", "folder\\file"])
def test_reject_unsafe_package_paths(tmp_path, path):
    with pytest.raises(ValueError, match="Unsafe"):
        handoff.child(tmp_path, path)


def test_inventory_rejects_corruption_and_extra_files(tmp_path):
    payload = tmp_path / "scores.json"
    payload.write_text('{"score": null}')
    handoff.save(tmp_path / "SHA256SUMS.json", handoff.inventory(tmp_path))
    assert handoff.verify_inventory(tmp_path) == 1
    payload.write_text('{"score": 2}')
    with pytest.raises(ValueError, match="hash mismatch"):
        handoff.verify_inventory(tmp_path)
    payload.write_text('{"score": null}')
    (tmp_path / "unexpected").write_text("extra")
    with pytest.raises(ValueError, match="extra"):
        handoff.verify_inventory(tmp_path)


def test_export_rejects_changed_source_manifest(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "adaptation_results.jsonl").write_text('{"score": 0}\n')
    handoff.save(
        source / "judge_evaluation_manifest.json", {"output_sha256": {"adaptation": "0" * 64}}
    )
    with pytest.raises(ValueError, match="Original judge hash mismatch"):
        handoff.compatible_export(source, tmp_path / "export")


def test_copy_preserves_unknown_score_and_bytes(tmp_path):
    source = tmp_path / "source.jsonl"
    source.write_bytes(b'{"score":null,"status":"unresolved"}\r\n')
    target = tmp_path / "copy/score.jsonl"
    handoff.copy_file(source, target)
    assert target.read_bytes() == source.read_bytes()
    assert handoff.read_rows(target)[0]["score"] is None


def test_missing_receipt_stops_packaging(tmp_path):
    handoff.save(
        tmp_path / "run-plan.json",
        {
            "jobs": [{"task": task} for task in handoff.TASKS],
            "input_sha256": {},
            "script_sha256": {},
        },
    )
    (tmp_path / "run-plan.sha256").write_text(handoff.sha(tmp_path / "run-plan.json"))
    with pytest.raises(FileNotFoundError):
        handoff.validate_run(tmp_path)


def test_windows_receipt_paths_relocate_without_rewriting_records(tmp_path):
    plan = {
        "repo": "C:\\original\\repo",
        "script_sha256": {"C:\\original\\run\\run_test.py": "a" * 64},
    }
    run = tmp_path / "audit"
    repo = tmp_path / "repo"
    assert (
        handoff.relocated_path("C:\\original\\run\\results\\scores.jsonl", run, repo, plan)
        == run / "results/scores.jsonl"
    )
    assert (
        handoff.relocated_path("C:\\original\\repo\\config\\frozen.json", run, repo, plan)
        == repo / "config/frozen.json"
    )
    with pytest.raises(ValueError, match="outside"):
        handoff.relocated_path("C:\\unrelated\\key", run, repo, plan)


def test_changed_seal_rejected_before_any_copy(tmp_path):
    handoff.save(tmp_path / "run-plan.json", {"jobs": []})
    (tmp_path / "run-plan.sha256").write_text("0" * 64)
    with pytest.raises(ValueError, match="seal mismatch"):
        handoff.validate_run(tmp_path)
