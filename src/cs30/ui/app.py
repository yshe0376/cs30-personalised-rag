"""Streamlit demo interface for the Week 1 personalised RAG thin slice."""

from __future__ import annotations

from html import escape

import streamlit as st

from cs30.config import AppConfig, load_config
from cs30.contracts import PipelineRun, StudentLevel
from cs30.errors import CS30Error
from cs30.logging import configure_logging, get_logger
from cs30.pipeline import build_fixture_deps, build_real_deps, run_pipeline

DEFAULT_QUESTION = "What is acceleration?"
EXAMPLE_QUESTIONS = {
    "Acceleration": DEFAULT_QUESTION,
    "Net force": "Why does an object accelerate when a net force acts on it?",
    "Quantum entanglement": "What is quantum entanglement?",
}
LOGGER = get_logger("ui")


def inject_styles() -> None:
    """Keep the Streamlit presentation simple, white, and easy to scan."""

    st.markdown(
        """
        <style>
        :root {
            --cs30-orange: #f06f54;
            --cs30-orange-dark: #df5b40;
            --cs30-ink: #171411;
            --cs30-muted: #706a64;
            --cs30-line: #e8e4e1;
        }
        [data-testid="stAppViewContainer"] {
            color: var(--cs30-ink);
            background: #ffffff;
        }
        [data-testid="stHeader"] { background: #ffffff; }
        [data-testid="stToolbar"], #MainMenu, footer { visibility: hidden; }
        .block-container { max-width: 1120px; padding-top: 2.3rem; padding-bottom: 2rem; }
        h1, h2, h3 { color: var(--cs30-ink); letter-spacing: -.025em; }
        .cs30-intro { margin: -.4rem 0 1.1rem; color: var(--cs30-muted); }
        .cs30-section-label {
            margin: 2px 0 18px;
            color: var(--cs30-orange-dark);
            font-size: 1.35rem !important;
            font-weight: 800;
            letter-spacing: -.015em;
        }
        .cs30-field-title {
            margin: 18px 0 8px;
            color: var(--cs30-ink);
            font-size: 1.05rem !important;
            font-weight: 750;
            letter-spacing: -.015em;
            line-height: 1.2;
        }
        .cs30-helper-title {
            margin: 14px 0 7px;
            color: var(--cs30-muted);
            font-size: .78rem !important;
            font-weight: 650;
            letter-spacing: .025em;
        }
        .cs30-result-meta { display: flex; flex-wrap: wrap; gap: 8px; margin: 14px 0 18px; }
        .cs30-run-meta {
            display: flex;
            flex-wrap: wrap;
            gap: 18px;
            margin: 4px 0 18px;
            color: var(--cs30-muted);
            font-size: .86rem;
        }
        .cs30-run-meta strong { color: var(--cs30-ink); }
        .cs30-citation-chip,
        .cs30-integrity-chip {
            display: inline-flex;
            align-items: center;
            padding: 6px 10px;
            border-radius: 999px;
            font-size: .76rem;
            font-weight: 700;
            overflow-wrap: anywhere;
        }
        .cs30-citation-chip {
            border: 1px solid #f1c8be;
            color: var(--cs30-orange-dark);
            background: #fff8f5;
        }
        .cs30-integrity-chip {
            border: 1px solid #b9dfca;
            color: #237a4b;
            background: #edf8f1;
        }
        .cs30-integrity-chip.skipped {
            border-color: #f0cf8a;
            color: #8a5a00;
            background: #fff8e6;
        }
        div[data-testid="stVerticalBlockBorderWrapper"] {
            border-color: var(--cs30-line);
            border-radius: 14px;
            background: #ffffff;
            box-shadow: none;
        }
        div[data-testid="stButton"] > button {
            min-height: 46px;
            border-color: var(--cs30-orange);
            border-radius: 10px;
            color: white;
            background: var(--cs30-orange);
            font-size: 1.05rem;
            font-weight: 750;
        }
        div[data-testid="stButton"] > button:hover {
            border-color: var(--cs30-orange-dark);
            color: white;
            background: var(--cs30-orange-dark);
        }
        div[data-testid="stButton"] > button p {
            font-size: 1.05rem;
            font-weight: 750;
        }
        div[data-baseweb="select"] > div,
        div[data-testid="stTextArea"] textarea {
            border-color: var(--cs30-line);
            border-radius: 10px;
            background: #ffffff;
        }
        .cs30-empty {
            padding: 42px 24px;
            border: 1px dashed var(--cs30-line);
            border-radius: 14px;
            color: var(--cs30-muted);
            text-align: center;
        }
        .cs30-empty strong { display: block; margin-bottom: 6px; color: var(--cs30-ink); }
        .cs30-refusal-note {
            margin: 8px 0 4px;
            padding: 10px 14px;
            border: 1px solid #f0cf8a;
            border-radius: 10px;
            color: #8a5a00;
            background: #fff8e6;
            font-size: .92rem;
        }
        .cs30-footer {
            margin-top: 26px;
            padding-top: 14px;
            border-top: 1px solid var(--cs30-line);
            color: var(--cs30-muted);
            font-size: .72rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def execute_fixture_run(question: str, level: StudentLevel) -> PipelineRun:
    """Run the stable fixture path consumed by the demo interface."""

    return execute_configured_run(question, level, load_config("development"))


def execute_configured_run(
    question: str,
    level: StudentLevel,
    config: AppConfig,
) -> PipelineRun:
    """Select fixture or real adapters from the active environment configuration."""

    deps = build_fixture_deps() if config.fixture_mode else build_real_deps(config)
    return run_pipeline(question=question, level=level, deps=deps, config=config)


def render_result(run: PipelineRun) -> None:
    """Render the new PipelineRun contract; business decisions stay in pipeline."""

    bundle = run.evidence_bundle
    validated = run.validated_answer
    if bundle is None or validated is None:
        raise ValueError("PipelineRun must contain evidence_bundle and validated_answer")

    st.markdown('<p class="cs30-section-label">PIPELINE OUTPUT</p>', unsafe_allow_html=True)
    if run.answer.abstained:
        st.markdown(
            '<div class="cs30-refusal-note"><strong>Grounded answer unavailable</strong></div>',
            unsafe_allow_html=True,
        )
        st.write(run.answer.explanation)
    else:
        st.markdown('<p class="cs30-field-title">Generated answer</p>', unsafe_allow_html=True)
        if run.answer.final_choice:
            st.markdown(f"**Final choice:** {run.answer.final_choice}")
        st.write(run.answer.explanation)

    integrity_status = validated.citation_status
    integrity_class = (
        "cs30-integrity-chip skipped"
        if integrity_status == "skipped"
        else "cs30-integrity-chip"
    )
    integrity_chip = (
        f'<span class="{integrity_class}">Citation integrity · '
        f"{escape(integrity_status.upper())}</span>"
    )
    st.markdown(
        f'<div class="cs30-result-meta">{integrity_chip}</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="cs30-run-meta">'
        f'<span><strong>Retrieval mode:</strong> '
        f'<code>{escape(bundle.retrieval_mode.value)}</code></span>'
        f'<span><strong>Run ID:</strong> <code>{escape(run.run_id)}</code></span>'
        '</div>',
        unsafe_allow_html=True,
    )

    st.markdown('<p class="cs30-field-title">Retrieved evidence</p>', unsafe_allow_html=True)
    if not bundle.evidence_items:
        st.caption("No relevant evidence was retrieved.")
    for item in bundle.evidence_items:
        cited = " · cited" if item.chunk_id in run.answer.citations else ""
        with st.container(border=True):
            st.markdown(
                f"**{item.evidence_id} · rank {item.rank} · {item.chunk_id}** "
                f"— score {item.score:.2f}{cited}"
            )
            st.write(item.text)
            st.caption(
                f"Chapter: {item.chapter_id} · Source: {item.source} · "
                f"Source locator: {item.source_locator or 'not supplied'}"
            )

    with st.expander("Technical run details"):
        validated_snapshot = validated.model_dump(mode="json")
        # Run provenance is already preserved in the Evidence Bundle. Keep the
        # validated answer focused on answer/citation state in this view.
        validated_snapshot.pop("run_provenance", None)
        st.json(
            {
                "run_summary": {
                    "run_id": run.run_id,
                    "mode": run.mode,
                    "profile": run.profile.model_dump(mode="json"),
                    "metadata": run.metadata,
                },
                "evidence_bundle": bundle.model_dump(mode="json"),
                "validated_answer": validated_snapshot,
                "trace": run.trace,
            }
        )


def main() -> None:
    """Render the demo and submit questions to the fixture pipeline."""

    config = load_config()
    configure_logging(config.log_level)
    st.set_page_config(
        page_title="CS-30 Personalised Learning Assistant",
        page_icon="🎓",
        layout="wide",
    )
    inject_styles()
    st.title("CS-30 Personalised Learning Assistant")
    st.markdown(
        '<p class="cs30-intro">Select a learner level, enter a physics question, '
        "and review the generated answer with retrieved evidence.</p>",
        unsafe_allow_html=True,
    )
    if config.fixture_mode:
        environment_label = (
            "STAGING PREVIEW" if config.environment == "staging" else config.environment.upper()
        )
        st.info(
            f"{environment_label} · FIXTURE MODE · MOCK DATA — Uses fixed demo data; "
            "no real retriever or LLM is connected."
        )
    else:
        st.info(f"{config.environment.upper()} · REAL MODE")

    input_column, result_column = st.columns([0.9, 1.1], gap="large")
    with input_column:
        with st.container(border=True):
            st.markdown(
                '<p class="cs30-section-label">QUESTION SETTINGS</p>',
                unsafe_allow_html=True,
            )
            st.markdown('<p class="cs30-field-title">Student level</p>', unsafe_allow_html=True)
            level_value = st.selectbox(
                "Select student level",
                options=[level.value for level in StudentLevel],
                index=0,
                format_func=str.title,
                label_visibility="collapsed",
            )
            st.markdown('<p class="cs30-field-title">Input question</p>', unsafe_allow_html=True)
            question = st.text_area(
                "Physics question",
                value=DEFAULT_QUESTION,
                height=150,
                key="question_input",
                label_visibility="collapsed",
            )

            def apply_example() -> None:
                example = st.session_state.get("selected_example")
                if example:
                    st.session_state["question_input"] = EXAMPLE_QUESTIONS[example]

            st.markdown('<p class="cs30-helper-title">Try an example</p>', unsafe_allow_html=True)
            st.pills(
                "Try a prepared question",
                options=list(EXAMPLE_QUESTIONS),
                selection_mode="single",
                key="selected_example",
                on_change=apply_example,
                label_visibility="collapsed",
            )

            if st.button("Run pipeline", type="primary", use_container_width=True):
                try:
                    run = execute_configured_run(question, StudentLevel(level_value), config)
                except (CS30Error, NotImplementedError, ValueError) as exc:
                    LOGGER.exception("pipeline_failed query=%r error=%s", question, exc)
                    st.error(f"The pipeline could not run: {exc}")
                    if not config.fixture_mode:
                        st.warning("Falling back to the offline fixture pipeline for this run.")
                        try:
                            run = execute_fixture_run(question, StudentLevel(level_value))
                        except (CS30Error, ValueError) as fallback_exc:
                            LOGGER.exception(
                                "fixture_fallback_failed query=%r error=%s",
                                question,
                                fallback_exc,
                            )
                            st.error(f"The fixture fallback also failed: {fallback_exc}")
                        else:
                            run.metadata["fallback_reason"] = str(exc)
                            run.trace["fallback_reason"] = str(exc)
                            st.session_state["pipeline_run"] = run
                else:
                    st.session_state["pipeline_run"] = run

    with result_column:
        stored_run = st.session_state.get("pipeline_run")
        if isinstance(stored_run, PipelineRun):
            render_result(stored_run)
        else:
            st.markdown(
                """
                <div class="cs30-empty">
                  <strong>Answer and evidence</strong>
                  <span>Run the pipeline to display the result.</span>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.markdown(
        '<div class="cs30-footer">CS-30 · v0.1 thin-slice · Demo interface</div>',
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
