# OpenStax College Physics 2e Parser v1.1.0

This version implements the CS-30 Week 1 requirements for Member 2 while
remaining compatible with the v1.0.0 command format and record fields.

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

- `openstax_document.json`: document metadata, full normalized text, records,
  spans, and known issues.
- `records.jsonl` / `all_records.jsonl`: all paragraph, heading, equation,
  figure, caption, and table records.
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

Member 4 can either:

1. chunk `openstax_document.json["text"]` and retain document-relative spans;
   or
2. consume `records.jsonl` and group paragraph records without crossing a
   chapter boundary.

For traceability, every record satisfies:

```python
document["text"][record["char_start"]:record["char_end"]] == record["text"]
```

Before handoff, complete the ten manual checks in `qa_report.json`, especially
for formulas, tables, figures, captions, and page transitions.
