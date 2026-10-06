from __future__ import annotations

from cs30.contracts import StudentLevel
from cs30.ui.app import execute_fixture_run
from cs30.ui.concept_check import (
    FIXTURE_CORPUS_HASH,
    FIXTURE_CORPUS_VERSION,
    build_fixture_session,
)
from cs30.v2.contracts import ConceptCheckResult, RetrievalMode


def test_fixture_ui_adapter_selects_a_bound_question(tmp_path) -> None:
    run = execute_fixture_run("What is acceleration?", StudentLevel.BEGINNER)

    session = build_fixture_session(run, event_directory=tmp_path)

    assert session.retrieval.mode is RetrievalMode.FIXTURE
    assert session.retrieval.provenance is not None
    assert session.retrieval.provenance.corpus_version == FIXTURE_CORPUS_VERSION
    assert session.retrieval.provenance.corpus_hash == FIXTURE_CORPUS_HASH
    assert session.validated.citation_status == "passed"
    assert session.release is not None
    assert session.release.question.topic_id == "motion"
    assert session.release.binding.bindings[0].chunk_ids == (
        session.retrieval.hits[0].chunk_id,
    )


def test_fixture_ui_adapter_submits_and_replays_state(tmp_path) -> None:
    run = execute_fixture_run("What is acceleration?", StudentLevel.BEGINNER)
    session = build_fixture_session(run, event_directory=tmp_path)

    grade, state = session.submit(
        selected_choice="A",
        attempt_id="attempt-ui-1",
        event_id="event-ui-1",
    )

    assert grade.result is ConceptCheckResult.CORRECT
    assert state.state_version == 1
    assert state.topics["motion"].total_attempts == 1
    assert state.topics["motion"].correct_attempts == 1


def test_fixture_ui_adapter_records_skip_without_topic_score(tmp_path) -> None:
    run = execute_fixture_run("What is acceleration?", StudentLevel.INTERMEDIATE)
    session = build_fixture_session(run, event_directory=tmp_path)

    grade, state = session.submit(
        selected_choice=None,
        attempt_id="attempt-ui-skip",
        event_id="event-ui-skip",
    )

    assert grade.result is ConceptCheckResult.SKIPPED
    assert state.state_version == 1
    assert state.topics == {}


def test_fixture_ui_adapter_can_record_a_new_attempt_for_the_displayed_question(tmp_path) -> None:
    run = execute_fixture_run("What is acceleration?", StudentLevel.BEGINNER)
    first_session = build_fixture_session(run, event_directory=tmp_path)
    assert first_session.release is not None
    release = first_session.release

    first_session.submit(
        selected_choice="C",
        attempt_id="attempt-ui-wrong",
        event_id="event-ui-wrong",
        release=release,
    )
    retry_session = build_fixture_session(run, event_directory=tmp_path)
    assert retry_session.release is None

    grade, state = retry_session.submit(
        selected_choice="A",
        attempt_id="attempt-ui-retry",
        event_id="event-ui-retry",
        release=release,
    )

    assert grade.result is ConceptCheckResult.CORRECT
    assert state.topics["motion"].total_attempts == 2
    assert state.topics["motion"].correct_attempts == 1


def test_fixture_ui_adapter_does_not_offer_question_after_abstention(tmp_path) -> None:
    run = execute_fixture_run(
        "What is quantum entanglement in condensed matter?",
        StudentLevel.ADVANCED,
    )

    session = build_fixture_session(run, event_directory=tmp_path)

    assert session.validated.abstained is True
    assert session.release is None
