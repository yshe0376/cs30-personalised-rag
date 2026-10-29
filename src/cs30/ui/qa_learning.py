"""Unified Streamlit page for the API-backed learning assistant demo."""

from __future__ import annotations

import uuid

import streamlit as st

from cs30.learning.assets import check_learning_setup
from cs30.learning.config import LearningConfig
from cs30.learning.runtime import LearningSetupBlocked, build_learning_runtime
from cs30.ui.learning_views import (
    render_answer,
    render_personalisation_trace,
    render_profile_sidebar,
    render_quiz,
    render_setup_report,
    render_sources,
)
from cs30.ui.math_markdown import format_math_markdown
from cs30.v2.contracts import StudentLevel, StudentProfile


def render_learning_page() -> None:
    """Render inside M8's page shell; the learning runtime owns all online state."""
    try:
        config = LearningConfig.load()
    except (OSError, ValueError) as exc:
        st.error(str(exc))
        st.info(
            "Copy `configs/learning-demo.example.toml` to `configs/learning-demo.toml` and "
            "fill in the local asset paths. Store API keys only in `.env.learning.local`."
        )
        return

    report = check_learning_setup(config)
    with st.expander("Local setup checks", expanded=not report.ready):
        render_setup_report(report)
    st.caption(
        f"Answer model: {config.answer_api.model} · Quiz model: {config.quiz_api.model} · "
        "Qwen3 + BM25 hybrid retrieval with Topic-aware reranking"
    )
    if config.model_selection_status == "provisional":
        st.warning(
            "The API role models are provisional Demo choices supported by M7 Dev. "
            "M7 generation-side "
            "checks are not answer-quality scores, and the formal model selection is not frozen."
        )
    if not report.ready:
        st.info(
            "No API client is created and no request is sent until local assets, offline Topic "
            "preflight, credentials, request cap, and the live API switch all pass."
        )
        return

    runtime = st.session_state.get("learning_runtime")
    if runtime is None:
        initial_level = st.sidebar.selectbox(
            "Starting learner level",
            options=list(StudentLevel),
            format_func=lambda value: value.value,
            key="learning_starting_level",
        )
        st.sidebar.caption(
            "Starting a session loads local retrieval resources only; it does not call a "
            "generation API."
        )
        if st.button("Start learning session", type="primary"):
            profile = StudentProfile(
                profile_id=f"learner-{uuid.uuid4().hex}",
                level=initial_level,
                confidence=1.0,
            )
            try:
                with st.spinner(
                    "Loading the local corpus, Qwen3 embedding model, and retriever. First startup "
                    "may take a minute or two; this step does not call a generation API.",
                    show_time=True,
                ):
                    runtime = build_learning_runtime(config, profile)
            except LearningSetupBlocked as exc:
                st.error(str(exc))
                return
            except Exception as exc:
                st.error(f"Local runtime startup failed: {str(exc)[:500]}")
                return
            st.session_state["learning_runtime"] = runtime
            st.session_state["learning_initial_level"] = initial_level.value
        else:
            return

    initial_level = runtime.static_profile.level
    with st.sidebar.expander("Start a new learner profile"):
        restart_level = st.selectbox(
            "New profile starting level", options=list(StudentLevel),
            index=list(StudentLevel).index(initial_level),
            format_func=lambda value: value.value, key="learning_restart_level",
        )
        st.caption("Starts a separate learner session. Existing history stays saved locally.")
        if st.button("Start new learner session"):
            for key in list(st.session_state):
                if key.startswith("learning_") and key != "learning_restart_level":
                    del st.session_state[key]
            st.session_state["learning_starting_level"] = restart_level
            st.rerun()
    render_profile_sidebar(runtime, initial_level)
    render_session_report(runtime)
    if st.sidebar.button("Undo the latest graded attempt"):
        st.session_state["learning_revoke_request"] = {"event_id": f"revoke-{uuid.uuid4().hex}"}
    revoke_request = st.session_state.pop("learning_revoke_request", None)
    if revoke_request:
        try:
            runtime.revoke_latest_attempt(event_id=revoke_request["event_id"])
        except ValueError as exc:
            st.sidebar.info(str(exc))
        else:
            st.sidebar.success(
                "Attempt undone. The learner profile was recalculated from the remaining events."
            )
            st.rerun()

    override = st.session_state.pop("learning_override", None)
    if override:
        try:
            runtime.override_level(
                override["topic_id"],
                StudentLevel(override["level"]),
                override["reason"],
                event_id=override["event_id"],
            )
        except ValueError as exc:
            st.error(str(exc))
        else:
            st.success(
                "Manual level adjustment saved. Ask the same question again explicitly to generate "
                "an answer using the updated profile."
            )
            st.rerun()

    st.markdown("### Ask a question")
    with st.container(border=True, key="qa-composer"), st.form(
        "learning-question-form", clear_on_submit=False,
    ):
        question = st.text_area(
            "Enter a physics question",
            placeholder=(
                "For example: How do heat and work change internal energy under the first law "
                "of thermodynamics?"
            ),
            height=105,
            key="learning_question_text",
        )
        ask = st.form_submit_button("Ask and view the textbook-grounded answer", type="primary")
    st.caption(
        "An exact repeat reuses the current session's answer. Use the button below to explicitly "
        "ask again with an updated learner profile."
    )
    if ask:
        try:
            turn = runtime.ask(question)
        except ValueError as exc:
            st.error(str(exc))
        else:
            st.session_state["learning_active_turn_id"] = turn.turn_id
            st.rerun()

    turn = runtime.active_turn
    if turn is None:
        st.info("Enter a question to start a learning turn.")
        return

    st.markdown(f"#### Current question: {turn.question}")
    answer_column, sources_column = st.columns([1.7, 1], gap="medium")
    with answer_column, st.container(border=True, key="qa-answer"):
        render_answer(turn, runtime.assets.corpus, show_sources=False)
    with sources_column, st.container(border=True, key="qa-sources"):
        render_sources(turn, runtime.assets.corpus)
    render_personalisation_trace(turn)

    if turn.status == "answered":
        st.markdown("### Practice and feedback")
        st.markdown("#### Concept Check")
        st.caption(
            "Generate up to three multiple-choice questions from the answer's validated textbook "
            "citations. Each quiz includes a textbook-supported answer and explanation and is "
            "graded "
            "locally."
        )
        st.caption(
            "The Demo selects only among approved Topic IDs assigned to citation-validated "
            "evidence. A candidate needs at least one cited chunk assigned to that Topic; chunks "
            "may support several Topics. If several candidates qualify, selection is proportional "
            "to rank-weighted citation support. This online Demo policy is not M7-validated."
        )
        st.caption(
            f"Question author output mode: {config.quiz_api.structured_output}. "
            "Options are validated as four ordered A-D choices, and required rationale and "
            "textbook quotations are located locally; no independent model review is performed."
        )
        if "*" in config.demo_topic_ids:
            st.caption(
                f"All {len(runtime.assets.topic_registry.topics)} registered Topics enabled. "
                "Only Topics mapped to this answer's cited textbook evidence can be selected."
            )
        else:
            st.caption("Enabled Topics: " + ", ".join(config.demo_topic_ids))
        next_index = max(turn.quizzes, default=0) + 1
        previous_view = turn.quizzes.get(next_index - 1)
        can_create = next_index <= 3 and not (
            previous_view and previous_view.status in {"pending", "offered"}
        )
        if can_create and st.button(
            "Generate Concept Check" if next_index == 1 else "Generate another question",
            key=f"make-quiz-{turn.turn_id}-{next_index}",
            type="primary",
        ):
            runtime.make_quiz(turn.turn_id, next_index)
            st.rerun()

        if turn.quizzes:
            quiz_index = max(turn.quizzes)
            view = turn.quizzes[quiz_index]
            record = turn.private_quizzes.get(quiz_index)
            result = turn.practice_results.get(view.practice_id or "") if view.practice_id else None
            with st.container(border=True, key="qa-practice"):
                render_quiz(view, result, record)
            pending = st.session_state.pop("learning_submit_choice", None)
            if pending and pending["turn_id"] == turn.turn_id:
                try:
                    runtime.submit(pending["turn_id"], pending["practice_id"], pending["choice"])
                except ValueError as exc:
                    st.error(str(exc))
                else:
                    st.rerun()

        if next_index > 3:
            st.caption(
                "All three quiz attempts for this answer have been used. "
                "Ask a new question to continue."
            )

        st.markdown("### Compare learner levels")
        comparison_levels = [
            level for level in StudentLevel if level is not runtime.static_profile.level
        ]
        if comparison_levels and not turn.comparison_done:
            other_level = st.selectbox(
                "Comparison level (does not change your profile)",
                options=comparison_levels,
                format_func=lambda value: value.value,
                key=f"comparison-level-{turn.turn_id}",
            )
            st.caption(
                "This comparison makes additional API requests and uses the same saved textbook "
                "evidence."
            )
            if st.button("Compare answers", key=f"compare-{turn.turn_id}"):
                runtime.compare_static_levels(turn.turn_id, other_level)
                st.rerun()
        if turn.comparison_done:
            if "error" in turn.comparison:
                st.warning(turn.comparison["error"])
            else:
                columns = st.columns(len(turn.comparison))
                for column, (level_name, answer_text) in zip(
                    columns, turn.comparison.items(), strict=False
                ):
                    with column:
                        st.markdown(f"**{level_name}**")
                        st.markdown(format_math_markdown(answer_text))
                st.caption(
                    "These are API outputs generated with different static learner profiles; "
                    "they are not an evaluation of learning effectiveness."
                )

        if st.button(
            "Ask the same question again with the current profile (uses the API again)",
            key=f"ask-again-{turn.turn_id}",
        ):
            runtime.ask_again(turn.question)
            st.rerun()


def render_session_report(runtime) -> None:
    """Use M8's report formats with the same online session event stream."""
    from cs30.evaluation.concept_check_reporting import (
        build_concept_check_report,
        render_concept_check_csv,
        render_concept_check_json,
        render_concept_check_markdown,
    )

    with st.sidebar.expander("Session report"):
        events = runtime.event_store.events(runtime.static_profile.profile_id)
        if not events:
            st.caption("Complete a Concept Check to record progress.")
            return
        report = build_concept_check_report(
            events,
            starting_levels={runtime.static_profile.profile_id: runtime.static_profile.level},
            topic_registry=runtime.assets.topic_registry,
        )
        st.markdown(render_concept_check_markdown(report))
        for label, renderer, suffix, mime in (
            ("CSV", render_concept_check_csv, "csv", "text/csv"),
            ("JSON", render_concept_check_json, "json", "application/json"),
            ("Markdown", render_concept_check_markdown, "md", "text/markdown"),
        ):
            st.download_button(
                f"Download {label}", renderer(report), f"session.{suffix}", mime=mime,
                key=f"learning-report-{suffix}", on_click="ignore",
            )
