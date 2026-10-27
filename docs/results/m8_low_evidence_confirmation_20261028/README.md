# Fresh six-request low evidence confirmation

Start with [report.md](report.md). The user executed this paid check after the evidence-quotation
repair: **3 accepted by validation, 3 unresolved**. Both current validators reproduce the saved
statuses offline. This is separate from the first 20-cell trial and from the later adaptation
applicability guard. No new API call was made to publish the package.

## Scope and selection

Five previously affected evidence contexts plus one previously valid Llama control were
selected explicitly with user confirmation. This is a diagnostic set, not a random or
population-representative sample. GPT-OSS: 2, Gemma: 3, Llama: 1; target levels: two each;
conditions: P1R1 combined 3, P1R0 prompt-only 2, P0R1 reranking-only 1. P0R0 is absent.
All six question/answer/evidence/citation payloads match their original trial requests exactly.
Only evidence_support ran, with low thinking, temperature 1.0 and one application attempt.

## Files

| File | Purpose |
| --- | --- |
| [requests.jsonl](requests.jsonl) | Exact six blinded request payloads used in the fresh run |
| [selected_inputs.jsonl](selected_inputs.jsonl) | Exact selected inputs, including generator/level/condition identities |
| [judge-config.json](judge-config.json) | Exact low Gemini configuration |
| [case_map.csv](case_map.csv) | Fixed question-to-request map and selection purpose |
| [results.jsonl](results.jsonl) | All six original result envelopes, including unresolved raw outputs |
| [fresh-cache.jsonl](fresh-cache.jsonl) | Three original successful cache entries |
| [summary.json](summary.json) | Machine-readable outcome, offline checks and usage limitations |
| [case_results.csv](case_results.csv) | Concise per-case status/usage table |
| [provenance.json](provenance.json) | Preparation/source hashes; local absolute module path omitted |
| [RUN_COMMAND.txt](RUN_COMMAND.txt) | Historical settings and a portable paid command, not executed here |
| [SHA256SUMS.json](SHA256SUMS.json) | SHA-256 of every other file in this package |

Raw input/config/result/cache files are byte-preserving copies, protected by the local
`.gitattributes`. The private preparation README/status predates execution; the completed
report above supersedes that preparation status. Original 20-cell artifacts are untouched.
No screenshot, billing-account URL, credential or private review draft is included.

## Reproducible inspection

Preparation source commit:
[`96626a7f3bd03cd08cc09c970511f94eb2138244`](https://github.com/yshe0376/cs30-personalised-rag/commit/96626a7f3bd03cd08cc09c970511f94eb2138244).
The current offline check used source commit `ceeb7e479d84fef4230ca0d4a98a53342c3a3142`.
The existing code paths are
[`build_evidence_support_request`](../../../src/cs30/evaluation/evidence_support.py),
[`validate_output_against_request` / `CachedJudgeRunner.run`](../../../src/cs30/evaluation/judge_runtime.py),
[`validate_evidence_support_output`](../../../src/cs30/evaluation/evidence_support.py), and
the [`run-judge-requests` CLI](../../../src/cs30/evaluation/v2_generation_cli.py).
Each result's request_id joins to requests.jsonl and case_map.csv. The selected input and
configuration rebuild the same request hash. Inspect the saved outputs with these validators;
that needs no provider. The preserved results allow exact inspection; a new stochastic paid
run is a separate experiment and cannot promise identical outputs.

For an offline check, paste the following from the repository-root PowerShell. It reads
saved files and calls only validation functions; it does not construct an API client:

```powershell
@'
import csv, json
from pathlib import Path
from collections import Counter
from cs30.evaluation.judge_runtime import validate_output_against_request
from cs30.evaluation.evidence_support import validate_evidence_support_output
from cs30.evaluation.v2_generation_models import JudgeRequest, GenerationEvaluationInput
p = Path("docs/results/m8_low_evidence_confirmation_20261028")
def rows(name):
    return [json.loads(s) for s in (p / name).read_text(encoding="utf-8").splitlines() if s]
requests = {r["request_id"]: JudgeRequest.model_validate(r) for r in rows("requests.jsonl")}
items = {r["question_id"]: GenerationEvaluationInput.model_validate(r) for r in rows("selected_inputs.jsonl")}
with (p / "case_map.csv").open(encoding="utf-8", newline="") as f:
    cases = {r["request_id"]: r["question_id"] for r in csv.DictReader(f)}
counts = Counter()
for r in rows("results.jsonl"):
    request = requests[r["request_id"]]
    raw = r["raw_output"] if r["unresolved"] else r["output"]
    errors = []
    for check in (
        lambda: validate_output_against_request(raw, request),
        lambda: validate_evidence_support_output(raw, request=request, item=items[cases[r["request_id"]]]),
    ):
        try:
            check()
        except ValueError as exc:
            errors.append(str(exc))
    assert len(errors) in (0, 2) and bool(errors) == r["unresolved"]
    status = "unresolved" if errors else "accepted"
    counts[status] += 1
    print(cases[r["request_id"]], status, errors)
assert counts == {"accepted": 3, "unresolved": 3}
print("No API calls. Saved statuses reproduced:", dict(counts))
'@ | python -
```

The runner did not retain provider usage on the three unresolved envelopes. Consequently,
USD 0.00458675 covers only recorded successful usage and is a lower bound, not the six-call
total. See the report before using these cost fields. Original-trial AUD observations are
documented separately in [billing_observation.md](../m8_judge_trial_20261027/billing_observation.md).

Full Dev is on hold until budget approval. This package makes no claim of completed human
calibration or semantic accuracy, and it does not authorise another paid call.
