# Human judge-audit guide

Scope: GPT-OSS Dev only. Leader/M3 review is pending. Ten calibration/orientation cases and 20 independent audit cases are prepared, not reviewed. The orientation packet does not claim historical calibration or authorize new prompt tuning.

## Review procedure

1. Read the question, answer and frozen level checklist before opening saved verdicts.
2. Record whether each saved judge dimension contains an obvious error, with a reason.
3. Use adaptation, discrimination and evidence support for the native audit ratings.
4. Review correctness separately when useful; it is not a native HumanAuditRating field.
5. I3 and citation support are reference-only; review and annotate them separately.
6. A true statement can be unsupported by the supplied evidence; truth is not support.
7. Do not use independent audit cases to tune prompts, thresholds or the checklist.
8. Do not mark any pending decision false merely because no review has occurred.

Open calibration_review.md for orientation if useful, then independent_review.md. Read the question and answer, apply the exact target-level criteria below, and inspect the supplied evidence. Expand the saved verdicts only after forming your own view. This is a review of obvious judge errors, not a new scoring model or accuracy estimate.

Reviewers may fill the pending lines in independent_review.md in plain English. M8 then transcribes only those actual decisions into ratings.pending.jsonl, with the real rater_id, three boolean decisions and notes. True means an obvious error; false means checked with no obvious error; null means pending. Retain all IDs and hashes. The audit rubric requires reviewer confirmation. If it changes before review, regenerate its binding rather than accepting an old hash.

I3 and citation support are reference-only. The native adaptation flag audits saved criterion decisions; the main intermediate aggregation separately excludes I3. Explain I3-only disagreements and distinguish bundle support from citation support in notes. A true statement can still lack support in supplied passages. Do not invent an aggregate pass threshold, word-count rule or formula-count shortcut.

The native audit covers adaptation, discrimination and evidence support. Correctness scores are optional context only; a substantive correctness audit also needs the Gold/rubric and is not claimed here. Completed ratings are later checked using load_bound_human_audit and the separately stored private identity key. Pending ratings must not pass that loader. Do not publish the private identity key.

## Frozen learner profiles and checklists

These are the exact saved definitions. Each case specifies which target level to use. Do not change the profiles, prompts or checklist on the independent audit cases.

```json
{
  "profiles": [
    {
      "schema_version": "1.0",
      "profile_version": "level-profile-v1",
      "level": "beginner",
      "student_positioning": "A learner who has not taken university physics. Everyday observations are available, but high-school physics coverage is not assumed. This is one global prior across topics, not a different level for each chapter.",
      "assumed_physics_background": [
        "Everyday experience of pushes, falling, warm and cool objects, light, sound, and household batteries; these experiences do not imply knowledge of their physical mechanisms.",
        "No prior mastery of Newton laws, conservation laws, fields, waves, thermal models, or circuit laws; introduce any required law or physical quantity in context."
      ],
      "assumed_mathematics_background": [
        "Arithmetic, fractions, ratios, unit reading, and substitution into a fully explained simple relation.",
        "Do not assume algebraic rearrangement, vector components, trigonometric identities, calculus, or differential equations; explain any indispensable extension."
      ],
      "terms_allowed_without_explanation": [
        "everyday uses of push, pull, heavier, warmer, cooler, distance, time, and speed",
        "common units such as seconds, metres, grams, and degrees Celsius; introduce unfamiliar units and scientific meanings in context"
      ],
      "acceptable_inference_span": "Make each new physical inference explicit: observation or given condition -> explained physical idea -> consequence -> requested answer. Ordinary arithmetic may be combined if its meaning is stated. This is a dependency rule, not a maximum sentence count or a fixed number of reasoning steps.",
      "omittable_intermediate_steps": [
        "Counting and elementary arithmetic after explaining what is being calculated.",
        "Restating information already made concrete in the question; use that situation as support instead of adding an unnecessary second analogy."
      ],
      "helpful_writing_patterns": [
        "Introduce a needed physics term in everyday words when first used, including ordinary words used with a specialised meaning such as work, power, or field.",
        "Use the given situation, a concrete example or a bounded analogy to make an unfamiliar concept understandable; explicitly connect it to the conclusion.",
        "Explain the meaning of each introduced formula and symbol, why the relation applies, and the physical meaning of the result. A correct simple equation is welcome when useful."
      ],
      "harmful_writing_patterns": [
        "A bare name, unexplained symbol, or law citation standing in for an explanation the question asks for.",
        "Unexplained calculus, vector notation, or technical analogies; a literal claim based on an analogy that changes the physics.",
        "Filling a sentence quota, adding decorative examples, or treating shorter answers or formula-free answers as automatically better."
      ],
      "anchor_examples": [
        {
          "anchor_id": "m7-anchor-pendulum-mass",
          "question": "Two ideal simple pendulums have the same length and are released from rest at the same small angle at the same location. One bob has twice the mass of the other. Neglect string mass, friction, and air resistance. Does the heavier bob take longer to complete one swing? Explain.",
          "answer": "No. The period, the time for one complete swing, is the same. Gravity pulls twice as strongly on the heavier bob, but its greater mass also makes its motion twice as hard to change. These effects balance. With equal lengths and small starting angles, neither bob takes longer.",
          "rationale": "Defines period and explains both causal links without requiring a familiar pendulum formula; the concrete comparison in the question supplies B3 support.",
          "is_gold": false
        },
        {
          "anchor_id": "m7-anchor-siren-doppler",
          "question": "An ambulance siren sounds higher in pitch while the ambulance approaches a listener standing at the roadside, and lower in pitch after it passes. What is this effect called?",
          "answer": "This is called the Doppler effect: the pitch you hear, meaning how high or low a sound seems, changes when the source of the sound moves toward you or away from you. The siren itself keeps making the same sound; only the pitch reaching you changes.",
          "rationale": "Names the effect and explains the new term in everyday words. The question asks only for the name, so B2 is met by the correct identification without a derivation, and the situation in the question already supplies concrete support. Separating the sound made from the sound heard avoids a misleading claim.",
          "is_gold": false
        },
        {
          "anchor_id": "m7-anchor-parallel-current",
          "question": "An ideal 9 V battery initially supplies one 6 ohm resistor. A second constant 6 ohm resistor is then connected in parallel, across the same battery terminals. Neglect wire resistance. How do the total battery current and the current in the original resistor change? Explain.",
          "answer": "The battery current doubles, from 1.5 A to 3 A; the original resistor still carries 1.5 A. Current is the rate at which electric charge, a property of particles such as electrons, passes a point; it is measured in amperes (A). Parallel means that both resistors connect across the same two battery terminals. Each therefore has the same 9 V voltage, the energy supplied per unit charge. Resistance measures how strongly a component opposes this flow. For a resistor, dividing voltage by resistance gives current: 9 divided by 6 is 1.5 A. The two branch currents add, giving 3 A.",
          "rationale": "Defines current, voltage and parallel connection, introduces the current calculation in words, and shows branch addition rather than using an unexplained equivalent-resistance shortcut.",
          "is_gold": false
        }
      ]
    },
    {
      "schema_version": "1.0",
      "profile_version": "level-profile-v1",
      "level": "intermediate",
      "student_positioning": "A learner currently taking or recently completing an algebra-based first-year introductory physics course. The assumed core is shared globally across topics; unfamiliar specialist topics still need explanation.",
      "assumed_physics_background": [
        "Introductory kinematics, Newton laws, work and energy, momentum and conservation principles.",
        "Basic temperature, heat transfer, waves, superposition, charge, potential difference, Ohm law, and simple series/parallel circuits at introductory course level.",
        "Can recognise standard idealisations such as negligible friction and ideal voltage sources; does not know every advanced model or exception."
      ],
      "assumed_mathematics_background": [
        "Algebraic rearrangement, proportions, graphs and slopes, powers and roots, units and dimensional checks.",
        "Basic vectors and trigonometry for introductory components; calculus and differential-equation solutions are not assumed."
      ],
      "terms_allowed_without_explanation": [
        "displacement, velocity, acceleration, net force, mass, inertia, work, kinetic and potential energy, momentum",
        "heat, temperature, specific heat, thermal equilibrium, frequency, wavelength, superposition",
        "charge, current, voltage, resistance, series and parallel, Newton laws, conservation of energy and charge, Ohm law"
      ],
      "acceptable_inference_span": "Name the governing principle, connect the question conditions to it, and state how it produces the conclusion. Routine substitution and algebra may be compressed; do not omit the choice of model, causal link, sign convention when consequential, or a non-obvious approximation. No sentence quota applies.",
      "omittable_intermediate_steps": [
        "Routine arithmetic, elementary rearrangement, and repeated definitions of mastered course terms.",
        "A full proof of a standard introductory law when naming and applying it supplies the requested explanation."
      ],
      "helpful_writing_patterns": [
        "Organise around the governing principle, its application to the givens, and the resulting physical interpretation.",
        "Use standard course terms accurately and introduce specialist quantities or notation not in the assumed core.",
        "Use equations when they clarify the mechanism or calculation and explain an important approximation or ambiguity."
      ],
      "harmful_writing_patterns": [
        "Repeating elementary dictionary definitions without advancing the answer.",
        "Quoting a law without connecting it to the requested result, or substituting arithmetic for the physical argument.",
        "Assuming a calculus derivation or unfamiliar specialist terminology is automatically known."
      ],
      "anchor_examples": [
        {
          "anchor_id": "m7-anchor-pendulum-mass",
          "question": "Two ideal simple pendulums have the same length and are released from rest at the same small angle at the same location. One bob has twice the mass of the other. Neglect string mass, friction, and air resistance. Does the heavier bob take longer to complete one swing? Explain.",
          "answer": "The periods are equal. By Newton's second law, the tangential gravitational force and inertia both scale with bob mass, so mass cancels when finding tangential acceleration. With equal lengths and the same small initial angle, the two pendulums have the same motion in time.",
          "rationale": "Names the governing law and connects force scaling to mass cancellation; does not redefine force or acceleration.",
          "is_gold": false
        },
        {
          "anchor_id": "m7-anchor-siren-doppler",
          "question": "An ambulance siren sounds higher in pitch while the ambulance approaches a listener standing at the roadside, and lower in pitch after it passes. What is this effect called?",
          "answer": "The Doppler effect. Motion of the sound source relative to the listener changes the frequency the listener receives: it is higher while the source approaches and lower while it recedes.",
          "rationale": "The correct name satisfies I1 for an identification question, and one sentence links it to the observed pitch change in course terms such as frequency, without redefining sound or pitch. No derivation is needed because the question asks only for the name.",
          "is_gold": false
        },
        {
          "anchor_id": "m7-anchor-parallel-current",
          "question": "An ideal 9 V battery initially supplies one 6 ohm resistor. A second constant 6 ohm resistor is then connected in parallel, across the same battery terminals. Neglect wire resistance. How do the total battery current and the current in the original resistor change? Explain.",
          "answer": "Ohm's law gives I = V/R = 9/6 = 1.5 A in each branch because each parallel resistor has the full battery voltage. Kirchhoff's junction rule gives total current 1.5 + 1.5 = 3 A. Thus battery current doubles, while the original branch current remains 1.5 A.",
          "rationale": "Connects Ohm's law and charge conservation to the two requested currents without repeating elementary definitions.",
          "is_gold": false
        }
      ]
    },
    {
      "schema_version": "1.0",
      "profile_version": "level-profile-v1",
      "level": "advanced",
      "student_positioning": "A learner who has completed calculus-based introductory university physics, not a subject specialist or research physicist. The same global prior applies to all topics; advanced specialist results still require context.",
      "assumed_physics_background": [
        "Calculus-based mechanics, energy and momentum, oscillations and waves, basic thermal physics, electricity and magnetism.",
        "Can select introductory models, follow conservation and field arguments, and recognise the role of idealisation, initial conditions, limiting cases and dimensional consistency.",
        "Does not automatically know quantum field theory, advanced statistical mechanics, tensor methods, or every named specialist effect."
      ],
      "assumed_mathematics_background": [
        "Algebra, trigonometry, vectors, derivatives and elementary integrals with physical interpretations.",
        "Can interpret a standard introductory differential equation, approximation, or limiting relation; solving an arbitrary differential equation and advanced mathematical methods are not assumed."
      ],
      "terms_allowed_without_explanation": [
        "standard introductory mechanics, thermal, wave and electromagnetism terminology listed for the intermediate level",
        "derivative, integral, vector component, small-angle approximation, ideal source, boundary condition, conservation equation, limiting case and dimensional analysis"
      ],
      "acceptable_inference_span": "A standard law-to-model-to-result chain may be compressed into a well-defined relation and interpretation. Routine calculus and algebra can be omitted when recoverable from the stated model. Keep any non-obvious model choice, important assumption, boundary of validity, or logical qualification visible. Concision never excuses an unsupported leap.",
      "omittable_intermediate_steps": [
        "Definitions of familiar introductory terms and standard laws.",
        "Routine algebra, elementary differentiation/integration, and numeric substitutions when they do not resolve an ambiguity.",
        "Beginner scaffolding or a second analogy that merely repeats an already transparent physical relation."
      ],
      "helpful_writing_patterns": [
        "Give the requested result with a compact physical argument and state assumptions that change its validity.",
        "Use a quantitative relation, scaling argument, or limiting case only when it clarifies the question; define specialised symbols.",
        "Account for expertise reversal: support that explains an unfamiliar step can help, while repeated mastered definitions can impose redundant processing. Judge redundancy by its role, not by answer length."
      ],
      "harmful_writing_patterns": [
        "Automatic tutorials on familiar concepts that obscure the requested result.",
        "Prestige jargon, gratuitous equations, or specialist methods used to signal sophistication.",
        "Unqualified generalisations beyond an ideal model, unexplained novel notation, or compression that hides a necessary inference."
      ],
      "anchor_examples": [
        {
          "anchor_id": "m7-anchor-pendulum-mass",
          "question": "Two ideal simple pendulums have the same length and are released from rest at the same small angle at the same location. One bob has twice the mass of the other. Neglect string mass, friction, and air resistance. Does the heavier bob take longer to complete one swing? Explain.",
          "answer": "The periods are equal. For an ideal point bob on a massless inextensible string, the small-angle equation is theta-double-dot + (g/L)theta = 0, giving T = 2 pi sqrt(L/g), independent of bob mass. Here L is pendulum length, g is local gravitational acceleration, theta is angular displacement, and T is period. The equal-length, small-angle and negligible-damping assumptions justify this expression.",
          "rationale": "Uses a compact quantitative argument with its idealisation and small-angle scope; no introductory explanation of gravity or inertia.",
          "is_gold": false
        },
        {
          "anchor_id": "m7-anchor-siren-doppler",
          "question": "An ambulance siren sounds higher in pitch while the ambulance approaches a listener standing at the roadside, and lower in pitch after it passes. What is this effect called?",
          "answer": "The Doppler effect for sound: the observed frequency is higher than the emitted frequency while the source approaches and lower while it recedes; the siren's emitted frequency itself is unchanged.",
          "rationale": "A precise identification that separates observed from emitted frequency passes A4 without an argument the question does not ask for. No quantitative relation is needed, so A3 is not applicable, and there is no redundant tutorial on sound or frequency (A1).",
          "is_gold": false
        },
        {
          "anchor_id": "m7-anchor-parallel-current",
          "question": "An ideal 9 V battery initially supplies one 6 ohm resistor. A second constant 6 ohm resistor is then connected in parallel, across the same battery terminals. Neglect wire resistance. How do the total battery current and the current in the original resistor change? Explain.",
          "answer": "With ideal fixed terminal voltage and constant ohmic resistances, I_original = V/R = 1.5 A before and after the change. Adding the identical parallel branch changes equivalent resistance from R to R/2 = 3 ohms, so I_total changes from V/R = 1.5 A to 2V/R = 3 A. Nonzero battery internal resistance could lower terminal voltage and invalidate the unchanged-branch-current conclusion.",
          "rationale": "Uses compact relations and identifies the important ideal-source boundary; no redundant introduction to current or voltage.",
          "is_gold": false
        }
      ]
    }
  ],
  "checklists": [
    {
      "schema_version": "1.0",
      "checklist_version": "level-checklist-v1",
      "level": "beginner",
      "criteria": [
        {
          "criterion_id": "B1",
          "level": "beginner",
          "description": "Explain each key unfamiliar physical term or specialised meaning at first use, or express it in understandable everyday language. Terms explicitly allowed by the beginner profile need no definition. Terms the question itself already uses also need no definition unless the answer gives them a new technical meaning. Always assess for a substantive answer. Pass with an exact answer quote showing accessible wording or the explanation; fail if necessary terminology remains unexplained."
        },
        {
          "criterion_id": "B2",
          "level": "beginner",
          "description": "Make the physical reasoning needed to answer the question recoverable from the beginner prior: connect the givens, the introduced physical idea, and the conclusion without an unexplained conceptual jump. Routine arithmetic can be combined. Always assess. If the question only asks to identify or name a term, object, quantity, or fact, and does not ask why or how, a correct identification with no unsupported claim passes; do not require reasoning the question does not ask for. Otherwise a missing necessary step is fail, never not_applicable."
        },
        {
          "criterion_id": "B3",
          "level": "beginner",
          "description": "When an unfamiliar abstract concept needs concrete support, supply a correct example, bounded analogy, explicit concrete calculation, or explanatory use of the situation already in the question. Assess necessity from the question and beginner prior before inspecting whether support was supplied. If no such support is needed for this question, use not_applicable; if needed but missing, use fail. Extra decorative examples earn no credit."
        },
        {
          "criterion_id": "B4",
          "level": "beginner",
          "description": "Keep formulas and notation within the beginner prior or explain any indispensable extension, its symbols, and why it applies. Always assess: clear ordinary-language reasoning can pass with a quote and does not require a formula. Unexplained advanced notation fails even in a qualitative question. Formula presence or absence alone is not the decision rule."
        }
      ]
    },
    {
      "schema_version": "1.0",
      "checklist_version": "level-checklist-v1",
      "level": "intermediate",
      "criteria": [
        {
          "criterion_id": "I1",
          "level": "intermediate",
          "description": "Identify the governing principle, law, or concept relevant to the question. Use standard terminology accurately. If the question only asks to identify or name a term, object, quantity, or fact, the correct identification itself satisfies I1. Always assess substantive answers. Do not demand an irrelevant law or a proof just to make the answer look longer."
        },
        {
          "criterion_id": "I2",
          "level": "intermediate",
          "description": "Explain how the givens, evidence, or governing principle lead to the conclusion at the intermediate prior. Routine algebra may be compressed, but a non-obvious physical inference or consequential assumption must remain clear. Always assess. If the question only asks to identify or name a term, object, quantity, or fact, and does not ask why or how, a correct identification with no unsupported claim passes; do not require an explanation the question does not ask for. Otherwise a missing necessary connection is fail, not not_applicable."
        },
        {
          "criterion_id": "I3",
          "level": "intermediate",
          "description": "Use course terminology accurately and explain unfamiliar specialist ideas while avoiding redundant redefinitions of the intermediate assumed core. A brief clarification that resolves a real ambiguity is helpful, not redundant. Always assess substantive answers. Judge conceptual role and precision, not terminology count or answer length."
        }
      ]
    },
    {
      "schema_version": "1.0",
      "checklist_version": "level-checklist-v1",
      "level": "advanced",
      "criteria": [
        {
          "criterion_id": "A1",
          "level": "advanced",
          "description": "Avoid redundant teaching of mastered introductory definitions or routine operations that obscures the requested argument. Brief reminders needed to remove ambiguity are acceptable. Always assess substantive answers. Judge the function of the explanation under the advanced prior, not word count, brevity alone, or the presence of everyday language."
        },
        {
          "criterion_id": "A2",
          "level": "advanced",
          "description": "State or unambiguously invoke important assumptions and scope when relaxing them could change the answer. Conditions already explicit in the question may be invoked compactly without copying all givens. Determine applicability from the question and advanced prior: if no consequential restriction requires discussion, use not_applicable; if one is necessary but omitted, use fail."
        },
        {
          "criterion_id": "A3",
          "level": "advanced",
          "description": "Use an accurate quantitative, scaling, or limiting relationship when it materially explains the question or is required for the requested result, with sufficient symbol meaning for the advanced prior. Determine usefulness from the question and prior, not whether the answer contains an equation. If none is useful, use not_applicable; if useful but absent or incorrectly used, use fail. Gratuitous formulas do not count as success."
        },
        {
          "criterion_id": "A4",
          "level": "advanced",
          "description": "Give a logically supported, precise physical argument with appropriately qualified claims, consistent quantities and no misleading over-generalisation. Standard recoverable steps may be compressed; specialist notation and non-obvious inferences still require enough context. Always assess substantive answers. If the question only asks to identify or name a term, object, quantity, or fact, and does not ask why or how, a correct and precisely stated identification with no unsupported or over-general claim passes; do not require an argument the question does not ask for. Apparent sophistication and formula count do not establish rigour."
        }
      ]
    }
  ]
}
```
