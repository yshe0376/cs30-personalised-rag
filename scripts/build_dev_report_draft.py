"""Make an exploratory Dev narrative from existing reports; no new scores or API calls."""

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    package, out = args.package.resolve(), args.out.resolve()
    if out.exists() or out.is_relative_to(package):
        raise ValueError("use a new output folder outside the immutable source package")
    hashes = json.loads((package / "SHA256SUMS.json").read_text(encoding="utf-8"))
    used = {}

    def source(relative):
        path = (package / relative).resolve()
        if not path.is_relative_to(package):
            raise ValueError("source path escapes the package")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != hashes.get(relative):
            raise ValueError("source hash mismatch: " + relative)
        used[relative] = digest
        return path

    manifest = json.loads(source("handoff_manifest.json").read_text(encoding="utf-8"))
    if manifest.get("kind") != "development_scoring_with_explicit_missingness":
        raise ValueError("only the reviewed Dev handoff is accepted")
    reports = {
        name: json.loads(
            source(f"development_reports/dev-{name}/v2_generation_evaluation.json").read_text(
                encoding="utf-8"
            )
        )
        for name in ("gpt-oss", "llama", "gemma")
    }
    if any(r["mode"] != "development" or r["reportable"] for r in reports.values()):
        raise ValueError("expected saved non-reportable development reports")
    text = [
        "# Dev evaluation report draft and human-audit handoff",
        "",
        "**Draft; reportable=false.** No completed independent human audit is claimed. "
        "Dev-only preparation; no Test answers were read and no API was called.",
        "",
        "## Start here",
        "",
        "Leader/M3: read [the audit guide](audit/AUDIT_GUIDE.md), confirm the draft audit "
        "rubric, optionally inspect calibration_review.md, then review the 20 cases in "
        "[independent_review.md](audit/independent_review.md). Fill actual decisions in "
        "the pending lines in the review sheet; M8 transcribes them to ratings.pending.jsonl "
        "and later checks the ratings with the private binding key and "
        "native load_bound_human_audit. Preparing this packet does not complete an audit.",
        "",
        "Selected scope: GPT-OSS only, with ten orientation/calibration cases and 20 independent "
        "audit cases. Llama and Gemma remain unaudited. The orientation cases are not proof "
        "of completed historical calibration or permission to tune the frozen judge. This "
        "local branch depends on the #223 follow-up; no new PR or Release update is implied.",
        "",
        "## Scope and sources",
        "",
        "154 Dev questions x three levels x four conditions = 1,848 cells per generator; "
        "5,544 primary Dev cells. A separate 30-question generation-repeat cohort contributes "
        "360 cells per generator (1,080 total). Combined handoff coverage is 6,624 cells; "
        "repeat cells do not enlarge the primary Dev denominator.",
        "",
        "Arms: P0R0 plain, P1R0 prompt-only, P0R1 reranking-only, P1R1 combined. All four "
        "tasks were scored. Lambda=0.1; gemini-3.1-flash-lite, thinking low, temperature 1; "
        "frozen profile 1888c3b7. Its independent physics review was waived, not completed.",
        "",
        "Source: [existing Dev Release](https://github.com/yshe0376/cs30-personalised-rag/"
        "releases/tag/v2-m8-full-dev-low-20261028), scoring archive SHA-256 "
        "da1b860a1204bb16a79026c5433614fa0d1b6202dfdbf9502d725e871969d07e. "
        "All original scores, caches and logs remain unchanged.",
        "",
        "## Correctness coverage (primary Dev only)",
        "",
        "| Generator | Cells | Strict-correct | Unresolved | Strict-correct bounds |",
        "|---|---:|---:|---:|---|",
    ]
    for name, report in reports.items():
        c = report["automatic_full_run"]["correctness"]
        lo, hi = c["strict_correct_rate_bounds"]
        text.append(
            f"| {name} | {c['denominator']} | {c['strict_correct_count']} | "
            f"{c['unresolved_count']} | {100 * lo:.2f}% - {100 * hi:.2f}% |"
        )
    text += [
        "",
        "Unresolved judgements remain unknown in the denominator; no complete-case "
        "point accuracy is substituted. Mean score/2 is not accuracy. Generation failures "
        "and unresolved judge outputs are distinct.",
        "",
        "## Saved exploratory contrasts (legacy I3-inclusive basis)",
        "",
        "Adaptation below is a continuous mean criterion pass rate, not a thresholded answer "
        "pass rate. The saved contrasts include I3 and are not the final revised primary "
        "analysis. Intervals are the saved question-cluster bootstrap intervals. No primary "
        "contrast, multiplicity correction or non-inferiority margin is invented.",
        "",
        "| Generator | Metric | Contrast | Difference (pp) | Interval (pp) | Missing pairs |",
        "|---|---|---|---:|---|---:|",
    ]
    for name in reports:
        with source(f"development_reports/dev-{name}/v2_generation_condition_contrasts.csv").open(
            encoding="utf-8", newline=""
        ) as stream:
            for row in csv.DictReader(stream):
                if row["metric"] not in {"strict_correct", "adaptation_criterion_pass_rate"}:
                    continue
                text.append(
                    f"| {name} | {row['metric']} | {row['contrast']} | "
                    f"{100 * float(row['estimate']):+.2f} | "
                    f"[{100 * float(row['ci_lower']):+.2f}, "
                    f"{100 * float(row['ci_upper']):+.2f}] | {row['missing_pair_count']} |"
                )
    text += [
        "",
        "Reranking effects are not clearly demonstrated in these exploratory comparisons; "
        "this is not proof of no effect. These are judge evaluations, not learner outcomes.",
        "",
        "## I3 and supporting diagnostics",
        "",
        "The Leader confirmed intermediate-i3-reference-only-v1: main intermediate rates use "
        "I1/I2 and report I3 separately, without changing the checklist or prompts. The "
        "[Dev I3 comparison](../m8_dev_validity_diagnostics_20261029/perturbation-results/"
        "DEV_I3_SENSITIVITY.md) gives paired available-cell changes of 0.00 pp for GPT-OSS, "
        "-0.44 pp for Gemma and -1.66 pp for Llama in the native main intermediate scope. "
        "The original handoff retains legacy aggregates. Final reporting must explicitly "
        "apply the new policy and recompute the selected contrasts consistently.",
        "",
        "[Existing diagnostics](../m8_dev_validity_diagnostics_20261029/REPORT.md) provide "
        "P0R0 observations, within-level length/formula associations, generation-plus-judge "
        "noise, optional N/A proportions and task/model/level/condition missingness. They "
        "are descriptive, not a blanket validity pass.",
        "",
        "## Human audit status and limits",
        "",
        "The native sampler uses fixed seed 5703/5704, normalized-answer deduplication, "
        "disjoint calibration/audit sets and coverage of all three levels and four conditions. "
        "Known trial, evidence-confirmation and perturbation exposures are excluded by question "
        "and answer. The frame requires resolved adaptation, discrimination and evidence "
        "outputs; it cannot validate unresolved cases. Unrecorded prior exposure cannot be "
        "ruled out. Metadata is hidden in reviewer packets, but public answers may still be "
        "recognizable. No completed review or reviewer identity is fabricated.",
        "",
        "The native audit detects obvious errors in three judge dimensions; it is not an "
        "accuracy or inter-rater-agreement estimate. Correctness observations are optional "
        "context and need Gold/rubric material for substantive review. Never tune the judge "
        "on independent audit cases. Pending ratings must fail native import until filled.",
        "",
        "## Validity findings and claim limits",
        "",
        "The perturbation audit detected 15/18 with I3 0/3; the original rule failed. The "
        "Leader accepted the reduced section 6 scope with I3 reference-only. No should-pass "
        "controls were run, so false-fail rate is unmeasured; evidence-llama is one observed "
        "correctness false fail. Non-target changes may include randomness. There was no "
        "independent same-answer retest, position-order check or second-family judge. Repeat "
        "measurements combine generation and judge noise; Test differences below the "
        "applicable metric-specific noise floor must not be reported as differences. "
        "Gemma/Gemini share a vendor; any Gemma advantage needs this caveat. Citation support "
        "is reference-only because of the structured citation_ids issue noted by the Leader.",
        "",
        "## Pending decisions and next steps",
        "",
        "| Item | Owner / next step | State |",
        "|---|---|---|",
        "| Primary-model human audit | Leader/M3 reviews; M8 validates ratings | "
        "prepared, not completed |",
        "| Comparator human audits | outside the selected scope | not completed |",
        "| Primary metric/contrast, delta, adaptation pass threshold, multiplicity | "
        "team registers decisions | pending confirmation |",
        "| I3/reduced validity scope | Leader registers #223 decisions | "
        "confirmed in review; verify registration |",
        "| Profile/eligibility and report provenance | owners freeze/review; "
        "M8 binds actual records | not cleared here |",
        "| Test models, sample size, seeded sample | Leader/M7 | separate prerequisite |",
        "| 187 Test correctness rubrics | designated reviewers | separate prerequisite |",
        "",
        "Saved native report blockers also include unresolved scores and unbound decision "
        "fields. Preserve those blockers; do not set reportable=true because a packet or PR "
        "exists. After actual review and decisions, update the narrative and versioned "
        "analysis. The original reports remain immutable evidence of the earlier state.",
        "",
        "Until all five #222 gates are recorded, no reading, sampling, summarizing or scoring "
        "of Test answers is allowed. Test scoring and budget are later tasks; this packet "
        "does not authorize any provider call.",
        "",
    ]
    missing = defaultdict(lambda: [0, 0, 0])
    with source("missingness_by_task_model_level_condition.csv").open(
        encoding="utf-8", newline=""
    ) as stream:
        for row in csv.DictReader(stream):
            if row["cohort"] == "dev":
                group = missing[(row["generator"], row["task"])]
                for index, field in enumerate(("applicable_cells", "scored", "missing")):
                    group[index] += int(row[field])
    text += ["## Primary Dev task coverage", "",
             "Cell-level counts from the saved missingness table, not unique API requests. "
             "Repeat batches are excluded. Evidence coverage differs by generator; missing "
             "judgements are not zero or automatically N/A.", "",
             "| Generator | Task | Applicable cells | Scored | Missing | Missing rate |",
             "|---|---|---:|---:|---:|---:|"]
    for (generator, task), (total, scored, count) in sorted(missing.items()):
        rate = f"{count / total:.2%}" if total else "N/A"
        text.append(f"| {generator} | {task} | {total} | {scored} | {count} | {rate} |")
    text += ["", "For full level/condition breakdowns use the unchanged source missingness "
             "tables. No threshold-based adaptation pass rate is inferred.", ""]
    out.mkdir(parents=True)
    (out / "DEV_REPORT_DRAFT.md").write_bytes("\n".join(text).encode())
    (out / "report_sources.json").write_bytes(
        (
            json.dumps(
                {"reportable": False, "source_files_sha256": used, "api_calls": 0},
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode()
    )


if __name__ == "__main__":
    main()
