# Review notes and items for confirmation

Date: 27 October 2026 (Sydney)
Status: **Provisional review notes; team confirmation is pending.**

## Summary

This review examines the existing **23 adaptation-criterion differences and 5 level-prediction differences**, plus the pending correctness assessment and the one evidence result still rejected after offline revalidation. It uses saved outputs and the frozen criteria; no new model calls were made.

These notes do not replace the original scores, record a completed team approval, estimate judge accuracy, or establish a final high/low choice. Decisions in human_review.md remain pending.

Main findings:

1. Both high and low have criterion-adherence issues. Lower cost or more thinking alone is not a basis for choosing a final setting.
2. B4 explicitly requires assessment for substantive answers. The absence of a formula is not a reason to return not_applicable; three existing differences can be checked directly against this rule.
3. Identification questions should not acquire unnecessary derivation or specialist-model requirements solely because the target is advanced. However, the identification exception does not excuse additional unsupported claims.
4. B3 needs a consistent convention for support already supplied in the question: an applicable criterion satisfied by that situation versus no additional support needed. Short answers should not automatically fail.
5. The high correctness needs_review result is consistent with the existing source-limited prompt: the supplied Gold core evidence does not establish the extra A-near-60 claim. Low's acceptance relies on knowledge outside that reference.
6. The remaining invalid high evidence output must stay unresolved. Do not remove it or invent the missing quotation.

## Sources and review scope

- Frozen criteria: [profile_checklist.frozen.json](https://github.com/yshe0376/cs30-personalised-rag/blob/b38a0a253bcb2d06a3bb74ef2547de6cf72a4c6d/docs/evaluation/level-profile-v1/profile_checklist.frozen.json).
- Existing outputs and the original paid trial: docs/results/m8_judge_trial_20261027/, as saved before the repair.
- Existing disagreement packet: docs/results/m8_judge_quote_revalidation_20261027/human_review.md.
- Correctness prompt: [build_judge_prompt](https://github.com/yshe0376/cs30-personalised-rag/blob/b38a0a253bcb2d06a3bb74ef2547de6cf72a4c6d/src/cs30/evaluation/open_answer_scoring.py#L120-L144).
- The opinions below evaluate adherence to the supplied profiles/checklists. They do not independently settle disputed specialist physics or medical-content claims. A reference/premise concern is escalated rather than silently rewriting Gold or forcing a high/low winner.

## 1. Adaptation: all 23 criterion differences

“Prefer” means closer to the existing criterion for this particular case, not a validated replacement score. N/A means not_applicable. Request IDs let the team locate the complete original judgments.

| # | Request / criterion | High → Low | Provisional finding and reason |
| --- | --- | --- | --- |
| 1 | adaptation-2fa418a5928a322a0d74 / A2 — quanta | fail → N/A | Prefer N/A for the naming task's scope. Do not demand a classical-limit discussion solely to make an advanced answer longer. Keep the separate causal-content concern open under A4. |
| 2 | adaptation-2fa418a5928a322a0d74 / A3 — quanta | fail → N/A | Prefer low's N/A. No quantitative/scaling result is requested by this identification question. A de Broglie calculation should not be imposed merely because the target is advanced. |
| 3 | adaptation-2fa418a5928a322a0d74 / A4 — quanta | fail → pass | Needs content confirmation. The phrase “so we expect them to behave like macroscopic particles” is a causal claim, not just the missing noun. The identification exception requires no unsupported/over-general claim, so low's pass cannot be accepted solely because “units of matter” is named. Check the premise and source context. |
| 4 | adaptation-81abcdbd27b56b1113d6 / B1 — EM radiation | pass → fail | Low's stated reason conflicts with B1: terms already in the question need no new definition unless a new technical meaning is introduced. However, the answer also adds “Maxwell's equations”, which deserves a separate unfamiliar-term check. Do not treat high's whole-answer pass as independently confirmed. |
| 5 | adaptation-81abcdbd27b56b1113d6 / B3 — EM radiation | pass → fail | Low overlooks the explicit example “Light is a form of EMR.” If concrete support is necessary, that example supports high's pass; if no additional support is necessary, N/A may be appropriate. The frozen rule does not justify fail just because no field analogy is added. Necessity calibration remains pending. |
| 6 | adaptation-87edb0405e75fa704503 / B3 — short periodic-motion answer | N/A → pass | Calibration item. The question already supplies a vibrating-guitar example, and the answer names the concept. Decide consistently whether the supplied situation satisfies an applicable B3 or makes extra support unnecessary. Do not force an additional analogy. |
| 7 | adaptation-87edb0405e75fa704503 / B4 — short periodic-motion answer | pass → N/A | Prefer high's pass. B4 explicitly says Always assess and permits clear ordinary language; “no formula required” is not a reason for N/A. |
| 8 | adaptation-8b127d8bb90e0690c4fd / I2 — quanta | pass → fail | Needs content confirmation for the added causal connection. The identification exception only applies when the identification has no unsupported claim. Do not decide this disputed physical premise just from matching the missing noun. |
| 9 | adaptation-8ff42a1699ae0f208a2c / B4 — convex lenses | N/A → pass | Prefer low's pass for B4. Formula-free ordinary language can satisfy the notation criterion. This does not settle the separate B1 issue of an unexplained word such as “convex”. |
| 10 | adaptation-9ac1884f150ad5b554ad / B1 — radiotherapy naming answer | fail → pass | High's concern is closer to the literal terminology rule: “radiation” is introduced without explaining its physical meaning. Low's causal restatement is not a definition of radiation. Whether the learner may treat this term as familiar needs content/level calibration; do not infer that permission from its familiarity to the reviewer. |
| 11 | adaptation-9ac1884f150ad5b554ad / B2 — radiotherapy | fail → pass | Prefer low for the requested task. The question supplies the causal premise and asks for the missing term, not an explanation of radiosensitivity. High demands an explanation beyond that naming task. |
| 12 | adaptation-9ac1884f150ad5b554ad / B3 — radiotherapy | fail → N/A | Low's N/A is more consistent with a direct factual completion if the supplied situation is sufficient. The need for extra concrete support must be determined before penalizing its absence; a new analogy is not automatically required. |
| 13 | adaptation-9ac1884f150ad5b554ad / B4 — radiotherapy | N/A → pass | Prefer low's pass. B4 remains applicable without formulas. Do not confuse terminology accessibility (B1) with notation accessibility (B4). |
| 14 | adaptation-a6f8d2d86b3c2a11e603 / A1 — pressure definition | pass → fail | Prefer high's pass. A definition is what the question asks for; answering it with one brief definition and P=F/A does not itself constitute teaching that obscures the requested answer. |
| 15 | adaptation-aed1aeb74cc009e69163 / A2 — radiotherapy | fail → N/A | Prefer low's N/A for this naming question. The requested missing word does not require a discussion of healthy-cell damage or a therapeutic model. This is task-scope analysis, not clinical validation of the premise. |
| 16 | adaptation-aed1aeb74cc009e69163 / A3 — radiotherapy | fail → N/A | Prefer low's N/A. Linear-quadratic or cell-repair models are not needed to identify the requested term. High's quantitative demand is beyond the frozen A3 usefulness rule. |
| 17 | adaptation-aed1aeb74cc009e69163 / A4 — radiotherapy | fail → pass | Low's pass is more consistent with the narrowly requested identification and the stated premise, provided the content owner accepts that premise. High's specialist caveats cannot alone establish that this naming answer is over-general. Do not generalize this to advice about treatment. |
| 18 | adaptation-b204abc160f8946f10ac / B3 — pressure | N/A → fail | Prefer high's N/A for this direct definition request. Low needs to establish why an additional concrete example is necessary; “pressure is abstract” alone does not establish that every naming answer needs an analogy. |
| 19 | adaptation-cb026500d8f093056d40 / A1 — short periodic-motion answer | fail → pass | Prefer low's pass. A concise direct answer to an explicit naming question is not redundant teaching merely because the concept is elementary. |
| 20 | adaptation-d067ade10e6d060d62aa / B2 — quanta | fail → pass | Needs content confirmation, for the same causal-premise concern as A4/I2. Low cannot treat a clear sentence as proof that the physical inference is valid. |
| 21 | adaptation-d067ade10e6d060d62aa / B3 — quanta | fail → N/A | Prefer N/A for extra examples in this identification task. The disputed inference needs content review under B2/A4; requiring an analogy is not a substitute for resolving it. |
| 22 | adaptation-d9aba666a3f847c49036 / I2 — pion | pass → fail | Needs the content owner's reference/premise review. High introduces “virtual particle” context not explicitly established by the question; low disputes the conservation claim. The project already flags this question as a reference concern. Do not force a score or silently correct Gold here. |
| 23 | adaptation-dd8e9943659cccb82422 / B3 — expanded periodic-motion answer | pass → N/A | Calibration item. The answer explicitly reuses the guitar-string situation. That can count as supplied concrete support if B3 is applicable; if no additional support is needed, N/A is plausible. The team needs one consistent applicability convention. |

### What this says about high versus low

There are clear rule-adherence concerns on both sides. High over-demands explanations in several naming questions. Low also returns N/A for an always-assessed criterion, overlooks concrete examples, or relies on a disputed premise. No overall “review accuracy” or win rate is calculated: the cases were selected because they disagree, judgments share answers/questions, and some decisions require content calibration.

## 2. Discrimination: all five level-prediction differences

The target generation level is hidden from the judge and is not a human-verified true writing level. A target/prediction mismatch does not by itself show judge error.

| Request | High → Low | Provisional finding |
| --- | --- | --- |
| discrimination-10eaf26afe0d6e71dcae — longitudinal wave | intermediate → beginner | High's intermediate is plausible: “direction of propagation” and “longitudinal” are used compactly. Low's “no equations therefore beginner” style of justification is insufficient under the profiles. The answer also describes the air motion, so beginner/intermediate overlap needs calibration rather than a forced definitive label. |
| discrimination-5e0bb728e7a01196741f — pion | uncertain → advanced | Prefer high's uncertainty over assigning advanced solely from sophisticated quantum terminology. The advanced profile is calculus-based introductory physics, not automatic quantum-field-theory knowledge. The questionable premise should be reviewed separately; it is not proof that high is the more accurate judge overall. |
| discrimination-6559f00a2739b29ebfa2 — black-hole tidal forces | intermediate → beginner | Intermediate is plausible because the answer adds a compact gravitational-gradient mechanism. However, several terms already occur in the question, so calling the whole answer inaccessible based on vocabulary alone would be too strong. Keep the label provisional. |
| discrimination-b24ce206d1caf3092a7b — cyclotron | intermediate → beginner | High's intermediate is better supported by the frozen prior: the new “magnetic field” term is not explained, and the beginner profile does not assume fields. Brevity and a one-sentence fact do not independently establish beginner fit. |
| discrimination-f3143ea5dce65fd8ae3c — ultrasound | intermediate → beginner | Neither rationale fully handles the unexplained specialist “piezoelectric transducer”. Low's claim of no advanced terminology is weak; high's assumption that all terms are standard introductory vocabulary is also insufficient. Uncertain/content-level calibration is safer than a forced label. |

The original warning remains: 7 answers target advanced, but high predicts advanced 0 times and low 1 time. This may involve generation style separation, overlapping global priors or judge behavior. These five selected differences cannot isolate the cause.

## 3. Correctness needs_review: sciq-train-05989

The candidate gives “nuclei” and then adds a statement about a mass number near 60. The exact Gold core evidence supplied to the correctness judge discusses binding-energy spikes and the missing term, but does not establish the A≈60 statement.

The existing prompt explicitly says to assess the entire candidate and to request review when an unlisted additional claim cannot be established from the supplied reference, rather than using unstated knowledge.

**Provisional finding:** high's needs_review follows the existing source-limited rule. Low's rationale appeals to factual knowledge outside the supplied core reference, so its automatic score should not be preferred solely because it completes more cases. A broader generation evidence bundle containing A≈60 is not automatically part of the correctness judge's allowed evidence.

**Action:** retain the pending state until the content owner confirms the extra claim or authorises an explicit reference/rubric update. No source, rubric or score was changed in this review.

## 4. Remaining invalid high evidence output: sciq-train-04946

The saved output declares supporting IDs E1 and E2 for one claim while supplying only the E1 quotation. Another excerpt contains wording that is not grounded as quoted in the named evidence.

**Action:** keep this original result unresolved. Do not delete it, manually invent an E2 quotation, or count it as a wrong generator answer. A later new judge execution can produce a separately recorded valid result; it must not erase the original failure history.

## 5. What a small low confirmation means

It is a bounded new-call check after the code repair, distinct from free replay. It is **not automatically another complete 20-cell high+low trial**, and it is not a replacement for content review.

A proposed minimal next scope is **evidence-support only, low only**, using the five unique affected request contexts plus one previously valid control (six answers total). This targets the actual quotation failure mode. It would not retest correctness, adaptation or discrimination, and therefore would not settle their semantic disagreements.

Before any execution, the exact contexts, application/SDK retry limits, maximum call allowance, output directory and cost assumptions must be written down and confirmed. All necessary quotations already exist in the saved material; this proposal is only for later fresh-output behavior, not for recovering the existing seven records.

**No command containing the paid opt-in was run or supplied as an instruction to execute here. No new API call or charge occurred.**

If the team instead wants to test all four tasks or a different coverage sample, that is a different scope and should be confirmed first. No silent switch to a full 20-cell retry is intended.

## 6. What can proceed now

- Completed for free: review notes for all 28 existing differences, the pending correctness item and the one remaining evidence failure.
- Still awaiting the team: approval of the quotation policy (including independent excerpts), B3 applicability calibration and specialist reference concerns.
- The user need not wait to read/review these notes while the Leader inspects #210.
- Fresh paid low confirmation is paused for explicit user initiation. Full Dev still requires the Leader's configuration/budget approval and the required validity decisions.
- Original scores, cached results, code, frozen profiles and human-approval records remain unchanged. These notes are published with PR #210 for confirmation; no completed team approval is claimed.
