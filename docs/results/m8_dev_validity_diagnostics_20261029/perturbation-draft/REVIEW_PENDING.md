# Perturbation cases: review pending, not scored

These 18 drafts are single contiguous edits of Dev answers already scored correct with the target criterion passed. All three generators are represented in each target group. No perturbed Gemini score exists. Check semantic isolation before freezing the plan or running any paid command.

Draft targets: B1, B4, A1, I3, correctness, evidence support. A1/I3 test needless re-teaching of the assumed core; they are a proposed alternative to derivation deletion, which can also damage correctness completeness. They do NOT test A4/I2. A1 is not relabelled as a depth criterion. The Leader must approve this target choice or request replacements before freezing or paid scoring. The 80% aggregate detection and at least one detected case per target are proposed thresholds, not yet approved decisions.

## perturb-v1-b1-gpt-oss

Target: B1; level: beginner; condition: P1R1_combined; source: evaluation-737bb64a1c7db426a3757c60.

Question: Sound, like all waves, travels at a certain speed and has the properties of frequency and this?

Frozen rule: Explain each key unfamiliar physical term or specialised meaning at first use, or express it in understandable everyday language. Terms explicitly allowed by the beginner profile need no definition. Terms the question itself already uses also need no definition unless the answer gives them a new technical meaning. Always assess for a substantive answer. Pass with an exact answer quote showing accessible wording or the explanation; fail if necessary terminology remains unexplained.

Original answer:

> Sound waves have two main properties: frequency, which determines pitch, and wavelength, which is the distance between successive compressions or rarefactions. The speed of sound is related to these by v = f λ.

Perturbed draft:

> Sound waves have two main properties: frequency, which determines pitch, and wavelength, which is the distance between successive compressions or rarefactions. The norm of the velocity vector of sound is related to these by v = f λ.

Expected (hypothesis): fail (not not_applicable)

Leader must verify this single contiguous edit violates the target clause, preserves all other relevant criteria and leaves physical correctness unchanged unless correctness is the target.

Leader decision and reason: **pending**.

## perturb-v1-b1-llama

Target: B1; level: beginner; condition: P1R1_combined; source: evaluation-810f667dd65ae15d389dac81.

Question: Displacement divided by time is equal to the average what?

Frozen rule: Explain each key unfamiliar physical term or specialised meaning at first use, or express it in understandable everyday language. Terms explicitly allowed by the beginner profile need no definition. Terms the question itself already uses also need no definition unless the answer gives them a new technical meaning. Always assess for a substantive answer. Pass with an exact answer quote showing accessible wording or the explanation; fail if necessary terminology remains unexplained.

Original answer:

> Displacement divided by time is equal to the average velocity. This is because velocity describes the speed and direction of an object, and average velocity is the displacement divided by the time over which the displacement occurs.

Perturbed draft:

> Displacement divided by time is equal to the average velocity. This is because velocity describes the norm of the velocity vector and direction of an object, and average velocity is the displacement divided by the time over which the displacement occurs.

Expected (hypothesis): fail (not not_applicable)

Leader must verify this single contiguous edit violates the target clause, preserves all other relevant criteria and leaves physical correctness unchanged unless correctness is the target.

Leader decision and reason: **pending**.

## perturb-v1-b1-gemma

Target: B1; level: beginner; condition: P0R1_reranking_only; source: evaluation-367e44f504851ba480549cf0.

Question: Average speed is equal to distance divided by what?

Frozen rule: Explain each key unfamiliar physical term or specialised meaning at first use, or express it in understandable everyday language. Terms explicitly allowed by the beginner profile need no definition. Terms the question itself already uses also need no definition unless the answer gives them a new technical meaning. Always assess for a substantive answer. Pass with an exact answer quote showing accessible wording or the explanation; fail if necessary terminology remains unexplained.

Original answer:

> Average speed is defined as the distance traveled divided by the time it took to travel that distance. This is explicitly stated in the provided evidence.

Perturbed draft:

> Average norm of the velocity vector is defined as the distance traveled divided by the time it took to travel that distance. This is explicitly stated in the provided evidence.

Expected (hypothesis): fail (not not_applicable)

Leader must verify this single contiguous edit violates the target clause, preserves all other relevant criteria and leaves physical correctness unchanged unless correctness is the target.

Leader decision and reason: **pending**.

## perturb-v1-b4-gpt-oss

Target: B4; level: beginner; condition: P1R0_prompt_only; source: evaluation-92ca9f4d39c611427a631f64.

Question: Displacement divided by time is equal to the average what?

Frozen rule: Keep formulas and notation within the beginner prior or explain any indispensable extension, its symbols, and why it applies. Always assess: clear ordinary-language reasoning can pass with a quote and does not require a formula. Unexplained advanced notation fails even in a qualitative question. Formula presence or absence alone is not the decision rule.

Original answer:

> Displacement divided by time gives the average velocity, which includes both speed and direction.

Perturbed draft:

> Displacement divided by time gives the average velocity, which includes both \(\|\vec{v}\|\) and direction.

Expected (hypothesis): fail (not not_applicable)

Leader must verify this single contiguous edit violates the target clause, preserves all other relevant criteria and leaves physical correctness unchanged unless correctness is the target.

Leader decision and reason: **pending**.

## perturb-v1-b4-llama

Target: B4; level: beginner; condition: P1R0_prompt_only; source: evaluation-c77ec67c368297168fa7ad58.

Question: What do we call the predictable distribution of molecular speeds found in gas of many molecules?

Frozen rule: Keep formulas and notation within the beginner prior or explain any indispensable extension, its symbols, and why it applies. Always assess: clear ordinary-language reasoning can pass with a quote and does not require a formula. Unexplained advanced notation fails even in a qualitative question. Formula presence or absence alone is not the decision rule.

Original answer:

> The predictable distribution of molecular speeds found in a gas of many molecules is called the Maxwell-Boltzmann distribution. This distribution is based on kinetic theory and has been confirmed experimentally. It shows that the most probable speed is less than the root-mean-square speed, and that the distribution is shifted to higher speeds at higher temperatures.

Perturbed draft:

> The predictable distribution of molecular speeds found in a gas of many molecules is called the Maxwell-Boltzmann distribution. This distribution is based on kinetic theory and has been confirmed experimentally. It shows that the most probable \(\|\vec{v}\|\) is less than the root-mean-square speed, and that the distribution is shifted to higher speeds at higher temperatures.

Expected (hypothesis): fail (not not_applicable)

Leader must verify this single contiguous edit violates the target clause, preserves all other relevant criteria and leaves physical correctness unchanged unless correctness is the target.

Leader decision and reason: **pending**.

## perturb-v1-b4-gemma

Target: B4; level: beginner; condition: P0R0_plain; source: evaluation-f35bc6908c296c2980a61a0a.

Question: Average speed is equal to distance divided by what?

Frozen rule: Keep formulas and notation within the beginner prior or explain any indispensable extension, its symbols, and why it applies. Always assess: clear ordinary-language reasoning can pass with a quote and does not require a formula. Unexplained advanced notation fails even in a qualitative question. Formula presence or absence alone is not the decision rule.

Original answer:

> Average speed is defined as the distance traveled divided by the time it took to travel that distance. This is explicitly stated in the provided evidence.

Perturbed draft:

> Average \(\|\vec{v}\|\) is defined as the distance traveled divided by the time it took to travel that distance. This is explicitly stated in the provided evidence.

Expected (hypothesis): fail (not not_applicable)

Leader must verify this single contiguous edit violates the target clause, preserves all other relevant criteria and leaves physical correctness unchanged unless correctness is the target.

Leader decision and reason: **pending**.

## perturb-v1-a1-gpt-oss

Target: A1; level: advanced; condition: P1R1_combined; source: evaluation-d8d919881699c394a205ed0c.

Question: Quantum chromodynamics combines what property with quark theory?

Frozen rule: Avoid redundant teaching of mastered introductory definitions or routine operations that obscures the requested argument. Brief reminders needed to remove ambiguity are acceptable. Always assess substantive answers. Judge the function of the explanation under the advanced prior, not word count, brevity alone, or the presence of everyday language.

Original answer:

> Quantum chromodynamics (QCD) is the theory that combines the quark model with the property of color charge, introducing gluons as the mediators of the strong force.

Perturbed draft:

> Quantum chromodynamics (QCD) is the theory that combines the quark model with the property of color charge, introducing gluons as the mediators of the strong force. Here are elementary reminders for the reader. An integer is a whole number. Adding zero to a number leaves it unchanged. Multiplying a number by one leaves it unchanged. For positive integers, multiplication is repeated addition. Two plus two equals four. Four divided by two equals two. A metre is one hundred centimetres. A second is a unit of time.

Expected (hypothesis): fail (not not_applicable)

Leader must verify this single contiguous edit violates the target clause, preserves all other relevant criteria and leaves physical correctness unchanged unless correctness is the target. Confirm the added elementary tutorial is genuinely redundant and obscures the requested answer for this prior; brief useful reminders would not violate the rule. This alternative targets redundancy, not A4/I2 reasoning depth.

Leader decision and reason: **pending**.

## perturb-v1-a1-llama

Target: A1; level: advanced; condition: P1R1_combined; source: evaluation-a32d4955f0a30791c59b4c58.

Question: Because of the wave character of matter, the idea of well-defined orbits gives way to a model in which there is a cloud of what?

Frozen rule: Avoid redundant teaching of mastered introductory definitions or routine operations that obscures the requested argument. Brief reminders needed to remove ambiguity are acceptable. Always assess substantive answers. Judge the function of the explanation under the advanced prior, not word count, brevity alone, or the presence of everyday language.

Original answer:

> Because of the wave character of matter, the idea of well-defined orbits gives way to a model in which there is a cloud of probability, consistent with Heisenberg’s uncertainty principle.

Perturbed draft:

> Because of the wave character of matter, the idea of well-defined orbits gives way to a model in which there is a cloud of probability, consistent with Heisenberg’s uncertainty principle. Here are elementary reminders for the reader. An integer is a whole number. Adding zero to a number leaves it unchanged. Multiplying a number by one leaves it unchanged. For positive integers, multiplication is repeated addition. Two plus two equals four. Four divided by two equals two. A metre is one hundred centimetres. A second is a unit of time.

Expected (hypothesis): fail (not not_applicable)

Leader must verify this single contiguous edit violates the target clause, preserves all other relevant criteria and leaves physical correctness unchanged unless correctness is the target. Confirm the added elementary tutorial is genuinely redundant and obscures the requested answer for this prior; brief useful reminders would not violate the rule. This alternative targets redundancy, not A4/I2 reasoning depth.

Leader decision and reason: **pending**.

## perturb-v1-a1-gemma

Target: A1; level: advanced; condition: P1R0_prompt_only; source: evaluation-623046725c74ce181e8d83c2.

Question: Metal detectors used for airport security work on which principle?

Frozen rule: Avoid redundant teaching of mastered introductory definitions or routine operations that obscures the requested argument. Brief reminders needed to remove ambiguity are acceptable. Always assess substantive answers. Judge the function of the explanation under the advanced prior, not word count, brevity alone, or the presence of everyday language.

Original answer:

> Metal detectors utilize the principle of inductance. A coil or inductor in the metal detector frame acts as both a transmitter and a receiver. The self-inductance of the circuit is affected by any metal object in the path, causing a change in the induced current.

Perturbed draft:

> Metal detectors utilize the principle of inductance. A coil or inductor in the metal detector frame acts as both a transmitter and a receiver. The self-inductance of the circuit is affected by any metal object in the path, causing a change in the induced current. Here are elementary reminders for the reader. An integer is a whole number. Adding zero to a number leaves it unchanged. Multiplying a number by one leaves it unchanged. For positive integers, multiplication is repeated addition. Two plus two equals four. Four divided by two equals two. A metre is one hundred centimetres. A second is a unit of time.

Expected (hypothesis): fail (not not_applicable)

Leader must verify this single contiguous edit violates the target clause, preserves all other relevant criteria and leaves physical correctness unchanged unless correctness is the target. Confirm the added elementary tutorial is genuinely redundant and obscures the requested answer for this prior; brief useful reminders would not violate the rule. This alternative targets redundancy, not A4/I2 reasoning depth.

Leader decision and reason: **pending**.

## perturb-v1-i3-gpt-oss

Target: I3; level: intermediate; condition: P0R0_plain; source: evaluation-988ce9c090ccafa6979e7494.

Question: Kirchhoff’s second rule (the loop rule) is an application of conservation of what?

Frozen rule: Use course terminology accurately and explain unfamiliar specialist ideas while avoiding redundant redefinitions of the intermediate assumed core. A brief clarification that resolves a real ambiguity is helpful, not redundant. Always assess substantive answers. Judge conceptual role and precision, not terminology count or answer length.

Original answer:

> Kirchhoff’s second rule (the loop rule) is an application of conservation of energy.

Perturbed draft:

> Kirchhoff’s second rule (the loop rule) is an application of conservation of energy. Here are elementary reminders for the reader. An integer is a whole number. Adding zero to a number leaves it unchanged. Multiplying a number by one leaves it unchanged. For positive integers, multiplication is repeated addition. Two plus two equals four. Four divided by two equals two. A metre is one hundred centimetres. A second is a unit of time.

Expected (hypothesis): fail (not not_applicable)

Leader must verify this single contiguous edit violates the target clause, preserves all other relevant criteria and leaves physical correctness unchanged unless correctness is the target. Confirm the added elementary tutorial is genuinely redundant and obscures the requested answer for this prior; brief useful reminders would not violate the rule. This alternative targets redundancy, not A4/I2 reasoning depth.

Leader decision and reason: **pending**.

## perturb-v1-i3-llama

Target: I3; level: intermediate; condition: P1R1_combined; source: evaluation-72ccccd890a625345b87616e.

Question: What process refers to a separation of charge within an atom or molecule?

Frozen rule: Use course terminology accurately and explain unfamiliar specialist ideas while avoiding redundant redefinitions of the intermediate assumed core. A brief clarification that resolves a real ambiguity is helpful, not redundant. Always assess substantive answers. Judge conceptual role and precision, not terminology count or answer length.

Original answer:

> Polarization is a separation of charge within an atom or molecule. This can be modeled as shown in Figure 19.17, where the orbits of electrons around the nucleus are shifted slightly by external charges, resulting in a separation of charge within the atom.

Perturbed draft:

> Polarization is a separation of charge within an atom or molecule. This can be modeled as shown in Figure 19.17, where the orbits of electrons around the nucleus are shifted slightly by external charges, resulting in a separation of charge within the atom. Here are elementary reminders for the reader. An integer is a whole number. Adding zero to a number leaves it unchanged. Multiplying a number by one leaves it unchanged. For positive integers, multiplication is repeated addition. Two plus two equals four. Four divided by two equals two. A metre is one hundred centimetres. A second is a unit of time.

Expected (hypothesis): fail (not not_applicable)

Leader must verify this single contiguous edit violates the target clause, preserves all other relevant criteria and leaves physical correctness unchanged unless correctness is the target. Confirm the added elementary tutorial is genuinely redundant and obscures the requested answer for this prior; brief useful reminders would not violate the rule. This alternative targets redundancy, not A4/I2 reasoning depth.

Leader decision and reason: **pending**.

## perturb-v1-i3-gemma

Target: I3; level: intermediate; condition: P1R1_combined; source: evaluation-d68b3ae012d246766667794e.

Question: Visible light is part of what spectrum?

Frozen rule: Use course terminology accurately and explain unfamiliar specialist ideas while avoiding redundant redefinitions of the intermediate assumed core. A brief clarification that resolves a real ambiguity is helpful, not redundant. Always assess substantive answers. Judge conceptual role and precision, not terminology count or answer length.

Original answer:

> Visible light is described as a narrow segment of the electromagnetic spectrum to which the human eye responds. It falls within a specific wavelength range, between 400 nm and 750 nm, and is characterized by colors like red, orange, yellow, green, blue, and violet. This places it as a part of the broader electromagnetic spectrum.

Perturbed draft:

> Visible light is described as a narrow segment of the electromagnetic spectrum to which the human eye responds. It falls within a specific wavelength range, between 400 nm and 750 nm, and is characterized by colors like red, orange, yellow, green, blue, and violet. This places it as a part of the broader electromagnetic spectrum. Here are elementary reminders for the reader. An integer is a whole number. Adding zero to a number leaves it unchanged. Multiplying a number by one leaves it unchanged. For positive integers, multiplication is repeated addition. Two plus two equals four. Four divided by two equals two. A metre is one hundred centimetres. A second is a unit of time.

Expected (hypothesis): fail (not not_applicable)

Leader must verify this single contiguous edit violates the target clause, preserves all other relevant criteria and leaves physical correctness unchanged unless correctness is the target. Confirm the added elementary tutorial is genuinely redundant and obscures the requested answer for this prior; brief useful reminders would not violate the rule. This alternative targets redundancy, not A4/I2 reasoning depth.

Leader decision and reason: **pending**.

## perturb-v1-correctness-gpt-oss

Target: correctness; level: intermediate; condition: P1R1_combined; source: evaluation-2d7b46305f1bafb4a950f5e1.

Question: Displacement divided by time is equal to the average what?

Frozen rule: Correctness rubric / evidence supportedness, unchanged production definitions.

Original answer:

> Displacement divided by time is defined as the average velocity, which is a vector quantity describing both magnitude and direction of motion.

Perturbed draft:

> Displacement divided by time is defined as the average acceleration, which is a vector quantity describing both magnitude and direction of motion.

Expected (hypothesis): detect factual error

Leader must verify this single contiguous edit violates the target clause, preserves all other relevant criteria and leaves physical correctness unchanged unless correctness is the target. Confirm replacing velocity with acceleration changes the required scientific answer, not an incidental example.

Leader decision and reason: **pending**.

## perturb-v1-correctness-llama

Target: correctness; level: beginner; condition: P0R0_plain; source: evaluation-1e0f851322fae0fbbc24757d.

Question: Displacement divided by time is equal to the average what?

Frozen rule: Correctness rubric / evidence supportedness, unchanged production definitions.

Original answer:

> Displacement divided by time is equal to the average velocity.

Perturbed draft:

> Displacement divided by time is equal to the average acceleration.

Expected (hypothesis): detect factual error

Leader must verify this single contiguous edit violates the target clause, preserves all other relevant criteria and leaves physical correctness unchanged unless correctness is the target. Confirm replacing velocity with acceleration changes the required scientific answer, not an incidental example.

Leader decision and reason: **pending**.

## perturb-v1-correctness-gemma

Target: correctness; level: advanced; condition: P1R0_prompt_only; source: evaluation-f92ac4897a70c7c0ee2c690a.

Question: Displacement divided by time is equal to the average what?

Frozen rule: Correctness rubric / evidence supportedness, unchanged production definitions.

Original answer:

> Average velocity is defined as displacement divided by time. This is explicitly stated in multiple sources. For example, the equation v_avg = displacement / time = Δd / Δt is provided in evidence E1.

Perturbed draft:

> Average acceleration is defined as displacement divided by time. This is explicitly stated in multiple sources. For example, the equation v_avg = displacement / time = Δd / Δt is provided in evidence E1.

Expected (hypothesis): detect factual error

Leader must verify this single contiguous edit violates the target clause, preserves all other relevant criteria and leaves physical correctness unchanged unless correctness is the target. Confirm replacing velocity with acceleration changes the required scientific answer, not an incidental example.

Leader decision and reason: **pending**.

## perturb-v1-evidence-support-gpt-oss

Target: evidence_support; level: beginner; condition: P1R1_combined; source: evaluation-596274ade67d3e5d2e8e76e7.

Question: What colorful arc-shaped atmospheric phenomena are produced by a combination of refraction and reflection?

Frozen rule: Correctness rubric / evidence supportedness, unchanged production definitions.

Original answer:

> The colorful arc-shaped phenomenon created by refraction and reflection of sunlight in water droplets is a rainbow. Rainbows appear when light enters a water drop, is refracted, reflects off the back of the drop, and is refracted again as it leaves, producing a spectrum of colors in an arc.

Perturbed draft:

> The colorful arc-shaped phenomenon created by refraction and reflection of sunlight in water droplets is a rainbow. Rainbows appear when light enters a water drop, is refracted, reflects off the back of the drop, and is refracted again as it leaves, producing a spectrum of colors in an arc. Gold has atomic number 79.

Expected (hypothesis): mark added claim unsupported

Leader must verify this single contiguous edit violates the target clause, preserves all other relevant criteria and leaves physical correctness unchanged unless correctness is the target. Confirm the added true scientific statement is absent from every supplied evidence passage; this is a supportedness perturbation, not a known false fact.

Leader decision and reason: **pending**.

## perturb-v1-evidence-support-llama

Target: evidence_support; level: advanced; condition: P0R0_plain; source: evaluation-61092f163b50c684056eecc4.

Question: Massive quanta, like electrons, also act like macroscopic particles—something we expect, because they are the smallest what?

Frozen rule: Correctness rubric / evidence supportedness, unchanged production definitions.

Original answer:

> Massive quanta, like electrons, also act like macroscopic particles—something we expect, because they are the smallest units of matter.

Perturbed draft:

> Massive quanta, like electrons, also act like macroscopic particles—something we expect, because they are the smallest units of matter. Gold has atomic number 79.

Expected (hypothesis): mark added claim unsupported

Leader must verify this single contiguous edit violates the target clause, preserves all other relevant criteria and leaves physical correctness unchanged unless correctness is the target. Confirm the added true scientific statement is absent from every supplied evidence passage; this is a supportedness perturbation, not a known false fact.

Leader decision and reason: **pending**.

## perturb-v1-evidence-support-gemma

Target: evidence_support; level: beginner; condition: P1R0_prompt_only; source: evaluation-0d6884b50852b1b48ec28ea1.

Question: How does sap get to the tops of tall trees?

Frozen rule: Correctness rubric / evidence supportedness, unchanged production definitions.

Original answer:

> Sap rises in tall trees due to a process called transpiration, where water evaporates from leaves. This evaporation creates a negative pressure, which pulls the sap up through the xylem vessels like a chain held together by cohesive forces. Capillary action alone cannot fully explain this process.

Perturbed draft:

> Sap rises in tall trees due to a process called transpiration, where water evaporates from leaves. This evaporation creates a negative pressure, which pulls the sap up through the xylem vessels like a chain held together by cohesive forces. Capillary action alone cannot fully explain this process. Gold has atomic number 79.

Expected (hypothesis): mark added claim unsupported

Leader must verify this single contiguous edit violates the target clause, preserves all other relevant criteria and leaves physical correctness unchanged unless correctness is the target. Confirm the added true scientific statement is absent from every supplied evidence passage; this is a supportedness perturbation, not a known false fact.

Leader decision and reason: **pending**.
