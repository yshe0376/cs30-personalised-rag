"""Synthetic Dev repeat noise calculations; no generated Test answers or provider."""

import copy
import json
import math
from pathlib import Path

import pytest

from cs30.contracts import StudentLevel
from cs30.evaluation.test_gate_noise import adaptation_repeat_floors
from cs30.evaluation.test_gate_readiness import load_noise_floors
from cs30.evaluation.v2_generation_models import ExperimentArm, GenerationEvaluationInput


def fixtures():
    base, repeat, base_rows, repeat_rows = [], [], [], []
    for level in (StudentLevel.BEGINNER, StudentLevel.ADVANCED):
        criteria = (
            ["B1", "B2", "B3", "B4"] if level is StudentLevel.BEGINNER else ["A1", "A2", "A3", "A4"]
        )
        for arm in (ExperimentArm.P0R0_PLAIN, ExperimentArm.P1R0_PROMPT_ONLY):
            key = f"fixture-{level.value}-{arm.value}"
            item = GenerationEvaluationInput(
                evaluation_id=key,
                run_id=key,
                question_id="fictional-q",
                question="Fixture question",
                answer="Fixture answer",
                target_level=level,
                condition=arm,
                lambda_weight=0.1,
                generation_model_family="gpt-oss-20b",
                generation_model_revision="fixture",
                source_split="dev",
                source_artifact_sha256="a" * 64,
                eligibility="endpoint_only",
            )
            base.append(item)
            repeat.append(item.model_copy(update={"evaluation_id": "repeat-" + key}))
            row = {
                "evaluation_id": key,
                "question_id": "fictional-q",
                "target_level": level.value,
                "evaluated_level": level.value,
                "condition": arm.value,
                "is_target_level_evaluation": True,
                "criteria": [{"criterion_id": c, "verdict": "pass"} for c in criteria],
            }
            base_rows.append(row)
            changed = copy.deepcopy(row)
            changed["evaluation_id"] = "repeat-" + key
            for criterion in changed["criteria"][: 1 if level is StudentLevel.BEGINNER else 2]:
                criterion["verdict"] = "fail"
            repeat_rows.append(changed)
    return base, repeat, base_rows, repeat_rows


def test_noise_is_root_mean_square_scaled_by_test_pairs_not_mean_signed_change():
    result = adaptation_repeat_floors(*fixtures(), {"beginner": 128, "advanced": 128})
    assert result["adaptation_noise_floors"]["beginner"] == pytest.approx(math.sqrt(0.25**2 / 128))
    assert result["adaptation_noise_floors"]["advanced"] == pytest.approx(math.sqrt(0.5**2 / 128))
    assert result["details"]["beginner"]["resolved_repeat_cells"] == 2


@pytest.mark.parametrize("change", ["test_split", "wrong_generator", "wrong_pair", "wrong_n"])
def test_noise_rejects_wrong_sources_and_pairing(change):
    base, repeat, rows, repeated = fixtures()
    counts = {"beginner": 128, "advanced": 128}
    if change == "test_split":
        repeat[0] = repeat[0].model_copy(update={"source_split": "test"})
    elif change == "wrong_generator":
        repeat[0] = repeat[0].model_copy(update={"generation_model_family": "llama"})
    elif change == "wrong_pair":
        repeat[0] = repeat[0].model_copy(update={"run_id": "other-run"})
    else:
        counts["beginner"] = 0
    with pytest.raises(ValueError):
        adaptation_repeat_floors(base, repeat, rows, repeated, counts)


def test_committed_noise_record_formula_and_generator_binding(tmp_path):
    source = (
        Path(__file__).parents[1]
        / "eval_inputs/m8/test-gates-20261029/dev-adaptation-noise-floors.json"
    )
    floors = load_noise_floors(source)
    assert floors["advanced"] > floors["beginner"] > 0
    data = json.loads(source.read_text(encoding="utf-8"))
    for field, value in [("generator", "llama-3.1-8b"), ("source_split", "test")]:
        changed = dict(data, **{field: value})
        path = tmp_path / f"{field}.json"
        path.write_text(json.dumps(changed), encoding="utf-8")
        with pytest.raises(ValueError):
            load_noise_floors(path)
