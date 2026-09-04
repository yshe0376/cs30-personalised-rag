# Member 7 - student profile

Implement `cs30.ports.ProfileProvider`:

    `get(level: StudentLevel) -> StudentProfile`

Drop the real implementation next to `fixture.py`, then swap it into
`build_real_deps()` in `src/cs30/pipeline.py`. Nothing else changes.

`Week1ProfileProvider` in `provider.py` is the real Week 1 implementation. It
creates strict `StudentProfile` contracts with stable ids for all three levels.

## Week 1 acceptance

- Beginner, intermediate, and advanced all reach the prompt.
- The same question at three levels produces three answers.

## Notes

`topic_levels` and `confidence` are already in the contract for the
per-topic personalisation planned for week 2.
