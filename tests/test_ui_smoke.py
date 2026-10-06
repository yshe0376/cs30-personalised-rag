from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest

from cs30.contracts import StudentLevel
from cs30.ui.app import execute_fixture_run


def test_ui_adapter_consumes_pipeline_run() -> None:
    result = execute_fixture_run("What is acceleration?", StudentLevel.BEGINNER)

    assert result.mode == "fixture"
    assert result.profile.level is StudentLevel.BEGINNER
    assert result.answer.abstained is False
    assert result.citation_integrity == "passed"
    assert result.evidence_bundle is not None
    assert result.validated_answer is not None
    assert result.trace["request_id"] == result.run_id


def test_ui_surfaces_an_abstained_answer() -> None:
    result = execute_fixture_run(
        "What is quantum entanglement in condensed matter?",
        StudentLevel.ADVANCED,
    )

    assert result.mode == "fixture"
    assert result.answer.abstained is True
    assert result.retrieval.hits == []


def test_streamlit_smoke_path() -> None:
    app_path = Path(__file__).parents[1] / "src" / "cs30" / "ui" / "app.py"
    app = AppTest.from_file(app_path).run()

    assert not app.exception
    app.selectbox[0].select("beginner")
    app.text_area[0].set_value("What is acceleration?")
    app.button[0].click().run()

    assert not app.exception
    assert any("Generated answer" in item.value for item in app.markdown)
    assert any("Source:" in item.value for item in app.caption)
    assert "FIXTURE" in app.info[0].value
    assert any(button.label == "Quiz me" for button in app.button)
    assert not app.radio


def test_streamlit_concept_check_fixture_path() -> None:
    app_path = Path(__file__).parents[1] / "src" / "cs30" / "ui" / "app.py"
    app = AppTest.from_file(app_path).run()

    app.selectbox[0].select("beginner")
    app.text_area[0].set_value("What is acceleration?")
    next(button for button in app.button if button.label == "Run pipeline").click().run()
    next(button for button in app.button if button.label == "Quiz me").click().run()

    assert not app.exception
    assert any("Quick check" in item.value for item in app.markdown)
    app.radio[0].set_value("A").run()
    next(button for button in app.button if button.label == "Submit answer").click().run()

    assert not app.exception
    assert any("Correct" in item.value for item in app.success)
    assert any("Quiz result" in item.value for item in app.markdown)
    assert any("Scored attempts" in item.value for item in app.markdown)
    assert any("Learner state" in item.value for item in app.markdown)
    assert any(expander.label == "Attempt record" for expander in app.expander)
    assert not app.radio


def test_streamlit_incorrect_answer_can_start_a_new_attempt() -> None:
    app_path = Path(__file__).parents[1] / "src" / "cs30" / "ui" / "app.py"
    app = AppTest.from_file(app_path).run()

    app.selectbox[0].select("beginner")
    app.text_area[0].set_value("What is acceleration?")
    next(button for button in app.button if button.label == "Run pipeline").click().run()
    next(button for button in app.button if button.label == "Quiz me").click().run()
    app.radio[0].set_value("C").run()
    next(button for button in app.button if button.label == "Submit answer").click().run()

    assert not app.exception
    assert any("Incorrect" in item.value for item in app.error)
    assert not app.radio

    next(button for button in app.button if button.label == "Try again").click().run()
    assert not app.exception
    assert len(app.radio) == 1

    app.radio[0].set_value("A").run()
    next(button for button in app.button if button.label == "Submit answer").click().run()

    assert not app.exception
    assert any("Correct" in item.value for item in app.success)
    assert any(
        "Scored attempts</span><span class=\"cs30-state-value\">2" in item.value
        for item in app.markdown
    )
