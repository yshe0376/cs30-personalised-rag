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
from cs30.v2.contracts import EvidenceBundle, GenerationQuestion, GoldQuestion, StudentProfile


def generation_question(question: str | GenerationQuestion | GoldQuestion) -> GenerationQuestion:
    """Keep MCQ choices across the generation boundary; never serialise Gold metadata."""

    if isinstance(question, GoldQuestion):
        return GenerationQuestion.from_gold(GoldQuestion.model_validate(question.model_dump()))
    if isinstance(question, GenerationQuestion):
        # Revalidate mutable mappings instead of trusting an earlier construction.
        return GenerationQuestion.model_validate(question.model_dump())
    return GenerationQuestion(kind="open_ended", question=question)


class V2PromptAdapter(PromptBuilder):
    """Preserve bundle contents while reusing v1 guidance, rules, and repairs."""

    prompt_version = "member7-v2-prompt-v3"
    base_prompt_version = "member7-v2-base-prompt-v3"

    def __init__(self, profile: StudentProfile, evidence: EvidenceBundle) -> None:
        self.citation_ids = {
            f"E{index}": item.chunk_id for index, item in enumerate(evidence.evidence_items, 1)
        }
        self._sources = {item.evidence_id: item for item in evidence.evidence_items}
        self._short_ids = {chunk_id: key for key, chunk_id in self.citation_ids.items()}
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
                    chunk_id=self._short_ids[item.chunk_id],
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
            citation_map={
                item.evidence_id: self._short_ids[item.chunk_id] for item in evidence.evidence_items
            },
            token_count=evidence.token_count,
        )

    def build_prompt(
        self, question: str | GenerationQuestion | GoldQuestion, *, personalise: bool = True
    ) -> str:
        request = generation_question(question)
        text = request.question
        if request.kind == "multiple_choice":
            text += "\n" + "\n".join(f"{label}. {request.options[label]}" for label in "ABCD")
        prompt = super().build(text, self._profile, self._evidence, personalise=personalise)
        if request.kind == "multiple_choice":
            prompt += (
                "\nMULTIPLE_CHOICE_REQUIREMENT:\n"
                "Choose from the supplied A-D options. final_choice must be A, B, C, or D; "
                "do not return null.\n"
            )
        return prompt

    def repair_prompt(self, original: str, raw_output: str, error: Exception) -> str:
        return super().build_repair(original, raw_output, error, self._evidence)

    def _format_item(self, item: PromptEvidenceItem) -> str:
        if not isinstance(item, PromptItem):
            raise TypeError("v2 prompting requires selected bundle evidence")
        source = self._sources[item.evidence_id]
        attributes = {
            "chunk_id": self._short_ids[source.chunk_id],
            "provider": source.provider,
            "textbook_id": source.textbook_id,
            "source": source.source_name,
            "source_locator": source.source_locator,
        }
        return (
            f"<evidence metadata={json.dumps(attributes, sort_keys=True)}>\n"
            f"{item.text}\n"
            "</evidence>"
        )
