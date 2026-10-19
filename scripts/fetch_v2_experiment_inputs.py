"""Fetch the pinned M3/M4 V2 development release assets, verifying every byte.

This is an explicit network operation. It downloads no models and supplies no
Role annotations or formal evaluation approval. Reuse already verified files;
refuse changed files and never overwrite an existing extracted corpus.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import tempfile
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

BASE = "https://github.com/yshe0376/cs30-personalised-rag/releases/download/"
ASSETS = {
    "gold_v0_1_1_integrated.jsonl": (
        BASE + "v2-m3-gold-v0.1.2-dev-v1/gold_v0_1_1_integrated.jsonl",
        "5875c2edc35195d475ea8d2980d7d9793cdfc8b83c12d12386049f13d1b69e6e",
    ),
    "SHA256SUMS.txt": (
        BASE + "v2-m3-gold-v0.1.2-dev-v1/SHA256SUMS.txt",
        "aa9d2168cc20afd7c4888dbd800650d3ff74f93b8890cc468c583ee9b491e273",
    ),
    "v2_structure_aware_corpus_3book_dev_main_3553825.zip": (
        BASE + "v2-m4-structure-v2-dev-v1/v2_structure_aware_corpus_3book_dev_main_3553825.zip",
        "9a10c86aad93d866d888f14d8360d6dde81e70e1970fcab67c7a128227f19976",
    ),
}


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fetch(root: Path) -> dict:
    root.mkdir(parents=True, exist_ok=True)
    for name, (url, expected) in ASSETS.items():
        path = root / name
        if not path.exists():
            with tempfile.TemporaryDirectory(dir=root, prefix="download-") as temporary_dir:
                temporary = Path(temporary_dir) / name
                with temporary.open("xb") as stream:
                    with urllib.request.urlopen(url, timeout=60) as response:
                        while chunk := response.read(1024 * 1024):
                            stream.write(chunk)
                if file_hash(temporary) != expected:
                    raise ValueError(f"download SHA-256 mismatch: {name}")
                # link is exclusive and cannot replace an existing download.
                os.link(temporary, path)
        if not path.is_file() or file_hash(path) != expected:
            raise ValueError(f"existing asset SHA-256 mismatch: {name}")
    target = root / "corpus-release"
    archive_path = root / "v2_structure_aware_corpus_3book_dev_main_3553825.zip"
    with zipfile.ZipFile(archive_path) as archive:
        names = set()
        for entry in archive.infolist():
            relative = PurePosixPath(entry.filename)
            if (
                relative.is_absolute()
                or ".." in relative.parts
                or "\\" in entry.filename
                or ":" in entry.filename
                or stat.S_ISLNK(entry.external_attr >> 16)
                or entry.filename in names
            ):
                raise ValueError("release archive contains an unsafe or duplicate path")
            names.add(entry.filename)
        if len(names) > 100 or sum(e.file_size for e in archive.infolist()) > 200 * 1024 * 1024:
            raise ValueError("unexpected release archive size")
        if target.exists():
            for entry in archive.infolist():
                if not entry.is_dir() and (target / entry.filename).read_bytes() != archive.read(
                    entry
                ):
                    raise ValueError("existing extracted corpus differs from pinned archive")
        else:
            with tempfile.TemporaryDirectory(dir=root, prefix="extract-") as temporary_dir:
                staging = Path(temporary_dir) / "corpus-release"
                staging.mkdir()
                archive.extractall(staging)
                staging.rename(target)
    provenance = {
        "schema_version": "0.1",
        "reportable": False,
        "assets": {name: {"url": url, "sha256": digest} for name, (url, digest) in ASSETS.items()},
        "limitations": [
            "Draft three-textbook Gold: 162 pending and 26 proposed_test questions.",
            "The 26-question Test set was previously exposed in M6 diagnostics.",
            "No matching V2 Role annotations are supplied by these releases.",
            "No split promotion, annotation review or formal approval is implied.",
        ],
    }
    (root / "download_manifest.json").write_text(
        json.dumps(provenance, indent=2) + "\n",
        encoding="utf-8",
    )
    return provenance


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        fetch(args.output_dir)
        print(f"Verified pinned V2 development inputs in {args.output_dir}")
        return 0
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        parser.exit(2, f"V2 input download failed: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
