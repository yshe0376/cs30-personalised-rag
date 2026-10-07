from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from cs30.evaluation.concept_check_reporting import (
    build_concept_check_report,
    load_concept_check_events,
    main,
    render_concept_check_csv,
    render_concept_check_json,
    write_concept_check_report,
)
from cs30.v2.config import ConceptCheckConfig
from cs30.v2.contracts import ConceptCheckEvent, ConceptCheckEventType, StudentLevel

_TIME = datetime(2026, 1, 1, tzinfo=UTC)


def _event(
    version: int,
    *,
    kind: ConceptCheckEventType,
    attempt_id: str | None = None,
    revoked_attempt_id: str | None = None,
    difficulty: StudentLevel | None = None,
    performance: float | None = None,
    new_level: StudentLevel | None = None,
) -> ConceptCheckEvent:
    submitted = kind is ConceptCheckEventType.ATTEMPT_SUBMITTED
    skipped = kind is ConceptCheckEventType.ATTEMPT_SKIPPED
    return ConceptCheckEvent(
        event_id=f"event-{version}",
        profile_id="student-1",
        attempt_id=attempt_id,
        revoked_attempt_id=revoked_attempt_id,
        question_id=f"question-{version}" if submitted or skipped else None,
        topic_id="acceleration",
        topic_registry_version="topics-1",
        question_difficulty=difficulty,
        new_level=new_level,
        selected_choice="A" if submitted else None,
        performance=performance,
        event_type=kind,
        state_version_before=version - 1,
        stream_version=version,
        created_at=_TIME + timedelta(seconds=version),
        reason="student correction"
        if kind is ConceptCheckEventType.TOPIC_LEVEL_OVERRIDDEN
        else None,
    )


def _events() -> tuple[ConceptCheckEvent, ...]:
    return (
        _event(
            1,
            kind=ConceptCheckEventType.ATTEMPT_SUBMITTED,
            attempt_id="attempt-1",
            difficulty=StudentLevel.BEGINNER,
            performance=1.0,
        ),
        _event(
            2,
            kind=ConceptCheckEventType.ATTEMPT_SKIPPED,
            attempt_id="attempt-skip",
            difficulty=StudentLevel.BEGINNER,
        ),
        _event(
            3,
            kind=ConceptCheckEventType.ATTEMPT_SUBMITTED,
            attempt_id="attempt-2",
            difficulty=StudentLevel.INTERMEDIATE,
            performance=0.0,
        ),
        _event(
            4,
            kind=ConceptCheckEventType.ATTEMPT_REVOKED,
            revoked_attempt_id="attempt-2",
        ),
        _event(
            5,
            kind=ConceptCheckEventType.TOPIC_LEVEL_OVERRIDDEN,
            new_level=StudentLevel.INTERMEDIATE,
        ),
        _event(
            6,
            kind=ConceptCheckEventType.TOPIC_LEVEL_OVERRIDDEN,
            new_level=StudentLevel.BEGINNER,
        ),
    )


def test_report_computes_metrics_and_replays_state() -> None:
    report = build_concept_check_report(
        _events(),
        starting_levels={"student-1": StudentLevel.BEGINNER},
    )

    assert report["overall"] == {
        "submitted": 2,
        "correct": 1,
        "skipped": 1,
        "revoked": 1,
        "accuracy": 0.5,
        "skip_rate": pytest.approx(1 / 3),
        "revocation_rate": 0.5,
    }
    assert report["by_topic"][0]["promotions"] == 0
    assert report["by_topic"][0]["demotions"] == 0
    assert report["by_difficulty"][0]["difficulty"] == "beginner"
    assert "include submissions that were later revoked" in report["definitions"]["accuracy"]
    assert "overrides and revocations excluded" in report["definitions"]["level_transitions"]
    final = report["final_learner_states"][0]
    assert final["state_version"] == 6
    assert final["topics"]["acceleration"]["level"] == "beginner"


def test_report_writes_csv_json_and_markdown(tmp_path) -> None:
    events_path = tmp_path / "events.jsonl"
    events_path.write_text(
        "".join(json.dumps(event.model_dump(mode="json")) + "\n" for event in _events()),
        encoding="utf-8",
    )
    loaded = load_concept_check_events(events_path)
    report = build_concept_check_report(
        loaded,
        starting_levels={"student-1": StudentLevel.BEGINNER},
    )

    output = tmp_path / "report"
    write_concept_check_report(report, output)

    assert (output / "concept_check_report.csv").is_file()
    assert json.loads((output / "concept_check_report.json").read_text(encoding="utf-8"))[
        "overall"
    ]["submitted"] == 2
    markdown = (output / "concept_check_report.md").read_text(encoding="utf-8")
    assert "## Definitions" in markdown
    assert "submissions that were later revoked" in markdown
    assert "## By topic" in markdown
    assert "revocation_rate" in markdown
    assert render_concept_check_json(report).endswith("\n")
    assert render_concept_check_csv(report).startswith("group,topic_id,difficulty")


def test_report_requires_a_starting_level_for_every_profile() -> None:
    with pytest.raises(ValueError, match="missing starting level"):
        build_concept_check_report(_events(), starting_levels={})


def test_answer_driven_demotion_is_counted_but_manual_changes_are_not() -> None:
    events = tuple(
        _event(
            version,
            kind=ConceptCheckEventType.ATTEMPT_SUBMITTED,
            attempt_id=f"attempt-{version}",
            difficulty=StudentLevel.BEGINNER,
            performance=0.0,
        )
        for version in range(1, 4)
    )

    report = build_concept_check_report(
        events,
        starting_levels={"student-1": StudentLevel.INTERMEDIATE},
        config=ConceptCheckConfig(demotion_threshold=0.4),
    )

    assert report["by_topic"][0]["promotions"] == 0
    assert report["by_topic"][0]["demotions"] == 1


def test_loader_ignores_an_incomplete_unterminated_final_record(tmp_path) -> None:
    path = tmp_path / "events.jsonl"
    first = json.dumps(_events()[0].model_dump(mode="json")).encode("utf-8")
    path.write_bytes(first + b'\n{"event_id": "partial')
    warnings: list[str] = []

    loaded = load_concept_check_events(path, on_warning=warnings.append)

    assert loaded == (_events()[0],)
    assert len(warnings) == 1
    assert "incomplete final Concept Check record" in warnings[0]


def test_loader_rejects_a_malformed_terminated_record(tmp_path) -> None:
    path = tmp_path / "events.jsonl"
    path.write_bytes(b'{"event_id": "broken"\n')

    with pytest.raises(ValueError, match="line 1"):
        load_concept_check_events(path)


def test_cli_requires_an_explicit_starting_level(tmp_path) -> None:
    events_path = tmp_path / "events.jsonl"
    events_path.write_text(
        json.dumps(_events()[0].model_dump(mode="json")) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(SystemExit) as exc:
        main([str(events_path), str(tmp_path / "report")])

    assert exc.value.code == 2
