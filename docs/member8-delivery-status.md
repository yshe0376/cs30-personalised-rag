# Member 8 delivery status

Status is based on the Week 1 V2 plan. `Complete` means the repository contains
the deliverable and it can be checked locally. `External gate` means Member 8
has prepared the integration path but another owner must supply or approve a
dependency.

| Required delivery | Status | Evidence / remaining action | Primary hand-off |
|---|---|---|---|
| Python version and dependency list | Complete | `pyproject.toml`, Python 3.11+ | Leader reviews changes |
| Environment variables and API-key template | Complete for current scope | `.env.example`; real secrets stay outside Git | Member 7/provider supplies required secret names |
| Windows one-click startup | Complete | `.cmd` launchers plus `.bat` aliases for development and staging preview | Another Windows member reproduces it |
| macOS/Linux startup | Complete | `start_demo.sh`, `start_staging_preview.sh` | A Mac member reproduces it |
| Streamlit demo interface | Complete | Level, question, answer, citations and evidence | Leader reviews UI |
| Evidence chapter, content type and source | Complete | `RetrievalHit.content_types` and UI display | Member 6 must preserve the field in the real adapter |
| Development configuration | Complete | `development.toml`, fixture mode | None |
| Staging configuration | Complete as configuration | `staging.toml` is non-fixture | Leader approves deployment values |
| Fixture-backed staging preview | Complete | Explicit preview launchers and banner | Tutor/client can review the flow |
| Real staging runtime | External gate | Proposal and acceptance gate documented | Members 5–7 plus Leader |
| CI | Complete by Leader | Existing GitHub Actions runs lint, tests and smoke | Member 8 does not duplicate it |
| Dedicated Smoke Test | Complete for fixture path | `pytest -m smoke` checks startup, index, retrieval, JSON, citations, staging preview and logs | Repeat against real adapters after integration |
| Log file and location | Complete | Terminal plus rotating `logs/cs30.log` | Deployment may redirect `CS30_LOG_DIR` |
| Common errors and recovery | Complete | `docs/troubleshooting.md` | Update when real adapter failures are known |
| README and installation instructions | Complete | Manual and one-click instructions | Second member performs clean-machine check |
| Customer demo operation guide | Complete | `docs/member8-demo-runbook.md` | Leader agrees presentation order |
| Staging architecture proposal | Complete | `docs/staging-integration-plan.md` | Leader decides hosting/access/model |
| Clean-machine reproducibility | External verification | Repository is prepared; another member must run it | One Windows and preferably one Mac teammate |

## Remaining conversations

1. **Member 6:** confirm the real Retriever copies content types into each
   `RetrievalHit` and supplies an index-loading smoke fixture.
2. **Member 7:** confirm the concrete Provider/Generator class names, required
   environment variables, timeout behaviour and JSON failure handling.
3. **Leader:** approve the shared `RetrievalHit.content_types` addition,
   `build_real_deps()` composition, deployment target, access policy and secret
   storage.
4. **One teammate:** follow only the README and report any missing step. This is
   the final proof that the environment is reproducible.
