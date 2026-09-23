"""The chunk ruler: which tokenizer decides chunk sizes, and how it is recorded."""

from __future__ import annotations

import pytest
from test_v2_contracts import make_document

from cs30.v2.chunking import V2BlockChunker
from cs30.v2.tokenization import (
    CHUNK_TOKENIZER_NAME,
    REGEX_TOKENIZER_NAME,
    HuggingFaceTokenCounter,
    RegexTokenCounter,
    build_token_counter,
)


def test_the_frozen_ruler_is_the_gte_modernbert_tokenizer() -> None:
    assert CHUNK_TOKENIZER_NAME == "Alibaba-NLP/gte-modernbert-base"


def test_the_named_ruler_decides_which_counter_is_built() -> None:
    assert isinstance(build_token_counter(REGEX_TOKENIZER_NAME), RegexTokenCounter)

    counter = build_token_counter(CHUNK_TOKENIZER_NAME)

    assert isinstance(counter, HuggingFaceTokenCounter)
    assert counter.name == CHUNK_TOKENIZER_NAME
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
    model_hash = V2BlockChunker(tokenizer_name=CHUNK_TOKENIZER_NAME).config_hash

    assert regex_hash != model_hash


@pytest.mark.parametrize("profile", ["real-development", "staging"])
def test_real_profiles_use_the_frozen_ruler_and_record_the_input_limit(
    profile: str,
) -> None:
    from cs30.v2.config import load_v2_config

    config = load_v2_config(profile)

    assert config.chunk_config["tokenizer_name"] == CHUNK_TOKENIZER_NAME
    assert config.embedding_model == CHUNK_TOKENIZER_NAME
    assert config.embedding_max_seq_length == 8192
