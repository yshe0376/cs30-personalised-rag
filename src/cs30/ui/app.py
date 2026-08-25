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
    """Apply a restrained blue presentation layer without changing behaviour."""

    st.markdown(
        """
        <style>
        :root {
            --cs30-blue: #3973e6;
            --cs30-blue-dark: #2454bd;
            --cs30-ink: #17233d;
            --cs30-muted: #687791;
            --cs30-line: #dbe6f4;
        }
        [data-testid="stAppViewContainer"] {
            color: var(--cs30-ink);
            background:
                radial-gradient(circle at 8% 8%, rgba(184, 216, 255, .45), transparent 28%),
                radial-gradient(circle at 92% 40%, rgba(225, 235, 255, .65), transparent 30%),
                #f6f9ff;
        }
        [data-testid="stHeader"] { background: transparent; }
        [data-testid="stToolbar"], #MainMenu, footer { visibility: hidden; }
        .block-container { max-width: 1180px; padding-top: 2rem; padding-bottom: 2rem; }
        .cs30-hero {
            display: flex;
            justify-content: space-between;
            gap: 28px;
            align-items: flex-end;
            padding: 26px 0 24px;
            border-bottom: 1px solid var(--cs30-line);
        }
        .cs30-kicker {
            margin: 0 0 9px;
            color: var(--cs30-blue);
            font-size: .72rem;
            font-weight: 800;
            letter-spacing: .14em;
        }
        .cs30-hero h1 {
            margin: 0;
            color: var(--cs30-ink);
            font-family: Georgia, 'Times New Roman', serif;
            font-size: clamp(2.45rem, 5vw, 4.5rem);
            font-weight: 500;
            letter-spacing: -.045em;
            line-height: 1;
        }
        .cs30-hero h1 span { color: var(--cs30-blue); }
        .cs30-subtitle { margin: 14px 0 0; color: var(--cs30-muted); font-size: 1rem; }
        .cs30-pill {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 8px 12px;
            border: 1px solid #bfd5f6;
            border-radius: 999px;
            color: var(--cs30-blue-dark);
            background: #edf5ff;
            font-size: .76rem;
            font-weight: 750;
            white-space: nowrap;
        }
        .cs30-pill::before {
            content: '';
            width: 7px;
            height: 7px;
            border-radius: 50%;
            background: #4f8cff;
            box-shadow: 0 0 0 4px #d8e8ff;
        }
        .cs30-section-label {
            margin: 4px 0 2px;
            color: var(--cs30-blue);
            font-size: .7rem;
            font-weight: 800;
            letter-spacing: .12em;
        }
        .cs30-step {
            display: inline-grid;
            place-items: center;
            width: 28px;
            height: 28px;
            margin-right: 8px;
            border: 1px solid #aac7ef;
            border-radius: 50%;
            color: var(--cs30-blue-dark);
            font-size: .68rem;
            font-weight: 800;
        }
        .cs30-empty {
            display: grid;
            min-height: 355px;
            place-content: center;
            padding: 40px;
            border: 1px dashed #bfd2ed;
            border-radius: 18px;
            color: var(--cs30-muted);
            background: rgba(255, 255, 255, .55);
            text-align: center;
        }
        .cs30-empty strong { margin-bottom: 8px; color: var(--cs30-ink); font-size: 1.1rem; }
        div[data-testid="stVerticalBlockBorderWrapper"] {
            border-color: var(--cs30-line);
            border-radius: 16px;
            background: rgba(255, 255, 255, .72);
            box-shadow: 0 10px 30px rgba(45, 91, 155, .06);
        }
        div[data-testid="stButton"] > button {
            min-height: 48px;
            border: 0;
            border-radius: 11px;
            color: white;
            background: linear-gradient(135deg, #4f86f7, #2f64d2);
            box-shadow: 0 10px 22px rgba(61, 114, 232, .20);
            font-weight: 750;
        }
        div[data-testid="stButton"] > button:hover {
            color: white;
            border: 0;
            background: var(--cs30-blue-dark);
        }
        div[data-baseweb="select"] > div,
        div[data-testid="stTextArea"] textarea {
            border-color: #cbdcf2;
            border-radius: 11px;
            background: rgba(255, 255, 255, .84);
        }
        div[data-testid="stAlert"] { border-radius: 12px; }
        details { border-color: var(--cs30-line) !important; border-radius: 12px !important; }
        .cs30-footer {
            display: flex;
            justify-content: space-between;
            margin-top: 32px;
            padding-top: 18px;
            border-top: 1px solid var(--cs30-line);
            color: var(--cs30-muted);
            font-size: .72rem;
        }
        @media (max-width: 700px) {
            .cs30-hero { align-items: flex-start; flex-direction: column; }
            .block-container { padding-top: 1rem; }
            .cs30-footer { gap: 8px; flex-direction: column; }
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

    st.markdown('<p class="cs30-section-label">PIPELINE RESULT</p>', unsafe_allow_html=True)
    st.info(f"Run mode: {run.mode.upper()}")

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
        st.caption(f"Citations: {citation_text}")

    integrity = run.citation_integrity.upper()
    st.markdown(f"**Citation integrity:** {integrity}")

    st.subheader("Retrieved evidence")
    if not run.retrieval.hits:
        st.caption("No relevant evidence was retrieved.")
    for hit in run.retrieval.hits:
        cited = " · cited" if hit.chunk_id in run.answer.citations else ""
        with st.container(border=True):
            st.markdown(
                f"**{hit.rank}. {hit.chunk_id}** — score {hit.score:.2f}{cited}"
            )
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
    st.markdown(
        """
        <div class="cs30-hero">
          <div>
            <p class="cs30-kicker">PERSONALISED PHYSICS SUPPORT</p>
            <h1>Ask clearly.<br><span>Learn at your level.</span></h1>
            <p class="cs30-subtitle">
              A focused demonstration of answers grounded in retrieved textbook evidence.
            </p>
          </div>
          <span class="cs30-pill">Fixture prototype</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.warning(
        "Fixture mode uses fixed sample data. It demonstrates the runnable path only; "
        "it does not report retrieval or model performance."
    )

    input_column, result_column = st.columns([0.9, 1.1], gap="large")
    with input_column:
        with st.container(border=True):
            st.markdown(
                '<p class="cs30-section-label">'
                '<span class="cs30-step">01</span>SET THE LEARNER</p>',
                unsafe_allow_html=True,
            )
            level_value = st.selectbox(
                "Student level",
                options=[level.value for level in StudentLevel],
                index=0,
                format_func=str.title,
            )
            st.markdown(
                '<p class="cs30-section-label"><span class="cs30-step">02</span>ASK THE SYSTEM</p>',
                unsafe_allow_html=True,
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

            if st.button("Run fixture pipeline  →", type="primary", use_container_width=True):
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
                  <strong>Your grounded answer appears here</strong>
                  <span>
                    Choose a learner level, enter a question and run the fixture pipeline.
                  </span>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.markdown(
        """
        <div class="cs30-footer">
          <span>CS-30 · v0.1 thin-slice</span>
          <span>Member 8 Streamlit interface · local fixture mode</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
