"""Runtime citation-integrity checks."""

from cs30.contracts import (
    EvidenceBundle,
    GeneratedAnswer,
    RetrievalResult,
    ValidatedAnswer,
)
from cs30.errors import CitationIntegrityError


def validate_citations(answer: GeneratedAnswer, retrieval: RetrievalResult) -> None:
    """Raise when an answer cites a chunk not supplied by retrieval."""

    allowed = {hit.chunk_id for hit in retrieval.hits}
    invalid = sorted(set(answer.citations) - allowed)
    if invalid:
        raise CitationIntegrityError(
            f"answer contains unknown citation IDs: {', '.join(invalid)}"
        )


def build_evidence_bundle(
    retrieval: RetrievalResult,
    *,
    retrieval_mode: str = "fixture",
    token_budget: int = 1200,
    provenance: dict[str, str] | None = None,
) -> EvidenceBundle:
    """Create stable E1/E2 identifiers without changing retrieved text."""

    items = []
    used_tokens = 0
    for hit in retrieval.hits:
        token_count = max(1, len(hit.text.split()))
        if items and used_tokens + token_count > token_budget:
            break
        evidence_id = f"E{len(items) + 1}"
        items.append(
            {
                "evidence_id": evidence_id,
                "chunk_id": hit.chunk_id,
                "text": hit.text,
                "chapter_id": hit.chapter_id,
                "source": hit.source,
                "source_locator": hit.source,
                "rank": hit.rank,
                "score": hit.score,
                "token_count": token_count,
            }
        )
        used_tokens += token_count
    return EvidenceBundle(
        query=retrieval.query,
        retrieval_mode=retrieval_mode,
        evidence_items=items,
        prompt_context=("\n\n".join(f"[{i['evidence_id']}] {i['text']}" for i in items) or None),
        citation_map={i["evidence_id"]: i["chunk_id"] for i in items},
        token_count=used_tokens,
        retrieval_provenance=retrieval.provenance,
        provenance=provenance or {},
    )


def resolve_and_validate(
    answer: GeneratedAnswer,
    bundle: EvidenceBundle,
) -> ValidatedAnswer:
    """Resolve model citation IDs and reject citations outside the bundle."""

    if answer.abstained:
        return ValidatedAnswer(
            answer=answer,
            resolved_citations=[],
            citation_status="skipped",
            provenance=bundle.provenance,
            abstained=True,
        )
    allowed_ids = set(bundle.citation_map)
    allowed_chunk_ids = set(bundle.citation_map.values())
    invalid = sorted(set(answer.citations) - allowed_ids - allowed_chunk_ids)
    if invalid:
        raise CitationIntegrityError(
            f"answer contains unknown evidence IDs: {', '.join(invalid)}"
        )
    return ValidatedAnswer(
        answer=answer,
        resolved_citations=[
            bundle.citation_map.get(citation, citation) for citation in answer.citations
        ],
        citation_status="passed",
        provenance=bundle.provenance,
        abstained=False,
    )


class EvidenceContextBuilder:
    """Named W5 façade for constructing an EvidenceBundle."""

    def __init__(self, token_budget: int = 1200) -> None:
        self.token_budget = token_budget

    def build(
        self,
        retrieval: RetrievalResult,
        *,
        retrieval_mode: str = "fixture",
        provenance: dict[str, str] | None = None,
    ) -> EvidenceBundle:
        return build_evidence_bundle(
            retrieval,
            retrieval_mode=retrieval_mode,
            token_budget=self.token_budget,
            provenance=provenance,
        )


class CitationResolver:
    """Resolve E-numbers or legacy chunk IDs to chunk IDs."""

    def resolve(self, answer: GeneratedAnswer, bundle: EvidenceBundle) -> ValidatedAnswer:
        return resolve_and_validate(answer, bundle)


class CitationValidator:
    """Named W5 façade for citation-integrity validation."""

    def validate(self, answer: GeneratedAnswer, bundle: EvidenceBundle) -> ValidatedAnswer:
        return resolve_and_validate(answer, bundle)
