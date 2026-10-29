# Test scoring preparation after PR #224

Status: PR #225 review fixes and committed pre-scoring records; no paid execution or Test findings.
Base: main `133e2389bd7220b7d6bd8578c182072325117556`.
Decisions: [five Test gates](https://github.com/yshe0376/cs30-personalised-rag/pull/224),
[main-model-only revision](https://github.com/yshe0376/cs30-personalised-rag/pull/226), and
[PR #225 review](https://github.com/yshe0376/cs30-personalised-rag/pull/225#issuecomment-6494640705).

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
   generator: GPT-OSS only under #226. No subsampling. Gemma/Llama comparisons remain
   exploratory Dev-only findings with no held-out Test confirmation.
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
intervals are **unadjusted**, not simultaneous Holm intervals. The Leader approved these implementation choices in the PR #225 review.
The output states that co-primary decisions use Holm-adjusted p-values and that
intervals are descriptive. No Test outcomes were used to choose them.

Adaptation analyses use complete question pairs. Unscored pair counts remain next
to each estimate; a missing pair does not veto the complete-pair result. Correctness
still uses unresolved-score bounds as registered. Positive and negative effects use
the same Holm rule and must exceed the Dev generation-repeat noise floor in absolute
magnitude before a directional effect is supported.

The frozen noise-floor definition is `sqrt(mean((repeat_rate - baseline_rate)^2) / n)`.
It pools available P0R0/P1R0 per-answer main rates at each endpoint and uses the Test
eligible pair count as n. The immutable GPT-OSS Dev package supplies 42 resolved
repeat cells (21 in each condition) per endpoint, with no missing cells; n is 128 at
each Test endpoint. The resulting floors are 0.014286230976105822 (beginner) and
0.02123253445022271 (advanced). This is generation-repeat noise, not a measured
same-answer judge-repeat floor. Source hashes, formula, counts and generator binding
are in `eval_inputs/m8/test-gates-20261029/dev-adaptation-noise-floors.json`.

## Offline entry points

Run from this checkout, with PYTHONPATH pointing at its src directory. Use the
matching environment's Python. Paths in angle brackets are placeholders, not
commands to paste unchanged. Use a new output path for each readiness/analysis file.

```powershell
$env:PYTHONPATH = "$PWD\src"
python -m cs30.evaluation.v2_generation_cli validate-inputs --profiles docs/evaluation/level-profile-v1/profile_checklist.frozen.json --eligibility docs/evaluation/eligibility-v1/personalisation_eligibility_v1.jsonl --gold <Gold.jsonl> --gold-version <approved-version> --eligibility-version v1 --eligibility-review-waiver eval_inputs/m8/test-gates-20261029/eligibility-review-waiver.json --allow-eligibility-superset --reportable --output <input-validation.json>
python -m cs30.evaluation.test_gate_readiness prepare --profiles docs/evaluation/level-profile-v1/profile_checklist.frozen.json --judge-config docs/results/m8_dev_validity_diagnostics_20261029/perturbation-results/run/config/judge-config.low.json --input-validation <input-validation.json> --gold <Gold.jsonl> --rubrics <approved-Test-rubrics.jsonl> --expected-rubrics-sha256 <SHA-from-approved-M7-manifest> --question-ids <Test-IDs.txt> --split-map docs/examples/v2-generation-split-dev154-test187.json --noise-floors eval_inputs/m8/test-gates-20261029/dev-adaptation-noise-floors.json --output <readiness.json>
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

## Completed pre-scoring records

`eval_inputs/m8/test-gates-20261029/` contains the actual input validation,
187 public Test IDs, the full per-question rubric hash readiness record,
Dev adaptation noise floors and the M7 rubric-source receipt. The readiness record
binds the noise-floor file digest and lists `comparison_models: []`.

The official M7 archive was checked against SHA-256 `c9545bf5...4511ebc`.
Only the three files under `test-correctness-rubrics/` were extracted. Gold was
reused from the existing Dev delivery and its hash matched the rubric manifest.
No generated Test answer file was extracted or read. The raw rubric digest is
`0dd87977f7a24747ec7677828b39b28e15dbc6d73d52f37e7c64fc09e100e6fc`;
the canonical 187-rubric set digest is recorded in `readiness.json`.
The archive and rubric contents stay outside Git.

Label superset acceptance now has its own `--allow-eligibility-superset` option;
it is independent of whether review evidence or a Leader waiver is supplied.
Missing required labels are always rejected. Existing callers retain exact
coverage by default.

Recompute the noise record offline from a freshly verified Dev handoff using
`python -m cs30.evaluation.test_gate_noise --dev-package <Dev-package> --eligibility
docs/evaluation/eligibility-v1/personalisation_eligibility_v1.jsonl --split-map
docs/examples/v2-generation-split-dev154-test187.json --output <new-noise-record.json>`.
The command checks source hashes and Dev-only metadata. It never accepts Test
answers and refuses to overwrite output.

## Required disclosures

Eligibility calibration/content review and Test rubric independent review were
waived, not performed. Report the reduced validity scope, lack of paid same-answer
retesting/order reversal/second-family judge/should-pass controls, I3 limitations,
reference-only metrics and the same-vendor Gemini/Gemma caveat. The result concerns
judge evaluations of generated answers, not measured learning outcomes.

## Local Windows test execution

The FAISS installation is functional: standalone insertion/search and all ten
FAISS tests pass. The managed Windows sandbox reproduces a FAISS DLL initialization
failure (`0xc0000008`) with default file-descriptor capture; disabling native
capture allows collection, but UI tests then stall inside that sandbox. Normal
Windows execution outside the sandbox successfully collects the full suite even
with default capture. A full run outside the sandbox with `--capture=sys` completes
with 1,565 passed and 2 skipped at the initial commit `ba10841`.

This identifies local execution-environment restrictions, not a demonstrated
retrieval-code defect. No dependency reinstall, test exclusion, blanket DLL
suppression, retrieval modification or CI change was made. Use a normal VS Code
PowerShell terminal for full-suite verification. `--capture=sys` is an optional
supported output-capture mode, not a requirement to change production behaviour.

In a disposable PowerShell terminal, from the repository root:

```powershell
$env:PYTHONPATH = "$PWD\src"
$localTestTemp = Join-Path $PWD '..\W8\test-scoring-readiness-20261029\native-temp'
New-Item -ItemType Directory -Force $localTestTemp | Out-Null
$env:TMP = (Resolve-Path $localTestTemp).Path
$env:TEMP = $env:TMP
python -m pytest --capture=sys -p no:cacheprovider --basetemp ..\W8\t225-local
```

The workspace temporary directory also avoids the separate sandbox temporary-file
cleanup permission error. Keep the pytest base directory short: deep checkpoint
fixtures can exceed Windows path limits when the base directory has a long name.
Use a new directory reserved for test fixtures; pytest may clear an existing base
directory when starting a run. These environment settings apply only to that terminal.
No dependency reinstall, test exclusion, blanket DLL suppression, or change to CI
is needed to try this execution mode. See the
[pytest capture documentation](https://docs.pytest.org/en/stable/how-to/capture-stdout-stderr.html).
