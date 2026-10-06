from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest

from cs30.ui.concept_check_demo import (
    SCENARIOS,
    build_demo_runtime,
    record_demo_attempt,
    select_demo_question,
)
from cs30.v2.contracts import ConceptCheckResult, StudentLevel, StudentProfile


def _page() -> Path:
    return (
        Path(__file__).parents[1]
        / "src"
        / "cs30"
        / "ui"
        / "pages"
        / "1_Concept_Check_Demo.py"
    )


def test_demo_runtime_uses_shared_fixtures_and_m7_service(tmp_path) -> None:
    profile = StudentProfile(profile_id="fixture-ui-student", level=StudentLevel.BEGINNER)
    runtime = build_demo_runtime(
        event_directory=tmp_path,
        profile=profile,
        scenario=SCENARIOS["Acceleration definition"],
    )

    release = select_demo_question(runtime)

    assert release is not None
    assert release.question.question_id == "cc-fixture-001"
    result = record_demo_attempt(runtime, release, "A")
    assert result.grade.result is ConceptCheckResult.CORRECT
    assert result.event.attempt_id == result.grade.attempt_id
    assert result.previous_state.topics == {}
    assert result.learner_state.topics["acceleration"].total_attempts == 1


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

    app.radio[0].set_value("A").run()
    next(button for button in app.button if button.label == "Submit answer").click().run()

    assert not app.exception
    assert any("Correct" in item.value for item in app.success)
    assert not app.radio
    assert any("Explanation" in item.value for item in app.markdown)
    assert any("Evidence" in item.value for item in app.markdown)
    assert any("Learner state change" in item.value for item in app.markdown)
    assert any("Textbook: College Physics 2e" in item.value for item in app.caption)
    assert any(expander.label == "Attempt record" for expander in app.expander)


def test_demo_page_skip_is_recorded_but_not_scored() -> None:
    app = AppTest.from_file(_page()).run()
    next(button for button in app.button if button.label == "Quiz me").click().run()
    next(button for button in app.button if button.label == "Skip").click().run()

    assert not app.exception
    assert any("not counted" in item.value for item in app.warning)
    assert any("Correct answer" in item.value for item in app.markdown)
    assert any(
        "Scored attempts</span><span class=\"cc-state-value\">0 → 0" in item.value
        for item in app.markdown
    )
    assert any(expander.label == "Attempt record" for expander in app.expander)


def test_demo_page_wrong_answer_can_retry_without_rewriting_attempt() -> None:
    app = AppTest.from_file(_page()).run()
    next(button for button in app.button if button.label == "Quiz me").click().run()
    app.radio[0].set_value("D").run()
    next(button for button in app.button if button.label == "Submit answer").click().run()

    assert any("Incorrect" in item.value for item in app.error)
    assert not app.radio
    next(button for button in app.button if button.label == "Try again").click().run()
    assert len(app.radio) == 1

    app.radio[0].set_value("A").run()
    next(button for button in app.button if button.label == "Submit answer").click().run()

    assert not app.exception
    assert any("Correct" in item.value for item in app.success)
    assert any(
        "Scored attempts</span><span class=\"cc-state-value\">1 → 2" in item.value
        for item in app.markdown
    )
