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
from cs30.indexing.faiss_index import (  # noqa: E402
    FaissIndexBuilder,
    get_query_instruction,
)

DEFAULT_CORPUS_DIR = (
    REPOSITORY_ROOT
    / "artifacts"
    / "w5"
    / "m4-v3"
    / "retrieval_corpus"
)


DEFAULT_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

def model_output_name(model_name: str) -> str:
    return model_name.split("/")[-1].lower()


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
        default=None,
        help=(
            "Directory where the FAISS index will be written. "
            "If omitted, a model-specific directory is used."
        ),
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

    if args.output_dir is None:
        output_dir = (
            REPOSITORY_ROOT
            / "artifacts"
            / "w5"
            / "m5_latest"
            / model_output_name(args.model)
        )
    else:
        output_dir = args.output_dir

    if output_dir.exists() and any(output_dir.iterdir()):
        print(
            f"ERROR: Output directory is not empty: {output_dir}",
            file=sys.stderr,
        )
        print(
            "Choose a different --output-dir or clear the directory first.",
            file=sys.stderr,
        )
        return 1

    query_instruction = get_query_instruction(args.model)

    builder = FaissIndexBuilder(
        model_name=args.model,
        index_dir=output_dir,
        query_instruction=query_instruction,
    )


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
    print(f"Index output: {output_dir}")
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

    if loaded_artifact.artifact_id != artifact.artifact_id:
        print(
            "ERROR: Reloaded artifact ID does not match built artifact:",
            file=sys.stderr,
        )
        print(
            f"  expected: {artifact.artifact_id}",
            file=sys.stderr,
        )
        print(
            f"  actual:   {loaded_artifact.artifact_id}",
            file=sys.stderr,
        )
        return 1

    print("Artifact ID match: True")
    print("Reloaded chunks:", len(builder.chunks))
    if len(builder.chunks) != len(chunks):
        print(
            "ERROR: Reload chunk count mismatch:",
            file=sys.stderr,
        )
        print(
            f"  expected: {len(chunks)}",
            file=sys.stderr,
        )
        print(
            f"  actual:   {len(builder.chunks)}",
            file=sys.stderr,
        )
        return 1
    if builder.index.ntotal != len(chunks):
        print(
            "ERROR: Reloaded FAISS vector count mismatch:",
            file=sys.stderr,
        )
        print(
            f"  expected: {len(chunks)}",
            file=sys.stderr,
        )
        print(
            f"  actual:   {builder.index.ntotal}",
            file=sys.stderr,
        )
        return 1

    expected_dimension = int(artifact.metadata["dimension"])

    if builder.index.d != expected_dimension:
        print(
            "ERROR: Reloaded FAISS dimension mismatch:",
            file=sys.stderr,
        )
        print(
            f"  expected: {expected_dimension}",
            file=sys.stderr,
        )
        print(
            f"  actual:   {builder.index.d}",
            file=sys.stderr,
        )
        return 1
    
    print()
    print("Official M5 FAISS index build and reload verification passed.")
    return 0
        


if __name__ == "__main__":
    raise SystemExit(main())