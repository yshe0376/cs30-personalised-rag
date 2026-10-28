"""Behavioural checks for the V2 layout over existing shared fixtures."""

from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest

PAGE = Path(__file__).parents[1] / "src/cs30/ui/v2_app.py"


def button(app, label):
    return next(item for item in app.button if item.label == label)


def start_practice():
    app = AppTest.from_file(PAGE, default_timeout=15).run()
    app.toggle[0].set_value(True).run()
    next(item for item in app.selectbox if item.label == "Demo scenario").set_value(
        "acceleration"
    ).run()
    button(app, "Quiz me").click().run()
    return app


def test_initial_page_is_explicitly_fixture_and_opted_out():
    app = AppTest.from_file(PAGE, default_timeout=15).run()
    assert not app.exception
    assert app.toggle[0].value is False
    assert "TEST DATA" in app.warning[0].value
    assert not app.radio
    assert all(item.label != "Change Topic level" for item in app.button)
    assert any("does not regenerate" in item.value for item in app.caption)
    assert len(app.sidebar.selectbox) == 2


def test_submit_feedback_and_undo_use_shared_state_and_reports():
    app = start_practice()
    assert not any("Correct answer" in item.value for item in app.markdown)
    app.radio[0].set_value("A").run()
    button(app, "Submit answer").click().run()
    assert not app.exception
    assert not app.radio
    assert any("Correct answer" in item.value for item in app.markdown)
    button(app, "Undo latest scored attempt").click().run()
    assert not app.exception
    assert any("was undone" in item.value for item in app.success)
    assert any('cc-report-label">Revoked' in item.value for item in app.markdown)


def test_skip_has_no_scored_attempt_or_undo():
    app = start_practice()
    button(app, "Skip").click().run()
    assert not app.exception
    assert any("not counted" in item.value for item in app.warning)
    assert all(item.label != "Undo latest scored attempt" for item in app.button)


def test_disabling_hides_controls_and_restores_history_on_reenable():
    app = start_practice()
    app.radio[0].set_value("A").run()
    button(app, "Submit answer").click().run()
    app.toggle[0].set_value(False).run()
    assert not app.exception
    assert all(item.label != "Quiz me" for item in app.button)
    assert all(item.label != "Change Topic level" for item in app.button)
    assert any("| Acceleration | beginner | 0.500 | 0 |" in x.value for x in app.markdown)
    app.toggle[0].set_value(True).run()
    assert not app.exception
    assert any("| Acceleration | beginner | 0.600 | 1 |" in x.value for x in app.markdown)


def test_override_requires_reason_and_does_not_rewrite_fixture_answer():
    app = start_practice()
    button(app, "Change Topic level").click().run()
    assert any("A reason is required" in x.value for x in app.error)
    next(x for x in app.selectbox if x.label == "New level").set_value("advanced").run()
    app.text_input[0].set_value("I studied this topic before.").run()
    button(app, "Change Topic level").click().run()
    assert not app.exception
    assert any("| Acceleration | advanced | 0.500 | 0 |" in x.value for x in app.markdown)
    assert any("does not regenerate" in x.value for x in app.caption)
    assert not app.radio


@pytest.mark.parametrize("scenario", ["topic-tie", "unmapped-chunk"])
def test_unresolved_topic_has_reason_and_no_fabricated_question(scenario):
    app = start_practice()
    next(x for x in app.selectbox if x.label == "Demo scenario").set_value(scenario).run()
    button(app, "Quiz me").click().run()
    assert not app.exception
    assert not app.radio
    assert any("No eligible" in x.value for x in app.info)


def test_scenario_change_clears_visible_attempt_without_losing_report():
    app = start_practice()
    app.radio[0].set_value("A").run()
    button(app, "Submit answer").click().run()
    next(x for x in app.selectbox if x.label == "Demo scenario").set_value(
        "newtons-second-law"
    ).run()
    assert not app.exception
    assert not app.radio
    assert all(x.label != "Undo latest scored attempt" for x in app.button)
    assert len(app.get("download_button")) == 3
