"""Streamlit demo interface for the Week 1 personalised RAG thin slice."""

from __future__ import annotations

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
            margin: 2px 0 4px;
            color: var(--cs30-orange-dark);
            font-size: .7rem;
            font-weight: 800;
            letter-spacing: .1em;
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
        st.subheader("Generated answer")
        if run.answer.final_choice:
            st.markdown(f"**Final choice:** {run.answer.final_choice}")
        st.write(run.answer.explanation)
        citation_text = ", ".join(run.answer.citations)
        st.caption(f"Citation ID: {citation_text}")

    st.markdown(f"**Citation integrity:** {run.citation_integrity.upper()}")
    st.subheader("Retrieved evidence")
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
            level_value = st.selectbox(
                "Student level",
                options=[level.value for level in StudentLevel],
                index=0,
                format_func=str.title,
            )
            example = st.pills(
                "Try a question",
                options=list(EXAMPLE_QUESTIONS),
                selection_mode="single",
            )
            if example and st.session_state.get("selected_example") != example:
                st.session_state["question_input"] = EXAMPLE_QUESTIONS[example]
                st.session_state["selected_example"] = example
            question = st.text_area(
                "Physics question",
                value=DEFAULT_QUESTION,
                height=150,
                key="question_input",
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
