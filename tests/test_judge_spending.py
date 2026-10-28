"""Offline spending arithmetic, attempt identity and operator pause signals."""

import json
from decimal import Decimal

import pytest

from cs30.evaluation.judge_spending import collect_attempts, estimate_spending, main


def attempt(identity="a1", **updates):
    return (
        dict(
            schema_version="1.0",
            task="correctness",
            attempt_id=identity,
            model_revision="fixture",
            provider_response_id="response",
            usage_available=True,
            input_tokens=1_000_000,
            output_tokens=2_000_000,
            thought_tokens=500_000,
        )
        | updates
    )


def write(path, rows):
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return path


def estimate(rows, **kwargs):
    return estimate_spending(
        rows,
        input_price=Decimal("0.25"),
        output_price=Decimal("1.5"),
        usd_to_aud=Decimal("2"),
        **kwargs,
    )


def test_price_fx_and_input_only_buffer_never_add_thinking_twice():
    report = estimate([attempt()], input_multiplier=Decimal("1.15"))
    assert Decimal(report["known_list_price_usd"]) == Decimal("3.25")
    assert Decimal(report["adjusted_estimate_aud"]) == Decimal("6.575")
    assert report["output_tokens_including_thinking"] == 2_000_000
    assert report["thought_tokens_already_in_output"] == 500_000
    assert report["action"] == "BELOW_PAUSE_ESTIMATE"


def test_ledgers_and_correctness_results_union_without_double_counting(tmp_path):
    row = attempt()
    ledger = write(tmp_path / "calls", [row, attempt("a2", task="evidence_support")])
    fresh = dict(
        judge_model="fixture", judge_calls_this_run=1, cache_hit=False, judge_attempts=[row]
    )
    cached = dict(
        judge_model="fixture", judge_calls_this_run=0, cache_hit=True, judge_attempts=[row]
    )
    results = write(tmp_path / "scores", [fresh, cached])
    records, duplicates = collect_attempts([ledger, ledger], [results, results], model="fixture")
    assert len(records) == 2 and duplicates == 4
    assert Decimal(estimate(records)["known_list_price_usd"]) == Decimal("6.5")


def test_distinct_attempts_with_same_provider_id_are_not_lost(tmp_path):
    ledger = write(tmp_path / "calls", [attempt("a1"), attempt("a2")])
    records, duplicates = collect_attempts([ledger], [], model="fixture")
    assert len(records) == 2 and duplicates == 0


def test_missing_usage_is_not_a_free_call_or_a_below_budget_guarantee(tmp_path):
    missing = attempt(
        "a2", usage_available=False, input_tokens=None, output_tokens=None, thought_tokens=None
    )
    ledger = write(tmp_path / "calls", [attempt(), missing])
    records, _ = collect_attempts([ledger], [], model="fixture")
    report = estimate(records)
    assert report["usage_complete"] is False and report["unknown_usage_attempts"] == 1
    assert report["attempt_count"] == 2 and report["known_usage_attempts"] == 1
    assert report["action"] == "VERIFY_UNKNOWN_USAGE"


@pytest.mark.parametrize(
    ("amount", "expected"),
    [("44.99", "BELOW_PAUSE_ESTIMATE"), ("45", "PAUSE_AND_REPORT"), ("60", "STOP_CAP")],
)
def test_actual_spend_at_pause_or_cap_takes_precedence(amount, expected):
    report = estimate([], actual_spend_aud=Decimal(amount))
    assert report["action"] == expected


@pytest.mark.parametrize(
    ("output", "action"), [(15_000_000, "PAUSE_AND_REPORT"), (20_000_000, "STOP_CAP")]
)
def test_estimated_pause_and_cap_are_inclusive(output, action):
    report = estimate([attempt(input_tokens=0, output_tokens=output, thought_tokens=0)])
    assert report["action"] == action


@pytest.mark.parametrize(
    "change",
    [
        {"attempt_id": None},
        {"usage_available": None},
        {"input_tokens": -1},
        {"input_tokens": True},
        {"input_tokens": None},
        {"thought_tokens": 3_000_000},
        {"usage_available": False},
        {"model_revision": "other"},
    ],
)
def test_ambiguous_or_wrong_price_records_are_rejected(tmp_path, change):
    ledger = write(tmp_path / "calls", [attempt(**change)])
    with pytest.raises(ValueError):
        collect_attempts([ledger], [], model="fixture")


def test_duplicate_identity_with_different_usage_is_rejected(tmp_path):
    ledger = write(tmp_path / "calls", [attempt(), attempt(input_tokens=2)])
    with pytest.raises(ValueError, match="conflicting"):
        collect_attempts([ledger], [], model="fixture")


def test_legacy_correctness_missing_attempt_ids_is_not_guessed(tmp_path):
    legacy = dict(judge_model="fixture", judge_calls_this_run=1, judge_attempts=[{}])
    result = write(tmp_path / "legacy", [legacy])
    with pytest.raises(ValueError, match="attempt_id missing"):
        collect_attempts([], [result], model="fixture")


@pytest.mark.parametrize(
    "change",
    [
        {"cache_hit": "false"},
        {"judge_calls_this_run": False},
        {"judge_calls_this_run": -1},
        {"cache_hit": True},
        {"judge_attempts": None},
    ],
)
def test_invalid_cache_metadata_cannot_silently_skip_real_cost(tmp_path, change):
    record = (
        dict(
            judge_model="fixture",
            judge_calls_this_run=1,
            cache_hit=False,
            judge_attempts=[attempt()],
        )
        | change
    )
    path = write(tmp_path / "scores", [record])
    with pytest.raises(ValueError):
        collect_attempts([], [path], model="fixture")


@pytest.mark.parametrize("data", [b'{"unfinished":', b"{}\n{broken}\n", b"[]\n"])
def test_partial_or_corrupt_files_do_not_silently_reduce_estimates(tmp_path, data):
    path = tmp_path / "calls"
    path.write_bytes(data)
    with pytest.raises(ValueError):
        collect_attempts([path], [], model="fixture")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"input_multiplier": Decimal("0.9")},
        {"pause_aud": Decimal("70")},
        {"actual_spend_aud": Decimal("NaN")},
        {"cap_aud": Decimal("-1")},
    ],
)
def test_invalid_budget_options_are_rejected(kwargs):
    with pytest.raises(ValueError):
        estimate([], **kwargs)


def test_cli_requires_explicit_prices_fx_and_needs_no_network(tmp_path, capsys):
    log = write(tmp_path / "calls", [attempt()])
    args = [
        "--attempt-log",
        str(log),
        "--model",
        "fixture",
        "--input-usd-per-million",
        "0.25",
        "--output-usd-per-million",
        "1.5",
        "--usd-to-aud",
        "2",
    ]
    assert main(args) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["attempt_count"] == 1 and report["duplicate_records_excluded"] == 0
    assert main(args + ["--actual-spend-aud", "45"]) == 3
    assert json.loads(capsys.readouterr().out)["action"] == "PAUSE_AND_REPORT"
    with pytest.raises(SystemExit) as exc:
        main(args[:-2])
    assert exc.value.code == 2
