"""V2 learning-page layout over the existing shared Concept Check fixtures."""

from __future__ import annotations

import streamlit as st

from cs30.concept_check.fixtures import load_fixture_scenarios
from cs30.ui.app import inject_styles
from cs30.ui.concept_check import render_quiz
from cs30.ui.concept_check_demo import (
    QUIZ_KEY,
    DemoRuntime,
    _event_directory,
    _inject_demo_styles,
    _register_starting_level,
    _render_control_notice,
    _render_learner_state,
    _render_level_settings,
    _render_session_report,
    _reset_selection,
    _revoke_current_attempt,
    _select_and_store_question,
    _session_token,
    build_demo_runtime,
    record_demo_attempt,
    selection_message,
)
from cs30.v2.contracts import ConceptCheckQuestionRelease, StudentLevel, StudentProfile


def inject_v2_styles() -> None:
    """Keep V1 typography and orange, including the native Streamlit switch."""

    inject_styles()
    _inject_demo_styles()
    st.markdown(
        """
        <style>
        [data-testid="stSidebar"] { background: #faf8f6; }
        [data-testid="stSidebar"] h2 { color: #171411; }
        [data-testid="stCheckbox"] label[data-baseweb="checkbox"]
        > div:first-child:has(input[role="switch"][aria-checked="true"]) {
            background-color: #f06f54;
        }
        [data-testid="stCheckbox"] label[data-baseweb="checkbox"]
        > div:first-child:has(input:checked) { background-color: #f06f54; }
        .v2-eyebrow { color: #df5b40; font-weight: 700; letter-spacing: .08em; }
        /* V1 hides the toolbar, which also hid the "expand sidebar" control.
           Keep the toolbar hidden but always show that control as a labelled tab. */
        [data-testid="stExpandSidebarButton"],
        [data-testid="stExpandSidebarButton"] *,
        [data-testid="stSidebarCollapsedControl"],
        [data-testid="stSidebarCollapsedControl"] * { visibility: visible !important; }
        [data-testid="stExpandSidebarButton"] {
            display: inline-flex !important;
            align-items: center;
            gap: 6px;
            width: auto !important;
            padding: 6px 14px 6px 10px !important;
            border: 1px solid #f06f54 !important;
            border-radius: 999px !important;
            color: #df5b40 !important;
            background: #fff4f1 !important;
            font-weight: 650;
        }
        [data-testid="stExpandSidebarButton"]::after {
            content: "Demo Mode";
            font-size: .9rem;
        }
        [data-testid="stExpandSidebarButton"]:hover { background: #ffe6df !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_fixture_answer(runtime: DemoRuntime, query: str, answer: str) -> None:
    """Display the selected fixture turn and its actual cited/retrieved passages."""

    st.markdown("### Your question")
    st.write(query)
    st.markdown("### Answer")
    st.write(answer)
    st.caption(
        "Saved fixture answer — changing a level does not regenerate this text. "
        "Live V2 question answering is not connected to this page."
    )
    st.markdown("#### Evidence and sources")
    st.caption("Synthetic fixture passages, not verified quotations from a live corpus.")
    cited = set(runtime.validated.resolved_citations)
    for index, hit in enumerate(runtime.retrieval.hits, start=1):
        role = "Cited" if hit.chunk_id in cited else "Retrieved only"
        with st.expander(f"E{index} · Chapter {hit.chapter_id} · {role}"):
            st.write(hit.text)
            st.caption(f"Textbook: {hit.textbook_id}")
            st.code(hit.source_locator, language=None)
            st.caption(f"Chunk ID: {hit.chunk_id}")


def render_practice(runtime: DemoRuntime) -> None:
    """Render optional practice using the existing service callbacks and quiz UI."""

    st.divider()
    st.markdown("### Check your understanding")
    if not runtime.service.config.enabled:
        st.info(
            "Concept Check is off. Practice and Topic-level changes are disabled. "
            "Your starting profile is active; existing history is kept."
        )
        return
    st.caption("Choose a short practice question based on this answer's cited Topic.")
    if st.button("Quiz me", type="primary", use_container_width=True):
        _select_and_store_question(runtime)
        st.rerun()
    release = st.session_state.get("concept_check_demo_release")
    if isinstance(release, ConceptCheckQuestionRelease):
        render_quiz(
            release,
            on_submit=lambda choice: record_demo_attempt(runtime, release, choice),
            on_skip=lambda: record_demo_attempt(runtime, release, None),
            on_next=lambda: _select_and_store_question(runtime),
            on_revoke=lambda attempt_id: _revoke_current_attempt(runtime, attempt_id),
            key=QUIZ_KEY,
        )
    elif st.session_state.get("concept_check_demo_no_question"):
        st.info(selection_message(st.session_state["concept_check_demo_selection"]))


def main() -> None:
    """Compose a local fixture-only learning screen without changing shared logic."""

    st.set_page_config(
        page_title="CS-30 · V2 Learning Demo", page_icon="🎓", layout="wide"
    )
    inject_v2_styles()
    scenarios = load_fixture_scenarios()
    by_id = {scenario.scenario_id: scenario for scenario in scenarios}
    with st.sidebar:
        st.markdown("## Your starting level")
        level_value = st.selectbox(
            "Starting level",
            options=[level.value for level in StudentLevel],
            format_func=str.title,
            key="concept_check_demo_level",
            on_change=_reset_selection,
        )
        st.caption(
            "Your baseline for this demo. Each starting level uses a separate fixture "
            "profile; switching back restores that profile's session history."
        )
        st.divider()
        enabled = st.toggle(
            "Enable Concept Check",
            value=False,
            key="concept_check_demo_enabled",
            on_change=_reset_selection,
        )
        st.caption(
            "Controls optional practice and dynamic Topic levels together. "
            "Turning it off keeps history and uses the starting profile."
        )
        st.divider()
        st.markdown("### Prepared question")
        scenario_id = st.selectbox(
            "Demo scenario",
            options=list(by_id),
            format_func=lambda value: by_id[value].title,
            key="concept_check_demo_scenario",
            on_change=_reset_selection,
        )
        st.caption("Select an existing fixture turn. No model or API is called.")

    profile = StudentProfile(
        profile_id=f"fixture-demo-{_session_token()}-{level_value}",
        level=StudentLevel(level_value),
    )
    _register_starting_level(profile)
    directory = _event_directory()
    scenario = by_id[scenario_id]
    runtime = build_demo_runtime(
        event_directory=directory, profile=profile, scenario=scenario, enabled=enabled
    )
    st.markdown('<p class="v2-eyebrow">CS-30 / VERSION 2</p>', unsafe_allow_html=True)
    st.title("Personalised Learning Assistant")
    st.caption("Read an answer, explore its evidence, and choose whether to practise.")
    st.warning("FIXTURE MODE · TEST DATA — NOT REAL PRACTICE QUESTIONS. No LLM is connected.")
    _render_control_notice()
    learning, report = st.tabs(["Learn and practise", "Session report"])
    with learning:
        render_fixture_answer(runtime, scenario.query, scenario.answer)
        render_practice(runtime)
        st.divider()
        st.markdown("### Topic progress")
        _render_learner_state(runtime)
        if enabled:
            _render_level_settings(runtime)
        else:
            st.caption("Enable Concept Check to use or adjust dynamic Topic levels.")
        with st.expander("Technical run details"):
            st.write(
                {
                    "mode": "fixture",
                    "scenario": scenario.scenario_id,
                    "starting_level": profile.level.value,
                    "concept_check_enabled": enabled,
                    "corpus_version": runtime.retrieval.provenance.corpus_version,
                    "fixture_citation_status": runtime.validated.citation_status,
                    "resolved_citations": list(runtime.validated.resolved_citations),
                    "answer_source": "saved fixture; not regenerated from learner state",
                }
            )
            selection = st.session_state.get("concept_check_demo_selection")
            if selection is not None:
                st.json(selection.model_dump(mode="json", exclude={"question"}))
    with report:
        _render_session_report(directory)
    st.caption("CS-30 · V2 local UI · Shared fixture runtime · Single-session event history")


if __name__ == "__main__":
    main()
