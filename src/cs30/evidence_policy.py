"""The single source of truth for official Week 5 evidence eligibility."""

from cs30.contracts import ContentType

EVIDENCE_POLICY_ID = "w5-evidence-v1"
EVIDENCE_CONTENT_TYPES = (
    ContentType.BODY,
    ContentType.EXAMPLE,
    ContentType.FIGURE_CAPTION,
    ContentType.GLOSSARY,
    ContentType.TABLE,
    ContentType.EQUATION,
)
