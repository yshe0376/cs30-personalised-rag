# Supplemental real-API retry usage check

This synthetic connectivity check supplements the automated usage tests in the follow-up
to [#210](https://github.com/yshe0376/cs30-personalised-rag/pull/210#issuecomment-6446282850).
The user executed it using an operator-confirmed Free Tier project. It is not a Dev scoring
run, an evidence-judgment quality test, a cost forecast or a new six-request trial.

## Scenario and result

The shared production Gemini adapter/provider/runner received **three real responses**.
After ordinary output validation passed, the private probe deliberately rejected the first
two locally. The third was accepted normally. These are controlled local validation failures,
not model reasoning errors or failed authentication/server requests. No token counter was
fabricated or rewritten. There was no assistant-initiated model call during publication.

| Attempt | Outcome | Input | Output including thinking | Thinking subset | Total |
| --- | --- | ---: | ---: | ---: | ---: |
| 1 | Intentionally rejected locally | 103 | 190 | 130 | 293 |
| 2 | Intentionally rejected locally | 229 | 195 | 122 | 424 |
| 3 | Accepted | 229 | 167 | 107 | 396 |
| **Sum** | | **561** | **552** | **359** | **1,113** |

The first two rejected responses account for **717 tokens**, all retained in the total.
Raw SDK output counts are visible candidates 60/73/60 plus thoughts 130/122/107; the adapter
correctly maps output to 190/195/167. Thinking is already included and must not be added twice.
Every SDK-to-ledger comparison passed, and the result envelope matches the all-attempt sum.

`metadata_matches_ledger_and_result`, `retry_scenario_passed` and `output_valid` are true;
`error` is null. The automated tests separately cover requests still unresolved after the
retry limit, including their complete returned usage. No additional real run is needed to
read or audit these saved measurements.

## Fixed scope and limits

- Production source commit: `8bab9a773e6d854fa05cd62cc07e403f31964295`.
- Probe source digest is recorded in [provenance.json](provenance.json); the exact clean
  driver snapshot is [probe_source.py.txt](probe_source.py.txt), not an annotated study copy.
- Model `gemini-3.1-flash-lite`, thinking low, temperature 1.0; fixed fictional cube input.
- Three application/provider attempts maximum, one SDK HTTP attempt per invocation,
  1,024 output tokens maximum per invocation, 45-second timeout per invocation.
- Returned timestamps: 2026-10-28 00:24:09–00:24:20 UTC / 11:24:09–11:24:20 Sydney (AEDT).
- Only the dedicated `API_FREE_KEY` variable was used; its value is not recorded. Project
  billing eligibility was confirmed by the operator, not inferred by the probe from the key.
- No Gold, frozen profiles, real Dev answers or previous trial payloads were sent. A simple
  discrimination schema served only as a structured connectivity fixture for the shared
  runner. Production evidence-support retry rules were not relaxed.

## Files and reproducible offline inspection

- [raw_usage_by_attempt.jsonl](raw_usage_by_attempt.jsonl): all three original SDK metadata records.
- [calls.jsonl](calls.jsonl): all three production attempt ledger rows, including the two rejections.
- [result.json](result.json): accepted result and aggregate usage.
- [summary.json](summary.json): per-attempt comparisons, limits and observed outcomes.
- [forced_rejections.json](forced_rejections.json): labels the deliberately rejected attempts.
- [request.json](request.json), [configuration.json](configuration.json): exact fictional inputs/settings.
- [cache.jsonl](cache.jsonl): the final successful cached envelope only.
- [raw_usage.json](raw_usage.json): convenience snapshot of the **last response only**, not the total.
- [SHA256SUMS.json](SHA256SUMS.json): all other package-file hashes.

All copied raw files are byte-preserving, protected by the local `.gitattributes`. Verify
the counts without a key or network from the repository-root PowerShell:

```powershell
@'
import json
from pathlib import Path
p = Path("docs/results/judge_attempt_usage_probe_20261028")
def rows(name):
    return [json.loads(s) for s in (p / name).read_text(encoding="utf-8").splitlines() if s]
raw = {r["attempt"]: r for r in rows("raw_usage_by_attempt.jsonl")}
calls = rows("calls.jsonl")
result = json.loads((p / "result.json").read_text(encoding="utf-8"))
assert len(calls) == len(raw) == 3
for r in calls:
    sdk = raw[r["attempt"]]
    assert r["input_tokens"] == sdk["prompt_token_count"]
    assert r["output_tokens"] == sdk["candidates_token_count"] + sdk["thoughts_token_count"]
    assert r["thought_tokens"] == sdk["thoughts_token_count"]
for field in ("input_tokens", "output_tokens", "thought_tokens"):
    assert result[field] == sum(r[field] for r in calls)
assert [r["status"] for r in calls] == ["invalid_output", "invalid_output", "accepted"]
print("Offline check passed: all three attempts retained; total", result["input_tokens"] + result["output_tokens"])
'@ | python -
```

The source snapshot is archival. Running it with no online switch uses local stand-ins.
Do not invoke its online mode merely to inspect this package; any new call is a separate
operator-initiated experiment. This evidence does not authorise full Dev: the follow-up
still needs review/merge and billing preparation under #213's AUD 60 cap / AUD 45 pause rule.
