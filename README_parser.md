# OpenStax College Physics 2e Parser v1.2.0

This version implements the CS-30 Week 1 requirements for Member 2 while
remaining compatible with the v1.0.0 command format and record fields.

Version 1.2.0 also matches the team's strict `models.py` v1 contract.

## Main improvements

- Recovers equations that are missing from the ordinary PDF text layer by
  reading the Tagged-PDF accessibility structure and formula `alt_text`.
- Inserts recovered equations back into paragraph reading order as
  `[EQUATION: ...]` instead of leaving blank spaces or corrupted symbols.
- Keeps both `formula_alt_text` (the source description) and
  `formula_display` (a conservative readable conversion) for QA.
- Uses the PDF outline for stable chapter and section boundaries.
- Keeps paragraph/text-block records and also builds one
  `OpenStaxDocument.text` string.
- Stores `char_start` and `char_end` for every record relative to the complete
  document text.
- Preserves v1 fields such as `chunk_source_id`, `section_type`, and
  `page_text_index` as compatibility aliases.
- Creates deterministic JSON/JSONL, metadata, statistics, known-issue, and QA
  outputs.
- Writes `openstax_document.json` with exactly the fields accepted by
  `models.OpenStaxDocument`; no forbidden parser-only fields are included.
- Represents each parser unit as a contract-compatible `TextBlock`. The block
  stores only a character span, while `OpenStaxDocument.text` remains the
  single source of truth.
- Adds contract `ContentType` values such as `body`, `heading`, `equation`,
  `example`, `summary`, `problem`, and `glossary`.

## Install

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

On Windows, activate the environment with:

```powershell
.venv\Scripts\activate
```

## Run one pilot chapter first

The original v1 command remains valid:

```bash
python college_physics_parser.py college-physics-2e_-_WEB.pdf \
  --chapters 2 \
  --output parsed_ch2 \
  --download-date 2026-09-03
```

## Run 2-3 chapters

Comma-separated syntax:

```bash
python college_physics_parser.py college-physics-2e_-_WEB.pdf \
  --chapters 2,3,4 \
  --output parsed_openstax \
  --download-date 2026-09-03
```

Space-separated and range syntax are also accepted:

```bash
python college_physics_parser.py college-physics-2e_-_WEB.pdf \
  --chapters 2 3 4 \
  --output-dir parsed_openstax

python college_physics_parser.py college-physics-2e_-_WEB.pdf \
  --chapters 2-4 \
  --output parsed_openstax
```

## Outputs

- `openstax_document.json`: strict `models.py` `OpenStaxDocument` payload with
  `schema_version`, metadata, full text, `chapters`, and `blocks`.
- `blocks.jsonl`: the contract-compatible `TextBlock` objects, one per line.
- `records.jsonl` / `all_records.jsonl`: all paragraph, heading, equation,
  figure, caption, and table records with extended parser/debug fields. These
  are compatibility outputs, not the cross-module contract.
- `chapter_N.json` and `chapter_N.jsonl`: compatibility outputs per chapter.
- `metadata.json`: title, edition, source, download date, SHA-256 hash, parser
  version, selected chapters, and statistics.
- `stats.json`: record, character, chapter, and issue statistics.
- `qa_report.json`: ten deterministic samples plus the manual QA checklist.
- `known_issues.json` / `known_issues.jsonl`: formula-conversion, figure, table,
  and cross-page limitations.
- `run_manifest.json`: reproducible input hash, parser version, and chapters.

## Formula policy

Many equations in this OpenStax PDF are vector graphics, not normal text.
PyMuPDF's plain `get_text()` therefore returns a blank where the formula should
be. This parser reads the source PDF's accessibility description instead.

Example output:

```text
Since elapsed time is [EQUATION: Δt = t_f − t_0], taking
[EQUATION: t_0 = 0] means that [EQUATION: Δt = t_f].
```

The symbolic conversion is deliberately conservative. For complex equations,
`formula_alt_text` remains the source of truth and `known_issues.json` flags
lower-confidence conversions for manual review. The parser does not use OCR or
invent a formula that is absent from both the text layer and accessibility
metadata.

## Handoff to Member 4

The preferred handoff is now `openstax_document.json`. It can be loaded without
field conversion:

```python
import json
from models import OpenStaxDocument

with open("parsed_openstax/openstax_document.json", encoding="utf-8") as file:
    document = OpenStaxDocument.model_validate(json.load(file))
```

Member 4 can then:

1. chunk `document.text` without crossing the spans in `document.chapters`;
2. use `document.blocks` to preserve section, page, and `content_type`; and
3. obtain any block's exact source text with `document.block_text(block)`.

For traceability, every record satisfies:

```python
document["text"][record["char_start"]:record["char_end"]] == record["text"]
```

Before handoff, complete the ten manual checks in `qa_report.json`, especially
for formulas, tables, figures, captions, and page transitions.
