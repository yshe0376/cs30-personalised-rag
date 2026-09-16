"""Build the official W5 M4 corpus from M1's prepared full document."""

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
)
from cs30.chunking.gold_mapping import validate_chunk_source_blocks  # noqa: E402
from cs30.evaluation import load_prepared_corpus  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--prepared-corpus-dir",
        required=True,
        type=Path,
        help=(
            "Directory containing M1's openstax_document.json, "
            "corpus_manifest.json and evidence_source_blocks.jsonl."
        ),
    )
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--embedding-model", default=W5_EMBEDDING_MODEL)
    parser.add_argument("--sample-count", default=20, type=int)
    return parser.parse_args()


def _rebuild_command(args: argparse.Namespace) -> str:
    command = [
        "python",
        "scripts/build_w5_m4_delivery.py",
        "--prepared-corpus-dir",
        str(args.prepared_corpus_dir),
        "--output-dir",
        str(args.output_dir),
        "--embedding-model",
        args.embedding_model,
    ]
    if args.sample_count != 20:
        command.extend(("--sample-count", str(args.sample_count)))
    return shlex.join(command)


def _load_m5_tokenizer(model_name: str) -> object:
    try:
        from sentence_transformers import SentenceTransformer

        from cs30.indexing.faiss_index import HFTokenCounter
    except ImportError as exc:
        raise SystemExit(
            'Missing M5 dependencies. Run: python -m pip install -e ".[dev,ml]"'
        ) from exc
    model = SentenceTransformer(model_name)
    return HFTokenCounter(model, model_name)


def main() -> None:
    args = parse_args()
    if args.sample_count < 0:
        raise ValueError("sample-count must not be negative")
    prepared_corpus = load_prepared_corpus(args.prepared_corpus_dir)
    document = prepared_corpus.document
    chunks = BlockAwareChunker(
        strategy=W5_CHUNKING_STRATEGY,
        token_counter=_load_m5_tokenizer(args.embedding_model),
    ).chunk(document)
    evidence_validation = validate_chunk_source_blocks(
        chunks,
        sorted(prepared_corpus.evidence_blocks_by_id),
    )
    manifest = export_retrieval_corpus(
        [document],
        chunks,
        args.output_dir,
        rebuild_command=_rebuild_command(args),
        sample_count=args.sample_count,
    )
    manifest["source_corpus_version"] = prepared_corpus.corpus_version
    manifest["source_evidence_policy_id"] = prepared_corpus.manifest()[
        "evidence_policy_id"
    ]
    manifest["evidence_source_block_validation"] = evidence_validation
    (args.output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        f"Built {manifest['record_count']} official chunks for "
        f"{prepared_corpus.corpus_version}; evidence source blocks match exactly."
    )


if __name__ == "__main__":
    main()
