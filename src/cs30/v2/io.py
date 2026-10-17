"""Neutral UTF-8 JSONL and content fingerprints for V2 data exchange."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pydantic import BaseModel


def read_jsonl(path: Path, data: bytes | None = None) -> list[dict]:
    result = []
    text = (path.read_bytes() if data is None else data).decode("utf-8")
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError("each JSONL row must be an object")
        except ValueError as exc:
            raise ValueError(f"invalid JSONL at {path}:{number}: {exc}") from exc
        result.append(value)
    return result


def unique_models(rows: list[dict], model: type[BaseModel], key: str) -> dict:
    result = {}
    for payload in rows:
        value = model.model_validate(payload)
        identifier = getattr(value, key)
        if identifier in result:
            raise ValueError(f"duplicate {key}: {identifier}")
        result[identifier] = value
    return result


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_hash(value: object) -> str:
    return sha256_bytes(json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8"))
