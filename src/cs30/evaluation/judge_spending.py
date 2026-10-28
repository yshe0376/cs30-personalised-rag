"""Read saved attempt records to estimate spending; never contacts a provider."""

from __future__ import annotations

import argparse
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


def _rows(path: Path) -> list[dict[str, Any]]:
    """Read complete JSONL rows; an unfinished append requires another snapshot."""
    data = path.read_bytes()
    lines = data.splitlines(keepends=True)
    rows = []
    for index, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except (ValueError, UnicodeError) as exc:
            if index == len(lines) and not data.endswith(b"\n"):
                raise ValueError(
                    f"{path}: final row is being written; retry this read-only command"
                ) from exc
            raise ValueError(f"{path}:{index}: malformed JSONL") from exc
        if not isinstance(row, dict):
            raise ValueError(f"{path}:{index}: expected a JSON object")
        rows.append(row)
    return rows


def collect_attempts(
    ledgers: list[Path], correctness_results: list[Path], *, model: str
) -> tuple[list[dict], int]:
    """Union ledgers and new correctness results by persistent attempt ID."""
    attempts: dict[str, dict] = {}
    duplicates = 0

    def add(row: dict, model_revision: str | None) -> None:
        nonlocal duplicates
        if not isinstance(row, dict):
            raise ValueError("each attempt must be a JSON object")
        identity = row.get("attempt_id")
        if not isinstance(identity, str) or not identity.strip():
            raise ValueError("attempt_id missing: legacy records cannot be safely deduplicated")
        if model_revision != model:
            raise ValueError(
                f"priced model {model!r} differs from recorded model {model_revision!r}"
            )
        available = row.get("usage_available")
        if type(available) is not bool:
            raise ValueError("usage_available must explicitly be true or false")
        usage = {
            name: row.get(name) for name in ("input_tokens", "output_tokens", "thought_tokens")
        }
        if available and any(type(value) is not int or value < 0 for value in usage.values()):
            raise ValueError("known usage requires nonnegative integer token counters")
        if not available and any(value is not None for value in usage.values()):
            raise ValueError("unknown usage must contain null token counters")
        if available and usage["thought_tokens"] > usage["output_tokens"]:
            raise ValueError("thinking tokens must already be included in output tokens")
        record = dict(
            task=row.get("task", "correctness"),
            model=model_revision,
            provider_response_id=row.get("provider_response_id"),
            usage_available=available,
            **usage,
        )
        if identity in attempts:
            if attempts[identity] != record:
                raise ValueError(f"conflicting records for attempt_id {identity}")
            duplicates += 1
        else:
            attempts[identity] = record

    for path in ledgers:
        for row in _rows(path):
            if row.get("schema_version") != "1.0" or row.get("task") not in {
                "correctness",
                "adaptation",
                "discrimination",
                "evidence_support",
            }:
                raise ValueError(f"{path}: not a supported judge attempt ledger")
            add(row, row.get("model_revision"))
    for path in correctness_results:
        for row in _rows(path):
            if "judge_attempts" not in row or "judge_calls_this_run" not in row:
                raise ValueError(f"{path}: expected correctness score rows, not result envelopes")
            cached = row.get("cache_hit", False)
            fresh_calls = row["judge_calls_this_run"]
            history = row["judge_attempts"]
            if type(cached) is not bool or type(fresh_calls) is not int or fresh_calls < 0:
                raise ValueError(f"{path}: invalid cache flag or fresh call count")
            if not isinstance(history, list) or (cached and fresh_calls != 0):
                raise ValueError(f"{path}: inconsistent cached correctness history")
            # Cached history describes an earlier charge. Its ledger remains the source.
            if cached or fresh_calls == 0:
                continue
            if fresh_calls != len(history):
                raise ValueError(
                    f"{path}: fresh correctness call count differs from attempt history"
                )
            for attempt in history:
                add(attempt, row.get("judge_model"))
    return list(attempts.values()), duplicates


def estimate_spending(
    attempts: list[dict],
    *,
    input_price: Decimal,
    output_price: Decimal,
    usd_to_aud: Decimal,
    input_multiplier: Decimal = Decimal("1"),
    pause_aud: Decimal = Decimal("45"),
    cap_aud: Decimal = Decimal("60"),
    actual_spend_aud: Decimal | None = None,
) -> dict:
    """Compute a transparent estimate from known usage, with an explicit FX rate."""
    values = (input_price, output_price, usd_to_aud, input_multiplier, pause_aud, cap_aud)
    if any(not value.is_finite() or value < 0 for value in values):
        raise ValueError("prices, rates and limits must be finite and nonnegative")
    if usd_to_aud <= 0 or input_multiplier < 1 or not 0 < pause_aud < cap_aud:
        raise ValueError("FX must be positive, multiplier >= 1, and 0 < pause < cap")
    if actual_spend_aud is not None and (not actual_spend_aud.is_finite() or actual_spend_aud < 0):
        raise ValueError("actual full-Dev spending must be finite and nonnegative")
    known = [row for row in attempts if row["usage_available"]]
    unknown = len(attempts) - len(known)
    inputs = sum(row["input_tokens"] for row in known)
    outputs = sum(row["output_tokens"] for row in known)
    thoughts = sum(row["thought_tokens"] for row in known)
    usd = (Decimal(inputs) * input_price + Decimal(outputs) * output_price) / 1_000_000
    adjusted_usd = (
        Decimal(inputs) * input_multiplier * input_price + Decimal(outputs) * output_price
    ) / 1_000_000
    aud = adjusted_usd * usd_to_aud
    observed = max(aud, actual_spend_aud or Decimal("0"))
    action = (
        "STOP_CAP"
        if observed >= cap_aud
        else "PAUSE_AND_REPORT"
        if observed >= pause_aud
        else "VERIFY_UNKNOWN_USAGE"
        if unknown
        else "BELOW_PAUSE_ESTIMATE"
    )
    return {
        "attempt_count": len(attempts),
        "known_usage_attempts": len(known),
        "unknown_usage_attempts": unknown,
        "usage_complete": unknown == 0,
        "input_tokens": inputs,
        "output_tokens_including_thinking": outputs,
        "thought_tokens_already_in_output": thoughts,
        "input_usd_per_million": str(input_price),
        "output_usd_per_million": str(output_price),
        "usd_to_aud": str(usd_to_aud),
        "input_multiplier": str(input_multiplier),
        "known_list_price_usd": str(usd),
        "adjusted_estimate_aud": str(aud),
        "actual_full_dev_spend_aud": str(actual_spend_aud)
        if actual_spend_aud is not None
        else None,
        "pause_at_aud": str(pause_aud),
        "cap_aud": str(cap_aud),
        "action": action,
        "note": (
            "Estimate only; unknown calls, SDK-internal retries, taxes and billing "
            "differences may be missing. The actual provider bill is authoritative. "
            "This command does not stop running jobs."
        ),
    }


def _decimal(value: str) -> Decimal:
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise argparse.ArgumentTypeError("expected a decimal number") from exc
    if not result.is_finite():
        raise argparse.ArgumentTypeError("expected a finite decimal number")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attempt-log", type=Path, nargs="+", default=[])
    parser.add_argument("--correctness-results", type=Path, nargs="+", default=[])
    parser.add_argument(
        "--model", required=True, help="exact configured model priced by these rates"
    )
    parser.add_argument("--input-usd-per-million", type=_decimal, required=True)
    parser.add_argument("--output-usd-per-million", type=_decimal, required=True)
    parser.add_argument(
        "--usd-to-aud", type=_decimal, required=True, help="AUD per USD; supplied by the operator"
    )
    parser.add_argument("--input-multiplier", type=_decimal, default=Decimal("1"))
    parser.add_argument("--pause-at-aud", type=_decimal, default=Decimal("45"))
    parser.add_argument("--cap-aud", type=_decimal, default=Decimal("60"))
    parser.add_argument(
        "--actual-spend-aud",
        type=_decimal,
        help="observed spending attributable to this full-Dev run",
    )
    args = parser.parse_args(argv)
    if not args.attempt_log and not args.correctness_results:
        parser.error("provide at least one attempt ledger or correctness result file")
    try:
        attempts, duplicates = collect_attempts(
            args.attempt_log, args.correctness_results, model=args.model
        )
        report = estimate_spending(
            attempts,
            input_price=args.input_usd_per_million,
            output_price=args.output_usd_per_million,
            usd_to_aud=args.usd_to_aud,
            input_multiplier=args.input_multiplier,
            pause_aud=args.pause_at_aud,
            cap_aud=args.cap_aud,
            actual_spend_aud=args.actual_spend_aud,
        )
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    report["duplicate_records_excluded"] = duplicates
    print(json.dumps(report, indent=2))
    return 0 if report["action"] == "BELOW_PAUSE_ESTIMATE" else 3
