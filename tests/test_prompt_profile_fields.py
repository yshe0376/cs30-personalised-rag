"""The prompt exposes a fixed set of profile fields, not whatever the model holds.

The expected values below were captured from the implementation *before* the
switch to explicit field selection, and are hard-coded on purpose. Regenerating
them with the current selection logic would let a mistake in that logic agree
with itself and still pass.
"""

from __future__ import annotations

import hashlib

import pytest

from cs30.contracts import (
    RetrievalMode,
    RetrievalResult,
    RetrievedEvidence,
    StudentLevel,
    StudentProfile,
)
from cs30.generation.prompt import PromptBuilder
from cs30.profile.provider import Week1ProfileProvider


def _hit(chunk_id: str, text: str) -> RetrievedEvidence:
    return RetrievedEvidence(
        chunk_id=chunk_id,
        text=text,
        chapter_id="1",
        source="fixture://openstax/physics#ch01",
        score=0.9,
        rank=1,
        retriever_type=RetrievalMode.BM25,
    )


_ENGLISH = RetrievalResult(
    query="What is acceleration?",
    mode=RetrievalMode.BM25,
    hits=[_hit("chunk_ch01_0001", "Acceleration is the rate of change of velocity.")],
)
_CHINESE = RetrievalResult(
    query="什么是加速度？",
    mode=RetrievalMode.BM25,
    hits=[_hit("chunk_ch01_0002", "加速度是速度随时间的变化率。")],
)

_PROVIDER = Week1ProfileProvider(profile_prefix="local-rag")


def _case(name: str) -> tuple[RetrievalResult, StudentProfile]:
    if name == "synthetic_beginner":
        return _ENGLISH, _PROVIDER.get(StudentLevel.BEGINNER)
    if name == "synthetic_intermediate":
        return _ENGLISH, _PROVIDER.get(StudentLevel.INTERMEDIATE)
    if name == "synthetic_advanced":
        return _ENGLISH, _PROVIDER.get(StudentLevel.ADVANCED)
    if name == "topic_levels_populated":
        return _ENGLISH, StudentProfile(
            profile_id="p-topics",
            level=StudentLevel.INTERMEDIATE,
            topic_levels={
                "mechanics": StudentLevel.ADVANCED,
                "optics": StudentLevel.BEGINNER,
            },
            confidence=0.55,
        )
    if name == "confidence_none":
        return _ENGLISH, StudentProfile(
            profile_id="p-none", level=StudentLevel.BEGINNER, confidence=None
        )
    if name == "confidence_zero":
        return _ENGLISH, StudentProfile(
            profile_id="p-zero", level=StudentLevel.ADVANCED, confidence=0.0
        )
    if name == "chinese":
        return _CHINESE, StudentProfile(
            profile_id="p-中文",
            level=StudentLevel.INTERMEDIATE,
            topic_levels={"力学": StudentLevel.ADVANCED},
            confidence=0.75,
        )
    raise AssertionError(f"unknown case: {name}")


# name -> (sha256 of the whole prompt, the STUDENT_PROFILE_JSON line verbatim)
_GOLDEN: dict[str, tuple[str, str]] = {
    "synthetic_beginner": (
        "af1d43546edbbd01",
        '{"confidence": 1.0, "level": "beginner", "profile_id": "local-rag-beginner",'
        ' "schema_version": "1.0", "topic_levels": {}}',
    ),
    "synthetic_intermediate": (
        "506b5e3e9e47d608",
        '{"confidence": 1.0, "level": "intermediate", "profile_id":'
        ' "local-rag-intermediate", "schema_version": "1.0", "topic_levels": {}}',
    ),
    "synthetic_advanced": (
        "b3a12f99c565616d",
        '{"confidence": 1.0, "level": "advanced", "profile_id": "local-rag-advanced",'
        ' "schema_version": "1.0", "topic_levels": {}}',
    ),
    "topic_levels_populated": (
        "4755396983583794",
        '{"confidence": 0.55, "level": "intermediate", "profile_id": "p-topics",'
        ' "schema_version": "1.0", "topic_levels": {"mechanics": "advanced", "optics":'
        ' "beginner"}}',
    ),
    "confidence_none": (
        "c397df3bc813fce7",
        '{"confidence": null, "level": "beginner", "profile_id": "p-none",'
        ' "schema_version": "1.0", "topic_levels": {}}',
    ),
    "confidence_zero": (
        "f13ee73cb08f6d13",
        '{"confidence": 0.0, "level": "advanced", "profile_id": "p-zero",'
        ' "schema_version": "1.0", "topic_levels": {}}',
    ),
    "chinese": (
        "fe90ff42bbd80fa1",
        '{"confidence": 0.75, "level": "intermediate", "profile_id": "p-\\u4e2d\\u6587",'
        ' "schema_version": "1.0", "topic_levels": {"\\u529b\\u5b66": "advanced"}}',
    ),
}


def _profile_json_line(prompt: str) -> str:
    lines = prompt.split("\n")
    marker = lines.index("STUDENT_PROFILE_JSON:")
    return lines[marker + 1]


@pytest.mark.parametrize("name", sorted(_GOLDEN))
def test_prompt_profile_line_is_unchanged(name: str) -> None:
    retrieval, profile = _case(name)
    prompt = PromptBuilder().build(retrieval.query, profile, retrieval)

    assert _profile_json_line(prompt) == _GOLDEN[name][1]


@pytest.mark.parametrize("name", sorted(_GOLDEN))
def test_whole_prompt_is_byte_identical(name: str) -> None:
    retrieval, profile = _case(name)
    prompt = PromptBuilder().build(retrieval.query, profile, retrieval)
    digest = hashlib.sha256(prompt.encode("utf-8")).hexdigest()

    assert digest.startswith(_GOLDEN[name][0])


def test_storage_metadata_never_reaches_the_prompt() -> None:
    """A field added for persistence must not appear in the prompt by itself."""

    class ProfileWithStorageMetadata(StudentProfile):
        last_updated: str = "2026-09-05T12:00:00Z"
        attempts: int = 4

    retrieval = _ENGLISH
    profile = ProfileWithStorageMetadata(
        profile_id="p-storage", level=StudentLevel.BEGINNER, confidence=1.0
    )
    prompt = PromptBuilder().build(retrieval.query, profile, retrieval)

    assert "last_updated" not in prompt
    assert "2026-09-05T12:00:00Z" not in prompt
    assert "attempts" not in prompt
    assert '"level": "beginner"' in prompt


def test_prompt_field_list_tracks_the_contract() -> None:
    """Adding a StudentProfile field is a decision, not a silent prompt change."""

    from cs30.generation.prompt import PROMPT_PROFILE_FIELDS

    assert set(PROMPT_PROFILE_FIELDS) == set(StudentProfile.model_fields)
