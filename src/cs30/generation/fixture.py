"""Fixture generator.

No model is called. The answer is assembled from the top retrieved chunk so the
citation is always genuinely grounded in the retrieval input, and the requested
level visibly changes the wording.
"""

from cs30.contracts import (
    EvidenceBundle,
    GeneratedAnswer,
    RetrievalResult,
    StudentLevel,
    StudentProfile,
)

_LEVEL_TEMPLATES = {
    StudentLevel.BEGINNER: "In simple terms, the textbook says: {evidence}",
    StudentLevel.INTERMEDIATE: "According to the textbook: {evidence}",
    StudentLevel.ADVANCED: (
        "The source states: {evidence} At this level you would also relate it to "
        "the formal definition and its limiting cases."
    ),
}

_NO_EVIDENCE = (
    "The retrieved evidence does not cover this question, so no grounded answer "
    "can be given from the available material."
)


class FixtureAnswerGenerator:
    """Restate the top hit at the requested level, or abstain."""

    def generate(
        self,
        question: str,
        profile: StudentProfile,
        retrieval: RetrievalResult,
    ) -> GeneratedAnswer:
        if not retrieval.hits:
            return GeneratedAnswer(explanation=_NO_EVIDENCE, abstained=True)

        top = retrieval.hits[0]
        template = _LEVEL_TEMPLATES[profile.level]
        return GeneratedAnswer(
            explanation=template.format(evidence=top.text),
            citations=[top.chunk_id],
        )

    def generate_from_bundle(
        self,
        question: str,
        profile: StudentProfile,
        bundle: EvidenceBundle,
    ) -> GeneratedAnswer:
        """Consume the packaged evidence seam without changing legacy output IDs."""

        if not bundle.evidence_items:
            return GeneratedAnswer(explanation=_NO_EVIDENCE, abstained=True)
        top = bundle.evidence_items[0]
        template = _LEVEL_TEMPLATES[profile.level]
        return GeneratedAnswer(
            explanation=template.format(evidence=top.text),
            citations=[top.chunk_id],
        )
