from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest

from cs30.concept_check.fixtures import load_fixture_scenarios
from cs30.concept_check.topics import ChunkTopicResolver
from cs30.ui.concept_check_demo import (
    _render_session_report,
    build_demo_runtime,
    override_demo_level,
    record_demo_attempt,
    revoke_demo_attempt,
    select_demo_question,
    select_demo_question_result,
)
from cs30.v2.contracts import (
    ConceptCheckEventType,
    ConceptCheckResult,
    StudentLevel,
    StudentProfile,
)


def _page() -> Path:
    return Path(__file__).parents[1] / "src" / "cs30" / "ui" / "pages" / "1_Concept_Check_Demo.py"


def _scenario(scenario_id: str):
    return next(
        scenario for scenario in load_fixture_scenarios() if scenario.scenario_id == scenario_id
    )


def test_demo_runtime_uses_shared_fixtures_and_m7_service(tmp_path) -> None:
    profile = StudentProfile(profile_id="fixture-ui-student", level=StudentLevel.BEGINNER)
    runtime = build_demo_runtime(
        event_directory=tmp_path,
        profile=profile,
        scenario=_scenario("acceleration"),
    )

    selection = select_demo_question(runtime)
    assert selection.status == "offered"
    release = selection.question

    assert release is not None
    assert isinstance(runtime.service.resolver, ChunkTopicResolver)
    assert release.question.question_id == "cc-fixture-001"
    result = record_demo_attempt(runtime, release, "A")
    assert result.grade.result is ConceptCheckResult.CORRECT
    assert result.event.attempt_id == result.grade.attempt_id
    assert result.previous_state.topics == {}
    assert result.learner_state.topics["acceleration"].total_attempts == 1


def test_disabled_demo_returns_static_selection_and_writes_no_event(tmp_path) -> None:
    profile = StudentProfile(profile_id="fixture-disabled", level=StudentLevel.INTERMEDIATE)
    runtime = build_demo_runtime(
        event_directory=tmp_path,
        profile=profile,
        scenario=_scenario("acceleration"),
        enabled=False,
    )

    selection = select_demo_question_result(runtime)

    assert selection.status == "disabled"
    assert selection.question is None
    assert runtime.event_store.events(profile.profile_id) == ()


def test_demo_controls_revoke_and_override_through_shared_service(tmp_path) -> None:
    profile = StudentProfile(profile_id="fixture-controls", level=StudentLevel.BEGINNER)
    runtime = build_demo_runtime(
        event_directory=tmp_path,
        profile=profile,
        scenario=_scenario("acceleration"),
    )
    release = select_demo_question(runtime)
    assert release is not None
    attempt = record_demo_attempt(runtime, release, "C")

    revoked_state = revoke_demo_attempt(runtime, attempt.event.attempt_id)
    assert revoked_state.topics["acceleration"].total_attempts == 0
    assert runtime.event_store.events(profile.profile_id)[-1].event_type is (
        ConceptCheckEventType.ATTEMPT_REVOKED
    )

    overridden = override_demo_level(
        runtime,
        "acceleration",
        StudentLevel.ADVANCED,
        "I have studied this topic before.",
    )
    assert overridden.topics["acceleration"].level is StudentLevel.ADVANCED
    control_event = runtime.event_store.events(profile.profile_id)[-1]
    assert control_event.event_type is ConceptCheckEventType.TOPIC_LEVEL_OVERRIDDEN
    assert control_event.reason == "I have studied this topic before."


def test_demo_page_hides_feedback_until_submit() -> None:
    app = AppTest.from_file(_page()).run()

    assert not app.exception
    assert "NOT REAL PRACTICE QUESTIONS" in app.warning[0].value
    assert not app.radio
    next(button for button in app.button if button.label == "Quiz me").click().run()

    assert not app.exception
    assert len(app.radio) == 1
    assert not any("Correct answer" in item.value for item in app.markdown)
    assert not any("The evidence defines acceleration" in item.value for item in app.markdown)

    app.radio[0].set_value("C").run()
    next(button for button in app.button if button.label == "Submit answer").click().run()

    assert not app.exception
    assert any("Correct" in item.value for item in app.success)
    assert not app.radio
    assert any("Explanation" in item.value for item in app.markdown)
    assert any("Evidence" in item.value for item in app.markdown)
    assert any("Learner state change" in item.value for item in app.markdown)
    assert any("Textbook: College Physics 2e" in item.value for item in app.caption)
    assert any(expander.label == "Attempt record" for expander in app.expander)
    assert any(button.label == "Undo latest scored attempt" for button in app.button)
    assert any("Current session report" in item.value for item in app.markdown)
    assert any(
        'cc-report-label">Submitted' in item.value and 'cc-report-value">1' in item.value
        for item in app.markdown
    )
    assert len(app.get("download_button")) == 3
    assert any(button.label == "Next question" for button in app.button)


def test_demo_page_skip_is_recorded_but_not_scored() -> None:
    app = AppTest.from_file(_page()).run()
    next(button for button in app.button if button.label == "Quiz me").click().run()
    next(button for button in app.button if button.label == "Skip").click().run()

    assert not app.exception
    assert any("not counted" in item.value for item in app.warning)
    assert any("Correct answer" in item.value for item in app.markdown)
    assert any(
        'Scored attempts</span><span class="cc-state-value">0 → 0' in item.value
        for item in app.markdown
    )
    assert any(expander.label == "Attempt record" for expander in app.expander)
    assert all(button.label != "Undo latest scored attempt" for button in app.button)
    assert all(button.label != "Answer now" for button in app.button)


def test_demo_page_wrong_answer_is_final_after_feedback_is_revealed() -> None:
    app = AppTest.from_file(_page()).run()
    next(button for button in app.button if button.label == "Quiz me").click().run()
    app.radio[0].set_value("D").run()
    next(button for button in app.button if button.label == "Submit answer").click().run()

    assert any("Incorrect" in item.value for item in app.error)
    assert not app.radio
    assert all(button.label != "Try again" for button in app.button)
    assert any(
        'Scored attempts</span><span class="cc-state-value">0 → 1' in item.value
        for item in app.markdown
    )


def test_demo_page_next_question_selects_an_unused_release() -> None:
    app = AppTest.from_file(_page()).run()
    next(button for button in app.button if button.label == "Quiz me").click().run()
    first_question = next(item.value for item in app.markdown if "According to" in item.value)
    app.radio[0].set_value("C").run()
    next(button for button in app.button if button.label == "Submit answer").click().run()

    next(button for button in app.button if button.label == "Next question").click().run()

    assert not app.exception
    assert len(app.radio) == 1
    assert not any("Correct answer" in item.value for item in app.markdown)
    assert not any(item.value == first_question for item in app.markdown)


@pytest.mark.parametrize(
    "scenario_id, code, reason",
    [
        ("topic-tie", "TOPIC_TIE", "more than one topic equally"),
        ("unmapped-chunk", "NO_TOPIC_AVAILABLE", "no assigned topic"),
    ],
)
def test_demo_page_handles_scenarios_without_an_eligible_topic(scenario_id, code, reason) -> None:
    app = AppTest.from_file(_page()).run()
    app.selectbox[1].set_value(scenario_id).run()
    next(button for button in app.button if button.label == "Quiz me").click().run()

    assert not app.exception
    assert not app.radio
    assert any(reason in item.value for item in app.info)
    trace = app.session_state["concept_check_demo_selection_trace"]
    assert trace["status"] == "no_topic_available"
    assert trace["error_code"] == code


def test_demo_page_toggle_disables_quiz_and_event_controls() -> None:
    app = AppTest.from_file(_page()).run()
    app.toggle[0].set_value(False).run()

    assert not app.exception
    assert all(button.label != "Quiz me" for button in app.button)
    assert all(button.label != "Undo latest scored attempt" for button in app.button)
    assert all(button.label != "Change Topic level" for button in app.button)
    assert all(
        expander.label != "Adjust current Topic level (optional)" for expander in app.expander
    )
    assert any("static student profile" in item.value for item in app.caption)
    assert any("event recording are disabled" in item.value for item in app.info)


def test_demo_page_view_evidence_control_reveals_source_chunks() -> None:
    app = AppTest.from_file(_page()).run()
    assert all(expander.label != "Cited evidence used by the scenario" for expander in app.expander)

    app.toggle[1].set_value(True).run()

    assert not app.exception
    assert any(expander.label == "Cited evidence used by the scenario" for expander in app.expander)


def test_demo_page_revoke_control_updates_the_report() -> None:
    app = AppTest.from_file(_page()).run()
    next(button for button in app.button if button.label == "Quiz me").click().run()
    app.radio[0].set_value("C").run()
    next(button for button in app.button if button.label == "Submit answer").click().run()

    undo = next(button for button in app.button if button.label == "Undo latest scored attempt")
    undo.click().run()

    assert not app.exception
    assert any("was undone" in item.value for item in app.success)
    assert any(
        'cc-report-label">Revoked' in item.value
        and 'cc-report-value">1' in item.value
        for item in app.markdown
    )


def test_demo_page_level_override_requires_reason_and_updates_state() -> None:
    app = AppTest.from_file(_page()).run()
    assert any(
        expander.label == "Adjust current Topic level (optional)" for expander in app.expander
    )
    assert not any(item.value == "### Student controls" for item in app.markdown)
    next(item for item in app.selectbox if item.label == "New level").set_value("advanced").run()
    next(item for item in app.text_input if item.label == "Reason for level change").set_value(
        "I completed this Topic before."
    ).run()

    next(button for button in app.button if button.label == "Change Topic level").click().run()

    assert not app.exception
    assert any("was changed to advanced" in item.value for item in app.success)
    assert any("| Acceleration | advanced | 0.500 | 0 |" in item.value for item in app.markdown)


def test_demo_page_two_block_advanced_selects_the_advanced_question() -> None:
    app = AppTest.from_file(_page()).run()
    app.selectbox[0].set_value("advanced").run()
    app.selectbox[1].set_value("two-block-system").run()
    next(button for button in app.button if button.label == "Quiz me").click().run()

    assert not app.exception
    assert len(app.radio) == 1
    assert any("Two blocks of 2 kg and 4 kg" in item.value for item in app.markdown)


def test_session_report_failure_isolated_from_the_quiz(monkeypatch, tmp_path) -> None:
    warnings: list[str] = []

    class StubStreamlit:
        @staticmethod
        def divider() -> None:
            return None

        @staticmethod
        def markdown(_value: str) -> None:
            return None

        @staticmethod
        def caption(_value: str) -> None:
            return None

        @staticmethod
        def warning(value: str) -> None:
            warnings.append(value)

    def fail(_event_directory: Path) -> None:
        raise OSError("broken report")

    monkeypatch.setattr("cs30.ui.concept_check_demo.st", StubStreamlit())
    monkeypatch.setattr("cs30.ui.concept_check_demo._render_session_report_contents", fail)

    _render_session_report(tmp_path)

    assert warnings == ["The session report is temporarily unavailable. The quiz remains usable."]
