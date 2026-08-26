# Troubleshooting and log locations

This guide covers the Week 1 demo interface and staging preview. Start with the
terminal message, then inspect `logs/cs30.log`. The log records pipeline timings,
retrieval hit counts, learner level, abstention and citation counts. It must not
contain API keys or private student data.

## Log locations

| Location | What it contains | What to do |
|---|---|---|
| Launcher terminal | Startup, dependency and Streamlit errors | Keep the window open during the demo |
| `logs/cs30.log` | Application and pipeline events | Use this first for a failed pipeline run |
| `logs/cs30.log.1` to `.3` | Rotated older logs | Use when the current log began after the failure |
| Streamlit page error box | Safe error shown to the presenter | Record the message and check the terminal/log file |

Set another log directory before starting if required:

```powershell
set CS30_LOG_DIR=C:\temp\cs30-logs
.\start_demo.cmd
```

```bash
CS30_LOG_DIR=/tmp/cs30-logs ./start_demo.sh
```

## Common problems

### Python 3.11 or newer was not found

Install Python 3.11+ and ensure `py`, `python3` or `python` is available from the
terminal. Close and reopen the terminal, then run the launcher again.

### Dependency installation failed

Check the internet connection, VPN or university proxy. Then run:

```bash
python -m pip install -e ".[dev]"
```

Do not copy another member's `.venv`; virtual environments are machine-specific.

### Port 8501 is already in use

Close the older demo window or choose another port:

```powershell
set CS30_PORT=8502
.\start_demo.cmd
```

```bash
CS30_PORT=8502 ./start_demo.sh
```

Open the port printed by the launcher.

### The page is stale after a code or contract update

Stop the launcher with `Ctrl+C`, start it again, then use `Ctrl+F5` in the
browser. A browser refresh alone does not reload already-imported Python
contracts.

### `real adapters are not wired yet`

The real Member 6 Retriever and Member 7 Generator have not been composed in
`build_real_deps()`. Use `start_demo.*` or `start_staging_preview.*` until those
adapters pass the integration gate. Do not change the banner to claim real mode.

### The system returns no evidence

An empty retrieval result is valid. The generator should refuse instead of
inventing an answer. Use one of the prepared physics examples to demonstrate a
grounded answer.

### API key is missing

Fixture mode does not need an API key. Real staging will read credentials from
deployment environment variables or the hosting platform's secret store. Never
commit `.env` or paste a real key into source code, screenshots or logs.

### The browser does not open automatically

Keep the launcher running and open the printed address manually, normally
`http://127.0.0.1:8501`.

## Information to include when reporting a failure

1. Development, staging preview or real staging.
2. Operating system and Python version.
3. Exact startup command.
4. The safe error message and relevant log lines (remove secrets first).
5. Whether `python -m pytest -m smoke` passes.
6. The commit ID being demonstrated.
