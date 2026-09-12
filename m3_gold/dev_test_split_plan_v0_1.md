# M3 Dev/Test Split Plan v0.1

## Scope

This plan applies to `m3_gold/gold_v0_1.jsonl`, the current 20-record M3 Gold
v0.1 set produced from `standardized/test.jsonl`.

These split labels are proposed only. They should not be treated as the frozen
formal evaluation split until the formal Gold set is expanded and reviewed.

## Deterministic Rule

Use OpenStax `chapter_id` as the isolation key.

- `chapter_id <= 16`: `proposed_dev`
- `chapter_id >= 17`: `proposed_test`
- Random seed: none, because no random assignment is used.

This keeps all records from the same OpenStax chapter on the same side of the
split and avoids random leakage across near-duplicate chapter concepts. Generic
section labels such as glossary, section summary, and problems/exercises are
not used as standalone concept groups; they are specialized by topic.

## Current v0.1 Distribution

Current record count: 20.

- `proposed_dev`: 12 records
- `proposed_test`: 8 records

Chapter assignment:

- `proposed_dev`: chapters 2, 4, 7, 8, 11, 13, 14, 16
- `proposed_test`: chapters 18, 22, 23, 24, 25, 32, 33

Repeated chapters remain isolated:

- Chapter 7: 3 records, all `proposed_dev`
- Chapter 11: 2 records, all `proposed_dev`
- Chapter 14: 2 records, all `proposed_dev`
- Chapter 24: 2 records, all `proposed_test`

Topic-specialized concept groups avoid cross-chapter generic-label leakage:

- `chemical_energy_glossary`
- `electromagnetic_spectrum_glossary`
- `temperature_scales_section_summary`
- `explosive_bolts_probe_separation_problem`
- `downhill_ski_energy_comparison_problem`

## Near-Duplicate Rule

If later annotation finds near-duplicate questions across different chapters or
concept groups, assign every near-duplicate member to the same split and record
the override in the split report. Do not move records based on model results.

## Expansion Target

The later formal target is 60 Dev / 180 Test. For expansion, keep the same
chapter-isolation principle but choose a larger chapter partition that better
matches the target ratio.

Recommended expansion procedure:

1. Group all accepted Gold records by OpenStax `chapter_id`.
2. Group near-duplicate questions inside each chapter by normalized question and
   answer text.
3. Assign whole chapters to Dev until the Dev target is reached.
4. Assign remaining chapters to Test.
5. If a chapter is too large and must be split, split only by stable
   `concept_group`, never by individual random question.

## Output

The current proposed split file is:

```text
m3_gold/gold_v0_1.jsonl
```

No separate split report is included in this cleaned PR. The deterministic rule
and current distribution above are the split audit record for v0.1.
