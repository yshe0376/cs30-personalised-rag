"""Acceptance and boundary regressions for the M7 follow-up tasks."""

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from cs30.concept_check.event_store import JsonlEventStore
from cs30.concept_check.fixtures import (
    FIXTURE_CORPUS_HASH,
    FIXTURE_CORPUS_VERSION,
    FIXTURE_TOPIC_REGISTRY_VERSION,
    fixture_retrieval_result,
    load_fixture_chunk_topic_map,
    load_fixture_manifest,
    load_fixture_releases,
    load_fixture_scenarios,
    load_fixture_topic_registry,
)
from cs30.concept_check.learner_state import EventReplayer
from cs30.concept_check.provider import FixtureQuestionProvider
from cs30.concept_check.service import ConceptCheckService
from cs30.concept_check.topics import ChunkTopicResolver
from cs30.v2.config import ConceptCheckConfig
from cs30.v2.contracts import (
    ConceptCheckEventType,
    ConceptCheckSelection,
    GeneratedAnswer,
    StudentLevel,
    StudentProfile,
    TopicResolution,
    TopicResolutionStatus,
    ValidatedAnswer,
)
from cs30.v2.ports import TopicResolver
from cs30.v2.topics import LoadedChunkTopicMap

PROFILE = StudentProfile(profile_id="m7-student", level=StudentLevel.BEGINNER, confidence=0.8)
TIME = datetime(2026, 10, 11, tzinfo=UTC)


def force_release():
    return next(r for r in load_fixture_releases() if r.question.topic_id == "newtons-second-law")


def runtime(tmp_path, *, releases=None, resolver=None, enabled=True):
    config = ConceptCheckConfig(enabled=enabled)
    replayer = EventReplayer(PROFILE, load_fixture_topic_registry(), config)
    store = JsonlEventStore(tmp_path, replayer)
    service = ConceptCheckService(
        config=config,
        resolver=resolver
        or ChunkTopicResolver(
            load_fixture_chunk_topic_map(), load_fixture_topic_registry(), config
        ),
        provider=FixtureQuestionProvider(load_fixture_releases() if releases is None else releases),
        event_store=store,
        replayer=replayer,
    )
    return service, store, replayer


def submit(service, attempt_id, *, release=None, choice="correct"):
    release = release or force_release()
    return service.submit(
        release,
        attempt_id=attempt_id,
        selected_choice=release.question.correct_answer if choice == "correct" else choice,
        event_id=f"submit:{attempt_id}",
        corpus_version=FIXTURE_CORPUS_VERSION,
        corpus_hash=FIXTURE_CORPUS_HASH,
        created_at=TIME,
    )[1]


@pytest.mark.parametrize("scenario", load_fixture_scenarios(), ids=lambda s: s.scenario_id)
def test_resolver_implements_protocol_and_shared_fixture_decisions(scenario, monkeypatch):
    loaded = load_fixture_chunk_topic_map()
    resolver = ChunkTopicResolver(loaded, load_fixture_topic_registry(), ConceptCheckConfig())
    assert isinstance(resolver, TopicResolver)

    def unexpected_validation(*args, **kwargs):
        raise AssertionError("the adapter must not revalidate the loaded map")

    monkeypatch.setattr("cs30.v2.topics.validate_chunk_topic_map", unexpected_validation)
    monkeypatch.setattr("cs30.v2.topics._validate_chunk_topic_map_identity", unexpected_validation)
    retrieval = resolver.resolve_retrieval_topic(scenario.retrieval())
    cited = resolver.resolve_cited_topic(scenario.retrieval(), scenario.validated_answer())
    assert (retrieval.topic_id, retrieval.error_code) == (
        scenario.expected_retrieval_topic,
        scenario.expected_retrieval_error,
    )
    assert (cited.topic_id, cited.error_code) == (
        scenario.expected_cited_topic,
        scenario.expected_cited_error,
    )


def test_configured_support_changes_both_resolution_paths():
    retrieval = fixture_retrieval_result(("fixture-cp2e-ch4-p2", "fixture-cp2e-ch2-p1"))
    cited = ValidatedAnswer(
        answer=GeneratedAnswer(
            explanation="fixture", citations=tuple(h.chunk_id for h in retrieval.hits)
        ),
        citation_status="passed",
        resolved_citations=tuple(h.chunk_id for h in retrieval.hits),
    )
    for threshold, expected in ((0.5, "resolved"), (0.8, "no_topic_available")):
        resolver = ChunkTopicResolver(
            load_fixture_chunk_topic_map(),
            load_fixture_topic_registry(),
            ConceptCheckConfig(min_topic_support=threshold),
        )
        for result in (
            resolver.resolve_retrieval_topic(retrieval),
            resolver.resolve_cited_topic(retrieval, cited),
        ):
            assert result.status.value == expected
            assert result.support == pytest.approx(2 / 3)
            if threshold == 0.8:
                assert result.error_code == "TOPIC_SUPPORT_BELOW_THRESHOLD"


@pytest.mark.parametrize("code", ["TOPIC_MAP_UNAVAILABLE", "TOPIC_MAP_MISMATCH"])
def test_map_failure_survives_adapter_and_selection(tmp_path, code):
    loaded = LoadedChunkTopicMap.unavailable(manifest=load_fixture_manifest(), error_code=code)
    resolver = ChunkTopicResolver(loaded, load_fixture_topic_registry(), ConceptCheckConfig())
    service, _, _ = runtime(tmp_path, resolver=resolver)
    scenario = load_fixture_scenarios()[0]
    assert (
        resolver.resolve_cited_topic(scenario.retrieval(), scenario.validated_answer()).error_code
        == code
    )
    prepared = service.prepare(scenario.retrieval(), PROFILE)
    result = service.select(prepared, scenario.retrieval(), scenario.validated_answer())
    assert result == ConceptCheckSelection(status="no_topic_available", error_code=code)
    assert (
        service.select(prepared, scenario.retrieval(), scenario.validated_answer()).question is None
    )


def test_missing_map_and_wrong_retrieval_corpus_report_distinct_errors():
    scenario = load_fixture_scenarios()[0]
    resolver = ChunkTopicResolver(None, load_fixture_topic_registry(), ConceptCheckConfig())
    assert (
        resolver.resolve_retrieval_topic(scenario.retrieval()).error_code == "TOPIC_MAP_UNAVAILABLE"
    )
    resolver.topic_map = load_fixture_chunk_topic_map()
    retrieval = scenario.retrieval()
    mismatched = retrieval.model_copy(
        update={
            "provenance": retrieval.provenance.model_copy(update={"corpus_hash": "sha256:other"})
        }
    )
    assert resolver.resolve_retrieval_topic(mismatched).error_code == "TOPIC_MAP_MISMATCH"
    assert (
        resolver.resolve_cited_topic(mismatched, scenario.validated_answer()).error_code
        == "TOPIC_MAP_MISMATCH"
    )


@pytest.mark.parametrize(
    "scenario",
    [s for s in load_fixture_scenarios() if s.scenario_id in {"topic-tie", "unmapped-chunk"}],
    ids=lambda s: s.scenario_id,
)
def test_unresolved_retrieval_never_calls_cited_resolver(tmp_path, scenario, monkeypatch):
    service, _, _ = runtime(tmp_path)
    prepared = service.prepare(scenario.retrieval(), PROFILE)

    def unexpected(*args):
        raise AssertionError("cited resolver must not run after unresolved retrieval")

    monkeypatch.setattr(service.resolver, "resolve_cited_topic", unexpected)
    result = service.select(prepared, scenario.retrieval(), scenario.validated_answer())
    assert result.status == "no_topic_available"
    assert result.error_code == scenario.expected_retrieval_error


@pytest.mark.parametrize("failure", ["abstained", "invalid", "no_citations"])
def test_unusable_answers_explain_no_question_before_cited_resolution(
    tmp_path, failure, monkeypatch
):
    service, _, _ = runtime(tmp_path)
    scenario = load_fixture_scenarios()[0]
    prepared = service.prepare(scenario.retrieval(), PROFILE)
    validated = scenario.validated_answer()
    if failure == "abstained":
        validated = ValidatedAnswer(
            answer=GeneratedAnswer(explanation="no answer", abstained=True),
            citation_status="passed",
        )
    elif failure == "invalid":
        validated = validated.model_copy(update={"citation_status": "failed"})
    else:
        validated = validated.model_copy(update={"resolved_citations": ()})

    def unexpected(*args):
        raise AssertionError("unusable answers must not call the cited resolver")

    monkeypatch.setattr(service.resolver, "resolve_cited_topic", unexpected)
    result = service.select(prepared, scenario.retrieval(), validated)
    assert result.status == "no_question_available"
    assert (
        result.error_code
        == {
            "abstained": "ANSWER_ABSTAINED",
            "invalid": "CITATION_VALIDATION_FAILED",
            "no_citations": "NO_CITATIONS",
        }[failure]
    )


def test_cited_topic_can_be_unresolved_after_resolved_retrieval(tmp_path):
    service, _, _ = runtime(tmp_path)
    retrieval = fixture_retrieval_result(("fixture-cp2e-ch4-p2", "fixture-cp2e-ch4-p1"))
    prepared = service.prepare(retrieval, PROFILE)
    cited = ValidatedAnswer(
        answer=GeneratedAnswer(explanation="fixture", citations=("fixture-cp2e-ch4-p1",)),
        citation_status="passed",
        resolved_citations=("fixture-cp2e-ch4-p1",),
    )
    assert prepared.retrieval_topic.status is TopicResolutionStatus.RESOLVED
    assert service.select(prepared, retrieval, cited) == ConceptCheckSelection(
        status="no_topic_available", error_code="TOPIC_TIE"
    )


def test_selection_filters_stale_registry_before_offering_valid_fallback(tmp_path):
    release = force_release()
    stale_question = release.question.model_copy(
        update={"question_id": "aaa-stale", "topic_registry_version": "old-topics"}
    )
    stale = release.model_copy(
        update={
            "question": stale_question,
            "binding": release.binding.model_copy(update={"question_id": "aaa-stale"}),
        }
    )
    service, _, _ = runtime(tmp_path, releases=(stale, release))
    scenario = load_fixture_scenarios()[0]
    prepared = service.prepare(scenario.retrieval(), PROFILE)
    result = service.select(prepared, scenario.retrieval(), scenario.validated_answer())
    assert result == ConceptCheckSelection(status="offered", question=release)
    assert (
        service.select(prepared, scenario.retrieval(), scenario.validated_answer()).question
        == release
    )
    service.provider = FixtureQuestionProvider((stale,))
    assert (
        service.select(prepared, scenario.retrieval(), scenario.validated_answer()).status
        == "no_question_available"
    )


def test_selection_excludes_revoked_questions_and_preserves_cited_topic(tmp_path):
    service, _, _ = runtime(tmp_path)
    scenario = next(s for s in load_fixture_scenarios() if s.scenario_id == "cited-topic-differs")
    prepared = service.prepare(scenario.retrieval(), PROFILE)
    result = service.select(prepared, scenario.retrieval(), scenario.validated_answer())
    assert result.status == "offered" and result.question.question.topic_id == "acceleration"
    submit(service, "a", release=result.question)
    service.revoke("a", event_id="revoke:a")
    again = service.select(prepared, scenario.retrieval(), scenario.validated_answer())
    assert again.status == "offered"
    assert again.question.question.question_id == "cc-fixture-002"


def test_disabled_controls_and_selection_touch_no_dependencies():
    service = ConceptCheckService(
        config=ConceptCheckConfig(), resolver=None, provider=None, event_store=None, replayer=None
    )
    assert service.select(None, None, None) == ConceptCheckSelection(status="disabled")
    assert service.select(None, None, None).question is None
    with pytest.raises(ValueError, match="disabled"):
        service.revoke("a", event_id="r")
    with pytest.raises(ValueError, match="disabled"):
        service.override_level("topic", StudentLevel.ADVANCED, reason="correction", event_id="o")


def test_revoke_restores_topic_state_and_retries_without_duplicate_events(tmp_path):
    service, store, _ = runtime(tmp_path)
    before = submit(service, "a1")
    submit(service, "a2")
    revoked = service.revoke("a2", event_id="r", created_at=TIME)
    topic = force_release().question.topic_id
    assert revoked.topics[topic] == before.topics[topic]
    assert revoked.state_version == 3
    event = store.events(PROFILE.profile_id)[-1]
    assert event.event_type is ConceptCheckEventType.ATTEMPT_REVOKED
    assert event.topic_id == topic and event.revoked_attempt_id == "a2"
    assert event.actor == "student"
    assert service.revoke("a2", event_id="r", created_at=TIME + timedelta(days=1)) == revoked
    assert len(store.events(PROFILE.profile_id)) == 3


def test_revoke_rejects_older_repeated_missing_skipped_attempts_and_conflicting_retry(tmp_path):
    service, store, _ = runtime(tmp_path)
    submit(service, "a1")
    submit(service, "a2")
    submit(service, "skip", choice=None)
    for attempt, message in (
        ("a1", "most recent"),
        ("missing", "existing submitted"),
        ("skip", "existing submitted"),
    ):
        with pytest.raises(ValueError, match=message):
            service.revoke(attempt, event_id=f"r:{attempt}")
    service.revoke("a2", event_id="r")
    with pytest.raises(ValueError, match="already revoked"):
        service.revoke("a2", event_id="r2")
    with pytest.raises(ValueError, match="idempotency conflict"):
        service.revoke("a1", event_id="r")
    assert len(store.events(PROFILE.profile_id)) == 4


def test_latest_revocation_is_per_topic_and_survives_restart(tmp_path):
    service, store, replayer = runtime(tmp_path)
    force = force_release()
    acceleration = next(r for r in load_fixture_releases() if r.question.topic_id == "acceleration")
    submit(service, "force", release=force)
    other_state = submit(service, "acceleration", release=acceleration)
    revoked = service.revoke("force", event_id="r")
    assert (
        revoked.topics[acceleration.question.topic_id]
        == other_state.topics[acceleration.question.topic_id]
    )
    assert revoked.topics[force.question.topic_id].total_attempts == 0
    restarted = JsonlEventStore(tmp_path, replayer)
    assert replayer.replay(restarted.events(PROFILE.profile_id)) == revoked
    assert len(next(tmp_path.glob("*.jsonl")).read_bytes().splitlines()) == len(
        store.events(PROFILE.profile_id)
    )


def test_override_resets_mastery_and_window_but_keeps_history_and_retry_is_idempotent(tmp_path):
    service, store, _ = runtime(tmp_path)
    before = submit(service, "a")
    topic = force_release().question.topic_id
    overridden = service.override_level(
        topic, StudentLevel.ADVANCED, reason="I know this topic", event_id="o", created_at=TIME
    )
    state = overridden.topics[topic]
    assert state.level is StudentLevel.ADVANCED
    assert state.mastery_score == 0.5
    assert state.attempt_coverage == state.attempts_since_level_change == 0
    assert state.total_attempts == before.topics[topic].total_attempts
    assert state.correct_attempts == before.topics[topic].correct_attempts
    assert (
        service.override_level(
            topic,
            StudentLevel.ADVANCED,
            reason="I know this topic",
            event_id="o",
            created_at=TIME + timedelta(days=1),
        )
        == overridden
    )
    for changes in ({"reason": "different"}, {"new_level": StudentLevel.INTERMEDIATE}):
        args = (
            dict(
                topic_id=topic,
                new_level=StudentLevel.ADVANCED,
                reason="I know this topic",
                event_id="o",
            )
            | changes
        )
        with pytest.raises(ValueError, match="idempotency conflict"):
            service.override_level(**args)
    assert len(store.events(PROFILE.profile_id)) == 2
    assert store.events(PROFILE.profile_id)[-1].actor == "student"
    after = submit(service, "after")
    assert after.topics[topic].attempts_since_level_change == 1


@pytest.mark.parametrize("reason", ["", "   "])
def test_override_requires_reason_before_writing(tmp_path, reason):
    service, store, _ = runtime(tmp_path)
    with pytest.raises(ValidationError):
        service.override_level("acceleration", StudentLevel.BEGINNER, reason=reason, event_id="o")
    assert store.events(PROFILE.profile_id) == ()


def test_resolved_registry_mismatch_becomes_structured_refusal(tmp_path):
    class WrongRegistry:
        def resolve_retrieval_topic(self, retrieval):
            return TopicResolution(
                status="resolved",
                topic_id="acceleration",
                topic_registry_version="old",
                support=1.0,
            )

        def resolve_cited_topic(self, retrieval, validated):
            raise AssertionError("must stop before cited resolution")

    service, _, _ = runtime(tmp_path, resolver=WrongRegistry())
    scenario = load_fixture_scenarios()[0]
    prepared = service.prepare(scenario.retrieval(), PROFILE)
    assert service.select(
        prepared, scenario.retrieval(), scenario.validated_answer()
    ) == ConceptCheckSelection(status="no_topic_available", error_code="TOPIC_REGISTRY_MISMATCH")


def test_selection_rejects_inconsistent_result_objects():
    with pytest.raises(ValueError):
        ConceptCheckSelection(status="offered")
    with pytest.raises(ValueError):
        ConceptCheckSelection(status="disabled", question=load_fixture_releases()[0])
    with pytest.raises(ValueError):
        ConceptCheckSelection(
            status="offered", question=load_fixture_releases()[0], error_code="NO_USABLE_QUESTION"
        )


@pytest.mark.parametrize("existing", [False, True])
def test_unknown_topic_override_never_changes_the_log_or_state(tmp_path, existing):
    service, store, replayer = runtime(tmp_path)
    if existing:
        submit(service, "valid")
    before_events = store.events(PROFILE.profile_id)
    before_state = replayer.replay(before_events)
    before_files = {p.name: p.read_bytes() for p in tmp_path.glob("*.jsonl")}
    with pytest.raises(ValueError, match="unknown Topic"):
        service.override_level(
            "newtons-secnd-law-TYPO",
            StudentLevel.ADVANCED,
            reason="student correction",
            event_id="unknown-override",
        )
    assert store.events(PROFILE.profile_id) == before_events
    assert replayer.replay(before_events) == before_state
    assert {p.name: p.read_bytes() for p in tmp_path.glob("*.jsonl")} == before_files


@pytest.mark.parametrize("kind", ["submitted", "skipped", "override", "revoked"])
def test_unknown_topic_is_rejected_by_store_and_replayer(tmp_path, kind):
    service, store, replayer = runtime(tmp_path)
    submit(service, "valid")
    if kind == "skipped":
        submit(service, "skip", choice=None)
    elif kind == "override":
        service.override_level(
            "acceleration", StudentLevel.ADVANCED, reason="correction", event_id="override"
        )
    elif kind == "revoked":
        service.revoke("valid", event_id="revoke")
    events = store.events(PROFILE.profile_id)
    invalid = events[-1].model_copy(
        update={
            "topic_id": "unknown-topic",
            "event_id": "bad",
            "attempt_id": "bad-attempt" if kind in {"submitted", "skipped"} else None,
        }
    )
    before = {p.name: p.read_bytes() for p in tmp_path.glob("*.jsonl")}
    with pytest.raises(ValueError, match="unknown Topic"):
        store.append(invalid)
    with pytest.raises(ValueError, match="unknown Topic"):
        replayer.replay((*events[:-1], invalid))
    assert {p.name: p.read_bytes() for p in tmp_path.glob("*.jsonl")} == before


def test_unknown_topic_in_existing_log_is_reported_without_rewriting_it(tmp_path):
    import json

    service, store, replayer = runtime(tmp_path)
    submit(service, "valid")
    event = store.events(PROFILE.profile_id)[0].model_copy(update={"topic_id": "old-typo"})
    path = next(tmp_path.glob("*.jsonl"))
    payload = (json.dumps(event.model_dump(mode="json")) + "\n").encode()
    path.write_bytes(payload)
    with pytest.raises(ValueError, match="unknown Topic"):
        replayer.replay(store.events(PROFILE.profile_id))
    with pytest.raises(ValueError, match="unknown Topic"):
        service.override_level(
            "acceleration", StudentLevel.BEGINNER, reason="correction", event_id="new"
        )
    assert path.read_bytes() == payload


def test_selection_error_codes_are_shared_and_round_trip_as_stable_strings():
    from cs30.v2.contracts import ConceptCheckErrorCode, ConceptCheckSelectionStatus

    result = ConceptCheckSelection(status="no_topic_available", error_code="TOPIC_TIE")
    assert result.status is ConceptCheckSelectionStatus.NO_TOPIC_AVAILABLE
    assert result.error_code is ConceptCheckErrorCode.TOPIC_TIE
    assert ConceptCheckSelection.model_validate_json(result.model_dump_json()) == result
    assert result.model_dump(mode="json")["error_code"] == "TOPIC_TIE"
    with pytest.raises(ValidationError):
        ConceptCheckSelection(status="no_topic_available", error_code="misspelled-code")
    with pytest.raises(ValidationError):
        ConceptCheckSelection(status="no_topic_available")


def test_unknown_topic_from_resolver_cannot_enter_a_snapshot(tmp_path):
    class UnknownResolver:
        def resolve_retrieval_topic(self, retrieval):
            return TopicResolution(
                status="resolved",
                topic_id="typo",
                support=1.0,
                topic_registry_version=FIXTURE_TOPIC_REGISTRY_VERSION,
            )

    service, _, _ = runtime(tmp_path, resolver=UnknownResolver())
    scenario = load_fixture_scenarios()[0]
    prepared = service.prepare(scenario.retrieval(), PROFILE)
    assert prepared.snapshot.topic_id is None
    selection = service.select(prepared, scenario.retrieval(), scenario.validated_answer())
    assert selection.error_code == "UNKNOWN_TOPIC"
