"""Free-text V2 Q&A with shared generation, validation and optional practice."""

from __future__ import annotations

import os
from pathlib import Path
from tempfile import mkdtemp
from uuid import uuid4

import streamlit as st

from cs30.evaluation.concept_check_reporting import (
    build_concept_check_report,
    render_concept_check_csv,
    render_concept_check_json,
    render_concept_check_markdown,
)
from cs30.ui.concept_check import clear_quiz_component, render_quiz
from cs30.ui.concept_check_demo import record_demo_attempt
from cs30.ui.v2_fixture import inject_v2_styles
from cs30.ui.v2_runtime import (
    TEAM_MODEL,
    QuestionRun,
    UiBm25Retriever,
    load_ui_corpus,
    refresh_controls,
    run_question,
)
from cs30.v2.contracts import StudentLevel, StudentProfile

QUIZ_KEY = "qa-quiz"
EXAMPLES = {
    "Acceleration": "What is average acceleration?",
    "Newton's second law": "How are net force, mass and acceleration related?",
    "Out of scope": "Which team won the football match yesterday?",
}


def clear_question() -> None:
    """Clear obsolete output when its source/model/baseline changes, retaining events."""

    st.session_state.pop("qa-run", None)
    clear_practice()


def clear_practice() -> None:
    st.session_state.pop("qa-selection", None)
    clear_quiz_component(QUIZ_KEY)


def session_directory() -> Path:
    if "qa-directory" not in st.session_state:
        st.session_state["qa-directory"] = mkdtemp(prefix="cs30-v2-qa-")
    return Path(st.session_state["qa-directory"])


def render_answer(run: QuestionRun) -> None:
    """Show the exact validated output and generation-time settings, never relabel it."""

    validated = run.runtime.validated
    st.markdown("### Answer")
    if validated.abstained:
        st.warning(validated.answer.explanation)
    else:
        st.write(validated.answer.explanation)
    snapshot = run.prepared.snapshot
    st.caption(
        f"Level used: {snapshot.profile.level.value.title()} · "
        f"Profile source: {snapshot.profile_source.value} · "
        f"Citation integrity: {validated.citation_status.upper()}"
    )
    st.markdown("#### Evidence and sources")
    cited = set(validated.resolved_citations)
    for item in run.bundle.evidence_items:
        marker = "Cited" if item.chunk_id in cited else "Retrieved only"
        with st.expander(
            f"{item.evidence_id} · {item.source_name} · Chapter {item.chapter_id} · {marker}"
        ):
            st.write(item.text)
            st.code(item.source_locator, language=None)
            st.caption(f"Chunk ID: {item.chunk_id} · Rank: {item.rank}")
    if not run.bundle.evidence_items:
        st.info(
            "No evidence was retrieved. The generator returns an abstention without a model call."
        )


def render_practice(run, corpus, directory, enabled) -> None:
    """Continue from the actual validated answer, using the shared selection contract."""

    runtime = refresh_controls(run, corpus, directory, enabled)
    st.divider()
    st.markdown("### Concept Check")
    if not enabled:
        st.info("Concept Check is off. Topic changes are paused; existing history is kept.")
        return
    if not corpus.synthetic:
        st.caption(
            "Real-corpus selection uses the released Topic map. No compatible reviewed "
            "practice releases are installed; fixture questions are never mixed into this corpus."
        )

    def select():
        clear_practice()
        prepared = runtime.service.prepare(runtime.retrieval, runtime.profile)
        st.session_state["qa-selection"] = runtime.service.select(
            prepared, runtime.retrieval, runtime.validated
        )

    if st.button("Quiz me", type="primary"):
        select()
        st.rerun()
    selection = st.session_state.get("qa-selection")
    if selection is not None:
        if selection.question is None:
            code = selection.error_code.value if selection.error_code else selection.status.value
            st.info(f"No practice question is offered for this answer. Reason: {code}")
        else:

            def revoke(attempt_id):
                runtime.service.revoke(attempt_id, event_id=f"revoke-{attempt_id}")
                clear_practice()

            render_quiz(
                selection.question,
                on_submit=lambda choice: record_demo_attempt(runtime, selection.question, choice),
                on_skip=lambda: record_demo_attempt(runtime, selection.question, None),
                on_next=select,
                on_revoke=revoke,
                key=QUIZ_KEY,
            )
    state = runtime.replayer.replay(runtime.event_store.events(runtime.profile.profile_id))
    resolution = runtime.service.resolver.resolve_cited_topic(runtime.retrieval, runtime.validated)
    topic_id = resolution.topic_id
    st.markdown("#### Topic progress")
    if topic_id is None:
        st.caption(f"Topic unavailable: {resolution.error_code or resolution.status.value}")
        return
    title = next(t.title for t in corpus.registry.topics if t.topic_id == topic_id)
    topic = state.topics.get(topic_id)
    st.write(
        f"Topic: {title} · Level: {(topic.level if topic else runtime.profile.level).value.title()}"
    )
    st.caption(
        f"Scored attempts: {topic.total_attempts if topic else 0}. "
        "State comes from shared event replay."
    )
    with st.expander("Adjust this Topic level"):
        new_level = st.selectbox(
            "New Topic level", list(StudentLevel), format_func=lambda x: x.value.title()
        )
        reason = st.text_input("Reason for level change")
        if st.button("Apply Topic level"):
            if not reason.strip():
                st.error("A reason is required.")
            else:
                try:
                    runtime.service.override_level(
                        topic_id, new_level, reason=reason, event_id=uuid4().hex
                    )
                except (ValueError, OSError):
                    st.error("The Topic change could not be saved. No success is claimed.")
                else:
                    clear_practice()
                    st.rerun()


def render_report(run, corpus, directory, enabled):
    runtime = refresh_controls(run, corpus, directory, enabled)
    try:
        events = runtime.event_store.events(runtime.profile.profile_id)
        if not events:
            st.info("No events have been recorded for this profile yet.")
            return
        report = build_concept_check_report(
            events,
            starting_levels={runtime.profile.profile_id: runtime.profile.level},
            topic_registry=corpus.registry,
        )
        st.markdown(render_concept_check_markdown(report))
        for label, renderer, suffix, mime in [
            ("CSV", render_concept_check_csv, "csv", "text/csv"),
            ("JSON", render_concept_check_json, "json", "application/json"),
            ("Markdown", render_concept_check_markdown, "md", "text/markdown"),
        ]:
            st.download_button(
                f"Download {label}", renderer(report), f"session.{suffix}", mime=mime
            )
    except Exception:
        st.warning("The report is unavailable. Recorded events have been retained.")


def main() -> None:
    st.set_page_config(page_title="CS-30 · Ask a question", page_icon="🎓", layout="wide")
    inject_v2_styles()
    directory = session_directory()
    if "qa-pending-example" in st.session_state:
        st.session_state["qa-question"] = st.session_state.pop("qa-pending-example")
    with st.sidebar:
        st.markdown("## Your starting level")
        level = st.selectbox(
            "Starting level",
            list(StudentLevel),
            format_func=lambda x: x.value.title(),
            key="qa-level",
            on_change=clear_question,
        )
        st.caption("Starting levels use separate profiles. Existing history is retained.")
        enabled = st.toggle(
            "Enable Concept Check", value=False, key="qa-enabled", on_change=clear_practice
        )
        st.caption(
            "Controls practice and dynamic Topic levels together. "
            "Changes apply to the next generated answer."
        )
        st.divider()
        mode = st.selectbox(
            "Demo mode",
            ["Team V2 · DeepInfra", "Offline integration · simulated answers"],
            key="qa-mode",
            on_change=clear_question,
        )
        live = mode == "Team V2 · DeepInfra"
        st.caption(f"Team generator: {TEAM_MODEL}")
        st.caption(
            "Searches the selected corpus using the team's BM25 baseline."
        )
        with st.expander("Connection details"):
            st.write(
                "DeepInfra key: "
                + ("configured" if os.environ.get("DEEPINFRA_API_KEY") else "not configured")
            )
            st.caption(
                "Set DEEPINFRA_API_KEY in the server terminal. "
                "Do not paste it into reports or chat."
            )
            st.caption(
                "The frozen M6 hybrid file is not an arbitrary-query search service. "
                "This page uses the existing BM25 baseline, without transferring "
                "the hybrid experiment's selected lambda."
            )
    st.markdown('<p class="v2-eyebrow">CS-30 / VERSION 2</p>', unsafe_allow_html=True)
    st.title("Personalised Learning Assistant")
    st.caption("Ask a physics question, inspect the evidence, and choose a Concept Check.")
    if live:
        st.info("TEAM MODEL · DeepInfra / gpt-oss-20b · V2 four-book corpus · BM25 baseline")
    else:
        st.warning(
            "OFFLINE INTEGRATION · SYNTHETIC CORPUS + MOCK ANSWERS · Not model-quality evidence"
        )
    st.session_state.setdefault("qa-question", EXAMPLES["Acceleration"])
    st.text_area("Your physics question", key="qa-question", height=110)
    example = st.selectbox("Prepared examples", ["Choose an example", *EXAMPLES])
    if st.button("Use example") and example in EXAMPLES:
        st.session_state["qa-pending-example"] = EXAMPLES[example]
        st.rerun()
    learning, report_tab = st.tabs(["Answer and practice", "Session report"])
    topic_dir = Path(__file__).resolve().parents[3] / "artifacts/v2/topics/releases/2.0.0-rc.1"
    corpus_path = os.environ.get("CS30_UI_CORPUS", "")
    cache_key = f"qa-corpus-{live}-{corpus_path}"
    corpus = None
    try:
        if cache_key not in st.session_state:
            st.session_state[cache_key] = load_ui_corpus(
                Path(corpus_path) if corpus_path else None, topic_dir, synthetic=not live
            )
        corpus = st.session_state[cache_key]
    except (OSError, ValueError) as exc:
        st.error(f"V2 corpus readiness check failed: {exc}")
    with learning:
        missing_key = live and not os.environ.get("DEEPINFRA_API_KEY", "").strip()
        if missing_key:
            st.warning(
                "DeepInfra is not configured on this machine. Generate answer becomes "
                "available after setup. Offline integration is available for a "
                "clearly labelled workflow demonstration."
            )
        clicked = st.button(
            "Generate answer" if live else "Run offline pipeline",
            type="primary",
            disabled=corpus is None or missing_key,
        )
        if clicked:
            clear_question()
            profile = StudentProfile(
                profile_id=f"qa-{directory.name}-{live}-{level.value}", level=level
            )
            try:
                with st.status("Running V2 question-answering pipeline", expanded=True) as status:
                    retriever = UiBm25Retriever(
                        corpus, directory / ("real-index" if live else "fixture-index")
                    )
                    run = run_question(
                        st.session_state["qa-question"],
                        profile,
                        corpus,
                        retriever,
                        directory,
                        enabled=enabled,
                        live=live,
                        progress=st.write,
                    )
                    st.session_state["qa-run"] = run
                    status.update(label="Pipeline completed", state="complete", expanded=False)
            except Exception as exc:
                st.error(
                    f"The pipeline stopped ({type(exc).__name__}). "
                    "No fallback answer was substituted."
                )
                if isinstance(exc, ValueError):
                    st.caption(str(exc))
        run = st.session_state.get("qa-run")
        if isinstance(run, QuestionRun):
            if st.session_state["qa-question"].strip() != run.runtime.retrieval.query:
                st.warning(
                    "The input has changed. "
                    "The result below belongs to the previous submitted question."
                )
            st.caption(f"Submitted question: {run.runtime.retrieval.query}")
            render_answer(run)
            try:
                render_practice(run, corpus, directory, enabled)
            except OSError:
                st.error("Practice storage is unavailable. No saved progress is claimed.")
            with st.expander("Technical run details"):
                st.json(
                    {
                        "run_id": run.run_id,
                        "mode": run.mode,
                        "steps": run.steps,
                        "model": run.trace.model if run.trace else None,
                        "corpus": run.runtime.retrieval.provenance.model_dump(mode="json"),
                        "profile_source": run.prepared.snapshot.profile_source.value,
                        "generation_level": run.prepared.snapshot.profile.level.value,
                        "retrieval_topic": run.prepared.retrieval_topic.model_dump(mode="json")
                        if run.prepared.retrieval_topic
                        else None,
                    }
                )
        else:
            st.info(
                "Enter a question and run the pipeline to see an answer, "
                "sources and practice availability."
            )
    with report_tab:
        run = st.session_state.get("qa-run")
        if isinstance(run, QuestionRun):
            render_report(run, corpus, directory, enabled)
        else:
            st.info("Run a question first. Reports are derived from recorded practice events.")


if __name__ == "__main__":
    main()
