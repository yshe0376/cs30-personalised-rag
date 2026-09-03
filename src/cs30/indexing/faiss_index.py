"""FAISS index builder for educational RAG chunks."""
import hashlib
import json
import time
from pathlib import Path

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

from cs30.contracts import Chunk, EvidenceProvenance, IndexArtifact
from cs30.errors import ArtifactMismatchError, IndexUnavailableError
from cs30.logging import get_logger

LOGGER = get_logger("indexing.faiss")


class HFTokenCounter:
    """Count tokens using the embedding model tokenizer."""

    def __init__(self, model: SentenceTransformer, name: str) -> None:
        self._tokenizer = model.tokenizer
        self.name = name

    def count(self, text: str) -> int:
        """Return the number of tokens without truncation."""

        return len(
            self._tokenizer.encode(
                text,
                add_special_tokens=False,
            )
        )

class FaissIndexBuilder:
    """Build, save, and load a FAISS dense vector index."""

    def __init__(
        self,
        model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
        index_dir: str = "data/index",
        expected_provenance: EvidenceProvenance | None = None,
    ) -> None:
        self.model_name = model_name
        self.index_dir = Path(index_dir)
        self.expected_provenance = expected_provenance

        self._model: SentenceTransformer | None = None

        self._index = None
        self._chunks: list[Chunk] = []
        self._chunk_map: list[dict[str, object]] = []

    def _warn_if_truncated(self, chunks: list[Chunk]) -> None:
        """Warn when chunk inputs exceed the embedding model sequence limit."""

        model = self._load_model()
        limit = getattr(model, "max_seq_length", None)

        if not limit:
            return

        counter = self.token_counter()

        over_limit = [
            chunk.chunk_id
            for chunk in chunks
            if counter.count(chunk.embedding_input) > limit
        ]

        if over_limit:
            LOGGER.warning(
                "%d/%d chunks exceed max_seq_length=%d and may be truncated",
                len(over_limit),
                len(chunks),
                limit,
            )

    def _embed_chunks(self, chunks: list[Chunk]) -> np.ndarray:
        """Convert chunk.embedding_input values into embedding vectors."""

        # IMPORTANT:
        # Use embedding_input rather than chunk.text directly.
        # embedding_input uses embed_text when available and falls back
        # to the original chunk text otherwise.
        texts = [chunk.embedding_input for chunk in chunks]

        model = self._load_model()
        self._warn_if_truncated(chunks)
        embeddings = model.encode(
            texts,
            convert_to_numpy=True,
        )

        return np.asarray(embeddings)

    def _build_faiss_index(
        self,
        embeddings: np.ndarray,
    ):
        """Build an IndexFlatIP index using L2-normalised embeddings."""

        # FAISS expects float32 vectors.
        embeddings = embeddings.astype("float32")

        # After L2 normalisation, inner product corresponds to
        # cosine similarity ranking.
        faiss.normalize_L2(embeddings)

        dimension = embeddings.shape[1]

        index = faiss.IndexFlatIP(dimension)
        index.add(embeddings)

        return index

    def _get_embedding_source(
        self,
        chunks: list[Chunk],
    ) -> str:
        """Describe whether text or enriched embed_text was embedded."""

        uses_embed_text = [
            chunk.embed_text is not None
            for chunk in chunks
        ]

        if all(uses_embed_text):
            return "embed_text"

        if not any(uses_embed_text):
            return "text"

        return "mixed"
        
    def _get_corpus_hash(self, chunks: list[Chunk]) -> str:
        """Build a stable identity for the corpus and parser version."""

        corpus_parts = sorted(
            {
                (
                    chunk.metadata["document_hash"],
                    chunk.metadata["parser_version"],
                )
                for chunk in chunks
            }
        )

        payload = json.dumps(
            corpus_parts,
            separators=(",", ":"),
        )

        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


    def _get_chunk_config_hash(self, chunks: list[Chunk]) -> str:
        """Build a stable identity for the chunking configuration."""

        config_keys = (
            "strategy",
            "chunker_version",
            "tokenizer_name",
            "target_tokens",
            "min_tokens",
            "max_tokens",
            "respect_section_boundaries",
        )

        configurations = {
            tuple(chunk.metadata[key] for key in config_keys)
            for chunk in chunks
        }

        if len(configurations) != 1:
            raise ValueError(
                "cannot index chunks produced by mixed chunk configurations"
            )

        configuration = next(iter(configurations))

        payload = json.dumps(
            dict(zip(config_keys, configuration, strict=True)),
            sort_keys=True,
            separators=(",", ":"),
        )

        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _validate_loaded_artifact(
        self,
        artifact: IndexArtifact,
    ) -> None:
        """Validate the saved artifact against its chunks and current expectations."""

        try:
            saved_provenance = EvidenceProvenance(
                corpus_hash=artifact.metadata["corpus_hash"],
                chunk_config_hash=artifact.metadata["chunk_config_hash"],
                embedding_model=artifact.metadata.get("embedding_model"),
                index_version=artifact.metadata["index_version"],
            )
        except (KeyError, ValueError) as exc:
            raise ArtifactMismatchError(
                f"index artifact has incomplete provenance metadata: {exc}"
            ) from exc

        actual_provenance = EvidenceProvenance(
            corpus_hash=self._get_corpus_hash(self._chunks),
            chunk_config_hash=self._get_chunk_config_hash(self._chunks),
            embedding_model=self.model_name,
            index_version=artifact.metadata["index_version"],
        )

        if saved_provenance != actual_provenance:
            raise ArtifactMismatchError(
                "saved index provenance does not match the persisted chunks "
                "or current embedding model"
            )

        if (
            self.expected_provenance is not None
            and saved_provenance != self.expected_provenance
        ):
            raise ArtifactMismatchError(
                "saved index provenance does not match the expected "
                "corpus, chunk configuration, embedding model, or index version"
            )
    def build(
        self,
        chunks: list[Chunk],
    ) -> IndexArtifact:
        """Build and persist a FAISS index from chunks."""

        if not chunks:
            raise ValueError(
                "cannot build an index from zero chunks"
            )

        start_time = time.perf_counter()

        # ---------------------------------------------------------
        # 1. Convert chunk text into embedding vectors
        # ---------------------------------------------------------
        embeddings = self._embed_chunks(chunks)

        # ---------------------------------------------------------
        # 2. Build FAISS IndexFlatIP
        # ---------------------------------------------------------
        index = self._build_faiss_index(embeddings)

        self._chunks = list(chunks)
        self._index = index

        # ---------------------------------------------------------
        # 3. Prepare output directory
        # ---------------------------------------------------------
        self.index_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        index_path = self.index_dir / "index.faiss"
        chunk_map_path = self.index_dir / "chunks.json"
        artifact_path = self.index_dir / "artifact.json"

        # ---------------------------------------------------------
        # 4. Save FAISS index
        # ---------------------------------------------------------
        faiss.write_index(
            index,
            str(index_path),
        )

        # ---------------------------------------------------------
        # 5. Save vector position -> chunk_id mapping
        # ---------------------------------------------------------
        chunk_map = [
            {
                "position": position,
                "chunk_id": chunk.chunk_id,
                "document_id": chunk.document_id,
                "chapter_id": chunk.chapter_id,
                "text": chunk.text,
                "source": chunk.source,
                "char_start": chunk.char_start,
                "char_end": chunk.char_end,
                "token_count": chunk.token_count,
                "metadata": chunk.metadata,
                "embed_text": chunk.embed_text,
            }
            for position, chunk in enumerate(chunks)
        ]

        self._chunk_map = chunk_map

        with chunk_map_path.open(
            "w",
            encoding="utf-8",
        ) as file:
            json.dump(
                chunk_map,
                file,
                indent=2,
            )

        # ---------------------------------------------------------
        # 6. Record build information
        # ---------------------------------------------------------
        build_time = time.perf_counter() - start_time

        model = self._load_model()
        device = str(model.device)

        embedding_source = self._get_embedding_source(
            chunks
        )
        model_short = self.model_name.split("/")[-1]

        strategies = {
            chunk.metadata["strategy"]
            for chunk in chunks
        }

        if len(strategies) != 1:
            raise ValueError(
                f"cannot index chunks from mixed strategies: {sorted(strategies)}"
            )

        strategy = next(iter(strategies))

        dimension = embeddings.shape[1]

        artifact_id = (
            f"faiss-{model_short}-{strategy}-{dimension}"
        )
        corpus_hash = self._get_corpus_hash(chunks)
        chunk_config_hash = self._get_chunk_config_hash(chunks)

        index_version = (
            f"{model_short}-{dimension}-"
            f"{chunks[0].metadata['chunker_version']}"
        )
        artifact = IndexArtifact(
            artifact_id=artifact_id,
            index_type="faiss-flat-ip",
            location=str(self.index_dir),
            chunk_count=len(chunks),
            metadata={
                "corpus_hash": corpus_hash,
                "chunk_config_hash": chunk_config_hash,
                "embedding_model": self.model_name,
                "index_version": index_version,
                "dimension": str(embeddings.shape[1]),
                "device": device,
                "build_time_seconds": f"{build_time:.4f}",
                "index_file": str(index_path),
                "chunk_map": str(chunk_map_path),
                "embedding_source": embedding_source,
                "normalisation": "L2",
                "similarity": "inner_product",
            },
        )

        # ---------------------------------------------------------
        # 7. Save IndexArtifact manifest
        # ---------------------------------------------------------
        with artifact_path.open(
            "w",
            encoding="utf-8",
        ) as file:
            file.write(
                artifact.model_dump_json(indent=2)
            )

        return artifact

    def _load_model(self) -> SentenceTransformer:
        """Load the embedding model only when it is first needed."""

        if self._model is None:
            self._model = SentenceTransformer(self.model_name)
        return self._model
    
    def load(self) -> IndexArtifact:
        """Load a previously saved FAISS index and metadata."""

        index_path = self.index_dir / "index.faiss"
        chunk_map_path = self.index_dir / "chunks.json"
        artifact_path = self.index_dir / "artifact.json"

        # ---------------------------------------------------------
        # Check that all required files exist
        # ---------------------------------------------------------
        if not index_path.exists():
            raise IndexUnavailableError(
                f"FAISS index not found: {index_path}"
            )

        if not chunk_map_path.exists():
            raise IndexUnavailableError(
                f"chunk map not found: {chunk_map_path}"
            )

        if not artifact_path.exists():
            raise IndexUnavailableError(
                f"index artifact not found: {artifact_path}"
            )

        try:
            # -----------------------------------------------------
            # 1. Restore FAISS index
            # -----------------------------------------------------
            self._index = faiss.read_index(
                str(index_path)
            )

            # -----------------------------------------------------
            # 2. Restore chunk_id mapping
            # -----------------------------------------------------
            with chunk_map_path.open(
                "r",
                encoding="utf-8",
            ) as file:
                self._chunk_map = json.load(file)

            # -----------------------------------------------------
            # 3. Restore IndexArtifact
            # -----------------------------------------------------
            with artifact_path.open(
                "r",
                encoding="utf-8",
            ) as file:
                artifact_data = json.load(file)
            
            self._chunks = [
                Chunk(
                    chunk_id=item["chunk_id"],
                    document_id=item["document_id"],
                    chapter_id=item["chapter_id"],
                    text=item["text"],
                    source=item["source"],
                    char_start=item["char_start"],
                    char_end=item["char_end"],
                    token_count=item["token_count"],
                    metadata=item["metadata"],
                    embed_text=item["embed_text"],
                )
                for item in self._chunk_map
            ]

            artifact = IndexArtifact.model_validate(
                artifact_data
            )
            self._validate_loaded_artifact(artifact)
        except ArtifactMismatchError:
            raise
        except Exception as exc:
            raise IndexUnavailableError(
                f"failed to load FAISS index: {exc}"
            ) from exc

        return artifact
    def token_counter(self) -> HFTokenCounter:
        """Return a token counter backed by the embedding model tokenizer."""

        model = self._load_model()

        return HFTokenCounter(
            model=model,
            name=self.model_name,
        )

    @property
    def index(self):
        """Return the loaded FAISS index."""

        if self._index is None:
            raise IndexUnavailableError(
                "index must be built or loaded before use"
            )

        return self._index

    @property
    def chunk_map(self) -> list[dict[str, object]]:
        """Return the FAISS position-to-chunk_id mapping."""

        if not self._chunk_map:
            raise IndexUnavailableError(
                "chunk map must be built or loaded before use"
            )

        return self._chunk_map

    @property
    def chunks(self) -> list[Chunk]:
        """Return chunks associated with the loaded FAISS index."""

        if not self._chunks:
            raise IndexUnavailableError(
                "chunks must be built or loaded before use"
            )

        return self._chunks
