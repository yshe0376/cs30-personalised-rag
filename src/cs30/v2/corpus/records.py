"""Read a published v2 corpus back as validated chunks.

``records.jsonl`` is trusted only while its bytes still hash to the Manifest's
``corpus_hash``.  Every line must be a v2 :class:`~cs30.v2.contracts.Chunk`;
v1 records (``schema_version`` 1.0) are rejected rather than coerced, so a v1
corpus can never be mistaken for a v2 one.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType

from pydantic import ValidationError

from cs30.v2.contracts import Chunk
from cs30.v2.corpus.canonical import canonical_chunks
from cs30.v2.corpus.manifest import CorpusManifest, load_corpus_manifest
from cs30.v2.errors import ContractError
from cs30.v2.ids import sha256_bytes

MANIFEST_FILENAME = "manifest.json"


@dataclass(frozen=True)
class LoadedCorpus:
    """One published corpus: its Manifest and its chunks in record order."""

    manifest: CorpusManifest
    chunks: tuple[Chunk, ...]
    chunks_by_id: Mapping[str, Chunk] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        by_id = {chunk.chunk_id: chunk for chunk in self.chunks}
        object.__setattr__(self, "chunks_by_id", MappingProxyType(by_id))

    @property
    def chunk_ids(self) -> tuple[str, ...]:
        """Record-order IDs, the same order as the index rows."""

        return tuple(chunk.chunk_id for chunk in self.chunks)


def _record_error(relpath: str, line_number: int, exc: ValidationError) -> ContractError:
    first = exc.errors()[0]
    location = ".".join(str(part) for part in first["loc"]) or "record"
    return ContractError(
        f"{relpath} line {line_number} is not a v2 chunk ({location}: {first['msg']})",
        code="CORPUS_RECORD_INVALID",
    )


def load_corpus_records(corpus_dir: Path) -> LoadedCorpus:
    """Load ``records.jsonl`` only if it is exactly the corpus its Manifest names.

    Development corpora load too; a caller that needs a reportable corpus checks
    ``loaded.manifest.reportable`` itself.
    """

    manifest = load_corpus_manifest(corpus_dir / MANIFEST_FILENAME)
    relpath = manifest.records_relpath
    records_path = corpus_dir / relpath
    if not records_path.is_file():
        raise ContractError(f"no {relpath} in {corpus_dir}", code="CORPUS_RECORDS_MISSING")
    data = records_path.read_bytes()
    # records.jsonl is exactly the canonical corpus bytes the hash covers.
    if sha256_bytes(data) != manifest.corpus_hash:
        raise ContractError(
            f"{relpath} no longer hashes to the manifest corpus_hash",
            code="CORPUS_HASH_MISMATCH",
        )

    chunks: list[Chunk] = []
    for line_number, line in enumerate(data.splitlines(), start=1):
        try:
            chunks.append(Chunk.model_validate_json(line))
        except ValidationError as exc:
            raise _record_error(relpath, line_number, exc) from exc

    if len(chunks) != manifest.record_count:
        raise ContractError(
            f"{relpath} holds {len(chunks)} records, the manifest says {manifest.record_count}",
            code="CORPUS_RECORD_COUNT_MISMATCH",
        )
    try:
        ordered = canonical_chunks(chunks)
    except ValueError as exc:
        raise ContractError(str(exc), code="CORPUS_RECORD_INVALID") from exc
    # Index row i is record line i, so a reordered file is not the same corpus.
    if [chunk.chunk_id for chunk in ordered] != [chunk.chunk_id for chunk in chunks]:
        raise ContractError(
            f"{relpath} is not in canonical record order",
            code="CORPUS_RECORD_ORDER_INVALID",
        )

    expected_counts = {
        document.document_id: document.chunk_count for document in manifest.documents
    }
    for chunk in chunks:
        if chunk.document_id not in expected_counts:
            raise ContractError(
                f"chunk {chunk.chunk_id} names a document outside the manifest",
                code="CORPUS_DOCUMENT_UNKNOWN",
            )
        if chunk.chunk_config_hash != manifest.chunk_config_hash:
            raise ContractError(
                f"chunk {chunk.chunk_id} was cut with a different chunk_config_hash",
                code="CHUNK_CONFIG_MISMATCH",
            )
    actual_counts = Counter(chunk.document_id for chunk in chunks)
    if any(actual_counts[doc_id] != count for doc_id, count in expected_counts.items()):
        raise ContractError(
            "per-document chunk counts do not match the manifest",
            code="CORPUS_RECORD_COUNT_MISMATCH",
        )
    return LoadedCorpus(manifest=manifest, chunks=tuple(chunks))
