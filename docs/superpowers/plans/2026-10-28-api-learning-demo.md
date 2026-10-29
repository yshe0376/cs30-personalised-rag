# Online Concept Check Task Checklist

Recorded 2026-10-29; governed by [framework v3](../specs/2026-10-28-api-learning-demo-design.md).
This replaces the initial plan's independent model review, 2–3 Topic allowlist and
single-Topic evidence requirements. "Implemented" below describes the local
worktree at that snapshot, not code submission or a merge into main. Later
implementation delivery and definition updates are tracked separately in
[PR #219](https://github.com/yshe0376/cs30-personalised-rag/pull/219).

## Implemented Framework at the Snapshot

- [x] One page for free-text questions, textbook citations, Concept Checks and profiles.
- [x] Qwen3 hybrid retrieval and existing reranking, retaining asset identity and local-weight checks.
- [x] Select Topics from validated answer citations; `topic_ids = ["*"]` enables every registered Topic.
- [x] Allow multi-Topic cited passages, select one Topic weighted by citation support, and persist an audit record.
- [x] API authoring of question, four options, answer, explanation and source quotation from the corresponding textbook text.
- [x] Remove independent model review and answer-uniqueness review; do not call a reviewer API.
- [x] Retain structural checks, citation-source restrictions, and quotation/chapter location; at most two author requests per question.
- [x] Show answer, explanation and quotation after an attempt; grade locally and replay events, without publishing drafts to the formal pool.
- [x] Sidebar follows the Concept Check Topic, with historical Topic switching, manual level changes and initial-level selection for a new session.
- [x] Common LaTeX display adaptation, preserving existing formulas and code blocks.
- [x] Persistent request accounting and cap; local keys, assets and events stay out of Git.
- [x] 17 related offline tests and corresponding Ruff checks passed; no paid API was called for that validation round.

## Delivery and Acceptance Items Open at the Snapshot

- [ ] Separately review, commit and integrate local implementation code; this framework-documentation PR is not code delivery.
- [ ] Within the user-confirmed request allowance, accept the combined real question-answering, quiz, attempt and profile loop.
- [ ] Sample across textbooks and Topics to manually review semantic alignment among answers, explanations and quotations.
- [ ] Report citation-mapping rate, question availability, structure failures, location failures and manually assessed correctness separately.
- [ ] Reproduce and investigate the Streamlit `removeChild` frontend error in the user's screenshot; do not claim it is fixed.
- [ ] If development diagnosis requires it, add private retention of raw author responses; only safe failure summaries are currently displayed.
- [ ] Formal M7/M8, Test and model freezes continue under their own frozen protocols; online Demo operation is not an experimental conclusion.

## What Acceptance Does Not Establish

Enabling all registered Topics does not mean that every textbook passage is mapped.
Locating a quotation does not establish answer correctness. Mastery is practice
state derived from AI answer labels, not a validated measure of learning ability.
