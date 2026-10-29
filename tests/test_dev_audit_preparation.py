"""Small offline regressions for the audit sampling frame, not human verdicts."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

from cs30.evaluation.evaluation_audit import answer_text_sha256

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/prepare_dev_human_audit.py"
SPEC = importlib.util.spec_from_file_location("prepare_dev_audit", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def item(**changes):
    values = dict(
        source_split="dev",
        technical_failure=False,
        abstained=False,
        answer="Fixture answer",
        question_id="q1",
        evaluation_id="e1",
    )
    values.update(changes)
    return SimpleNamespace(**values)


def test_known_question_or_normalized_answer_exposure_is_excluded():
    candidate = item()
    assert MODULE.candidates([candidate], {"e1"}, {"q1"}, set()) == []
    exposed = {answer_text_sha256(" fixture   ANSWER ")}
    assert MODULE.candidates([candidate], {"e1"}, set(), exposed) == []


@pytest.mark.parametrize(
    "changes",
    [
        {"technical_failure": True},
        {"abstained": True},
        {"answer": None},
        {"answer": ""},
    ],
)
def test_non_answers_do_not_enter_the_frame(changes):
    assert MODULE.candidates([item(**changes)], {"e1"}, set(), set()) == []


def test_missing_judgements_are_not_silently_audited_as_successes():
    assert MODULE.candidates([item()], set(), set(), set()) == []


def test_test_split_is_rejected():
    with pytest.raises(ValueError, match="only Dev"):
        MODULE.candidates([item(source_split="test")], {"e1"}, set(), set())


def test_candidate_is_preserved_without_looking_at_verdict_values():
    candidate = item()
    before = vars(candidate).copy()
    assert MODULE.candidates([candidate], {"e1"}, set(), set()) == [candidate]
    assert vars(candidate) == before


def test_generated_json_is_sorted_and_lf(tmp_path):
    path = tmp_path / "fixture.json"
    MODULE.write_json(path, {"z": 1, "a": None})
    assert path.read_bytes().index(b'"a"') < path.read_bytes().index(b'"z"')
    assert b"\r" not in path.read_bytes()
