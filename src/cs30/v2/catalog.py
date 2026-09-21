"""The v2 textbook catalogue and its exact three-book official set."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TextbookSpec:
    textbook_id: str
    provider: str
    title: str
    source_version: str
    source_name: str
    source_uri: str
    license: str
    parser_name: str
    selected_chapters: tuple[str, ...] = ()
    expected_source_sha256: str | None = None
    enabled: bool = False


# M1 freezes the set; raw source hashes are filled when M2 receives the retained
# source files.  An absent hash is therefore visible and cannot be mistaken for
# a verified source pin.
REQUIRED_TEXTBOOK_IDS: tuple[str, ...] = (
    "openstax_college_physics_2e",
    "ck12_peoples_physics_basic",
    "ck12_physics_concepts_intermediate",
)

TEXTBOOK_CATALOG: dict[str, TextbookSpec] = {
    "openstax_college_physics_2e": TextbookSpec(
        textbook_id="openstax_college_physics_2e",
        provider="openstax",
        title="College Physics 2e",
        source_version="2e",
        source_name="openstax_college_physics_2e.json",
        source_uri="https://openstax.org/details/books/college-physics-2e",
        license="CC BY 4.0",
        parser_name="openstax",
        enabled=True,
    ),
    "ck12_peoples_physics_basic": TextbookSpec(
        textbook_id="ck12_peoples_physics_basic",
        provider="ck12",
        title="People's Physics Book - Basic",
        source_version="SciQ Appendix A source edition",
        source_name="ck12_peoples_physics_basic.json",
        source_uri="http://www.ck12.org/book/Peoples-Physics-Book-Basic/",
        license="CC BY-NC 3.0",
        parser_name="ck12",
        enabled=True,
    ),
    "ck12_physics_concepts_intermediate": TextbookSpec(
        textbook_id="ck12_physics_concepts_intermediate",
        provider="ck12",
        title="CK-12 Physics Concepts - Intermediate",
        source_version="SciQ Appendix A source edition",
        source_name="ck12_physics_concepts_intermediate.json",
        source_uri="http://www.ck12.org/book/CK-12-Physics-Concepts-Intermediate/",
        license="CC BY-NC 3.0",
        parser_name="ck12",
        enabled=True,
    ),
}


def validate_catalog() -> None:
    if len(REQUIRED_TEXTBOOK_IDS) != 3 or len(set(REQUIRED_TEXTBOOK_IDS)) != 3:
        raise ValueError("v2 official catalogue must contain exactly three unique textbook IDs")
    if set(REQUIRED_TEXTBOOK_IDS) != set(TEXTBOOK_CATALOG):
        raise ValueError("catalogue keys must equal the frozen v2 textbook set")
    for textbook_id, spec in TEXTBOOK_CATALOG.items():
        if textbook_id != spec.textbook_id:
            raise ValueError(f"catalogue key does not match textbook_id: {textbook_id}")
        if not spec.source_name.strip():
            raise ValueError(f"source_name must not be empty: {textbook_id}")
        if spec.provider != spec.provider.casefold():
            raise ValueError(f"provider must be canonical lowercase: {textbook_id}")


def get_textbook_spec(textbook_id: str) -> TextbookSpec:
    validate_catalog()
    try:
        return TEXTBOOK_CATALOG[textbook_id]
    except KeyError as exc:
        raise ValueError(f"unknown textbook_id: {textbook_id}") from exc
