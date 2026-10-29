# Test scoring preparation after PR #224

Status: local implementation for review; no paid execution or Test findings.
Base: main `133e2389bd7220b7d6bd8578c182072325117556`.
Decision: [Leader's five Test gates](https://github.com/yshe0376/cs30-personalised-rag/pull/224).

## Scope and sequence

1. Validate the approved profile and eligibility labels using the recorded Leader
   waiver. This records waived reviews, not completed human reviews. The existing
   evidence-based validation path still requires its calibration evidence.
2. Before scoring, bind all 187 Test rubric hashes, the complete Test ID set, Gold,
   judge configuration and validation record into a new readiness file. Compare
   the rubric file digest against the approved M7 source manifest. Do not open
   generated Test answers as part of this step.
3. Review this implementation and its numerical choices before Test scoring.
   Confirm the separately approved Test budget. This branch does not authorize
   expenditure or launch any scoring job.
4. Run scoring later with the existing frozen providers, prompts and retry/usage
   logging. Keep Test results, caches and attempt ledgers separate from Dev.
   Expected scope: 187 questions x 3 levels x 4 conditions = 2,244 cells per
   generator, for GPT-OSS, Gemma and Llama. No subsampling.
5. After scoring, validate the existing M7 adapter and correctness binding, all
   judge-file digests and run provenance; then calculate a separate analysis JSON.
   Original scores, criterion verdicts, caches and source artifacts stay unchanged.

M7's generation schema and shared runtime contracts are consumed unchanged.
The added code belongs to evaluation input validation and reporting. No generation
code, provider, judge prompt, quote validator, cache key or attempt limit changes.

## Recorded reporting rules

- Gemini `gemini-3.1-flash-lite`, thinking `low`, unchanged full-Dev configuration;
  profile `1888c3b7...`, answer-quote-v2.
- Main adaptation uses full and endpoint_only eligibility. Intermediate main
  adaptation uses I1/I2; I3 remains visible as reference-only. Joint "correct and
  adapted" requires strict correctness and every applicable main criterion passing.
- GPT-OSS P1R0 minus P0R0 at beginner and advanced forms a family of exactly two
  co-primary tests. Holm alpha is 0.05. Missing endpoints do not shrink the family.
  Other models are exploratory; their raw results do not receive a primary claim.
- Correctness non-inferiority uses the same contrast, pooled over all levels,
  delta 0.03. Resample whole questions, retaining their level pairs together.
  Generation failures/abstentions have fixed system zero. Answered but unscored
  responses remain unknown; both worst- and best-case intervals must meet the bound.
  Condition coverage includes end-to-end and answered-only correctness bounds.
- Discrimination and citation support remain reference-only. Do not derive a fix
  to citation_ids or add a new citation missingness rule.

The implementation uses 2,000 question-cluster bootstrap draws, seed 5703,
percentile 95% intervals, and a two-sided null-centred bootstrap p-value with a
plus-one correction. Holm adjusts the two p-values; the displayed percentile
intervals are **unadjusted**, not simultaneous Holm intervals. These are explicit
implementation choices for review, not additional numerical decisions attributed
to the Leader. No Test outcomes were used to choose them.

Positive adaptation claims additionally require a same-metric, same-level Dev
generation-repeat noise floor. Without one, `positive_effect_supported` is false.
A supplied noise-floor record must name the policy/profile, `source_split: dev`,
`metric: adaptation_criterion_pass_rate`, `scope: generation_repeat`, a source
artifact SHA-256, and `adaptation_noise_floors` for beginner/advanced. Its derivation
and source must be reviewed; supplying a hash alone does not prove its calculation.
Judge-repeat uncertainty has not been measured and must not be invented.

## Offline entry points

Run from this checkout, with PYTHONPATH pointing at its src directory. Use the
matching environment's Python. Paths in angle brackets are placeholders, not
commands to paste unchanged. Use a new output path for each readiness/analysis file.

```powershell
$env:PYTHONPATH = "$PWD\src"
python -m cs30.evaluation.v2_generation_cli validate-inputs --profiles docs/evaluation/level-profile-v1/profile_checklist.frozen.json --eligibility docs/evaluation/eligibility-v1/personalisation_eligibility_v1.jsonl --gold <Gold.jsonl> --gold-version <approved-version> --eligibility-version v1 --eligibility-review-waiver eval_inputs/m8/test-gates-20261029/eligibility-review-waiver.json --reportable --output <input-validation.json>
python -m cs30.evaluation.test_gate_readiness prepare --profiles docs/evaluation/level-profile-v1/profile_checklist.frozen.json --judge-config docs/results/m8_dev_validity_diagnostics_20261029/perturbation-results/run/config/judge-config.low.json --input-validation <input-validation.json> --gold <Gold.jsonl> --rubrics <approved-Test-rubrics.jsonl> --expected-rubrics-sha256 <SHA-from-approved-M7-manifest> --question-ids <Test-IDs.txt> --split-map docs/examples/v2-generation-split-dev154-test187.json --output <readiness.json>
```

Preparation accepts IDs, rubrics and metadata only. It has no generated-answer,
API key, provider execution or paid-run option. Offline tests use fictional Gold,
rubrics and answers; public Test IDs and frozen configuration metadata are used
only to verify the guards.

After scoring, `python -m cs30.evaluation.test_gate_readiness report --help` lists
the source-bound analysis inputs. This command reads scored Test artifacts and
must not run during preparation. It produces a draft analysis with `reportable:
false`; it neither fabricates a human audit nor bypasses legacy reportability
checks. It is not a replacement for the complete final report, exploratory
comparison tables or the existing M7 handoff verifier.

## Required disclosures

Eligibility calibration/content review and Test rubric independent review were
waived, not performed. Report the reduced validity scope, lack of paid same-answer
retesting/order reversal/second-family judge/should-pass controls, I3 limitations,
reference-only metrics and the same-vendor Gemini/Gemma caveat. The result concerns
judge evaluations of generated answers, not measured learning outcomes.
