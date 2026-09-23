"""M8 adapters for governed v2 evidence assembly and citation validation."""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping

from cs30.v2.contracts import (
    EvidenceBundle,
    EvidenceItem,
    GeneratedAnswer,
    RetrievalResult,
    ValidatedAnswer,
)
from cs30.v2.tokenization import RegexTokenCounter, TokenCounter

LOGGER = logging.getLogger(__name__)

EVIDENCE_BUILDER_VERSION = "m8-v2-evidence-bundle-1"
DEFAULT_TOKEN_BUDGET = 1500
TOKEN_BUDGET_POLICY = "observe_only"


class EvidenceBundleAdapter:
    """Build the M1-owned v2 EvidenceBundle without changing retrieval selection.

    The token budget remains observational, as decided for v1: dropping hits at
    this boundary would make M7's citation allow-list differ from M6's selected
    evidence. A caller that wants a different selection must produce a different
    RetrievalResult upstream.
    """

    def __init__(
        self,
        token_counter: TokenCounter | None = None,
        *,
        default_token_budget: int = DEFAULT_TOKEN_BUDGET,
        run_provenance: Mapping[str, str] | None = None,
    ) -> None:
        if default_token_budget <= 0:
            raise ValueError("default_token_budget must be positive")
        self.token_counter = token_counter or RegexTokenCounter()
        self.default_token_budget = default_token_budget
        self.run_provenance = dict(run_provenance or {})

    def build(
        self,
        retrieval: RetrievalResult,
        *,
        token_budget: int | None = None,
    ) -> EvidenceBundle:
        budget = self.default_token_budget if token_budget is None else token_budget
        if budget <= 0:
            raise ValueError("token_budget must be positive")
        if (
            retrieval.provenance is not None
            and retrieval.provenance.retrieval_mode is not retrieval.mode
        ):
            raise ValueError("retrieval mode does not match EvidenceProvenance")

        items = tuple(
            EvidenceItem(
                evidence_id=f"E{index}",
                provider=hit.provider,
                textbook_id=hit.textbook_id,
                document_id=hit.document_id,
                chunk_id=hit.chunk_id,
                chapter_id=hit.chapter_id,
                source_name=hit.source_name,
                page_or_location=hit.page_or_location,
                source_locator=hit.source_locator,
                text=hit.text,
                rank=hit.rank,
                score=hit.score,
                token_count=max(1, self.token_counter.count(hit.text)),
            )
            for index, hit in enumerate(retrieval.hits, start=1)
        )
        total_tokens = sum(item.token_count for item in items)
        if total_tokens > budget:
            LOGGER.warning(
                "v2 evidence exceeds the observational token budget; preserving all hits: "
                "tokens=%s budget=%s query=%r",
                total_tokens,
                budget,
                retrieval.query,
            )
        provenance = {
            **self.run_provenance,
            "evidence_builder_version": EVIDENCE_BUILDER_VERSION,
            "token_counter": self.token_counter.name,
            "token_budget": str(budget),
            "token_budget_policy": TOKEN_BUDGET_POLICY,
            "token_budget_exceeded": str(total_tokens > budget).lower(),
        }
        return EvidenceBundle(
            query=retrieval.query,
            retrieval_mode=retrieval.mode,
            evidence_items=items,
            prompt_context=_prompt_context(items),
            citation_map={item.evidence_id: item.chunk_id for item in items},
            token_count=total_tokens,
            retrieval_provenance=retrieval.provenance,
            run_provenance=provenance,
        )


class CitationValidatorAdapter:
    """Resolve only stable chunk-ID citations against one exact bundle."""

    def validate(
        self,
        answer: GeneratedAnswer,
        evidence: EvidenceBundle,
    ) -> ValidatedAnswer:
        if answer.abstained:
            return ValidatedAnswer(
                answer=answer,
                resolved_citations=(),
                citation_status="skipped",
                run_provenance=evidence.run_provenance,
            )

        allowed_chunk_ids = set(evidence.citation_map.values())
        if any(citation not in allowed_chunk_ids for citation in answer.citations):
            return ValidatedAnswer(
                answer=answer,
                resolved_citations=(),
                citation_status="failed",
                run_provenance=evidence.run_provenance,
            )
        return ValidatedAnswer(
            answer=answer,
            resolved_citations=answer.citations,
            citation_status="passed",
            run_provenance=evidence.run_provenance,
        )


def _prompt_context(items: tuple[EvidenceItem, ...]) -> str | None:
    """Render deterministic context with full source identity for M7 and the UI."""

    if not items:
        return None
    blocks = []
    for item in items:
        identity = {
            "evidence_id": item.evidence_id,
            "chunk_id": item.chunk_id,
            "provider": item.provider,
            "textbook_id": item.textbook_id,
            "document_id": item.document_id,
            "chapter_id": item.chapter_id,
            "source_name": item.source_name,
            "page_or_location": item.page_or_location,
            "source_locator": item.source_locator,
            "rank": item.rank,
            "score": item.score,
        }
        blocks.append(
            f"<evidence metadata={json.dumps(identity, ensure_ascii=False, sort_keys=True)}>\n"
            f"{item.text}\n"
            "</evidence>"
        )
    return "\n\n".join(blocks)


__all__ = [
    "CitationValidatorAdapter",
    "DEFAULT_TOKEN_BUDGET",
    "EVIDENCE_BUILDER_VERSION",
    "EvidenceBundleAdapter",
    "TOKEN_BUDGET_POLICY",
]

