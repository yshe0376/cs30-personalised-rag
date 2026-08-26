# Customer and Tutor Demo Runbook

## Purpose and boundary

Demonstrate that the Week 1 interface and shared `PipelineRun` path are runnable.
The current staging preview uses fixed fixture data. It does not demonstrate
retrieval quality, model accuracy or a connected real LLM.

## Before the session

1. Fetch the approved team revision and confirm the intended branch/commit.
2. Run `python -m pytest -m smoke` and record the result.
3. Start `start_staging_preview.cmd` on Windows or
   `./start_staging_preview.sh` on macOS/Linux.
4. Confirm that the page says `STAGING PREVIEW · FIXTURE MODE`.
5. Confirm that `logs/cs30.log` is created.
6. Keep one screenshot of the working page as a fallback.

## Suggested two-minute walkthrough

1. **State the boundary.** “This is a fixture-backed integration demo. The UI
   runs the shared pipeline contract, but the real retriever and LLM are not
   connected yet.”
2. **Show the inputs.** Select `Beginner`, keep `What is acceleration?`, then
   run the pipeline.
3. **Show the output.** Point out the generated answer, citation ID, citation
   integrity, retrieved evidence, chapter and source.
4. **Show personalisation.** Select `Advanced` and rerun the same question.
   Explain that the fixture response template changes by learner level; the
   real prompt and LLM are still Member 7's integration step.
5. **Show safe refusal.** Select the prepared `Safe refusal` question and run
   it. Explain that no evidence is a valid result and the system refuses rather
   than fabricating an answer.
6. **Show technical details if asked.** Expand `Technical run details` to show
   the complete `PipelineRun` JSON, environment, mode and timings.

## Presenter checks

| Check | Expected result |
|---|---|
| Page banner | Clearly says fixture mode |
| Learner levels | Beginner, Intermediate and Advanced are selectable |
| Grounded example | Answer and at least one evidence passage appear |
| Evidence provenance | Chapter and source appear |
| Citation integrity | `PASSED` and cited IDs exist in retrieved hits |
| Out-of-scope example | No evidence and an explicit refusal |
| Technical details | Valid `PipelineRun` JSON |

## If the live page fails

1. Read the safe error on screen; do not hide or edit it during the session.
2. Check the launcher terminal and `logs/cs30.log`.
3. If the port or Python process is stale, restart once.
4. Use the prepared screenshot and explain the failure honestly if restart does
   not recover within one minute.
5. Record the failure for the integration backlog.

## After the session

Stop Streamlit with `Ctrl+C`. Do not upload logs until they have been checked
for secrets or private data. Record client questions, integration failures and
the next owner in the team backlog.
