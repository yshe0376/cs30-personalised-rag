"""Build one deterministic Retrieval Document corpus from contract documents."""

from __future__ import annotations

import argparse
import shlex
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from cs30.chunking import (  # noqa: E402
    BlockAwareChunker,
    BlockChunkingStrategy,
    export_retrieval_corpus,
    get_chunking_candidate,
)
from cs30.contracts import OpenStaxDocument  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--document",
        action="append",
        required=True,
        type=Path,
        help="Contract-valid OpenStaxDocument JSON. Repeat for multiple documents.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        type=Path,
        help="Directory for records.jsonl, manifest, schema and QA evidence.",
    )
    parser.add_argument(
        "--candidate",
        default="main",
        help="Chunking candidate: main or S1-S6 (default: main).",
    )
    parser.add_argument(
        "--sample-count",
        default=20,
        type=int,
        help="Number of deterministic source trace-back samples (default: 20).",
    )
    return parser.parse_args()


def load_document(path: Path) -> OpenStaxDocument:
    return OpenStaxDocument.model_validate_json(path.read_text(encoding="utf-8"))


def rebuild_command(args: argparse.Namespace) -> str:
    command = ["python", "scripts/build_retrieval_corpus.py"]
    for path in sorted(args.document):
        command.extend(("--document", str(path)))
    command.extend(("--output-dir", str(args.output_dir)))
    if args.candidate.lower() != "main":
        command.extend(("--candidate", args.candidate.upper()))
    if args.sample_count != 20:
        command.extend(("--sample-count", str(args.sample_count)))
    return shlex.join(command)


def main() -> None:
    args = parse_args()
    if args.sample_count < 0:
        raise ValueError("sample-count must not be negative")

    documents = [load_document(path) for path in sorted(args.document)]
    strategy = (
        BlockChunkingStrategy()
        if args.candidate.lower() == "main"
        else get_chunking_candidate(args.candidate).strategy
    )
    chunks = [
        chunk
        for document in documents
        for chunk in BlockAwareChunker(strategy=strategy).chunk(document)
    ]
    manifest = export_retrieval_corpus(
        documents,
        chunks,
        args.output_dir,
        rebuild_command=rebuild_command(args),
        sample_count=args.sample_count,
    )
    print(
        f"Built {manifest['record_count']} records at {args.output_dir} "
        f"with corpus ID {manifest['corpus_id']}"
    )


if __name__ == "__main__":
    main()
