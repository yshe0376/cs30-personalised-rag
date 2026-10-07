"""Reports over append-only Concept Check JSONL event streams."""

from __future__ import annotations

import argparse
import csv
import json
import logging
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from io import StringIO
from pathlib import Path
from typing import Any

from cs30.concept_check.learner_state import EventReplayer
from cs30.v2.config import ConceptCheckConfig
from cs30.v2.contracts import (
    ConceptCheckEvent,
    ConceptCheckEventType,
    StudentLevel,
    StudentProfile,
)

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class AttemptMetrics:
    submitted: int
    correct: int
    skipped: int
    revoked: int
    accuracy: float | None
    skip_rate: float | None
    revocation_rate: float | None


def load_concept_check_events(
    path: Path,
    *,
    on_warning: Callable[[str], None] | None = None,
) -> tuple[ConceptCheckEvent, ...]:
    """Load typed JSONL events, ignoring only an incomplete final record."""

    events: list[ConceptCheckEvent] = []
    lines = Path(path).read_bytes().splitlines(keepends=True)
    for index, line in enumerate(lines):
        line_number = index + 1
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            if index == len(lines) - 1 and not line.endswith((b"\n", b"\r")):
                message = f"Ignoring incomplete final Concept Check record in {path}"
                _LOGGER.warning(message)
                if on_warning is not None:
                    on_warning(message)
                break
            raise ValueError(f"invalid Concept Check event at line {line_number}: {exc}") from exc
        try:
            events.append(ConceptCheckEvent.model_validate(value))
        except ValueError as exc:
            raise ValueError(f"invalid Concept Check event at line {line_number}: {exc}") from exc
    return tuple(events)


def _metrics(events: Iterable[ConceptCheckEvent]) -> AttemptMetrics:
    items = tuple(events)
    submitted = sum(
        event.event_type is ConceptCheckEventType.ATTEMPT_SUBMITTED for event in items
    )
    correct = sum(
        event.event_type is ConceptCheckEventType.ATTEMPT_SUBMITTED
        and event.performance == 1.0
        for event in items
    )
    skipped = sum(event.event_type is ConceptCheckEventType.ATTEMPT_SKIPPED for event in items)
    revoked = sum(event.event_type is ConceptCheckEventType.ATTEMPT_REVOKED for event in items)
    return AttemptMetrics(
        submitted=submitted,
        correct=correct,
        skipped=skipped,
        revoked=revoked,
        accuracy=correct / submitted if submitted else None,
        skip_rate=skipped / (submitted + skipped) if submitted + skipped else None,
        revocation_rate=revoked / submitted if submitted else None,
    )


def _level_index(level: StudentLevel) -> int:
    return (
        StudentLevel.BEGINNER,
        StudentLevel.INTERMEDIATE,
        StudentLevel.ADVANCED,
    ).index(level)


def _transition_counts(
    replayer: EventReplayer,
    events: Sequence[ConceptCheckEvent],
) -> dict[str, dict[str, int]]:
    """Count only level transitions caused by submitted answers."""

    counts: dict[str, dict[str, int]] = defaultdict(lambda: {"promotions": 0, "demotions": 0})
    ordered = tuple(sorted(events, key=lambda item: item.stream_version))
    previous_state = replayer.replay(())
    for index, event in enumerate(ordered, start=1):
        state = replayer.replay(ordered[:index])
        if (
            event.event_type is ConceptCheckEventType.ATTEMPT_SUBMITTED
            and event.topic_id is not None
        ):
            topic_id = event.topic_id
            before_state = previous_state.topics.get(topic_id)
            after_state = state.topics.get(topic_id)
            before = (
                before_state.level if before_state is not None else replayer.static_profile.level
            )
            after = after_state.level if after_state is not None else replayer.static_profile.level
            if _level_index(after) > _level_index(before):
                counts[topic_id]["promotions"] += 1
            elif _level_index(after) < _level_index(before):
                counts[topic_id]["demotions"] += 1
        previous_state = state
    return dict(counts)


def _group_rows(
    events: Sequence[ConceptCheckEvent],
    *,
    key_name: str,
    key_fn: Any,
) -> list[dict[str, Any]]:
    groups: dict[str, list[ConceptCheckEvent]] = defaultdict(list)
    attempts = {
        event.attempt_id: event
        for event in events
        if event.attempt_id is not None
        and event.event_type
        in {
            ConceptCheckEventType.ATTEMPT_SUBMITTED,
            ConceptCheckEventType.ATTEMPT_SKIPPED,
        }
    }
    for event in events:
        target = event
        if event.event_type is ConceptCheckEventType.ATTEMPT_REVOKED:
            target = attempts.get(event.revoked_attempt_id or "", event)
        key = key_fn(target)
        if key is not None:
            groups[str(key)].append(event)
    return [
        {key_name: key, **asdict(_metrics(group))}
        for key, group in sorted(groups.items())
    ]


def build_concept_check_report(
    events: Sequence[ConceptCheckEvent],
    *,
    starting_levels: Mapping[str, StudentLevel],
    config: ConceptCheckConfig | None = None,
) -> dict[str, Any]:
    """Build aggregate metrics and replay-derived states without rewriting M7 rules."""

    by_profile: dict[str, list[ConceptCheckEvent]] = defaultdict(list)
    for event in events:
        by_profile[event.profile_id].append(event)
    missing = sorted(set(by_profile) - set(starting_levels))
    if missing:
        raise ValueError(f"missing starting level for profile(s): {', '.join(missing)}")

    transitions: dict[str, dict[str, int]] = defaultdict(
        lambda: {"promotions": 0, "demotions": 0}
    )
    final_states: list[dict[str, Any]] = []
    for profile_id, profile_events in sorted(by_profile.items()):
        registry_versions = {event.topic_registry_version for event in profile_events}
        if len(registry_versions) != 1:
            raise ValueError(f"profile {profile_id} spans multiple Topic registry versions")
        profile = StudentProfile(profile_id=profile_id, level=starting_levels[profile_id])
        replayer = EventReplayer(profile, next(iter(registry_versions)), config=config)
        ordered = tuple(sorted(profile_events, key=lambda item: item.stream_version))
        state = replayer.replay(ordered)
        final_states.append(state.model_dump(mode="json"))
        for topic_id, values in _transition_counts(replayer, ordered).items():
            transitions[topic_id]["promotions"] += values["promotions"]
            transitions[topic_id]["demotions"] += values["demotions"]

    by_topic = _group_rows(events, key_name="topic_id", key_fn=lambda event: event.topic_id)
    for row in by_topic:
        row.update(transitions.get(row["topic_id"], {"promotions": 0, "demotions": 0}))

    by_difficulty = _group_rows(
        events,
        key_name="difficulty",
        key_fn=lambda event: (
            event.question_difficulty.value if event.question_difficulty is not None else None
        ),
    )
    by_topic_and_difficulty = _group_rows(
        events,
        key_name="topic_and_difficulty",
        key_fn=lambda event: (
            f"{event.topic_id}|{event.question_difficulty.value}"
            if event.question_difficulty is not None
            else None
        ),
    )
    for row in by_topic_and_difficulty:
        topic_id, difficulty = row.pop("topic_and_difficulty").split("|", maxsplit=1)
        row["topic_id"] = topic_id
        row["difficulty"] = difficulty

    return {
        "schema_version": "0.1",
        "definitions": {
            "accuracy": (
                "correct / submitted; both counts include submissions that were later revoked"
            ),
            "skip_rate": "skipped / (submitted + skipped)",
            "revocation_rate": "revoked / submitted",
            "level_transitions": "answer-driven changes only; overrides and revocations excluded",
            "state_source": "EventReplayer",
        },
        "overall": asdict(_metrics(events)),
        "by_topic": by_topic,
        "by_difficulty": by_difficulty,
        "by_topic_and_difficulty": by_topic_and_difficulty,
        "final_learner_states": final_states,
    }


def _format_rate(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.3f}"


def _markdown_table(rows: Sequence[Mapping[str, Any]], columns: Sequence[str]) -> str:
    if not rows:
        return "_No rows._"
    header = "| " + " | ".join(columns) + " |"
    separator = "| " + " | ".join("---" for _ in columns) + " |"
    body = [
        "| "
        + " | ".join(
            _format_rate(row[column])
            if column.endswith("rate") or column == "accuracy"
            else str(row[column])
            for column in columns
        )
        + " |"
        for row in rows
    ]
    return "\n".join((header, separator, *body))


def render_concept_check_markdown(report: Mapping[str, Any]) -> str:
    """Render the machine-readable report as a compact review document."""

    metric_columns = (
        "submitted",
        "correct",
        "skipped",
        "revoked",
        "accuracy",
        "skip_rate",
        "revocation_rate",
    )
    overall = report["overall"]
    lines = [
        "# Concept Check event report",
        "",
        "## Definitions",
        "",
        f"- Accuracy: {report['definitions']['accuracy']}",
        f"- Skip rate: {report['definitions']['skip_rate']}",
        f"- Revocation rate: {report['definitions']['revocation_rate']}",
        f"- Level transitions: {report['definitions']['level_transitions']}",
        "",
        "## Overall",
        "",
        _markdown_table([overall], metric_columns),
        "",
        "## By topic",
        "",
        _markdown_table(
            report["by_topic"],
            ("topic_id", *metric_columns, "promotions", "demotions"),
        ),
        "",
        "## By difficulty",
        "",
        _markdown_table(report["by_difficulty"], ("difficulty", *metric_columns)),
        "",
        "## By topic and difficulty",
        "",
        _markdown_table(
            report["by_topic_and_difficulty"],
            ("topic_id", "difficulty", *metric_columns),
        ),
        "",
    ]
    return "\n".join(lines)


_REPORT_FIELDNAMES = (
    "group",
    "topic_id",
    "difficulty",
    "submitted",
    "correct",
    "skipped",
    "revoked",
    "accuracy",
    "skip_rate",
    "revocation_rate",
    "promotions",
    "demotions",
)


def render_concept_check_json(report: Mapping[str, Any]) -> str:
    """Render one report as stable, human-readable JSON."""

    return json.dumps(report, indent=2, sort_keys=True) + "\n"


def _report_rows(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = [{"group": "overall", **report["overall"]}]
    rows.extend({"group": "topic", **row} for row in report["by_topic"])
    rows.extend({"group": "difficulty", **row} for row in report["by_difficulty"])
    rows.extend(
        {"group": "topic_and_difficulty", **row}
        for row in report["by_topic_and_difficulty"]
    )
    return rows


def render_concept_check_csv(report: Mapping[str, Any]) -> str:
    """Render one report as CSV without writing an intermediate file."""

    stream = StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=_REPORT_FIELDNAMES, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(_report_rows(report))
    return stream.getvalue()


def write_concept_check_report(report: Mapping[str, Any], output_directory: Path) -> None:
    """Write JSON, CSV, and Markdown representations of one report."""

    output_directory = Path(output_directory)
    output_directory.mkdir(parents=True, exist_ok=True)
    (output_directory / "concept_check_report.json").write_text(
        render_concept_check_json(report),
        encoding="utf-8",
    )
    (output_directory / "concept_check_report.md").write_text(
        render_concept_check_markdown(report),
        encoding="utf-8",
    )
    (output_directory / "concept_check_report.csv").write_text(
        render_concept_check_csv(report),
        encoding="utf-8",
        newline="",
    )


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("events", type=Path, help="Concept Check JSONL event file")
    parser.add_argument("output_directory", type=Path, help="Directory for CSV/JSON/Markdown")
    parser.add_argument(
        "--starting-level",
        choices=[level.value for level in StudentLevel],
        required=True,
        help="Static starting level applied to every profile in this event file",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    events = load_concept_check_events(args.events)
    profiles = {event.profile_id for event in events}
    starting_level = StudentLevel(args.starting_level)
    report = build_concept_check_report(
        events,
        starting_levels={profile_id: starting_level for profile_id in profiles},
    )
    write_concept_check_report(report, args.output_directory)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
