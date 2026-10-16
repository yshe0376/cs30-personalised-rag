# V2 generation evaluation

This document describes the M8-owned evaluation extension for saved V2 answers. It does not
run retrieval, reranking, answer generation, lambda-search generation, or Test generation.

## Ownership boundary

M8 owns:

- frozen profile/checklist and eligibility validation;
- level-adaptation, blind level-discrimination, and semantic evidence-support judge tasks;
- judge cache binding, quote verification, and automatic validity checks;
- question-paired condition contrasts, question-cluster bootstrap, and non-inferiority;
- de-duplicated human calibration/audit packets; and
- separated development reporting.

The generation owner retains generation, reranking, generation seed support, retained-lambda
reruns, and lambda-selection orchestration. Shared Gold/manifest formats remain owned by their
existing maintainers. This extension defines evaluation-only adapters and does not modify those
public contracts.

The open-answer 0/1/2 correctness scorer in PR #182 is an upstream dependency. It must be reused
after merge rather than copied into this branch.

## Fail-closed inputs

Formal use requires all of the following to be frozen and hash-bound:

1. three independently authored learner profiles and B1-B4/I1-I3/A1-A4 checklists;
2. an eligibility sidecar tied to the exact Gold hash, calibrated on 15-20 questions with the
   Leader and created without viewing generated answers;
3. an independently configured judge plus any required data-transfer approval;
4. correctness delta, adaptation threshold, lambda epsilon, validity thresholds, primary metric,
   primary contrast, and multiplicity policy;
5. a completed non-overlapping human audit; and
6. a new approved holdout Test set.

Missing decisions are permitted only in development mode and keep `reportable=false`.

## Judge tasks

Every request contains one answer only.

| Task | Visible to judge | Hidden from judge |
|---|---|---|
| Adaptation | question, one answer, one target profile/checklist | condition, lambda, generator, other answers |
| Discrimination | question, one answer, all three profiles | target level, condition, lambda, generator, other answers |
| Evidence support | question, one answer, evidence actually sent, citation IDs | condition, level, lambda, generator, Gold answer |

P0R0 adaptation requests are automatically prepared against all three checklists. A frozen list
of personalised evaluation IDs can also be assessed against all three checklists for the
cross-level validity sample. Pass/fail quotes, claim text, and evidence quotes must be exact
substrings and are rejected otherwise.

The runtime is provider-neutral. It never silently selects or calls a paid judge. The approved
client implements `JudgeProvider`, while `CachedJudgeRunner` validates structured output and
binds the cache to the complete blinded input and judge configuration.

## Commands

Validate frozen input packages:

```text
cs30-v2-generation-eval validate-inputs \
  --profiles artifacts/level-profile-v1.json \
  --eligibility artifacts/personalisation_eligibility_v1.jsonl \
  --gold artifacts/gold_v0_1_2.jsonl \
  --gold-version gold-v0.1.2 \
  --eligibility-version eligibility-v1 \
  --eligibility-calibration-count 15 \
  --calibrated-with-leader \
  --labels-created-without-model-answers \
  --output artifacts/evaluation/input_validation.json
```

Prepare blinded judge requests without calling a model:

```text
cs30-v2-generation-eval prepare-judge-requests \
  --inputs artifacts/evaluation/generation_eval_inputs.jsonl \
  --profiles artifacts/level-profile-v1.json \
  --judge-config artifacts/evaluation/judge_config.json \
  --task adaptation \
  --cross-level-evaluation-ids artifacts/evaluation/cross_level_ids.txt \
  --output artifacts/evaluation/adaptation_requests.jsonl
```

Compute the four fixed condition contrasts:

```text
cs30-v2-generation-eval condition-stats \
  --observations artifacts/evaluation/metric_observations.jsonl \
  --bootstrap-draws 2000 \
  --bootstrap-seed 5703 \
  --output artifacts/evaluation/condition_contrasts.json
```

Prepare disjoint human materials (defaults: 10 calibration and 20 audit cases):

```text
cs30-v2-generation-eval prepare-audit \
  --inputs artifacts/evaluation/generation_eval_inputs.jsonl \
  --output-dir artifacts/evaluation/human_audit
```

The public packets hide condition, lambda, and generator identity. The private key is separate.
Blank packet rows never count as completed human ratings.

## Interpretation rules

- Strict correctness counts only score 2. Technical failures remain in the end-to-end denominator
  as zero. Unresolved judge rows produce bounds, not a point estimate.
- Adaptation, discrimination, correctness, and evidence support are separate dimensions. There is
  no total score.
- FKGL, jargon, length, formulas, and preferred evidence Roles are descriptive diagnostics only.
- Lambda=0 is a control, not a reranking candidate. Two or three positive candidates must be
  predeclared. A positive lambda is recommended only when it passes the relevance and correctness
  gates and improves adaptation; otherwise the report says no improvement.
- All development outputs remain `reportable=false`. The exposed 26-question set is not a clean
  final Test.
