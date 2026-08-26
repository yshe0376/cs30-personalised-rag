# Staging integration proposal

## Recommendation

Use two explicit stages rather than waiting for every real module:

1. **Staging preview now:** the existing staging configuration with fixture
   adapters forced on and a visible fixture banner. This validates startup,
   packaging, UI behaviour and the client walkthrough.
2. **Real staging after adapter hand-off:** the same UI and `PipelineRun`
   contract, with Member 6 and 7 implementations supplied by
   `build_real_deps()` and secrets supplied by the hosting environment.

Prefer a university-managed VM/container or approved school environment for
real staging. If none is available, use a private, access-controlled cloud
service only after the Leader/client confirms hosting, privacy, cost and secret
management. Do not make a public deployment the default.

## Proposed adapter composition

`build_real_deps(config)` is the only composition point that should change.
It should return:

```python
PipelineDeps(
    mode="real",
    profile_provider=real_profile_provider,
    retriever=real_retriever,
    generator=real_answer_generator,
)
```

Required hand-offs:

| Owner | Required hand-off | Integration acceptance |
|---|---|---|
| Member 5 | Persistent `IndexArtifact` and index location | Another process can load it |
| Member 6 | `Retriever` implementation | Returns ranked hits, chapter and source through the current contract |
| Member 7 | `ProfileProvider` and `AnswerGenerator` | Three levels, fixed JSON, timeout/error handling and grounded citations |
| Leader | Approved `build_real_deps()` composition and deployment target | One command starts the integrated path |
| Platform and demo owner | Launchers, configuration, smoke gate, logs and demo runbook | Another member can reproduce the staging demo |

## Proposed real-staging configuration

Keep `src/cs30/configs/staging.toml` as the non-fixture configuration. Supply
deployment-specific values as environment variables or platform secrets:

```text
CS30_ENV=staging
CS30_FIXTURE_MODE=false
CS30_LOG_LEVEL=INFO
CS30_LOG_DIR=logs
LLM_PROVIDER=<approved provider>
LLM_MODEL=<approved model>
LLM_API_KEY=<secret store only>
```

Additional index/model locations should be added only when Members 5–7 define
their adapter requirements. Never place machine-specific absolute paths in the
shared configuration.

## Real-staging acceptance gate

1. `build_real_deps()` returns protocol-compatible implementations.
2. The persistent index loads in a fresh process.
3. A grounded question returns Top-K evidence and a parseable answer.
4. Every citation ID exists in the same retrieval result.
5. An out-of-scope question produces a safe refusal or agreed abstention.
6. No secret appears in Git, the browser, screenshots or logs.
7. `python -m pytest -m smoke` passes with fixture mode, followed by a separate
   real-staging smoke run using approved credentials.
8. A second team member reproduces the launch from the README.

## Decisions to confirm before real staging

The proposed defaults are:

- **Hosting:** university-managed environment first; otherwise an approved
  private cloud deployment.
- **Access:** team/client-only during development, not public.
- **Model:** one approved provider/model for Week 1 integration; comparison is
  deferred to formal experimentation.
- **Secrets:** hosting secret store or injected environment variables.
- **Ownership:** The integration lead approves composition and infrastructure;
  the platform and demo owner maintains reproducible startup, operational
  documentation and smoke verification.
