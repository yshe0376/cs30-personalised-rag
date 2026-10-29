# Frozen Test scoring results (2026-10-30)

Scope: GPT-OSS-20B only, 187 questions x 3 levels x 4 conditions = 2,244 cells.
M8 owns evaluation aggregation and this report; M7 may read the bound scores for
integration or verification without generating answers again.

Start with [REPORT.md](REPORT.md). Machine-readable registered findings are in
[registered-test-analysis.json](registered-test-analysis.json). The report retains
missing scores, waived checks, descriptive/reference-only outputs and the native
`reportable=false` flag. No post-Test scoring rule, prompt, threshold or retry
setting was changed, and no extra API call was launched during delivery.

Large artifacts belong to the dedicated Test pre-release:
[v2-m8-test-scoring-20261030](https://github.com/yshe0376/cs30-personalised-rag/releases/tag/v2-m8-test-scoring-20261030).
The scoring archive contains native bound outputs and joined rows; the separate
audit archive preserves originals, requests, caches and attempt ledgers. Archive
digests are in [SHA256SUMS.txt](SHA256SUMS.txt). Publication is artifact availability,
not approval of every research claim. The Dev release is separate and unchanged.

The production scorers and registered analysis already exist on main. This branch
adds only an offline delivery tool, tests, small findings and integrity metadata.
See [delivery instructions](../../evaluation/test-scoring-handoff.md). Do not
upload raw result/cache files into Git.
