"""Build and load the v2 dense index, bound to one exact corpus.

The builder embeds chunks in the order the build pipeline hands them over --
the canonical order that ``records.jsonl`` and ``corpus_hash`` also use -- so
FAISS row *i* is always record line *i*.  The artifact repeats the corpus,
manifest, and chunk-config hashes, and the loader refuses to pair an index with
a corpus whose bytes no longer match.

The encoder is injected.  ``SentenceTransformerEncoder`` is the production one
and needs the ``[ml]`` extra; tests use a deterministic stub instead of
downloading a model.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar, Protocol, runtime_checkable

from cs30.v2.contracts import Chunk, IndexArtifact
from cs30.v2.corpus.manifest import CorpusManifest, load_corpus_manifest
from cs30.v2.errors import ContractError, InputError
from cs30.v2.ids import canonical_json_bytes, sha256_bytes, sha256_file, slug

if TYPE_CHECKING:  # pragma: no cover - typing only
    import numpy as np

INDEX_DIRNAME = "index"
INDEX_FILENAME = "index.faiss"
CHUNK_IDS_FILENAME = "chunk_ids.json"
ARTIFACT_FILENAME = "artifact.json"
RECORDS_FILENAME = "records.jsonl"
MANIFEST_FILENAME = "manifest.json"
INDEX_TYPE = "faiss.IndexFlatIP"
INDEX_FORMAT_VERSION = "faiss-serialized-v1"
INDEX_VERSION = "v2-faiss-flat-ip-1"
SIMILARITY_METRIC = "inner_product"


@runtime_checkable
class Encoder(Protocol):
    """Minimal embedding boundary the index builder needs."""

    @property
    def model_name(self) -> str: ...

    @property
    def revision(self) -> str: ...

    @property
    def dimension(self) -> int: ...

    @property
    def max_input_tokens(self) -> int | None: ...

    def encode(self, texts: Sequence[str], *, batch_size: int) -> np.ndarray: ...

    def count_tokens(self, text: str) -> int: ...


def _package_version(name: str) -> str:
    try:
        return importlib_metadata.version(name)
    except importlib_metadata.PackageNotFoundError:
        return "not-installed"


class SentenceTransformerEncoder:
    """Encode with a sentence-transformers model and record its exact revision."""

    def __init__(
        self,
        model_name: str,
        *,
        revision: str | None = None,
        device: str | None = None,
        max_seq_length: int | None = None,
    ) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise InputError(
                'the v2 index builder needs pip install -e ".[ml]"',
                code="INDEX_DEPENDENCY_MISSING",
            ) from exc
        self._model = SentenceTransformer(model_name, revision=revision, device=device)
        self._model_name = model_name
        # Record the exact weights: the pinned revision, else the commit hash
        # transformers resolved while loading.
        resolved = revision
        if resolved is None:
            auto_model = getattr(self._model[0], "auto_model", None)
            resolved = getattr(getattr(auto_model, "config", None), "_commit_hash", None)
        self._revision = str(resolved or "unpinned")
        if max_seq_length is not None:
            self._model.max_seq_length = max_seq_length
        limit = getattr(self._model, "max_seq_length", None)
        tokenizer = self._model.tokenizer
        special = getattr(tokenizer, "num_special_tokens_to_add", None)
        reserved = int(special(pair=False)) if callable(special) else 0
        self._max_input_tokens = max(1, int(limit) - reserved) if limit else None

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def revision(self) -> str:
        return self._revision

    @property
    def dimension(self) -> int:
        return int(self._model.get_sentence_embedding_dimension())

    @property
    def max_input_tokens(self) -> int | None:
        return self._max_input_tokens

    def encode(self, texts: Sequence[str], *, batch_size: int) -> np.ndarray:
        return self._model.encode(
            list(texts),
            batch_size=batch_size,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )

    def count_tokens(self, text: str) -> int:
        return len(self._model.tokenizer.encode(text, add_special_tokens=False))


@dataclass
class FaissIndexBuilder:
    """v2 ``IndexBuilder``: one flat inner-product index over the whole corpus."""

    encoder_factory: Callable[[], Encoder]
    batch_size: int = 32
    is_fixture: ClassVar[bool] = False
    _encoder: Encoder | None = field(default=None, init=False, repr=False)

    @property
    def encoder(self) -> Encoder:
        if self._encoder is None:
            self._encoder = self.encoder_factory()
        return self._encoder

    def build(
        self,
        chunks: Sequence[Chunk],
        manifest: CorpusManifest,
        *,
        output_dir: Path,
    ) -> IndexArtifact:
        import faiss
        import numpy as np

        chunks = tuple(chunks)
        if not chunks:
            raise ContractError("cannot index an empty corpus", code="EMPTY_CORPUS")
        encoder = self.encoder
        vectors = np.asarray(
            encoder.encode([chunk.embedding_input for chunk in chunks], batch_size=self.batch_size),
            dtype="float32",
        )
        if vectors.shape != (len(chunks), encoder.dimension):
            raise ContractError(
                f"encoder returned {vectors.shape} for {len(chunks)} chunks and "
                f"dimension {encoder.dimension}",
                code="EMBEDDING_SHAPE_MISMATCH",
            )
        if not np.isfinite(vectors).all():
            raise ContractError("embeddings contain NaN or infinity", code="EMBEDDING_INVALID")
        # The artifact promises normalised vectors, so inner product is cosine.
        faiss.normalize_L2(vectors)

        index = faiss.IndexFlatIP(encoder.dimension)
        index.add(vectors)
        if index.ntotal != len(chunks):
            raise ContractError(
                f"index holds {index.ntotal} vectors for {len(chunks)} chunks",
                code="INDEX_SIZE_MISMATCH",
            )

        chunk_ids = tuple(chunk.chunk_id for chunk in chunks)
        index_dir = output_dir / INDEX_DIRNAME
        index_dir.mkdir(parents=True, exist_ok=True)
        # Serialise in memory: faiss.write_index cannot handle every path
        # encoding Windows allows.
        index_bytes = bytes(faiss.serialize_index(index))
        (index_dir / INDEX_FILENAME).write_bytes(index_bytes)
        chunk_ids_bytes = canonical_json_bytes(list(chunk_ids))
        (index_dir / CHUNK_IDS_FILENAME).write_bytes(chunk_ids_bytes)

        limit = encoder.max_input_tokens
        truncated = (
            sum(1 for chunk in chunks if encoder.count_tokens(chunk.embedding_input) > limit)
            if limit
            else 0
        )
        metadata = {
            "batch_size": str(self.batch_size),
            "faiss_version": _package_version("faiss-cpu"),
            "sentence_transformers_version": _package_version("sentence-transformers"),
            "max_input_tokens": str(limit) if limit else "unlimited",
            "truncated_chunk_count": str(truncated),
            "index_sha256": sha256_bytes(index_bytes),
            "chunk_ids_sha256": sha256_bytes(chunk_ids_bytes),
        }
        return IndexArtifact(
            artifact_id=(
                f"v2-faiss-{slug(encoder.model_name)}-{manifest.corpus_hash[-12:]}"
            ),
            index_type=INDEX_TYPE,
            index_format_version=INDEX_FORMAT_VERSION,
            location=INDEX_DIRNAME,
            asset_relpaths=(
                f"{INDEX_DIRNAME}/{INDEX_FILENAME}",
                f"{INDEX_DIRNAME}/{CHUNK_IDS_FILENAME}",
            ),
            corpus_version=manifest.corpus_version,
            corpus_hash=manifest.corpus_hash,
            manifest_hash=manifest.manifest_hash,
            chunk_config_hash=manifest.chunk_config_hash,
            required_textbook_ids=manifest.required_textbook_ids,
            included_textbook_ids=manifest.included_textbook_ids,
            chunk_count=len(chunk_ids),
            chunk_ids=chunk_ids,
            embedding_model=encoder.model_name,
            embedding_revision=encoder.revision,
            embedding_dimension=encoder.dimension,
            similarity_metric=SIMILARITY_METRIC,
            normalise_embeddings=True,
            index_version=INDEX_VERSION,
            metadata=metadata,
        )


def build_faiss_index_builder(
    model_name: str,
    *,
    revision: str | None = None,
    batch_size: int = 32,
    device: str | None = None,
    max_seq_length: int | None = None,
) -> FaissIndexBuilder:
    """Builder whose model is loaded on first use, not when it is configured."""

    return FaissIndexBuilder(
        encoder_factory=lambda: SentenceTransformerEncoder(
            model_name,
            revision=revision,
            device=device,
            max_seq_length=max_seq_length,
        ),
        batch_size=batch_size,
    )


@dataclass(frozen=True)
class LoadedIndex:
    index: object
    chunk_ids: tuple[str, ...]
    artifact: IndexArtifact
    manifest: CorpusManifest

    def search(self, vectors: np.ndarray, top_k: int) -> list[list[tuple[str, float]]]:
        """Return ``(chunk_id, score)`` per query row, best first."""

        import numpy as np

        queries = np.asarray(vectors, dtype="float32")
        if queries.ndim == 1:
            queries = queries.reshape(1, -1)
        scores, positions = self.index.search(queries, top_k)
        return [
            [
                (self.chunk_ids[position], float(score))
                for score, position in zip(score_row, position_row, strict=True)
                if position >= 0
            ]
            for score_row, position_row in zip(scores, positions, strict=True)
        ]


def _mismatch(field_name: str) -> ContractError:
    return ContractError(
        f"index artifact {field_name} does not match the published corpus",
        code="INDEX_ARTIFACT_MISMATCH",
    )


def load_faiss_index(corpus_dir: Path) -> LoadedIndex:
    """Load a published v2 index only if it still belongs to this corpus."""

    import faiss
    import numpy as np

    manifest = load_corpus_manifest(corpus_dir / MANIFEST_FILENAME)
    artifact_path = corpus_dir / ARTIFACT_FILENAME
    if not artifact_path.is_file():
        raise ContractError(
            f"no index artifact in {corpus_dir}", code="INDEX_ARTIFACT_MISSING"
        )
    artifact = IndexArtifact.model_validate_json(artifact_path.read_text(encoding="utf-8"))
    for field_name in ("corpus_version", "corpus_hash", "manifest_hash", "chunk_config_hash"):
        if getattr(artifact, field_name) != getattr(manifest, field_name):
            raise _mismatch(field_name)

    records_path = corpus_dir / manifest.records_relpath
    # records.jsonl is exactly the canonical corpus bytes the hash covers.
    if sha256_file(records_path) != manifest.corpus_hash:
        raise ContractError(
            f"{manifest.records_relpath} no longer hashes to the manifest corpus_hash",
            code="CORPUS_HASH_MISMATCH",
        )

    chunk_ids_path = corpus_dir / INDEX_DIRNAME / CHUNK_IDS_FILENAME
    chunk_ids_bytes = chunk_ids_path.read_bytes()
    if sha256_bytes(chunk_ids_bytes) != artifact.metadata.get("chunk_ids_sha256"):
        raise _mismatch("chunk_ids_sha256")
    chunk_ids = tuple(json.loads(chunk_ids_bytes.decode("utf-8")))
    if chunk_ids != artifact.chunk_ids:
        raise _mismatch("chunk_ids")

    index_bytes = (corpus_dir / INDEX_DIRNAME / INDEX_FILENAME).read_bytes()
    if sha256_bytes(index_bytes) != artifact.metadata.get("index_sha256"):
        raise _mismatch("index_sha256")
    index = faiss.deserialize_index(np.frombuffer(index_bytes, dtype="uint8"))
    if index.ntotal != artifact.chunk_count:
        raise _mismatch("chunk_count")
    if artifact.embedding_dimension is not None and index.d != artifact.embedding_dimension:
        raise _mismatch("embedding_dimension")
    return LoadedIndex(index=index, chunk_ids=chunk_ids, artifact=artifact, manifest=manifest)
