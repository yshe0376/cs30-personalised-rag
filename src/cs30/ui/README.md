# Member 8 - demo interface

This module consumes `PipelineRun`.

## Week 1 acceptance

- A new member can start the system from the README.
- The client can pick a level, ask a question, and see the answer and sources.
- No real key reaches the repository.

## Notes

Always surface `PipelineRun.mode`. A fixture run must never be presented
as a real result, and an abstained answer must be shown as a refusal
rather than as an empty answer.

## Run locally

Install the project as described in the repository README, then start the UI:

```bash
python -m streamlit run src/cs30/ui/app.py
```

The first version intentionally calls the fixture pipeline. Replace the dependency
builder at the composition boundary only after the leader wires the real adapters.
