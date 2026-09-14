# M3 Gold Evidence v0.1.1

This directory contains the local contract for W5 M3 Gold Evidence annotation.

## Files

- `gold_v0_1_1.jsonl`: M3 Gold v0.1.1 JSONL normalized to the M4
  unified 34-chapter source corpus.
- `gold_v0_1_1.schema.json`: JSON Schema for one JSONL record.
- `candidate_pool_v0_1_1.review_labeled.csv`: M3 manual review record for accepted candidates.
- `dev_test_split_plan_v0_1_1.md`: deterministic proposed Dev/Test split plan.
- `personalisation_candidate_list_v0_1_1.csv`: provisional M3 personalisation candidate screen.
- `personalisation_candidate_list_v0_1_1.md`: narrative summary of the personalisation screen.
- `validate_gold.py`: dependency-free validator for schema-adjacent checks and OpenStax char-span audits.

## Record Semantics

`gold_core_evidence_sets` is an OR-of-ANDs:

- Outer list: alternative sufficient evidence paths.
- Inner list: spans that must be jointly retrieved for that path.

For example, `[[span_A, span_B], [span_C]]` means either both `span_A` and
`span_B` are retrieved together, or `span_C` alone is retrieved.

`partial_evidence` is related but insufficient evidence. It must not be counted as a complete Gold hit.

`gold_answer` is the option id (`A`, `B`, `C`, or `D`), not the raw answer text. The correct answer text remains in `gold_answer_text`.

Gold v0.1.1 is bound to the M4 unified source corpus:

- Corpus root: `m3_unified_source_corpus/source_corpus/`
- Source document: `openstax_document.json`
- Corpus version:
  `openstax-cp2e-a052d9fae2a90e13-ch01-34-v9c54ac0e04d23864`

Consumers must use `document_id + char_start + char_end` against the unified
document `text` to replay a span exactly. Each span also carries `chapter_id`
and `block_id` so M4/M5 can map Gold evidence to chunks without reconstructing
block membership from character offsets alone. The span object does not carry
`content_type`; consumers should read the block type from the source corpus by
`block_id`.

Evidence spans are restricted to six source content types:

- `body`
- `equation`
- `example`
- `figure_caption`
- `glossary`
- `table`

If the best support lands in `summary`, `learning_objective`, `problem`, or
another excluded type, replace it with allowed evidence where possible. If no
sufficient allowed evidence exists, move the item to the unresolved pool rather
than marking it unanswerable from support mismatch alone.

`annotation_status` is `m3_initial` for this package. The
`candidate_pool_v0_1_1.review_labeled.csv` file records M3's manual accept
decisions, but it is not an independent M2 provenance review.

`personalisation_eligibility` is intentionally `pending` in `gold_v0_1_1.jsonl`
until M1 confirms the A3 taxonomy definition.

## Known Limitations

These are deliberate limits of the v0.1.1 batch, not data errors. Read them
before consuming the file.

- **Answer position is not randomised.** Every record has `gold_answer: "D"`,
  because options are emitted in the fixed order `distractor3`, `distractor1`,
  `distractor2`, `correct_answer`. An "always answer D" baseline therefore
  scores 100 percent. Do not report answer accuracy from this file until
  option order is shuffled deterministically, seeded by `question_id`.
- **No unanswerable records.** All 20 records are `answerable: true`, so this
  batch cannot exercise the abstention confusion table (correct abstention,
  answered-when-unanswerable).
- **Accepted candidates only.** `candidate_pool_v0_1_1.review_labeled.csv`
  records the 20 accepted items; rejected and unalignable candidates are not
  logged here, so selection bias cannot be audited from it.
- **Selection remains lexical.** This batch still favours questions whose
  answer string appears verbatim in an OpenStax span. It should not be used to
  compare BM25, dense, and hybrid retrieval quality.

Randomised option order and unanswerable records are the first targets for
Gold v0.2.

## First-Step Contract

M1/M8 should be able to load each JSONL object using these stable fields:

- `question_id`
- `source_split`
- `question`
- `options`
- `gold_answer`
- `gold_answer_text`
- `answerable`
- `gold_core_evidence_sets`
- `partial_evidence`
- `question_difficulty`
- `question_type`
- `concept_group`
- `personalisation_eligibility`
- `eligibility_reason`
- `split`
- `corpus_version`
- `parser_version`
- `gold_annotation_version`
- `annotation_status`
- `review_record_id`
- `source`

Run:

```sh
python3 m3_gold/validate_gold.py \
  --corpus-root m3_unified_source_corpus/source_corpus \
  m3_gold/gold_v0_1_1.jsonl
```

If the parsed OpenStax corpus lives elsewhere, pass that directory with
`--corpus-root` or set `CS30_OPENSTAX_ROOT`.

Loader smoke check:

```python
import json
from pathlib import Path

from cs30.evaluation import load_gold_samples

document = json.loads(
    Path("m3_unified_source_corpus/source_corpus/openstax_document.json").read_text()
)
samples = load_gold_samples(
    "m3_gold/gold_v0_1_1.jsonl",
    documents={document["document_id"]: document["text"]},
)
```

Calling `load_gold_samples("m3_gold/gold_v0_1_1.jsonl")` only parses records and
does not validate spans against source text.
