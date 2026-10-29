"""Package completed Test scores and verify them with the existing offline readers.

This tool never constructs a provider, retries a judge or changes scoring policy.
All original files are copied byte-for-byte into a separate audit directory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import socket
import sys
import tarfile
from pathlib import Path, PurePosixPath, PureWindowsPath
from types import SimpleNamespace

TASKS = ("correctness", "adaptation", "discrimination", "evidence_support")
COMPONENTS = {
    "adaptation": "adaptation_results.jsonl",
    "discrimination": "discrimination_results.jsonl",
    "evidence_support": "evidence_support_results.jsonl",
    "unresolved": "judge_unresolved.jsonl",
}


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def read_rows(path):
    # JSONL is delimited by physical LF, not Unicode separators inside strings.
    with Path(path).open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def save(path, value):
    Path(path).write_bytes((json.dumps(value, indent=2, sort_keys=True) + "\n").encode())


def save_rows(path, values):
    with Path(path).open("w", encoding="utf-8", newline="\n") as stream:
        for value in values:
            stream.write(json.dumps(value, ensure_ascii=True, sort_keys=True) + "\n")


def child(root, relative):
    """Reject absolute, platform-specific, traversal and symlink escapes."""
    relative = str(relative)
    part = PurePosixPath(relative)
    if (
        "\\" in relative
        or part.is_absolute()
        or PureWindowsPath(relative).drive
        or ".." in part.parts
        or not part.parts
    ):
        raise ValueError("Unsafe package path")
    path = root.joinpath(*part.parts)
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("Package path escapes root")
    return path


def inventory(root):
    return {
        path.relative_to(root).as_posix(): sha(path)
        for path in sorted(root.rglob("*"))
        if path.is_file() and path != root / "SHA256SUMS.json"
    }


def verify_inventory(root):
    expected = read_json(root / "SHA256SUMS.json")
    for relative, digest in expected.items():
        if sha(child(root, relative)) != digest:
            raise ValueError("Package hash mismatch: " + relative)
    if inventory(root) != expected:
        raise ValueError("Package inventory has missing or extra files")
    return len(expected)


def compatible_export(source, destination):
    """Export a value-identical copy for the unchanged legacy JSONL reader."""
    destination.mkdir(parents=True, exist_ok=False)
    manifest = read_json(source / "judge_evaluation_manifest.json")
    proof = {}
    for name, filename in COMPONENTS.items():
        original = source / filename
        if sha(original) != manifest["output_sha256"][name]:
            raise ValueError("Original judge hash mismatch: " + filename)
        values = read_rows(original)
        target = destination / filename
        save_rows(target, values)
        legacy_values = [json.loads(x) for x in target.read_text().splitlines() if x]
        if read_rows(target) != values or legacy_values != values:
            raise ValueError("Export changed decoded values")
        proof[filename] = {
            "original_sha256": sha(original),
            "export_sha256": sha(target),
            "records": len(values),
            "decoded_values_identical": True,
        }
        manifest["output_sha256"][name] = sha(target)
    manifest["serialization_source_manifest_sha256"] = sha(
        source / "judge_evaluation_manifest.json"
    )
    save(destination / "judge_evaluation_manifest.json", manifest)
    return proof


def copy_file(source, destination):
    if source.is_symlink() or not source.is_file():
        raise ValueError("Expected a regular file: " + str(source))
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    if sha(source) != sha(destination):
        raise ValueError("Copy differs from original")


def copy_tree(source, destination):
    for path in sorted(source.rglob("*")):
        if path.is_symlink():
            raise ValueError("Symlink in audit sources")
        if path.is_file() and "__pycache__" not in path.parts:
            copy_file(path, destination / path.relative_to(source))


def relocated_path(filename, run, repo, plan):
    """Resolve original machine paths without editing their sealed records."""
    parser = PureWindowsPath if PureWindowsPath(plan["repo"]).drive else PurePosixPath
    original = parser(filename)
    original_repo = parser(plan["repo"])
    script_roots = {parser(p).parent for p in plan["script_sha256"]}
    if len(script_roots) != 1:
        raise ValueError("Sealed scripts must share one run directory")
    original_run = next(iter(script_roots))
    for old_root, new_root in ((original_run, run), (original_repo, repo)):
        try:
            relative = original.relative_to(old_root)
        except ValueError:
            continue
        return child(new_root, relative.as_posix())
    raise ValueError("Sealed path is outside the run and repository")


def validate_run(run, repo=None):
    """Validate the sealed plan and receipts before copying any completed run."""
    plan = read_json(run / "run-plan.json")
    if (run / "run-plan.sha256").read_text().strip() != sha(run / "run-plan.json"):
        raise ValueError("Run-plan seal mismatch")
    if len(plan["jobs"]) != 4 or {j["task"] for j in plan["jobs"]} != set(TASKS):
        raise ValueError("Expected exactly the four Test tasks")
    repo = repo or Path(plan.get("repo", run))
    for filename, digest in {**plan["input_sha256"], **plan["script_sha256"]}.items():
        if sha(relocated_path(filename, run, repo, plan)) != digest:
            raise ValueError("Frozen input or script changed: " + filename)
    for job in plan["jobs"]:
        receipt = read_json(run / "receipts" / f"{job['task']}.done.json")
        output = relocated_path(job["output"], run, repo, plan)
        files = [output] if job["output_kind"] == "file" else sorted(output.rglob("*"))
        expected = receipt["output_sha256"]
        actual = {filename: sha(relocated_path(filename, run, repo, plan)) for filename in expected}
        locations = {relocated_path(filename, run, repo, plan) for filename in expected}
        if (
            not actual
            or locations != {p for p in files if p.is_file()}
            or receipt["exit_code"] not in (0, 3)
            or receipt["plan_sha256"] != sha(run / "run-plan.json")
            or receipt["output_sha256"] != actual
        ):
            raise ValueError("Incomplete or modified completed task: " + job["task"])
    return plan


def load_native(package, repo):
    sys.path.insert(0, str(repo / "src"))
    from cs30.evaluation import v2_generation_cli as cli
    from cs30.evaluation.judge_results import (
        assemble_judge_results,
        load_judge_envelopes,
        load_judge_evaluation_outputs,
    )
    from cs30.evaluation.level_profiles import load_profile_checklist_package
    from cs30.evaluation.test_gate_analysis import main_adaptation
    from cs30.evaluation.v2_generation_artifacts import load_open_answer_scores
    from cs30.evaluation.v2_generation_models import JudgeConfiguration

    items = cli._load_inputs(package / "inputs/generation_evaluation_inputs.jsonl")
    adapter = read_json(package / "inputs/adapter_manifest.json")
    scores = load_open_answer_scores(
        package / "correctness/open_answer_scores.jsonl",
        items,
        gold_sha256=adapter["gold_sha256"],
        binding_path=package / "correctness/score-binding.json",
        evaluation_inputs_sha256=sha(package / "inputs/generation_evaluation_inputs.jsonl"),
    )
    profile = load_profile_checklist_package(package / "config/profile_checklist.frozen.json")
    config = JudgeConfiguration.model_validate(read_json(package / "config/judge-config.low.json"))
    saved = load_judge_evaluation_outputs(package / "judge_evaluation")
    envelopes = load_judge_envelopes(package / "judge-results.jsonl")
    cli._validate_judge_execution_records(
        envelopes,
        judge_execution_id=saved["manifest"]["provenance"]["judge_execution_id"],
        provider_name=config.provider,
    )
    rebuilt = assemble_judge_results(items, profile, config, envelopes)
    for name in COMPONENTS:
        if saved[name] != rebuilt[name]:
            raise ValueError("Canonical reassembly differs: " + name)
    target = {x["evaluation_id"]: x for x in saved["adaptation"] if x["is_target_level_evaluation"]}
    discrimination = {x["evaluation_id"]: x for x in saved["discrimination"]}
    evidence = {x["evaluation_id"]: x for x in saved["evidence_support"]}
    cell_rows = []
    for item in items:
        score = scores[item.evaluation_id]
        adaptation = target.get(item.evaluation_id)
        cell_rows.append(
            {
                "evaluation_id": item.evaluation_id,
                "run_id": item.run_id,
                "question_id": item.question_id,
                "condition": item.condition.value,
                "target_level": item.target_level.value,
                "eligibility": item.eligibility.value,
                "source_run_sha256": item.source_run_sha256,
                "answer_sha256": item.answer_sha256,
                "source_status": item.source_status.value,
                "correctness_status": score.score_status,
                "correctness_score": score.score if score.score_status == "scored" else None,
                "adaptation": adaptation,
                "main_adaptation": main_adaptation(adaptation) if adaptation else None,
                "discrimination_reference_only": discrimination.get(item.evaluation_id),
                "evidence_support_reference_only": evidence.get(item.evaluation_id),
            }
        )
    return cell_rows


def replay_analysis(package, repo):
    sys.path.insert(0, str(repo / "src"))
    # report returns its object and optionally writes it; no analysis file is replaced.
    import tempfile

    from cs30.evaluation.test_gate_readiness import report

    with tempfile.TemporaryDirectory(dir=package.parent) as temporary:
        result = report(
            SimpleNamespace(
                readiness=package / "config/readiness.json",
                inputs=package / "inputs/generation_evaluation_inputs.jsonl",
                adapter_manifest=package / "inputs/adapter_manifest.json",
                correctness_scores=package / "correctness/open_answer_scores.jsonl",
                correctness_binding=package / "correctness/score-binding.json",
                judge_evaluation_dir=package / "judge_evaluation",
                noise_floors=package / "config/dev-adaptation-noise-floors.json",
                output=Path(temporary) / "replayed.json",
            )
        )
    if result != read_json(package / "analysis/registered-test-analysis.json"):
        raise ValueError("Registered analysis replay differs")


def replay_adapter(package, audit):
    import tempfile

    from cs30.evaluation.v2_generation_cli import main as cli

    source = audit / "source"
    generation = source / "gpt-oss20b-run"
    with tempfile.TemporaryDirectory(dir=package.parent) as temporary:
        output = Path(temporary)
        argv = ["adapt-m7-artifacts", "--output-dir", str(output)]
        for flag, path in {
            "expected-experiment": generation / "expected_experiment.json",
            "generation-records": generation / "generation_records.jsonl",
            "saved-answers": generation / "saved_answers.jsonl",
            "run-manifest": generation / "run_manifest.json",
            "gold": source / "gpt-oss20b-prepared/gold.jsonl",
            "eligibility": source / "evaluation-config/eligibility.draft.jsonl",
            "lambda-selection": source / "gpt-oss20b-prepared/lambda_selection.json",
        }.items():
            argv.extend(["--" + flag, str(path)])
        if cli(argv) != 0:
            raise ValueError("M7 source adapter replay failed")
        for name in ("generation_evaluation_inputs.jsonl", "adapter_manifest.json"):
            if sha(output / name) != sha(package / "inputs" / name):
                raise ValueError("M7 source replay differs: " + name)


def verify(package, repo, audit=None):
    files = verify_inventory(package)
    cells = load_native(package, repo)
    if cells != read_rows(package / "scores_by_cell.jsonl"):
        raise ValueError("Convenience scores differ from native data")
    replay_analysis(package, repo)
    result = {
        "files_verified": files,
        "cells": len(cells),
        "native_canonical_reassembly_equal": True,
        "correctness_run_and_answer_binding_valid": True,
        "registered_analysis_replayed_identically": True,
        "api_calls": 0,
        "reportable": False,
    }
    if audit is not None:
        result["original_audit_files_verified"] = verify_inventory(audit)
        validate_run(audit, repo)
        manifest = read_json(package / "handoff_manifest.json")
        if inventory(audit) != manifest["original_audit_files"]:
            raise ValueError("Audit files differ from scoring handoff binding")
        for filename in COMPONENTS.values():
            if read_rows(audit / "final/judged" / filename) != read_rows(
                package / "judge_evaluation" / filename
            ):
                raise ValueError("Export differs from original judge values")
        if sha(audit / "results/correctness/open_answer_scores.jsonl") != sha(
            package / "correctness/open_answer_scores.jsonl"
        ):
            raise ValueError("Original correctness bytes differ")
        replay_adapter(package, audit)
        result["m7_source_adapter_replayed_identically"] = True
        result["original_receipts_and_frozen_files_unchanged"] = True
    return result


def scan_secrets(root):
    pattern = re.compile(rb"AIza[0-9A-Za-z_-]{35}|gh[pousr]_[0-9A-Za-z]{30,}")
    for path in root.rglob("*"):
        if path.is_file() and pattern.search(path.read_bytes()):
            raise ValueError("Possible credential in package: " + path.relative_to(root).as_posix())


def build(run, repo, out):
    plan = validate_run(run, repo)
    if out.is_relative_to(run) or run.is_relative_to(out) or out.is_relative_to(repo):
        raise ValueError("Output must be separate from the source run and Git repository")
    out.mkdir(parents=True, exist_ok=False)
    package = out / "m8-test-scoring-handoff-20261030"
    audit = out / "m8-test-scoring-audit-20261030"
    package.mkdir()
    audit.mkdir()
    for name in (
        "source",
        "adapted",
        "requests",
        "results",
        "caches",
        "ledgers",
        "receipts",
        "logs",
        "final",
        "analysis-v1",
    ):
        copy_tree(run / name, audit / name)
    for name in ("run-plan.json", "run-plan.sha256"):
        copy_file(run / name, audit / name)
    for name in plan["script_sha256"]:
        path = relocated_path(name, run, repo, plan)
        copy_file(path, audit / path.relative_to(run))
    originals = inventory(audit)
    for name in ("generation_evaluation_inputs.jsonl", "adapter_manifest.json"):
        copy_file(run / "adapted" / name, package / "inputs" / name)
    copy_file(
        run / "results/correctness/open_answer_scores.jsonl",
        package / "correctness/open_answer_scores.jsonl",
    )
    copy_file(
        run / "final/correctness-score-binding.json", package / "correctness/score-binding.json"
    )
    copy_file(run / "final/judge-results.jsonl", package / "judge-results.jsonl")
    proof = compatible_export(run / "final/judged", package / "judge_evaluation")
    save(package / "serialization-verification.json", proof)
    frozen = repo / "eval_inputs/m8/test-gates-20261029"
    for name in (
        "readiness.json",
        "dev-adaptation-noise-floors.json",
        "input-validation.json",
        "eligibility-review-waiver.json",
    ):
        copy_file(frozen / name, package / "config" / name)
    copy_file(
        repo / "docs/evaluation/level-profile-v1/profile_checklist.frozen.json",
        package / "config/profile_checklist.frozen.json",
    )
    copy_file(
        run / "source/evaluation-config/judge-config.low.json",
        package / "config/judge-config.low.json",
    )
    for name in ("REPORT.md", "missingness_by_task_level_condition.csv"):
        copy_file(run / "analysis-v1" / name, package / "analysis" / name)
    # Replay the approved report for the freshly exported manifest digest.
    sys.path.insert(0, str(repo / "src"))
    from cs30.evaluation.test_gate_readiness import report

    analysis = report(
        SimpleNamespace(
            readiness=package / "config/readiness.json",
            inputs=package / "inputs/generation_evaluation_inputs.jsonl",
            adapter_manifest=package / "inputs/adapter_manifest.json",
            correctness_scores=package / "correctness/open_answer_scores.jsonl",
            correctness_binding=package / "correctness/score-binding.json",
            judge_evaluation_dir=package / "judge_evaluation",
            noise_floors=package / "config/dev-adaptation-noise-floors.json",
            output=package / "analysis/registered-test-analysis.json",
        )
    )
    earlier = read_json(run / "analysis-v1/registered-test-analysis.json")
    if analysis != earlier:
        raise ValueError("Fresh package analysis differs from completed local analysis")
    save_rows(package / "scores_by_cell.jsonl", load_native(package, repo))
    save(
        package / "handoff_manifest.json",
        {
            "schema_version": "cs30-test-scoring-handoff-1",
            "cells": 2244,
            "production_scoring_commit": plan["source_commit"],
            "reporting_policy": analysis["policy"],
            "reportable": False,
            "source_release": "https://github.com/yshe0376/cs30-personalised-rag/releases/tag/v2-m7-api-test-gpt-oss20b-20261029",
            "original_and_derived_separate": True,
            "original_audit_files": originals,
            "consumer_entry": "scores_by_cell.jsonl",
            "api_calls_during_packaging": 0,
        },
    )
    (package / "README.md").write_text(
        "# Completed Test scoring handoff\n\n"
        "M8 owns evaluation aggregation and this report. M7 may consume the bound scores "
        "for integration or verification; no generation rerun is required.\n\n"
        "- analysis/REPORT.md: findings, missingness and limitations.\n"
        "- scores_by_cell.jsonl: 2,244 convenience rows joined by evaluation_id, run_id, "
        "answer_sha256 and source_run_sha256. Unknown scores are null.\n"
        "- inputs/, correctness/, judge-results.jsonl, judge_evaluation/: native inputs, "
        "bound correctness, saved judge envelopes and canonical assembled outputs.\n"
        "- config/: unchanged frozen reporting inputs; intermediate I3 and "
        "discrimination/citation support remain reference-only.\n"
        "- serialization-verification.json: equivalent JSON escaping for the existing "
        "reader, with source/export digests. No score or validation rule changes.\n"
        "- handoff_manifest.json and SHA256SUMS.json: provenance and exact file inventory.\n\n"
        "The companion audit archive contains byte-identical original results, requests, "
        "caches, per-attempt usage, completion receipts and M7 generation sources. "
        "Absolute paths in original audit records describe the original machine and are "
        "not portable execution commands. Do not rerun paid commands.\n\n"
        "Verify offline from the repository: `python scripts/build_test_scoring_handoff.py "
        "verify --package <this-extracted-directory> --repo <repository>`.\n\n"
        "Release publication is artifact availability, not approval of all research claims. "
        "Native reportable=false remains. Read the findings and uncertainty before "
        "citing conclusions.\n",
        encoding="utf-8",
        newline="\n",
    )
    copy_file(Path(__file__), package / "tools/build_test_scoring_handoff.py")
    for root in (package, audit):
        scan_secrets(root)
        save(root / "SHA256SUMS.json", inventory(root))
    verification = verify(package, repo, audit)
    validate_run(run, repo)
    save(out / "PACKAGE_VERIFICATION.json", verification)
    for root in (package, audit):
        archive = out / f"{root.name}.tar.gz"
        with tarfile.open(archive, "w:gz") as stream:
            for path in sorted(root.rglob("*")):
                if path.is_file():
                    stream.add(
                        path,
                        arcname=root.name + "/" + path.relative_to(root).as_posix(),
                        recursive=False,
                    )
    assets = [*sorted(out.glob("*.tar.gz")), out / "PACKAGE_VERIFICATION.json"]
    (out / "SHA256SUMS.txt").write_text(
        "".join(f"{sha(path)}  {path.name}\n" for path in assets), encoding="utf-8", newline="\n"
    )
    return verification


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    builder = commands.add_parser("build")
    builder.add_argument("--run-root", required=True, type=Path)
    builder.add_argument("--out", required=True, type=Path)
    verifier = commands.add_parser("verify")
    verifier.add_argument("--package", required=True, type=Path)
    verifier.add_argument("--audit", type=Path)
    for command in (builder, verifier):
        command.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()

    def no_network(*_args, **_kwargs):
        raise RuntimeError("Packaging and verification are offline")

    socket.socket.connect = no_network
    socket.create_connection = no_network
    if args.command == "build":
        result = build(args.run_root.resolve(), args.repo.resolve(), args.out.resolve())
    else:
        result = verify(
            args.package.resolve(),
            args.repo.resolve(),
            args.audit.resolve() if args.audit else None,
        )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
