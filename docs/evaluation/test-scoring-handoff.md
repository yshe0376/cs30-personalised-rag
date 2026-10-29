# Completed Test scoring delivery

This delivery follows the frozen reporting decisions in PRs #224–#226. M8 owns
the score-to-answer aggregation and evaluation report. M7 supplies generation
artifacts and may consume the bound scores for integration or verification;
M7 does not take over the scoring report and does not need to regenerate answers.

## Existing implementation and the remaining delivery layer

| Responsibility | Existing implementation |
|---|---|
| Read M7 generation artifacts and retain identities | `v2_generation_artifacts.py`, `adapt-m7-artifacts` |
| Validate correctness against run, answer, Gold and rubric hashes | `load_open_answer_scores` |
| Reassemble saved adaptation, discrimination and evidence judgments | `judge_results.assemble_judge_results` |
| Apply the registered main adaptation policy, paired bootstrap and Holm family | `test_gate_analysis.py` |
| Validate frozen Test inputs and produce source-bound analysis | `test_gate_readiness report` |
| Copy completed artifacts, export portable JSONL, package and verify | `scripts/build_test_scoring_handoff.py` |

The delivery script calls these existing readers and analysis functions. It adds
no generation path, provider request, retry, score override, new threshold or
statistical method. Intermediate I3 and discrimination/citation support stay
reference-only. Unknown scores remain null; generation failures retain the
already-approved system zero. The native `reportable=false` flag is preserved.

Literal Unicode line separators inside valid JSON strings are legal JSONL, but
the existing assembled-output reader uses `str.splitlines()`. The delivery layer
therefore creates a separate ASCII-escaped JSONL export and updates only its file
digests. It checks exact equality of decoded objects, preserves raw originals,
and verifies canonical reassembly with the existing validators. This is an I/O
compatibility measure, not a change to accepted judge outputs or quote matching.

## Reproduce offline

Use the repository environment, with `PYTHONPATH` pointing to this checkout's
`src`. Building requires the original completed run directory. The output
directory must not already exist.

```powershell
$env:PYTHONPATH = "$PWD\src"
python scripts/build_test_scoring_handoff.py build --run-root <completed-Test-run> --out <new-output-directory> --repo .
```

The two archives have separate purposes:

- `m8-test-scoring-handoff-20261030.tar.gz`: native bound scores, 2,244 joined
  convenience rows, frozen configuration, registered analysis and report.
- `m8-test-scoring-audit-20261030.tar.gz`: byte-identical originals, source
  generation package, request inputs, caches, per-attempt ledgers and receipts.
  Original absolute paths describe the execution machine. They are audit data,
  not instructions to execute paid jobs on a different machine.

After checking the archive digest and extracting the scoring archive:

```powershell
python scripts/build_test_scoring_handoff.py verify --package <extracted-scoring-directory> --repo .
```

Verification rejects missing, changed or extra files; checks native correctness
bindings; reassembles the saved judge envelopes; compares every joined row; and
replays the registered analysis. No provider is constructed. The CLI blocks
network connections during build and verification. Use the bundled copy under
`tools/` with `--repo` if the delivery PR has not yet merged.

## Repository and Release boundaries

Keep only the tool, fictional tests, small report, machine-readable aggregate
analysis, verification metadata and checksums in Git. Put both large archives in
a dedicated **Test pre-release**, separate from the Dev release. The Release
description must identify which archive to read, exact digests, approved scope,
missingness, costs as estimates, and limitations. Publication makes artifacts
available; it does not certify all research claims or change `reportable`.

No post-Test rule tuning or selective paid retries are part of this delivery.
Any future correction would require a separately disclosed, versioned decision
and must preserve the original Test run and its findings.
