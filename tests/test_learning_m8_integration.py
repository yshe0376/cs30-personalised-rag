"""Real citation binding, events and M8 page interaction using a local author."""

from pathlib import Path
from types import SimpleNamespace as NS

import pytest
from test_learning_online_quiz import _author_payload, _FakeClient
from test_v2_span_resolver import _corpus_with_chapter_base

from cs30.concept_check.event_store import JsonlEventStore
from cs30.concept_check.fixtures import (
    fixture_retrieval_result,
    load_fixture_corpus,
    load_fixture_topic_registry,
)
from cs30.concept_check.learner_state import EventReplayer
from cs30.concept_check.provider import FixtureQuestionProvider
from cs30.concept_check.service import ConceptCheckService
from cs30.concept_check.snapshot import build_learner_context_snapshot
from cs30.concept_check.topics import ChunkTopicResolver
from cs30.generation.client import MockJsonLLMClient
from cs30.learning.assets import LearningAssets, SetupReport
from cs30.learning.budget import BudgetedClient, PersistentRequestBudget
from cs30.learning.models import LearningTurn
from cs30.learning.online_quiz import OnlineQuizGenerator
from cs30.learning.runtime import LearningRuntime
from cs30.v2.config import ConceptCheckConfig
from cs30.v2.contracts import StudentLevel, StudentProfile
from cs30.v2.evidence import CitationValidatorAdapter, EvidenceBundleAdapter
from cs30.v2.generation import V2AnswerGenerator
from cs30.v2.topics import ChunkTopicAssignment, ChunkTopicMap, LoadedChunkTopicMap


def online_runtime(tmp_path):
    corpus = _corpus_with_chapter_base(tmp_path)
    chunk = corpus.chunks[0]
    registry = load_fixture_topic_registry()
    topic_id = registry.topics[0].topic_id
    topic_map = LoadedChunkTopicMap.validated(
        ChunkTopicMap(
            corpus_version=corpus.manifest.corpus_version,
            corpus_hash=corpus.manifest.corpus_hash,
            topic_registry_version=registry.topic_registry_version,
            assignments=(ChunkTopicAssignment(chunk_id=chunk.chunk_id, topic_ids=(topic_id,)),),
        ), manifest=corpus.manifest, corpus_chunk_ids=corpus.chunk_ids,
    )
    retrieval = fixture_retrieval_result((load_fixture_corpus().chunks[0].chunk_id,))
    hit = retrieval.hits[0].model_copy(update={
        name: getattr(chunk, name) for name in (
            "provider", "textbook_id", "document_id", "chunk_id", "chapter_id",
            "source_name", "source_locator", "page_or_location", "text",
        )
    })
    retrieval = retrieval.model_copy(update={
        "hits": (hit,),
        "provenance": retrieval.provenance.model_copy(update={
            "corpus_version": corpus.manifest.corpus_version,
            "corpus_hash": corpus.manifest.corpus_hash,
        }),
    })
    profile = StudentProfile(profile_id="online-integration", level=StudentLevel.BEGINNER)
    policy = ConceptCheckConfig(enabled=True)
    replayer = EventReplayer(profile, registry, policy)
    store = JsonlEventStore(tmp_path / "events", replayer)
    service = ConceptCheckService(
        config=policy, resolver=ChunkTopicResolver(topic_map, registry, policy),
        provider=FixtureQuestionProvider(()), event_store=store, replayer=replayer,
    )
    budget = PersistentRequestBudget(tmp_path / "requests.json", total_cap=20)
    role = NS(model="local-author", structured_output="json_schema", api_key_env="NO_TEST_KEY")
    config = NS(demo_topic_ids=("*",), answer_api=role, quiz_api=role, verify_api=role,
                model_selection_status="frozen")
    client = _FakeClient(_author_payload(
        evidence_chunk_id=chunk.chunk_id, evidence_quote=chunk.text,
        rationale="The cited textbook passage supports this option.",
    ))
    generator = OnlineQuizGenerator(
        author_client=BudgetedClient(client, budget), corpus=corpus,
        topic_registry=registry, profile_id=profile.profile_id, quiz_config=policy,
    )
    runtime = LearningRuntime(
        config=config, assets=LearningAssets(corpus, registry, topic_map, None, None, None),
        static_profile=profile, concept_check=True, retriever=None, answer_generator=None,
        quiz_generator=generator, request_budget=budget, concept_service=service,
        event_store=store, replayer=replayer,
    )
    bundle = EvidenceBundleAdapter().build(retrieval)
    snapshot = build_learner_context_snapshot(profile, enabled=False)
    answer = V2AnswerGenerator(MockJsonLLMClient()).generate("Explain force", snapshot, bundle)
    validated = CitationValidatorAdapter().validate(answer, bundle)
    assert validated.citation_status == "passed"
    turn = LearningTurn(
        turn_id="turn-local", question="Explain force", status="answered",
        retrieval=retrieval, reranked_retrieval=retrieval, evidence=bundle,
        validated_answer=validated,
    )
    runtime.turns[turn.turn_id] = turn
    runtime.active_turn_id = turn.turn_id
    return runtime


@pytest.mark.parametrize("choice", ["A", None])
def test_bound_draft_grades_or_skips_once_and_replays(tmp_path, choice):
    runtime = online_runtime(tmp_path)
    view = runtime.make_quiz("turn-local", 1)
    assert view.status == "offered", view.notice
    assert runtime.make_quiz("turn-local", 1) is view
    assert runtime.request_usage["used"] == 1
    assert "correct_answer" not in view.model_dump()
    result = runtime.submit(view.turn_id, view.practice_id, choice)
    assert runtime.submit(view.turn_id, view.practice_id, choice) is result
    events = runtime.event_store.events(runtime.static_profile.profile_id)
    assert len(events) == 1
    topic = runtime.learner_state.topics.get(view.topic_id)
    assert (topic.total_attempts if topic else 0) == (1 if choice else 0)
    assert runtime.active_turn.private_quizzes[1].question.status.value == "draft"
    if choice:
        runtime.revoke_latest_attempt()
        topic = runtime.learner_state.topics.get(view.topic_id)
        assert (topic.total_attempts if topic else 0) == 0


def test_m8_online_page_hides_explanation_until_submit_and_downloads_report(monkeypatch, tmp_path):
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest

    from cs30.ui import qa_learning

    runtime = online_runtime(tmp_path)
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
    assert next(item for item in app.button if item.label == "Submit answer").disabled
    assert not any("The cited textbook passage supports" in item.value for item in app.markdown)
    next(item for item in app.radio if item.label == "Choose one answer").set_value("A").run()
    next(item for item in app.button if item.label == "Submit answer").click().run()
    assert not app.exception
    assert any("The cited textbook passage supports" in item.value for item in app.markdown)
    assert len(app.get("download_button")) == 3
    assert runtime.learner_state.topics[view.topic_id].total_attempts == 1
    undo = next(item for item in app.button if item.label == "Undo the latest graded attempt")
    undo.click().run()
    assert not app.exception
    topic = runtime.learner_state.topics.get(view.topic_id)
    assert (topic.total_attempts if topic else 0) == 0
