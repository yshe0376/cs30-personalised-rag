"""Exercise the real build adapters and persisted FAISS handoff without downloads."""

import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import numpy as np
import pytest

from cs30 import build
from cs30.chunking.official import W5_CHUNKING_STRATEGY
from cs30.contracts import IndexArtifact
from cs30.errors import IndexUnavailableError
from cs30.evidence_policy import EVIDENCE_CONTENT_TYPES
from cs30.pipeline import BuildDeps
from cs30.retrieval import BM25Retriever

DOCUMENT = Path(__file__).parents[1] / "src/cs30/fixtures/openstax_document.json"


def test_json_adapter_uses_shared_contract():
    document = build.RealDocumentParser().parse(DOCUMENT)
    assert document.blocks
    assert document.text


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
    monkeypatch.setitem(sys.modules, module.__name__, module)
    source = tmp_path / "book.pdf"
    document = build.RealDocumentParser(chapters=("2", "3")).parse(source)
    assert document.document_id == payload["document_id"]
    assert calls[0][1]["selected_chapters"] == ("2", "3")


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


def test_cli_reports_a_chunking_failure_as_a_clean_error(monkeypatch, tmp_path, capsys):
    """A chunker rejection must reach the operator as a message, not a traceback.

    The real 34-chapter corpus trips this: every shared candidate still sets
    ``reject_duplicate_text=True``, and the blocks surviving an ``include_types``
    filter contain verbatim repeats, so ``S2``-``S6`` abort with "exact duplicate
    chunk text detected".  The packaged fixture is three unique body blocks and
    never reaches that guard, so the path is covered here instead.
    """

    class RejectingChunker:
        def chunk(self, document):
            raise ValueError("exact duplicate chunk text detected")

    def deps(**kwargs):
        return BuildDeps(
            parser=build.RealDocumentParser(),
            chunker=RejectingChunker(),
            index_builder=object(),
            retriever=BM25Retriever(),
        )

    monkeypatch.setattr(build, "build_real_build_deps", deps)

    exit_code = build.main([str(DOCUMENT), "--index-dir", str(tmp_path / "index")])

    assert exit_code == 1
    assert "exact duplicate chunk text detected" in capsys.readouterr().err


def test_default_candidate_is_the_frozen_official_configuration():
    """The default must match the policy Gold is annotated against.

    Member 4's mapping binds chunk IDs produced by the frozen configuration.
    An index built with any other candidate cannot be scored against it, so the
    default has to be the one that corresponds -- not the unfiltered one.
    """

    assert build._chunking_strategy("official") is W5_CHUNKING_STRATEGY
    assert build._chunking_strategy("official").include_types == EVIDENCE_CONTENT_TYPES
    assert build._chunking_strategy("official").reject_duplicate_text is False


def test_main_candidate_still_reaches_the_unfiltered_strategy():
    assert build._chunking_strategy("main").include_types is None


def test_cli_defaults_to_official_when_no_candidate_is_given(monkeypatch, tmp_path):
    """A build run without --candidate must still match Gold's policy."""

    seen = {}

    def deps(**kwargs):
        seen.update(kwargs)
        raise IndexUnavailableError("stop before loading a model")

    monkeypatch.setattr(build, "build_real_build_deps", deps)
    build.main([str(DOCUMENT), "--index-dir", str(tmp_path / "index")])

    assert seen["candidate"] == "official"
