"""Every retrieval knob must reach the object it configures (backlog B21).

A configuration field that is declared but never passed to a retriever does not
fail loudly. It validates, it reads back correctly from ``AppConfig``, and it
silently changes nothing. That has already happened twice in this module:
``bm25_min_score`` and ``dense_min_similarity`` shipped as configuration fields
and environment variables while ``build_real_deps`` still constructed the
retrievers with no arguments. CI was green throughout, because no test and no
smoke assertion connected the two ends.

A dead knob is worse than a missing one. An ablation row filled from a knob
that does nothing records a number nobody can explain, and the table looks
complete while being wrong.

The registry below is the point of this module. Every field on
``RetrievalConfig`` must appear either in ``WIRING_CASES`` -- proving a
distinctive value travels from configuration to a named attribute of the
retriever ``build_real_deps`` hands back -- or in ``NOT_CONSTRUCTOR_KNOBS``
with a written reason. ``test_every_retrieval_knob_is_registered`` fails when a
new field is added to neither, so the next knob cannot be forgotten quietly.

These tests deliberately stub index loading. Whether ``build_real_deps``
actually loads an index is covered by ``test_real_retrieval.py`` and by the
real-mode assertions in CI's smoke job; what is checked here is only that
configuration reaches construction.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

import cs30.retrieval.real as real_retrieval
from cs30.config import AppConfig, RetrievalConfig
from cs30.contracts import IndexArtifact, RetrievalMode
from cs30.pipeline import build_real_deps

SHARED_FIXTURE_INDEX = Path(__file__).parent / "fixtures" / "index"


@dataclass(frozen=True)
class WiringCase:
    """One configuration field, and where its value must end up."""

    field: str
    value: Any
    mode: RetrievalMode
    attribute: str
    """Dotted path from the retriever ``build_real_deps`` returns."""


WIRING_CASES: tuple[WiringCase, ...] = (
    WiringCase("bm25_min_score", 7.5, RetrievalMode.BM25, "min_score"),
    WiringCase("bm25_min_score", 7.5, RetrievalMode.HYBRID, "bm25.min_score"),
    WiringCase("dense_min_similarity", 0.42, RetrievalMode.DENSE, "min_similarity"),
    WiringCase(
        "dense_min_similarity", 0.42, RetrievalMode.HYBRID, "dense.min_similarity"
    ),
    WiringCase("rrf_k", 17, RetrievalMode.HYBRID, "rrf_k"),
    WiringCase("rrf_input_top_k", 33, RetrievalMode.HYBRID, "input_top_k"),
    # ``_stopwords`` is private, but this assertion is about wiring rather than
    # behaviour, and the public surface is the constructor argument. The
    # behavioural half lives in test_bm25_stopword_knob_changes_retrieval.
    WiringCase("bm25_stopwords", False, RetrievalMode.BM25, "_stopwords"),
    WiringCase("bm25_stopwords", False, RetrievalMode.HYBRID, "bm25._stopwords"),
)

EXPECTED_VALUES: dict[tuple[str, Any], Any] = {
    ("bm25_stopwords", False): frozenset(),
}
"""Where the stored value differs from the configured one."""

NOT_CONSTRUCTOR_KNOBS: dict[str, str] = {
    "top_k": (
        "Passed to Retriever.retrieve() on every call, not to the constructor. "
        "run_pipeline reads it; test_pipeline.py covers that path."
    ),
    "index_dir": (
        "Locates artifact.json rather than configuring a retriever. Every test "
        "here proves it is read, because build_real_deps finds the artifact."
    ),
    "mode": (
        "Selects which backend is built rather than setting a value on one. "
        "test_mode_selects_the_matching_backend covers it."
    ),
    "index_type": (
        "Only a fallback label for PipelineRun metadata, used when a retriever "
        "exposes no index_type attribute. Every real retriever defines one, so "
        "in real mode the configured value is never read. Kept because fixture "
        "backends still fall back to it."
    ),
}


def _resolve(obj: object, dotted: str) -> Any:
    for name in dotted.split("."):
        obj = getattr(obj, name)
    return obj


def _write_artifact(index_dir: Path) -> None:
    """Write the smallest artifact.json build_real_deps will accept."""

    index_dir.mkdir(parents=True, exist_ok=True)
    artifact = IndexArtifact(
        artifact_id="knob-reachability-artifact",
        index_type="bm25",
        location=str(index_dir),
        chunk_count=1,
        metadata={
            "corpus_hash": "knob-corpus",
            "chunk_config_hash": "knob-chunk-config",
            "index_version": "knob-v1",
        },
    )
    (index_dir / "artifact.json").write_text(
        artifact.model_dump_json(),
        encoding="utf-8",
    )


@pytest.fixture
def stub_index_loading(monkeypatch: pytest.MonkeyPatch) -> None:
    """Build the retrievers without touching FAISS, a model, or a chunk map."""

    monkeypatch.setattr(
        real_retrieval.RealRetrievalService,
        "load_index",
        lambda self, artifact, mode: None,
    )


def _deps_for(index_dir: Path, **retrieval: Any):
    config = AppConfig(
        fixture_mode=False,
        retrieval=RetrievalConfig(index_dir=str(index_dir), **retrieval),
    )
    return build_real_deps(config)


@pytest.mark.parametrize(
    "case",
    WIRING_CASES,
    ids=lambda case: f"{case.field}-{case.mode.value}",
)
def test_configured_knob_reaches_the_retriever(
    case: WiringCase,
    tmp_path: Path,
    stub_index_loading: None,
) -> None:
    _write_artifact(tmp_path)

    deps = _deps_for(tmp_path, mode=case.mode, **{case.field: case.value})

    expected = EXPECTED_VALUES.get((case.field, case.value), case.value)
    assert deps.mode == "real"
    assert _resolve(deps.retriever, case.attribute) == expected


@pytest.mark.parametrize(
    ("mode", "expected_type"),
    [
        (RetrievalMode.BM25, real_retrieval.BM25Retriever),
        (RetrievalMode.DENSE, real_retrieval.FaissDenseRetriever),
        (RetrievalMode.HYBRID, real_retrieval.RRFRetriever),
    ],
)
def test_mode_selects_the_matching_backend(
    mode: RetrievalMode,
    expected_type: type,
    tmp_path: Path,
    stub_index_loading: None,
) -> None:
    _write_artifact(tmp_path)

    deps = _deps_for(tmp_path, mode=mode)

    assert isinstance(deps.retriever, expected_type)


def test_every_retrieval_knob_is_registered() -> None:
    """The guard itself: a new knob must be wired or explained, never ignored.

    If this fails, do not widen NOT_CONSTRUCTOR_KNOBS to make it pass. Add a
    WiringCase proving the new field reaches the object it claims to configure.
    """

    registered = {case.field for case in WIRING_CASES} | set(NOT_CONSTRUCTOR_KNOBS)
    declared = set(RetrievalConfig.model_fields)

    assert declared - registered == set(), (
        "new RetrievalConfig field is not proven to reach any retriever: "
        f"{sorted(declared - registered)}"
    )
    assert registered - declared == set(), (
        "registry names a RetrievalConfig field that no longer exists: "
        f"{sorted(registered - declared)}"
    )


def test_bm25_stopword_knob_changes_retrieval() -> None:
    """Ablation A2 must be runnable from configuration alone.

    Without query-side stopword filtering, an English question matches any
    passage sharing a function word: "What is quantum entanglement?" scores
    against every chunk containing "is". That is the defect the filter fixes,
    so toggling the knob has to reproduce both sides of it.
    """

    off_the_topic = "What is quantum entanglement?"

    filtered = _deps_for(
        SHARED_FIXTURE_INDEX, mode=RetrievalMode.BM25, bm25_stopwords=True
    )
    assert filtered.retriever.retrieve(off_the_topic, 5).hits == []

    unfiltered = _deps_for(
        SHARED_FIXTURE_INDEX, mode=RetrievalMode.BM25, bm25_stopwords=False
    )
    assert unfiltered.retriever.retrieve(off_the_topic, 5).hits, (
        "disabling the stopword filter should restore the stopword-only match "
        "this ablation is meant to measure"
    )


def test_stopword_env_override_reaches_the_retriever(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stub_index_loading: None,
) -> None:
    """The environment variable is a separate path from the TOML default."""

    from cs30.config import load_config

    _write_artifact(tmp_path)
    monkeypatch.setenv("CS30_BM25_STOPWORDS", "false")
    monkeypatch.setenv("CS30_INDEX_DIR", str(tmp_path))
    monkeypatch.setenv("CS30_RETRIEVAL_MODE", "bm25")

    config = load_config("development")
    assert config.retrieval.bm25_stopwords is False

    deps = build_real_deps(config.model_copy(update={"fixture_mode": False}))
    assert deps.retriever._stopwords == frozenset()


def test_invalid_stopword_env_value_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from cs30.config import load_config
    from cs30.errors import ConfigError

    monkeypatch.setenv("CS30_BM25_STOPWORDS", "maybe")

    with pytest.raises(ConfigError, match="CS30_BM25_STOPWORDS"):
        load_config("development")


def test_shared_fixture_index_stays_usable() -> None:
    """The shared fixture is a dependency of the tests above and of CI."""

    chunks = json.loads(
        (SHARED_FIXTURE_INDEX / "chunks.json").read_text(encoding="utf-8")
    )
    artifact = json.loads(
        (SHARED_FIXTURE_INDEX / "artifact.json").read_text(encoding="utf-8")
    )

    assert artifact["chunk_count"] == len(chunks)
    assert [chunk["position"] for chunk in chunks] == list(range(len(chunks)))
    assert len({chunk["chunk_id"] for chunk in chunks}) == len(chunks)
    assert not any(
        word in chunk["text"].lower()
        for chunk in chunks
        for word in ("quantum", "entanglement")
    ), "the out-of-scope assertions depend on these words being absent"
