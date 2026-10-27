from __future__ import annotations

import copy
import csv
import hashlib
import json
import runpy
from pathlib import Path

import pytest

from cs30.evaluation.evidence_quotes import QUOTE_ROW_SEPARATOR, merge_quote_rows, quote_is_grounded
from cs30.evaluation.evidence_support import (
    build_evidence_support_request,
    validate_evidence_support_output,
)
from cs30.evaluation.judge_runtime import validate_output_against_request
from cs30.evaluation.v2_generation_models import (
    EvaluationEvidence,
    GenerationEvaluationInput,
    JudgeConfiguration,
)


@pytest.mark.parametrize(
    ("quote", "source", "accepted"),
    [
        (
            "Force acts on mass … It causes acceleration",
            "Force acts on mass. It causes acceleration.",
            True,
        ),
        (
            "Force acts on mass...It causes acceleration",
            "Force acts on mass. It causes acceleration.",
            True,
        ),
        (
            "It causes acceleration … Force acts on mass",
            "Force acts on mass. It causes acceleration.",
            False,
        ),
        ("Force ... invented", "Force causes acceleration.", False),
        ("...", "Force causes acceleration.", False),
        ("Force\u00a0causes acceleration", "Force\n causes  acceleration.", True),
        ("cafe\u0301 serves coffee", "café serves coffee", True),
        ("two-lens optical system", "two\u2011lens optical system", True),
        ('"force" causes acceleration', "\u201cforce\u201d causes acceleration", True),
        ("Force causes acceleration", "force causes acceleration.", False),
        ("mass is 50", "mass is 60", False),
        ("x - y", "x \u2212 y", False),
        ("x2", "x²", False),
        ("light is slow", "light is fast", False),
    ],
)
def test_excerpt_matching_changes_formatting_not_content(quote, source, accepted):
    assert quote_is_grounded(quote, source) is accepted


@pytest.mark.parametrize("quote", ["a ... e", "damaged ... Healthy cells are not"])
def test_leader_counterexamples_are_rejected(quote):
    source = (
        "Cancer cells reproduce rapidly. Healthy cells are not damaged "
        "by the radiation dose used in therapy."
    )
    assert not quote_is_grounded(quote, source)


@pytest.mark.parametrize(
    ("quote", "source", "accepted"),
    [
        ("one two three ... four five six", "one two three four five six", True),
        ("four five six ... one two three", "one two three four five six", False),
        ("one two three ... three four five", "one two three four five", False),
        ("one two three ... one two three", "one two three", False),
        ("one two three ... one two three", "one two three then one two three", True),
        ("are received", "Signals are received from tissue.", False),
        ("one two ... three four five", "one two three four five", False),
        ("one two ---", "one two ---", False),
    ],
)
def test_each_row_requires_three_words_order_and_nonoverlap(quote, source, accepted):
    assert quote_is_grounded(quote, source) is accepted


def test_separate_rows_keep_boundaries_and_allow_reverse_order_and_overlap():
    merged = merge_quote_rows(
        [
            {"evidence_id": "E1", "quote": "three four five"},
            {"evidence_id": "E1", "quote": "one two three"},
        ]
    )
    assert merged == {"E1": "three four five" + QUOTE_ROW_SEPARATOR + "one two three"}
    assert quote_is_grounded(merged["E1"], "one two three four five")
    assert not quote_is_grounded("three four five ... one two three", "one two three four five")


def test_reserved_row_separator_cannot_be_injected_into_one_online_row():
    with pytest.raises(ValueError, match="reserved row separator"):
        merge_quote_rows(
            [
                {
                    "evidence_id": "E1",
                    "quote": "three four five" + QUOTE_ROW_SEPARATOR + "one two three",
                }
            ]
        )


@pytest.mark.parametrize("bad", [None, 4, "", "   "])
def test_duplicate_quote_rows_cannot_hide_invalid_values(bad):
    with pytest.raises(ValueError, match="nonempty quote"):
        merge_quote_rows(
            [
                {"evidence_id": "E1", "quote": "valid"},
                {"evidence_id": "E1", "quote": bad},
            ]
        )


def evidence_case():
    item = GenerationEvaluationInput(
        evaluation_id="eval-1",
        run_id="run-1",
        question_id="q-1",
        question="What causes acceleration?",
        answer="Force causes acceleration.",
        target_level="beginner",
        condition="P0R0_plain",
        lambda_weight=0.1,
        generation_model_family="gpt-oss",
        generation_model_revision="20b",
        eligibility="full",
        evidence=[
            EvaluationEvidence(
                evidence_id="source-1",
                text="Force acts on mass. It causes acceleration.",
                rank=1,
                role="definition",
            )
        ],
        citation_ids=["source-1"],
        source_artifact_sha256="a" * 64,
    )
    configuration = JudgeConfiguration(
        config_version="test",
        provider="local",
        model_family="independent",
        model_revision="test",
        temperature=0,
        seed=1,
        prompt_version="test",
        output_schema_version="1.0",
        local_model=True,
        data_approval="not_required",
    )
    request = build_evidence_support_request(item, configuration)
    raw = {
        "schema_version": "1.0",
        "request_id": request.request_id,
        "claims": [
            {
                "claim_id": "c1",
                "claim_text": item.answer,
                "bundle_support": "supported",
                "citation_support": "supported",
                "supporting_evidence_ids": ["E1"],
                "evidence_quotes": [
                    {"evidence_id": "E1", "quote": "Force acts on mass."},
                    {"evidence_id": "E1", "quote": "It causes acceleration."},
                ],
                "reason": "Two original excerpts.",
            }
        ],
    }
    return item, request, raw


def test_both_validation_layers_accept_multiple_grounded_excerpts():
    item, request, raw = evidence_case()
    first = validate_output_against_request(raw, request)
    second = validate_evidence_support_output(raw, request=request, item=item)
    assert first.claims[0].evidence_quotes == {
        "E1": "Force acts on mass." + QUOTE_ROW_SEPARATOR + "It causes acceleration."
    }
    assert second.claims[0].supporting_evidence_ids == ["source-1"]


def test_separate_rows_survive_model_serialization_and_both_validators():
    item, request, raw = evidence_case()
    raw["claims"][0]["evidence_quotes"].reverse()
    runtime = validate_output_against_request(raw, request)
    saved = json.loads(runtime.model_dump_json())
    assert QUOTE_ROW_SEPARATOR in saved["claims"][0]["evidence_quotes"]["E1"]
    assert validate_output_against_request(saved, request)
    assert validate_evidence_support_output(saved, request=request, item=item)


@pytest.mark.parametrize("quote", ["Force acts", "It causes acceleration ... Force acts on mass"])
def test_both_layers_reject_short_or_reordered_fragments(quote):
    item, request, raw = evidence_case()
    raw["claims"][0]["evidence_quotes"] = [{"evidence_id": "E1", "quote": quote}]
    with pytest.raises(ValueError):
        validate_output_against_request(raw, request)
    with pytest.raises(ValueError):
        validate_evidence_support_output(raw, request=request, item=item)


@pytest.mark.parametrize("problem", ["fabrication", "missing_id", "unknown_id", "wrong_request"])
def test_both_layers_reject_broken_evidence_bindings(problem):
    item, request, raw = evidence_case()
    raw = copy.deepcopy(raw)
    claim = raw["claims"][0]
    if problem == "fabrication":
        claim["evidence_quotes"][1]["quote"] = "It causes levitation."
    elif problem == "missing_id":
        claim["supporting_evidence_ids"].append("E2")
    elif problem == "unknown_id":
        claim["supporting_evidence_ids"] = ["E9"]
        claim["evidence_quotes"] = [{"evidence_id": "E9", "quote": "Force"}]
    else:
        raw["request_id"] = "other-request"
    with pytest.raises(ValueError):
        validate_output_against_request(raw, request)
    with pytest.raises(ValueError):
        validate_evidence_support_output(raw, request=request, item=item)


def test_trial_requires_explicit_paid_opt_in_and_selection_is_repeatable():
    namespace = runpy.run_path(str(Path(__file__).parents[1] / "scripts/judge_trial.py"))
    guard = namespace["require_paid_opt_in"]
    with pytest.raises(ValueError, match="Paid calls disabled"):
        guard(False, False)
    guard(True, False)
    generators = namespace["GENERATORS"]
    adapted = {
        generator: [
            {
                "source_status": "answered",
                "target_level": level,
                "condition": condition,
                "eligibility": "endpoint_only",
                "question_id": f"{level}-{condition}",
            }
            for level in ("beginner", "intermediate", "advanced")
            for condition in (
                "P0R0_plain",
                "P1R0_prompt_only",
                "P0R1_reranking_only",
                "P1R1_combined",
            )
        ]
        for generator in generators
    }
    select = namespace["select_cells"]
    first = select(adapted, 20, 5703)
    assert first == select(adapted, 20, 5703)
    assert len(first) == 20
    assert {row["_generator"] for row in first} == set(generators)
    assert {row["target_level"] for row in first} == {"beginner", "intermediate", "advanced"}


def test_saved_trial_revalidation_and_cost_audit_do_not_construct_a_client(tmp_path, monkeypatch):
    from cs30.evaluation.gemini_judge_client import GeminiJudgeClient

    def forbidden(*args, **kwargs):
        pytest.fail("Offline audit must never construct an API client")

    monkeypatch.setattr(GeminiJudgeClient, "__init__", forbidden)
    namespace = runpy.run_path(str(Path(__file__).parents[1] / "scripts/revalidate_judge_trial.py"))
    root, out = tmp_path / "original", tmp_path / "offline"
    folder = root / "thinking-high" / "evidence_support"
    folder.mkdir(parents=True)
    item, request, raw = evidence_case()
    inputs = root / "subset" / "example" / "inputs.jsonl"
    inputs.parent.mkdir(parents=True)
    inputs.write_text(json.dumps(item.model_dump(mode="json")) + "\n", encoding="utf-8")
    (folder / "example-requests.jsonl").write_text(
        json.dumps(request.model_dump(mode="json")) + "\n", encoding="utf-8"
    )
    (folder / "example-results.jsonl").write_text(
        json.dumps(
            {
                "request_id": request.request_id,
                "unresolved": True,
                "output": None,
                "raw_output": raw,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "selection.json").write_text('[{"_generator":"example"}]', encoding="utf-8")
    (root / "summary.json").write_text(
        json.dumps(
            {
                "price_usd_per_million": {"input": 0.25, "output_incl_thinking": 1.5},
                "levels": {"high": {"total_spent_usd": 0.000325}},
            }
        ),
        encoding="utf-8",
    )
    with (root / "calls.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=[
                "thinking_level",
                "input_tokens",
                "output_tokens",
                "cost_usd",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "thinking_level": "high",
                "input_tokens": 100,
                "output_tokens": 200,
                "cost_usd": 0.000325,
            }
        )
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob("*") if p.is_file()}
    assert namespace["main"](["--trial-root", str(root), "--out", str(out)]) == 0
    report = json.loads((out / "revalidation.json").read_text(encoding="utf-8"))
    assert report["api_calls"] == 0
    assert report["new_cost_usd"] == 0
    assert report["levels"]["high"]["recovered_offline"] == 1
    assert report["original_usage_audit"]["total_token_cost_usd"] == pytest.approx(0.000325)
    assert all(hashlib.sha256(p.read_bytes()).hexdigest() == digest for p, digest in before.items())
    with pytest.raises(SystemExit):
        namespace["main"](["--trial-root", str(root), "--out", str(root / "overwrite")])
    (root / "calls.csv").write_text(
        "thinking_level,input_tokens,output_tokens,cost_usd\nhigh,100,200,1.0\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="does not match tokens"):
        namespace["audit_usage"](root)
