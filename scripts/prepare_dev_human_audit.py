"""Prepare a Dev-only, source-bound human audit; never score or call a provider."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

from cs30.evaluation.evaluation_audit import answer_text_sha256, prepare_calibration_and_audit
from cs30.evaluation.v2_generation_models import GenerationEvaluationInput


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def write_json(path: Path, value: object) -> None:
    path.write_bytes(
        (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
    )


def write_rows(path: Path, values: list[dict]) -> None:
    path.write_bytes(
        "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in values).encode()
    )


def candidates(items, judged_ids, exposed_questions, exposed_answers):
    """Use availability, never verdict values, to form the disclosed sampling frame."""
    selected = []
    for item in items:
        if item.source_split != "dev":
            raise ValueError("only Dev inputs are accepted")
        if (
            item.technical_failure
            or item.abstained
            or not item.answer
            or item.question_id in exposed_questions
            or answer_text_sha256(item.answer) in exposed_answers
            or item.evaluation_id not in judged_ids
        ):
            continue
        selected.append(item)
    return selected


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--package", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--private-out", required=True, type=Path)
    args = parser.parse_args()
    repo, package, out, private = (
        p.resolve() for p in (args.repo, args.package, args.out, args.private_out)
    )
    if out.exists() or private.exists():
        raise ValueError("both output directories must be new")
    if private.is_relative_to(repo) or private.is_relative_to(out):
        raise ValueError("the identity key must stay outside the Git repository and public output")
    if out.is_relative_to(package) or private.is_relative_to(package):
        raise ValueError("never write into the source handoff")
    checksums = json.loads((package / "SHA256SUMS.json").read_text(encoding="utf-8"))
    consumed = {}

    def source(relative):
        path = (package / relative).resolve()
        if not path.is_relative_to(package) or sha(path) != checksums.get(relative):
            raise ValueError(f"source binding failed: {relative}")
        consumed[relative] = sha(path)
        return path

    manifest = json.loads(source("handoff_manifest.json").read_text(encoding="utf-8"))
    if manifest.get("kind") != "development_scoring_with_explicit_missingness":
        raise ValueError("expected the reviewed Dev scoring handoff")
    batch = next(b for b in manifest["batches"] if b["batch"] == "dev-gpt-oss")
    inputs_path = source(batch["inputs"])
    items = [GenerationEvaluationInput.model_validate(r) for r in rows(inputs_path)]
    profile = json.loads(source("profile_checklist.frozen.json").read_text(encoding="utf-8"))
    if profile["package_sha256"] != (
        "1888c3b7fb6f2f0fd52dbe06455c40cef88ff8839ab47383a76d7c29a1088238"
    ):
        raise ValueError("the audit must use the reviewed frozen profile")
    jdir = batch["judge_evaluation_dir"]
    adaptation = {
        (r["evaluation_id"], r["evaluated_level"]): r
        for r in rows(source(jdir + "/adaptation_results.jsonl"))
    }
    discrimination = {
        r["evaluation_id"]: r for r in rows(source(jdir + "/discrimination_results.jsonl"))
    }
    evidence = {
        r["evaluation_id"]: r for r in rows(source(jdir + "/evidence_support_results.jsonl"))
    }
    correctness = {r["run_id"]: r for r in rows(source(batch["correctness_scores"]))}
    envelopes = {r["request_id"]: r for r in rows(source(batch["judge_results"]))}
    available = {
        i.evaluation_id
        for i in items
        if (i.evaluation_id, i.target_level.value) in adaptation
        and i.evaluation_id in discrimination
        and i.evaluation_id in evidence
    }

    # These are previously inspected Dev sources, not new reviewer judgements.
    prior_paths = [
        repo / "docs/results/m8_judge_trial_20261027/selection.json",
        repo / "docs/results/m8_low_evidence_confirmation_20261028/selected_inputs.jsonl",
        repo
        / "docs/results/m8_dev_validity_diagnostics_20261029/perturbation-draft/cases.draft.jsonl",
    ]
    exposed_questions, exposed_answers, exposure_hashes = set(), set(), {}
    for path in prior_paths:
        prior = (
            json.loads(path.read_text(encoding="utf-8")) if path.suffix == ".json" else rows(path)
        )
        exposure_hashes[path.relative_to(repo).as_posix()] = sha(path)
        for record in prior:
            exposed_questions.add(record["question_id"])
            text = record.get("answer") or record.get("original_answer")
            if text:
                exposed_answers.add(answer_text_sha256(text))
    pool = candidates(items, available, exposed_questions, exposed_answers)
    private.mkdir(parents=True)
    native = private / "native"
    paths = prepare_calibration_and_audit(
        pool,
        native,
        evaluation_inputs_sha256=sha(inputs_path),
        calibration_size=10,
        audit_size=20,
        seed=5703,
    )
    # Keep native binding semantics, but canonicalize the generated artifacts to LF.
    for key in ("calibration", "audit", "private_key"):
        write_rows(paths[key], rows(paths[key]))
    binding = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    for key in ("calibration", "audit", "private_key"):
        binding[key + "_sha256"] = sha(paths[key])
    write_json(paths["manifest"], binding)
    out.mkdir(parents=True)
    for key in ("calibration", "audit", "manifest"):
        shutil.copy2(paths[key], out / paths[key].name)
    write_json(out / "profile_checklist.frozen.json", profile)
    rubric = {
        "status": "draft_for_Leader_or_M3_confirmation",
        "purpose": "find obvious judge errors, not estimate accuracy or agreement",
        "instructions": [
            "Read the question, answer and frozen level checklist before opening saved verdicts.",
            "Record whether each saved judge dimension contains an obvious error, with a reason.",
            "Use adaptation, discrimination and evidence support for the native audit ratings.",
            "Review correctness separately when useful; it is not a native HumanAuditRating field.",
            "I3 and citation support are reference-only; review and annotate them separately.",
            "A true statement can be unsupported by the supplied evidence; truth is not support.",
            "Do not use independent audit cases to tune prompts, thresholds or the checklist.",
            "Do not mark any pending decision false merely because no review has occurred.",
        ],
        "reviewer": "Leader or M3; no completed review is claimed",
        "rating_fields": {
            "adaptation_obvious_error": "true: obvious error; false: checked, no obvious error",
            "discrimination_obvious_error": "true: obvious error; false: checked, no obvious error",
            "evidence_support_obvious_error": (
                "true: obvious error; false: checked, no obvious error"
            ),
        },
    }
    write_json(out / "human_audit_rubric.draft.json", rubric)
    rubric_sha = sha(out / "human_audit_rubric.draft.json")
    guide = [
        "# Human judge-audit guide",
        "",
        "Scope: GPT-OSS Dev only. Leader/M3 review is pending. Ten calibration/orientation "
        "cases and 20 independent audit cases are prepared, not reviewed. The orientation "
        "packet does not claim historical calibration or authorize new prompt tuning.",
        "",
        "## Review procedure",
        "",
    ]
    guide += [f"{n}. {rule}" for n, rule in enumerate(rubric["instructions"], 1)]
    guide += [
        "",
        "Open calibration_review.md for orientation if useful, then independent_review.md. "
        "Read the question and answer, apply the exact target-level criteria below, and inspect "
        "the supplied evidence. Expand the saved verdicts only after forming your own view. "
        "This is a review of obvious judge errors, not a new scoring model or accuracy estimate.",
        "",
        "Reviewers may fill the pending lines in independent_review.md in plain English. "
        "M8 then transcribes only those actual decisions into ratings.pending.jsonl, "
        "with the real rater_id, three boolean decisions and notes. "
        "True means an obvious error; false means checked with no obvious error; null means "
        "pending. Retain all IDs and hashes. The audit rubric requires reviewer confirmation. "
        "If it changes before review, regenerate its binding rather than accepting an old hash.",
        "",
        "I3 and citation support are reference-only. The native adaptation flag audits saved "
        "criterion decisions; the main intermediate aggregation separately excludes I3. "
        "Explain I3-only disagreements and distinguish bundle support from citation support "
        "in notes. A true statement can still lack support in supplied passages. Do not invent "
        "an aggregate pass threshold, word-count rule or formula-count shortcut.",
        "",
        "The native audit covers adaptation, discrimination and evidence support. Correctness "
        "scores are optional context only; a substantive correctness audit also needs the "
        "Gold/rubric and is not claimed here. Completed ratings are later checked using "
        "load_bound_human_audit and the separately stored private identity key. Pending ratings "
        "must not pass that loader. Do not publish the private identity key.",
        "",
        "## Frozen learner profiles and checklists",
        "",
        "These are the exact saved definitions. Each case specifies which target level to use. "
        "Do not change the profiles, prompts or checklist on the independent audit cases.",
        "",
        "```json",
        json.dumps(
            {"profiles": profile["profiles"], "checklists": profile["checklists"]},
            ensure_ascii=False,
            indent=2,
        ),
        "```",
        "",
    ]
    (out / "AUDIT_GUIDE.md").write_bytes("\n".join(guide).encode())
    private_rows = rows(paths["private_key"])
    by_id = {r["blinded_answer_id"]: r for r in private_rows}
    pending = []
    for row in rows(paths["audit"]):
        pending.append(
            {
                "schema_version": "1.0",
                "blinded_answer_id": row["blinded_answer_id"],
                "rater_id": None,
                "adaptation_obvious_error": None,
                "discrimination_obvious_error": None,
                "evidence_support_obvious_error": None,
                "notes": None,
                "profile_package_sha256": profile["package_sha256"],
                "rubric_sha256": rubric_sha,
            }
        )
    write_rows(out / "ratings.pending.jsonl", pending)
    for key, title in (
        ("calibration", "Calibration / orientation (not completed)"),
        ("audit", "Independent audit (pending human review)"),
    ):
        text = [
            "# " + title,
            "",
            "Read AUDIT_GUIDE.md first. Saved verdicts are collapsed below; "
            "form your own view first. No identity key is included. "
            "All human decisions are pending.",
            "",
        ]
        for number, row in enumerate(rows(paths[key]), 1):
            identity = by_id[row["blinded_answer_id"]]
            eid, level = identity["evaluation_id"], row["target_level"]
            a, d, e = adaptation[(eid, level)], discrimination[eid], evidence[eid]
            c = correctness.get(identity["run_id"])
            saved = {
                "adaptation": {
                    "criteria": a["criteria"],
                    "original_criterion_pass_rate": a["criterion_pass_rate"],
                },
                "discrimination": {
                    k: v
                    for k, v in envelopes[d["request_id"]]["output"].items()
                    if k not in {"request_id", "schema_version"}
                },
                "evidence_support": {"claims": e["claims"]},
                "correctness_optional": (
                    {k: c.get(k) for k in ("score", "score_status", "reason")} if c else None
                ),
            }
            text += [
                f"## {number}. {row['blinded_answer_id']}",
                "",
                f"Target level: **{level}**",
                "",
                "### Question",
                row["question"],
                "",
                "### Saved answer",
                row["answer"],
                "",
                "Structured citation IDs: " + json.dumps(row["citation_ids"]),
                "",
                "<details><summary>Supplied evidence (read for support review)</summary>",
                "",
            ]
            for passage in row["evidence"]:
                text += [f"**{passage['evidence_id']}**", passage["text"], ""]
            text += [
                "</details>",
                "",
                "<details><summary>Saved judge verdicts and reasons</summary>",
                "",
                "```json",
                json.dumps(saved, ensure_ascii=False, indent=2),
                "```",
                "</details>",
                "",
                "Human reviewer: pending",
                "Adaptation obvious error and reason: pending",
                "Discrimination obvious error and reason: pending",
                "Evidence-support obvious error and reason: pending",
                "I3 / citation-support reference-only observations: pending",
                "Optional correctness observation: pending",
                "",
            ]
        (
            out / ("calibration_review.md" if key == "calibration" else "independent_review.md")
        ).write_bytes("\n".join(text).encode())
    write_json(
        out / "preparation_manifest.json",
        {
            "status": "prepared_only_no_human_approval",
            "batch": "dev-gpt-oss",
            "source_files_sha256": consumed,
            "known_exposure_files_sha256": exposure_hashes,
            "known_exposed_question_count": len(exposed_questions),
            "candidate_cells": len(pool),
            "sampling": "native normalized-answer deduplication and stratified seed 5703/5704",
            "limitations": [
                "complete-case frame for the three audit dimensions; availability is not accuracy",
                "known recorded exposures excluded; unrecorded prior access cannot be ruled out",
                "only the primary generator is audited; comparators remain unaudited",
                "ten orientation cases are new material, not proof of historical calibration",
            ],
            "calibration_count": 10,
            "independent_audit_count": 20,
            "completed_ratings": 0,
            "rubric_sha256": rubric_sha,
            "api_calls": 0,
            "identity_key_in_repository": False,
        },
    )
    print(
        json.dumps(
            {
                "candidate_cells": len(pool),
                "calibration": 10,
                "audit": 20,
                "known_exposed_questions_excluded": len(exposed_questions),
                "api_calls": 0,
            }
        )
    )


if __name__ == "__main__":
    main()
