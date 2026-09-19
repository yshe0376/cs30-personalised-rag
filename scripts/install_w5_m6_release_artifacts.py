"""Install the frozen W5 M4 and provisional M5 release inputs for local M6 runs.

Only named files are extracted. Release archive SHA-256 values are pinned, and an
existing local file is never overwritten with different content.
"""

from __future__ import annotations

import hashlib
import io
import json
import urllib.request
import zipfile
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
RELEASE_BASE = "https://github.com/yshe0376/cs30-personalised-rag/releases/download"

ARCHIVES = (
    (
        "w5-m4-official-v1",
        "prepared_corpus.zip",
        "7c41e6a72fb41efbe2ef30f3c963dbcb8f4e2939abe56e5215b2f30cf0026f95",
        (
            "prepared_corpus/openstax_document.json",
            "prepared_corpus/corpus_manifest.json",
            "prepared_corpus/evidence_source_blocks.jsonl",
        ),
        "artifacts/w5/m4-v3",
    ),
    (
        "w5-m4-official-v1",
        "gold_normalized.zip",
        "2e15e9c72364d9159c1d591d9144aeb58e5f66a145ac619ef76631a8278f0887",
        ("gold_normalized/gold_v0_2_from_m3_v0_1_1.jsonl",),
        "artifacts/w5/m4-v3",
    ),
    (
        "w5-m4-official-v1",
        "gold_mapping.zip",
        "880ff834c7e0e535f633eeb4f54f1cf829c7f4b011f0994682d94bcca9422f45",
        ("gold_mapping/evaluation_mapping_v0_1.json",),
        "artifacts/w5/m4-v3",
    ),
    (
        "w5-m4-official-v1",
        "retrieval_corpus.zip",
        "05a67364a561e93e843709da7c6286ea25761e8508b5dcf5301c92339f516635",
        (
            "retrieval_corpus/records.jsonl",
            "retrieval_corpus/manifest.json",
        ),
        "artifacts/w5/m4-v3",
    ),
    (
        "w5-m5-minilm-local-rebuild-v1",
        "w5-m5-all-minilm-l6-v2-local-rebuild.zip",
        "4e98be294603ecc995a373beebe0246312b1f82a55fc059c7965339515876070",
        ("artifact.json", "chunks.json", "index.faiss"),
        "artifacts/w5/m5_latest/all-minilm-l6-v2",
    ),
)


def download_archive(tag: str, name: str, expected_sha256: str) -> bytes:
    url = f"{RELEASE_BASE}/{tag}/{name}"
    request = urllib.request.Request(url, headers={"User-Agent": "cs30-m6-release-installer"})
    with urllib.request.urlopen(request, timeout=90) as response:
        payload = response.read()
    actual_sha256 = hashlib.sha256(payload).hexdigest()
    if actual_sha256 != expected_sha256:
        raise ValueError(
            f"Release checksum mismatch for {name}: {actual_sha256} != {expected_sha256}"
        )
    print(f"Verified {name}: sha256:{actual_sha256}")
    return payload


def install_archive(
    tag: str,
    name: str,
    expected_sha256: str,
    members: tuple[str, ...],
    destination: str,
) -> None:
    root = REPOSITORY_ROOT.resolve()
    target_root = (root / destination).resolve()
    if target_root != root and root not in target_root.parents:
        raise ValueError(f"Destination escapes the repository: {target_root}")

    payload = download_archive(tag, name, expected_sha256)
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        available = set(archive.namelist())
        missing = set(members) - available
        if missing:
            raise FileNotFoundError(f"{name} is missing: {sorted(missing)}")
        for member in members:
            target = (target_root / Path(member)).resolve()
            if target_root not in target.parents:
                raise ValueError(f"Archive member escapes the target directory: {member}")
            content = archive.read(member)
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                if not target.is_file() or target.read_bytes() != content:
                    raise FileExistsError(f"Refusing to replace a different local file: {target}")
                print(f"Already verified: {target.relative_to(root)}")
                continue
            with target.open("xb") as stream:
                stream.write(content)
            print(f"Installed: {target.relative_to(root)}")


def verify_installed_identities() -> None:
    m4_root = REPOSITORY_ROOT / "artifacts/w5/m4-v3"
    index_root = REPOSITORY_ROOT / "artifacts/w5/m5_latest/all-minilm-l6-v2"
    corpus = m4_root / "retrieval_corpus/records.jsonl"
    corpus_manifest = json.loads(
        (m4_root / "retrieval_corpus/manifest.json").read_text(encoding="utf-8")
    )
    corpus_id = "sha256:" + hashlib.sha256(corpus.read_bytes()).hexdigest()
    if corpus_id != corpus_manifest["corpus_id"]:
        raise ValueError("M4 retrieval corpus does not match its frozen manifest")

    index = json.loads((index_root / "artifact.json").read_text(encoding="utf-8"))
    normalized_gold = m4_root / "gold_normalized/gold_v0_2_from_m3_v0_1_1.jsonl"
    gold_rows = [line for line in normalized_gold.read_text(encoding="utf-8").splitlines() if line]
    if index["chunk_count"] != corpus_manifest["record_count"] or len(gold_rows) != 20:
        raise ValueError("M4/M5 chunk count or normalized Gold count is inconsistent")
    if index["metadata"]["embedding_model"] != "sentence-transformers/all-MiniLM-L6-v2":
        raise ValueError("M5 artifact is not the expected MiniLM model")
    print(f"Identity checks passed: {index['chunk_count']} chunks, {len(gold_rows)} Gold rows")
    print("Caveat: the M5 release is a provisional local rebuild, pending M5 validation.")


def main() -> None:
    for archive in ARCHIVES:
        install_archive(*archive)
    verify_installed_identities()


if __name__ == "__main__":
    main()
