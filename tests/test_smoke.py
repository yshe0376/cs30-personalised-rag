"""Critical runnable-path checks required by the Member 8 delivery plan."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from cs30.config import load_config
from cs30.contracts import PipelineRun, StudentLevel
from cs30.logging import configure_logging, get_logger, log_path
from cs30.pipeline import (
    build_fixture_build_deps,
    build_fixture_deps,
    run_build_pipeline,
    run_pipeline,
)

pytestmark = pytest.mark.smoke


def test_smoke_streamlit_starts_and_submits_a_question() -> None:
    app_path = Path(__file__).parents[1] / "src" / "cs30" / "ui" / "app.py"
    app = AppTest.from_file(app_path).run()

    assert not app.exception
    app.selectbox[0].select("beginner")
    app.text_area[0].set_value("What is acceleration?")
    app.button[0].click().run()

    assert not app.exception
    assert any("Generated answer" in item.value for item in app.markdown)
    assert any("Content type: Body" in item.value for item in app.caption)


def test_smoke_index_load_and_retrieval_interface() -> None:
    deps = build_fixture_build_deps()
    artifact = run_build_pipeline(Path("unused-fixture-source"), deps)
    result = deps.retriever.retrieve("What is acceleration?", top_k=3)

    assert artifact.chunk_count == 3
    assert result.hits
    assert result.hits[0].content_types


def test_smoke_json_round_trip_and_citation_integrity() -> None:
    run = run_pipeline(
        "What is acceleration?",
        StudentLevel.INTERMEDIATE,
        build_fixture_deps(),
        load_config("development"),
    )
    restored = PipelineRun.model_validate_json(run.model_dump_json())
    retrieved_ids = {hit.chunk_id for hit in restored.retrieval.hits}

    assert restored.citation_integrity == "passed"
    assert set(restored.answer.citations) <= retrieved_ids


def test_smoke_staging_preview_is_explicitly_fixture_backed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CS30_ENV", "staging")
    monkeypatch.setenv("CS30_FIXTURE_MODE", "true")
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    config = load_config("staging")

    assert config.environment == "staging"
    assert config.fixture_mode is True
    assert config.generation.provider == "mock"

    app_path = Path(__file__).parents[1] / "src" / "cs30" / "ui" / "app.py"
    app = AppTest.from_file(app_path).run()
    assert not app.exception
    assert "STAGING PREVIEW" in app.info[0].value
    assert "FIXTURE MODE" in app.info[0].value


def test_smoke_log_file_is_written(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = logging.getLogger("cs30")
    existing_file_handlers = [
        handler for handler in root.handlers if getattr(handler, "_cs30_file", False)
    ]
    for handler in existing_file_handlers:
        root.removeHandler(handler)

    monkeypatch.setenv("CS30_LOG_DIR", str(tmp_path))
    configure_logging("INFO")
    get_logger("smoke").info("smoke-log-check")

    target = log_path()
    assert target.is_file()
    assert "smoke-log-check" in target.read_text(encoding="utf-8")

    new_file_handlers = [
        handler for handler in root.handlers if getattr(handler, "_cs30_file", False)
    ]
    for handler in new_file_handlers:
        root.removeHandler(handler)
        handler.close()
    for handler in existing_file_handlers:
        root.addHandler(handler)
