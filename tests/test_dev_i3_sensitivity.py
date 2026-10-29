"""Reporting-only checks; all inputs are synthetic, with no model calls."""

import copy
import importlib.util
import json
from pathlib import Path

import pytest


def load_script(relative):
    path = Path(__file__).resolve().parents[1] / relative
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


REPORT = load_script("scripts/summarize_dev_i3_sensitivity.py")
DIAGNOSTICS = load_script("scripts/build_dev_diagnostics.py")


def sample(eid="one", eligibility="full"):
    item = {
        "evaluation_id": eid,
        "target_level": "intermediate",
        "condition": "P1R1_combined",
        "eligibility": eligibility,
    }
    record = dict(
        item,
        evaluated_level="intermediate",
        is_target_level_evaluation=True,
        enters_main_adaptation_result=eligibility in {"full", "endpoint_only"},
        criterion_pass_rate=2 / 3,
        criteria=[
            {"criterion_id": k, "verdict": v}
            for k, v in zip(("I1", "I2", "I3"), ("pass", "fail", "pass"), strict=True)
        ],
    )
    return item, record


def test_i3_changes_denominator_and_preserves_source():
    _, record = sample()
    before = copy.deepcopy(record)
    assert REPORT.rates(record) == (2 / 3, 0.5, 1)
    assert record == before


def test_expected_cells_keep_missing_and_exclude_cross_level():
    one, record = sample()
    two, _ = sample("two")
    three, _ = sample("three", "none")
    cross = dict(record, evaluation_id="cross", is_target_level_evaluation=False)
    summary = REPORT.summarize([one, two, three], [record, cross])
    main = next(
        r
        for r in summary
        if r["scope"] == "main_eligible_intermediate" and r["condition"] == "all_conditions"
    )
    assert (main["expected_cells"], main["resolved_cells"], main["unresolved_cells"]) == (2, 1, 1)
    assert main["mean_without_i3"] == 0.5
    all_rows = summary[0]
    assert all_rows["expected_cells"] == 3


def test_endpoint_only_retains_intermediate_in_main_scope():
    item, record = sample(eligibility="endpoint_only")
    main = REPORT.summarize([item], [record])[2]
    assert main["scope"] == "main_eligible_intermediate"
    assert main["resolved_cells"] == 1


def test_no_resolved_records_stay_null():
    item, _ = sample()
    assert REPORT.summarize([item], [])[0]["mean_without_i3"] is None


@pytest.mark.parametrize("change", ["duplicate", "missing", "na", "wrong_rate"])
def test_invalid_saved_judgements_are_rejected(change):
    _, record = sample()
    if change == "duplicate":
        record["criteria"].append(record["criteria"][0])
    elif change == "missing":
        record["criteria"].pop()
    elif change == "na":
        record["criteria"][2]["verdict"] = "not_applicable"
    else:
        record["criterion_pass_rate"] = 1.0
    with pytest.raises(ValueError):
        REPORT.rates(record)


def test_duplicate_or_unbound_records_are_rejected():
    item, record = sample()
    with pytest.raises(ValueError, match="duplicate"):
        REPORT.summarize([item], [record, record])
    with pytest.raises(ValueError, match="unbound"):
        REPORT.summarize([], [record])


def test_json_writer_sorts_requested_keys_and_uses_lf(tmp_path):
    path = tmp_path / "SOURCE_HASHES.json"
    DIAGNOSTICS.json_file(path, {"z": "last", "A": "first"}, sort_keys=True)
    assert list(json.loads(path.read_bytes())) == ["A", "z"]
    assert b"\r" not in path.read_bytes()
