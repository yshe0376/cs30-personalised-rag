"""Streamlit demo interface for the Week 1 personalised RAG thin slice."""

from __future__ import annotations

from html import escape

import streamlit as st

from cs30.config import load_config
from cs30.contracts import PipelineRun, StudentLevel
from cs30.errors import CS30Error
from cs30.pipeline import build_fixture_deps, run_pipeline

DEFAULT_QUESTION = "What is acceleration?"
EXAMPLE_QUESTIONS = {
    "Acceleration": DEFAULT_QUESTION,
    "Net force": "Why does an object accelerate when a net force acts on it?",
    "Safe refusal": "What is quantum entanglement?",
}


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
            font-size: 1.05rem;
            font-weight: 800;
            letter-spacing: .04em;
        }
        .cs30-field-title {
            margin: 18px 0 8px;
            color: var(--cs30-ink);
            font-size: 1.15rem;
            font-weight: 750;
            letter-spacing: -.015em;
            line-height: 1.2;
        }
        .cs30-meta {
            display: grid;
            grid-template-columns: 120px minmax(0, 1fr);
            gap: 12px;
            margin: 8px 0;
            color: var(--cs30-muted);
            font-size: .84rem;
        }
        .cs30-meta strong { color: var(--cs30-ink); font-weight: 700; }
        .cs30-meta span { overflow-wrap: anywhere; }
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
            font-size: .95rem;
            font-weight: 700;
        }
        div[data-testid="stButton"] > button:hover {
            border-color: var(--cs30-orange-dark);
            color: white;
            background: var(--cs30-orange-dark);
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

    return run_pipeline(
        question=question,
        level=level,
        deps=build_fixture_deps(),
        config=load_config("development"),
    )


def render_result(run: PipelineRun) -> None:
    """Render one complete pipeline result without changing its contract."""

    st.markdown('<p class="cs30-section-label">PIPELINE OUTPUT</p>', unsafe_allow_html=True)

    if run.answer.abstained:
        st.warning("The system refused to answer because the retrieved evidence was insufficient.")
        st.write(run.answer.explanation)
    else:
        st.success("Smoke path completed")
        st.markdown('<h3 class="cs30-field-title">Generated answer</h3>', unsafe_allow_html=True)
        if run.answer.final_choice:
            st.markdown(f"**Final choice:** {run.answer.final_choice}")
        st.write(run.answer.explanation)
        citation_text = ", ".join(run.answer.citations)
        st.markdown(
            '<div class="cs30-meta"><strong>Citation ID</strong>'
            f"<span>{escape(citation_text)}</span></div>",
            unsafe_allow_html=True,
        )

    st.markdown(
        '<div class="cs30-meta"><strong>Citation integrity</strong>'
        f"<span>{escape(run.citation_integrity.upper())}</span></div>",
        unsafe_allow_html=True,
    )
    st.markdown('<h3 class="cs30-field-title">Retrieved evidence</h3>', unsafe_allow_html=True)
    if not run.retrieval.hits:
        st.caption("No relevant evidence was retrieved.")
    for hit in run.retrieval.hits:
        cited = " · cited" if hit.chunk_id in run.answer.citations else ""
        with st.container(border=True):
            st.markdown(f"**{hit.rank}. {hit.chunk_id}** — score {hit.score:.2f}{cited}")
            st.write(hit.text)
            st.caption(f"{hit.chapter_id} · {hit.source}")

    with st.expander("Technical run details"):
        st.json(run.model_dump(mode="json"))


def main() -> None:
    """Render the demo and submit questions to the fixture pipeline."""

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
    st.info(
        "FIXTURE MODE · MOCK DATA — Uses fixed demo data; "
        "no real retriever or LLM is connected."
    )

    input_column, result_column = st.columns([0.9, 1.1], gap="large")
    with input_column:
        with st.container(border=True):
            st.markdown(
                '<p class="cs30-section-label">QUESTION SETTINGS</p>',
                unsafe_allow_html=True,
            )
            st.markdown('<h3 class="cs30-field-title">Student level</h3>', unsafe_allow_html=True)
            level_value = st.selectbox(
                "Select student level",
                options=[level.value for level in StudentLevel],
                index=0,
                format_func=str.title,
                label_visibility="collapsed",
            )
            st.markdown('<h3 class="cs30-field-title">Input question</h3>', unsafe_allow_html=True)
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

            st.markdown('<h3 class="cs30-field-title">Try</h3>', unsafe_allow_html=True)
            st.pills(
                "Try a prepared question",
                options=list(EXAMPLE_QUESTIONS),
                selection_mode="single",
                key="selected_example",
                on_change=apply_example,
                label_visibility="collapsed",
            )

            if st.button("Run fixture pipeline", type="primary", use_container_width=True):
                try:
                    run = execute_fixture_run(question, StudentLevel(level_value))
                except (CS30Error, ValueError) as exc:
                    st.error(f"The pipeline could not run: {exc}")
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
                  <span>Run the fixture pipeline to display the result.</span>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.markdown(
        '<div class="cs30-footer">CS-30 · v0.1 thin-slice · Member 8 demo interface</div>',
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
