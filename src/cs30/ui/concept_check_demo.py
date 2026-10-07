"""Standalone Streamlit demo for the shared Concept Check fixture runtime."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from tempfile import mkdtemp
from typing import Any
from uuid import uuid4

import streamlit as st

from cs30.concept_check.event_store import JsonlEventStore
from cs30.concept_check.fixtures import (
    FIXTURE_CORPUS_HASH,
    FIXTURE_CORPUS_VERSION,
    FIXTURE_TOPIC_REGISTRY_VERSION,
    FixtureScenario,
    load_fixture_chunk_topic_map,
    load_fixture_releases,
    load_fixture_scenarios,
    load_fixture_topic_registry,
)
from cs30.concept_check.learner_state import EventReplayer
from cs30.concept_check.provider import FixtureQuestionProvider
from cs30.concept_check.service import ConceptCheckService
from cs30.evaluation.concept_check_reporting import (
    build_concept_check_report,
    load_concept_check_events,
    render_concept_check_csv,
    render_concept_check_json,
    render_concept_check_markdown,
)
from cs30.ui.concept_check import Choice, QuizAttemptView, clear_quiz_component, render_quiz
from cs30.v2.config import ConceptCheckConfig
from cs30.v2.contracts import (
    ConceptCheckEvent,
    ConceptCheckQuestionRelease,
    RetrievalResult,
    StudentLevel,
    StudentProfile,
    TopicResolution,
    ValidatedAnswer,
)
from cs30.v2.topics import resolve_topic_from_citations, resolve_topic_from_retrieval

QUIZ_KEY = "concept-check-demo-quiz"
_LOGGER = logging.getLogger(__name__)


class _FixtureTopicResolver:
    """Adapt the shared fixture map to the Concept Check service port."""

    def __init__(self) -> None:
        self.topic_map = load_fixture_chunk_topic_map()
        self.registry = load_fixture_topic_registry()

    def resolve_retrieval_topic(self, retrieval: RetrievalResult) -> TopicResolution:
        return resolve_topic_from_retrieval(retrieval, self.topic_map, self.registry)

    def resolve_cited_topic(
        self,
        retrieval: RetrievalResult,
        validated: ValidatedAnswer,
    ) -> TopicResolution:
        return resolve_topic_from_citations(retrieval, validated, self.topic_map, self.registry)


@dataclass(frozen=True)
class DemoRuntime:
    profile: StudentProfile
    retrieval: RetrievalResult
    validated: ValidatedAnswer
    service: ConceptCheckService
    event_store: JsonlEventStore
    replayer: EventReplayer


def build_demo_runtime(
    *,
    event_directory: Path,
    profile: StudentProfile,
    scenario: FixtureScenario,
) -> DemoRuntime:
    """Compose only the shared deterministic fixture dependencies."""

    replayer = EventReplayer(profile, FIXTURE_TOPIC_REGISTRY_VERSION)
    event_store = JsonlEventStore(event_directory, replayer)
    retrieval = scenario.retrieval()
    validated = scenario.validated_answer()
    service = ConceptCheckService(
        config=ConceptCheckConfig(enabled=True),
        resolver=_FixtureTopicResolver(),
        provider=FixtureQuestionProvider(load_fixture_releases()),
        event_store=event_store,
        replayer=replayer,
    )
    return DemoRuntime(
        profile=profile,
        retrieval=retrieval,
        validated=validated,
        service=service,
        event_store=event_store,
        replayer=replayer,
    )


def select_demo_question(runtime: DemoRuntime) -> ConceptCheckQuestionRelease | None:
    """Call M7's prepare and select seams in their required order."""

    prepared = runtime.service.prepare(runtime.retrieval, runtime.profile)
    return runtime.service.select(prepared, runtime.retrieval, runtime.validated)


def record_demo_attempt(
    runtime: DemoRuntime,
    release: ConceptCheckQuestionRelease,
    selected_choice: Choice | None,
) -> QuizAttemptView:
    """Persist one submit/skip event and expose before/after replay state."""

    events_before = runtime.event_store.events(runtime.profile.profile_id)
    previous_state = runtime.replayer.replay(events_before)
    grade, learner_state = runtime.service.submit(
        release,
        attempt_id=f"attempt-{uuid4().hex}",
        selected_choice=selected_choice,
        event_id=f"event-{uuid4().hex}",
        corpus_version=FIXTURE_CORPUS_VERSION,
        corpus_hash=FIXTURE_CORPUS_HASH,
    )
    event = runtime.event_store.events(runtime.profile.profile_id)[-1]
    return QuizAttemptView(
        grade=grade,
        previous_state=previous_state,
        learner_state=learner_state,
        event=event,
        baseline_level=runtime.profile.level,
    )


def _event_directory() -> Path:
    key = "concept_check_demo_event_directory"
    value = st.session_state.get(key)
    if value is None:
        value = Path(mkdtemp(prefix="cs30-concept-check-demo-"))
        st.session_state[key] = value
    return Path(value)


def _session_token() -> str:
    key = "concept_check_demo_session_token"
    value = st.session_state.get(key)
    if value is None:
        value = uuid4().hex
        st.session_state[key] = value
    return str(value)


def _inject_demo_styles() -> None:
    """Reuse the v1 orange for demo action buttons and the selected quiz option."""

    st.markdown(
        """
        <style>
        div[data-testid="stButton"] > button {
            border-color: #f06f54;
            color: white;
            background: #f06f54;
        }
        div[data-testid="stButton"] > button:hover {
            border-color: #df5b40;
            color: white;
            background: #df5b40;
        }
        label[data-testid="stRadioOption"][data-selected="true"]
        > div > div:first-child {
            border-color: #f06f54;
            background: #f06f54;
        }
        .cc-report-grid {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 9px;
            margin: 8px 0 14px;
        }
        .cc-report-item {
            padding: 8px 10px;
            border: 1px solid #e8e4e1;
            border-radius: 9px;
            background: #ffffff;
        }
        .cc-report-label {
            display: block;
            margin-bottom: 2px;
            color: #706a64;
            font-size: .76rem;
        }
        .cc-report-value {
            display: block;
            color: #171411;
            font-size: 1.12rem;
            font-weight: 700;
            line-height: 1.25;
        }
        @media (max-width: 720px) {
            .cc-report-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _session_events(
    event_directory: Path,
) -> tuple[tuple[ConceptCheckEvent, ...], tuple[str, ...]]:
    events: list[ConceptCheckEvent] = []
    warnings: list[str] = []
    for path in sorted(event_directory.glob("*.jsonl")):
        events.extend(load_concept_check_events(path, on_warning=warnings.append))
    ordered = tuple(sorted(events, key=lambda event: (event.profile_id, event.stream_version)))
    return ordered, tuple(warnings)


def _starting_levels() -> dict[str, StudentLevel]:
    value = st.session_state.get("concept_check_demo_starting_levels")
    return dict(value) if isinstance(value, dict) else {}


def _register_starting_level(profile: StudentProfile) -> None:
    levels = _starting_levels()
    levels[profile.profile_id] = profile.level
    st.session_state["concept_check_demo_starting_levels"] = levels


def _report_signature(events: tuple[ConceptCheckEvent, ...]) -> tuple[str, ...]:
    return tuple(
        json.dumps(event.model_dump(mode="json"), sort_keys=True)
        for event in events
    )


def _display_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []
    for line in render_concept_check_markdown(report).splitlines():
        if line.startswith("## "):
            lines.append(f"##### {line[3:]}")
        elif line.startswith("# "):
            lines.append(f"#### {line[2:]}")
        else:
            lines.append(line)
    return "\n".join(lines)


def _render_session_report_contents(event_directory: Path) -> None:
    events, warnings = _session_events(event_directory)
    if warnings:
        warning = (
            warnings[0]
            if len(warnings) == 1
            else f"{len(warnings)} incomplete records ignored."
        )
        st.warning(warning)
    if not events:
        st.info("Submit or skip at least one quiz to generate the session report.")
        return

    signature = _report_signature(events)
    report = st.session_state.get("concept_check_demo_report")
    if (
        st.session_state.get("concept_check_demo_report_signature") != signature
        or not isinstance(report, dict)
    ):
        report = build_concept_check_report(
            events,
            starting_levels=_starting_levels(),
        )
        st.session_state["concept_check_demo_report"] = report
        st.session_state["concept_check_demo_report_signature"] = signature

    overall = report["overall"]
    values = (
        ("Submitted", str(overall["submitted"])),
        ("Correct", str(overall["correct"])),
        ("Skipped", str(overall["skipped"])),
        ("Revoked", str(overall["revoked"])),
        (
            "Accuracy",
            "n/a" if overall["accuracy"] is None else f"{overall['accuracy']:.3f}",
        ),
        (
            "Skip rate",
            "n/a" if overall["skip_rate"] is None else f"{overall['skip_rate']:.3f}",
        ),
        (
            "Revocation rate",
            "n/a"
            if overall["revocation_rate"] is None
            else f"{overall['revocation_rate']:.3f}",
        ),
    )
    cards = "".join(
        '<div class="cc-report-item">'
        f'<span class="cc-report-label">{label}</span>'
        f'<span class="cc-report-value">{value}</span>'
        "</div>"
        for label, value in values
    )
    st.markdown(f'<div class="cc-report-grid">{cards}</div>', unsafe_allow_html=True)

    with st.expander("Detailed event report", expanded=True):
        st.markdown(_display_markdown(report))

    downloads = st.columns(3)
    downloads[0].download_button(
        "Download CSV",
        data=render_concept_check_csv(report).encode("utf-8"),
        file_name="concept_check_report.csv",
        mime="text/csv",
        use_container_width=True,
    )
    downloads[1].download_button(
        "Download JSON",
        data=render_concept_check_json(report).encode("utf-8"),
        file_name="concept_check_report.json",
        mime="application/json",
        use_container_width=True,
    )
    downloads[2].download_button(
        "Download Markdown",
        data=render_concept_check_markdown(report).encode("utf-8"),
        file_name="concept_check_report.md",
        mime="text/markdown",
        use_container_width=True,
    )


def _render_session_report(event_directory: Path) -> None:
    st.divider()
    st.markdown("### Current session report")
    st.caption(
        "Automatically generated from submit and skip events recorded in this "
        "fixture session."
    )
    try:
        _render_session_report_contents(event_directory)
    except Exception:  # The report must never take down the quiz interaction.
        _LOGGER.exception("Concept Check session report could not be rendered")
        st.warning("The session report is temporarily unavailable. The quiz remains usable.")


def _reset_selection() -> None:
    st.session_state.pop("concept_check_demo_release", None)
    st.session_state.pop("concept_check_demo_selection_trace", None)
    st.session_state.pop("concept_check_demo_no_question", None)
    clear_quiz_component(QUIZ_KEY)


def _scenario_summary(runtime: DemoRuntime, scenario: FixtureScenario) -> None:
    st.markdown("### Simulated previous Q&A scenario")
    st.write(scenario.query)
    st.caption(f"Fixture answer: {scenario.answer}")
    with st.expander("Cited evidence used by the scenario"):
        cited = set(scenario.cited_chunk_ids)
        for hit in runtime.retrieval.hits:
            marker = "cited" if hit.chunk_id in cited else "retrieved"
            st.markdown(f"**{hit.chunk_id} · Chapter {hit.chapter_id} · {marker}**")
            st.write(hit.text)
            st.caption(f"Textbook: {hit.textbook_id} · Source: {hit.source_locator}")


def _select_and_store_question(runtime: DemoRuntime, scenario: FixtureScenario) -> None:
    clear_quiz_component(QUIZ_KEY)
    release = select_demo_question(runtime)
    st.session_state["concept_check_demo_selection_trace"] = {
        "steps": ["prepare", "select"],
        "profile_id": runtime.profile.profile_id,
        "scenario_id": scenario.scenario_id,
        "scenario_title": scenario.title,
        "retrieval_chunk_ids": [hit.chunk_id for hit in runtime.retrieval.hits],
        "selected_question_id": release.question.question_id if release else None,
    }
    if release is None:
        st.session_state["concept_check_demo_no_question"] = True
        st.session_state.pop("concept_check_demo_release", None)
    else:
        st.session_state["concept_check_demo_release"] = release
        st.session_state.pop("concept_check_demo_no_question", None)


def main() -> None:
    """Render the independent M8 fixture demonstration page."""

    st.set_page_config(page_title="Concept Check fixture demo", page_icon="✅", layout="wide")
    _inject_demo_styles()
    st.title("Concept Check demo")
    st.warning("TEST-DATA DEMO — NOT REAL PRACTICE QUESTIONS.")
    st.caption(
        "This standalone page uses published synthetic fixtures and deterministic grading. "
        "It does not call an LLM or alter the v1 question-and-answer page."
    )

    scenarios = load_fixture_scenarios()
    scenarios_by_id = {scenario.scenario_id: scenario for scenario in scenarios}

    control_left, control_right = st.columns(2)
    with control_left:
        level_value = st.selectbox(
            "Starting level",
            options=[level.value for level in StudentLevel],
            index=0,
            key="concept_check_demo_level",
            on_change=_reset_selection,
        )
    with control_right:
        scenario_id = st.selectbox(
            "Simulated previous Q&A scenario",
            options=list(scenarios_by_id),
            format_func=lambda value: scenarios_by_id[value].title,
            key="concept_check_demo_scenario",
            on_change=_reset_selection,
        )
        st.caption(
            "Select fixture context that simulates the answer and cited evidence normally "
            "provided by the future v2 Q&A flow."
        )

    level = StudentLevel(level_value)
    scenario = scenarios_by_id[scenario_id]
    profile = StudentProfile(
        profile_id=f"fixture-demo-{_session_token()}-{level.value}",
        level=level,
    )
    _register_starting_level(profile)
    event_directory = _event_directory()
    runtime = build_demo_runtime(
        event_directory=event_directory,
        profile=profile,
        scenario=scenario,
    )
    _scenario_summary(runtime, scenario)

    if st.button("Quiz me", type="primary", use_container_width=True):
        _select_and_store_question(runtime, scenario)
        st.rerun()

    release = st.session_state.get("concept_check_demo_release")
    if isinstance(release, ConceptCheckQuestionRelease):
        render_quiz(
            release,
            on_submit=lambda choice: record_demo_attempt(runtime, release, choice),
            on_skip=lambda: record_demo_attempt(runtime, release, None),
            on_next=lambda: _select_and_store_question(runtime, scenario),
            key=QUIZ_KEY,
        )
    elif st.session_state.get("concept_check_demo_no_question"):
        st.info(
            "No eligible published fixture question is available for this scenario."
        )

    trace = st.session_state.get("concept_check_demo_selection_trace")
    if isinstance(trace, dict):
        with st.expander("Demo trace"):
            st.json(trace)

    _render_session_report(event_directory)


if __name__ == "__main__":
    main()
