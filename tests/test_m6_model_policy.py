from cs30.retrieval.model_policy import (
    CANDIDATE_EMBEDDING_MODELS,
    PRIMARY_EMBEDDING_MODEL,
    SUPPORTED_EMBEDDING_MODELS,
)


def test_m6_primary_model_matches_m5_official_default() -> None:
    assert PRIMARY_EMBEDDING_MODEL == "sentence-transformers/all-MiniLM-L6-v2"
    assert SUPPORTED_EMBEDDING_MODELS[0] == PRIMARY_EMBEDDING_MODEL


def test_m5_comparison_models_remain_candidates() -> None:
    assert CANDIDATE_EMBEDDING_MODELS == (
        "sentence-transformers/all-mpnet-base-v2",
        "intfloat/e5-base-v2",
        "BAAI/bge-base-en-v1.5",
        "BAAI/bge-m3",
    )
