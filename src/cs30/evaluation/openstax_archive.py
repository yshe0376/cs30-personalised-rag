"""Load and freeze the chapter archive handed off by the OpenStax parser.

The archive supplied by M2 contains one contract-valid ``openstax_document.json``
per chapter.  M1 consumes one corpus identity, while the chunker and the
gold-span contract use one document-wide character coordinate system.  This
module therefore validates the chapter documents and creates a deterministic
unified document without changing any source text.

It deliberately does not create questions, gold evidence, or chunk mappings.
Those remain M3/M4 deliverables.  The result is only the corpus hand-off that
the real evaluation runner can consume once those artifacts are available.
"""

from __future__ import annotations

import hashlib
import json
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cs30.contracts import OpenStaxChapter, OpenStaxDocument, TextBlock

_CHAPTER_ENTRY = re.compile(r"^parsed_openstax_ch[^/]+/openstax_document\.json$")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return "sha256:" + digest.hexdigest()


def _chapter_sort_key(chapter_id: str) -> tuple[int, int | str]:
    try:
        return (0, int(chapter_id))
    except ValueError:
        return (1, chapter_id)


def _compact_chapter_label(chapter_ids: list[str]) -> str:
    """Return a short, readable label for the selected chapter set."""

    numeric_ids: list[int] = []
    for chapter_id in chapter_ids:
        if not chapter_id.isdigit():
            numeric_ids = []
            break
        numeric_ids.append(int(chapter_id))
    if numeric_ids and numeric_ids == list(range(numeric_ids[0], numeric_ids[-1] + 1)):
        if len(numeric_ids) == 1:
            return f"{numeric_ids[0]:02d}"
        return f"{numeric_ids[0]:02d}-{numeric_ids[-1]:02d}"
    encoded = json.dumps(chapter_ids, ensure_ascii=False, separators=(",", ":"))
    return "set-" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:10]


def _corpus_version(document: OpenStaxDocument, separator: str) -> str:
    """Build a compact identity that also freezes the document separator."""

    chapter_ids = [chapter.chapter_id for chapter in document.chapters]
    fingerprint_payload = {
        "document_id": document.document_id,
        "document_hash": document.document_hash,
        "parser_version": document.parser_version,
        "chapter_ids": chapter_ids,
        "separator": separator,
    }
    encoded = json.dumps(
        fingerprint_payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    fingerprint = hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]
    return (
        f"{document.document_id}-ch{_compact_chapter_label(chapter_ids)}"
        f"-v{fingerprint}"
    )


def _read_json_entry(archive: zipfile.ZipFile, entry_name: str) -> object:
    try:
        with archive.open(entry_name, "r") as stream:
            return json.loads(stream.read().decode("utf-8"))
    except (KeyError, OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"failed to read JSON entry {entry_name!r}: {exc}") from exc


@dataclass(frozen=True)
class _ChapterFragment:
    entry_name: str
    chapter: OpenStaxChapter
    text: str
    blocks: tuple[TextBlock, ...]


@dataclass(frozen=True)
class OpenStaxArchiveCorpus:
    """Unified corpus plus the immutable identities needed by M1 manifests."""

    document: OpenStaxDocument
    corpus_version: str
    archive_sha256: str
    separator: str
    chapter_entries: dict[str, str]

    def manifest(self) -> dict[str, Any]:
        """Return a portable manifest; no absolute local path is included."""

        document = self.document
        return {
            "manifest_version": "1.0",
            "corpus_version": self.corpus_version,
            "document_id": document.document_id,
            "document_hash": document.document_hash,
            "title": document.title,
            "version": document.version,
            "source": document.source,
            "parser_version": document.parser_version,
            "chapter_ids": [chapter.chapter_id for chapter in document.chapters],
            "chapter_count": len(document.chapters),
            "character_count": len(document.text),
            "block_count": len(document.blocks),
            "archive_sha256": self.archive_sha256,
            "separator": self.separator,
            "chapter_entries": dict(
                sorted(
                    self.chapter_entries.items(),
                    key=lambda item: _chapter_sort_key(item[0]),
                )
            ),
            "note": (
                "Parsed OpenStax chapter archive unified for the evaluation handoff. "
                "Gold samples and gold-to-chunk mappings are separate artifacts."
            ),
        }


def _validate_shared_identity(documents: list[tuple[str, OpenStaxDocument]]) -> None:
    if not documents:
        raise ValueError(
            "archive contains no parsed_openstax_ch*/openstax_document.json entries"
        )
    first_entry, first = documents[0]
    identity = (
        first.document_id,
        first.title,
        first.version,
        first.source,
        first.document_hash,
        first.parser_version,
    )
    for entry_name, document in documents[1:]:
        current = (
            document.document_id,
            document.title,
            document.version,
            document.source,
            document.document_hash,
            document.parser_version,
        )
        if current != identity:
            raise ValueError(
                "chapter documents do not share one source identity: "
                f"{first_entry!r} and {entry_name!r}"
            )


def _fragments(
    documents: list[tuple[str, OpenStaxDocument]],
    selected_chapters: set[str] | None,
) -> list[_ChapterFragment]:
    fragments: list[_ChapterFragment] = []
    seen: set[str] = set()
    for entry_name, document in documents:
        for chapter in document.chapters:
            chapter_id = chapter.chapter_id
            if selected_chapters is not None and chapter_id not in selected_chapters:
                continue
            if chapter_id in seen:
                raise ValueError(f"duplicate chapter_id {chapter_id!r} in archive")
            seen.add(chapter_id)
            chapter_text = document.text[chapter.char_start : chapter.char_end]
            chapter_blocks: list[TextBlock] = []
            for block in document.blocks:
                if block.chapter_id != chapter_id:
                    continue
                if block.char_start < chapter.char_start or block.char_end > chapter.char_end:
                    raise ValueError(
                        f"block {block.block_id or '<anonymous>'!r} exceeds chapter {chapter_id!r}"
                    )
                payload = block.model_dump(mode="python")
                payload["char_start"] = block.char_start - chapter.char_start
                payload["char_end"] = block.char_end - chapter.char_start
                chapter_blocks.append(TextBlock.model_validate(payload))
            if not chapter_blocks:
                raise ValueError(f"chapter {chapter_id!r} contains no blocks")
            fragments.append(
                _ChapterFragment(
                    entry_name=entry_name,
                    chapter=chapter,
                    text=chapter_text,
                    blocks=tuple(chapter_blocks),
                )
            )

    fragments.sort(key=lambda fragment: _chapter_sort_key(fragment.chapter.chapter_id))
    if selected_chapters is not None:
        missing = selected_chapters - seen
        if missing:
            missing_text = ", ".join(sorted(missing, key=_chapter_sort_key))
            raise ValueError(f"requested chapter(s) not found in archive: {missing_text}")
    if not fragments:
        raise ValueError("no chapters selected from archive")
    return fragments


def _merge_fragments(
    documents: list[tuple[str, OpenStaxDocument]],
    fragments: list[_ChapterFragment],
    *,
    separator: str,
) -> tuple[OpenStaxDocument, dict[str, str]]:
    first = documents[0][1]
    text_parts: list[str] = []
    chapters: list[OpenStaxChapter] = []
    blocks: list[TextBlock] = []
    chapter_entries: dict[str, str] = {}
    offset = 0
    for index, fragment in enumerate(fragments):
        if index:
            text_parts.append(separator)
            offset += len(separator)
        text_parts.append(fragment.text)
        chapter = fragment.chapter.model_dump(mode="python")
        chapter["char_start"] = offset
        chapter["char_end"] = offset + len(fragment.text)
        chapters.append(OpenStaxChapter.model_validate(chapter))
        for block in fragment.blocks:
            payload = block.model_dump(mode="python")
            payload["char_start"] = offset + block.char_start
            payload["char_end"] = offset + block.char_end
            blocks.append(TextBlock.model_validate(payload))
        chapter_entries[fragment.chapter.chapter_id] = fragment.entry_name
        offset += len(fragment.text)

    document_payload = first.model_dump(mode="python")
    document_payload["text"] = "".join(text_parts)
    document_payload["chapters"] = [chapter.model_dump(mode="python") for chapter in chapters]
    document_payload["blocks"] = [block.model_dump(mode="python") for block in blocks]
    return OpenStaxDocument.model_validate(document_payload), chapter_entries


def load_openstax_archive(
    archive_path: str | Path,
    *,
    chapters: list[str] | tuple[str, ...] | None = None,
    separator: str = "\n\n",
) -> OpenStaxArchiveCorpus:
    """Validate and merge a parsed OpenStax chapter archive.

    ``chapters`` is optional.  When omitted, every chapter in the archive is
    included.  The archive itself is never modified or extracted by this
    function.
    """

    path = Path(archive_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"OpenStax archive not found: {path}")
    if not separator:
        raise ValueError("separator must not be empty")

    requested: set[str] | None = None
    if chapters is not None:
        requested = {str(chapter).strip() for chapter in chapters if str(chapter).strip()}
        if not requested:
            raise ValueError("chapters must contain at least one chapter id")

    try:
        archive = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile) as exc:
        raise ValueError(f"invalid OpenStax archive {path}: {exc}") from exc
    with archive:
        entry_names = sorted(
            name
            for name in archive.namelist()
            if not name.startswith("__MACOSX/") and _CHAPTER_ENTRY.fullmatch(name)
        )
        documents: list[tuple[str, OpenStaxDocument]] = []
        for entry_name in entry_names:
            payload = _read_json_entry(archive, entry_name)
            try:
                document = OpenStaxDocument.model_validate(payload)
            except ValueError as exc:
                raise ValueError(f"invalid OpenStaxDocument in {entry_name!r}: {exc}") from exc
            documents.append((entry_name, document))

    _validate_shared_identity(documents)
    fragments = _fragments(documents, requested)
    merged, chapter_entries = _merge_fragments(documents, fragments, separator=separator)
    corpus_version = _corpus_version(merged, separator)
    return OpenStaxArchiveCorpus(
        document=merged,
        corpus_version=corpus_version,
        archive_sha256=_sha256_file(path),
        separator=separator,
        chapter_entries=chapter_entries,
    )


def load_openstax_document(path: str | Path) -> OpenStaxDocument:
    """Load one prepared contract document for Gold span validation."""

    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"OpenStax document not found: {source}")
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
        return OpenStaxDocument.model_validate(payload)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"invalid OpenStax document {source}: {exc}") from exc


def load_prepared_corpus(
    document_path: str | Path,
    manifest_path: str | Path | None = None,
) -> OpenStaxArchiveCorpus:
    """Load a prepared corpus only when its manifest still verifies its identity."""

    document_source = Path(document_path).expanduser().resolve()
    document = load_openstax_document(document_source)
    manifest_source = (
        Path(manifest_path).expanduser().resolve()
        if manifest_path is not None
        else document_source.parent / "corpus_manifest.json"
    )
    if not manifest_source.is_file():
        raise FileNotFoundError(
            "prepared corpus manifest not found: "
            f"{manifest_source}; formal evaluation requires corpus_manifest.json"
        )
    try:
        payload = json.loads(manifest_source.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid prepared corpus manifest {manifest_source}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"invalid prepared corpus manifest {manifest_source}: expected object")

    required = (
        "corpus_version",
        "document_id",
        "document_hash",
        "parser_version",
        "chapter_ids",
        "separator",
        "archive_sha256",
        "chapter_entries",
    )
    missing = [field for field in required if field not in payload]
    if missing:
        raise ValueError(
            f"invalid prepared corpus manifest {manifest_source}: missing "
            + ", ".join(missing)
        )
    if payload["document_id"] != document.document_id:
        raise ValueError("prepared corpus manifest document_id does not match the document")
    if payload["document_hash"] != document.document_hash:
        raise ValueError("prepared corpus manifest document_hash does not match the document")
    if payload["parser_version"] != document.parser_version:
        raise ValueError("prepared corpus manifest parser_version does not match the document")

    chapter_ids = [chapter.chapter_id for chapter in document.chapters]
    if payload["chapter_ids"] != chapter_ids:
        raise ValueError("prepared corpus manifest chapter_ids do not match the document")
    separator = payload["separator"]
    if not isinstance(separator, str) or not separator:
        raise ValueError("prepared corpus manifest separator must be a non-empty string")
    expected_version = _corpus_version(document, separator)
    if payload["corpus_version"] != expected_version:
        raise ValueError(
            "prepared corpus manifest corpus_version does not match the document and separator"
        )
    if not isinstance(payload["archive_sha256"], str) or not payload["archive_sha256"]:
        raise ValueError("prepared corpus manifest archive_sha256 must be a non-empty string")
    if not isinstance(payload["chapter_entries"], dict):
        raise ValueError("prepared corpus manifest chapter_entries must be an object")
    chapter_entries = {str(key): str(value) for key, value in payload["chapter_entries"].items()}
    if set(chapter_entries) != set(chapter_ids):
        raise ValueError("prepared corpus manifest chapter_entries do not match the document")

    return OpenStaxArchiveCorpus(
        document=document,
        corpus_version=expected_version,
        archive_sha256=payload["archive_sha256"],
        separator=separator,
        chapter_entries=chapter_entries,
    )


def write_prepared_corpus(
    corpus: OpenStaxArchiveCorpus,
    output_dir: str | Path,
) -> dict[str, str]:
    """Write a unified contract document and manifest without overwriting files."""

    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    document_path = destination / "openstax_document.json"
    manifest_path = destination / "corpus_manifest.json"
    existing = [path for path in (document_path, manifest_path) if path.exists()]
    if existing:
        shown = ", ".join(str(path) for path in existing)
        raise FileExistsError(f"refusing to overwrite prepared corpus files: {shown}")
    document_path.write_text(
        json.dumps(corpus.document.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    manifest_path.write_text(
        json.dumps(corpus.manifest(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return {"document": str(document_path), "manifest": str(manifest_path)}
