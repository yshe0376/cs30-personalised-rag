# Judge attempt accounting and evidence retry preparation

This follow-up implements the two code prerequisites in the
[Leader's post-merge #210 comment](https://github.com/yshe0376/cs30-personalised-rag/pull/210#issuecomment-6446282850).
It performs no paid experiment. The Leader waived another six-request paid confirmation;
full Dev still requires review/merge of these changes and sufficient billing balance.

## Per-attempt ledger

`CachedJudgeRunner` now appends a JSONL record immediately after every provider attempt,
including failed local validation and exhausted requests. A later success does not erase
earlier usage. `StructuredJsonJudgeProvider` also preserves returned usage when JSON decoding,
JSON-object shape checks or output truncation reject a response before ordinary validation.
Gemini empty-content and safety-blocked returns retain their response identity and any
returned usage through an Evaluation-owned `LLMEmptyResponseError` subclass. They remain
invalid outputs: retries can recover, but exhausted requests stay unresolved without a score.

The CLI writes `RESULT_STEM.attempts.jsonl` beside its result output by default. For example,
`--output results.jsonl` produces `results.attempts.jsonl`. `--attempt-log PATH` selects an
explicit append-only ledger such as `calls.jsonl`. Direct runner callers default to a ledger
beside their success cache, using `CACHE_STEM.attempts.jsonl`.

Each record includes:

| Fields | Meaning |
| --- | --- |
| `schema_version`, `attempt_id` | Versioned log row and unique attempt identity |
| `judge_execution_id`, `task`, `request_id`, `cache_key`, `config_sha256` | Join to the execution, request and exact configuration |
| `provider`, `model_revision`, `reported_model` | Configured and returned model provenance |
| `attempt` | One-based application attempt within this runner invocation |
| `started_at_utc`, `completed_at_utc`, `provider_response_id` | Attempt timing and optional provider identifier |
| `status`, `error` | `accepted`, `invalid_output` or `provider_error`, with the local failure reason |
| `usage_available` | Whether a provider response supplied usage metadata |
| `input_tokens`, `output_tokens`, `thought_tokens` | Returned per-attempt counters, or JSON null when usage is unavailable |

Unknown usage is **not** recorded as a measured zero. A transport error without a response
cannot supply exact usage. Legacy mapping-only fixture providers likewise lack counters.
Gemini responses without `usage_metadata` also produce null ledger counters, including
otherwise valid, empty, malformed and truncated responses. Numeric zero placeholders inside
the shared response/envelope types do not imply measured zero usage.
For Gemini, output tokens already include thinking; never add thought tokens a second time.
Internal SDK HTTP retries are not separately observable here: one ledger row is one provider
invocation/application attempt, not a claim to instrument every underlying HTTP request.

The log is opened before provider execution. An unwritable log prevents execution; an append
failure after a response propagates and stops before another retry. Log paths cannot alias
the cache, and the CLI also rejects aliases to request/config/result files. The ledger stores
metadata and error text, rather than separate prompt, answer or raw-output fields; validator
errors can include excerpts of the rejected output.

## Result totals, cache and resumption

New result envelopes retain their existing field names/types. Their token counters now sum
all **known** attempts in that `run` invocation, for accepted and unresolved outcomes. If an
attempt's usage is unavailable, these totals are partial; inspect `usage_available` in the
ledger and use the provider bill for actual spending. Response identity/model fields still
describe the last returned response, rather than an invented aggregate response.

Cache reuse makes no provider call and adds no ledger row. A cached envelope's stored usage
describes its original execution, not a new charge. For spending totals, aggregate the ledger
for the intended `judge_execution_id` and task; do not add repeated cached envelopes. If a
request is attempted again after interruption, its new unique attempt IDs distinguish the
new records even when the request/within-invocation attempt number repeats. Earlier ledger
entries remain. Old records with missing usage are not retroactively repaired or estimated.

The ledger covers adaptation, discrimination and evidence-support execution through
`CachedJudgeRunner`. The follow-up also gives the separate correctness scorer the same
immediate, per-attempt accounting. Shared generation/provider contracts, frozen profiles,
Gold and historical trial artifacts are unchanged.

## Correctness accounting and result metadata

`OpenAnswerScorer` captures usage before parsing or checking content. It also extracts
metadata from `GeminiJudgeEmptyResponseError`; empty/blocked output remains rejected.
Exhausted attempts still produce `judge_error` with no correctness score. Missing metadata
and invalid counters produce null counters with `usage_available: false`; a real measured
zero remains zero with `usage_available: true`. Thinking is already part of output tokens.
This does not route rule-based scoring to an API. Complete aliases and supported numerical
rules still return before the client path; semantic judging uses a client only when supplied.
Without a client, non-rule answers remain `needs_review`. A rubric supplies the assessment
criteria; it is not itself a semantic execution engine.

The correctness CLI writes `OUTPUT_DIR.attempts.jsonl` **beside** the immutable report
directory, so the six existing report files and their creation rule are preserved.
`--attempt-log PATH` overrides it. Log paths cannot alias inputs, enter the report directory,
or enter the success-cache directory. An unwritable log prevents execution; an append
failure stops before another provider call. Direct Python callers can supply
`OpenAnswerScorer(..., attempt_log_path=...)`; otherwise they receive attempt history in the
returned scores, but no live sidecar ledger. Log/execution IDs do not enter judge configuration
hashes or change cache identities.

Each new correctness attempt has a persistent `attempt_id` and optional response ID in both
the ledger and the saved score. A cached score retains its historical attempts and IDs, has
`judge_calls_this_run: 0`, and writes no new ledger row. Historical attempts are never relabelled
as new spending. Legacy caches still load; their old zero fields remain historically ambiguous.

Both `JudgeResultEnvelope` and `OpenAnswerScore` add:

| Field | New results | Historical records without the field |
| --- | --- | --- |
| `attempt_count` | Attempts represented by the result's history/totals, including rejected outputs | null; not inferred from old envelope totals |
| `usage_complete` | true only when every represented attempt has known usage | null on old envelopes; false on newly emitted correctness results using unknown legacy history |

Rule-only or otherwise unjudged new correctness results have zero attempts and complete
zero-call accounting. A cached result's count describes its original history, not fresh calls.
These are Evaluation-owned result extensions: old data remains readable by the updated
models, but older strict readers need updating to accept the new fields and nullable
correctness counters. Online judge output schemas, request hashes, scoring criteria and
score calculations are unchanged. Do not use this metadata as evidence of judging accuracy.

## Offline running cost estimate

`scripts/judge_spending.py` reads the explicitly selected ledgers and/or new correctness
score JSONL files. It never constructs a provider, reads a key, changes billing or runs scoring.
One consistent model's verified input/output prices and an explicit AUD-per-USD rate are
required. Different configured models are rejected rather than priced at one guessed rate.

The script unions records by `attempt_id`, so selecting a ledger twice, copying it, or
selecting both its correctness results and ledger does not charge the same attempt twice.
Distinct attempt IDs remain distinct even if provider response IDs match. Conflicting copies,
malformed files and legacy attempts without reliable IDs fail rather than silently undercount.
Cached correctness rows are skipped; their original execution's ledger is the source if it
belongs to the monitored run. Three-task result envelopes are not an extra spending source.
An incomplete final log row asks the operator to take another snapshot; it is not ignored.

Only select files belonging to the approved full-Dev budget period, including its repeat,
validity and repair executions. Earlier trials and Test must remain outside this file set.
The input/output rates below are the original trial parameters, not a live price lookup;
verify current rates before using them for an authorised run. The FX rate is operator-supplied.

```powershell
$runRoot = "..\W8\full-dev" # Replace with the actual full-Dev execution folder.
$logs = @(Get-ChildItem -LiteralPath $runRoot -Recurse -File -Filter "*.attempts.jsonl" |
    Select-Object -ExpandProperty FullName)
if ($logs.Count -eq 0) { throw "No attempt ledgers found in the selected execution folder" }
$usdToAud = Read-Host "Enter the planning exchange rate: AUD per USD"
.\.venv\Scripts\python.exe scripts\judge_spending.py --attempt-log $logs --model gemini-3.1-flash-lite --input-usd-per-million 0.25 --output-usd-per-million 1.5 --usd-to-aud $usdToAud --input-multiplier 1.15
```

`--correctness-results PATH [PATH ...]` can supplement or replace correctness ledgers with
new score files. `--actual-spend-aud AMOUNT` optionally supplies observed spending attributable
to **this full-Dev run**, rather than account balance or all historical account spending.

The default input multiplier is 1. The example explicitly buffers **input** by 15%, following
the observation recorded in #213; it is a planning allowance, not a universal billing rule.
Output includes thinking already and receives no extra thinking charge. The JSON report shows
known list-price USD, buffered AUD estimate, unknown-attempt count and every supplied rate.
Any unknown attempt makes the total incomplete; it cannot establish that spending is below budget.

At/above AUD 45 the action is `PAUSE_AND_REPORT`; at/above AUD 60 it is `STOP_CAP`. The larger
of the estimate and supplied actual spend is used for those signals. Below both thresholds,
unknown usage returns `VERIFY_UNKNOWN_USAGE`, otherwise `BELOW_PAUSE_ESTIMATE`. Attention
states return exit code 3; invalid input returns 2. This read-only helper does **not** terminate
another process or guarantee a spending cap. Actual billing, tax, unavailable usage, SDK-internal
HTTP attempts and currency differences can diverge from the estimate. The operator still pauses
the scoring process and follows the Leader's actual-bill limits.

## Evidence-support output and retry rule

The prompt now explicitly requires:

- supporting IDs only when quotations for those IDs are supplied;
- at least one quote row for every listed supporting ID;
- the already accepted three-word, ordered, nonoverlapping fragment rule within each row;
- citation support only when a quoted supporting ID is also an actual answer citation.

Both the CLI and direct runner reject fewer than two evidence-support application attempts.
The default remains two: the initial attempt plus one possible repair. A valid first response
stops immediately; retries are permitted, not automatically spent. SDK network retries remain
a separate unchanged setting. Invalid outputs after the limit remain unresolved; no verdict,
evidence ID or quotation is rewritten to make an output pass.

The prompt text is part of the existing request hash, so the new prompt produces new evidence
request/cache identities. Regenerate evidence-support requests from the original inputs before
a future authorised run. Do not relabel an old request/output as using the new prompt. Use
fresh full-Dev output/cache/ledger paths and the approved low configuration.

## Offline verification

`tests/test_judge_attempt_usage.py` uses local stand-ins; its Gemini adapter receives an
injected SDK stand-in rather than constructing a network client. The two required scenarios
return input counters 100 and 80 and check a total of 180:

1. first output rejected, second output accepted;
2. both outputs rejected, request unresolved.

The tests also cover returned usage on malformed/truncated responses, unknown transport-error
usage, immediate log persistence before a retry, cache reuse without duplicated attempts,
log write failure, evidence retry preflight and CLI default ledger creation. Running these
tests does not use a paid or free-tier API, and needs no API key. End-to-end adapter/provider/
runner tests additionally cover empty and safety-blocked returns followed by success or
exhausted retries, and missing metadata in valid/empty/malformed/truncated returns.

Follow-up verification on 2026-10-28: **250 related tests passed** (including correctness,
Gemini adapters, cache compatibility and spending signals); full offline regression
**1,393 passed, 2 skipped**; Ruff and diff whitespace checks passed. All tests use local
stand-ins. Correctness rule-based routing and scores are explicitly covered without an API.

```powershell
python -m pytest -o addopts='' -q -p no:cacheprovider tests/test_judge_attempt_usage.py tests/test_correctness_attempt_usage.py tests/test_judge_spending.py
```

## Full-Dev gate

The budget decision in [#213](https://github.com/yshe0376/cs30-personalised-rag/pull/213) is
AUD 60 maximum on actual provider spending, with a pause/report threshold of AUD 45 if the
run is unfinished. It excludes Test. These code changes do not charge the account, top it
up, read the live AI Studio bill or authorise starting the run automatically. The Leader
accepted the original prerequisites in #215, which is merged. This additional follow-up is
prepared separately for review; its optional metadata/estimator work must not be presented as
a new Leader-imposed gate. Before using this follow-up for full Dev, review/merge its changes,
prepare billing balance and retain the Leader's actual-spending controls.
