# Personalisation Candidate List v0.1

This is an M3 provisional question-level screen. It does not replace M5 Evidence Role review.

## Summary

- Records screened: 20
- `full`: 1
- `endpoint_only`: 8
- `none`: 8
- `pending`: 3

## Screening Signals

- Evidence reliability: SciQ support exact/near-exact alignment with accepted OpenStax gold span.
- Richness: longer span, relational/comparison wording, non-glossary concept, and section-level teaching material signals.
- `alternative` evidence is not inferred here; it requires inspecting other candidate spans or full chapter context.
- This screen is intentionally conservative. It is not a retrieval benchmark,
  and it should not be used to compare BM25, dense, or hybrid retrieval quality.
- The first candidate pool favored questions whose answer string appeared in a
  top OpenStax span, so the next expansion pass should deliberately include
  questions where the answer is paraphrased or distributed across spans.

## Candidate Rows

### sciq-test-00770 - none

- Split: `proposed_test`
- Concept: `static_electricity_and_charge_conservation_of_charge`
- Question: No charge is actually created or destroyed when charges are separated as we have been discussing. rather, existing charges are moved about. in fact, in all situations the total amount of charge is always this?
- Answer: `constant`
- Alignment: `evidence_exact_substring_of_support` (0.9333)
- Reason: Core fact is reliable but too direct/thin for meaningful retrieval-side personalisation.

### sciq-test-00536 - none

- Split: `proposed_dev`
- Concept: `acceleration`
- Question: What term always refers to acceleration in the direction opposite to the direction of the velocity and always reduces speed, unlike negative acceleration?
- Answer: `deceleration`
- Alignment: `evidence_exact_substring_of_support` (0.8696)
- Reason: Core fact is reliable but too direct/thin for meaningful retrieval-side personalisation.

### sciq-test-00646 - none

- Split: `proposed_test`
- Concept: `magnets`
- Question: Magnets have a "north" and a "south" what?
- Answer: `pole`
- Alignment: `evidence_exact_substring_of_support` (0.9412)
- Reason: Core fact is reliable but too direct/thin for meaningful retrieval-side personalisation.

### sciq-test-00246 - endpoint_only

- Split: `proposed_dev`
- Concept: `nonconservative_forces`
- Question: When a car is brought to a stop by friction on level ground, it loses what?
- Answer: `kinetic energy`
- Alignment: `high_token_overlap` (0.95)
- Reason: Core evidence is reliable and likely supports Beginner vs Advanced contrast, but Intermediate may be unstable without M5 role review.

### sciq-test-00942 - endpoint_only

- Split: `proposed_test`
- Concept: `nuclear_weapons`
- Question: What type of bombs put a much larger fraction of their output into thermal energy than do conventional bombs?
- Answer: `nuclear`
- Alignment: `high_token_overlap` (0.9688)
- Reason: Core evidence is reliable and likely supports Beginner vs Advanced contrast, but Intermediate may be unstable without M5 role review.

### sciq-test-00335 - none

- Split: `proposed_test`
- Concept: `eddy_currents_and_magnetic_damping`
- Question: What do induction cooktops have under their surface?
- Answer: `electromagnets`
- Alignment: `evidence_exact_substring_of_support` (1.0)
- Reason: Core fact is reliable but too direct/thin for meaningful retrieval-side personalisation.

### sciq-test-00333 - endpoint_only

- Split: `proposed_dev`
- Concept: `convection`
- Question: If the water vapor condenses in liquid droplets as clouds form, what is released in the atmosphere?
- Answer: `heat`
- Alignment: `evidence_exact_substring_of_support` (1.0)
- Reason: Core evidence is reliable and likely supports Beginner vs Advanced contrast, but Intermediate may be unstable without M5 role review.

### sciq-test-00465 - endpoint_only

- Split: `proposed_test`
- Concept: `total_internal_reflection`
- Question: Because optics fibers are thin, entering light may strike the inside surface at greater than the critical angle, requiring attention to what?
- Answer: `refractive index`
- Alignment: `high_token_overlap` (0.9722)
- Reason: Core evidence is reliable and likely supports Beginner vs Advanced contrast, but Intermediate may be unstable without M5 role review.

### sciq-test-00116 - none

- Split: `proposed_dev`
- Concept: `archimedes_principle`
- Question: If a lump of clay is dropped into water, what will occur?
- Answer: `it will sink`
- Alignment: `evidence_exact_substring_of_support` (0.9259)
- Reason: Core fact is reliable but too direct/thin for meaningful retrieval-side personalisation.

### sciq-test-00709 - pending

- Split: `proposed_test`
- Concept: `electromagnetic_spectrum_glossary`
- Question: The full range of wavelengths and frequencies of electromagnetic radiation make up the ____________
- Answer: `electromagnetic spectrum`
- Alignment: `low_token_overlap` (0.5385)
- Reason: OpenStax evidence is accepted, but SciQ support alignment is low; inspect before using for personalisation.

### sciq-test-00401 - endpoint_only

- Split: `proposed_dev`
- Concept: `phase_change_and_latent_heat`
- Question: What is the transition from solid to vapor is called?
- Answer: `sublimation`
- Alignment: `evidence_exact_substring_of_support` (1.0)
- Reason: Core evidence is reliable and likely supports Beginner vs Advanced contrast, but Intermediate may be unstable without M5 role review.

### sciq-test-00974 - endpoint_only

- Split: `proposed_test`
- Concept: `maxwell_s_equations_electromagnetic_waves_predicted_and_observed`
- Question: Hertz proved that what type of waves travel at the speed of light?
- Answer: `electromagnetic`
- Alignment: `high_token_overlap` (0.8889)
- Reason: Core evidence is reliable and likely supports Beginner vs Advanced contrast, but Intermediate may be unstable without M5 role review.

### sciq-test-00614 - endpoint_only

- Split: `proposed_dev`
- Concept: `explosive_bolts_probe_separation_problem`
- Question: By exploding what the space probes get separated from their launchers?
- Answer: `bolts`
- Alignment: `high_token_overlap` (1.0)
- Reason: Core evidence is reliable and likely supports Beginner vs Advanced contrast, but Intermediate may be unstable without M5 role review.

### sciq-test-00315 - none

- Split: `proposed_dev`
- Concept: `simple_harmonic_motion_a_special_periodic_motion`
- Question: An object attached to a spring sliding on a frictionless surface is an uncomplicated type of what device?
- Answer: `simple harmonic oscillator`
- Alignment: `evidence_exact_substring_of_support` (0.64)
- Reason: Core fact is reliable but too direct/thin for meaningful retrieval-side personalisation.

### sciq-test-00540 - endpoint_only

- Split: `proposed_test`
- Concept: `particles_patterns_and_conservation_laws`
- Question: What action do particles of the same charge do to each other?
- Answer: `repel`
- Alignment: `high_token_overlap` (0.9789)
- Reason: Core evidence is reliable and likely supports Beginner vs Advanced contrast, but Intermediate may be unstable without M5 role review.

### sciq-test-00620 - full

- Split: `proposed_dev`
- Concept: `downhill_ski_energy_comparison_problem`
- Question: Downhill skiiers gain little advantage from a running start because the initial kinetic energy is small compared with the gain in what other energy form?
- Answer: `gravitational potential energy`
- Alignment: `high_token_overlap` (0.8868)
- Reason: Core evidence is reliable and the concept appears rich enough for Beginner/Intermediate/Advanced retrieval differences.

### sciq-test-00068 - none

- Split: `proposed_dev`
- Concept: `newton_s_second_law_of_motion_concept_of_a_system`
- Question: Newton’s second law of what is more than a definition; it is a relationship among acceleration, force, and mass?
- Answer: `motion`
- Alignment: `evidence_exact_substring_of_support` (0.5303)
- Reason: Core fact is reliable but too direct/thin for meaningful retrieval-side personalisation.

### sciq-test-00024 - pending

- Split: `proposed_dev`
- Concept: `chemical_energy_glossary`
- Question: Where is energy stored in a chemical substance?
- Answer: `between atoms`
- Alignment: `low_token_overlap` (0.5)
- Reason: OpenStax evidence is accepted, but SciQ support alignment is low; inspect before using for personalisation.

### sciq-test-00432 - none

- Split: `proposed_dev`
- Concept: `cohesion_and_adhesion_in_liquids_surface_tension_and_capillary_action`
- Question: One important phenomenon related to the relative strength of cohesive and adhesive forces is capillary action—the tendency of a fluid to be raised or suppressed in a narrow tube, or called this?
- Answer: `capillary tube`
- Alignment: `evidence_exact_substring_of_support` (0.3243)
- Reason: Core fact is reliable but too direct/thin for meaningful retrieval-side personalisation.

### sciq-test-00955 - pending

- Split: `proposed_dev`
- Concept: `temperature_scales_section_summary`
- Question: Fahrenheit, celsius, and kelvin are all units which measure what?
- Answer: `temperature`
- Alignment: `low_token_overlap` (0.5385)
- Reason: OpenStax evidence is accepted, but SciQ support alignment is low; inspect before using for personalisation.
