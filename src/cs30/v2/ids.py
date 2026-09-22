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


def canonical_document_hash(payload: Mapping[str, object]) -> str:
    """Hash a parser's normalized payload, excluding filesystem/runtime data."""

    return sha256_bytes(canonical_json_bytes(dict(payload)))


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


def page_location(page_start: int, page_end: int) -> str:
    """Return the canonical ``page_or_location`` for a physical PDF page range.

    Pages are 1-based physical PDF pages, not printed page labels, so the
    value stays stable for a pinned source file: ``p25`` or ``p25-26``.
    """

    if page_start < 1 or page_end < page_start:
        raise ValueError("page range must start at 1 and must not run backwards")
    return f"p{page_start}" if page_end == page_start else f"p{page_start}-{page_end}"


def source_locator(
    *,
    source_name: str,
    textbook_id: str,
    chapter_id: str,
    page_or_location: str | None,
    char_start: int,
    char_end: int,
) -> str:
    """Build a canonical, path-independent locator string.

    The locator is stable across parser runs and deliberately excludes URLs
    and generated document IDs.  ``source_name`` is a stable logical source
    name, not a machine-local file basename.
    """

    return "|".join(
        (
            f"source={_encode_locator_value(source_name)}",
            f"textbook={_encode_locator_value(textbook_id)}",
            f"chapter={_encode_locator_value(chapter_id)}",
            f"location={_encode_locator_value(page_or_location)}",
            f"span={char_start}:{char_end}",
        )
    )


def _encode_locator_value(value: str | None) -> str:
    return quote(value or "", safe="")


def source_locator_prefix(
    *,
    source_name: str,
    textbook_id: str,
    chapter_id: str,
    page_or_location: str | None,
) -> str:
    """Return the stable locator prefix shared by chunks and evidence."""

    return "|".join(
        (
            f"source={_encode_locator_value(source_name)}",
            f"textbook={_encode_locator_value(textbook_id)}",
            f"chapter={_encode_locator_value(chapter_id)}",
            f"location={_encode_locator_value(page_or_location)}",
        )
    )


def validate_source_locator_shape(
    locator: str,
    *,
    source_name: str,
    textbook_id: str,
    chapter_id: str,
    page_or_location: str | None,
) -> None:
    """Reject legacy URI/document locators while retaining the span suffix."""

    prefix = source_locator_prefix(
        source_name=source_name,
        textbook_id=textbook_id,
        chapter_id=chapter_id,
        page_or_location=page_or_location,
    )
    marker = prefix + "|span="
    if not locator.startswith(marker) or not re.fullmatch(
        r"\d+:\d+", locator[len(marker) :]
    ):
        raise ValueError(
            "source_locator must use the v2 source/textbook/chapter/location/span format"
        )
