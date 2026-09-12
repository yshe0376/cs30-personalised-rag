import json
from pathlib import Path

import pytest

import cs30.evaluation.io as evaluation_io
from cs30.contracts import OpenStaxChapter, OpenStaxDocument, TextBlock
from cs30.evaluation import (
    GoldSample,
    SpanResolutionStatus,
    load_normalized_gold,
    normalize_gold_samples,
    write_normalized_gold,
)
from cs30.evaluation.openstax_archive import OpenStaxArchiveCorpus


@pytest.fixture
def test_corpus() -> OpenStaxArchiveCorpus:
    first = "Alpha."
    second = "Beta."
    separator = "\n\n"
    document = OpenStaxDocument(
        document_id="test-book",
        title="Test Book",
        version="1",
        source="test",
        document_hash="test-hash",
        parser_version="test-parser",
        text=first + separator + second,
        chapters=[
            OpenStaxChapter(chapter_id="one", title="One", char_start=0, char_end=len(first)),
            OpenStaxChapter(
                chapter_id="two",
                title="Two",
                char_start=len(first) + len(separator),
                char_end=len(first) + len(separator) + len(second),
            ),
        ],
        blocks=[
            TextBlock(block_id="one-alpha", chapter_id="one", char_start=0, char_end=len(first)),
            TextBlock(
                block_id="two-beta",
                chapter_id="two",
                char_start=len(first) + len(separator),
                char_end=len(first) + len(separator) + len(second),
            ),
        ],
    )
    return OpenStaxArchiveCorpus(
        document=document,
        corpus_version="test-book-ch01-02-vabc123",
        archive_sha256="sha256:test",
        separator=separator,
        chapter_entries={"one": "one.json", "two": "two.json"},
    )


@pytest.fixture
def raw_samples() -> list[GoldSample]:
    return [
        GoldSample.model_validate(
            {
                "question_id": "question-1",
                "source_split": "test",
                "question": "Which statement is supported?",
                "options": {
                    "A": {"text": "Alpha", "source_field": "correct_answer"},
                    "B": {"text": "Beta", "source_field": "distractor1"},
                    "C": {"text": "Gamma", "source_field": "distractor2"},
                    "D": {"text": "Delta", "source_field": "distractor3"},
                },
                "gold_answer": "A",
                "gold_answer_text": "Alpha",
                "answerable": True,
                "gold_core_evidence_sets": [
                    [
                        {
                            "span_id": "core-alpha",
                            "document_id": "test-book",
                            "chapter_id": "one",
                            "block_id": "one-alpha",
                            "char_start": 0,
                            "char_end": 6,
                            "verbatim_text": "Alpha.",
                            "sufficiency": "core_sufficient",
                            "annotation_note": "Direct support.",
                        }
                    ]
                ],
                "partial_evidence": [
                    {
                        "span_id": "partial-beta",
                        "document_id": "test-book",
                        "chapter_id": "two",
                        "block_id": "two-beta",
                        "char_start": 0,
                        "char_end": 5,
                        "verbatim_text": "Beta.",
                        "sufficiency": "partial",
                        "annotation_note": "Related context.",
                    }
                ],
                "question_difficulty": "easy",
                "question_type": "identification",
                "concept_group": "test-concept",
                "personalisation_eligibility": "none",
                "eligibility_reason": "Fixture question.",
                "split": "proposed_test",
                "corpus_version": "m3-raw-corpus",
                "parser_version": "test-parser",
                "gold_annotation_version": "m3-gold-v0.1",
                "annotation_status": "m3_initial",
                "review_record_id": "review-question-1",
                "source": {
                    "dataset": "fixture",
                    "source_question_id": "question-1",
                    "support": "Alpha.",
                },
            }
        )
    ]


def test_normalization_sets_full_corpus_version_and_global_offsets(
    test_corpus: OpenStaxArchiveCorpus, raw_samples: list[GoldSample]
) -> None:
    normalized, report = normalize_gold_samples(raw_samples, test_corpus)

    assert report.stale == 0
    assert normalized[0].schema_version == "0.2"
    assert normalized[0].corpus_version == test_corpus.corpus_version
    span = normalized[0].gold_core_evidence_sets[0][0]
    assert span.chapter_char_start == span.char_start
    assert span.corpus_char_end == 6


def test_normalization_preserves_source_corpus_version(
    test_corpus: OpenStaxArchiveCorpus, raw_samples: list[GoldSample]
) -> None:
    normalized, _ = normalize_gold_samples(raw_samples, test_corpus)

    assert normalized[0].source_corpus_version == raw_samples[0].corpus_version


def test_normalization_covers_partial_evidence(
    test_corpus: OpenStaxArchiveCorpus, raw_samples: list[GoldSample]
) -> None:
    normalized, _ = normalize_gold_samples(raw_samples, test_corpus)

    partial = normalized[0].partial_evidence[0]
    assert partial.resolution_status is SpanResolutionStatus.RESOLVED
    assert partial.corpus_char_start == 8


def test_normalization_is_idempotent(
    test_corpus: OpenStaxArchiveCorpus, raw_samples: list[GoldSample]
) -> None:
    first, _ = normalize_gold_samples(raw_samples, test_corpus)
    second, _ = normalize_gold_samples(first, test_corpus)

    assert [item.model_dump(mode="json") for item in first] == [
        item.model_dump(mode="json") for item in second
    ]


def test_stale_span_is_reported_and_not_written_as_formal_gold(
    test_corpus: OpenStaxArchiveCorpus, raw_samples: list[GoldSample], tmp_path: Path
) -> None:
    stale = raw_samples[0].model_copy(deep=True)
    stale.gold_core_evidence_sets[0][0].verbatim_text = "Omega."
    _, report = normalize_gold_samples([stale], test_corpus)

    assert report.stale == 1
    with pytest.raises(ValueError, match="stale"):
        write_normalized_gold([stale], report, tmp_path / "gold.jsonl")


def test_existing_normalized_file_is_never_overwritten(
    tmp_path: Path, test_corpus: OpenStaxArchiveCorpus, raw_samples: list[GoldSample]
) -> None:
    normalized, report = normalize_gold_samples(raw_samples, test_corpus)
    destination = tmp_path / "gold.jsonl"

    write_normalized_gold(normalized, report, destination)

    with pytest.raises(FileExistsError):
        write_normalized_gold(normalized, report, destination)


def test_normalized_output_round_trips_and_replays_global_coordinates(
    tmp_path: Path, test_corpus: OpenStaxArchiveCorpus, raw_samples: list[GoldSample]
) -> None:
    normalized, report = normalize_gold_samples(raw_samples, test_corpus)
    destination = tmp_path / "gold.jsonl"
    write_normalized_gold(normalized, report, destination)

    loaded = load_normalized_gold(destination, document=test_corpus.document)

    assert loaded == normalized


def test_normalized_loader_rejects_raw_or_unresolved_artifacts(
    tmp_path: Path, test_corpus: OpenStaxArchiveCorpus, raw_samples: list[GoldSample]
) -> None:
    raw_path = tmp_path / "raw.jsonl"
    raw_path.write_text(json.dumps(raw_samples[0].model_dump(mode="json")) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="schema 0.2"):
        load_normalized_gold(raw_path)

    normalized, _ = normalize_gold_samples(raw_samples, test_corpus)
    unresolved = normalized[0].model_copy(deep=True)
    unresolved.gold_core_evidence_sets[0][0].resolution_status = SpanResolutionStatus.STALE
    unresolved.gold_core_evidence_sets[0][0].corpus_char_start = None
    unresolved.gold_core_evidence_sets[0][0].corpus_char_end = None
    unresolved_path = tmp_path / "unresolved.jsonl"
    unresolved_path.write_text(
        json.dumps(unresolved.model_dump(mode="json")) + "\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="resolved"):
        load_normalized_gold(unresolved_path)


def test_normalized_loader_rejects_missing_provenance_and_mixed_corpus_versions(
    tmp_path: Path, test_corpus: OpenStaxArchiveCorpus, raw_samples: list[GoldSample]
) -> None:
    normalized, _ = normalize_gold_samples(raw_samples, test_corpus)
    missing_provenance = normalized[0].model_copy(
        update={"normalizer_version": None}
    )
    missing_path = tmp_path / "missing-provenance.jsonl"
    missing_path.write_text(
        json.dumps(missing_provenance.model_dump(mode="json")) + "\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="provenance"):
        load_normalized_gold(missing_path)

    other_version = normalized[0].model_copy(
        update={"question_id": "question-2", "corpus_version": "other-corpus"}
    )
    mixed_path = tmp_path / "mixed.jsonl"
    mixed_path.write_text(
        "\n".join(
            json.dumps(item.model_dump(mode="json")) for item in [normalized[0], other_version]
        )
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="exactly one corpus version"):
        load_normalized_gold(mixed_path)


def test_normalized_loader_rejects_coordinates_that_do_not_replay(
    tmp_path: Path, test_corpus: OpenStaxArchiveCorpus, raw_samples: list[GoldSample]
) -> None:
    normalized, _ = normalize_gold_samples(raw_samples, test_corpus)
    altered = normalized[0].model_copy(deep=True)
    altered.gold_core_evidence_sets[0][0].corpus_char_start = 1
    altered.gold_core_evidence_sets[0][0].corpus_char_end = 7
    path = tmp_path / "wrong-coordinates.jsonl"
    path.write_text(json.dumps(altered.model_dump(mode="json")) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="does not replay"):
        load_normalized_gold(path, document=test_corpus.document)


def test_normalized_output_is_byte_deterministic(
    tmp_path: Path, test_corpus: OpenStaxArchiveCorpus, raw_samples: list[GoldSample]
) -> None:
    first, first_report = normalize_gold_samples(raw_samples, test_corpus)
    second, second_report = normalize_gold_samples(raw_samples, test_corpus)
    first_path = tmp_path / "first.jsonl"
    second_path = tmp_path / "second.jsonl"

    write_normalized_gold(first, first_report, first_path)
    write_normalized_gold(second, second_report, second_path)

    assert first_path.read_bytes() == second_path.read_bytes()


def test_normalized_writer_never_replaces_artifact_created_during_promotion(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    test_corpus: OpenStaxArchiveCorpus,
    raw_samples: list[GoldSample],
) -> None:
    normalized, report = normalize_gold_samples(raw_samples, test_corpus)
    destination = tmp_path / "gold.jsonl"
    competing_bytes = b'{"writer":"competing"}\n'
    original_link = evaluation_io.os.link

    def link_after_competing_write(source: str | Path, target: str | Path) -> None:
        Path(target).write_bytes(competing_bytes)
        original_link(source, target)

    monkeypatch.setattr(evaluation_io.os, "link", link_after_competing_write)

    with pytest.raises(FileExistsError):
        write_normalized_gold(normalized, report, destination)

    assert destination.read_bytes() == competing_bytes


@pytest.mark.parametrize(
    ("corpus_char_start", "corpus_char_end", "message"),
    [
        (5, 5, "end must be greater"),
        (0, 5, "length must match"),
    ],
)
def test_normalized_loader_rejects_invalid_global_coordinate_shape_without_document(
    tmp_path: Path,
    test_corpus: OpenStaxArchiveCorpus,
    raw_samples: list[GoldSample],
    corpus_char_start: int,
    corpus_char_end: int,
    message: str,
) -> None:
    normalized, _ = normalize_gold_samples(raw_samples, test_corpus)
    malformed = normalized[0].model_copy(deep=True)
    span = malformed.gold_core_evidence_sets[0][0]
    span.corpus_char_start = corpus_char_start
    span.corpus_char_end = corpus_char_end
    path = tmp_path / "malformed.jsonl"
    path.write_text(json.dumps(malformed.model_dump(mode="json")) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        load_normalized_gold(path)
