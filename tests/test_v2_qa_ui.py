"""Free-text UI and shared V2 chain regression, with no paid model calls."""

from dataclasses import replace
from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest

from cs30.generation.client import MockJsonLLMClient
from cs30.ui import v2_runtime
from cs30.ui.v2_runtime import UiBm25Retriever, load_ui_corpus, run_question
from cs30.v2.contracts import StudentLevel, StudentProfile

ROOT = Path(__file__).parents[1]
PAGE = ROOT / "src/cs30/ui/qa_app.py"


def dataset():
    return load_ui_corpus(None, ROOT, synthetic=True)


def profile():
    return StudentProfile(profile_id="qa-test", level=StudentLevel.BEGINNER)


def test_typed_question_runs_shared_bm25_generation_validation_and_practice(tmp_path):
    corpus = dataset()
    retriever = UiBm25Retriever(corpus, tmp_path / "index")
    run = run_question(
        "What is average acceleration?",
        profile(),
        corpus,
        retriever,
        tmp_path,
        enabled=True,
        live=False,
    )
    assert run.runtime.retrieval.query == "What is average acceleration?"
    assert run.runtime.validated.citation_status == "passed"
    assert len(run.steps) == 6
    assert run.prepared.retrieval_topic.topic_id == "acceleration"
    selection = run.runtime.service.select(
        run.prepared, run.runtime.retrieval, run.runtime.validated
    )
    assert selection.status == "offered"
    assert selection.question.question.topic_id == "acceleration"
    assert set(run.runtime.validated.resolved_citations) <= set(run.bundle.citation_map.values())


def test_empty_retrieval_abstains_without_calling_client(tmp_path):
    class NoCalls:
        model = "no-call"
        temperature = 0

        def complete(self, *args):
            raise AssertionError("No evidence must cause no call")

    corpus = dataset()
    run = run_question(
        "quasizzz",
        profile(),
        corpus,
        UiBm25Retriever(corpus, tmp_path / "index"),
        tmp_path,
        enabled=False,
        live=False,
        client=NoCalls(),
    )
    assert run.runtime.validated.abstained
    assert run.runtime.validated.citation_status == "skipped"
    assert not run.trace.attempts


def test_blank_input_fails_before_client_or_retrieval(tmp_path):
    with pytest.raises(ValueError, match="Enter a physics question"):
        run_question(" ", profile(), dataset(), None, tmp_path, enabled=False, live=False)


def test_team_model_cannot_be_mixed_with_fixture_corpus(tmp_path):
    with pytest.raises(ValueError, match="real V2 corpus"):
        run_question("force", profile(), dataset(), None, tmp_path, enabled=False, live=True)


def test_topic_override_changes_next_generation_snapshot(tmp_path):
    corpus = dataset()
    retriever = UiBm25Retriever(corpus, tmp_path / "index")
    first = run_question(
        "What is average acceleration?",
        profile(),
        corpus,
        retriever,
        tmp_path,
        enabled=True,
        live=False,
    )
    first.runtime.service.override_level(
        "acceleration", StudentLevel.ADVANCED, reason="Prior course", event_id="override-1"
    )
    second = run_question(
        "What is average acceleration?",
        profile(),
        corpus,
        retriever,
        tmp_path,
        enabled=True,
        live=False,
    )
    assert first.prepared.snapshot.profile.level is StudentLevel.BEGINNER
    assert second.trace.effective_level is StudentLevel.ADVANCED
    disabled = run_question(
        "What is average acceleration?",
        profile(),
        corpus,
        retriever,
        tmp_path,
        enabled=False,
        live=False,
    )
    assert disabled.trace.effective_level is StudentLevel.BEGINNER


def test_real_corpus_provider_never_offers_fixture_questions(tmp_path):
    corpus = replace(dataset(), synthetic=False)
    run = run_question(
        "What is average acceleration?",
        profile(),
        corpus,
        UiBm25Retriever(corpus, tmp_path / "index"),
        tmp_path,
        enabled=True,
        live=True,
        client=MockJsonLLMClient(),
    )
    result = run.runtime.service.select(run.prepared, run.runtime.retrieval, run.runtime.validated)
    assert result.error_code.value == "NO_USABLE_QUESTION"
    assert result.question is None


def test_missing_team_key_does_not_construct_provider(monkeypatch, tmp_path):
    monkeypatch.delenv("DEEPINFRA_API_KEY", raising=False)
    monkeypatch.setattr(
        v2_runtime, "OpenAICompatibleClient", lambda *a, **k: pytest.fail("provider constructed")
    )
    with pytest.raises(ValueError, match="DEEPINFRA_API_KEY"):
        v2_runtime.team_client(tmp_path, "run-1")


@pytest.mark.parametrize(
    "model, output_format, tokens, extra_body",
    [
        ("openai/gpt-oss-20b", "json_object", 4096, {"reasoning_effort": "low"}),
        ("google/gemma-3-12b-it", "json_schema", 2048, {}),
        ("meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo", "json_object", 2048, {}),
    ],
)
def test_team_client_reuses_m7_settings_and_bounds_ui_requests(
    monkeypatch, tmp_path, model, output_format, tokens, extra_body
):
    recorded = {}

    class Client:
        def __init__(self, model, **settings):
            recorded.update(settings, model=model)

        def configure_run(self, directory):
            recorded["directory"] = directory

        def for_cell(self, run_id, cache):
            recorded.update(run_id=run_id, cache=cache)
            return self

    monkeypatch.setenv("DEEPINFRA_API_KEY", "offline-test-placeholder")
    monkeypatch.setattr(v2_runtime, "OpenAICompatibleClient", Client)
    v2_runtime.team_client(tmp_path, "run-1", model)
    assert recorded["model"] == model
    assert recorded["base_url"] == "https://api.deepinfra.com/v1/openai"
    assert recorded["structured_output"] == output_format
    assert recorded["max_output_tokens"] == tokens
    assert recorded["extra_body"] == extra_body
    assert recorded["max_api_requests"] == 2
    assert recorded["transport_retries"] == 0


def test_provider_failure_does_not_substitute_an_answer(tmp_path):
    class BrokenClient:
        model = "broken-offline-provider"
        temperature = 0

        def complete(self, *args):
            raise RuntimeError("offline transport failure")

    from cs30.v2.generation import V2GenerationFailure

    corpus = dataset()
    with pytest.raises(V2GenerationFailure):
        run_question(
            "What is average acceleration?",
            profile(),
            corpus,
            UiBm25Retriever(corpus, tmp_path / "index"),
            tmp_path,
            enabled=False,
            live=False,
            client=BrokenClient(),
        )


def app_button(app, name):
    return next(x for x in app.button if x.label == name)


def offline_page(monkeypatch):
    monkeypatch.delenv("DEEPINFRA_API_KEY", raising=False)
    app = AppTest.from_file(PAGE, default_timeout=20).run()
    next(x for x in app.selectbox if x.label == "Demo mode").set_value(
        "Offline integration · simulated answers"
    ).run()
    return app


def test_main_page_has_free_text_input_and_live_readiness(monkeypatch):
    monkeypatch.delenv("DEEPINFRA_API_KEY", raising=False)
    app = AppTest.from_file(ROOT / "src/cs30/ui/v2_app.py", default_timeout=20).run()
    assert not app.exception
    assert app.text_area[0].label == "Your physics question"
    assert app_button(app, "Generate answer").disabled


def test_question_to_quiz_to_report_and_switch_preserves_history(monkeypatch):
    app = offline_page(monkeypatch)
    app.toggle[0].set_value(True).run()
    app.text_area[0].set_value("What is average acceleration?").run()
    app_button(app, "Run offline pipeline").click().run()
    assert not app.exception
    assert app.session_state["qa-run"].runtime.retrieval.query == "What is average acceleration?"
    app_button(app, "Quiz me").click().run()
    assert not app.exception
    assert len(app.radio) == 1
    app.radio[0].set_value("A").run()
    app_button(app, "Submit answer").click().run()
    assert not app.exception
    assert len(app.get("download_button")) == 3
    app.toggle[0].set_value(False).run()
    assert not app.exception
    assert all(x.label != "Quiz me" for x in app.button)
    app.toggle[0].set_value(True).run()
    assert not app.exception
    assert any("Scored attempts: 1" in x.value for x in app.caption)


def test_changed_question_clears_old_output_when_new_run_fails(monkeypatch):
    app = offline_page(monkeypatch)
    app_button(app, "Run offline pipeline").click().run()
    app.text_area[0].set_value("").run()
    app_button(app, "Run offline pipeline").click().run()
    assert not app.exception
    assert any("pipeline stopped" in x.value for x in app.error)
    assert "qa-run" not in app.session_state


def test_example_populates_the_input_before_next_run(monkeypatch):
    app = offline_page(monkeypatch)
    assert all(x.label != "Prepared examples" for x in app.selectbox)
    assert all(x.label != "Use example" for x in app.button)
    for label in ["Acceleration", "Newton's second law", "Out of scope"]:
        assert app_button(app, label)
    app_button(app, "Newton's second law").click().run()
    assert not app.exception
    assert "net force" in app.text_area[0].value
    assert "qa-run" not in app.session_state


def test_three_independent_model_choices_change_banner_without_calls(monkeypatch):
    monkeypatch.delenv("DEEPINFRA_API_KEY", raising=False)
    app = AppTest.from_file(PAGE, default_timeout=20).run()
    selector = next(x for x in app.selectbox if x.label == "Answer model")
    assert len(selector.options) == 3
    selector.set_value("google/gemma-3-12b-it").run()
    assert not app.exception
    assert any("Gemma 3 12B" in x.value for x in app.info)
    assert app_button(app, "Generate answer").disabled
    assert "qa-run" not in app.session_state
