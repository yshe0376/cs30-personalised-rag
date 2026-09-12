import json
import zipfile
from pathlib import Path

import pytest

from cs30.contracts import OpenStaxChapter, OpenStaxDocument, TextBlock
from cs30.evaluation import load_openstax_archive, write_prepared_corpus
from cs30.evaluation.cli import main


def _document(
    chapter_id: str,
    text: str,
    *,
    document_hash: str = "source-hash",
) -> OpenStaxDocument:
    return OpenStaxDocument(
        document_id="openstax-test-book",
        title="College Physics 2e",
        version="2e",
        source="https://openstax.org/details/books/college-physics-2e",
        document_hash=document_hash,
        parser_version="1.2.0",
        text=text,
        chapters=[
            OpenStaxChapter(
                chapter_id=chapter_id,
                title=f"Chapter {chapter_id}",
                char_start=0,
                char_end=len(text),
            )
        ],
        blocks=[
            TextBlock(
                block_id=f"block-{chapter_id}",
                chapter_id=chapter_id,
                content_type="body",
                char_start=0,
                char_end=len(text),
            )
        ],
    )


def _archive(path: Path, documents: list[tuple[str, OpenStaxDocument]]) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        for folder, document in documents:
            archive.writestr(
                f"parsed_openstax_ch{folder}/openstax_document.json",
                document.model_dump_json(),
            )
        archive.writestr("__MACOSX/._parsed_openstax_ch1", b"not corpus data")


def test_archive_is_merged_into_one_document_coordinate_system(tmp_path: Path) -> None:
    archive_path = tmp_path / "data.zip"
    _archive(
        archive_path,
        [
            ("2", _document("2", "Second chapter.")),
            ("1", _document("1", "First chapter.")),
        ],
    )

    corpus = load_openstax_archive(archive_path)

    assert corpus.corpus_version.startswith("openstax-test-book-ch01-02-v")
    assert len(corpus.corpus_version) < 80
    assert [chapter.chapter_id for chapter in corpus.document.chapters] == ["1", "2"]
    assert corpus.document.text == "First chapter.\n\nSecond chapter."
    assert corpus.document.chapters[0].char_start == 0
    assert corpus.document.chapters[0].char_end == len("First chapter.")
    assert corpus.document.chapters[1].char_start == len("First chapter.\n\n")
    second_block = corpus.document.blocks[1]
    assert corpus.document.text[second_block.char_start : second_block.char_end] == (
        "Second chapter."
    )
    assert corpus.manifest()["chapter_entries"]["1"].endswith(
        "parsed_openstax_ch1/openstax_document.json"
    )


def test_archive_can_select_a_subset_of_chapters(tmp_path: Path) -> None:
    archive_path = tmp_path / "data.zip"
    _archive(
        archive_path,
        [("1", _document("1", "First.")), ("2", _document("2", "Second."))],
    )

    corpus = load_openstax_archive(archive_path, chapters=["2"])

    assert corpus.document.text == "Second."
    assert [chapter.chapter_id for chapter in corpus.document.chapters] == ["2"]
    assert corpus.document.chapters[0].char_start == 0
    assert corpus.corpus_version.startswith("openstax-test-book-ch02-v")


def test_separator_is_part_of_the_corpus_identity(tmp_path: Path) -> None:
    archive_path = tmp_path / "data.zip"
    _archive(
        archive_path,
        [("1", _document("1", "First.")), ("2", _document("2", "Second."))],
    )

    default = load_openstax_archive(archive_path)
    alternate = load_openstax_archive(archive_path, separator="\n")

    assert default.corpus_version != alternate.corpus_version


def test_archive_rejects_mismatched_source_identity(tmp_path: Path) -> None:
    archive_path = tmp_path / "data.zip"
    _archive(
        archive_path,
        [
            ("1", _document("1", "First.")),
            ("2", _document("2", "Second.", document_hash="different-hash")),
        ],
    )

    with pytest.raises(ValueError, match="do not share one source identity"):
        load_openstax_archive(archive_path)


def test_archive_error_names_the_expected_entry_layout(tmp_path: Path) -> None:
    archive_path = tmp_path / "empty.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("README.txt", "not a parsed archive")

    with pytest.raises(
        ValueError,
        match=r"parsed_openstax_ch\*/openstax_document\.json",
    ):
        load_openstax_archive(archive_path)


def test_prepared_corpus_writes_portable_artifacts_once(tmp_path: Path) -> None:
    archive_path = tmp_path / "data.zip"
    _archive(archive_path, [("1", _document("1", "First."))])
    corpus = load_openstax_archive(archive_path)
    output_dir = tmp_path / "prepared"

    paths = write_prepared_corpus(corpus, output_dir)

    document_path = Path(paths["document"])
    manifest_path = Path(paths["manifest"])
    assert json.loads(document_path.read_text(encoding="utf-8"))["text"] == "First."
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["corpus_version"] == corpus.corpus_version
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        write_prepared_corpus(corpus, output_dir)


def test_prepare_corpus_cli_writes_the_real_handoff_shape(tmp_path: Path, capsys) -> None:
    archive_path = tmp_path / "data.zip"
    _archive(archive_path, [("1", _document("1", "First."))])
    output_dir = tmp_path / "prepared"

    assert (
        main(
            [
                "prepare-corpus",
                "--archive",
                str(archive_path),
                "--output-dir",
                str(output_dir),
            ]
        )
        == 0
    )
    summary = json.loads(capsys.readouterr().out)
    assert summary["chapter_count"] == 1
    assert (output_dir / "openstax_document.json").is_file()
    assert (output_dir / "corpus_manifest.json").is_file()
