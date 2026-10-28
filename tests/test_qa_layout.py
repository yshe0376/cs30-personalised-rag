"""Feature-parity checks for the V3 preview page; no paid model calls.

Each V2 page behaviour (tests/test_v2_qa_ui.py in cs30-v2-ui-local) is repeated here
against the V3 layout, plus checks for the new presentation pieces.
"""

from dataclasses import replace
from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest

from cs30.v2.contracts import StudentLevel

ROOT = Path(__file__).parents[1]
PAGE = ROOT / "src/cs30/ui/qa_app.py"
ENTRY = ROOT / "src/cs30/ui/v2_app.py"
FIXTURE = "Fixture mode · offline, no API key"


def app_button(app, name):
    return next(x for x in app.button if x.label == name)


def markdown_with(app, text):
    """Rendered markdown containing ``text``; the page's <style> blocks are skipped."""

    return [
        x.value
        for x in app.markdown
        if text in x.value and not x.value.lstrip().startswith("<style")
    ]


def offline_page(monkeypatch):
    monkeypatch.delenv("DEEPINFRA_API_KEY", raising=False)
    return AppTest.from_file(PAGE, default_timeout=30).run()


def answered_page(monkeypatch, *, concept_check=True):
    app = offline_page(monkeypatch)
    if concept_check:
        app.toggle[0].set_value(True).run()
    app_button(app, "Generate answer · fixture").click().run()
    assert not app.exception
    return app


# ---------- same behaviour as V2 ----------


def test_entry_page_defaults_to_visible_fixture_mode_without_key(monkeypatch):
    monkeypatch.delenv("DEEPINFRA_API_KEY", raising=False)
    app = AppTest.from_file(ENTRY, default_timeout=30).run()
    assert not app.exception
    assert app.text_area[0].label == "Your physics question"
    assert app.session_state["qa-demo-settings"]["mode"] == FIXTURE
    assert markdown_with(app, "v3-mode-fixture")  # mode badge next to the title
    assert not app_button(app, "Generate answer · fixture").disabled


def test_live_mode_needs_corpus_and_index_and_never_falls_back(monkeypatch, tmp_path):
    monkeypatch.setenv("DEEPINFRA_API_KEY", "offline-test-placeholder")
    monkeypatch.delenv("CS30_UI_CORPUS", raising=False)
    monkeypatch.setenv("CS30_UI_HYBRID_INDEX", str(tmp_path / "missing"))
    app = AppTest.from_file(PAGE, default_timeout=30).run()
    assert not app.exception
    assert app.session_state["qa-demo-settings"]["mode"] == "Team V2 · DeepInfra"
    assert app.session_state["qa-demo-settings"]["retrieval"] == "hybrid"
    assert any("M6 Qwen3 hybrid index not found" in x.value for x in app.error)
    assert markdown_with(app, "Hybrid retrieval")  # live mode badge names the retriever
    assert app_button(app, "Generate answer").disabled


def test_demo_mode_dialog_models_update_the_mode_badge_without_calls(monkeypatch):
    monkeypatch.delenv("DEEPINFRA_API_KEY", raising=False)
    app = AppTest.from_file(PAGE, default_timeout=30).run()
    app_button(app, "Demo Mode").click().run()
    next(x for x in app.selectbox if x.label == "Demo mode").set_value("Team V2 · DeepInfra").run()
    selector = next(x for x in app.selectbox if x.label == "Answer model")
    assert len(selector.options) == 3
    selector.set_value("google/gemma-3-12b-it").run()
    app_button(app, "Done").click().run()
    assert not app.exception
    assert markdown_with(app, "Gemma 3 12B")
    assert app_button(app, "Generate answer").disabled
    assert "qa-run" not in app.session_state
    app_button(app, "Demo Mode").click().run()  # settings survive closing the dialog
    assert (
        next(x for x in app.selectbox if x.label == "Answer model").value == "google/gemma-3-12b-it"
    )
    app_button(app, "Done").click().run()


def test_starting_level_and_concept_check_sit_on_the_main_page(monkeypatch):
    app = offline_page(monkeypatch)
    level = next(x for x in app.selectbox if x.label == "Starting level")
    assert level.value is StudentLevel.BEGINNER
    assert app.toggle[0].label == "Enable Concept Check"
    assert markdown_with(app, "v3-field-title")
    assert not app.sidebar.selectbox and not app.sidebar.toggle  # sidebar is the report only


def test_example_pills_fill_the_question_without_running(monkeypatch):
    app = offline_page(monkeypatch)
    examples = app.pills[0]
    assert list(examples.options) == ["Acceleration", "Newton's second law", "Out of scope"]
    examples.set_value("Newton's second law").run()
    assert not app.exception
    assert "net force" in app.text_area[0].value
    assert "qa-run" not in app.session_state


def test_failed_run_clears_old_output_and_substitutes_nothing(monkeypatch):
    app = answered_page(monkeypatch, concept_check=False)
    app.text_area[0].set_value("").run()
    app_button(app, "Generate answer · fixture").click().run()
    assert not app.exception
    assert any("pipeline stopped" in x.value for x in app.error)
    assert "qa-run" not in app.session_state


def test_question_to_quiz_to_report_and_switch_preserves_history(monkeypatch):
    app = answered_page(monkeypatch)
    assert app.session_state["qa-run"].runtime.retrieval.query == "What is average acceleration?"
    app_button(app, "Quiz me").click().run()
    assert len(app.radio) == 1
    app.radio[0].set_value("A").run()
    app_button(app, "Submit answer").click().run()
    assert not app.exception
    assert app_button(app, "Next question")
    assert app_button(app, "Undo latest scored attempt")
    assert all(x.label != "Quiz me" for x in app.button)  # replaced by Next question
    assert len(app.get("download_button")) == 3  # Session report panel
    app.toggle[0].set_value(False).run()
    assert not app.exception
    assert all(x.label != "Quiz me" for x in app.button)
    app.toggle[0].set_value(True).run()
    scored = '<span class="cc-state-label">Scored attempts</span>'
    assert any(scored + '<span class="cc-state-value">1</span>' in x.value for x in app.markdown)


def test_skip_is_recorded_but_not_scored_and_undo_revokes(monkeypatch):
    app = answered_page(monkeypatch)
    app_button(app, "Quiz me").click().run()
    app_button(app, "Skip").click().run()
    assert not app.exception
    assert any("not counted" in x.value for x in app.warning)
    assert all(x.label != "Undo latest scored attempt" for x in app.button)
    app_button(app, "Next question").click().run()
    app.radio[0].set_value("A").run()
    app_button(app, "Submit answer").click().run()
    app_button(app, "Undo latest scored attempt").click().run()
    assert not app.exception


def test_topic_level_change_needs_a_reason_and_updates_progress(monkeypatch):
    app = answered_page(monkeypatch)
    assert all(x.label != "Adjust this Topic level" for x in app.expander)
    level = next(x for x in app.selectbox if x.label == "New Topic level")
    assert level.value is StudentLevel.BEGINNER
    level.set_value(StudentLevel.ADVANCED).run()
    app_button(app, "Apply Topic level").click().run()
    assert any("reason is required" in x.value for x in app.error)
    next(x for x in app.text_input if x.label == "Reason for level change").input(
        "Prior course"
    ).run()
    app_button(app, "Apply Topic level").click().run()
    assert not app.exception
    assert markdown_with(app, 'Topic level</span><span class="cc-state-value">Advanced</span>')


def test_concept_check_off_keeps_answer_and_explains_how_to_practise(monkeypatch):
    app = answered_page(monkeypatch, concept_check=False)
    assert all(x.label != "Quiz me" for x in app.button)
    assert any("Concept Check is off" in x.value for x in app.caption)
    explanation = app.session_state["qa-run"].runtime.validated.answer.explanation
    assert markdown_with(app, explanation)


def test_session_report_panel_waits_for_a_question(monkeypatch):
    app = offline_page(monkeypatch)
    assert any(x.value == "## Session report" for x in app.markdown)
    assert any("Run a question first" in x.value for x in app.info)
    assert not app.get("download_button")


def test_technical_details_stay_collapsed(monkeypatch):
    app = answered_page(monkeypatch, concept_check=False)
    details = next(x for x in app.expander if x.label == "Technical run details")
    assert details.proto.expanded is False


# ---------- V3 presentation ----------


def test_answer_card_shows_run_settings_as_badges_and_simulated_notice(monkeypatch):
    app = answered_page(monkeypatch, concept_check=False)
    badges = markdown_with(app, "v3-badges")[0]
    assert "Level used · Beginner" in badges
    assert "Citation check · passed" in badges
    assert markdown_with(app, "Simulated answer")


def test_answer_preserves_markdown_blocks_instead_of_escaping_them_into_html(monkeypatch):
    app = answered_page(monkeypatch, concept_check=False)
    run = app.session_state["qa-run"]
    explanation = "A **bold** explanation.\n\n- First step\n- Second step"
    answer = run.runtime.validated.answer.model_copy(update={"explanation": explanation})
    validated = run.runtime.validated.model_copy(update={"answer": answer})
    app.session_state["qa-run"] = replace(
        run, runtime=replace(run.runtime, validated=validated)
    )
    app.run()
    assert not app.exception
    assert any(item.value == explanation for item in app.markdown)


def test_sources_use_book_titles_and_keep_chunk_ids(monkeypatch):
    app = answered_page(monkeypatch, concept_check=False)
    labels = [x.label for x in app.expander if x.label.startswith("E")]
    assert len(labels) == 5
    assert all("College Physics 2e" in label for label in labels)
    assert sum(label.endswith("Cited") for label in labels) >= 1
    run = app.session_state["qa-run"]
    cited = markdown_with(app, "v3-cited-line")[0]
    cited_ids = {
        item.evidence_id
        for item in run.bundle.evidence_items
        if item.chunk_id in set(run.runtime.validated.resolved_citations)
    }
    assert all(evidence_id in cited for evidence_id in cited_ids)
    first_chunk = run.bundle.evidence_items[0].chunk_id
    assert any(first_chunk in x.value for x in app.caption)  # traceable to the chunk


def test_empty_state_explains_what_will_appear(monkeypatch):
    app = offline_page(monkeypatch)
    assert markdown_with(app, "Your answer will appear here")
