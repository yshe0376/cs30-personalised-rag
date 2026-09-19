"""Read selected evidence through the frozen contracts, without retrieval I/O.

The integration pipeline still passes RetrievalResult. Native EvidenceBundle
callers use the same stable chunk-ID citation namespace (ADR-0001, 2026-09-05).
Bundle construction and citation-to-source resolution remain owned by M8.
"""

from collections.abc import Sequence
from typing import TypeAlias

from cs30.contracts import EvidenceBundle, EvidenceItem, RetrievalResult, RetrievedEvidence

GenerationEvidence: TypeAlias = EvidenceBundle | RetrievalResult
PromptEvidenceItem: TypeAlias = EvidenceItem | RetrievedEvidence


def evidence_items(evidence: GenerationEvidence) -> Sequence[PromptEvidenceItem]:
    """Return only the selected evidence, preserving text and ordering."""

    if isinstance(evidence, EvidenceBundle):
        return evidence.evidence_items
    if isinstance(evidence, RetrievalResult):
        return evidence.hits
    raise TypeError("generation requires EvidenceBundle or RetrievalResult")


def allowed_citation_ids(evidence: GenerationEvidence) -> list[str]:
    """E labels are for display only; the model cites stable chunk IDs."""

    return list(dict.fromkeys(item.chunk_id for item in evidence_items(evidence)))
