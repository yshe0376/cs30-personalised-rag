# Perturbation v2: per-case review pending, not scored

This replaces the rejected repeated-template v1 draft. Eighteen distinct Dev questions
cover six targets and three generators. IDs are purposefully selected for coverage;
the sample is not random or representative. All difficulty labels are pre-run proposals.
Leader review must confirm the target violation, other-criterion effects and full-answer
consistency. A mechanical single-span check does not prove semantic isolation.
A saved baseline pass is a selection filter, not an independent physics endorsement.
External references below are review-only; never add them to the judge evidence bundle.
JSONL preserves the exact answer text; Markdown is a display of that record.

| Case | Generator | Question | Target | Domain | Proposed difficulty |
|---|---|---|---|---|---|
| perturb-v2-b1-gpt-oss | gpt-oss | sciq-train-05303 | B1 | fluid_transport | moderate |
| perturb-v2-b1-llama | llama | sciq-train-08318 | B1 | mechanics | subtle |
| perturb-v2-b1-gemma | gemma | sciq-train-01286 | B1 | electrostatics | clear |
| perturb-v2-b4-gpt-oss | gpt-oss | sciq-train-04113 | B4 | fluids | clear |
| perturb-v2-b4-llama | llama | sciq-train-01031 | B4 | thermodynamics | moderate |
| perturb-v2-b4-gemma | gemma | sciq-train-05470 | B4 | acoustics | subtle |
| perturb-v2-a1-gpt-oss | gpt-oss | sciq-train-02258 | A1 | magnetism | clear |
| perturb-v2-a1-llama | llama | sciq-train-06151 | A1 | circuits | moderate |
| perturb-v2-a1-gemma | gemma | sciq-train-06162 | A1 | gravitation | subtle |
| perturb-v2-i3-gpt-oss | gpt-oss | sciq-train-03171 | I3 | particle_physics | clear |
| perturb-v2-i3-llama | llama | sciq-train-04566 | I3 | gravitation | subtle |
| perturb-v2-i3-gemma | gemma | sciq-train-02662 | I3 | metrology | moderate |
| perturb-v2-correctness-gpt-oss | gpt-oss | sciq-train-07345 | correctness | atomic_physics | clear |
| perturb-v2-correctness-llama | llama | sciq-train-00580 | correctness | circuits | moderate |
| perturb-v2-correctness-gemma | gemma | sciq-train-09112 | correctness | optics | subtle |
| perturb-v2-evidence-support-gpt-oss | gpt-oss | sciq-train-01983 | evidence_support | acoustics | moderate |
| perturb-v2-evidence-support-llama | llama | sciq-train-07974 | evidence_support | nuclear_physics | subtle |
| perturb-v2-evidence-support-gemma | gemma | sciq-train-00362 | evidence_support | electrical_measurement | clear |

## perturb-v2-b1-gpt-oss

Question: How does sap get to the tops of tall trees?

Source: evaluation-d8c629c144cef8d5e503f547; beginner; P1R1_combined.

Frozen criterion: Explain each key unfamiliar physical term or specialised meaning at first use, or express it in understandable everyday language. Terms explicitly allowed by the beginner profile need no definition. Terms the question itself already uses also need no definition unless the answer gives them a new technical meaning. Always assess for a substantive answer. Pass with an exact answer quote showing accessible wording or the explanation; fail if necessary terminology remains unexplained.

Original answer:

> Sap rises because water molecules stick together (cohesion). When water evaporates in a leaf, it pulls the rest of the column of water upward, creating a negative pressure that lifts the sap through the xylem vessels. This pull can reach the heights needed for tall trees.

Perturbed candidate:

> Sap rises because cohesion maintains hydraulic continuity. When water evaporates in a leaf, it pulls the rest of the column of water upward, creating a negative pressure that lifts the sap through the xylem vessels. This pull can reach the heights needed for tall trees.

Controlled edit (one semantic target; repeated mentions may share one span):

```text
BEFORE: "water molecules stick together (cohesion)"
AFTER: "cohesion maintains hydraulic continuity"
```

Selection reason: Replace the real sap-transport explanation with unexplained hydraulic terminology while preserving the leaf-evaporation pulling mechanism.

Expected response (hypothesis): target criterion fail, not not_applicable

Proposed difficulty: moderate

Difficulty reason: The leaf-evaporation explanation remains readable, but the key cohesion explanation has become unexplained hydraulic terminology.

Proposed invariants (not human-confirmed):

- Leaf evaporation, the upward water-column pull and xylem transport remain unchanged.
- No numerical claim or extra physical mechanism is introduced.

Review focus: Confirm the replacement is physically accurate but inaccessible at the beginner prior; check whether the remaining water-column causal chain still meets B2. Reject if B2 also changes.

Leader checks:

- Intended target violation: **pending**.
- Other-criterion effects / physics preservation: **pending**.
- Full-answer internal consistency: **pending**.
- Difficulty label confirmation: **pending**.
- Accept / revise / reject and reason: **pending**.
- Reviewer, date and frozen sample hash: **pending**.


## perturb-v2-b1-llama

Question: What is the other name of newton’s first law?

Source: evaluation-c7807e5643a5695c9ef54c17; beginner; P1R0_prompt_only.

Frozen criterion: Explain each key unfamiliar physical term or specialised meaning at first use, or express it in understandable everyday language. Terms explicitly allowed by the beginner profile need no definition. Terms the question itself already uses also need no definition unless the answer gives them a new technical meaning. Always assess for a substantive answer. Pass with an exact answer quote showing accessible wording or the explanation; fail if necessary terminology remains unexplained.

Original answer:

> Newton's first law of motion is also known as the law of inertia. This means that an object at rest will remain at rest, and an object in motion will continue to move with a constant velocity, unless acted upon by an external force.

Perturbed candidate:

> Newton's first law of motion is also known as the law of inertia. An inertial state persists unless the resultant external force is nonzero.

Controlled edit (one semantic target; repeated mentions may share one span):

```text
BEFORE: "This means that an object at rest will remain at rest, and an object in motion will continue to move with a constant velocity, unless acted upon by an external force."
AFTER: "An inertial state persists unless the resultant external force is nonzero."
```

Selection reason: Keep the correct law name while replacing accessible physical wording with unexplained inertial-state/resultant terminology.

Expected response (hypothesis): target criterion fail, not not_applicable

Proposed difficulty: subtle

Difficulty reason: The formal Newton-law wording is scientifically credible; the gap is accessibility of inertial state and resultant, not a false conclusion.

Proposed invariants (not human-confirmed):

- The identification remains the law of inertia.
- The force-free motion claim is not reversed.

Review focus: Confirm the formal replacement is physically equivalent, genuinely unfamiliar under the beginner prior, and not adequately explained elsewhere.

Leader checks:

- Intended target violation: **pending**.
- Other-criterion effects / physics preservation: **pending**.
- Full-answer internal consistency: **pending**.
- Difficulty label confirmation: **pending**.
- Accept / revise / reject and reason: **pending**.
- Reviewer, date and frozen sample hash: **pending**.


## perturb-v2-b1-gemma

Question: Since the electric field lines point radially away from the charge, they are perpendicular to what?

Source: evaluation-8af395d4f3ca54b0eb1f0527; beginner; P1R0_prompt_only.

Frozen criterion: Explain each key unfamiliar physical term or specialised meaning at first use, or express it in understandable everyday language. Terms explicitly allowed by the beginner profile need no definition. Terms the question itself already uses also need no definition unless the answer gives them a new technical meaning. Always assess for a substantive answer. Pass with an exact answer quote showing accessible wording or the explanation; fail if necessary terminology remains unexplained.

Original answer:

> Electric field lines radiate away from a positive charge. Equipotential lines are lines where the electric potential is constant. The evidence states that electric field lines are perpendicular to equipotential lines.

Perturbed candidate:

> Electric field lines radiate away from a positive charge. The evidence states that electric field lines are perpendicular to equipotential lines.

Controlled edit (one semantic target; repeated mentions may share one span):

```text
BEFORE: " Equipotential lines are lines where the electric potential is constant."
AFTER: ""
```

Selection reason: Delete the subject-specific definition of the requested object; retain the perpendicularity statement.

Expected response (hypothesis): target criterion fail, not not_applicable

Proposed difficulty: clear

Difficulty reason: The only standalone definition of the requested equipotential lines is removed.

Proposed invariants (not human-confirmed):

- The field-line direction and named equipotential lines are unchanged.
- No mathematical notation or numerical claim is introduced.

Review focus: Confirm the question does not already explain equipotential; judge the term gap rather than brevity alone.

Leader checks:

- Intended target violation: **pending**.
- Other-criterion effects / physics preservation: **pending**.
- Full-answer internal consistency: **pending**.
- Difficulty label confirmation: **pending**.
- Accept / revise / reject and reason: **pending**.
- Reviewer, date and frozen sample hash: **pending**.


## perturb-v2-b4-gpt-oss

Question: What is defined as force per unit area?

Source: evaluation-743a8ad9b62221dba6cbf9b5; beginner; P0R1_reranking_only.

Frozen criterion: Keep formulas and notation within the beginner prior or explain any indispensable extension, its symbols, and why it applies. Always assess: clear ordinary-language reasoning can pass with a quote and does not require a formula. Unexplained advanced notation fails even in a qualitative question. Formula presence or absence alone is not the decision rule.

Original answer:

> Force per unit area is defined as pressure, which is the force divided by the area over which it is applied.

Perturbed candidate:

> Force per unit area is defined as pressure, which is the force divided by the area over which it is applied. Locally, \(p=\mathrm{d}F_\perp/\mathrm{d}A\).

Controlled edit (one semantic target; repeated mentions may share one span):

```text
BEFORE: ""
AFTER: " Locally, \\(p=\\mathrm{d}F_\\perp/\\mathrm{d}A\\)."
```

Selection reason: Add a legitimate local pressure relation using calculus and a normal-force subscript without explaining them to a beginner.

Expected response (hypothesis): target criterion fail, not not_applicable

Proposed difficulty: clear

Difficulty reason: The added differential and normal-force notation clearly exceeds the beginner mathematics prior.

Proposed invariants (not human-confirmed):

- Original force-per-area explanation is unchanged.
- The local-pressure qualification avoids confusing an average with a spatially varying local value.

Review focus: Confirm B4 fails for unexplained differential/subscript notation, not simply because an equation is present.

External physics references (review-only, not judge evidence):

- [Review-only physics check of local p=dF/dA; never add this page to the judge evidence.](https://openstax.org/books/university-physics-volume-1/pages/14-1-fluids-density-and-pressure)

Leader checks:

- Intended target violation: **pending**.
- Other-criterion effects / physics preservation: **pending**.
- Full-answer internal consistency: **pending**.
- Difficulty label confirmation: **pending**.
- Accept / revise / reject and reason: **pending**.
- Reviewer, date and frozen sample hash: **pending**.


## perturb-v2-b4-llama

Question: What is the pressure of gas in a gas mixture termed?

Source: evaluation-feab248764e2ec76f140eed2; beginner; P1R1_combined.

Frozen criterion: Keep formulas and notation within the beginner prior or explain any indispensable extension, its symbols, and why it applies. Always assess: clear ordinary-language reasoning can pass with a quote and does not require a formula. Unexplained advanced notation fails even in a qualitative question. Formula presence or absence alone is not the decision rule.

Original answer:

> The pressure of gas in a gas mixture is termed partial pressure. It is the pressure a gas would create if it occupied the total volume available. In a mixture of gases, the total pressure is the sum of partial pressures of the component gases, assuming ideal gas behavior and no chemical reactions between the components.

Perturbed candidate:

> The pressure of gas in a gas mixture is termed partial pressure. It is the pressure a gas would create if it occupied the total volume available. For a nonreacting ideal-gas mixture, \(p_{\mathrm{tot}}=\sum_{i=1}^{n}p_i\).

Controlled edit (one semantic target; repeated mentions may share one span):

```text
BEFORE: "In a mixture of gases, the total pressure is the sum of partial pressures of the component gases, assuming ideal gas behavior and no chemical reactions between the components."
AFTER: "For a nonreacting ideal-gas mixture, \\(p_{\\mathrm{tot}}=\\sum_{i=1}^{n}p_i\\)."
```

Selection reason: Express the same qualified pressure-sum relationship with summation indices that the beginner prior does not include.

Expected response (hypothesis): target criterion fail, not not_applicable

Proposed difficulty: moderate

Difficulty reason: The ideal-mixture relation is correct and contextual, but the sigma operator and indices are not explained.

Proposed invariants (not human-confirmed):

- The definition of partial pressure stays intact.
- The ideal-gas and nonreacting qualifications are retained.

Review focus: Confirm the notation is not already explained by the remaining sentences; check the equation preserves the physical relationship.

Leader checks:

- Intended target violation: **pending**.
- Other-criterion effects / physics preservation: **pending**.
- Full-answer internal consistency: **pending**.
- Difficulty label confirmation: **pending**.
- Accept / revise / reject and reason: **pending**.
- Reviewer, date and frozen sample hash: **pending**.


## perturb-v2-b4-gemma

Question: What is the measure of sound intensity levels?

Source: evaluation-ece46aa5cb829c6d1dadb739; beginner; P0R0_plain.

Frozen criterion: Keep formulas and notation within the beginner prior or explain any indispensable extension, its symbols, and why it applies. Always assess: clear ordinary-language reasoning can pass with a quote and does not require a formula. Unexplained advanced notation fails even in a qualitative question. Formula presence or absence alone is not the decision rule.

Original answer:

> Sound intensity levels are measured in decibels (dB). The decibel scale is logarithmic and better reflects how humans perceive sound compared to intensity in watts per meter squared. The evidence states, 'sound intensity levels in decibels fit your experience better than intensities in watts per meter squared.'

Perturbed candidate:

> Sound intensity levels are measured in decibels (dB). The decibel scale is logarithmic and better reflects how humans perceive sound compared to intensity in watts per meter squared. The evidence states, 'sound intensity levels in decibels fit your experience better than intensities in watts per meter squared.' Quantitatively, \(\beta=10\log_{10}(I/I_0)\).

Controlled edit (one semantic target; repeated mentions may share one span):

```text
BEFORE: ""
AFTER: " Quantitatively, \\(\\beta=10\\log_{10}(I/I_0)\\)."
```

Selection reason: Introduce the real decibel relation without defining beta, the reference intensity or the logarithm.

Expected response (hypothesis): target criterion fail, not not_applicable

Proposed difficulty: subtle

Difficulty reason: The prose already names a logarithmic scale, so detecting the still-unexplained reference intensity and symbols requires reading beyond formula presence.

Proposed invariants (not human-confirmed):

- The requested decibel unit and original factual statements remain unchanged.
- The logarithm is dimensionless because it is an intensity ratio.

Review focus: Confirm B4 needs the missing notation/symbol explanations; keep correctness separate from beginner accessibility.

External physics references (review-only, not judge evidence):

- [Review-only check of the sound-level relation.](https://openstax.org/books/college-physics-2e/pages/17-3-sound-intensity-and-sound-level)

Leader checks:

- Intended target violation: **pending**.
- Other-criterion effects / physics preservation: **pending**.
- Full-answer internal consistency: **pending**.
- Difficulty label confirmation: **pending**.
- Accept / revise / reject and reason: **pending**.
- Reviewer, date and frozen sample hash: **pending**.


## perturb-v2-a1-gpt-oss

Question: Magnetic force is always perpendicular to what?

Source: evaluation-c74671c78a3c07841e7f1cfa; advanced; P0R0_plain.

Frozen criterion: Avoid redundant teaching of mastered introductory definitions or routine operations that obscures the requested argument. Brief reminders needed to remove ambiguity are acceptable. Always assess substantive answers. Judge the function of the explanation under the advanced prior, not word count, brevity alone, or the presence of everyday language.

Original answer:

> The magnetic force on a moving charge is always perpendicular to the velocity of the charge (and also perpendicular to the magnetic field).

Perturbed candidate:

> Velocity is a vector quantity: it has a size and a direction. The size is the speed, while the direction describes where the charge is moving. A force is also a vector, so its direction can be discussed separately from its size. Perpendicular directions meet at a right angle, which is an angle of ninety degrees. The magnetic force on a moving charge is always perpendicular to the velocity of the charge (and also perpendicular to the magnetic field).

Controlled edit (one semantic target; repeated mentions may share one span):

```text
BEFORE: ""
AFTER: "Velocity is a vector quantity: it has a size and a direction. The size is the speed, while the direction describes where the charge is moving. A force is also a vector, so its direction can be discussed separately from its size. Perpendicular directions meet at a right angle, which is an angle of ninety degrees. "
```

Selection reason: Delay a compact magnetic-force identification with elementary vector/angle definitions already mastered by the advanced prior.

Expected response (hypothesis): target criterion fail, not not_applicable

Proposed difficulty: clear

Difficulty reason: Four elementary vector/angle definitions precede a one-sentence identification.

Proposed invariants (not human-confirmed):

- The original perpendicularity conclusion is preserved verbatim.
- Every inserted definition is physically correct and on topic.

Review focus: Confirm the preface obscures the requested identification rather than resolving a genuine ambiguity; word count alone is not failure.

Leader checks:

- Intended target violation: **pending**.
- Other-criterion effects / physics preservation: **pending**.
- Full-answer internal consistency: **pending**.
- Difficulty label confirmation: **pending**.
- Accept / revise / reject and reason: **pending**.
- Reviewer, date and frozen sample hash: **pending**.


## perturb-v2-a1-llama

Question: Kirchhoff’s second rule (the loop rule) is an application of conservation of what?

Source: evaluation-c1823640473d2831e5dceeae; advanced; P0R0_plain.

Frozen criterion: Avoid redundant teaching of mastered introductory definitions or routine operations that obscures the requested argument. Brief reminders needed to remove ambiguity are acceptable. Always assess substantive answers. Judge the function of the explanation under the advanced prior, not word count, brevity alone, or the presence of everyday language.

Original answer:

> Kirchhoff's second rule is an application of conservation of energy.

Perturbed candidate:

> Kirchhoff's second rule (a circuit is a connected path through which electric charge can move; current is the rate of charge flow; voltage is energy transferred per unit charge; charge is measured in coulombs, current in amperes, and voltage in volts; tracing a closed loop means following connected components back to the starting point) is an application of conservation of energy.

Controlled edit (one semantic target; repeated mentions may share one span):

```text
BEFORE: "Kirchhoff's second rule"
AFTER: "Kirchhoff's second rule (a circuit is a connected path through which electric charge can move; current is the rate of charge flow; voltage is energy transferred per unit charge; charge is measured in coulombs, current in amperes, and voltage in volts; tracing a closed loop means following connected components back to the starting point)"
```

Selection reason: Place a circuit-specific elementary tutorial inside the short answer instead of appending a generic arithmetic paragraph.

Expected response (hypothesis): target criterion fail, not not_applicable

Proposed difficulty: moderate

Difficulty reason: The circuit definitions are on topic but interrupt the requested conservation-law identification inside a parenthesis.

Proposed invariants (not human-confirmed):

- The answer still names conservation of energy.
- No conservation law, sign, unit or requested circuit conclusion is changed.

Review focus: Confirm these mastered definitions obstruct the answer and are not needed to remove an ambiguity; inspect A4 for any unintended physical overstatement.

Leader checks:

- Intended target violation: **pending**.
- Other-criterion effects / physics preservation: **pending**.
- Full-answer internal consistency: **pending**.
- Difficulty label confirmation: **pending**.
- Accept / revise / reject and reason: **pending**.
- Reviewer, date and frozen sample hash: **pending**.


## perturb-v2-a1-gemma

Question: If a ball is released from rest when air resistance is negligible, velocity is seen to increase linearly, while what related property is a constant?

Source: evaluation-713300fdaee8fdbc04c92e3e; advanced; P1R0_prompt_only.

Frozen criterion: Avoid redundant teaching of mastered introductory definitions or routine operations that obscures the requested argument. Brief reminders needed to remove ambiguity are acceptable. Always assess substantive answers. Judge the function of the explanation under the advanced prior, not word count, brevity alone, or the presence of everyday language.

Original answer:

> When air resistance is negligible, the acceleration due to gravity is constant. This means that the velocity increases linearly with time, while the acceleration remains constant. This is experimentally verified and described in the provided evidence (E1, E2, E4).

Perturbed candidate:

> When air resistance is negligible, the acceleration due to gravity is constant. This means that the velocity increases linearly with time, while the acceleration remains constant. This is experimentally verified and described in the provided evidence (E1, E2, E4). Acceleration means the rate at which velocity changes. A change in velocity is obtained by subtracting the initial velocity from the final velocity. Dividing that change by the elapsed time gives the average acceleration. In the constant-acceleration fall described here, equal time intervals give equal velocity increases, so each interval gives the same ratio. This repeats the same constant gravitational acceleration identified above.

Controlled edit (one semantic target; repeated mentions may share one span):

```text
BEFORE: ""
AFTER: " Acceleration means the rate at which velocity changes. A change in velocity is obtained by subtracting the initial velocity from the final velocity. Dividing that change by the elapsed time gives the average acceleration. In the constant-acceleration fall described here, equal time intervals give equal velocity increases, so each interval gives the same ratio. This repeats the same constant gravitational acceleration identified above."
```

Selection reason: Repeat elementary acceleration operations in the actual falling-ball context; no unrelated sum or multiplication example is used.

Expected response (hypothesis): target criterion fail, not not_applicable

Proposed difficulty: subtle

Difficulty reason: The velocity-difference walkthrough resembles a helpful explanation; the intended issue is repetition of mastered steps, which requires explicit human confirmation.

Proposed invariants (not human-confirmed):

- The original constant-g conclusion and negligible-air-resistance setting are unchanged.
- The added average-acceleration statements are restricted to the constant-acceleration case.

Review focus: Confirm this walkthrough is redundant under the advanced prior rather than a useful brief explanation of the requested relationship.

Leader checks:

- Intended target violation: **pending**.
- Other-criterion effects / physics preservation: **pending**.
- Full-answer internal consistency: **pending**.
- Difficulty label confirmation: **pending**.
- Accept / revise / reject and reason: **pending**.
- Reviewer, date and frozen sample hash: **pending**.


## perturb-v2-i3-gpt-oss

Question: Quantum chromodynamics combines what property with quark theory?

Source: evaluation-f20c8c4db3c7925107ccbc45; intermediate; P0R0_plain.

Frozen criterion: Use course terminology accurately and explain unfamiliar specialist ideas while avoiding redundant redefinitions of the intermediate assumed core. A brief clarification that resolves a real ambiguity is helpful, not redundant. Always assess substantive answers. Judge conceptual role and precision, not terminology count or answer length.

Original answer:

> Quantum chromodynamics is the theory that combines quark theory with the property of color, the quantum number that explains the strong force between quarks.

Perturbed candidate:

> Quantum chromodynamics is the theory that combines quark theory with the property of color.

Controlled edit (one semantic target; repeated mentions may share one span):

```text
BEFORE: ", the quantum number that explains the strong force between quarks"
AFTER: ""
```

Selection reason: Leave the correct color answer but remove the explanation distinguishing the specialist quantum property from ordinary visual color.

Expected response (hypothesis): target criterion fail, not not_applicable

Proposed difficulty: clear

Difficulty reason: The specialist meaning distinguishing quantum color from visual color is deleted.

Proposed invariants (not human-confirmed):

- The requested property remains color.
- No QCD mechanism or factual alternative is introduced.

Review focus: Confirm the removed explanation is necessary under the intermediate prior and that name-only I1/I2 requirements still hold.

Leader checks:

- Intended target violation: **pending**.
- Other-criterion effects / physics preservation: **pending**.
- Full-answer internal consistency: **pending**.
- Difficulty label confirmation: **pending**.
- Accept / revise / reject and reason: **pending**.
- Reviewer, date and frozen sample hash: **pending**.


## perturb-v2-i3-llama

Question: Light from a distant galaxy can travel different paths to the earth because it is bent around an intermediary galaxy by what?

Source: evaluation-86e19a783a40ff9c63a04c0f; intermediate; P1R0_prompt_only.

Frozen criterion: Use course terminology accurately and explain unfamiliar specialist ideas while avoiding redundant redefinitions of the intermediate assumed core. A brief clarification that resolves a real ambiguity is helpful, not redundant. Always assess substantive answers. Judge conceptual role and precision, not terminology count or answer length.

Original answer:

> The governing principle is gravitational lensing, which is the bending of light around an intermediary galaxy due to gravity. This produces several images of the more distant galaxy, as seen in Figure 34.12. The evidence from OpenStax College Physics 2e and OpenStax College Physics AP 2e supports this principle, with observations of gravitational lensing and its verification of general relativity.

Perturbed candidate:

> The governing principle is gravitational lensing, described by null geodesics of the curved spacetime geometry. This produces several images of the more distant galaxy, as seen in Figure 34.12. The evidence from OpenStax College Physics 2e and OpenStax College Physics AP 2e supports this principle, with observations of gravitational lensing and its verification of general relativity.

Controlled edit (one semantic target; repeated mentions may share one span):

```text
BEFORE: "gravitational lensing, which is the bending of light around an intermediary galaxy due to gravity"
AFTER: "gravitational lensing, described by null geodesics of the curved spacetime geometry"
```

Selection reason: Replace a plain lensing explanation with physically relevant specialist terminology beyond the algebra-based introductory prior.

Expected response (hypothesis): target criterion fail, not not_applicable

Proposed difficulty: subtle

Difficulty reason: The replacement is a credible general-relativistic account, but null geodesics lie outside the intermediate prior and are not explained.

Proposed invariants (not human-confirmed):

- The phenomenon remains gravitational lensing.
- The multiple-image observation and source references remain unchanged.

Review focus: Confirm the model wording is accurate and unexplained; judge the unfamiliar concepts, not the number of technical terms.

Leader checks:

- Intended target violation: **pending**.
- Other-criterion effects / physics preservation: **pending**.
- Full-answer internal consistency: **pending**.
- Difficulty label confirmation: **pending**.
- Accept / revise / reject and reason: **pending**.
- Reviewer, date and frozen sample hash: **pending**.


## perturb-v2-i3-gemma

Question: The fundamental unit of time, the second, is based on what type of clock?

Source: evaluation-2323257417220cb419801c2c; intermediate; P0R0_plain.

Frozen criterion: Use course terminology accurately and explain unfamiliar specialist ideas while avoiding redundant redefinitions of the intermediate assumed core. A brief clarification that resolves a real ambiguity is helpful, not redundant. Always assess substantive answers. Judge conceptual role and precision, not terminology count or answer length.

Original answer:

> The fundamental unit of time, the second, is now defined based on the vibrations of Cesium atoms. Specifically, it is defined as the time required for 9,192,631,770 Cesium atom vibrations.

Perturbed candidate:

> The fundamental unit of time, the second, is now defined based on the vibrations of Cesium atoms. Specifically, it is defined as the time required for 9,192,631,770 Cesium atom vibrations. Frequency means the number of repetitions per second. A hertz is one repetition per second, and a period is the time occupied by one repetition. Counting more repetitions in the same second means a higher frequency, while taking more time for one repetition means a longer period. Thus cycles per second and seconds per cycle describe the same repeated clock process from opposite sides.

Controlled edit (one semantic target; repeated mentions may share one span):

```text
BEFORE: ""
AFTER: " Frequency means the number of repetitions per second. A hertz is one repetition per second, and a period is the time occupied by one repetition. Counting more repetitions in the same second means a higher frequency, while taking more time for one repetition means a longer period. Thus cycles per second and seconds per cycle describe the same repeated clock process from opposite sides."
```

Selection reason: Add a clock-specific introductory frequency/period tutorial that repeats knowledge explicitly allowed by the intermediate prior.

Expected response (hypothesis): target criterion fail, not not_applicable

Proposed difficulty: moderate

Difficulty reason: Frequency/period reminders relate to the atomic clock, but repeat introductory concepts already mastered at intermediate level.

Proposed invariants (not human-confirmed):

- The atomic-clock answer and exact reference count remain unchanged.
- The added frequency/period statements are true; no new specialist mechanism is assumed.

Review focus: Confirm these frequency/period reminders are redundant for the intermediate prior rather than necessary to explain the atomic-clock reference; reject the draft if they resolve a real ambiguity.

Leader checks:

- Intended target violation: **pending**.
- Other-criterion effects / physics preservation: **pending**.
- Full-answer internal consistency: **pending**.
- Difficulty label confirmation: **pending**.
- Accept / revise / reject and reason: **pending**.
- Reviewer, date and frozen sample hash: **pending**.


## perturb-v2-correctness-gpt-oss

Question: All carbon atoms have how many protons?

Source: evaluation-de142d318f71dc05242a2c50; beginner; P0R0_plain.

Frozen criterion: Existing correctness rubric / supplied-evidence support definition.

Original answer:

> All carbon atoms have an atomic number of 6, which means each carbon nucleus contains 6 protons.

Perturbed candidate:

> All carbon atoms have an atomic number of 7, which means each carbon nucleus contains 7 protons.

Controlled edit (one semantic target; repeated mentions may share one span):

```text
BEFORE: "6, which means each carbon nucleus contains 6"
AFTER: "7, which means each carbon nucleus contains 7"
```

Selection reason: Change one atomic-number fact consistently in both mentions so no correct six-proton answer remains as an easy contradiction cue.

Expected response (hypothesis): not fully correct under the existing rubric (score below 2)

Proposed difficulty: clear

Difficulty reason: A single element fact is wrong in both mentions, so the judge must check proton count rather than detect internal inconsistency.

Proposed invariants (not human-confirmed):

- The same element and all surrounding wording remain unchanged.
- Both repeated mentions of the single incorrect fact are updated together.

Review focus: The intended error is the proton count, not answer self-contradiction. Confirm the rubric judges this key fact as wrong.

Leader checks:

- Intended target violation: **pending**.
- Other-criterion effects / physics preservation: **pending**.
- Full-answer internal consistency: **pending**.
- Difficulty label confirmation: **pending**.
- Accept / revise / reject and reason: **pending**.
- Reviewer, date and frozen sample hash: **pending**.


## perturb-v2-correctness-llama

Question: Positive charges move in the direction of the electric field and the same direction as what current?

Source: evaluation-a0de4f30b65e12bae092f797; intermediate; P0R0_plain.

Frozen criterion: Existing correctness rubric / supplied-evidence support definition.

Original answer:

> Positive charges move in the direction of the electric field and the same direction as conventional current.

Perturbed candidate:

> Positive charges move in the direction of the electric field and the opposite direction to conventional current.

Controlled edit (one semantic target; repeated mentions may share one span):

```text
BEFORE: "the same direction as conventional current"
AFTER: "the opposite direction to conventional current"
```

Selection reason: Introduce a realistic sign/direction error while retaining one internally consistent statement.

Expected response (hypothesis): not fully correct under the existing rubric (score below 2)

Proposed difficulty: moderate

Difficulty reason: A single direction word reverses the relation between positive charge motion and conventional current.

Proposed invariants (not human-confirmed):

- The charge is still positive and the electric-field clause is untouched.
- No correct alternative current direction appears elsewhere in the answer.

Review focus: Check the entire answer, not only the edited phrase, for a surviving correct alternative or changed charge sign.

Leader checks:

- Intended target violation: **pending**.
- Other-criterion effects / physics preservation: **pending**.
- Full-answer internal consistency: **pending**.
- Difficulty label confirmation: **pending**.
- Accept / revise / reject and reason: **pending**.
- Reviewer, date and frozen sample hash: **pending**.


## perturb-v2-correctness-gemma

Question: What is defined as the spreading of white light into its full spectrum of wavelengths?

Source: evaluation-91c23e61510112874179de4a; advanced; P0R0_plain.

Frozen criterion: Existing correctness rubric / supplied-evidence support definition.

Original answer:

> Dispersion is defined as the spreading of white light into its full spectrum of wavelengths.

Perturbed candidate:

> Diffraction is defined as the spreading of white light into its full spectrum of wavelengths.

Controlled edit (one semantic target; repeated mentions may share one span):

```text
BEFORE: "Dispersion"
AFTER: "Diffraction"
```

Selection reason: Substitute a plausible neighboring optics concept in a one-sentence definition; remove the old velocity/acceleration self-contradiction problem.

Expected response (hypothesis): not fully correct under the existing rubric (score below 2)

Proposed difficulty: subtle

Difficulty reason: Diffraction is a plausible neighboring optics term and the one-sentence answer contains no surviving correct alternative.

Proposed invariants (not human-confirmed):

- The white-light/spectrum description remains unchanged.
- No later sentence restores dispersion or supplies the correct alternative.

Review focus: Confirm the term substitution changes the required physical concept and does not rely on a contradictory second sentence.

Leader checks:

- Intended target violation: **pending**.
- Other-criterion effects / physics preservation: **pending**.
- Full-answer internal consistency: **pending**.
- Difficulty label confirmation: **pending**.
- Accept / revise / reject and reason: **pending**.
- Reviewer, date and frozen sample hash: **pending**.


## perturb-v2-evidence-support-gpt-oss

Question: The wave on a guitar string is transverse. the sound wave rattles a sheet of paper in a direction that shows the sound wave is what?

Source: evaluation-8c33b99135907f94ac3e74d2; advanced; P0R0_plain.

Frozen criterion: Existing correctness rubric / supplied-evidence support definition.

Original answer:

> The sheet of paper rattle shows the sound wave moves the air in the direction of propagation, indicating a longitudinal wave.

Perturbed candidate:

> The sheet of paper rattle shows the sound wave, travelling through dry air at 20 degrees Celsius at approximately 343 m/s, moves the air in the direction of propagation, indicating a longitudinal wave.

Controlled edit (one semantic target; repeated mentions may share one span):

```text
BEFORE: "the sound wave moves"
AFTER: "the sound wave, travelling through dry air at 20 degrees Celsius at approximately 343 m/s, moves"
```

Selection reason: Embed a plausible quantitative sound claim in the actual wave explanation; the supplied passages describe wave type but not this temperature-specific speed.

Expected response (hypothesis): the added factual subclaim has bundle_support unsupported

Proposed difficulty: moderate

Difficulty reason: A plausible temperature-specific speed is embedded in the supported wave explanation; source presence must be checked separately from scientific truth.

Proposed invariants (not human-confirmed):

- The longitudinal classification and paper-motion reasoning remain unchanged.
- The added value is physically reasonable under its explicit air/temperature conditions.

Review focus: Read every supplied passage; identify whether any directly supports or derives 343 m/s at 20 C. External correctness must not count as bundle support.

Evidence actually supplied to generation:

- ID: openstax_college_physics_2e__89ad46e1222dbb4a__16__e924c191__01089

> [FIGURE DESCRIPTION: The figure shows a guitar connected to an amplifier and a man holding a sheet of paper facing the speaker attached to the amplifier. The strings of the guitar when played cause transverse waves. On the other hand, the sound of the guitar creates ripples on the sheet of paper causing it to rattle in a direction that shows that the sound waves are longitudinal.]
>
> FIGURE 16.31 The wave on a guitar string is transverse. The sound wave rattles a sheet of paper in a direction that shows the sound wave is longitudinal.
>
> Earthquake waves under Earth’s surface also have both longitudinal and transverse components (called compressional or P-waves and shear or S-waves, respectively). These components have important individual characteristics—they propagate at different speeds, for example. Earthquakes also have surface waves that are similar to surface waves on water.

- ID: openstax_college_physics_ap_2e__919d8eba53f94d04__16__e924c191__01072

> [FIGURE DESCRIPTION: The figure shows a guitar connected to an amplifier and a man holding a sheet of paper facing the speaker attached to the amplifier. The strings of the guitar when played cause transverse waves. On the other hand, the sound of the guitar creates ripples on the sheet of paper causing it to rattle in a direction that shows that the sound waves are longitudinal.]
>
> FIGURE 16.31 The wave on a guitar string is transverse. The sound wave rattles a sheet of paper in a direction that shows the sound wave is longitudinal.
>
> Earthquake waves under Earth’s surface also have both longitudinal and transverse components (called compressional or P-waves and shear or S-waves, respectively). These components have important individual characteristics—they propagate at different speeds, for example. Earthquakes also have surface waves that are similar to surface waves on water.

- ID: openstax_physics__68184df67ec9780c__13__e924c191__00622

> Longitudinal waves are sometimes called compression waves or compressional waves, and transverse waves are sometimes called shear waves.
>
> Waves may be transverse, longitudinal, or a combination of the two. The waves on the strings of musical instruments are transverse (as shown in Figure 13.5 ), and so are electromagnetic waves, such as visible light. Sound waves in air and water are longitudinal. Their disturbances are periodic variations in pressure that are transmitted in fluids.
>
> [FIGURE DESCRIPTION: A guitar string is disturbed vertically but travels horizontally. Sound travels from the guitar, through an amplifier, out of a speaker, and to a piece of paper, which vibrates back and forth with the waves of compression.]
>
> FIGURE 13.5 The wave on a guitar string is transverse. However, the sound wave coming out of a speaker rattles a sheet of paper in a direction that shows that such sound wave is longitudinal.
>
> Sound in solids can be both longitudinal and transverse. Essentially, water waves are also a combination of transverse and longitudinal components, although the simplified water wave illustrated in Figure 13.2 does not show the longitudinal motion of the bird.
>
> Earthquake waves under Earth’s surface have both longitudinal and transverse components as well. The longitudinal
>
> waves in an earthquake are called pressure or P-waves, and the transverse waves are called shear or S-waves. These components have important individual characteristics; for example, they propagate at different speeds. Earthquakes also have surface waves that are similar to surface waves on water.

- ID: ck12_peoples_physics_concepts__d976bbd43160dfdf__11__e924c191__00106

> In transverse waves, the vibrations of the medium are perpendicular to the direction of motion. A classic example is a wave created in a long rope: the wave travels from one end of the rope to the other, but the actual rope moves up and down, and not from left to right as the wave does. Water waves act as a mix of longitudinal and transverse waves. A typical water molecule pretty much moves in a circle when a wave passes through it.
>
> Most wave media act like a series of connected oscillators. For instance, a rope can be thought of as a large number of masses (molecules) connected by springs (intermolecular forces). The speed of a wave through connected harmonic oscillators depends on the distance between them, the spring constant, and the mass. In this way, we can model wave media using the principles of simple harmonic motion. The speed of a wave on a string depends on the material the string is made of, as well as the tension in the string. This fact is why tightening a string on your violin or guitar will increase the frequency, or pitch, of the sound it produces.

- ID: openstax_physics__68184df67ec9780c__14__e924c191__00659

> , and some of the energy is converted to thermal energy in the air.
>
> Figure 14.4
>
> shows a graph of gauge pressure versus distance from the vibrating string. From this figure, you can see that the compression of a longitudinal wave is analogous to the peak of a transverse wave, and the rarefaction of a longitudinal wave is analogous to the trough of a transverse wave. Just as a transverse wave alternates between peaks and troughs, a longitudinal wave alternates between compression and rarefaction.
>
> [FIGURE DESCRIPTION: A sound wave with areas of alternating compression and rarefaction enter an ear canal and eardrum.]
>
> FIGURE 14.5 Sound wave compressions and rarefactions travel up the ear canal and force the eardrum to vibrate. There is a net force on the eardrum, since the sound wave pressures differ from the atmospheric pressure found behind the eardrum. A complicated mechanism converts the vibrations to nerve impulses, which are then interpreted by the brain.


External physics references (review-only, not judge evidence):

- [Review-only fact check; do not add this outside passage to the scoring bundle.](https://openstax.org/books/college-physics-ap-courses/pages/17-2-speed-of-sound-frequency-and-wavelength)

Leader checks:

- Intended target violation: **pending**.
- Other-criterion effects / physics preservation: **pending**.
- Full-answer internal consistency: **pending**.
- Difficulty label confirmation: **pending**.
- Accept / revise / reject and reason: **pending**.
- Reviewer, date and frozen sample hash: **pending**.


## perturb-v2-evidence-support-llama

Question: What process is the opposite of fusion and releases energy only when heavy nuclei are split?

Source: evaluation-14e73d4cb0cf3c91416902c7; advanced; P0R0_plain.

Frozen criterion: Existing correctness rubric / supplied-evidence support definition.

Original answer:

> Fission is the process in which a heavy nucleus is split into two or more smaller nuclei, releasing energy in the process. This is the opposite of fusion, where two or more smaller nuclei combine to form a single, heavier nucleus.

Perturbed candidate:

> Fission is the process in which a heavy nucleus is split into two or more smaller nuclei, releasing energy in the process. Some neutrons are emitted after the split when radioactive fission products decay, rather than being emitted immediately in the splitting event. This is the opposite of fusion, where two or more smaller nuclei combine to form a single, heavier nucleus.

Controlled edit (one semantic target; repeated mentions may share one span):

```text
BEFORE: " This is the opposite of fusion"
AFTER: " Some neutrons are emitted after the split when radioactive fission products decay, rather than being emitted immediately in the splitting event. This is the opposite of fusion"
```

Selection reason: Add a relevant neutron-emission mechanism that is not established by the supplied introductory fission/fusion and decay passages.

Expected response (hypothesis): the added factual subclaim has bundle_support unsupported

Proposed difficulty: subtle

Difficulty reason: The passages mention neutron production and radioactive decay separately, which can tempt an unwarranted inference to the added delayed-neutron mechanism.

Proposed invariants (not human-confirmed):

- The original fission/fusion definitions are preserved.
- The new delayed-neutron statement is true, rather than an intentionally false nuclear claim.

Review focus: The bundle mentions neutrons and decay separately; check whether it actually supports delayed-neutron emission from fission products, rather than inferring the mechanism from outside knowledge.

Evidence actually supplied to generation:

- ID: openstax_college_physics_2e__89ad46e1222dbb4a__32__e924c191__02246

> • Define nuclear fission.
>
> • Discuss how fission fuel reacts and describe what it produces.
>
> • Describe controlled and uncontrolled chain reactions.
>
> Nuclear fission is a reaction in which a nucleus is split (or fissured). Controlled fission is a reality, whereas controlled fusion is a hope for the future. Hundreds of nuclear fission power plants around the world attest to the fact that controlled fission is practical and, at least in the short term, economical, as seen in Figure 32.20. Whereas nuclear power was of little interest for decades following TMI and Chernobyl (and now Fukushima Daiichi), growing concerns over global warming has brought nuclear power back on the table as a viable energy alternative. By the end of 2009, there were 442 reactors operating in 30 countries, providing 15% of the world’s electricity. France provides over 75% of its electricity with nuclear power, while the US has 104 operating reactors providing 20% of its electricity. Australia and New Zealand have none. China is building nuclear power plants at the rate of one start every month.
>
> [EQUATION: The image shows people living in their homes located near a nuclear power plant.]
>
> FIGURE 32.20 The people living near this nuclear power plant have no measurable exposure to radiation that is traceable to the plant. About 16% of the world’s electrical power is generated by controlled nuclear fission in such plants. The cooling towers are the most prominent features but are not unique to nuclear power. The reactor is in the small domed building to the left of the towers. (credit: Kalmthouts)
>
> Fission is the opposite of fusion and releases energy only when heavy nuclei are split. As noted in Fusion, energy is released if the products of a nuclear reaction have a greater binding energy per nucleon ( [EQUATION: BE / A] ) than the parent nuclei. Figure 32.21 shows that [EQUATION: BE / A] is greater for medium-mass nuclei than heavy nuclei, implying that when a heavy nucleus is split, the products have less mass per nucleon, so that mass is destroyed and energy is released in the reaction. The amount of energy per fission reaction can be large, even by nuclear standards. The graph in Figure 32.21 shows [EQUATION: BE / A] to be about 7.6 MeV/nucleon for the heaviest nuclei ( [EQUATION: A] about 240), while [EQUATION: BE / A] is about 8.6 MeV/nucleon for nuclei having [EQUATION: A] about 120. Thus, if a heavy nucleus splits in half, then about 1 MeV per nucleon, or approximately 240 MeV per fission, is released. This is about 10 times the energy per fusion reaction, and about 100 times the energy of the average [EQUATION: alpha], [EQUATION: beta], or [EQUATION: gamma] decay.
>
> EXAMPLE 32.3

- ID: openstax_college_physics_ap_2e__919d8eba53f94d04__32__e924c191__02213

> • Define nuclear fission.
>
> • Discuss how fission fuel reacts and describe what it produces.
>
> • Describe controlled and uncontrolled chain reactions.
>
> Nuclear fission is a reaction in which a nucleus is split (or fissured). Controlled fission is a reality, whereas controlled fusion is a hope for the future. Hundreds of nuclear fission power plants around the world attest to the fact that controlled fission is practical and, at least in the short term, economical, as seen in Figure 32.20. Whereas nuclear power was of little interest for decades following TMI and Chernobyl (and now Fukushima Daiichi), growing concerns over global warming has brought nuclear power back on the table as a viable energy alternative. By the end of 2009, there were 442 reactors operating in 30 countries, providing 15% of the world’s electricity. France provides over 75% of its electricity with nuclear power, while the US has 104 operating reactors providing 20% of its electricity. Australia and New Zealand have none. China is building nuclear power plants at the rate of one start every month.
>
> [EQUATION: The image shows people living in their homes located near a nuclear power plant.]
>
> FIGURE 32.20 The people living near this nuclear power plant have no measurable exposure to radiation that is traceable to the plant. About 16% of the world’s electrical power is generated by controlled nuclear fission in such plants. The cooling towers are the most prominent features but are not unique to nuclear power. The reactor is in the small domed building to the left of the towers. (credit: Kalmthouts)
>
> Fission is the opposite of fusion and releases energy only when heavy nuclei are split. As noted in Fusion, energy is released if the products of a nuclear reaction have a greater binding energy per nucleon ( [EQUATION: BE / A] ) than the parent nuclei. Figure 32.21 shows that [EQUATION: BE / A] is greater for medium-mass nuclei than heavy nuclei, implying that when a heavy nucleus is split, the products have less mass per nucleon, so that mass is destroyed and energy is released in the reaction. The amount of energy per fission reaction can be large, even by nuclear standards. The graph in Figure 32.21 shows [EQUATION: BE / A] to be about 7.6 MeV/nucleon for the heaviest nuclei ( [EQUATION: A] about 240), while [EQUATION: BE / A] is about 8.6 MeV/nucleon for nuclei having [EQUATION: A] about 120. Thus, if a heavy nucleus splits in half, then about 1 MeV per nucleon, or approximately 240 MeV per fission, is released. This is about 10 times the energy per fusion reaction, and about 100 times the energy of the average [EQUATION: alpha], [EQUATION: beta], or [EQUATION: gamma] decay.
>
> EXAMPLE 32.3

- ID: ck12_peoples_physics_concepts__d976bbd43160dfdf__20__e924c191__00205

> • Give an overview of radioactive decay. • Write nuclear equations.
>
> Students will learn about radioactive decay and how to write nuclear equations.
>
> Key Equations
>
> • Atomic symbols like A ZX are interpreted in the following way: X is the symbol for the element involved. For example, U is the symbol for the element uranium. Z is the atomic number. A is the atomic mass number, the total number of nucleons (protons and neutrons). A would be 235 for uranium.
>
> • The nuclear process is largely random in direction. Therefore, radiation strength decreases with distance by the inverse square of the distance (the 1/r2 law, which also holds for gravity, electric fields, light intensity, sound intensity, and so on.)
>
> Guidance
>
> • Alpha decay is the process in which an isotope releases a helium nucleus (2 protons and 2 neutrons, 4 2 He) and thus decays into an atom with two less protons.
>
> Example: 232
>
> 90 Th →228 88 Ra+ 4 2 He
>
> Beta Decay
>
> • Beta decay is the process in which one of the neutrons in an isotope decays, leaving a proton, electron and anti-neutrino. As a result, the nucleus decays into an atom that has the same number of nucleons, with one neutron replaced by a proton. (Beta positive decay is the reverse process, in which a proton decays into a neutron, anti-electron and neutrino.)
>
> Example: 14
>
> 6 C →14 7 N+ 0 −1 e−+ v
>
> Gamma Decay
>
> • Gamma decay is the process in which an excited atomic nucleus kicks out a photon and releases some of its energy. The makeup of the nucleus doesn’t change, it just loses energy. (It can be useful to think of this as energy of motion –think of a shuddering nucleus that only relaxes after emitting some light.)
>
> Example: 137
>
> 56 Ba∗→137 56 Ba+y
>
> Fission and Fusion
>
> • Fission is the process in which an atomic nucleus breaks apart into two less massive nuclei. Energy is released in the process in many forms, heat, gamma rays and the kinetic energy of neutrons. If these neutrons collide with nuclei and induce more fission, then a runaway chain reaction can take place. Fission is responsible for nuclear energy and atom-bomb explosions: the fission of uranium acts as a heat source for the Earth’s molten interior.
>
> Example: 1 n+ 235 U →141 Ba+ 92 Kr+31 n
>
> • Fusion is the process in which two atomic nuclei fuse together to make a single nucleus. Energy is released in the form of nuclear particles, neutrons, and gamma-rays.
>
> Example: 3
>
> 1 H+ 2 1 H →4 2 He+ 1 0 n+y
>
> Simulation
>
> Alpha Decay
>
> Alpha Decay (PhET Simulation)
>
> Beta Decay
>
> Beta Decay (PhET Simulation)

- ID: openstax_college_physics_2e__89ad46e1222dbb4a__32__e924c191__02236

> • Define nuclear fusion.
>
> • Discuss processes to achieve practical fusion energy generation.
>
> While basking in the warmth of the summer sun, a student reads of the latest breakthrough in achieving sustained thermonuclear power and vaguely recalls hearing about the cold fusion controversy. The three are connected. The Sun’s energy is produced by nuclear fusion (see Figure 32.11 ). Thermonuclear power is the name given to the use of controlled nuclear fusion as an energy source. While research in the area of thermonuclear power is progressing, high temperatures and containment difficulties remain. The cold fusion controversy centered around unsubstantiated claims of practical fusion power at room temperatures.
>
> [FIGURE DESCRIPTION: This figure shows Sun rays piercing clouds to illuminate a natural scene.]
>
> FIGURE 32.11 The Sun’s energy is produced by nuclear fusion. (credit: Spiralz)
>
> Nuclear fusion is a reaction in which two nuclei are combined, or fused, to form a larger nucleus. We know that all nuclei have less mass than the sum of the masses of the protons and neutrons that form them. The missing mass times [EQUATION: c ²] equals the binding energy of the nucleus—the greater the binding energy, the greater the missing mass. We also know that [EQUATION: BE / A], the binding energy per nucleon, is greater for medium-mass nuclei and has a maximum at Fe (iron). This means that if two low-mass nuclei can be fused together to form a larger nucleus, energy can be released. The larger nucleus has a greater binding energy and less mass per nucleon than the two that combined. Thus mass is destroyed in the fusion reaction, and energy is released (see Figure 32.12 ). On average, fusion of lowmass nuclei releases energy, but the details depend on the actual nuclides involved.
>
> [FIGURE DESCRIPTION: This figure is a graph of atomic mass as horizontal axis versus binding energy per nucleon as vertical axis showing that, as a function of atomic mass, the binding energy per nucleon steeply increases from zero to about 9 M e V per nucleon then, after attaining a peak, slowly decreases to about 8 M e V per nucleon.]
>
> FIGURE 32.12 Fusion of light nuclei to form medium-mass nuclei destroys mass, because
>
> [EQUATION: BE / A]
>
> is greater for the product nuclei. The larger

- ID: openstax_college_physics_ap_2e__919d8eba53f94d04__32__e924c191__02203

> • Define nuclear fusion.
>
> • Discuss processes to achieve practical fusion energy generation.
>
> While basking in the warmth of the summer sun, a student reads of the latest breakthrough in achieving sustained thermonuclear power and vaguely recalls hearing about the cold fusion controversy. The three are connected. The Sun’s energy is produced by nuclear fusion (see Figure 32.11 ). Thermonuclear power is the name given to the use of controlled nuclear fusion as an energy source. While research in the area of thermonuclear power is progressing, high temperatures and containment difficulties remain. The cold fusion controversy centered around unsubstantiated claims of practical fusion power at room temperatures.
>
> [FIGURE DESCRIPTION: This figure shows Sun rays piercing clouds to illuminate a natural scene.]
>
> FIGURE 32.11 The Sun’s energy is produced by nuclear fusion. (credit: Spiralz)
>
> Nuclear fusion is a reaction in which two nuclei are combined, or fused, to form a larger nucleus. We know that all nuclei have less mass than the sum of the masses of the protons and neutrons that form them. The missing mass times [EQUATION: c ²] equals the binding energy of the nucleus—the greater the binding energy, the greater the missing mass. We also know that [EQUATION: BE / A], the binding energy per nucleon, is greater for medium-mass nuclei and has a maximum at Fe (iron). This means that if two low-mass nuclei can be fused together to form a larger nucleus, energy can be released. The larger nucleus has a greater binding energy and less mass per nucleon than the two that combined. Thus mass is destroyed in the fusion reaction, and energy is released (see Figure 32.12 ). On average, fusion of lowmass nuclei releases energy, but the details depend on the actual nuclides involved.
>
> [FIGURE DESCRIPTION: This figure is a graph of atomic mass as horizontal axis versus binding energy per nucleon as vertical axis showing that, as a function of atomic mass, the binding energy per nucleon steeply increases from zero to about 9 M e V per nucleon then, after attaining a peak, slowly decreases to about 8 M e V per nucleon.]
>
> FIGURE 32.12 Fusion of light nuclei to form medium-mass nuclei destroys mass, because
>
> [EQUATION: BE / A]
>
> is greater for the product nuclei. The larger


External physics references (review-only, not judge evidence):

- [Review-only neutron question B7123 verifies the mechanism; never supply this reference to the judge.](https://www.nrc.gov/reactors/operator-licensing/history-rulemaking-activities/generic-fundamentals-examinations/bwr/bwr-files/292001.pdf)

Leader checks:

- Intended target violation: **pending**.
- Other-criterion effects / physics preservation: **pending**.
- Full-answer internal consistency: **pending**.
- Difficulty label confirmation: **pending**.
- Accept / revise / reject and reason: **pending**.
- Reviewer, date and frozen sample hash: **pending**.


## perturb-v2-evidence-support-gemma

Question: Electrical potential energy can be described by the equation pe = qv, where q is the electric charge and v is what?

Source: evaluation-64a7f6e246c361983f97e50b; advanced; P1R1_combined.

Frozen criterion: Existing correctness rubric / supplied-evidence support definition.

Original answer:

> Electrical potential energy is given by the equation pe = qv, where q is the electric charge and v represents the voltage. This is evident from the equation PE = qV, where PE is electric potential energy, q is the charge, and V is the voltage.

Perturbed candidate:

> Electrical potential energy is given by the equation pe = qv, where q is the electric charge and v represents the voltage measured by a voltmeter connected in parallel across the two points. This is evident from the equation PE = qV, where PE is electric potential energy, q is the charge, and V is the voltage.

Controlled edit (one semantic target; repeated mentions may share one span):

```text
BEFORE: "v represents the voltage."
AFTER: "v represents the voltage measured by a voltmeter connected in parallel across the two points."
```

Selection reason: Extend the correct voltage identification to a credible measurement procedure absent from the supplied qV/potential-energy passages.

Expected response (hypothesis): the added factual subclaim has bundle_support unsupported

Proposed difficulty: clear

Difficulty reason: The supplied passages identify voltage but none describes a voltmeter connection; the added procedure remains physically correct.

Proposed invariants (not human-confirmed):

- The qV relation, charge identification and voltage answer remain unchanged.
- The added parallel-voltmeter procedure is physically correct.

Review focus: Read all supplied passages, including objectives/headings; a passage naming voltage does not automatically support the meter-connection procedure.

Evidence actually supplied to generation:

- ID: openstax_college_physics_2e__89ad46e1222dbb4a__19__e924c191__01237

> • Define electric potential and electric potential energy.
>
> • Describe the relationship between potential difference and electrical potential energy.
>
> • Explain electron volt and its usage in submicroscopic process.
>
> • Determine electric potential energy given potential difference and amount of charge.
>
> When a free positive charge [EQUATION: q] is accelerated by an electric field, such as shown in Figure 19.2, it is given kinetic energy. The process is analogous to an object being accelerated by a gravitational field. It is as if the charge is going down an electrical hill where its electric potential energy is converted to kinetic energy. Let us explore the work done on a charge [EQUATION: q] by the electric field in this process, so that we may develop a definition of electric potential energy.
>
> [FIGURE DESCRIPTION: A charge plus q moves from a positive to a negative sheet of charge. The change in the electric potential energy equals the change in kinetic energy. This is similar to the change from gravitational potential energy to kinetic energy when an object of mass m rolls downhill.]
>
> FIGURE 19.2 A charge accelerated by an electric field is analogous to a mass going down a hill. In both cases potential energy is converted to another form. Work is done by a force, but since this force is conservative, we can write
>
> [EQUATION: W = number en dash normal Δ PE]
>
> .
>
> The electrostatic or Coulomb force is conservative, which means that the work done on [EQUATION: q] is independent of the path taken. This is exactly analogous to the gravitational force in the absence of dissipative forces such as friction. When a force is conservative, it is possible to define a potential energy associated with the force, and it is usually easier to deal with the potential energy (because it depends only on position) than to calculate the work directly.
>
> We use the letters PE to denote electric potential energy, which has units of joules (J). The change in potential energy, [EQUATION: Δ PE], is crucial, since the work done by a conservative force is the negative of the change in potential energy; that is, [EQUATION: W = en dash Δ PE]. For example, work [EQUATION: W] done to accelerate a positive charge from rest is positive and results from a loss in PE, or a negative [EQUATION: Δ PE]. There must be a minus sign in front of [EQUATION: Δ PE] to make [EQUATION: W] positive. PE can be found at any point by taking one point as a reference and calculating the work needed to move a charge to the other point.

- ID: openstax_college_physics_ap_2e__919d8eba53f94d04__19__e924c191__01217

> • Define electric potential and electric potential energy.
>
> • Describe the relationship between potential difference and electrical potential energy.
>
> • Explain electron volt and its usage in submicroscopic process.
>
> • Determine electric potential energy given potential difference and amount of charge.
>
> When a free positive charge [EQUATION: q] is accelerated by an electric field, such as shown in Figure 19.2, it is given kinetic energy. The process is analogous to an object being accelerated by a gravitational field. It is as if the charge is going down an electrical hill where its electric potential energy is converted to kinetic energy. Let us explore the work done on a charge [EQUATION: q] by the electric field in this process, so that we may develop a definition of electric potential energy.
>
> [FIGURE DESCRIPTION: A charge plus q moves from a positive to a negative sheet of charge. The change in the electric potential energy equals the change in kinetic energy. This is similar to the change from gravitational potential energy to kinetic energy when an object of mass m rolls downhill.]
>
> FIGURE 19.2 A charge accelerated by an electric field is analogous to a mass going down a hill. In both cases potential energy is converted
>
> to another form. Work is done by a force, but since this force is conservative, we can write
>
> [EQUATION: W = number en dash normal Δ PE]
>
> .
>
> The electrostatic or Coulomb force is conservative, which means that the work done on [EQUATION: q] is independent of the path taken. This is exactly analogous to the gravitational force in the absence of dissipative forces such as friction. When a force is conservative, it is possible to define a potential energy associated with the force, and it is usually easier to deal with the potential energy (because it depends only on position) than to calculate the work directly.
>
> We use the letters PE to denote electric potential energy, which has units of joules (J). The change in potential energy, [EQUATION: Δ PE], is crucial, since the work done by a conservative force is the negative of the change in potential energy; that is, [EQUATION: W = en dash Δ PE]. For example, work [EQUATION: W] done to accelerate a positive charge from rest is positive and results from a loss in PE, or a negative [EQUATION: Δ PE]. There must be a minus sign in front of [EQUATION: Δ PE] to make [EQUATION: W] positive. PE can be found at any point by taking one point as a reference and calculating the work needed to move a charge to the other point.

- ID: openstax_college_physics_2e__89ad46e1222dbb4a__21__e924c191__01380

> So the voltage drop across [EQUATION: R_1] is [EQUATION: V_1 = italic IR_1], that across [EQUATION: R_2] is [EQUATION: V_2 = italic IR_2], and that across [EQUATION: R_3] is [EQUATION: V_3 = italic IR_3]. The sum of these voltages equals the voltage output of the source; that is,
>
> [EQUATION: V = V_1 + V_2 + V_3.]
>
> 21.1
>
> This equation is based on the conservation of energy and conservation of charge. Electrical potential energy can be described by the equation [EQUATION: PE = qV], where [EQUATION: q] is the electric charge and [EQUATION: V] is the voltage. Thus the energy supplied by the source is [EQUATION: qV], while that dissipated by the resistors is
>
> [EQUATION: qV_1 + qV_2 + qV_3.]
>
> 21.2

- ID: openstax_college_physics_2e__89ad46e1222dbb4a__19__e924c191__01239

> This is the electric potential energy per unit charge.
>
> [EQUATION: V = PE / q]
>
> 19.2
>
> Since PE is proportional to [EQUATION: q], the dependence on [EQUATION: q] cancels. Thus [EQUATION: V] does not depend on [EQUATION: q]. The change in potential energy [EQUATION: Δ PE] is crucial, and so we are concerned with the difference in potential or potential difference [EQUATION: ΔV] between two points, where
>
> [EQUATION: ΔV = V_cap B − V_cap A = Δ PE / q.]
>
> 19.3
>
> The potential difference between points A and B, [EQUATION: V_cap B en dash V_cap A], is thus defined to be the change in potential energy of a charge [EQUATION: q] moved from A to B, divided by the charge. Units of potential difference are joules per coulomb, given the name volt (V) after Alessandro Volta.
>
> [EQUATION: 1 cap V = 1 (cap J) / (cap C)]
>
> 19.4

- ID: openstax_college_physics_ap_2e__919d8eba53f94d04__21__e924c191__01357

> So the voltage drop across [EQUATION: R_1] is [EQUATION: V_1 = italic IR_1], that across [EQUATION: R_2] is [EQUATION: V_2 = italic IR_2], and that across [EQUATION: R_3] is [EQUATION: V_3 = italic IR_3]. The sum of these voltages equals the voltage output of the source; that is,
>
> [EQUATION: V = V_1 + V_2 + V_3.]
>
> 21.1
>
> This equation is based on the conservation of energy and conservation of charge. Electrical potential energy can be described by the equation [EQUATION: PE = qV], where [EQUATION: q] is the electric charge and [EQUATION: V] is the voltage. Thus the energy supplied by the source is [EQUATION: qV], while that dissipated by the resistors is
>
> [EQUATION: qV_1 + qV_2 + qV_3.]
>
> 21.2


External physics references (review-only, not judge evidence):

- [Review-only meter fact check; not part of the model evidence bundle.](https://openstax.org/books/college-physics-2e/pages/21-4-dc-voltmeters-and-ammeters)

Leader checks:

- Intended target violation: **pending**.
- Other-criterion effects / physics preservation: **pending**.
- Full-answer internal consistency: **pending**.
- Difficulty label confirmation: **pending**.
- Accept / revise / reject and reason: **pending**.
- Reviewer, date and frozen sample hash: **pending**.
