"""Adapt selected v2 evidence to M7's existing level-aware prompt builder."""

from __future__ import annotations

import json

from cs30.contracts import EvidenceBundle as PromptBundle
from cs30.contracts import EvidenceItem as PromptItem
from cs30.contracts import RetrievalMode as PromptRetrievalMode
from cs30.contracts import StudentLevel as PromptLevel
from cs30.contracts import StudentProfile as PromptProfile
from cs30.generation.evidence import PromptEvidenceItem
from cs30.generation.prompt import PromptBuilder
from cs30.v2.contracts import EvidenceBundle, StudentProfile


class V2PromptAdapter(PromptBuilder):
    """Preserve bundle contents while reusing v1 guidance, rules, and repairs."""

    def __init__(self, profile: StudentProfile, evidence: EvidenceBundle) -> None:
        self._sources = {item.evidence_id: item for item in evidence.evidence_items}
        self._profile = PromptProfile(
            profile_id=profile.profile_id,
            level=PromptLevel(profile.level.value),
            topic_levels={
                key: PromptLevel(level.value) for key, level in profile.topic_levels.items()
            },
            confidence=profile.confidence,
        )
        self._evidence = PromptBundle(
            query=evidence.query,
            retrieval_mode=PromptRetrievalMode(evidence.retrieval_mode.value),
            evidence_items=[
                PromptItem(
                    evidence_id=item.evidence_id,
                    chunk_id=item.chunk_id,
                    text=item.text,
                    chapter_id=item.chapter_id,
                    source=item.source_name,
                    source_locator=item.source_locator,
                    rank=item.rank,
                    score=item.score,
                    token_count=item.token_count,
                )
                for item in evidence.evidence_items
            ],
            citation_map=dict(evidence.citation_map),
            token_count=evidence.token_count,
        )

    def build_prompt(self, question: str) -> str:
        return super().build(question, self._profile, self._evidence)

    def repair_prompt(self, original: str, raw_output: str, error: Exception) -> str:
        return super().build_repair(original, raw_output, error, self._evidence)

    def _format_item(self, item: PromptEvidenceItem) -> str:
        if not isinstance(item, PromptItem):
            raise TypeError("v2 prompting requires selected bundle evidence")
        source = self._sources[item.evidence_id]
        attributes = {
            "chunk_id": source.chunk_id,
            "provider": source.provider,
            "textbook_id": source.textbook_id,
            "document_id": source.document_id,
            "chapter_id": source.chapter_id,
            "source": source.source_name,
            "source_locator": source.source_locator,
            "rank": source.rank,
            "score": source.score,
        }
        return (
            f"<evidence metadata={json.dumps(attributes, sort_keys=True)}>\n"
            f"{item.text}\n"
            "</evidence>"
        )
