"""The v2 textbook catalogue: the frozen required set and the providers it must cover."""

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
    # SHA-256 of M2's delivered parse of that source, which parsed builds read
    # instead of re-parsing the PDF.
    expected_parsed_sha256: str | None = None
    # Some providers deliver parsed files in a different Release archive.
    parsed_release_tag: str | None = None
    parsed_archive_name: str | None = None
    parsed_archive_member: str | None = None
    # Raw CK-12 PDF parsing is not vendored in this repository yet.
    supports_raw: bool = True
    # False until source-specific licence and parser QA review permit use.
    source_approved: bool = True
    enabled: bool = False


# M1 freezes the set; the number of books is whatever this tuple holds. Every
# entry is pinned to the exact source and parsed delivery selected for v2.
REQUIRED_TEXTBOOK_IDS: tuple[str, ...] = (
    "openstax_college_physics_2e",
    "openstax_physics",
    "openstax_college_physics_ap_2e",
    "ck12_peoples_physics_concepts",
)

# An official v2 corpus must contain at least one book from each provider.
REQUIRED_PROVIDERS: tuple[str, ...] = ("openstax", "ck12")

TEXTBOOK_CATALOG: dict[str, TextbookSpec] = {
    "openstax_college_physics_2e": TextbookSpec(
        textbook_id="openstax_college_physics_2e",
        provider="openstax",
        title="College Physics 2e",
        source_version="2e",
        source_name="openstax_college_physics_2e",
        source_uri="https://openstax.org/details/books/college-physics-2e",
        license="CC BY 4.0",
        parser_name="openstax",
        selected_chapters=tuple(str(chapter) for chapter in range(1, 35)),
        expected_source_sha256=(
            "sha256:a052d9fae2a90e135a74d70c001a78bb49b83280be58191e108d5de577699bb6"
        ),
        expected_parsed_sha256=(
            "sha256:548281102331a1ecfac3ff928ac98dfdb2bbec748cc73dcd89513c555c8f58da"
        ),
        enabled=True,
    ),
    "openstax_physics": TextbookSpec(
        textbook_id="openstax_physics",
        provider="openstax",
        title="Physics",
        source_version="1e",
        source_name="openstax_physics",
        source_uri="https://openstax.org/details/books/physics",
        license="CC BY 4.0",
        parser_name="openstax",
        selected_chapters=tuple(str(chapter) for chapter in range(1, 24)),
        expected_source_sha256=(
            "sha256:a3f75487411ef13d0270c65fc801ceff2b28e6b339afed9b407fe477f7e8453e"
        ),
        expected_parsed_sha256=(
            "sha256:16e3414de0ec4e798dd01c4a24a768d0729cbb1d52972767a9697649a1b69e63"
        ),
        enabled=True,
    ),
    # About 94% of this edition's retrievable text is verbatim College Physics
    # 2e; the build reports those blocks as cross-textbook duplicate groups.
    "openstax_college_physics_ap_2e": TextbookSpec(
        textbook_id="openstax_college_physics_ap_2e",
        provider="openstax",
        title="College Physics for AP® Courses 2e",
        source_version="2e",
        source_name="openstax_college_physics_ap_2e",
        source_uri="https://openstax.org/details/books/college-physics-ap-courses-2e",
        license="CC BY 4.0",
        parser_name="openstax",
        selected_chapters=tuple(str(chapter) for chapter in range(1, 35)),
        expected_source_sha256=(
            "sha256:de438d7a0ed13339340d3e6bb93346920ef146c99e1275e8c84ba476555943d7"
        ),
        expected_parsed_sha256=(
            "sha256:be096dc24ef5dccad587e7222a522efaf7b98c4dd4f77ef2b6cc989647322746"
        ),
        enabled=True,
    ),
    "ck12_peoples_physics_concepts": TextbookSpec(
        textbook_id="ck12_peoples_physics_concepts",
        provider="ck12",
        title="CK-12 People's Physics Concepts (With Answers)",
        source_version="2016-09-09",
        source_name="ck12_peoples_physics_concepts",
        source_uri="https://www.ck12.org/book/peoples-physics-concepts/",
        # The licence notice printed in this 2016-09-09 PDF; it also requires
        # the attribution link http://www.ck12.org/saythanks.
        license="CC BY-NC 3.0",
        parser_name="ck12",
        selected_chapters=tuple(str(chapter) for chapter in range(1, 21)),
        expected_source_sha256=(
            "sha256:6e8bbab8107fd79e9a8ce1487c938b85cd8101edd756ba61aac9448952daebe2"
        ),
        expected_parsed_sha256=(
            "sha256:1039bc79faf12609203b3d8dcef5d4aeec69b1e5fbe2e85cc1963d7be5ed0e66"
        ),
        parsed_release_tag="M2_ck12",
        parsed_archive_name="ck12_parser_v1_1_0.2.zip",
        parsed_archive_member=(
            "ck12_parser_v1_1_0/ck12_output_without_chapter_21/"
            "openstax_document.json"
        ),
        supports_raw=False,
        # Approved by M1 on 2026-10-14 for development and official builds.
        source_approved=True,
        enabled=True,
    ),
}


def validate_catalog() -> None:
    if not REQUIRED_TEXTBOOK_IDS or len(set(REQUIRED_TEXTBOOK_IDS)) != len(
        REQUIRED_TEXTBOOK_IDS
    ):
        raise ValueError("v2 catalogue must contain at least one textbook and no duplicates")
    if set(REQUIRED_TEXTBOOK_IDS) != set(TEXTBOOK_CATALOG):
        raise ValueError("catalogue keys must equal the frozen v2 textbook set")
    if not REQUIRED_PROVIDERS or any(
        provider != provider.casefold() for provider in REQUIRED_PROVIDERS
    ):
        raise ValueError("required providers must be canonical lowercase names")
    for textbook_id, spec in TEXTBOOK_CATALOG.items():
        if textbook_id != spec.textbook_id:
            raise ValueError(f"catalogue key does not match textbook_id: {textbook_id}")
        # source_name enters every locator and the corpus hash. It is the
        # textbook_id, or textbook_id/<part> if one book is ever split across
        # several source files; a file extension would tie identity to format.
        if spec.source_name != textbook_id and not spec.source_name.startswith(
            textbook_id + "/"
        ):
            raise ValueError(
                f"source_name must be the textbook_id or textbook_id/<part>: {textbook_id}"
            )
        if "." in spec.source_name.rsplit("/", 1)[-1]:
            raise ValueError(f"source_name must not carry a file extension: {textbook_id}")
        if spec.provider != spec.provider.casefold():
            raise ValueError(f"provider must be canonical lowercase: {textbook_id}")


def get_textbook_spec(textbook_id: str) -> TextbookSpec:
    validate_catalog()
    try:
        return TEXTBOOK_CATALOG[textbook_id]
    except KeyError as exc:
        raise ValueError(f"unknown textbook_id: {textbook_id}") from exc


def missing_required_providers(
    textbook_ids: tuple[str, ...],
    required_providers: tuple[str, ...] = REQUIRED_PROVIDERS,
) -> tuple[str, ...]:
    """Return the required providers that none of ``textbook_ids`` comes from."""

    covered = {get_textbook_spec(textbook_id).provider for textbook_id in textbook_ids}
    return tuple(provider for provider in required_providers if provider not in covered)
