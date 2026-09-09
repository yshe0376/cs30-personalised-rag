# Real offline index build

Install with `python -m pip install -e ".[ml,parse]"`. JSON input needs only
`[ml]`; PDF parsing additionally needs `[parse]`. The selected embedding model
must be available locally or downloadable on the first run.

Build from M2's shared contract file (not its extended `records.jsonl`):

```sh
cs30-build parsed_openstax/openstax_document.json --index-dir data/index-w5 --candidate S2
```

Or parse an OpenStax College Physics 2e PDF and build in one command:

```sh
cs30-build college-physics.pdf --chapters 2 3 4 --index-dir data/index-w5 --candidate S2
```

List the registered textbook IDs:

```sh
cs30-list-textbooks
```

Build one of the five SciQ Appendix A CK-12 sources from a locally retained PDF:

```sh
cs30-build ck12-physics-intermediate.pdf \
  --textbook ck12_physics_concepts_intermediate \
  --chapters 1 2 3 \
  --index-dir data/index-ck12-physics-intermediate \
  --candidate S2
```

The same command supports these CK-12 IDs:

- `ck12_peoples_physics_basic`
- `ck12_physical_science_concepts_middle_school`
- `ck12_physical_science_middle_school`
- `ck12_physics_concepts_intermediate`
- `ck12_peoples_physics_concepts`

The CK-12 entries preserve the source pages and `CC BY-NC 3.0` licence reported
by the SciQ paper. The catalogue does not download or redistribute the books.
Because legacy CK-12 PDF structure varies, each title must pass the parser QA
gate before its output is admitted to the frozen corpus. The PDF adapter also
checks the embedded title, outline, and first five pages against the selected
catalogue profile so a different local PDF cannot be silently labelled as CK-12
or OpenStax.

`python -m cs30.build` is equivalent to `cs30-build`. Run `--help` for all options.
`--model` selects the embedding model, not the answer-generation LLM.
The default is `sentence-transformers/all-MiniLM-L6-v2`.
M4 counts tokens with that same model's tokenizer and the real build adapts its
chunk-size ceiling to the model's input limit. A chunk that still exceeds the
limit is rejected before FAISS indexing, so the index cannot silently contain
truncated embeddings. This is an engineering build, not evidence of retrieval
effectiveness.

The output directory must be empty or absent. Each build writes M5's
`artifact.json`, `chunks.json`, and `index.faiss`. A failed build reports an
error and does not produce a valid artifact. There is no fixture fallback.
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
