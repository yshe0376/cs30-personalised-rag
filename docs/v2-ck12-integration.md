# v2 CK-12 source integration

## Pinned delivery

The v2 catalogue now includes CK-12 *People's Physics Concepts (With Answers)*
as `ck12_peoples_physics_concepts`. The build reads M2's parsed delivery from
the `M2_ck12` release:

| Item | Pinned value |
|---|---|
| Source version | `2016-09-09` |
| PDF SHA-256 | `6e8bbab8107fd79e9a8ce1487c938b85cd8101edd756ba61aac9448952daebe2` |
| Parsed JSON SHA-256 | `1039bc79faf12609203b3d8dcef5d4aeec69b1e5fbe2e85cc1963d7be5ed0e66` |
| Release asset | `ck12_parser_v1_1_0.2.zip` |
| Parsed member | `ck12_parser_v1_1_0/ck12_output_without_chapter_21/openstax_document.json` |
| Included chapters | 1–20 |

The legacy filename `openstax_document.json` is retained in M2's CK-12 archive;
the v2 parser uses the CK-12 adapter and does not treat the file as OpenStax
output. The adapter preserves the source block IDs and spans. It also remaps
blocks whose `metadata.ck12_role` is `summary` from `body` to `summary`, so the
v2 retrieval evidence policy does not index them. Exercise and answer blocks
retain their non-evidence content types.

Install parsed sources with:

```powershell
.\.venv\Scripts\python.exe scripts\install_v2_sources.py --format parsed
```

The installer downloads each provider's archive, verifies the per-file hash,
and writes parsed files under `data/parsed/v2`. Local archives can be supplied
with repeated `--from-archive` options. The raw CK-12 parser is not vendored, so
the v2 source installer rejects `--format raw` while this textbook is required.

## QA and official-build gate

The release's automatic validation passed for 20 chapters, 4,702 blocks, and
467,042 characters. Its `qa_report.json` still sets
`manual_review_required: true`; all ten sample records are `pending`. The
release also records 13 issues, including image-only content, an untagged PDF,
formula and table layout, and cross-page text. The adapter carries
`source_qa_status=manual_review_required` in the document metadata.

The CK-12 licence is recorded as pending source-specific review. CK-12's
[current Curriculum Materials License](https://help.ck12.org/hc/en-us/articles/50990257420955-CK-12-Curriculum-Materials-License)
limits use to defined Educational Purposes and restricts AI/ML model training,
automated derivative creation, and aggregator distribution. CK-12 also says
usage depends on the license attached to each resource. The exact terms for
this 2016 PDF need to be confirmed before any RAG processing or application
use. See its [book page](https://www.ck12.org/book/peoples-physics-concepts/)
and the CK-12 [license guidance](https://help.ck12.org/hc/en-us/articles/53032403416219-Can-I-Use-CK-12-Content-to-Make-Money).

For those two reasons, `source_approved` is false for this catalogue entry.
The v2 pipeline fails closed before parsing in both development and official
modes until an authorized reviewer clears the source-specific terms and the
manual QA. Adding the adapter does not itself approve the textbook for RAG use.
