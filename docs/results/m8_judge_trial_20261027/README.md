# Paid Dev judge trial — 2026-10-27

This package publishes the completed 20-cell trial requested in #209. It contains the actual reports and saved judgments so the Leader can review the findings. This is development evidence, not a formal evaluation or a completed human audit. Full Dev scoring has not started and requires separate budget approval.

## Read first

| File | What to inspect |
| --- | --- |
| [report.md](report.md) | Original generated per-task token, retry, cost and projection tables |
| [analysis.md](analysis.md) | Semantic disagreements, validation failures and recommended follow-up |
| [summary.json](summary.json) | Machine-readable aggregate counts and costs |
| [calls.csv](calls.csv), [calls.jsonl](calls.jsonl) | 204 logged judge-client attempts with tokens, timing and calculated cost |
| [selection.json](selection.json) | Exact fixed selection: 20 cells, 19 distinct questions |
| [spotcheck.md](spotcheck.md) | Answer and judgment previews; some JSON is truncated by the original trial script |
| [thinking-high/](thinking-high/), [thinking-low/](thinking-low/) | Full requests, final results, success caches, correctness scores/review queues, configs and manifests |
| [subset/](subset/) | Selected per-generator inputs, answers and expected matrices |
| [manifest.json](manifest.json) | Source provenance and SHA-256 hashes for every packaged file |

## Findings and limits

- Estimated token spend: high US$0.3641535, low US$0.12593075, total US$0.49008425; low was 65.4% cheaper. Provider invoice reconciliation is pending.
- Base full-Dev projection: high US$70.54 / low US$24.16. Additional judge validity repeats/order checks, another judge family, future repair/re-run costs, taxes and currency conversion are excluded.
- Wrapper-level API exceptions: zero; recorded truncations: zero. This does not mean every output was valid.
- High correctness: 19 scored and 1 needs_review; low: 20 scored. The 19 mutually scored cells agree on scores.
- Adaptation: 30 resolved outputs per setting; 23 of 111 criterion verdicts differ. Discrimination predictions differ on 5 of 20 requests. These are descriptive configuration differences, not accuracy or independent human-agreement estimates.
- Evidence support: 3/20 high and 5/20 low outputs remain unresolved. Exact quotation, evidence-ID duplication and ID/quotation coverage validation caused rejections. High has 12 and low 8 extra application attempts for this task.
- Low is a cheaper candidate for further validation; it is not established as an equally reliable replacement. A human spot-check and failure investigation remain pending.

## Important reading corrections

The copied raw runtime outputs are preserved byte-for-byte. In particular, report.md says every API call including retries is logged. More precisely, calls.csv logs each judge-client invocation and application retry; internal SDK HTTP retries are not separately instrumented. The SDK can retry 408/429/5xx responses. Costs are computed from returned usage at US$0.25/M input and US$1.50/M output including thinking, not taken from an invoice. Raw records may contain local paths that describe the original execution environment.

The raw spotcheck.md previews truncate judgment JSON; use the full task result files to investigate. Raw counts labelled API errors describe exceptions at the wrapper, while unresolved describes output/validation or review outcomes. Unresolved judge outputs are not incorrect generator answers.

## Provenance and coverage

- Runtime source: 7068dae27e44c4ad316e4ce3bed7cb64dd2daf2a; its file tree matched merged #209 commit 0bc96aa5e087b58f673719c8b7041f35a5ff96c0 before the trial.
- Generator handoff: [v2-m7-api-dev-20261026](https://github.com/yshe0376/cs30-personalised-rag/releases/tag/v2-m7-api-dev-20261026), archive SHA-256 4020a9a984f759cf1948d1cd9140cf66aab4679b7f3c04a65ab4e41f686ba7ee.
- Gemini model: gemini-3.1-flash-lite; temperature 1.0; high and low used the identical saved selection.
- Generators GPT-OSS/Llama/Gemma: 7/7/6. Target levels beginner/intermediate/advanced: 8/5/7. Conditions P0R0/P1R0/P0R1/P1R1: 5/5/4/6.
- Eligibility: endpoint_only 18 and full 2; none-scope cases were excluded. Labels remain drafts, so adaptation results remain provisional. The two full questions have documented reference concerns.
- The frozen profiles use the Leader's independent physics-review waiver; this package does not claim independent physics approval.
- Full-Dev task request counts are 3,611 correctness, 5,485 adaptation, 3,611 discrimination and 4,169 evidence support, as computed by the original trial script after task-specific applicability and de-duplication. The 20-cell sample does not establish projection precision for the full workload.

The original script and local study notes remain outside the repository under W8. The bulk handoff package and full-Dev projection intermediates are not duplicated here. No new API calls were made to prepare this publication.


## Later supplements

Leader decision #212 now selects thinking low for all four tasks; high remains historical
comparison evidence. Full Dev still awaits budget approval. The sampling and budget script
is now versioned at [scripts/judge_trial.py](../../../scripts/judge_trial.py).

- [Provider AUD billing observation](billing_observation.md): user-reported AUD 0.69 project
  spending, rounded provider token charts and explicit reconciliation limits. Original USD
  estimates and trial files are unchanged.
- [Fresh six-request low evidence confirmation](../m8_low_evidence_confirmation_20261028/README.md):
  separate user-executed diagnostic run after quotation repair; three accepted and three
  unresolved, with incomplete saved usage on failed outputs. Not another full trial.
