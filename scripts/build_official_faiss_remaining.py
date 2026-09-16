"""Build remaining official M5 FAISS embedding indexes."""

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

OUTPUT_ROOT = REPOSITORY_ROOT / "artifacts" / "w5" / "m5_latest"

MODELS = {
    "mpnet": "sentence-transformers/all-mpnet-base-v2",
    "e5": "intfloat/e5-base-v2",
    "bge": "BAAI/bge-base-en-v1.5",
}


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
        raise FileNotFoundError(
            f"Official corpus not found: {CORPUS_PATH}"
        )

    chunks = load_chunks(CORPUS_PATH)

    print(f"Corpus: {CORPUS_PATH}")
    print(f"Loaded chunks: {len(chunks)}")
    print()

    if len(chunks) != 3684:
        raise ValueError(
            f"Expected 3684 official chunks, got {len(chunks)}"
        )

    for short_name, model_name in MODELS.items():
        index_dir = OUTPUT_ROOT / short_name

        print("=" * 70)
        print(f"Model: {model_name}")
        print(f"Output: {index_dir}")
        print()

        builder = FaissIndexBuilder(
            model_name=model_name,
            index_dir=index_dir,
        )

        started = time.perf_counter()
        artifact = builder.build(chunks)
        elapsed = time.perf_counter() - started

        print()
        print("Build complete.")
        print(f"Build time: {elapsed:.2f} seconds")
        print(f"Artifact ID: {artifact.artifact_id}")
        print(f"Embedding dimension: {artifact.metadata['dimension']}")

        print("Reloading saved index...")

        loaded_artifact = builder.load()

        artifact_match = (
            loaded_artifact.artifact_id == artifact.artifact_id
        )

        print(f"Artifact ID match: {artifact_match}")
        print(f"Reloaded chunks: {len(builder.chunks)}")

        if not artifact_match:
            raise RuntimeError(
                f"{short_name}: artifact ID mismatch after reload"
            )

        if len(builder.chunks) != len(chunks):
            raise RuntimeError(
                f"{short_name}: reload chunk count mismatch"
            )

        print(f"{short_name}: PASSED")
        print()

    print("=" * 70)
    print("All remaining official M5 FAISS indexes passed.")


if __name__ == "__main__":
    main()