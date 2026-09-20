"""Draft/finalize/write lifecycle for a v2 three-textbook Manifest."""

from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from cs30.v2.contracts import TextbookDocument
from cs30.v2.contracts.models import Identifier
from cs30.v2.corpus.canonical import canonical_corpus_bytes
from cs30.v2.corpus.canonical import manifest_hash as calculate_manifest_hash
from cs30.v2.ids import sha256_bytes


class ManifestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CorpusDocument(ManifestModel):
    provider: Identifier
    textbook_id: Identifier
    document_id: Identifier
    document_hash: Identifier
    raw_source_sha256: Identifier
    parser_version: Identifier
    source_name: Identifier
    source_uri: str | None = None
    source_version: Identifier
    license: Identifier
    selected_chapters: tuple[Identifier, ...] = ()
    chunk_count: int = Field(ge=0)


class CorpusManifestDraft(ManifestModel):
    schema_version: Literal["2.0"] = "2.0"
    corpus_version: Identifier
    corpus_hash: Identifier
    chunk_config_hash: Identifier
    required_textbook_ids: tuple[Identifier, ...] = Field(min_length=3)
    included_textbook_ids: tuple[Identifier, ...] = ()
    failed_textbook_ids: tuple[Identifier, ...] = ()
    documents: tuple[CorpusDocument, ...] = ()
    record_count: int = Field(ge=0)
    records_relpath: Identifier = "records.jsonl"
    mode: Literal["development", "official"]
    reportable: bool = False
    validation_errors: tuple[Identifier, ...] = ()

    @model_validator(mode="after")
    def validate_sets(self) -> CorpusManifestDraft:
        if len(self.required_textbook_ids) != 3:
            raise ValueError("required_textbook_ids must contain exactly three IDs")
        if len(set(self.required_textbook_ids)) != len(self.required_textbook_ids):
            raise ValueError("required_textbook_ids must be unique")
        if len(set(self.included_textbook_ids)) != len(self.included_textbook_ids):
            raise ValueError("included_textbook_ids must be unique")
        if len(set(self.failed_textbook_ids)) != len(self.failed_textbook_ids):
            raise ValueError("failed_textbook_ids must be unique")
        if not set(self.included_textbook_ids).issubset(self.required_textbook_ids):
            raise ValueError("included_textbook_ids must be a subset of required_textbook_ids")
        if not set(self.failed_textbook_ids).issubset(self.required_textbook_ids):
            raise ValueError("failed_textbook_ids must be a subset of required_textbook_ids")
        if set(self.included_textbook_ids) & set(self.failed_textbook_ids):
            raise ValueError("a textbook cannot be both included and failed")
        if self.reportable and self.__class__.__name__ == "CorpusManifestDraft":
            raise ValueError("reportable is derived by finalize_manifest")
        relative_records = PurePosixPath(self.records_relpath)
        if relative_records.is_absolute() or ".." in relative_records.parts:
            raise ValueError("records_relpath must remain inside the v2 output directory")
        document_ids = [document.document_id for document in self.documents]
        if len(document_ids) != len(set(document_ids)):
            raise ValueError("document_id values must be unique")
        textbook_document_pairs = [
            (document.textbook_id, document.document_id) for document in self.documents
        ]
        if len(textbook_document_pairs) != len(set(textbook_document_pairs)):
            raise ValueError("textbook/document identity pairs must be unique")
        return self


class CorpusManifest(CorpusManifestDraft):
    manifest_hash: Identifier


def _ordered_ids(values) -> tuple[str, ...]:
    result = tuple(values)
    if len(result) != len(set(result)):
        raise ValueError("textbook IDs must be unique")
    return result


def build_manifest_draft(
    documents,
    chunks,
    *,
    corpus_version: str,
    chunk_config_hash: str,
    required_textbook_ids,
    mode: Literal["development", "official"],
    failed_textbook_ids=(),
) -> CorpusManifestDraft:
    """Derive included textbooks from actual successful documents and chunks."""

    required = _ordered_ids(required_textbook_ids)
    if len(required) != 3:
        raise ValueError("required_textbook_ids must contain exactly three IDs")
    documents = tuple(documents)
    chunks = tuple(chunks)
    documents_by_id: dict[str, TextbookDocument] = {}
    for document in documents:
        if document.document_id in documents_by_id:
            raise ValueError(f"duplicate document_id: {document.document_id}")
        if document.textbook_id not in required:
            raise ValueError(f"document uses non-required textbook_id: {document.textbook_id}")
        documents_by_id[document.document_id] = document

    seen_chunk_ids: set[str] = set()
    counts: dict[str, int] = {textbook_id: 0 for textbook_id in required}
    for chunk in chunks:
        if chunk.chunk_id in seen_chunk_ids:
            raise ValueError(f"duplicate chunk_id: {chunk.chunk_id}")
        seen_chunk_ids.add(chunk.chunk_id)
        document = documents_by_id.get(chunk.document_id)
        if document is None:
            raise ValueError(f"chunk references unknown document_id: {chunk.document_id}")
        if chunk.textbook_id != document.textbook_id:
            raise ValueError(f"chunk textbook_id does not match document: {chunk.chunk_id}")
        if chunk.chunk_config_hash != chunk_config_hash:
            raise ValueError(f"chunk has a different chunk_config_hash: {chunk.chunk_id}")
        counts[chunk.textbook_id] += 1

    included = tuple(textbook_id for textbook_id in required if counts[textbook_id] > 0)
    failed = _ordered_ids(failed_textbook_ids)
    records = tuple(
        CorpusDocument(
            provider=document.provider,
            textbook_id=document.textbook_id,
            document_id=document.document_id,
            document_hash=document.document_hash,
            raw_source_sha256=document.raw_source_sha256,
            parser_version=document.parser_version,
            source_name=document.source_name,
            source_uri=document.source_uri,
            source_version=document.source_version,
            license=document.license,
            selected_chapters=document.selected_chapters,
            chunk_count=counts[document.textbook_id],
        )
        for document in sorted(documents, key=lambda item: (item.textbook_id, item.document_id))
    )
    return CorpusManifestDraft(
        corpus_version=corpus_version,
        corpus_hash=sha256_bytes(canonical_corpus_bytes(chunks)),
        chunk_config_hash=chunk_config_hash,
        required_textbook_ids=required,
        included_textbook_ids=included,
        failed_textbook_ids=failed,
        documents=records,
        record_count=len(chunks),
        mode=mode,
    )


def finalize_manifest(draft: CorpusManifestDraft) -> CorpusManifest:
    errors = list(draft.validation_errors)
    if draft.mode == "development":
        errors.append("development mode is diagnostic-only")
    if draft.mode == "official" and draft.included_textbook_ids != draft.required_textbook_ids:
        errors.append("included textbook IDs do not equal required textbook IDs")
    if draft.failed_textbook_ids:
        errors.append("one or more textbooks failed during the build")
    if draft.mode == "official" and draft.record_count == 0:
        errors.append("official corpus must contain at least one record")
    if any(document.chunk_count == 0 for document in draft.documents):
        errors.append("every successful document must contribute at least one chunk")

    reportable = draft.mode == "official" and not errors
    candidate = draft.model_copy(
        update={
            "reportable": reportable,
            "validation_errors": tuple(dict.fromkeys(errors)),
        }
    )
    # The hash is calculated only after the derived reportability state is fixed;
    # write_corpus_manifest never silently fills it in later.
    return CorpusManifest(
        **candidate.model_dump(),
        manifest_hash=calculate_manifest_hash(candidate),
    )


def write_corpus_manifest(manifest: CorpusManifest, path: Path) -> None:
    expected = calculate_manifest_hash(manifest)
    if expected != manifest.manifest_hash:
        raise ValueError("manifest_hash does not match the finalized manifest")
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        manifest.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
    )
    path.write_bytes((payload + "\n").encode("utf-8"))


def load_corpus_manifest(path: Path) -> CorpusManifest:
    manifest = CorpusManifest.model_validate_json(path.read_text(encoding="utf-8"))
    expected = calculate_manifest_hash(manifest)
    if expected != manifest.manifest_hash:
        raise ValueError("manifest_hash does not match the manifest payload")
    return manifest
