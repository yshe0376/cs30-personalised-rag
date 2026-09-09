"""Exercise the real build adapters and persisted FAISS handoff without downloads."""

import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import numpy as np
import pytest

from cs30 import build
from cs30.contracts import IndexArtifact
from cs30.retrieval import BM25Retriever

DOCUMENT = Path(__file__).parents[1] / "src/cs30/fixtures/openstax_document.json"


def test_json_adapter_uses_shared_contract():
    document = build.RealDocumentParser().parse(DOCUMENT)
    assert document.blocks
    assert document.text


def test_real_build_caps_chunk_strategy_to_embedder_limit(monkeypatch, tmp_path):
    class FakeBuilder:
        def __init__(self, **kwargs):
            pass

        def token_counter(self):
            return SimpleNamespace(
                name="fake-tokenizer",
                max_input_tokens=128,
                count=lambda text: len(text.split()),
            )

    from cs30.indexing import faiss_index

    monkeypatch.setattr(faiss_index, "FaissIndexBuilder", FakeBuilder)
    deps = build.build_real_build_deps(
        index_dir=tmp_path,
        model_name="fake-model",
        candidate="S2",
    )

    assert deps.chunker.strategy.max_tokens == 128
    assert deps.chunker.strategy.target_tokens == 128
    assert deps.chunker.strategy.min_tokens == 100


def test_pdf_adapter_converts_m2_payload(monkeypatch, tmp_path):
    payload = json.loads(DOCUMENT.read_text(encoding="utf-8"))
    calls = []
    module = ModuleType("cs30.ingest.openstax_parser")

    def parse(source, **kwargs):
        calls.append((source, kwargs))
        return "parser-internal-document"

    def convert(value):
        assert value == "parser-internal-document"
        return payload

    module.parse_openstax = parse
    module.build_contract_payload = convert
    module.validate_source_identity = lambda source, markers: None
    module.sha256_file = lambda source: "a" * 64
    monkeypatch.setitem(sys.modules, module.__name__, module)
    source = tmp_path / "book.pdf"
    document = build.RealDocumentParser(chapters=("2", "3")).parse(source)
    assert document.document_id == payload["document_id"]
    assert calls[0][1]["selected_chapters"] == ("2", "3")


def test_pdf_adapter_applies_ck12_catalog_metadata(monkeypatch, tmp_path):
    payload = json.loads(DOCUMENT.read_text(encoding="utf-8"))
    calls = []
    module = ModuleType("cs30.ingest.openstax_parser")
    module.sha256_file = lambda source: "a" * 64
    module.validate_source_identity = lambda source, markers: None
    module.parse_openstax = lambda source, **kwargs: calls.append(kwargs) or "parsed"
    module.build_contract_payload = lambda value: payload
    monkeypatch.setitem(sys.modules, module.__name__, module)

    document = build.RealDocumentParser(
        chapters=("1",),
        textbook_id="ck12_physics_concepts_intermediate",
    ).parse(tmp_path / "book.pdf")

    assert calls[0]["title"] == "CK-12 Physics Concepts - Intermediate"
    assert calls[0]["source_url"].endswith("CK-12-Physics-Concepts-Intermediate/")
    assert calls[0]["document_id"].startswith("ck12-physics-concepts-intermediate-")
    assert document.blocks[0].metadata["provider"] == "CK-12"
    assert document.blocks[0].metadata["license"] == "CC BY-NC 3.0"


def test_cli_rejects_missing_chapters_before_model_loading(tmp_path, capsys):
    source = tmp_path / "book.pdf"
    source.touch()
    assert build.main([str(source), "--index-dir", str(tmp_path / "index")]) == 1
    assert "requires --chapters" in capsys.readouterr().err


def test_cli_preserves_existing_output(tmp_path, capsys):
    existing = tmp_path / "artifact.json"
    existing.write_text("keep", encoding="utf-8")
    assert build.main([str(DOCUMENT), "--index-dir", str(tmp_path)]) == 1
    assert existing.read_text() == "keep"
    assert "must be empty" in capsys.readouterr().err


def test_real_builder_writes_reloadable_index(monkeypatch, tmp_path, capsys):
    faiss = pytest.importorskip("faiss")

    # Only the external embedding model is replaced; M4, M5 and FAISS run normally.
    class Model:
        device = "cpu"
        max_seq_length = 512

        def __init__(self, name):
            self.tokenizer = SimpleNamespace(encode=lambda text, **kw: text.split())

        def encode(self, texts, **kwargs):
            return np.array([[1, i + 1, 2, 3] for i in range(len(texts))], dtype=np.float32)

    fake = ModuleType("sentence_transformers")
    fake.SentenceTransformer = Model
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake)
    from cs30.indexing import faiss_index

    monkeypatch.setattr(faiss_index, "SentenceTransformer", Model)

    output = tmp_path / "index"
    assert (
        build.main(
            [
                str(DOCUMENT),
                "--index-dir",
                str(output),
                "--model",
                "test-model",
                "--candidate",
                "S2",
            ]
        )
        == 0
    )
    artifact = IndexArtifact.model_validate_json(capsys.readouterr().out)
    assert artifact.metadata["embedding_model"] == "test-model"
    index = faiss.read_index(str(output / "index.faiss"))
    assert index.ntotal == artifact.chunk_count > 0
    rows = json.loads((output / "chunks.json").read_text())
    assert all(row["metadata"]["tokenizer_name"] == "test-model" for row in rows)
    assert all(row["metadata"]["candidate_id"] == "S2" for row in rows)
    retriever = BM25Retriever()
    retriever.load_index(artifact)
    assert retriever.retrieve("acceleration", 3).hits
