# Full Dev low thinking scoring run

All 24 base jobs finished on 29 October 2026. This package archives the original
execution and a separate offline v2 revalidation. It is a **development review
package**, not completed judge validation, a repaired final score release or Test.
No model call or paid retry was made while preparing this package.

## What is included

- `original/results/`: all six correctness report directories and all 18 structured
  judge result files, copied byte for byte from the operator's original run.
- `original/ledgers/`: all 24 per-attempt logs, including rejected and failed attempts.
- `original/run-plan.json` and `judge-config.low.json`: the actual recorded plan and configuration.
- `run_index.json`: portable relative paths for each of the 24 jobs.
- `revalidation-v2/`: counts and per-record diagnostics from the verified default
  offline replay, including the prepared-cache coverage proof. These do not replace
  any original score. Prepared caches and executable paid commands remain local.
- `SHA256SUMS.json`: SHA-256 of every copied source artifact. The local W8 originals
  remain untouched. `.gitattributes` prevents Git newline conversion of these bytes.

The copied original manifests and plan retain historical machine paths for audit.
Use `run_index.json` to locate the archived files; do not treat historical paths as
portable execution instructions. Original caches remain with the operator. Source
generation inputs come from the verified upstream package below rather than being
duplicated here.

## Scope and source

The six batches are three generators (GPT-OSS, Llama, Gemma), each with Dev and
generation-repeat answers. Each batch receives correctness, adaptation,
discrimination and evidence-support scoring. Thinking is low throughout.

Execution code: `2b565b8ad4b0181ba27bda7a287700db24d5a36e`.
Frozen profile package: `1888c3b7fb6f2f0fd52dbe06455c40cef88ff8839ab47383a76d7c29a1088238`.
Upstream [generation handoff](../m7_api_dev_20261026/README.md) and
[release](https://github.com/yshe0376/cs30-personalised-rag/releases/tag/v2-m7-api-dev-20261026).
Its archive SHA-256 is `4020a9a984f759cf1948d1cd9140cf66aab4679b7f3c04a65ab4e41f686ba7ee`.

Run IDs can repeat across batches. Always retain the source-run, answer, Gold and
rubric bindings; do not flatten or join this archive only on `run_id`.

## Original outcomes

| Task | Unit | Total | Unresolved after execution |
| --- | --- | ---: | ---: |
| Correctness | result rows | 6624 | 76 judge errors and 12 review requests |
| Adaptation | unique requests | 5485 | 107 |
| Discrimination | unique requests | 3611 | 8 |
| Evidence support | unique requests | 4169 | 230 |

Correctness has 6,536 scored rows, including the original generation failures
assigned system scores under the existing contract. The upstream 84 generation
failures were not erased or regenerated. Unresolved judge scores remain null.
Different task units must not be combined into one failure-rate denominator.

## Verified offline v2 replay

| Task | Original failure entries | Recovered from saved attempts | Covered by existing cache | Still unresolved entries | Accepted now invalid | Unique retry requests |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Correctness | 76 | 32 | 8 | 36 | 0 | 32 |
| Adaptation | 107 | 21 | 0 | 86 | 0 | 86 |
| Discrimination | 8 | 5 | 0 | 3 | 0 | 3 |
| Evidence support | 230 | 29 | 0 | 201 | 7 | 208 |
| Total audit entries | 421 | 87 | 8 | 326 | 7 | 329 |

Rows and unique requests are explicitly distinct. Correctness uses the first valid
saved attempt for an otherwise uncached key, reuses an existing valid success cache
when available, and keeps already accepted assessments unchanged. Evidence has seven
previously accepted contradictions (unsupported claims listing supporting IDs) that
must be handled explicitly. A revalidation pass establishes schema/quotation
validity, not factual judge accuracy or permission to spend.

## Cost observations

The original 19,303 logged attempts include 19,301 known usage records and two
disconnects with unknown usage. Known input is 44,569,716 tokens; output including
thinking is 9,364,780, of which thinking is 3,450,593. Do not charge thinking twice.
At the recorded list prices the known cost is **USD 25.189599**. The input-only 1.15
allowance and planning 1.50 AUD/USD factor produce **AUD 40.291445025**, an estimate.

The operator supplied a project month-to-date display of **AUD 36.52**, including
earlier activity. It is not a confirmed full-Dev-only invoice. Subtracting the earlier
AUD 0.69 trial would give AUD 35.83 only if there was no other billable activity.
Billing delays, tax and unknown usage require reconciliation with the final provider
bill. No account identifiers, payment images or API keys are included.

The existing actual-spend control remains **AUD 45 pause/report and AUD 60 cap**.
The proposed small retry budget is not approved or automatically enforced here.
An average-cost estimate is not a guaranteed maximum.

## Remaining work before final handoff

Review and merge the validation change; authorise any targeted paid retry separately;
retain its new result/cache/ledger provenance. Then build correctness bindings and
assemble all four dimensions with the existing evaluation tools. Judge repeat and
order-reversed validity checks and the final development report remain outstanding;
profile/eligibility limits remain explicit. Test is outside this run.

## 中文核对说明

这里已经归档 24 项原始结果和全部调用日志，原文件逐字节保留；另列新规则下的离线
检查结果。87 条从保存输出恢复、8 条由已有成功缓存覆盖，仍需补跑的独立请求为 329。
没有启动补跑，也没有把这份原始记录归档冒充修复后的最终交接包。费用显示、估算与
最终账单口径分开记录。实际支出仍受组长批准的 AU$45 暂停线和 AU$60 上限约束。

## Local verification before publication

The patched source passed Ruff and **1,432 tests, with 2 skips**; the 39 new tests
are included in that total. The default offline replay completed against the real
24-job inputs. A separate count of actual prepared-cache misses also gives 329.
No API call was made. See `verification.json` for the tested patch identity.
