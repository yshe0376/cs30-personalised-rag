"""Run local setup diagnostics and write a redacted asset identity report."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cs30.learning.assets import check_learning_setup  # noqa: E402
from cs30.learning.config import LearningConfig, LearningConfigurationError  # noqa: E402


def _file_info(path: Path) -> dict[str, object]:
    value: dict[str, object] = {"path": str(path), "exists": path.exists()}
    if path.is_file():
        raw = path.read_bytes()
        value["size_bytes"] = len(raw)
        value["sha256"] = hashlib.sha256(raw).hexdigest()
        payload = None
        if path.suffix.casefold() == ".json":
            try:
                payload = json.loads(raw)
            except (UnicodeDecodeError, json.JSONDecodeError):
                payload = None
        if isinstance(payload, dict):
            fields = (
                "corpus_version",
                "corpus_hash",
                "manifest_hash",
                "chunk_config_hash",
                "topic_registry_version",
                "role_taxonomy_version",
                "labels_sha256",
                "lambda_weight",
                "profile_confidence",
                "candidate_k",
                "evidence_k",
                "embedding_model",
                "embedding_revision",
                "index_version",
                "chunk_count",
            )
            value["identity"] = {key: payload[key] for key in fields if key in payload}
            if isinstance(payload.get("metadata"), dict):
                value["metadata"] = {
                    key: payload["metadata"].get(key)
                    for key in ("index_sha256", "embedding_model", "embedding_revision")
                    if key in payload["metadata"]
                }
    elif path.is_dir() and (path / "manifest.json").is_file():
        value["manifest"] = _file_info(path / "manifest.json")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=None)
    args = parser.parse_args()
    try:
        config = LearningConfig.load(Path(args.config) if args.config else None)
    except LearningConfigurationError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    report = check_learning_setup(config)
    files = {
        "corpus": config.corpus_dir,
        "source_topic_map": config.source_topic_map_path,
        "bound_topic_map": config.topic_map_path,
        "topic_registry": config.topic_registry_path,
        "role_manifest": config.role_manifest_path,
        "lambda_selection": config.lambda_selection_path,
        "index_artifact": config.index_artifact_path,
        "index_file": config.index_file_path,
        "question_bank": config.question_bank_path,
        "topic_preflight": config.preflight_report_path,
    }
    payload = {
        "schema_version": "1",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "status": "ready" if report.ready else "blocked",
        "checks": [
            {
                "name": item.name,
                "passed": item.passed,
                "blocking": item.blocking,
                "detail": item.detail,
            }
            for item in report.checks
        ],
        "assets": {name: _file_info(path) for name, path in files.items()},
        "api_roles": [
            {
                "role": name,
                "provider": role.provider_name,
                "model": role.model,
                "model_version": role.model_version,
                "api_key_env": role.api_key_env,
                "api_key_present": bool(os.environ.get(role.api_key_env, "").strip()),
                "structured_output": role.structured_output,
                "transport_retries": 0,
            }
            for name, role in (
                ("answer", config.answer_api),
                ("quiz", config.quiz_api),
            )
        ],
        "retrieval": {
            "embedding_model": config.dense_embedding_model,
            "embedding_revision": config.dense_embedding_revision,
            "dense_weight": config.dense_weight,
            "bm25_weight": config.bm25_weight,
            "rrf_k": config.rrf_k,
            "candidate_k": config.candidate_k,
            "evidence_k": config.evidence_k,
        },
        "model_selection_status": config.model_selection_status,
        "total_request_cap": config.total_request_cap,
        "live_calls_enabled": config.live_calls_enabled,
        "report_path": str(config.state_dir / "asset-preflight.json"),
    }
    output = config.state_dir / "asset-preflight.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": payload["status"], "report": str(output)}, ensure_ascii=False))
    for item in report.checks:
        prefix = "OK" if item.passed else "WARN" if not item.blocking else "BLOCKED"
        print(f"{prefix} {item.name}: {item.detail}")
    return 0 if report.ready else 2


if __name__ == "__main__":
    raise SystemExit(main())
