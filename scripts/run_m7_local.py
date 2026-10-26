"""Local M7 setup and Dev API launcher. Default status never calls an API."""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path

from cs30.config import _load_local_env
from cs30.generation.compatible import parse_extra_body
from cs30.v2.experiment import load_prepared

PROJECT = Path(__file__).resolve().parents[1]
DEFAULT_ROOT = PROJECT / "artifacts/m7-readiness-20261026"
SPLIT = PROJECT / "docs/examples/v2-generation-split-dev154-test187.json"
REPEATS = PROJECT / "docs/results/m7_api_readiness_20261023/noise_question_ids.json"
CORPUS = "2.0.0-dev.m4-four-book-main-a1fe99e"
CANDIDATES = "m7_qwen3_d0.10_b0.90_original_top20.jsonl"


def cli(root: Path, label: str, arguments: list[str]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    log = root / f"{label}.log"
    with log.open("a", encoding="utf-8") as stream:
        result = subprocess.run(
            [sys.executable, "-m", "cs30.v2.experiment_cli", *arguments],
            cwd=PROJECT, stdout=stream, stderr=subprocess.STDOUT, check=False,
        )
    if result.returncode:
        raise ValueError(f"{label} stopped (exit {result.returncode}); inspect {log}")
    print(f"{label}: OK ({log})")


def prepare(root: Path, batch: str, model: str) -> Path:
    # The downloader verifies existing bytes too; no model downloads are needed.
    from fetch_v2_experiment_inputs import fetch

    inputs = root / "inputs"
    fetch(inputs)
    converted = root / "converted"
    if not converted.exists():
        cli(root, "convert", [
            "convert-gold", "--gold", str(inputs / "gold_v0_1_3.jsonl"),
            "--corpus-dir", str(inputs / CORPUS), "--split-map", str(SPLIT),
            "--output-dir", str(converted),
        ])
    common = [
        "prepare", "--corpus-dir", str(inputs / CORPUS),
        "--gold", str(converted / "gold.jsonl"),
        "--gold-conversion-manifest", str(converted / "conversion_manifest.json"),
        "--role-manifest", str(inputs / "role_labels_v2_provenance_manifest.json"),
        "--retrieval", str(inputs / CANDIDATES), "--require-retrieval",
        "--model", model, "--split", "dev", "--candidate-k", "20", "--evidence-k", "5",
    ]
    candidates = root / "dev-candidates"
    if not candidates.exists():
        cli(root, "prepare-candidates", [*common, "--output-dir", str(candidates)])
    selection = root / "selected-lambda.json"
    if not selection.exists():
        cli(root, "select-lambda", [
            "select-lambda", "--prepared-dir", str(candidates),
            "--lambdas", "0", "0.1", "0.2", "0.35", "0.5", "--output", str(selection),
        ])
    model_key = hashlib.sha256(model.encode()).hexdigest()[:12]
    destination = root / f"{batch}-{model_key}-prepared"
    if not destination.exists():
        extras = ["--limit", "10"] if batch == "smoke" else []
        if batch == "probe":
            extras = ["--limit", "1"]
        if batch == "repeat":
            extras = ["--question-ids", str(REPEATS)]
        cli(root, f"prepare-{batch}", [
            *common, "--selected-lambda", str(selection), *extras,
            "--output-dir", str(destination),
        ])
    manifest, config, *_ = load_prepared(destination)
    if config.generator_model != model or config.split != "dev":
        raise ValueError("prepared model/split mismatch; choose a new output root")
    if not manifest["source_retrieval_sha256"] or not manifest["role_coverage_complete"]:
        raise ValueError("explicit M6 candidates and complete Roles are required")
    cli(root, f"check-{batch}", ["check", "--prepared-dir", str(destination)])
    print(
        f"Prepared {manifest['question_count']} Dev questions / {manifest['expected_runs']} cells"
    )
    return destination


def run_arguments(
    settings: dict[str, str], prepared: Path, batch: str, *, resume: bool = False,
    run_label: str | None = None,
) -> list[str]:
    required = ["M7_MODEL", "M7_BASE_URL", "M7_PROVIDER", "M7_MODEL_VERSION"]
    missing = [name for name in required if not settings.get(name, "").strip()]
    if missing:
        raise ValueError("Fill local .env.m7: " + ", ".join(missing))
    budget_name = f"M7_{batch.upper()}_REQUEST_CAP"
    budget = int(settings.get(budget_name, "0"))
    tokens = int(settings.get("M7_MAX_OUTPUT_TOKENS", "0"))
    concurrency = int(settings.get("M7_CONCURRENCY", "3"))
    if budget < 1 or tokens < 1 or concurrency < 1:
        raise ValueError(f"Set a positive {budget_name}, M7_MAX_OUTPUT_TOKENS and concurrency")
    mode = settings.get("M7_OUTPUT_FORMAT", "").strip() or "auto"
    if mode not in {"auto", "json_schema", "json_object", "text"}:
        raise ValueError("M7_OUTPUT_FORMAT must be auto/json_schema/json_object/text")
    if batch not in {"smoke", "probe"} and mode == "auto":
        raise ValueError("Dev/repeat require a smoke-verified explicit M7_OUTPUT_FORMAT")
    key_env = settings.get("M7_API_KEY_ENV", "M7_GENERATION_API_KEY")
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key_env):
        raise ValueError("M7_API_KEY_ENV must be an environment-variable name")
    extra_body = settings.get("M7_EXTRA_BODY", "{}") or "{}"
    parse_extra_body(extra_body)
    transport_retries = int(settings.get("M7_TRANSPORT_RETRIES", "3"))
    if transport_retries < 0:
        raise ValueError("M7_TRANSPORT_RETRIES must be nonnegative")
    if run_label is not None and not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", run_label):
        raise ValueError("run-label must contain lowercase letters, numbers and hyphens")
    suffix = f"-{run_label}-run" if run_label else "-run"
    output = prepared.with_name(prepared.name.removesuffix("-prepared") + suffix)
    arguments = [
        "run", "--prepared-dir", str(prepared), "--output-dir", str(output),
        "--provider", "openai-compatible", "--base-url", settings["M7_BASE_URL"],
        "--provider-name", settings["M7_PROVIDER"],
        "--model-version", settings["M7_MODEL_VERSION"],
        "--api-key-env", key_env, "--extra-body", extra_body,
        "--structured-output", mode, "--max-output-tokens", str(tokens),
        "--max-api-requests", str(budget), "--concurrency", str(concurrency),
        "--timeout", "120", "--transport-retries", str(transport_retries),
        "--stop-after-errors", "3",
    ]
    if settings.get("M7_API_SEED", "").strip():
        arguments += ["--api-seed", str(int(settings["M7_API_SEED"]))]
    if resume:
        arguments.append("--resume")
    return arguments


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("status", "prepare", "run"), nargs="?", default="status")
    parser.add_argument("--batch", choices=("probe", "smoke", "dev", "repeat"), default="smoke")
    parser.add_argument("--env-file", type=Path, default=PROJECT / ".env.m7")
    parser.add_argument(
        "--credentials-file", type=Path, default=PROJECT / ".env.m7.credentials",
    )
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--dry-run", action="store_true", help="validate without sending requests")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--run-label", help="new run identity when smoke settings change")
    args = parser.parse_args(argv)
    _load_local_env(args.credentials_file)
    _load_local_env(args.env_file)
    root = args.root.resolve()
    settings = dict(os.environ)
    if args.action == "status":
        print(f"Local settings: {args.env_file}")
        print(f"Inputs and outputs: {root}")
        key_env = settings.get("M7_API_KEY_ENV", "M7_GENERATION_API_KEY")
        for name in ("M7_MODEL", "M7_PROVIDER", "M7_BASE_URL", "M7_MODEL_VERSION",
                     key_env, "M7_OUTPUT_FORMAT", "M7_MAX_OUTPUT_TOKENS"):
            print(f"{name}: {'configured' if settings.get(name, '').strip() else 'missing'}")
        for batch in ("PROBE", "SMOKE", "DEV", "REPEAT"):
            name = f"M7_{batch}_REQUEST_CAP"
            print(f"{name}: {settings.get(name, '0')} (0 disables requests)")
        print("No API calls. Check positive token and request limits before running.")
        return 0
    try:
        model = settings.get("M7_MODEL", "").strip() or "readiness-no-api"
        if args.action == "run":
            # Check missing provider/budget settings before doing any preparation.
            run_arguments(
                settings, root / "pending-prepared", args.batch,
                resume=args.resume, run_label=args.run_label,
            )
            key_env = settings.get("M7_API_KEY_ENV", "M7_GENERATION_API_KEY")
            if not args.dry_run and not settings.get(key_env, "").strip():
                raise ValueError(f"Fill {key_env} locally; never paste it into chat")
        prepared = prepare(root, args.batch, model)
        if args.action == "prepare":
            return 0
        arguments = run_arguments(
            settings, prepared, args.batch, resume=args.resume, run_label=args.run_label,
        )
        if args.dry_run:
            print("API configuration validated; no API requests sent.")
            return 0
        model_key = hashlib.sha256(model.encode()).hexdigest()[:12]
        label = f"-{args.run_label}" if args.run_label else ""
        cli(root, f"run-{args.batch}-{model_key}{label}", arguments)
        return 0
    except (OSError, ValueError) as exc:
        print(f"M7 setup: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
