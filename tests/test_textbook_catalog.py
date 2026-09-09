"""Provider-neutral textbook catalogue and compatibility boundary."""

from cs30.contracts import OpenStaxChapter, OpenStaxDocument, TextbookChapter, TextbookDocument
from cs30.ingest import DEFAULT_TEXTBOOK_ID, TEXTBOOKS, get_textbook
from cs30.ingest.textbooks import chapter_number


def test_generic_contract_names_preserve_v1_compatibility() -> None:
    assert TextbookDocument is OpenStaxDocument
    assert TextbookChapter is OpenStaxChapter


def test_catalog_contains_openstax_and_the_five_sciq_physics_ck12_books() -> None:
    assert DEFAULT_TEXTBOOK_ID == "openstax_college_physics_2e"
    assert len(TEXTBOOKS) == 6
    expected_ck12 = {
        "ck12_peoples_physics_basic": ("People's Physics Book - Basic", "physics"),
        "ck12_physical_science_concepts_middle_school": (
            "CK-12 Physical Science Concepts For Middle School",
            "physics+chemistry",
        ),
        "ck12_physical_science_middle_school": (
            "CK-12 Physical Science For Middle School",
            "physics+chemistry",
        ),
        "ck12_physics_concepts_intermediate": ("CK-12 Physics Concepts - Intermediate", "physics"),
        "ck12_peoples_physics_concepts": ("People's Physics Concepts", "physics"),
    }
    assert set(TEXTBOOKS) == {DEFAULT_TEXTBOOK_ID, *expected_ck12}
    assert {
        textbook_id: (spec.title, spec.subject)
        for textbook_id, spec in TEXTBOOKS.items()
        if spec.provider == "CK-12"
    } == expected_ck12
    assert all(spec.source_url for spec in TEXTBOOKS.values())
    assert all(
        spec.license == "CC BY-NC 3.0"
        for spec in TEXTBOOKS.values()
        if spec.provider == "CK-12"
    )


def test_unknown_textbook_lists_valid_choices() -> None:
    try:
        get_textbook("missing")
    except ValueError as exc:
        assert "openstax_college_physics_2e" in str(exc)
        assert "ck12_peoples_physics_basic" in str(exc)
    else:
        raise AssertionError("unknown textbook must fail")


def test_chapter_number_supports_openstax_and_legacy_ck12_bookmarks() -> None:
    assert chapter_number("Chapter 3 Motion") == "3"
    assert chapter_number("3. Motion") == "3"
    assert chapter_number("3 Motion") == "3"
    assert chapter_number("3.1 Velocity") is None
