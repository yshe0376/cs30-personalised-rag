"""Deterministic v2 identity and canonical serialisation helpers."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from urllib.parse import quote


def canonical_json_bytes(payload: object) -> bytes:
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def sha256_bytes(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return "sha256:" + digest.hexdigest()


def slug(value: str) -> str:
    normalised = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip().lower())
    return normalised.strip("-") or "unknown"


def make_document_id(
    *,
    textbook_id: str,
    raw_source_sha256: str,
    document_hash: str,
    parser_version: str,
    selected_chapters: Sequence[str],
) -> str:
    identity = "|".join(
        (
            textbook_id,
            raw_source_sha256,
            document_hash,
            parser_version,
            ",".join(selected_chapters),
        )
    )
    suffix = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
    return f"{slug(textbook_id)}__{suffix}"


def chunk_config_hash(config: Mapping[str, object]) -> str:
    return sha256_bytes(canonical_json_bytes(dict(config)))


def make_chunk_id(document_id: str, chapter_id: str, config_hash: str, ordinal: int) -> str:
    if ordinal < 1:
        raise ValueError("chunk ordinal must be positive")
    config_fragment = re.sub(r"[^a-fA-F0-9]", "", config_hash)[-8:] or "config"
    return f"{slug(document_id)}__{slug(chapter_id)}__{config_fragment}__{ordinal:05d}"


def source_locator(
    *,
    source_uri: str | None,
    textbook_id: str,
    document_id: str,
    chapter_id: str,
    page_or_location: str | None,
    char_start: int,
    char_end: int,
) -> str:
    """Build a canonical, path-independent locator string.

    Each value is escaped independently, so delimiters in a URL or location
    cannot change the meaning of the locator.
    """

    def encoded(value: str | None) -> str:
        return quote(value or "", safe="")

    return "|".join(
        (
            f"uri={encoded(source_uri)}",
            f"textbook={encoded(textbook_id)}",
            f"document={encoded(document_id)}",
            f"chapter={encoded(chapter_id)}",
            f"location={encoded(page_or_location)}",
            f"span={char_start}:{char_end}",
        )
    )
