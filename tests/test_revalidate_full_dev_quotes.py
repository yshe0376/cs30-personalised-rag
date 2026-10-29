"""Offline full-Dev revalidation: recovers, flags and prepares retries without API calls."""

from __future__ import annotations

import hashlib
import json
import runpy
from pathlib import Path

import pytest

from cs30.contracts import StudentLevel
from cs30.evaluation.evidence_support import build_evidence_support_request
from cs30.evaluation.judge_runtime import (
    CachedJudgeRunner,
    request_cache_key,
    validate_output_against_request,
)
from cs30.evaluation.level_discrimination import build_discrimination_request
from cs30.evaluation.open_answer_models import OpenAnswerRubric
from cs30.evaluation.open_answer_scoring import canonical_hash
from cs30.evaluation.v2_generation_models import (
    ApprovalStatus,
    EvaluationEvidence,
    GenerationEvaluationInput,
    JudgeConfiguration,
    JudgeRequest,
    JudgeResultEnvelope,
    LevelProfile,
)

SCRIPT = Path(__file__).parents[1] / "scripts/revalidate_full_dev_quotes.py"
STAMP = "2026-10-28T12:00:00+00:00"
NARROW = " "
# Correctness answers; rows sharing an answer share one judge prompt and cache key.
ANSWERS = {
    "a1": f"The object’s speed{NARROW}changes because a net force acts.",
    "a2": f"A net force{NARROW}changes the motion of the cart.",
    "a3": "A net force acts on the ball, so it accelerates.",
    "a4": f"Gravity pulls the apple{NARROW}down.",
}
ERROR = "ValueError: judge quote is absent from the complete original answer"


def _config() -> JudgeConfiguration:
    return JudgeConfiguration(
        config_version="judge-v1",
        provider="local",
        model_family="independent",
        model_revision="r1",
        temperature=0,
        seed=7,
        prompt_version="p1",
        output_schema_version="1.0",
        local_model=True,
        data_approval=ApprovalStatus.NOT_REQUIRED,
    )


def _profile(level: StudentLevel) -> LevelProfile:
    return LevelProfile.model_validate(
        {
            "profile_version": "profiles-v1",
            "level": level,
            "student_positioning": "learner",
            "assumed_physics_background": ["motion"],
            "assumed_mathematics_background": ["algebra"],
            "acceptable_inference_span": "one",
            "helpful_writing_patterns": ["clear"],
            "harmful_writing_patterns": ["vague"],
            "anchor_examples": [
                {
                    "anchor_id": f"{level.value}-{n}",
                    "question": "Q?",
                    "answer": "A.",
                    "rationale": "anchor",
                }
                for n in (1, 2)
            ],
        }
    )


def _item(run_id: str) -> GenerationEvaluationInput:
    return GenerationEvaluationInput(
        evaluation_id=f"eval-{run_id}",
        run_id=run_id,
        question_id="q-1",
        question="Why does the speed change?",
        answer=ANSWERS["a1"] + f" ({run_id})",
        target_level=StudentLevel.BEGINNER,
        condition="P1R1_combined",
        lambda_weight=0.2,
        generation_model_family="gpt-oss",
        generation_model_revision="20b",
        eligibility="full",
        evidence=[
            EvaluationEvidence(
                evidence_id="E1",
                rank=1,
                role="definition",
                text="A net force acting on an object changes its speed.",
            )
        ],
        citation_ids=["E1"],
        source_artifact_sha256="a" * 64,
    )


def _envelope(request, *, output=None, raw=None, error=None) -> dict:
    return JudgeResultEnvelope(
        task=request.task,
        request_id=request.request_id,
        cache_key=request_cache_key(request),
        judge_config_version="judge-v1",
        judge_execution_id="exec",
        output=output,
        raw_output=raw,
        unresolved=output is None,
        error=error,
        completed_at_utc=STAMP,
    ).model_dump(mode="json")


def _write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return path


def _assessment(quote: str) -> dict:
    return {
        "criteria": [
            {"criterion_id": "term", "verdict": "met", "answer_quote": quote, "reason": "r"}
        ],
        "critical_error": False,
        "critical_error_quote": None,
        "minor_error": False,
        "minor_error_quote": None,
        "needs_review": False,
        "review_reason": None,
        "rationale": "fine",
    }


def _rubric() -> OpenAnswerRubric:
    return OpenAnswerRubric(
        question_id="q-1",
        gold_sha256="1" * 64,
        rubric_version="r1",
        criteria=[
            dict(
                criterion_id="term",
                description="Names the cause.",
                core=True,
                reference_span_ids=["s1"],
            )
        ],
        required_paths=[["term"]],
        full_credit_answers=["net force"],
    )


def _score_row(run_id: str, answer_key: str, *, quotes=(), assessed_quote=None) -> dict:
    answer = ANSWERS[answer_key]
    attempt = dict(
        reported_model="judge",
        input_tokens=1,
        output_tokens=1,
        thought_tokens=0,
        usage_available=True,
    )
    row = {
        "run_id": run_id,
        "question_id": "q-1",
        "condition_id": "P1R1_combined",
        "student_level": "beginner",
        "generator_model": "gen",
        "schema_version": "0.1",
        "split": "dev",
        "gold_sha256": "1" * 64,
        "rubric_sha256": canonical_hash(_rubric().model_dump(mode="json")),
        "rubric_version": "r1",
        "answer_sha256": hashlib.sha256(answer.encode()).hexdigest(),
        "run_status": "answered",
        "scoring_source": "judge",
        "judge_model": "judge",
        "judge_prompt_version": "v",
        # The real prompt hash depends on the answer, so identical answers share it.
        "judge_prompt_sha256": hashlib.sha256(answer_key.encode()).hexdigest(),
        "judge_config_sha256": "3" * 64,
    }
    if assessed_quote is not None:
        return row | {
            "score_status": "scored",
            "score": 2,
            "reason": "ok",
            "assessment": _assessment(assessed_quote),
            "judge_attempts": [dict(attempt, raw_output="{}", error=None)],
        }
    return row | {
        "score_status": "judge_error",
        "score": None,
        "reason": "judge failed",
        "judge_attempts": [
            dict(attempt, raw_output=json.dumps(_assessment(q)), error=ERROR) for q in quotes
        ],
    }


def _key(row: dict) -> str:
    return canonical_hash(
        {
            "prompt": row["judge_prompt_sha256"],
            "config": row["judge_config_sha256"],
            "gold": row["gold_sha256"],
            "rubric": row["rubric_sha256"],
        }
    )


@pytest.fixture
def run_root(tmp_path: Path) -> Path:
    root = tmp_path / "run"
    profiles = [_profile(level) for level in StudentLevel]

    # Discrimination: r1 accepted and cached; r1b accepted but its cache line is missing;
    # r2 recoverable (formatting only); r3 truly reworded.
    disc = {
        rid: build_discrimination_request(_item(rid), profiles, _config())
        for rid in ("r1", "r1b", "r2", "r3")
    }

    def disc_raw(request, quote):
        return {
            "schema_version": "1.0",
            "request_id": request.request_id,
            "predicted_level": "beginner",
            "exact_quote": quote,
            "reason": "plain",
        }

    _write_jsonl(
        root / "requests/b/discrimination.requests.jsonl",
        [r.model_dump(mode="json") for r in disc.values()],
    )
    accepted = _envelope(disc["r1"], output=disc_raw(disc["r1"], "a net force acts"))
    accepted_uncached = _envelope(disc["r1b"], output=disc_raw(disc["r1b"], "a net force acts"))
    _write_jsonl(root / "caches/b/discrimination.cache.jsonl", [accepted])
    message = "attempt 2: discrimination quote is not an exact answer substring"
    _write_jsonl(
        root / "results/b/discrimination.results.jsonl",
        [
            accepted,
            accepted_uncached,
            _envelope(
                disc["r2"], raw=disc_raw(disc["r2"], "The object's speed changes"), error=message
            ),
            _envelope(disc["r3"], raw=disc_raw(disc["r3"], "the velocity varies"), error=message),
        ],
    )

    # Evidence: one cached output that the downstream rule now rejects.
    evidence = build_evidence_support_request(_item("r4"), _config())
    contradictory = {
        "schema_version": "1.0",
        "request_id": evidence.request_id,
        "claims": [
            {
                "claim_id": "c1",
                "claim_text": "a net force acts",
                "bundle_support": "unsupported",
                "citation_support": "unsupported",
                "supporting_evidence_ids": ["E1"],
                "evidence_quotes": {"E1": "A net force acting on an object"},
                "reason": "x",
            }
        ],
    }
    _write_jsonl(
        root / "requests/b/evidence_support.requests.jsonl", [evidence.model_dump(mode="json")]
    )
    _write_jsonl(
        root / "caches/b/evidence_support.cache.jsonl", [_envelope(evidence, output=contradictory)]
    )
    _write_jsonl(
        root / "results/b/evidence_support.results.jsonl",
        [_envelope(evidence, output=contradictory)],
    )

    # Correctness.
    _write_jsonl(root / "rubrics.jsonl", [_rubric().model_dump(mode="json")])
    rows = [
        # c1: second saved attempt passes after normalisation -> recovered.
        _score_row("c1", "a1", quotes=["velocity changes", "The object's speed changes"]),
        # c2 + c3 share an answer; only c3's second attempt passes -> both recovered.
        _score_row("c2", "a2", quotes=["force moves", "cart goes"]),
        _score_row("c3", "a2", quotes=["force moves", "A net force changes"]),
        # c4 failed but c5 (same answer) succeeded and is cached -> covered, not retried.
        _score_row("c4", "a3", quotes=["force acts on it"]),
        _score_row("c5", "a3", assessed_quote="A net force acts on the ball"),
        # c6 stays unresolved -> exactly one retry request.
        _score_row("c6", "a4", quotes=["gravity drags the apple"]),
        # c7 scored by rule: needs no judge cache.
        {
            **_score_row("c7", "a1"),
            "scoring_source": "rule",
            "score_status": "scored",
            "score": 2,
            "judge_attempts": [],
        },
    ]
    _write_jsonl(root / "results/b/correctness/open_answer_scores.jsonl", rows)
    _write_jsonl(
        root / "saved_answers.jsonl",
        [
            {
                "run_id": r["run_id"],
                "question_id": "q-1",
                "condition_id": "P1R1_combined",
                "student_level": "beginner",
                "generator_model": "gen",
                "status": "answered",
                "answer": {"explanation": ANSWERS[k], "citations": ["chunk"], "abstained": False},
            }
            for r, k in zip(rows, ["a1", "a2", "a2", "a3", "a3", "a4", "a1"], strict=True)
        ],
    )
    cache_dir = root / "caches/b/correctness"
    cache_dir.mkdir(parents=True)
    c5 = rows[4]
    (cache_dir / f"{_key(c5)}.json").write_text(
        json.dumps(
            {
                "key": _key(c5),
                "trace": {
                    k: c5[k]
                    for k in (
                        "judge_model",
                        "judge_prompt_version",
                        "judge_prompt_sha256",
                        "judge_config_sha256",
                    )
                },
                "assessment": c5["assessment"],
                "attempts": c5["judge_attempts"],
            }
        ),
        encoding="utf-8",
    )

    def command(module, options):
        args = " ".join(f"'{k}' '{v}'" for k, v in options)
        return f"& 'python.exe' -m {module} '{options[0][0]}' " + args

    jobs = [
        {
            "batch": "b",
            "task": "correctness",
            "command": (
                "& 'python.exe' -m cs30.evaluation.open_answer_cli 'score' "
                f"'--runs' '{root / 'saved_answers.jsonl'}' '--rubrics' '{root / 'rubrics.jsonl'}' "
                f"'--output-dir' '{root / 'results/b/correctness'}' '--cache-dir' '{cache_dir}' "
                "'--attempt-log' 'old.jsonl' '--provider' 'gemini' '--thinking-level' 'low'"
            ),
        }
    ]
    for task in ("discrimination", "evidence_support"):
        jobs.append(
            {
                "batch": "b",
                "task": task,
                "command": (
                    "& 'python.exe' -m cs30.evaluation.v2_generation_cli 'run-judge-requests' "
                    f"'--requests' '{root / f'requests/b/{task}.requests.jsonl'}' "
                    f"'--cache' '{root / f'caches/b/{task}.cache.jsonl'}' "
                    f"'--output' '{root / f'results/b/{task}.results.jsonl'}' "
                    f"'--judge-execution-id' 'exec-{task}' '--attempt-log' 'old.jsonl' "
                    "'--max-attempts' '2'"
                ),
            }
        )
    (root / "run-plan.json").write_text(json.dumps({"jobs": jobs}), encoding="utf-8")
    return root


def _main():
    return runpy.run_path(str(SCRIPT))["main"]


def _snapshot(root: Path) -> dict[Path, bytes]:
    return {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}


def test_revalidation_recovers_flags_and_prepares_exact_retries(run_root, tmp_path):
    before = _snapshot(run_root)
    out = tmp_path / "out"
    assert _main()(["--plan", str(run_root / "run-plan.json"), "--out", str(out)]) == 0
    assert _snapshot(run_root) == before  # originals untouched

    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert summary["api_calls"] == 0 and summary["analysis_only"] is False
    assert summary["cs30_imported_from"].endswith("cs30")
    jobs = {row["task"]: row for row in summary["jobs"]}

    correctness = jobs["correctness"]
    assert correctness["recovered_offline"] == 3  # c1, plus c2 and c3 as one group
    assert correctness["covered_by_existing_cache"] == 1  # c4, served by c5's cache
    assert correctness["still_unresolved"] == 1 and correctness["retry_requests"] == 1
    assert correctness["coverage_verified"] is True

    discrimination = jobs["discrimination"]
    assert discrimination["accepted_rebuilt_from_results"] == 1  # r1b's missing cache line
    assert discrimination["recovered_offline"] == 1
    assert discrimination["retry_requests"] == 1  # only the reworded r3
    assert jobs["evidence_support"]["accepted_now_invalid"] == 1
    assert jobs["evidence_support"]["retry_requests"] == 1

    prepared = [
        json.loads(line)
        for line in (out / "prepared/b/discrimination.cache.jsonl").read_text().splitlines()
    ]
    assert len(prepared) == 3
    assert [p["answer_quote_policy"] for p in prepared].count("answer-quote-v2") == 1
    assert (out / "prepared/b/evidence_support.cache.jsonl").read_text() == ""

    cache_dir = out / "prepared/b/correctness-cache"
    original_cache = run_root / "caches/b/correctness"
    for path in original_cache.iterdir():  # existing entries copied unchanged
        assert (cache_dir / path.name).read_bytes() == path.read_bytes()
    recovered = {
        p.name: json.loads(p.read_text(encoding="utf-8"))
        for p in cache_dir.glob("*.json")
        if not (original_cache / p.name).exists()
    }
    assert len(recovered) == 2  # one entry per recovered answer, not per row
    assert {v["recovered_from_run_id"] for v in recovered.values()} == {"c1", "c3"}

    retry = (out / "RETRY_COMMANDS.md").read_text(encoding="utf-8")
    assert "(1 requests)" in retry
    assert "exec-discrimination-quote-v2-retry1" in retry
    assert "-m cs30.evaluation.v2_generation_cli 'run-judge-requests'" in retry
    assert "-m cs30.evaluation.open_answer_cli 'score'" in retry
    assert "'--max-attempts' '2'" in retry  # untouched arguments survive
    assert str(cache_dir) in retry
    assert f"'{run_root / 'caches/b/discrimination.cache.jsonl'}'" not in retry


def test_analysis_only_writes_nothing_runnable(run_root, tmp_path):
    out = tmp_path / "analysis"
    assert (
        _main()(["--plan", str(run_root / "run-plan.json"), "--out", str(out), "--analysis-only"])
        == 0
    )
    assert not (out / "prepared").exists()
    retry = (out / "RETRY_COMMANDS.md").read_text(encoding="utf-8")
    assert retry.startswith("# Analysis only") and "powershell" not in retry
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert summary["totals"]["retry_requests"] == 3
    assert {j["task"]: j["coverage_verified"] for j in summary["jobs"]}["correctness"] is False


def test_missing_correctness_cache_entry_stops_before_any_command(run_root, tmp_path):
    for path in (run_root / "caches/b/correctness").iterdir():
        path.unlink()  # c5's success is no longer cached: a rerun would pay for it again
    out = tmp_path / "out"
    with pytest.raises(ValueError, match="not in the prepared cache"):
        _main()(["--plan", str(run_root / "run-plan.json"), "--out", str(out)])
    assert not (out / "RETRY_COMMANDS.md").exists()


def test_revalidation_refuses_a_non_empty_output_directory(run_root, tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    (out / "keep.txt").write_text("x", encoding="utf-8")
    with pytest.raises(SystemExit):
        _main()(["--plan", str(run_root / "run-plan.json"), "--out", str(out)])


def test_outdated_cache_hit_stops_instead_of_being_returned_or_rebought(run_root):
    request = JudgeRequest.model_validate(
        json.loads(
            (run_root / "requests/b/evidence_support.requests.jsonl").read_text(encoding="utf-8")
        )
    )
    runner = CachedJudgeRunner(
        run_root / "caches/b/evidence_support.cache.jsonl", judge_execution_id="review"
    )
    provider_calls: list[int] = []

    def provider(*_):
        provider_calls.append(1)
        raise AssertionError("no provider call expected")

    def validator(raw):
        return validate_output_against_request(raw, request)

    with pytest.raises(ValueError, match="fails current validation"):
        runner.verify_cached(request, validator)
    with pytest.raises(ValueError, match="fails current validation"):
        runner.run(request, _config(), provider, validator)
    assert provider_calls == []
