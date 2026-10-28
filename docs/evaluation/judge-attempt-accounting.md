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
`CachedJudgeRunner`. Correctness retains its separate scorer/attempt-recording path; shared
generation/provider contracts, frozen profiles, Gold and historical trial artifacts are unchanged.

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

Verification on 2026-10-28: **130 related tests passed** (including Gemini adapter tests);
full offline regression **1,341 passed, 2 skipped**; Ruff and diff whitespace checks passed.

```powershell
python -m pytest -o addopts='' -q -p no:cacheprovider tests/test_judge_attempt_usage.py
```

## Full-Dev gate

The budget decision in [#213](https://github.com/yshe0376/cs30-personalised-rag/pull/213) is
AUD 60 maximum on actual provider spending, with a pause/report threshold of AUD 45 if the
run is unfinished. It excludes Test. These code changes do not charge the account, top it
up, monitor the live AI Studio bill or authorise starting the run automatically. Before the
user starts full Dev: this follow-up must be reviewed/merged, billing balance must be ready,
and the execution/monitoring plan must retain the Leader's spending controls.
