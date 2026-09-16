# Real offline index build

Install with `python -m pip install -e ".[ml,parse]"`. JSON input needs only
`[ml]`; PDF parsing additionally needs `[parse]`. The selected embedding model
must be available locally or downloadable on the first run.

Build from M2's shared contract file (not its extended `records.jsonl`):

```sh
cs30-build data/processed/openstax-w5-v2/openstax_document.json \
  --index-dir data/index-w5 --candidate official
```

If M2 supplies the per-chapter archive used for the W5 handoff, prepare the
single document first.  This preserves one document-wide character-span
coordinate system for M3 gold evidence and M4 chunks:

```sh
cs30-evaluate prepare-corpus \
  --archive D:/path/to/data.zip \
  --output-dir data/processed/openstax-w5-v2
cs30-build data/processed/openstax-w5-v2/openstax_document.json \
  --index-dir data/index-w5 --candidate official
```

The prepared corpus manifest records the source document hash, parser version,
selected chapters, and archive hash.  It is a handoff artifact, not a Gold
sample or an evaluation result.

Or parse an OpenStax College Physics 2e PDF and build in one command:

```sh
cs30-build college-physics.pdf --chapters 2 3 4 --index-dir data/index-w5 --candidate official
```

`official` is the default, and is the frozen W5 configuration
`w5-m4-official-v1`. It is the only candidate whose content filter matches the
evidence policy Gold is annotated against, so an index built any other way
cannot be scored against Member 4's mapping — the chunk IDs will not correspond.

The `S1`-`S6` ablation candidates stay reachable but abort on the real corpus.
They filter by content type, and the surviving blocks repeat verbatim — short
equations, figure captions and glossary entries recur at different source
locations in the textbook — while every one of them still sets
`reject_duplicate_text=True`. The frozen configuration sets it to `False` for
exactly that reason. Until the shared candidates are updated, the retrieval
ablation cannot run against real text.

`main` applies no content filter, so it indexes the `problem` and `summary`
blocks the evidence policy excludes. Use it only for quick local checks.

`python -m cs30.build` is equivalent to `cs30-build`. Run `--help` for all options.
`--model` selects the embedding model, not the answer-generation LLM.
The default is `sentence-transformers/all-MiniLM-L6-v2`.
M4 counts tokens with that same model's tokenizer. Its default size constraints
can exceed the model's sequence limit; M5 warns about truncation. This is an
engineering build, not evidence of retrieval effectiveness.

The output directory must be empty or absent. Each build writes M5's
`artifact.json`, `chunks.json`, and `index.faiss`. Failed builds may leave partial
files; choose another output directory when retrying. There is no fixture fallback.
Standard output is the IndexArtifact JSON; progress goes to standard error.
After building, the entry point verifies BM25 loading of the saved chunk map.
Dense/hybrid model loading happens separately in the online retrieval process.

To query the result in PowerShell:

```powershell
$env:CS30_INDEX_DIR = "data/index-w5"
cs30-demo --mode real --retrieval-mode hybrid --provider mock --question "What is acceleration?"
```

The reusable `cs30.build.build_real_build_deps()` factory supplies M1's existing
`BuildDeps` for `run_build_pipeline()`. `RealDocumentParser` converts M2's internal
PDF representation to the shared contract before M4 runs. JSON input skips PDF
parsing but undergoes the same contract validation. PDF QA artifacts are not
exported by this entry point; use `cs30-parse-openstax` separately when needed.
