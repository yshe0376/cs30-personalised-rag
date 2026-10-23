"""Cost planning and independently generated noise-floor denominators."""

import json
from dataclasses import replace

import pytest
from test_v2_experiment import Client, prepare

from cs30.v2.experiment import run_experiment
from cs30.v2.experiment_planning import estimate_api_cost, noise_floor_report


def test_cost_estimate_has_no_model_calls_and_separates_planned_request_cap(tmp_path):
    prepared = prepare(tmp_path)
    result = estimate_api_cost(
        prepared,
        input_price=2,
        output_price=4,
        mean_input_tokens=1000,
        max_output_tokens=500,
        max_api_requests=24,
    )
    assert result["nominal_requests"] == 12
    assert result["nominal_planning_usd"] == pytest.approx(0.048)
    assert result["request_cap_planning_usd"] == pytest.approx(0.096)
    with pytest.raises(ValueError):
        estimate_api_cost(
            prepared,
            input_price=float("nan"),
            output_price=1,
            mean_input_tokens=1000,
            max_output_tokens=500,
            max_api_requests=24,
        )


def test_noise_floor_measures_answer_changes_and_reports_failures_separately(tmp_path):
    class Changed(Client):
        def complete(self, prompt, text_format):
            response = super().complete(prompt, text_format)
            payload = json.loads(response.text)
            payload["explanation"] += " A repeated draw."
            return replace(response, text=json.dumps(payload))

    prepared = prepare(tmp_path)
    first, repeat = tmp_path / "first", tmp_path / "repeat"
    run_experiment(prepared, first, Client(fail_first=True), provider="synthetic")
    run_experiment(prepared, repeat, Changed(), provider="synthetic")
    result = noise_floor_report(first, repeat)
    assert result["expected_pairs"] == 12 and result["successful_pairs"] == 11
    assert result["paired_technical_failures"] == 1 and result["answer_mismatch_rate"] == 1
    assert result["final_choice_changes"] == result["citation_set_changes"] == 0
    assert result["diagnostic_only"] is True
    assert result["scoring_noise_floor_status"] == "pending_m8_scoring"
    assert result["m8_handoff"]["repeat_cells"] == result["expected_pairs"]
    with pytest.raises(ValueError, match="independent repeat"):
        noise_floor_report(first, first)
    answers = repeat / "saved_answers.jsonl"
    answers.write_bytes(answers.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="hash mismatch"):
        noise_floor_report(first, repeat)
