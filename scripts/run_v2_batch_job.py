"""Start one durable local V2 batch, inspect progress, or resume its frozen snapshot."""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


def timestamp() -> str:
    return datetime.now(ZoneInfo("Australia/Sydney")).isoformat(timespec="seconds")


def alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def launch(job_dir: Path, *, resume: bool) -> dict:
    job = json.loads((job_dir / "job.json").read_bytes())
    progress_path = job_dir / "progress.json"
    if progress_path.exists():
        previous = json.loads(progress_path.read_bytes())
        if previous.get("status") in {"running", "verifying"} and alive(previous.get("worker_pid")):
            raise ValueError("this batch already has a live supervisor")
    command = [
        job["python"],
        "-u",
        str(Path(job["code_dir"]) / "scripts/run_v2_batch_job.py"),
        "worker",
        "--job-dir",
        str(job_dir),
    ]
    if resume:
        command.append("--resume")
    if sys.platform == "darwin":
        command = ["/usr/bin/caffeinate", "-i", "-s", *command]
    env = {**os.environ, "PYTHONPATH": str(Path(job["code_dir"]) / "src")}
    with (job_dir / "supervisor.log").open("ab") as stream:
        process = subprocess.Popen(
            command,
            cwd=job["code_dir"],
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=stream,
            stderr=stream,
            start_new_session=True,
        )
    result = {
        "launched_at": timestamp(),
        "launcher_pid": process.pid,
        "resume": resume,
        "job_dir": str(job_dir),
        "progress_file": str(progress_path),
    }
    (job_dir / "launch.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def worker(job_dir: Path, *, resume: bool) -> None:
    from cs30.v2.experiment import load_prepared
    from cs30.v2.experiment_checkpoint import atomic_json, load_cells, writer_lock
    from cs30.v2.experiment_models import GenerationRun
    from cs30.v2.io import read_jsonl, unique_models

    job = json.loads((job_dir / "job.json").read_bytes())
    _, _, matrix, *_ = load_prepared(Path(job["prepared_dir"]))
    output = job_dir / "output"
    with writer_lock(job_dir):
        command = [
            job["python"],
            "-u",
            "-m",
            "cs30.v2.experiment_cli",
            "run",
            "--prepared-dir",
            job["prepared_dir"],
            "--output-dir",
            str(output),
            "--provider",
            "ollama",
            "--timeout",
            str(job["timeout"]),
            "--max-output-tokens",
            str(job["max_output_tokens"]),
            "--context-window",
            str(job["context_window"]),
            "--stop-after-errors",
            "3",
        ]
        if resume:
            command.append("--resume")
        attempt = len(list(job_dir.glob("attempt-*.log"))) + 1
        log_path = job_dir / f"attempt-{attempt:03d}.log"
        env = {**os.environ, "PYTHONPATH": str(Path(job["code_dir"]) / "src")}
        started = time.monotonic()
        records = {}
        with log_path.open("xb") as stream:
            child = subprocess.Popen(
                command,
                cwd=job["code_dir"],
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=stream,
                stderr=stream,
                start_new_session=True,
            )

            def propagate(signum, frame):
                if child.poll() is None:
                    os.killpg(child.pid, signal.SIGINT)

            signal.signal(signal.SIGTERM, propagate)
            signal.signal(signal.SIGINT, propagate)

            def publish(status: str, **extra) -> None:
                for path in (output / "checkpoints").glob("*.json"):
                    value = json.loads(path.read_bytes())
                    records[value["record"]["run_id"]] = value["record"]
                counts = Counter(row["status"] for row in records.values())
                elapsed = time.monotonic() - started
                state = {
                    "schema_version": "0.1",
                    "status": status,
                    "updated_at": timestamp(),
                    "worker_pid": os.getpid(),
                    "child_pid": child.pid,
                    "source_commit": job["source_commit"],
                    "attempt": attempt,
                    "completed_cells": len(records),
                    "expected_cells": len(matrix.cases),
                    "status_counts": dict(counts),
                    "elapsed_this_attempt_seconds": round(elapsed, 1),
                    "log_file": str(log_path),
                    "output_dir": str(output),
                    "resume_supported": True,
                    "reportable": False,
                    **extra,
                }
                atomic_json(job_dir / "progress.json", state)
                resume_script = Path(job["code_dir"]) / "scripts/run_v2_batch_job.py"
                (job_dir / "README.md").write_text(
                    "# V2 Dev 批量运行\n\n"
                    f"状态：**{status}**；"
                    f"已保存 **{len(records)}/{len(matrix.cases)}** 个单元。\n\n"
                    f"更新时间：{state['updated_at']}。分状态计数：{dict(counts)}。\n\n"
                    f"[详细进度]({job_dir}/progress.json) · [本轮日志]({log_path}) · "
                    f"[保存答案]({output}/saved_answers.jsonl)\n\n"
                    "采用冻结输入中的 Role 包及正 lambda；生成产物交给 M8 独立评分。"
                    "运行报告不等于正式准确率。\n\n"
                    "关闭聊天不会取消这个独立进程；关机、系统休眠或手动结束进程会中断。"
                    "已完成单元有原子检查点，正在处理但未保存的一条可能重试。\n\n"
                    "续跑（原代码、输入、模型版本和参数均校验一致）：\n\n"
                    f"```bash\n{job['python']} {resume_script} "
                    f"resume --job-dir {job_dir}\n```\n\n"
                    f"代码快照：`{job['source_commit']}`。保持电脑接电，避免合盖导致休眠。\n",
                    encoding="utf-8",
                )

            publish("running")
            while child.poll() is None:
                time.sleep(5)
                publish("running")
            exit_code = child.wait()
            publish("verifying", exit_code=exit_code)
        if exit_code in {0, 3}:
            cells = load_cells(output / "checkpoints", matrix.cases)
            saved = unique_models(
                read_jsonl(output / "saved_answers.jsonl"), GenerationRun, "run_id"
            )
            expected = {cell.run_id for cell in matrix.cases}
            if set(cells) != expected or set(saved) != expected:
                raise ValueError("completed batch does not match every expected cell")
            manifest = json.loads((output / "run_manifest.json").read_bytes())
            from cs30.v2.io import sha256_bytes

            for relative, digest in manifest["output_sha256"].items():
                if sha256_bytes((output / relative).read_bytes()) != digest:
                    raise ValueError("completed batch output hash mismatch")
            atomic_json(
                job_dir / "verification.json",
                {
                    "status": "passed",
                    "checked_at": timestamp(),
                    "expected_cells": len(expected),
                    "checkpoint_count": len(cells),
                    "saved_answers": len(saved),
                    "output_hashes": "passed",
                    "status_counts": dict(Counter(row.status for row in saved.values())),
                    "reportable": False,
                },
            )
            publish(
                "completed_with_generation_failures" if exit_code == 3 else "completed",
                exit_code=exit_code,
            )
        else:
            publish("interrupted_resume_available", exit_code=exit_code)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("start", "resume", "status", "worker"))
    parser.add_argument("--job-dir", type=Path, required=True)
    parser.add_argument("--prepared-dir", type=Path)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--context-window", type=int, default=32768)
    parser.add_argument("--timeout", type=float, default=180)
    args = parser.parse_args(argv)
    if sys.platform == "win32":
        print(
            "V2 batch supervisor supports macOS/Linux only; use experiment_cli run on Windows.",
            file=sys.stderr,
        )
        return 2
    directory = args.job_dir.resolve()
    try:
        if args.command == "start":
            import shutil

            if directory.exists() or args.prepared_dir is None:
                raise ValueError("start needs a new job directory and prepared inputs")
            root = Path(__file__).resolve().parents[1]
            # Unrelated local changes are not copied into the frozen checkout.
            commit = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=root, text=True
            ).strip()
            directory.mkdir(parents=True)
            code = directory / "code"
            subprocess.run(
                ["git", "clone", "--local", "--no-hardlinks", "--quiet", str(root), str(code)],
                check=True,
            )
            prepared = directory / "inputs"
            shutil.copytree(args.prepared_dir.resolve(), prepared)
            job = {
                "schema_version": "0.1",
                "created_at": timestamp(),
                "source_commit": commit,
                "code_dir": str(code),
                "python": sys.executable,
                "prepared_dir": str(prepared),
                "context_window": args.context_window,
                "timeout": args.timeout,
                "max_output_tokens": 2048,
            }
            (directory / "job.json").write_text(json.dumps(job, indent=2) + "\n")
            print(json.dumps(launch(directory, resume=False)))
        elif args.command == "resume":
            print(json.dumps(launch(directory, resume=True)))
        elif args.command == "status":
            print((directory / "progress.json").read_text(encoding="utf-8"))
        else:
            worker(directory, resume=args.resume)
        return 0
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        if args.command == "worker":
            from cs30.v2.experiment_checkpoint import atomic_json

            atomic_json(
                directory / "supervisor_error.json",
                {
                    "status": "error",
                    "checked_at": timestamp(),
                    "error": str(exc),
                },
            )
            progress_path = directory / "progress.json"
            state = json.loads(progress_path.read_bytes()) if progress_path.exists() else {}
            state.update(status="supervisor_error", updated_at=timestamp(), error=str(exc))
            atomic_json(progress_path, state)
        print(f"V2 batch job: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
