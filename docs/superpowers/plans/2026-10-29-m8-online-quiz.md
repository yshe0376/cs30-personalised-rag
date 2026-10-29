# M8 online Concept Check integration

Goal: use M8's Streamlit page and cards for the user's existing textbook-grounded
online authoring, local grading, and Topic progress flow.

User confirmed the source branch `feat/v2-streamlit-qa-demo` and requested direct
integration on 2026-10-29. Keep the original workspaces intact.

- [x] Import the existing `cs30.learning` implementation, its example configuration,
  asset preparation commands, and offline regression tests. Preserve the draft-only
  question boundary and persistent request budget.
- [x] Add an online learning mode to `qa_app.py`. Keep Team V2 and fixture modes
  available for comparisons. Online settings come from `LearningConfig`; do not
  imply that Team V2's model selector changes these settings.
- [x] Move the online page into `qa_learning.py`, use M8's answer/source cards and
  two-column practice styles, and turn `learning_app.py` into a compatibility entry.
- [x] Verify missing setup, mode switching, no answer disclosure before submission,
  grading/skip/undo, Topic progress, and the existing M8 offline flow without API calls.
- [x] Document the unified launch path and run relevant tests and Ruff checks.

Review focus: switching mode must not send requests; runtime remains session-local;
new profiles retain persistent request accounting; draft quizzes never enter the
published fixture provider; formula rendering preserves raw evidence.

Review fixes: keep the choice radio outside a form so browser changes enable
Submit; avoid feature TOMLs in `configs/` shadowing packaged app configuration.
Explicit `CS30_CONFIG_DIR` remains authoritative. Tests use fake API responses;
no paid online acceptance was performed.

Validation: full `pytest` with this worktree's `src` on `PYTHONPATH` passed
1,464 tests with one skip. Related M8/learning tests passed 68 cases before
the configuration regression tests were added; config and integration checks
passed 16 cases in independent review. Ruff for the added/changed learning and
configuration code and `git diff --check` passed.
