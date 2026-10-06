# Member 8 - v2 demo interface

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

## Concept Check fixture preview

The existing question-and-answer UI is retained. After a cited answer passes
validation, the result panel offers an optional **Quiz me** action. The
Concept Check is off until the learner selects that action and is explicitly
labelled fixture/development. It
adapts the saved `PipelineRun` to the v2 contracts, then delegates question
selection, deterministic grading, JSONL event storage, and LearnerState replay
to M7's `ConceptCheckService`.

Each submission or skip creates an immutable attempt record. Incorrect and
skipped results can start a new attempt without changing the earlier event.
The result view keeps the question and submitted choice visible, gives immediate
feedback, and shows compact LearnerState values plus the attempt history.

This adapter does not create official v2 identities or results. Real-mode
Concept Check remains unavailable until the v2 retrieval result, reviewed
question release, current-corpus binding, Topic map, and post-answer composition
seam have passed their upstream gates.
