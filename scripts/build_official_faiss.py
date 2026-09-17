"""Build the official M5 FAISS index from M4 frozen chunks."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from cs30.contracts import Chunk  # noqa: E402
from cs30.indexing import FaissIndexBuilder  # noqa: E402

DEFAULT_CORPUS_DIR = (
    REPOSITORY_ROOT
    / "artifacts"
    / "w5"
    / "m4-v3"
    / "retrieval_corpus"
)

DEFAULT_INDEX_DIR = (
    REPOSITORY_ROOT
    / "artifacts"
    / "w5"
    / "m5_latest"
    / "minilm"
)

DEFAULT_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


def get_query_instruction(model_name: str) -> str:
    if model_name == "BAAI/bge-base-en-v1.5":
        return "Represent this sentence for searching relevant passages: "

    if model_name == "intfloat/e5-base-v2":
        return "query: "

    return ""

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the official M5 FAISS index."
    )

    parser.add_argument(
        "--corpus-dir",
        type=Path,
        default=DEFAULT_CORPUS_DIR,
        help=(
            "Directory containing records.jsonl and manifest.json. "
            "Defaults to the official M4 frozen corpus."
        ),
    )

    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL_NAME,
        help="SentenceTransformer model name.",
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_INDEX_DIR,
        help="Directory where the FAISS index will be written.",
    )

    return parser.parse_args()

def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)

    return f"sha256:{digest.hexdigest()}"


def load_manifest(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def load_chunks(path: Path) -> list[Chunk]:
    chunks: list[Chunk] = []

    with path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                continue

            try:
                record = json.loads(line)
                chunks.append(Chunk.model_validate(record))
            except Exception as exc:
                raise RuntimeError(
                    f"Failed to load chunk at line {line_number}: {exc}"
                ) from exc

    return chunks


def main() -> int:
    args = parse_args()

    corpus_path = args.corpus_dir / "records.jsonl"
    manifest_path = args.corpus_dir / "manifest.json"

    if not args.corpus_dir.is_dir():
        print(
            f"ERROR: Corpus directory not found: {args.corpus_dir}",
            file=sys.stderr,
        )
        print(
            "Download the official corpus with:",
            file=sys.stderr,
        )
        print(
            '  gh release download w5-m4-official-v1 '
            '--pattern "retrieval_corpus.zip" '
            "--dir artifacts/w5/m4-v3",
            file=sys.stderr,
        )
        print(
            "Then extract retrieval_corpus.zip under "
            "artifacts/w5/m4-v3.",
            file=sys.stderr,
        )
        return 1

    if not manifest_path.is_file():
        print(
            f"ERROR: Missing corpus manifest: {manifest_path}",
            file=sys.stderr,
        )
        return 1

    print(f"Corpus: {corpus_path}")
    print(f"Model: {args.model}")
    print(f"Index output: {args.output_dir}")
    print()
    manifest = load_manifest(manifest_path)

    expected_corpus_id = manifest["corpus_id"]
    actual_corpus_id = sha256_file(corpus_path)

    if actual_corpus_id != expected_corpus_id:
        print(
            "ERROR: Corpus SHA256 mismatch:",
            file=sys.stderr,
        )
        print(
            f"  expected: {expected_corpus_id}",
            file=sys.stderr,
        )
        print(
            f"  actual:   {actual_corpus_id}",
            file=sys.stderr,
        )
        return 1

    chunks = load_chunks(corpus_path)
    print(f"Loaded chunks: {len(chunks)}")

    expected_record_count = manifest["record_count"]

    if len(chunks) != expected_record_count:
        print(
            "ERROR: Corpus record count mismatch:",
            file=sys.stderr,
        )
        print(
            f"  expected: {expected_record_count}",
            file=sys.stderr,
        )
        print(
            f"  actual:   {len(chunks)}",
            file=sys.stderr,
        )
        return 1

    query_instruction = get_query_instruction(args.model)

    builder = FaissIndexBuilder(
        model_name=args.model,
        index_dir=args.output_dir,
        query_instruction=query_instruction,
    )

    print()
    print("Building FAISS index...")

    started = time.perf_counter()
    artifact = builder.build(chunks)
    elapsed = time.perf_counter() - started

    print()
    print("Build complete.")
    print(f"Build time: {elapsed:.2f} seconds")
    print(f"Artifact ID: {artifact.artifact_id}")
    print(f"Index location: {artifact.location}")
    print(f"Embedding dimension: {artifact.metadata['dimension']}")

    print()
    print("Reloading saved index...")

    loaded_artifact = builder.load()

    print(
        "Artifact ID match:",
        loaded_artifact.artifact_id == artifact.artifact_id,
    )

    print("Reloaded chunks:", len(builder.chunks))

    if len(builder.chunks) != len(chunks):
        raise RuntimeError(
            f"Reload chunk count mismatch: "
            f"{len(builder.chunks)} != {len(chunks)}"
        )

    print()
    print("Official M5 FAISS index build and reload verification passed.")
    return 0
    


if __name__ == "__main__":
    raise SystemExit(main())