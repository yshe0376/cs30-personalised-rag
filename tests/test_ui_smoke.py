from pathlib import Path

from streamlit.testing.v1 import AppTest

from cs30.contracts import StudentLevel
from cs30.ui.app import execute_fixture_run


def test_ui_adapter_consumes_pipeline_run() -> None:
    result = execute_fixture_run("What is acceleration?", StudentLevel.BEGINNER)

    assert result.mode == "fixture"
    assert result.profile.level is StudentLevel.BEGINNER
    assert result.answer.abstained is False
    assert result.citation_integrity == "passed"


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
    assert app.success[0].value == "Smoke path completed"
    assert "FIXTURE" in app.info[0].value
