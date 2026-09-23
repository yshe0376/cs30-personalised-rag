"""Building and loading the v2 dense index, and refusing a mismatched pairing."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from test_v2_contracts import make_document
from test_v2_pipeline import StaticParser, StaticRegistry

from cs30.v2.catalog import REQUIRED_TEXTBOOK_IDS, get_textbook_spec
from cs30.v2.chunking import V2BlockChunker
from cs30.v2.errors import ContractError
from cs30.v2.ids import sha256_text
from cs30.v2.indexing import FaissIndexBuilder, load_faiss_index
from cs30.v2.pipeline import (
    BuildDeps,
    MultiTextbookBuildSpec,
    run_build_pipeline,
)
from cs30.v2.ports import TextbookInput

pytest.importorskip("faiss")
np = pytest.importorskip("numpy")

DIMENSION = 8


class HashEncoder:
    """Deterministic unit-length vectors, so no model download is needed."""

    model_name = "test/hash-encoder"
    revision = "test-revision"
    dimension = DIMENSION
    max_input_tokens = 3  # short, so some chunks count as truncated

    def __init__(self) -> None:
        self.batch_sizes: list[int] = []

    def encode(self, texts, *, batch_size: int):
        self.batch_sizes.append(batch_size)
        rows = []
        for text in texts:
            digest = hashlib.sha256(text.encode("utf-8")).digest()
            vector = np.frombuffer(digest[:DIMENSION], dtype="uint8").astype("float32")
            rows.append(vector / np.linalg.norm(vector))
        return np.vstack(rows)

    def count_tokens(self, text: str) -> int:
        return len(text.split())


def build_corpus(tmp_path: Path, *, index: bool = True):
    inputs = []
    parsers = {}
    for position, textbook_id in enumerate(REQUIRED_TEXTBOOK_IDS, start=1):
        text = f"Book {position} explains force, motion and energy.\n[[FORMULA:f=ma]]\n[[IMAGE:f]]"
        document = make_document(
            textbook_id,
            provider=get_textbook_spec(textbook_id).provider,
            text=text,
        ).model_copy(update={"raw_source_sha256": sha256_text(text)})
        source = tmp_path / f"{textbook_id}.txt"
        source.write_bytes(text.encode("utf-8"))
        inputs.append(
            TextbookInput(
                textbook_id=textbook_id,
                source_path=source,
                source_name=document.source_name,
                source_version=document.source_version,
                source_uri=document.source_uri,
            )
        )
        parsers[textbook_id] = StaticParser(document)
    encoder = HashEncoder()
    builder = FaissIndexBuilder(encoder_factory=lambda: encoder, batch_size=4)
    output_dir = tmp_path / "artifacts" / "v2" / "textbooks" / "indexed"
    outcome = run_build_pipeline(
        inputs,
        BuildDeps(
            parser_registry=StaticRegistry(parsers),
            chunker=V2BlockChunker(),
            index_builder=builder if index else None,
        ),
        MultiTextbookBuildSpec(
            corpus_version="2.0.0-dev.1",
            required_textbook_ids=REQUIRED_TEXTBOOK_IDS,
            mode="development",
            environment="development",
            output_dir=output_dir,
        ),
    )
    return outcome, output_dir, encoder


def test_index_rows_follow_the_published_record_order(tmp_path: Path) -> None:
    outcome, output_dir, encoder = build_corpus(tmp_path)

    artifact = outcome.artifact
    assert artifact is not None
    record_ids = [
        json.loads(line)["chunk_id"]
        for line in (output_dir / "records.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert list(artifact.chunk_ids) == record_ids
    assert artifact.embedding_model == "test/hash-encoder"
    assert artifact.embedding_revision == "test-revision"
    assert artifact.embedding_dimension == DIMENSION
    assert artifact.normalise_embeddings is True
    assert artifact.similarity_metric == "inner_product"
    assert encoder.batch_sizes == [4]
    assert (output_dir / "index" / "index.faiss").is_file()
    assert (output_dir / "index" / "chunk_ids.json").is_file()


def test_a_loaded_index_finds_the_chunk_its_own_vector_came_from(tmp_path: Path) -> None:
    _, output_dir, encoder = build_corpus(tmp_path)

    loaded = load_faiss_index(output_dir)

    assert loaded.chunk_ids == loaded.artifact.chunk_ids
    assert loaded.index.ntotal == loaded.artifact.chunk_count
    records = [
        json.loads(line)
        for line in (output_dir / "records.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    target = records[3]
    query = encoder.encode([target["text"]], batch_size=1)
    best = loaded.search(query, 1)[0][0]
    assert best[0] == target["chunk_id"]
    assert best[1] == pytest.approx(1.0, abs=1e-5)


def test_truncation_against_the_model_limit_is_recorded(tmp_path: Path) -> None:
    _, output_dir, _ = build_corpus(tmp_path)

    artifact = load_faiss_index(output_dir).artifact

    assert artifact.metadata["max_input_tokens"] == "3"
    assert int(artifact.metadata["truncated_chunk_count"]) >= 1


@pytest.mark.parametrize(
    ("relative", "content"),
    [
        ("records.jsonl", b'{"chunk_id": "tampered"}\n'),
        ("index/chunk_ids.json", b'["tampered"]'),
        ("index/index.faiss", b"not-an-index"),
    ],
)
def test_loading_refuses_a_corpus_or_index_that_changed(
    tmp_path: Path, relative: str, content: bytes
) -> None:
    _, output_dir, _ = build_corpus(tmp_path)
    (output_dir / relative).write_bytes(content)

    with pytest.raises(ContractError) as exc_info:
        load_faiss_index(output_dir)

    assert exc_info.value.code in {"CORPUS_HASH_MISMATCH", "INDEX_ARTIFACT_MISMATCH"}


def test_loading_without_an_index_artifact_is_explicit(tmp_path: Path) -> None:
    _, output_dir, _ = build_corpus(tmp_path, index=False)

    with pytest.raises(ContractError) as exc_info:
        load_faiss_index(output_dir)

    assert exc_info.value.code == "INDEX_ARTIFACT_MISSING"


def test_an_encoder_with_the_wrong_shape_is_rejected(tmp_path: Path) -> None:
    class WrongShapeEncoder(HashEncoder):
        def encode(self, texts, *, batch_size: int):
            return super().encode(texts, batch_size=batch_size)[:, :-1]

    builder = FaissIndexBuilder(encoder_factory=WrongShapeEncoder)
    document = make_document(REQUIRED_TEXTBOOK_IDS[0])
    chunks = V2BlockChunker().chunk(document)

    class FakeManifest:
        corpus_version = "2.0.0-dev.1"
        corpus_hash = "sha256:" + "0" * 64
        manifest_hash = "sha256:" + "1" * 64
        chunk_config_hash = "sha256:config"
        required_textbook_ids = REQUIRED_TEXTBOOK_IDS
        included_textbook_ids = REQUIRED_TEXTBOOK_IDS

    with pytest.raises(ContractError) as exc_info:
        builder.build(chunks, FakeManifest(), output_dir=tmp_path)

    assert exc_info.value.code == "EMBEDDING_SHAPE_MISMATCH"
