"""Build the official M5 FAISS index from M4 frozen chunks."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from cs30.contracts import Chunk  # noqa: E402
from cs30.indexing import FaissIndexBuilder  # noqa: E402

CORPUS_PATH = (
    REPOSITORY_ROOT
    / "artifacts"
    / "w5"
    / "m4"
    / "corpus_latest"
    / "records.jsonl"
)

INDEX_DIR = (
    REPOSITORY_ROOT
    / "artifacts"
    / "w5"
    / "m5_latest"
    / "bge_m3"
)

MODEL_NAME = "BAAI/bge-m3"


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


def main() -> None:
    if not CORPUS_PATH.exists():
        raise FileNotFoundError(f"Official corpus not found: {CORPUS_PATH}")

    print(f"Corpus: {CORPUS_PATH}")
    print(f"Model: {MODEL_NAME}")
    print(f"Index output: {INDEX_DIR}")
    print()

    chunks = load_chunks(CORPUS_PATH)

    print(f"Loaded chunks: {len(chunks)}")

    if len(chunks) != 3684:
        raise ValueError(
            f"Expected 3684 official chunks, got {len(chunks)}"
        )

    builder = FaissIndexBuilder(
        model_name=MODEL_NAME,
        index_dir=INDEX_DIR,
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


if __name__ == "__main__":
    main()