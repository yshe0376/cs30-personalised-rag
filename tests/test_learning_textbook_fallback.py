"""Topic selection falls back to validated passages without inventing Topic progress."""

import json
from dataclasses import replace
from pathlib import Path

import pytest
from test_learning_m8_integration import online_runtime

from cs30.v2.topics import ChunkTopicMap, LoadedChunkTopicMap


def without_topic_mapping(runtime):
    corpus = runtime.assets.corpus
    registry = runtime.assets.topic_registry
    mapping = LoadedChunkTopicMap.validated(
        ChunkTopicMap(
            corpus_version=corpus.manifest.corpus_version,
            corpus_hash=corpus.manifest.corpus_hash,
            topic_registry_version=registry.topic_registry_version,
            assignments=(),
        ),
        manifest=corpus.manifest,
        corpus_chunk_ids=corpus.chunk_ids,
    )
    runtime.assets = replace(runtime.assets, topic_map=mapping)
    runtime.concept_service.resolver.topic_map = mapping
    return runtime


@pytest.mark.parametrize("choice", ["A", "B", None])
def test_unmapped_citation_generates_and_grades_without_topic_events(tmp_path, choice):
    runtime = without_topic_mapping(online_runtime(tmp_path))
    before = runtime.learner_state.model_dump()
    view = runtime.make_quiz("turn-local", 1)
    assert view.status == "offered", view.notice
    assert view.generation_basis == "textbook"
    assert view.topic_id is None
    assert "correct_answer" not in view.model_dump()
    assert runtime.make_quiz("turn-local", 1) is view
    assert runtime.request_usage["used"] == 1
    record = runtime.active_turn.private_quizzes[1]
    assert record.topic_id is None
    assert record.question.evidence_anchors
    assert not hasattr(record.question, "topic_id")
    result = runtime.submit(view.turn_id, view.practice_id, choice)
    assert result.grade.result.value == {"A": "correct", "B": "incorrect", None: "skipped"}[choice]
    assert result.topic_id is None
    assert runtime.submit(view.turn_id, view.practice_id, choice) is result
    assert runtime.learner_state.model_dump() == before
    assert runtime.event_store.events(runtime.static_profile.profile_id) == ()
    journal = runtime.event_store.directory / "textbook_practice_attempts.jsonl"
    rows = journal.read_text().splitlines()
    assert len(rows) == 1
    assert json.loads(rows[0])["topic_id"] is None
    with pytest.raises(ValueError, match="no graded answer to undo"):
        runtime.revoke_latest_attempt()


def test_mapped_topic_is_preferred_and_updates_topic_progress(tmp_path):
    runtime = online_runtime(tmp_path)
    view = runtime.make_quiz("turn-local", 1)
    assert view.status == "offered", view.notice
    assert view.generation_basis == "topic"
    assert view.topic_id
    runtime.submit(view.turn_id, view.practice_id, "A")
    assert runtime.learner_state.topics[view.topic_id].total_attempts == 1
    assert not (runtime.event_store.directory / "textbook_practice_attempts.jsonl").exists()


@pytest.mark.parametrize("failure", ["failed_citations", "missing_citations", "mismatched_corpus"])
def test_fallback_never_bypasses_invalid_evidence(tmp_path, failure):
    runtime = without_topic_mapping(online_runtime(tmp_path))
    turn = runtime.active_turn
    if failure == "failed_citations":
        turn.validated_answer = turn.validated_answer.model_copy(
            update={"citation_status": "failed"},
        )
    elif failure == "missing_citations":
        turn.validated_answer = turn.validated_answer.model_copy(update={"resolved_citations": ()})
    else:
        retrieval = turn.reranked_retrieval
        turn.reranked_retrieval = retrieval.model_copy(
            update={
                "provenance": retrieval.provenance.model_copy(
                    update={"corpus_hash": "wrong-corpus"}
                ),
            }
        )
    view = runtime.make_quiz(turn.turn_id, 1)
    assert view.status == "unavailable"
    assert runtime.request_usage["used"] == 0


@pytest.mark.parametrize("skip", [False, True])
def test_textbook_fallback_page_submits_or_skips_without_topic_progress(
    monkeypatch, tmp_path, skip,
):
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest

    from cs30.learning.assets import SetupReport
    from cs30.ui import qa_learning

    runtime = without_topic_mapping(online_runtime(tmp_path))
    view = runtime.make_quiz("turn-local", 1)
    assert view.status == "offered", view.notice
    monkeypatch.setattr(qa_learning.LearningConfig, "load", lambda: runtime.config)
    monkeypatch.setattr(qa_learning, "check_learning_setup", lambda config: SetupReport(()))
    app = AppTest.from_file(
        Path(__file__).parents[1] / "src/cs30/ui/qa_app.py", default_timeout=30,
    )
    app.session_state["qa-demo-settings"] = {
        "mode": "Online learning · textbook quizzes", "model": "openai/gpt-oss-20b",
        "retrieval": "hybrid",
    }
    app.session_state["learning_runtime"] = runtime
    app.run()
    assert not app.exception
    assert any("Textbook-based practice" in item.value for item in app.info)
    assert not any("The cited textbook passage supports" in item.value for item in app.markdown)
    if skip:
        next(button for button in app.button if button.label == "Skip this question").click().run()
    else:
        next(item for item in app.radio if item.label == "Choose one answer").set_value("A").run()
        next(button for button in app.button if button.label == "Submit answer").click().run()
    assert not app.exception
    assert any("The cited textbook passage supports" in item.value for item in app.markdown)
    assert any("Topic mastery and levels were not changed" in item.value for item in app.caption)
    assert not runtime.learner_state.topics
