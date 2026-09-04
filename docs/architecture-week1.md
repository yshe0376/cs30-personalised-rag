# Week 1 architecture: components, data flow, and call path

Scope: the `v0.1-thin-slice` engineering path only. The semester-long design
(hybrid retrieval, evidence roles, restricted KG, the full evaluation layer)
lives in `docs/系统架构与文献映射.md` and is deliberately **not** shown here.

## 1. Components and ownership

Every box is one member's module. Cross-module payloads are frozen contracts
from `src/cs30/contracts`; computational boundaries are Protocols in
`src/cs30/ports.py`. The UI consumes `PipelineRun` directly.

```mermaid
flowchart TB
    subgraph offline["Offline — build the knowledge base"]
        RAW[("OpenStax source<br/>data/raw/ · git-ignored")]
        M2["<b>Member 2</b><br/>cs30.ingest<br/><i>DocumentParser</i>"]
        M4["<b>Member 4</b><br/>cs30.chunking<br/><i>Chunker</i>"]
        M5["<b>Member 5</b><br/>cs30.indexing<br/><i>IndexBuilder</i>"]
        IDX[("FAISS IndexFlatIP<br/>indexes/ · git-ignored")]
        RAW --> M2
        M2 -->|"OpenStaxDocument"| M4
        M4 -->|"list[Chunk]"| M5
        M5 --> IDX
    end

    subgraph online["Online — answer one question"]
        Q(["Student question"])
        M6["<b>Member 6</b><br/>cs30.retrieval<br/><i>Retriever</i>"]
        M7P["<b>Member 7</b><br/>cs30.profile<br/><i>ProfileProvider</i>"]
        M7G["<b>Member 7</b><br/>cs30.generation<br/><i>AnswerGenerator</i>"]
        CIT["cs30.citation<br/>integrity check"]
        Q --> M6
        IDX -.->|"loaded by"| M6
        M6 -->|"RetrievalResult"| M7G
        M7P -->|"StudentProfile"| M7G
        M7G -->|"GeneratedAnswer"| CIT
    end

    subgraph shell["Leader — integration shell"]
        PIPE["cs30.pipeline<br/>run_pipeline()"]
        CFG["cs30.config · cs30.logging · cs30.errors"]
    end

    M3["<b>Member 3</b><br/>cs30.questions<br/><i>QuestionProvider</i>"] -->|"SciQQuestion"| Q
    CIT -->|"PipelineRun"| M8["<b>Member 8</b><br/>cs30.ui<br/>demo interface"]
    PIPE -.->|"BuildDeps orchestrates"| offline
    PIPE -.->|"PipelineDeps orchestrates"| online
    CFG -.-> PIPE
```

## 2. Data flow with contract types

| Stage | Producer | Payload | Consumer |
|---|---|---|---|
| Parse | Member 2 | `OpenStaxDocument` | Member 4 |
| Chunk | Member 4 | `list[Chunk]` | Member 5, Member 6 |
| Index | Member 5 | `IndexArtifact` → FAISS index + `chunk_id` map | Member 6 |
| Question | Member 3 | `SciQQuestion` | Members 6, 7 |
| Retrieve | Member 6 | `RetrievalResult` | Member 7 |
| Profile | Member 7 | `StudentProfile` | Member 7 |
| Generate | Member 7 | `GeneratedAnswer` | citation check, UI |
| Run | Leader | `PipelineRun` | Member 8, ablation table |

The character-span convention that ties `Chunk` back to `OpenStaxDocument` is
specified in [interfaces.md](interfaces.md) and enforced by the contract layer.

## 3. End-to-end call path

```mermaid
sequenceDiagram
    participant UI as UI / CLI (M8)
    participant PL as run_pipeline (Leader)
    participant PR as ProfileProvider (M7)
    participant RT as Retriever (M6)
    participant GN as AnswerGenerator (M7)
    participant CK as citation check

    UI->>PL: question + level
    PL->>PR: get(level)
    PR-->>PL: StudentProfile
    PL->>RT: retrieve(question, top_k)
    alt evidence found
        RT-->>PL: RetrievalResult(hits=[...])
        PL->>GN: generate(question, profile, retrieval)
        GN-->>PL: GeneratedAnswer(citations=[...])
    else nothing relevant
        RT-->>PL: RetrievalResult(hits=[])
        PL->>GN: generate(question, profile, retrieval)
        GN-->>PL: GeneratedAnswer(abstained=True)
    end
    PL->>CK: validate_citations(answer, retrieval)
    CK-->>PL: every citation came from retrieval
    PL-->>UI: PipelineRun
```

Two properties this path guarantees, and they are the reason the project exists:

1. **Grounding.** `validate_citations` rejects any answer citing a chunk that
   retrieval did not return. A fabricated source cannot survive the pipeline.
2. **Refusal.** Empty retrieval leads to an abstained answer rather than an
   answer built from unrelated evidence.

## 4. The integration seam

The offline and online paths have separate dependency groups:

- `run_build_pipeline()` uses `BuildDeps` to run parser → chunker → index builder,
  then passes the returned `IndexArtifact` to `Retriever.load_index()`.
- `run_pipeline()` uses `PipelineDeps` for profile → retrieval → generation.

`build_fixture_build_deps()` and `build_fixture_deps()` supply stand-ins. The
configured-provider path is wired through the same frozen interfaces in
`build_real_deps()`. It remains labelled as a fixture run until a real Member 6
retriever and index replace the portable smoke evidence:

```python
def build_real_deps(config: AppConfig) -> PipelineDeps:
    return PipelineDeps(
        mode="fixture",
        profile_provider=Week1ProfileProvider(),
        retriever=CombinedEvidenceRetriever(evidence),
        generator=PersonalisedAnswerGenerator(client),
    )
```

Member 3 works behind `QuestionProvider`; member 8 consumes `PipelineRun`
directly. This keeps module work independent without claiming that the UI is a
computational Protocol implementation. Member 6's later dense retriever can
replace the portable retriever without changing `PipelineDeps` or the contracts.

## 5. What is deliberately absent in week 1

BM25 and RRF, evidence-role annotation, restricted KG, topic resolution,
level-aware reranking, calibrated abstention thresholds, and every retrieval or
answer metric. Week 1 proves the path runs; it proves nothing about quality.
