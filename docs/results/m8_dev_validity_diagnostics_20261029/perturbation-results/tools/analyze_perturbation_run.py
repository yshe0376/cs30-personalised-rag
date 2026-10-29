"""Step 6 of the M8 small perturbation audit: offline detection analysis.

Reads the run folder produced by START_PERTURBATION.ps1, re-validates every judge output
with the repository's canonical assembly, applies the detection rules recorded in #220
(PLAN_DRAFT.json detection_scoring_proposal) and compares each perturbed answer with its
original full-Dev scores. No API calls.
Usage: python analyze_perturbation_run.py --repo REPO --run RUN_DIR \
    --scoring-package HANDOFF_DIR --out OUT_DIR
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import sys
from pathlib import Path

DETECTION_RATE = 0.8
PER_TARGET_MIN = 1
PRICE = {
    "input_usd_per_million": 0.25,
    "output_usd_per_million": 1.50,
    "usd_to_aud": 1.50,
    "input_multiplier": 1.15,
}


def rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def norm(text: str) -> str:
    return " ".join(text.split())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo", type=Path, required=True)
    ap.add_argument("--run", type=Path, required=True)
    ap.add_argument("--scoring-package", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    if a.out.exists():
        raise SystemExit("output exists; refusing to overwrite")
    sys.path.insert(0, str(a.repo / "src"))
    from cs30.evaluation import v2_generation_cli as cli
    from cs30.evaluation.judge_results import assemble_judge_results, load_judge_envelopes
    from cs30.evaluation.level_profiles import load_profile_checklist_package
    from cs30.evaluation.v2_generation_models import JudgeConfiguration

    run, pkg = a.run, a.scoring_package
    cases_spec = {
        c["case_id"]: c
        for c in rows(
            a.repo
            / "docs/results/m8_dev_validity_diagnostics_20261029"
            / "perturbation-draft/cases.draft.jsonl"
        )
    }
    case_map = json.loads((run / "case_map.json").read_text(encoding="utf-8"))
    items = cli._load_inputs(run / "inputs/perturbed_generation_evaluation_inputs.jsonl")
    profile = load_profile_checklist_package(run / "config/profile_checklist.frozen.json")
    config = JudgeConfiguration.model_validate_json(
        (run / "config/judge-config.low.json").read_text(encoding="utf-8")
    )
    envelopes = {}
    for task in ("adaptation", "discrimination", "evidence_support"):
        envelopes.update(load_judge_envelopes(run / f"results/{task}.results.jsonl"))
    assembled = assemble_judge_results(items, profile, config, envelopes)
    corr = {r["run_id"]: r for r in rows(run / "results/correctness/open_answer_scores.jsonl")}

    # Baseline: original full-Dev scores for the same answers before the edit.
    manifest = json.loads((pkg / "handoff_manifest.json").read_text(encoding="utf-8"))
    base_adapt, base_disc, base_ev, base_corr = {}, {}, {}, {}
    for b in manifest["batches"]:
        if not b["batch"].startswith("dev-"):
            continue
        jdir = pkg / b["judge_evaluation_dir"]
        for r in rows(jdir / "adaptation_results.jsonl"):
            base_adapt[(r["evaluation_id"], r["evaluated_level"])] = r
        for r in rows(jdir / "discrimination_results.jsonl"):
            base_disc[r["evaluation_id"]] = r
        for r in rows(jdir / "evidence_support_results.jsonl"):
            base_ev[r["evaluation_id"]] = r
        for r in rows(pkg / b["correctness_scores"]):
            base_corr[r["run_id"]] = r

    adapt = collections.defaultdict(dict)
    for r in assembled["adaptation"]:
        adapt[r["evaluation_id"]][r["evaluated_level"]] = r
    disc = {r["evaluation_id"]: r for r in assembled["discrimination"]}
    ev = {r["evaluation_id"]: r for r in assembled["evidence_support"]}
    unresolved = collections.defaultdict(list)
    for u in assembled["unresolved"]:
        unresolved[u["evaluation_id"]].append(u)

    results = []
    for cm in case_map:
        spec = cases_spec[cm["case_id"]]
        eid, beid, level = (
            cm["perturbed_evaluation_id"],
            cm["base_evaluation_id"],
            cm["target_level"],
        )
        target = cm["target"]
        edit = (
            spec["single_edit"]
            if isinstance(spec["single_edit"], dict)
            else json.loads(spec["single_edit"])
        )
        rec = {
            k: cm[k]
            for k in (
                "case_id",
                "target",
                "generator",
                "difficulty_proposal",
                "target_level",
                "condition",
                "base_evaluation_id",
            )
        }
        rec["perturbed_span"] = edit.get("perturbed_span")
        rec["original_span"] = edit.get("original_span")
        # ---- target detection
        if target in ("B1", "B4", "A1", "I3"):
            out = adapt[eid].get(level)
            if out is None:
                rec.update(
                    status="unresolved",
                    detected=False,
                    target_verdict=None,
                    unresolved_reason=[
                        u["reason"]
                        for u in unresolved[eid]
                        if u["dimension"] == "adaptation" and u.get("evaluated_level") == level
                    ],
                )
            else:
                verdict = {c["criterion_id"]: c for c in out["criteria"]}[target]
                rec.update(
                    status="resolved",
                    detected=verdict["verdict"] == "fail",
                    target_verdict=verdict["verdict"],
                    target_reason=verdict.get("reason"),
                    target_quote=verdict.get("exact_quote"),
                )
        elif target == "correctness":
            c = corr[cm["perturbed_run_id"]]
            if c["score_status"] != "scored":
                rec.update(
                    status="unresolved",
                    detected=False,
                    correctness_score=None,
                    unresolved_reason=c["score_status"],
                )
            else:
                rec.update(
                    status="resolved",
                    detected=c["score"] < 2,
                    correctness_score=c["score"],
                    target_reason=c.get("reason"),
                )
        else:  # evidence_support
            out = ev.get(eid)
            if out is None:
                rec.update(
                    status="unresolved",
                    detected=False,
                    unresolved_reason=[
                        u["reason"] for u in unresolved[eid] if u["dimension"] == "evidence_support"
                    ],
                )
            else:
                added = norm(edit["perturbed_span"])
                original = norm(edit.get("original_span") or "")
                # inserted material = the part of the perturbed span not in the original span
                new_text = (
                    added.replace(original, " ").strip()
                    if original and original in added
                    else added
                )
                key_phrases = [p for p in (new_text[:40], new_text[-40:]) if p.strip()]
                covering = [
                    cl
                    for cl in out["claims"]
                    if any(
                        norm(p) in norm(cl["claim_text"]) or norm(cl["claim_text"]) in new_text
                        for p in key_phrases
                    )
                ]
                verdicts = [cl["bundle_support"] for cl in covering]
                rec.update(
                    status="resolved",
                    detected=any(v == "unsupported" for v in verdicts),
                    covering_claims=[
                        {
                            "claim_text": cl["claim_text"],
                            "bundle_support": cl["bundle_support"],
                            "reason": cl.get("reason"),
                        }
                        for cl in covering
                    ],
                    target_note=None
                    if covering
                    else "no extracted claim covers the inserted subclaim",
                )
        # ---- non-target comparison with the original full-Dev scores
        changes = {}
        for lvl, out in adapt[eid].items():
            base = base_adapt.get((beid, lvl))
            if base is None:
                continue
            bv = {c["criterion_id"]: c["verdict"] for c in base["criteria"]}
            for c in out["criteria"]:
                if (
                    target in ("B1", "B4", "A1", "I3")
                    and lvl == level
                    and c["criterion_id"] == target
                ):
                    continue
                if bv.get(c["criterion_id"]) != c["verdict"]:
                    changes.setdefault("adaptation", []).append(
                        f"{lvl}:{c['criterion_id']} {bv.get(c['criterion_id'])}->{c['verdict']}"
                    )
        if target != "correctness":
            c, b = corr.get(cm["perturbed_run_id"]), base_corr.get(cm["base_run_id"])
            if c and b and (c["score_status"], c["score"]) != (b["score_status"], b["score"]):
                changes["correctness"] = (
                    f"{b['score_status']}:{b['score']} -> {c['score_status']}:{c['score']}"
                )
        if (
            eid in disc
            and beid in base_disc
            and disc[eid]["predicted_level"] != base_disc[beid]["predicted_level"]
        ):
            changes["discrimination"] = (
                f"{base_disc[beid]['predicted_level']} -> {disc[eid]['predicted_level']}"
            )
        if target != "evidence_support" and eid in ev and beid in base_ev:
            if (ev[eid]["bundle_unsupported_count"], ev[eid]["citation_unsupported_count"]) != (
                base_ev[beid]["bundle_unsupported_count"],
                base_ev[beid]["citation_unsupported_count"],
            ):
                changes["evidence_support"] = (
                    "unsupported bundle/citation "
                    f"{base_ev[beid]['bundle_unsupported_count']}/"
                    f"{base_ev[beid]['citation_unsupported_count']}"
                    f" -> {ev[eid]['bundle_unsupported_count']}/"
                    f"{ev[eid]['citation_unsupported_count']}"
                )
        nontarget_unresolved = [
            u["dimension"] + (":" + u["evaluated_level"] if u.get("evaluated_level") else "")
            for u in unresolved[eid]
            if not (
                u["dimension"] == ("adaptation" if target in ("B1", "B4", "A1", "I3") else target)
                and (u.get("evaluated_level") in (None, level))
            )
        ]
        if target != "correctness" and corr.get(cm["perturbed_run_id"], {}).get(
            "score_status"
        ) not in (None, "scored"):
            nontarget_unresolved.append("correctness")
        rec["non_target_changes"] = changes
        rec["non_target_unresolved"] = nontarget_unresolved
        results.append(rec)

    by_target = collections.OrderedDict()
    for t in ("B1", "B4", "A1", "I3", "correctness", "evidence_support"):
        group = [r for r in results if r["target"] == t]
        by_target[t] = {
            "cases": len(group),
            "detected": sum(r["detected"] for r in group),
            "unresolved": sum(r["status"] == "unresolved" for r in group),
        }
    detected = sum(r["detected"] for r in results)
    rate = detected / len(results)
    rule_pass = rate >= DETECTION_RATE and all(
        v["detected"] >= PER_TARGET_MIN for v in by_target.values()
    )
    by_difficulty = collections.OrderedDict(
        (
            d,
            {
                "cases": sum(r["difficulty_proposal"] == d for r in results),
                "detected": sum(r["detected"] for r in results if r["difficulty_proposal"] == d),
            },
        )
        for d in ("clear", "moderate", "subtle")
    )

    usage = {
        "attempts": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "unknown_usage": 0,
        "status": collections.Counter(),
    }
    for f in sorted((run / "ledgers").glob("*.jsonl")):
        for r in rows(f):
            usage["attempts"] += 1
            usage["status"][r.get("status")] += 1
            if r.get("usage_available") is False:
                usage["unknown_usage"] += 1
            usage["input_tokens"] += r.get("input_tokens") or 0
            usage["output_tokens"] += r.get("output_tokens") or 0
    input_usd = usage["input_tokens"] / 1e6 * PRICE["input_usd_per_million"]
    output_usd = usage["output_tokens"] / 1e6 * PRICE["output_usd_per_million"]
    usage["status"] = dict(usage["status"])
    usage["known_list_price_usd"] = round(input_usd + output_usd, 6)
    usage["adjusted_estimate_aud"] = round(
        (input_usd * PRICE["input_multiplier"] + output_usd) * PRICE["usd_to_aud"], 4
    )
    usage["pricing_assumptions"] = PRICE

    summary = {
        "audit": "M8 small perturbation audit v2 (Dev-only synthetic answers)",
        "cases": len(results),
        "detected": detected,
        "detection_rate": round(rate, 4),
        "rule": (
            f">= {int(DETECTION_RATE * 100)}% overall and >= {PER_TARGET_MIN} detected per target; "
            "unresolved count as not detected"
        ),
        "rule_passed": rule_pass,
        "by_target": by_target,
        "by_difficulty_proposal": by_difficulty,
        "unresolved_target_cases": sum(r["status"] == "unresolved" for r in results),
        "cases_with_non_target_changes": sum(bool(r["non_target_changes"]) for r in results),
        "usage": usage,
        "inputs_sha256": {
            "case_map.json": sha(run / "case_map.json"),
            "adaptation.results.jsonl": sha(run / "results/adaptation.results.jsonl"),
            "discrimination.results.jsonl": sha(run / "results/discrimination.results.jsonl"),
            "evidence_support.results.jsonl": sha(run / "results/evidence_support.results.jsonl"),
            "correctness/open_answer_scores.jsonl": sha(
                run / "results/correctness/open_answer_scores.jsonl"
            ),
        },
        "interpretation": (
            "Targeted sensitivity examples written and reviewed before scoring; "
            "not population judge accuracy."
        ),
    }
    a.out.mkdir(parents=True)
    (a.out / "perturbation_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    with (a.out / "perturbation_cases.jsonl").open("w", encoding="utf-8", newline="\n") as s:
        for r in results:
            s.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
