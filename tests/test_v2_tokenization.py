"""The chunk ruler: which tokenizer decides chunk sizes, and how it is recorded."""

from __future__ import annotations

import pytest
from test_v2_contracts import make_document

from cs30.v2.chunking import V2BlockChunker
from cs30.v2.tokenization import (
    CHUNK_TOKENIZER_NAME,
    CHUNK_TOKENIZER_REVISION,
    REGEX_TOKENIZER_NAME,
    HuggingFaceTokenCounter,
    RegexTokenCounter,
    build_token_counter,
    is_pinned_revision,
)

DEFAULT_EMBEDDING_MODEL = "Alibaba-NLP/gte-modernbert-base"


def test_the_frozen_ruler_is_bert_wordpiece_at_a_pinned_revision() -> None:
    assert CHUNK_TOKENIZER_NAME == "google-bert/bert-base-uncased"
    assert is_pinned_revision(CHUNK_TOKENIZER_REVISION)


def test_only_a_full_commit_hash_counts_as_pinned() -> None:
    assert not is_pinned_revision(None)
    assert not is_pinned_revision("main")
    assert not is_pinned_revision(CHUNK_TOKENIZER_REVISION[:12])
    assert not is_pinned_revision(CHUNK_TOKENIZER_REVISION.upper())


def test_the_named_ruler_decides_which_counter_is_built() -> None:
    assert isinstance(build_token_counter(REGEX_TOKENIZER_NAME), RegexTokenCounter)

    counter = build_token_counter(CHUNK_TOKENIZER_NAME, revision=CHUNK_TOKENIZER_REVISION)

    assert isinstance(counter, HuggingFaceTokenCounter)
    assert counter.name == CHUNK_TOKENIZER_NAME
    assert counter.revision == CHUNK_TOKENIZER_REVISION
    # Naming a Hugging Face ruler must not download it; only counting does.
    assert counter._tokenizer is None


def test_the_chunker_counts_with_its_injected_ruler() -> None:
    class DoubleCounter:
        name = "double-v1"

        def __init__(self) -> None:
            self.calls = 0

        def count(self, text: str) -> int:
            self.calls += 1
            return 2 * len(text.split())

    counter = DoubleCounter()
    chunker = V2BlockChunker(tokenizer_name=counter.name, token_counter=counter)
    document = make_document()

    chunks = chunker.chunk(document)

    assert counter.calls == len(chunks)
    assert chunks[0].token_count == 2 * len(chunks[0].text.split())


def test_the_ruler_name_is_part_of_the_chunk_config_hash() -> None:
    regex_hash = V2BlockChunker(tokenizer_name=REGEX_TOKENIZER_NAME).config_hash
    model_hash = V2BlockChunker(
        tokenizer_name=CHUNK_TOKENIZER_NAME,
        tokenizer_revision=CHUNK_TOKENIZER_REVISION,
    ).config_hash

    assert regex_hash != model_hash


def test_the_ruler_revision_is_part_of_the_chunk_config_hash() -> None:
    pinned = V2BlockChunker(
        tokenizer_name=CHUNK_TOKENIZER_NAME,
        tokenizer_revision=CHUNK_TOKENIZER_REVISION,
    )
    other = V2BlockChunker(tokenizer_name=CHUNK_TOKENIZER_NAME, tokenizer_revision="0" * 40)
    unpinned = V2BlockChunker(tokenizer_name=CHUNK_TOKENIZER_NAME)

    assert len({pinned.config_hash, other.config_hash, unpinned.config_hash}) == 3


def test_chunks_record_the_ruler_revision() -> None:
    class OneCounter:
        name = CHUNK_TOKENIZER_NAME

        def count(self, text: str) -> int:
            return 1

    chunker = V2BlockChunker(
        tokenizer_name=CHUNK_TOKENIZER_NAME,
        tokenizer_revision=CHUNK_TOKENIZER_REVISION,
        token_counter=OneCounter(),
    )

    chunk = chunker.chunk(make_document())[0]

    assert chunk.metadata["tokenizer_name"] == CHUNK_TOKENIZER_NAME
    assert chunk.metadata["tokenizer_revision"] == CHUNK_TOKENIZER_REVISION


def test_configured_hugging_face_rulers_must_be_pinned() -> None:
    with pytest.raises(ValueError, match="tokenizer_revision"):
        V2BlockChunker.from_config({"tokenizer_name": CHUNK_TOKENIZER_NAME})
    with pytest.raises(ValueError, match="tokenizer_revision"):
        V2BlockChunker.from_config(
            {"tokenizer_name": CHUNK_TOKENIZER_NAME, "tokenizer_revision": "main"}
        )

    pinned = V2BlockChunker.from_config(
        {
            "tokenizer_name": CHUNK_TOKENIZER_NAME,
            "tokenizer_revision": CHUNK_TOKENIZER_REVISION,
        }
    )
    regex = V2BlockChunker.from_config({"tokenizer_name": REGEX_TOKENIZER_NAME})

    assert pinned.tokenizer_revision == CHUNK_TOKENIZER_REVISION
    assert regex.tokenizer_revision is None


def test_the_pinned_ruler_counts_past_every_model_input_limit() -> None:
    # MiniLM's copy of this vocabulary truncates at 128 tokens when its
    # tokenizer.json is loaded directly; the ruler must count the whole text.
    # Runs only where the pinned tokenizer is already cached, so CI never
    # downloads it.
    transformers = pytest.importorskip("transformers")
    try:
        transformers.AutoTokenizer.from_pretrained(
            CHUNK_TOKENIZER_NAME,
            revision=CHUNK_TOKENIZER_REVISION,
            local_files_only=True,
        )
    except OSError:
        pytest.skip(f"{CHUNK_TOKENIZER_NAME}@{CHUNK_TOKENIZER_REVISION} is not cached")

    counter = build_token_counter(CHUNK_TOKENIZER_NAME, revision=CHUNK_TOKENIZER_REVISION)

    assert counter.count("physics " * 700) == 700


@pytest.mark.parametrize("profile", ["real-development", "staging"])
def test_real_profiles_pin_the_frozen_ruler_apart_from_the_embedding_model(
    profile: str,
) -> None:
    from cs30.v2.config import load_v2_config

    config = load_v2_config(profile)

    assert config.chunk_config == {
        "tokenizer_name": CHUNK_TOKENIZER_NAME,
        "tokenizer_revision": CHUNK_TOKENIZER_REVISION,
    }
    V2BlockChunker.from_config(config.chunk_config)
    assert config.embedding_model == DEFAULT_EMBEDDING_MODEL
    assert config.embedding_max_seq_length == 8192
