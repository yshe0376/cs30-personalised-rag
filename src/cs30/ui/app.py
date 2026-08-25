"""Streamlit demo interface for the Week 1 personalised RAG thin slice."""

from __future__ import annotations

import streamlit as st

from cs30.config import load_config
from cs30.contracts import PipelineRun, StudentLevel
from cs30.errors import CS30Error
from cs30.pipeline import build_fixture_deps, run_pipeline

DEFAULT_QUESTION = "What is acceleration?"


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

    st.divider()
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
        layout="centered",
    )
    st.title("CS-30 Personalised Learning Assistant")
    st.caption("v0.1 thin-slice staging demo")
    st.warning(
        "Fixture mode uses fixed sample data. It demonstrates the runnable path only; "
        "it does not report retrieval or model performance."
    )

    level_value = st.selectbox(
        "Student level",
        options=[level.value for level in StudentLevel],
        index=0,
        format_func=str.title,
    )
    question = st.text_area("Physics question", value=DEFAULT_QUESTION, height=120)

    if st.button("Run fixture pipeline", type="primary"):
        try:
            run = execute_fixture_run(question, StudentLevel(level_value))
        except (CS30Error, ValueError) as exc:
            st.error(f"The pipeline could not run: {exc}")
        else:
            st.session_state["pipeline_run"] = run

    stored_run = st.session_state.get("pipeline_run")
    if isinstance(stored_run, PipelineRun):
        render_result(stored_run)


if __name__ == "__main__":
    main()
