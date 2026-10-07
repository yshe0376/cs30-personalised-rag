"""Reusable Streamlit renderer for one published Concept Check question.

The component owns presentation only. Runtime composition, question selection,
grading, event persistence, and learner-state replay stay behind callbacks so a
future v2 answer page can reuse this renderer without copying the quiz logic.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from html import escape
from typing import Literal

import streamlit as st

from cs30.v2.catalog import get_textbook_spec
from cs30.v2.contracts import (
    ConceptCheckEvent,
    ConceptCheckGrade,
    ConceptCheckQuestionRelease,
    ConceptCheckResult,
    LearnerState,
    StudentLevel,
    TopicState,
)

Choice = Literal["A", "B", "C", "D"]


@dataclass(frozen=True)
class QuizAttemptView:
    """Everything the component needs after one immutable attempt."""

    grade: ConceptCheckGrade
    previous_state: LearnerState
    learner_state: LearnerState
    event: ConceptCheckEvent
    baseline_level: StudentLevel


SubmitCallback = Callable[[Choice], QuizAttemptView]
SkipCallback = Callable[[], QuizAttemptView]
NextCallback = Callable[[], None]


def inject_concept_check_styles() -> None:
    """Apply component-scoped styling without changing the v1 application."""

    st.markdown(
        """
        <style>
        :root {
            --cc-orange: #f06f54;
            --cc-orange-dark: #df5b40;
            --cc-ink: #171411;
            --cc-muted: #706a64;
            --cc-line: #e8e4e1;
        }
        .cc-field-title {
            margin: 16px 0 8px;
            color: var(--cc-ink);
            font-size: 1.05rem !important;
            font-weight: 750;
        }
        .cc-answer-review {
            display: grid;
            gap: 7px;
            margin: 10px 0 18px;
        }
        .cc-answer-option {
            padding: 8px 11px;
            border: 1px solid var(--cc-line);
            border-radius: 9px;
            color: #49433e;
            background: #ffffff;
            font-size: .94rem;
        }
        .cc-answer-option.correct {
            border-color: #a9d8bd;
            color: #1f7045;
            background: #edf8f1;
        }
        .cc-answer-option.incorrect {
            border-color: #efb8ac;
            color: #a33e2b;
            background: #fff4f1;
        }
        .cc-state-grid {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 10px;
            margin: 8px 0 16px;
        }
        .cc-state-item {
            padding: 10px 12px;
            border: 1px solid var(--cc-line);
            border-radius: 9px;
            background: #ffffff;
        }
        .cc-state-label {
            display: block;
            margin-bottom: 3px;
            color: var(--cc-muted);
            font-size: .82rem;
        }
        .cc-state-value {
            display: block;
            color: var(--cc-ink);
            font-size: .96rem;
            font-weight: 700;
            line-height: 1.3;
            overflow-wrap: anywhere;
        }
        @media (max-width: 720px) {
            .cc-state-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def clear_quiz_component(key: str) -> None:
    """Clear rendered state while leaving previously persisted events intact."""

    for suffix in ("choice", "question_id", "result"):
        st.session_state.pop(f"{key}:{suffix}", None)


def _topic_state(
    state: LearnerState,
    topic_id: str,
    baseline_level: StudentLevel,
) -> TopicState:
    return state.topics.get(topic_id) or TopicState(topic_id=topic_id, level=baseline_level)


def _render_options(release: ConceptCheckQuestionRelease, grade: ConceptCheckGrade) -> None:
    question = release.question
    rows: list[str] = []
    for choice, option in question.options.items():
        classes = ["cc-answer-option"]
        notes: list[str] = []
        if choice == grade.correct_answer:
            classes.append("correct")
            notes.append("Correct answer")
        if choice == grade.selected_choice:
            notes.append("Your answer")
            if grade.result is ConceptCheckResult.INCORRECT:
                classes.append("incorrect")
        suffix = f" <strong>· {' · '.join(notes)}</strong>" if notes else ""
        rows.append(
            f'<div class="{" ".join(classes)}">'
            f"{escape(choice)} — {escape(option)}{suffix}</div>"
        )
    st.markdown(
        f'<div class="cc-answer-review">{"".join(rows)}</div>',
        unsafe_allow_html=True,
    )


def _render_evidence(release: ConceptCheckQuestionRelease) -> None:
    bindings = {item.span_id: item for item in release.binding.bindings}
    st.markdown('<p class="cc-field-title">Evidence</p>', unsafe_allow_html=True)
    for anchor in release.question.evidence_anchors:
        binding = bindings[anchor.span_id]
        textbook = get_textbook_spec(anchor.textbook_id)
        with st.container(border=True):
            st.write(anchor.verbatim_text)
            st.caption(
                f"Textbook: {textbook.title} · Chapter {anchor.chapter_id} · "
                f"Chunk(s): {', '.join(binding.chunk_ids)}"
            )


def _render_state_change(release: ConceptCheckQuestionRelease, result: QuizAttemptView) -> None:
    topic_id = release.question.topic_id
    before = _topic_state(result.previous_state, topic_id, result.baseline_level)
    after = _topic_state(result.learner_state, topic_id, result.baseline_level)
    values = (
        ("Topic level", f"{before.level.value.title()} → {after.level.value.title()}"),
        ("Mastery", f"{before.mastery_score:.2f} → {after.mastery_score:.2f}"),
        ("Scored attempts", f"{before.total_attempts} → {after.total_attempts}"),
        ("Correct", f"{before.correct_attempts} → {after.correct_attempts}"),
    )
    items = "".join(
        '<div class="cc-state-item">'
        f'<span class="cc-state-label">{escape(label)}</span>'
        f'<span class="cc-state-value">{escape(value)}</span>'
        "</div>"
        for label, value in values
    )
    st.markdown('<p class="cc-field-title">Learner state change</p>', unsafe_allow_html=True)
    st.markdown(f'<div class="cc-state-grid">{items}</div>', unsafe_allow_html=True)


def _render_result(
    release: ConceptCheckQuestionRelease,
    result: QuizAttemptView,
) -> None:
    grade = result.grade
    question = release.question
    st.markdown('<p class="cc-field-title">Quiz result</p>', unsafe_allow_html=True)
    st.write(question.question)
    _render_options(release, grade)

    if grade.result is ConceptCheckResult.CORRECT:
        st.success("Correct — this scored attempt was recorded.")
    elif grade.result is ConceptCheckResult.INCORRECT:
        st.error(
            f"Incorrect. The correct answer is {grade.correct_answer}: "
            f"{question.options[grade.correct_answer]}"
        )
    else:
        st.warning("Skipped — the event was recorded, but it is not counted as a scored attempt.")

    st.markdown('<p class="cc-field-title">Explanation</p>', unsafe_allow_html=True)
    st.write(question.rationale)
    _render_evidence(release)
    _render_state_change(release, result)

    with st.expander("Attempt record"):
        st.json(result.event.model_dump(mode="json"))


def render_quiz(
    release: ConceptCheckQuestionRelease,
    *,
    on_submit: SubmitCallback,
    on_skip: SkipCallback,
    on_next: NextCallback | None = None,
    key: str = "concept-check-quiz",
) -> QuizAttemptView | None:
    """Render one reusable A–D quiz and invoke the supplied persistence callbacks.

    The correct answer, rationale, and evidence are rendered only after submit
    or skip. The component never calls an LLM and never constructs a service or
    event store itself.
    """

    inject_concept_check_styles()
    question = release.question
    question_key = f"{key}:question_id"
    if st.session_state.get(question_key) != question.question_id:
        clear_quiz_component(key)
        st.session_state[question_key] = question.question_id

    stored = st.session_state.get(f"{key}:result")
    if isinstance(stored, QuizAttemptView):
        _render_result(release, stored)
        if on_next is not None and st.button(
            "Next question",
            key=f"{key}:next",
            type="primary",
            use_container_width=True,
        ):
            on_next()
            st.rerun()
        return stored

    st.markdown('<p class="cc-field-title">Quick check</p>', unsafe_allow_html=True)
    st.write(question.question)
    selected = st.radio(
        "Concept Check answer",
        options=list(question.options),
        index=None,
        format_func=lambda choice: f"{choice} — {question.options[choice]}",
        key=f"{key}:choice",
        label_visibility="collapsed",
    )
    submit_column, skip_column = st.columns(2)
    submit = submit_column.button(
        "Submit answer",
        key=f"{key}:submit",
        type="primary",
        use_container_width=True,
        disabled=selected is None,
    )
    skip = skip_column.button("Skip", key=f"{key}:skip", use_container_width=True)
    if not submit and not skip:
        return None

    try:
        result = on_submit(selected) if submit else on_skip()
    except ValueError as exc:
        st.error(f"The attempt could not be recorded: {exc}")
        return None
    if result.grade.question_id != question.question_id:
        raise ValueError("quiz callback returned a grade for a different question")
    st.session_state[f"{key}:result"] = result
    st.rerun()
    return result
