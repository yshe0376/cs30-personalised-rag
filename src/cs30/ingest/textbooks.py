"""Supported textbook catalogue and provider-neutral ingestion metadata.

The catalogue records provenance; it does not download copyrighted material.
Builds consume a local PDF or an already-normalised contract JSON.  The CK-12
URLs are the source pages cited by the SciQ paper's Appendix A and may now be
legacy links, so reproducibility ultimately depends on retaining the local
source file hash in the document contract.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class TextbookSpec:
    textbook_id: str
    title: str
    provider: str
    version: str
    source_url: str
    subject: str
    license: str
    source_title_markers: tuple[str, ...]

    @property
    def document_id_prefix(self) -> str:
        return self.textbook_id.replace("_", "-")


TEXTBOOKS: dict[str, TextbookSpec] = {
    "openstax_college_physics_2e": TextbookSpec(
        textbook_id="openstax_college_physics_2e",
        title="College Physics 2e",
        provider="OpenStax",
        version="2e",
        source_url="https://openstax.org/details/books/college-physics-2e",
        subject="physics",
        license="CC BY 4.0",
        source_title_markers=("college physics",),
    ),
    "ck12_peoples_physics_basic": TextbookSpec(
        textbook_id="ck12_peoples_physics_basic",
        title="People's Physics Book - Basic",
        provider="CK-12",
        version="SciQ Appendix A source edition",
        source_url="http://www.ck12.org/book/Peoples-Physics-Book-Basic/",
        subject="physics",
        license="CC BY-NC 3.0",
        source_title_markers=("people's physics book basic", "peoples physics book basic"),
    ),
    "ck12_physical_science_concepts_middle_school": TextbookSpec(
        textbook_id="ck12_physical_science_concepts_middle_school",
        title="CK-12 Physical Science Concepts For Middle School",
        provider="CK-12",
        version="SciQ Appendix A source edition",
        source_url=(
            "http://www.ck12.org/book/"
            "CK-12-Physical-Science-Concepts-For-Middle-School/"
        ),
        subject="physics+chemistry",
        license="CC BY-NC 3.0",
        source_title_markers=("physical science concepts for middle school",),
    ),
    "ck12_physical_science_middle_school": TextbookSpec(
        textbook_id="ck12_physical_science_middle_school",
        title="CK-12 Physical Science For Middle School",
        provider="CK-12",
        version="SciQ Appendix A source edition",
        source_url="http://www.ck12.org/book/CK-12-Physical-Science-For-Middle-School/",
        subject="physics+chemistry",
        license="CC BY-NC 3.0",
        source_title_markers=(
            "physical science for middle school",
            "physical science middle school",
        ),
    ),
    "ck12_physics_concepts_intermediate": TextbookSpec(
        textbook_id="ck12_physics_concepts_intermediate",
        title="CK-12 Physics Concepts - Intermediate",
        provider="CK-12",
        version="SciQ Appendix A source edition",
        source_url="http://www.ck12.org/book/CK-12-Physics-Concepts-Intermediate/",
        subject="physics",
        license="CC BY-NC 3.0",
        source_title_markers=("physics concepts intermediate",),
    ),
    "ck12_peoples_physics_concepts": TextbookSpec(
        textbook_id="ck12_peoples_physics_concepts",
        title="People's Physics Concepts",
        provider="CK-12",
        version="SciQ Appendix A source edition",
        source_url="http://www.ck12.org/book/Peoples-Physics-Concepts/",
        subject="physics",
        license="CC BY-NC 3.0",
        source_title_markers=("people's physics concepts", "peoples physics concepts"),
    ),
}

DEFAULT_TEXTBOOK_ID = "openstax_college_physics_2e"

def get_textbook(textbook_id: str) -> TextbookSpec:
    try:
        return TEXTBOOKS[textbook_id]
    except KeyError as exc:
        choices = ", ".join(TEXTBOOKS)
        raise ValueError(f"unknown textbook_id {textbook_id!r}; choose one of: {choices}") from exc


def main() -> int:
    """Print the supported textbook catalogue as stable JSON."""

    print(json.dumps([asdict(TEXTBOOKS[key]) for key in TEXTBOOKS], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
