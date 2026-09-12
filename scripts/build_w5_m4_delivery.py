"""Build the official W5 M4 corpus with M5's real embedding tokenizer."""

from __future__ import annotations

import argparse
import json
import shlex
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from cs30.chunking import (  # noqa: E402
    W5_CHUNKING_STRATEGY,
    W5_EMBEDDING_MODEL,
    BlockAwareChunker,
    export_retrieval_corpus,
    verify_corpus_identity,
)
from cs30.chunking.reporting import traceback_selection  # noqa: E402
from cs30.contracts import OpenStaxDocument  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--document",
        action="append",
        required=True,
        type=Path,
        help="Frozen contract-valid M2 OpenStaxDocument JSON; repeat as needed.",
    )
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--embedding-model", default=W5_EMBEDDING_MODEL)
    parser.add_argument("--sample-count", default=20, type=int)
    parser.add_argument(
        "--expected-manifest",
        type=Path,
        help="Optional prior manifest; fail if retrieval-relevant identity changed.",
    )
    return parser.parse_args()


def _rebuild_command(args: argparse.Namespace) -> str:
    command = ["python", "scripts/build_w5_m4_delivery.py"]
    for path in sorted(args.document):
        command.extend(("--document", str(path)))
    command.extend(("--output-dir", str(args.output_dir)))
    command.extend(("--embedding-model", args.embedding_model))
    if args.sample_count != 20:
        command.extend(("--sample-count", str(args.sample_count)))
    return shlex.join(command)


def _load_m5_tokenizer(model_name: str) -> tuple[object, int, int, int]:
    try:
        from sentence_transformers import SentenceTransformer

        from cs30.indexing.faiss_index import HFTokenCounter
    except ImportError as exc:
        message = 'Missing M5 dependencies. Run: python -m pip install -e ".[dev,ml]"'
        raise SystemExit(message) from exc

    model = SentenceTransformer(model_name)
    model_limit = getattr(model, "max_seq_length", None)
    if not isinstance(model_limit, int) or model_limit <= 0:
        raise ValueError(f"embedding model has no valid max_seq_length: {model_name}")
    special_tokens = model.tokenizer.num_special_tokens_to_add(pair=False)
    content_limit = model_limit - special_tokens
    if content_limit <= 0:
        raise ValueError(f"embedding model has no usable content-token limit: {model_name}")
    return HFTokenCounter(model, model_name), content_limit, model_limit, special_tokens


def main() -> None:
    args = parse_args()
    if args.sample_count < 20:
        raise ValueError("the official W5 delivery requires at least 20 trace-back samples")

    documents = [
        OpenStaxDocument.model_validate_json(path.read_text(encoding="utf-8"))
        for path in sorted(args.document)
    ]
    (
        token_counter,
        embedding_max_tokens,
        model_max_sequence_length,
        special_token_count,
    ) = _load_m5_tokenizer(args.embedding_model)
    chunker = BlockAwareChunker(
        strategy=W5_CHUNKING_STRATEGY,
        token_counter=token_counter,
    )
    chunks = [chunk for document in documents for chunk in chunker.chunk(document)]
    if len(chunks) < 20:
        raise ValueError("the official W5 corpus must contain at least 20 chunks")
    selected = traceback_selection(chunks, args.sample_count)
    selected_reasons = {reason for _, reasons in selected for reason in reasons}
    required_reasons = {
        "chapter_start",
        "chapter_end",
        "formula_or_equation",
        "short_source_block",
        "cross_block",
    }
    missing_reasons = sorted(required_reasons - selected_reasons)
    if missing_reasons:
        raise ValueError(
            "trace-back sample does not cover required categories: "
            + ", ".join(missing_reasons)
        )
    manifest = export_retrieval_corpus(
        documents,
        chunks,
        args.output_dir,
        rebuild_command=_rebuild_command(args),
        sample_count=args.sample_count,
        embedding_max_tokens=embedding_max_tokens,
        embedding_model_max_sequence_length=model_max_sequence_length,
        embedding_special_token_count=special_token_count,
    )
    if args.expected_manifest:
        expected = json.loads(args.expected_manifest.read_text(encoding="utf-8"))
        verify_corpus_identity(expected, manifest)
    print(
        f"Built W5 M4 corpus {manifest['corpus_id']} with "
        f"{manifest['record_count']} chunks; content-token ceiling="
        f"{embedding_max_tokens}, model max sequence length={model_max_sequence_length}."
    )


if __name__ == "__main__":
    main()
