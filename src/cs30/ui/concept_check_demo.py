"""Standalone Streamlit demo for the shared Concept Check fixture runtime."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from tempfile import mkdtemp
from uuid import uuid4

import streamlit as st

from cs30.concept_check.event_store import JsonlEventStore
from cs30.concept_check.fixtures import (
    FIXTURE_CORPUS_HASH,
    FIXTURE_CORPUS_VERSION,
    FIXTURE_TOPIC_REGISTRY_VERSION,
    fixture_retrieval_result,
    load_fixture_releases,
)
from cs30.concept_check.learner_state import EventReplayer
from cs30.concept_check.provider import FixtureQuestionProvider
from cs30.concept_check.service import ConceptCheckService
from cs30.ui.concept_check import Choice, QuizAttemptView, clear_quiz_component, render_quiz
from cs30.v2.config import ConceptCheckConfig
from cs30.v2.contracts import (
    ConceptCheckQuestionRelease,
    GeneratedAnswer,
    RetrievalResult,
    StudentLevel,
    StudentProfile,
    TopicResolution,
    TopicResolutionStatus,
    ValidatedAnswer,
)

QUIZ_KEY = "concept-check-demo-quiz"


@dataclass(frozen=True)
class DemoScenario:
    label: str
    answered_question: str
    answer: str
    chunk_ids: tuple[str, ...]
    cited_chunk_ids: tuple[str, ...]


SCENARIOS = {
    "Acceleration definition": DemoScenario(
        label="Acceleration definition",
        answered_question="What does acceleration tell us about motion?",
        answer="Acceleration describes how velocity changes with time.",
        chunk_ids=("fixture-cp2e-ch2-p1", "fixture-cp2e-ch2-p2"),
        cited_chunk_ids=("fixture-cp2e-ch2-p1",),
    ),
    "Newton's second law": DemoScenario(
        label="Newton's second law",
        answered_question="How does net force affect acceleration?",
        answer="For fixed mass, acceleration is proportional to net force.",
        chunk_ids=("fixture-cp2e-ch4-p1", "fixture-cp2e-ch4-p2"),
        cited_chunk_ids=("fixture-cp2e-ch4-p1",),
    ),
    "Two-block system": DemoScenario(
        label="Two-block system",
        answered_question="How do we analyse two blocks that move together?",
        answer="Treat both blocks as one system, then analyse one block separately.",
        chunk_ids=("fixture-cp2e-ch4-p3", "fixture-cp2e-ch4-p1"),
        cited_chunk_ids=("fixture-cp2e-ch4-p3",),
    ),
}


class FixtureChapterTopicResolver:
    """Temporary chapter resolver copied from the shared fixture test seam."""

    _topics = {"2": "acceleration", "4": "newtons-second-law"}

    def _resolve(self, chapter_id: str) -> TopicResolution:
        topic_id = self._topics.get(chapter_id)
        if topic_id is None:
            return TopicResolution(
                status=TopicResolutionStatus.UNRESOLVED,
                topic_registry_version=FIXTURE_TOPIC_REGISTRY_VERSION,
                support=0.0,
            )
        return TopicResolution(
            status=TopicResolutionStatus.RESOLVED,
            topic_id=topic_id,
            topic_registry_version=FIXTURE_TOPIC_REGISTRY_VERSION,
            support=1.0,
        )

    def resolve_retrieval_topic(self, retrieval: RetrievalResult) -> TopicResolution:
        if not retrieval.hits:
            return self._resolve("")
        return self._resolve(retrieval.hits[0].chapter_id)

    def resolve_cited_topic(
        self,
        retrieval: RetrievalResult,
        validated: ValidatedAnswer,
    ) -> TopicResolution:
        hits = {hit.chunk_id: hit for hit in retrieval.hits}
        if not validated.resolved_citations:
            return self._resolve("")
        cited = hits.get(validated.resolved_citations[0])
        return self._resolve(cited.chapter_id if cited is not None else "")


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
    scenario: DemoScenario,
) -> DemoRuntime:
    """Compose only the shared deterministic fixture dependencies."""

    replayer = EventReplayer(profile, FIXTURE_TOPIC_REGISTRY_VERSION)
    event_store = JsonlEventStore(event_directory, replayer)
    retrieval = fixture_retrieval_result(
        scenario.chunk_ids,
        query=scenario.answered_question,
    )
    validated = ValidatedAnswer(
        answer=GeneratedAnswer(
            explanation=scenario.answer,
            citations=scenario.cited_chunk_ids,
        ),
        citation_status="passed",
        resolved_citations=scenario.cited_chunk_ids,
    )
    service = ConceptCheckService(
        config=ConceptCheckConfig(enabled=True),
        resolver=FixtureChapterTopicResolver(),
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
        </style>
        """,
        unsafe_allow_html=True,
    )


def _reset_selection() -> None:
    st.session_state.pop("concept_check_demo_release", None)
    st.session_state.pop("concept_check_demo_selection_trace", None)
    st.session_state.pop("concept_check_demo_no_question", None)
    clear_quiz_component(QUIZ_KEY)


def _scenario_summary(runtime: DemoRuntime, scenario: DemoScenario) -> None:
    st.markdown("### Simulated previous Q&A scenario")
    st.write(scenario.answered_question)
    st.caption(f"Fixture answer: {scenario.answer}")
    with st.expander("Cited evidence used by the scenario"):
        cited = set(scenario.cited_chunk_ids)
        for hit in runtime.retrieval.hits:
            marker = "cited" if hit.chunk_id in cited else "retrieved"
            st.markdown(f"**{hit.chunk_id} · Chapter {hit.chapter_id} · {marker}**")
            st.write(hit.text)
            st.caption(f"Textbook: {hit.textbook_id} · Source: {hit.source_locator}")


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
        scenario_name = st.selectbox(
            "Simulated previous Q&A scenario",
            options=list(SCENARIOS),
            key="concept_check_demo_scenario",
            on_change=_reset_selection,
        )
        st.caption(
            "Select fixture context that simulates the answer and cited evidence normally "
            "provided by the future v2 Q&A flow."
        )

    level = StudentLevel(level_value)
    scenario = SCENARIOS[scenario_name]
    profile = StudentProfile(
        profile_id=f"fixture-demo-{_session_token()}-{level.value}",
        level=level,
    )
    runtime = build_demo_runtime(
        event_directory=_event_directory(),
        profile=profile,
        scenario=scenario,
    )
    _scenario_summary(runtime, scenario)

    if st.button("Quiz me", type="primary", use_container_width=True):
        clear_quiz_component(QUIZ_KEY)
        release = select_demo_question(runtime)
        st.session_state["concept_check_demo_selection_trace"] = {
            "steps": ["prepare", "select"],
            "profile_id": profile.profile_id,
            "scenario": scenario.label,
            "retrieval_chunk_ids": [hit.chunk_id for hit in runtime.retrieval.hits],
            "selected_question_id": release.question.question_id if release else None,
        }
        if release is None:
            st.session_state["concept_check_demo_no_question"] = True
            st.session_state.pop("concept_check_demo_release", None)
        else:
            st.session_state["concept_check_demo_release"] = release
            st.session_state.pop("concept_check_demo_no_question", None)
        st.rerun()

    release = st.session_state.get("concept_check_demo_release")
    if isinstance(release, ConceptCheckQuestionRelease):
        render_quiz(
            release,
            on_submit=lambda choice: record_demo_attempt(runtime, release, choice),
            on_skip=lambda: record_demo_attempt(runtime, release, None),
            key=QUIZ_KEY,
        )
    elif st.session_state.get("concept_check_demo_no_question"):
        st.info(
            "No eligible published fixture question remains for this scenario. "
            "A more specific reason can be shown after M7 exposes the planned selection-result API."
        )

    trace = st.session_state.get("concept_check_demo_selection_trace")
    if isinstance(trace, dict):
        with st.expander("Demo trace"):
            st.json(trace)


if __name__ == "__main__":
    main()
