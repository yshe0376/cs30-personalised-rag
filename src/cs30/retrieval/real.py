"""Real Dense, BM25, and reciprocal-rank-fusion retrieval backends.

All backends consume the same ``IndexArtifact`` and ``chunks.json`` produced by
Member 5.  Keeping one chunk map is important: Dense, BM25, and Hybrid results
must use the same chunk ids so their rankings can be compared and fused.

Heavy machine-learning packages are imported lazily.  The fixture pipeline can
therefore still run after a core-only installation of this project.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter, OrderedDict
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

import numpy as np

from cs30.contracts import (
    EvidenceProvenance,
    IndexArtifact,
    RetrievalMode,
    RetrievalResult,
    RetrievedEvidence,
)
from cs30.errors import (
    ArtifactMismatchError,
    EmptyQueryError,
    IndexUnavailableError,
    RetrievalError,
    RetrievalModeError,
)

_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")

_STOPWORDS = frozenset({
    "a", "an", "and", "are", "as", "at", "be", "by", "can", "do", "does",
    "for", "from", "how", "in", "is", "it", "of", "on", "or", "that", "the",
    "to", "was", "were", "what", "when", "where", "which", "who", "why",
    "will", "with",
})


class _EmbeddingModel(Protocol):
    """The small part of SentenceTransformer used by this module."""

    def encode(self, sentences: list[str], *, convert_to_numpy: bool = True) -> Any: ...


class _VectorIndex(Protocol):
    """The small part of a FAISS index used by this module."""

    ntotal: int
    d: int

    def search(self, vectors: np.ndarray, top_k: int) -> tuple[Any, Any]: ...


ModelLoader = Callable[[str], _EmbeddingModel]
IndexReader = Callable[[Path], _VectorIndex]


class _ResultCache:
    """Small in-memory LRU cache scoped to one loaded artifact."""

    def __init__(self, max_size: int) -> None:
        if max_size < 0:
            raise ValueError("cache_size must not be negative")
        self._max_size = max_size
        self._items: OrderedDict[tuple[str, str, int], RetrievalResult] = OrderedDict()

    def clear(self) -> None:
        self._items.clear()

    def get(self, key: tuple[str, str, int]) -> RetrievalResult | None:
        if self._max_size == 0:
            return None
        result = self._items.pop(key, None)
        if result is None:
            return None
        self._items[key] = result
        return result.model_copy(deep=True)

    def put(self, key: tuple[str, str, int], result: RetrievalResult) -> None:
        if self._max_size == 0:
            return
        self._items.pop(key, None)
        self._items[key] = result.model_copy(deep=True)
        while len(self._items) > self._max_size:
            self._items.popitem(last=False)


def _default_model_loader(model_name: str) -> _EmbeddingModel:
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:  # pragma: no cover - depends on optional install
        raise IndexUnavailableError(
            'Dense retrieval needs the ML dependencies: pip install -e ".[ml]"'
        ) from exc
    return SentenceTransformer(model_name)


def _default_index_reader(path: Path) -> _VectorIndex:
    try:
        import faiss
    except ImportError as exc:  # pragma: no cover - depends on optional install
        raise IndexUnavailableError(
            'Dense retrieval needs the ML dependencies: pip install -e ".[ml]"'
        ) from exc
    return faiss.read_index(str(path))


def _resolve_artifact_file(
    artifact: IndexArtifact,
    metadata_key: str,
    default_name: str,
) -> Path:
    """Resolve a file even if an artifact directory was moved with the repo."""

    location_candidate = Path(artifact.location) / default_name
    metadata_value = artifact.metadata.get(metadata_key)
    metadata_candidate = Path(metadata_value) if metadata_value else None

    for candidate in (location_candidate, metadata_candidate):
        if candidate is not None and candidate.is_file():
            return candidate

    shown = metadata_candidate or location_candidate
    raise IndexUnavailableError(f"artifact file not found: {shown}")


def _load_chunk_map(artifact: IndexArtifact) -> list[dict[str, Any]]:
    path = _resolve_artifact_file(artifact, "chunk_map", "chunks.json")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise IndexUnavailableError(f"failed to read chunk map {path}: {exc}") from exc

    if not isinstance(payload, list) or not payload:
        raise ArtifactMismatchError("chunk map must be a non-empty JSON list")
    if len(payload) != artifact.chunk_count:
        raise ArtifactMismatchError(
            "chunk map count does not match IndexArtifact.chunk_count"
        )

    required = {"position", "chunk_id", "text", "chapter_id", "source"}
    seen_ids: set[str] = set()
    validated: list[dict[str, Any]] = []
    for expected_position, item in enumerate(payload):
        if not isinstance(item, dict):
            raise ArtifactMismatchError("every chunk-map item must be an object")
        missing = required - set(item)
        if missing:
            raise ArtifactMismatchError(
                f"chunk-map item {expected_position} is missing {sorted(missing)}"
            )
        if item["position"] != expected_position:
            raise ArtifactMismatchError("chunk-map positions must be consecutive from zero")
        chunk_id = str(item["chunk_id"]).strip()
        if not chunk_id or chunk_id in seen_ids:
            raise ArtifactMismatchError(f"invalid or duplicate chunk_id: {chunk_id!r}")
        for field in ("text", "chapter_id", "source"):
            if not isinstance(item[field], str) or not item[field].strip():
                raise ArtifactMismatchError(
                    f"chunk {chunk_id!r} has invalid {field!r}"
                )
        seen_ids.add(chunk_id)
        validated.append(item)
    return validated


def _provenance(
    artifact: IndexArtifact,
    *,
    include_embedding_model: bool,
) -> EvidenceProvenance:
    required = ("corpus_hash", "chunk_config_hash", "index_version")
    missing = [key for key in required if not artifact.metadata.get(key)]
    if missing:
        raise ArtifactMismatchError(
            f"IndexArtifact is missing provenance metadata: {', '.join(missing)}"
        )

    embedding_model = None
    if include_embedding_model:
        embedding_model = artifact.metadata.get("embedding_model")
        if not embedding_model:
            raise ArtifactMismatchError(
                "IndexArtifact is missing metadata.embedding_model"
            )

    return EvidenceProvenance(
        corpus_hash=artifact.metadata["corpus_hash"],
        chunk_config_hash=artifact.metadata["chunk_config_hash"],
        embedding_model=embedding_model,
        index_version=artifact.metadata["index_version"],
    )


def _validate_request(query: str, top_k: int) -> str:
    cleaned = query.strip()
    if not cleaned:
        raise EmptyQueryError("query must not be empty")
    if top_k < 1:
        raise RetrievalError("top_k must be positive")
    return cleaned


def _cache_key(artifact_id: str, query: str, top_k: int) -> tuple[str, str, int]:
    return artifact_id, query.casefold(), top_k


class FaissDenseRetriever:
    """Cosine-similarity retrieval over Member 5's FAISS ``IndexFlatIP``."""

    index_type = "faiss-flat-ip"

    def __init__(
        self,
        *,
        expected_model_name: str | None = None,
        query_instruction: str | None = None,
        cache_size: int = 256,
        min_similarity: float | None = None,
        model_loader: ModelLoader | None = None,
        index_reader: IndexReader | None = None,
    ) -> None:
        if min_similarity is not None and not -1.0 <= min_similarity <= 1.0:
            raise ValueError("min_similarity must be between -1 and 1")
            
        self.expected_model_name = expected_model_name
        self.query_instruction = query_instruction
        self.min_similarity = min_similarity
        self._model_loader = model_loader or _default_model_loader
        self._index_reader = index_reader or _default_index_reader
        self._cache = _ResultCache(cache_size)

        self._artifact: IndexArtifact | None = None
        self._provenance: EvidenceProvenance | None = None
        self._chunks: list[dict[str, Any]] = []
        self._index: _VectorIndex | None = None
        self._model: _EmbeddingModel | None = None
        self._effective_instruction = ""

    def load_index(self, artifact: IndexArtifact) -> None:
        if artifact.index_type != self.index_type:
            raise ArtifactMismatchError(
                "Dense retrieval requires a faiss-flat-ip artifact; "
                f"received {artifact.index_type!r}"
            )

        model_name = artifact.metadata.get("embedding_model")
        if not model_name:
            raise ArtifactMismatchError(
                "IndexArtifact is missing metadata.embedding_model"
            )
        if self.expected_model_name and model_name != self.expected_model_name:
            raise ArtifactMismatchError(
                "configured embedding model does not match the saved FAISS index: "
                f"{self.expected_model_name!r} != {model_name!r}"
            )

        chunks = _load_chunk_map(artifact)
        index_path = _resolve_artifact_file(artifact, "index_file", "index.faiss")
        try:
            index = self._index_reader(index_path)
            model = self._model_loader(model_name)
        except (IndexUnavailableError, ArtifactMismatchError):
            raise
        except Exception as exc:
            raise IndexUnavailableError(f"failed to load dense index: {exc}") from exc

        if getattr(index, "ntotal", len(chunks)) != len(chunks):
            raise ArtifactMismatchError(
                "FAISS vector count does not match the persisted chunk map"
            )
        saved_dimension = artifact.metadata.get("dimension")
        if saved_dimension and int(saved_dimension) != int(index.d):
            raise ArtifactMismatchError(
                "FAISS dimension does not match IndexArtifact.metadata.dimension"
            )

        self._artifact = artifact
        self._provenance = _provenance(artifact, include_embedding_model=True)
        self._chunks = chunks
        self._index = index
        self._model = model
        self._effective_instruction = (
            self.query_instruction
            if self.query_instruction is not None
            else artifact.metadata.get("query_instruction", "")
        )
        self._cache.clear()

    def _query_input(self, query: str) -> str:
        instruction = self._effective_instruction
        if not instruction:
            return query
        if "{query}" in instruction:
            return instruction.format(query=query)
        return f"{instruction}{query}"

    def retrieve(self, query: str, top_k: int) -> RetrievalResult:
        cleaned = _validate_request(query, top_k)
        if (
            self._artifact is None
            or self._provenance is None
            or self._index is None
            or self._model is None
        ):
            raise IndexUnavailableError("load_index() must be called before dense retrieval")

        key = _cache_key(self._artifact.artifact_id, cleaned, top_k)
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        try:
            encoded = self._model.encode(
                [self._query_input(cleaned)],
                convert_to_numpy=True,
            )
            query_vector = np.asarray(encoded, dtype=np.float32)
            if query_vector.ndim == 1:
                query_vector = query_vector.reshape(1, -1)
            if query_vector.shape != (1, int(self._index.d)):
                raise ArtifactMismatchError(
                    "query embedding dimension does not match the loaded FAISS index"
                )
            norm = float(np.linalg.norm(query_vector[0]))
            if not math.isfinite(norm) or norm == 0.0:
                raise RetrievalError("embedding model produced an invalid query vector")
            query_vector /= norm
            scores, positions = self._index.search(
                query_vector,
                min(top_k, len(self._chunks)),
            )
        except (ArtifactMismatchError, RetrievalError):
            raise
        except Exception as exc:
            raise RetrievalError(f"dense retrieval failed: {exc}") from exc

        hits: list[RetrievedEvidence] = []
        
        for score, position in zip(scores[0], positions[0], strict=True):
            position = int(position)
            if position < 0:
                continue
            score_value = float(score)
            if (
                self.min_similarity is not None
                and score_value < self.min_similarity
            ):
                continue
                
            item = self._chunks[position]
            hits.append(
                RetrievedEvidence(
                    chunk_id=item["chunk_id"],
                    text=item["text"],
                    chapter_id=item["chapter_id"],
                    source=item["source"],
                    score=score_value,
                    rank=len(hits) + 1,
                    retriever_type=RetrievalMode.DENSE,
                )
            )

        result = RetrievalResult(
            query=cleaned,
            mode=RetrievalMode.DENSE,
            hits=hits,
            provenance=self._provenance,
        )
        self._cache.put(key, result)
        return result

    @property
    def evidence_count(self) -> int:
        return len(self._chunks)


class BM25Retriever:
    """Dependency-free Okapi BM25 over the same chunk map as Dense retrieval."""

    index_type = "bm25"

    def __init__(
        self,
        *,
        k1: float = 1.5,
        b: float = 0.75,
        cache_size: int = 256,
        min_score: float = 0.0,
        stopwords: frozenset[str] | None = None,
    ) -> None:
        if k1 <= 0:
            raise ValueError("k1 must be positive")
        if not 0 <= b <= 1:
            raise ValueError("b must be between zero and one")
        if min_score < 0:
            raise ValueError("min_score must not be negative")

        self.k1 = k1
        self.b = b
        self.min_score = min_score
        self._stopwords = _STOPWORDS if stopwords is None else stopwords
        self._cache = _ResultCache(cache_size)

        self._artifact: IndexArtifact | None = None
        self._provenance: EvidenceProvenance | None = None
        self._chunks: list[dict[str, Any]] = []
        self._term_frequencies: list[Counter[str]] = []
        self._document_lengths: list[int] = []
        self._document_frequency: Counter[str] = Counter()
        self._average_document_length = 0.0

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        return _TOKEN_PATTERN.findall(text.casefold())

    def _query_terms(self, query: str) -> Counter[str]:
        return Counter(
            token
            for token in self._tokenize(query)
            if token not in self._stopwords
        )
    def load_index(self, artifact: IndexArtifact) -> None:
        chunks = _load_chunk_map(artifact)
        term_frequencies: list[Counter[str]] = []
        document_lengths: list[int] = []
        document_frequency: Counter[str] = Counter()

        for item in chunks:
            tokens = self._tokenize(item["text"])
            frequencies = Counter(tokens)
            term_frequencies.append(frequencies)
            document_lengths.append(len(tokens))
            document_frequency.update(frequencies.keys())

        self._artifact = artifact
        self._provenance = _provenance(artifact, include_embedding_model=False)
        self._chunks = chunks
        self._term_frequencies = term_frequencies
        self._document_lengths = document_lengths
        self._document_frequency = document_frequency
        self._average_document_length = sum(document_lengths) / len(document_lengths)
        self._cache.clear()

    def _score_document(self, query_terms: Counter[str], position: int) -> float:
        frequencies = self._term_frequencies[position]
        document_length = self._document_lengths[position]
        document_count = len(self._chunks)
        score = 0.0

        for term, query_frequency in query_terms.items():
            term_frequency = frequencies.get(term, 0)
            if term_frequency == 0:
                continue
            document_frequency = self._document_frequency[term]
            inverse_document_frequency = math.log(
                1.0
                + (document_count - document_frequency + 0.5)
                / (document_frequency + 0.5)
            )
            length_ratio = (
                document_length / self._average_document_length
                if self._average_document_length
                else 0.0
            )
            denominator = term_frequency + self.k1 * (1 - self.b + self.b * length_ratio)
            score += (
                query_frequency
                * inverse_document_frequency
                * term_frequency
                * (self.k1 + 1)
                / denominator
            )
        return score

    def retrieve(self, query: str, top_k: int) -> RetrievalResult:
        cleaned = _validate_request(query, top_k)
        if self._artifact is None or self._provenance is None or not self._chunks:
            raise IndexUnavailableError("load_index() must be called before BM25 retrieval")

        key = _cache_key(self._artifact.artifact_id, cleaned, top_k)
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        query_terms = self._query_terms(cleaned)
        if not query_terms:
            result = RetrievalResult(
                query=cleaned,
                mode=RetrievalMode.BM25,
                hits=[],
                provenance=self._provenance,
            )
            self._cache.put(key, result)
            return result

        scored = [
            (self._score_document(query_terms, position), position)
            for position in range(len(self._chunks))
        ]
        scored = [pair for pair in scored if pair[0] > self.min_score]
        scored.sort(
            key=lambda pair: (
                -pair[0],
                self._chunks[pair[1]]["chunk_id"],
            )
        )

        hits = [
            RetrievedEvidence(
                chunk_id=self._chunks[position]["chunk_id"],
                text=self._chunks[position]["text"],
                chapter_id=self._chunks[position]["chapter_id"],
                source=self._chunks[position]["source"],
                score=float(score),
                rank=rank,
                retriever_type=RetrievalMode.BM25,
            )
            for rank, (score, position) in enumerate(scored[:top_k], start=1)
        ]
        result = RetrievalResult(
            query=cleaned,
            mode=RetrievalMode.BM25,
            hits=hits,
            provenance=self._provenance,
        )
        self._cache.put(key, result)
        return result

    @property
    def evidence_count(self) -> int:
        return len(self._chunks)


class RRFRetriever:
    """Fuse Dense and BM25 ranks using Reciprocal Rank Fusion (RRF)."""

    index_type = "rrf-hybrid"

    def __init__(
        self,
        dense: FaissDenseRetriever | None = None,
        bm25: BM25Retriever | None = None,
        *,
        rrf_k: int = 60,
        input_top_k: int = 20,
        cache_size: int = 256,
    ) -> None:
        if rrf_k < 1:
            raise ValueError("rrf_k must be positive")
        if input_top_k < 1:
            raise ValueError("input_top_k must be positive")
        self.dense = dense or FaissDenseRetriever(cache_size=cache_size)
        self.bm25 = bm25 or BM25Retriever(cache_size=cache_size)
        self.rrf_k = rrf_k
        self.input_top_k = input_top_k
        self._cache = _ResultCache(cache_size)
        self._artifact: IndexArtifact | None = None

    def load_index(self, artifact: IndexArtifact) -> None:
        self.dense.load_index(artifact)
        self.bm25.load_index(artifact)
        self._artifact = artifact
        self._cache.clear()

    def retrieve(self, query: str, top_k: int) -> RetrievalResult:
        cleaned = _validate_request(query, top_k)
        if self._artifact is None:
            raise IndexUnavailableError("load_index() must be called before hybrid retrieval")

        key = _cache_key(self._artifact.artifact_id, cleaned, top_k)
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        candidate_count = max(top_k, self.input_top_k)
        dense_result = self.dense.retrieve(cleaned, candidate_count)
        bm25_result = self.bm25.retrieve(cleaned, candidate_count)

        fused: dict[str, dict[str, Any]] = {}
        for result in (dense_result, bm25_result):
            for hit in result.hits:
                state = fused.setdefault(
                    hit.chunk_id,
                    {
                        "hit": hit,
                        "score": 0.0,
                        "best_rank": hit.rank,
                        "modes": set(),
                    },
                )
                # RRF formula: add 1 / (k + rank) for every contributing list.
                state["score"] += 1.0 / (self.rrf_k + hit.rank)
                state["best_rank"] = min(state["best_rank"], hit.rank)
                state["modes"].add(result.mode)

        ranked = sorted(
            fused.values(),
            key=lambda state: (
                -state["score"],
                state["best_rank"],
                state["hit"].chunk_id,
            ),
        )
        hits: list[RetrievedEvidence] = []
        for state in ranked[:top_k]:
            original = state["hit"]
            contributing_modes = state["modes"]
            retriever_type = (
                RetrievalMode.HYBRID
                if len(contributing_modes) == 2
                else next(iter(contributing_modes))
            )
            hits.append(
                RetrievedEvidence(
                    chunk_id=original.chunk_id,
                    text=original.text,
                    chapter_id=original.chapter_id,
                    source=original.source,
                    score=float(state["score"]),
                    rank=len(hits) + 1,
                    retriever_type=retriever_type,
                )
            )

        result = RetrievalResult(
            query=cleaned,
            mode=RetrievalMode.HYBRID,
            hits=hits,
            provenance=dense_result.provenance,
        )
        self._cache.put(key, result)
        return result

    @property
    def evidence_count(self) -> int:
        return self.dense.evidence_count


class RealRetrievalService:
    """Mode dispatcher for experiments that compare all three retrievers."""

    def __init__(
        self,
        dense: FaissDenseRetriever | None = None,
        bm25: BM25Retriever | None = None,
        hybrid: RRFRetriever | None = None,
        *,
        rrf_k: int = 60,
        input_top_k: int = 20,
    ) -> None:
        self.dense = dense or FaissDenseRetriever()
        self.bm25 = bm25 or BM25Retriever()
        self.hybrid = hybrid or RRFRetriever(
            dense=self.dense,
            bm25=self.bm25,
            rrf_k=rrf_k,
            input_top_k=input_top_k,
        )

    def backend(
        self,
        mode: RetrievalMode,
    ) -> FaissDenseRetriever | BM25Retriever | RRFRetriever:
        """Return the retrieval backend selected for one experiment."""

        if mode is RetrievalMode.DENSE:
            return self.dense
        if mode is RetrievalMode.BM25:
            return self.bm25
        if mode is RetrievalMode.HYBRID:
            return self.hybrid
        raise RetrievalModeError(
            f"unsupported real retrieval mode: {mode}"
        )

    def load_index(
        self,
        artifact: IndexArtifact,
        mode: RetrievalMode,
    ) -> None:
        """Load only the backend required by the selected mode."""

        self.backend(mode).load_index(artifact)

    def retrieve(
        self,
        query: str,
        top_k: int,
        mode: RetrievalMode,
    ) -> RetrievalResult:
        """Retrieve evidence and enforce real-mode provenance."""

        result = self.backend(mode).retrieve(query, top_k)

        if result.provenance is None:
            raise ArtifactMismatchError(
                "real retrieval result must include provenance"
            )

        return result
