"""Presentation helpers for the unified API learning demo."""

from __future__ import annotations

import uuid

import streamlit as st

from cs30.learning.assets import SetupReport
from cs30.learning.models import LearningTurn, OnlineQuizView, PracticeResult
from cs30.v2.contracts import StudentLevel, TopicResolutionStatus

from .math_markdown import format_math_markdown


def render_setup_report(report: SetupReport) -> None:
    st.subheader("Local setup checks")
    for check in report.checks:
        if check.passed:
            st.success(f"{check.name}: {check.detail}")
        elif check.blocking:
            st.error(f"{check.name}: {check.detail}")
        else:
            st.warning(f"{check.name}: {check.detail}")


def render_answer(turn: LearningTurn, corpus, *, show_sources: bool = True) -> None:
    st.markdown("### Answer")
    if turn.status == "failed":
        st.error(turn.error or "This answer could not be completed.")
        return
    if turn.validated_answer is None:
        st.info("Waiting for an answer.")
        return
    answer = turn.validated_answer.answer
    st.markdown(format_math_markdown(answer.explanation))
    if turn.validated_answer.citation_status == "failed":
        st.error("The answer citations failed local validation. A refusal has been displayed.")
        return
    if show_sources:
        render_sources(turn, corpus)


def render_sources(turn: LearningTurn, corpus) -> None:
    """Display the answer's actual validated citations in M8's source card."""
    st.markdown("### Textbook evidence")
    if turn.validated_answer is None:
        st.caption("Sources appear after an answer is generated.")
        return
    hit_by_id = {
        hit.chunk_id: hit
        for hit in (turn.reranked_retrieval.hits if turn.reranked_retrieval else ())
    }
    if not turn.validated_answer.resolved_citations:
        st.caption("No textbook citations passed validation for this answer.")
    for index, chunk_id in enumerate(turn.validated_answer.resolved_citations, 1):
        chunk = corpus.chunks_by_id.get(chunk_id)
        hit = hit_by_id.get(chunk_id)
        if chunk is None:
            continue
        label = f"[{index}] {chunk.source_name} · {chunk.chapter_id}"
        if chunk.page_or_location:
            label += f" · {chunk.page_or_location}"
        with st.expander(label):
            st.caption(f"chunk_id: {chunk.chunk_id}")
            st.write(chunk.text)
            if hit is not None:
                st.caption(
                    f"Hybrid RRF score: {hit.score:.4f} · Personalized evidence rank: {hit.rank}"
                )


def render_quiz(view: OnlineQuizView, result: PracticeResult | None, record=None) -> None:
    selection_trace = getattr(view, "topic_selection_trace", None)
    textbook_only = getattr(view, "generation_basis", "topic") == "textbook"
    if textbook_only:
        st.info(
            "Textbook-based practice: no usable mapped Topic was found. This question uses "
            "the answer's validated textbook passages and does not change Topic mastery or level."
        )
        if selection_trace is not None:
            with st.expander("Topic lookup details"):
                _render_topic_selection_trace(selection_trace)
    elif selection_trace is not None:
        _render_topic_selection_trace(selection_trace)
    elif view.topic_id:
        st.caption(f"Topic ID: `{view.topic_id}`")
    else:
        candidate_topic_ids = getattr(view, "candidate_topic_ids", ())
        if candidate_topic_ids:
            candidates = "`, `".join(candidate_topic_ids)
            st.caption(f"Candidate Topic IDs: `{candidates}`")

    if view.status in {"unavailable", "interrupted", "expired"}:
        st.info(view.notice)
        return
    if view.status == "pending":
        st.info(view.notice)
        return
    if view.status == "offered":
        st.caption(view.notice)
        if view.topic_id:
            difficulty = view.difficulty.value if view.difficulty else "—"
            st.caption(f"Difficulty: {difficulty}")
        if view.evidence_labels:
            st.caption("Textbook sources: " + "; ".join(view.evidence_labels))
        st.markdown(format_math_markdown(view.question or ""))
        # Keep the radio outside a form: selecting it must rerun the page so
        # the initially disabled Submit button becomes enabled in a browser.
        with st.container(key=f"cc-options-learning-{view.practice_id}"):
            choice = st.radio(
                "Choose one answer",
                options=["A", "B", "C", "D"],
                index=None,
                format_func=lambda label: format_math_markdown(
                    f"{label}. {view.options.get(label, '')}"
                ).replace("$$", "$" ).replace("\n", " "),
                key=f"choice-{view.practice_id}",
            )
        submit_column, skip_column = st.columns(2)
        submitted = submit_column.button(
            "Submit answer", type="primary", disabled=choice is None,
            key=f"submit-{view.practice_id}", use_container_width=True,
        )
        if submitted:
            st.session_state["learning_submit_choice"] = {
                "practice_id": view.practice_id,
                "choice": choice,
                "turn_id": view.turn_id,
            }
        if skip_column.button(
            "Skip this question", key=f"skip-{view.practice_id}", use_container_width=True,
        ):
            st.session_state["learning_submit_choice"] = {
                "practice_id": view.practice_id,
                "choice": None,
                "turn_id": view.turn_id,
            }
        return
    if result is None or record is None:
        st.info(view.notice)
        return
    question = record.question
    st.caption(view.notice)
    st.markdown(format_math_markdown(question.question))
    columns = st.columns(2)
    for index, (label, option) in enumerate(question.options.items()):
        with columns[index % 2], st.container(border=True):
            st.markdown(format_math_markdown(f"**{label}** — {option}"))
    st.write(f"Your answer: {result.grade.selected_choice or 'Skipped'}")
    if result.grade.result.value == "correct":
        st.success("Correct.")
    elif result.grade.result.value == "incorrect":
        st.warning("That answer is incorrect.")
    else:
        st.info("This question was skipped and does not update mastery.")
    st.markdown(format_math_markdown(
        f"Correct answer: {result.correct_answer}. {question.options[result.correct_answer]}"
    ))
    st.markdown(format_math_markdown(result.explanation))
    with st.expander("Textbook evidence for this answer"):
        for span in question.evidence_anchors:
            st.write(span.verbatim_text)
            st.caption(f"{span.textbook_id} · Chapter {span.chapter_id}")
    if result.topic_id is None:
        st.caption("Practice result saved. Topic mastery and levels were not changed.")
    else:
        st.caption(
            f"Topic level: {result.level_before.value} → {result.level_after.value} · "
            f"Profile event version: {result.learner_state.state_version}. "
            "Mastery can change even when the level stays the same."
        )


def _render_topic_selection_trace(trace) -> None:
    st.markdown("**Cited Topic selection**")
    st.caption(
        "Rank-weighted citation Topic support is separate from M6 Dense/BM25 retrieval weights "
        "and the reranking lambda."
    )
    if trace.candidates:
        for candidate in trace.candidates:
            evidence_count = len(candidate.sufficient_evidence_chunk_ids)
            eligibility = (
                f"eligible · {evidence_count} qualifying cited chunk(s)"
                if candidate.eligible
                else "not eligible · no sufficient direct cited evidence"
            )
            st.write(
                f"`{candidate.topic_id}` · support {candidate.rank_weighted_support:.3f} · "
                f"{eligibility}"
            )
    else:
        st.caption("No approved Demo Topic appeared in the validated citations.")

    if trace.selected_topic_id:
        method = trace.selection_method.replace("_", " ")
        st.success(f"Selected Topic ID: `{trace.selected_topic_id}` · {method}")
    elif trace.failure_reason:
        st.info(trace.failure_reason)

    with st.expander("Topic selection audit details"):
        st.write(f"Policy: {trace.policy_version} · {trace.policy_validation_status}")
        st.write(f"RNG seed: {trace.rng_seed}")
        if trace.rng_draw is not None:
            st.write(f"Weighted draw: {trace.rng_draw:.12f}")
        st.caption(trace.minimum_evidence_rule)
        st.caption(trace.support_definition)
        st.write(
            f"Resolver status: {trace.resolver_status} · {trace.resolver_error_code or 'none'}"
        )
        for item in trace.cited_evidence:
            topic_ids = ", ".join(item.topic_ids) or "unmapped"
            st.caption(f"{item.chunk_id} · rank {item.rank or 'unavailable'} · {topic_ids}")


def _profile_topic_ids(runtime) -> list[str]:
    """Prefer actual quiz Topics, then retrieval and previously practiced Topics."""
    turn = runtime.active_turn
    candidates = []
    if turn:
        candidates.extend(
            view.topic_id for _, view in sorted(turn.quizzes.items(), reverse=True)
            if view.topic_id
        )
        topic = turn.retrieval_topic
        if topic and topic.status is TopicResolutionStatus.RESOLVED and topic.topic_id:
            candidates.append(topic.topic_id)
    candidates.extend(runtime.learner_state.topics)
    known = {topic.topic_id for topic in runtime.assets.topic_registry.topics}
    return list(dict.fromkeys(topic_id for topic_id in candidates if topic_id in known))


def render_profile_sidebar(runtime, initial_level: StudentLevel) -> None:
    st.sidebar.markdown("## Learner profile")
    st.sidebar.write(f"Starting level: **{runtime.static_profile.level.value}**")
    turn = runtime.active_turn
    topic_ids = _profile_topic_ids(runtime)
    if not topic_ids:
        st.sidebar.info("Generate a Concept Check to display its Topic mastery and level.")
    else:
        titles = {item.topic_id: item.title for item in runtime.assets.topic_registry.topics}
        topic_id = st.sidebar.selectbox(
            "Concept Check Topic", options=topic_ids,
            format_func=lambda value: titles[value],
            key=f"profile-topic-{turn.turn_id if turn else 'history'}-{'|'.join(topic_ids)}",
        )
        state = runtime.learner_state.topics.get(topic_id)
        level = (
            state.level if state else
            runtime.static_profile.topic_levels.get(topic_id, runtime.static_profile.level)
        )
        mastery = state.mastery_score if state else 0.5
        attempts = state.total_attempts if state else 0
        st.sidebar.caption(f"Topic ID: `{topic_id}`")
        st.sidebar.write(f"Level: **{level.value}**")
        st.sidebar.progress(mastery, text=f"Mastery: {mastery:.2f}")
        st.sidebar.caption(f"Graded attempts: {attempts}")
        with st.sidebar.form(f"override-topic-level-{topic_id}-{level.value}"):
            new_level = st.selectbox(
                "Manually adjust this Topic level", options=list(StudentLevel),
                index=list(StudentLevel).index(level),
                format_func=lambda value: value.value,
                key=f"override-level-{topic_id}-{level.value}",
            )
            reason = st.text_input("Reason for the adjustment")
            override = st.form_submit_button("Save level adjustment")
        if override:
            st.session_state["learning_override"] = {
                "topic_id": topic_id, "level": new_level.value, "reason": reason,
                "event_id": f"override-{uuid.uuid4().hex}",
            }

    usage = runtime.request_usage
    st.sidebar.markdown("## API usage")
    st.sidebar.write(f"Saved total: **{usage['used']} / {usage['cap']} requests**")
    if turn:
        st.sidebar.write(f"Current answer: **{turn.api_requests} requests**")
        st.sidebar.caption(
            f"Visible token usage: {turn.input_tokens} input / {turn.output_tokens} output"
        )
    st.sidebar.caption(
        "Failed requests count toward the cap. Refreshing or restarting does not reset it."
    )


def render_personalisation_trace(turn: LearningTurn) -> None:
    if turn.snapshot is None:
        return
    with st.expander("Personalization and run details"):
        st.write(f"Profile source: {turn.snapshot.profile_source.value}")
        st.write(f"Level used for the answer: {turn.snapshot.profile.level.value}")
        st.write(f"Profile event version: {turn.snapshot.state_version}")
        if turn.retrieval_topic is not None:
            st.write(
                f"Retrieval Topic ID: {turn.retrieval_topic.topic_id or 'unresolved'} · "
                f"{turn.retrieval_topic.status.value}"
            )
            if turn.retrieval_topic.topic_support:
                support = ", ".join(
                    f"{topic_id} ({value:.2f})"
                    for topic_id, value in sorted(
                        turn.retrieval_topic.topic_support.items(),
                        key=lambda item: (-item[1], item[0]),
                    )
                )
                st.caption(f"Topic support: {support}")
        if turn.rerank_trace:
            st.write(f"Dev lambda: {turn.rerank_trace.get('lambda_weight')}")
            st.caption(
                "The Role taxonomy is marked as a fixture in this conservative Demo configuration. "
                "M7 outputs have not received independent M8 quality scoring, so personalization "
                "effectiveness is not yet established."
            )
        st.caption(
            f"Retrieval: {turn.retrieval_ms:.0f} ms · "
            f"Answer and citation checks: {turn.generation_ms:.0f} ms"
        )
