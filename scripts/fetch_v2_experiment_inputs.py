"""Fetch the pinned M3/M4 V2 development release assets, verifying every byte.

This is an explicit network operation. It downloads no models and implies no
formal evaluation approval. Reuse already verified files; refuse changed files
and never overwrite an existing extracted corpus.
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
CORPUS_ARCHIVE = "M4_to_M5_four_book_corpus_a1fe99e.zip"
# The archive holds a single folder named after the corpus version; that folder
# is the --corpus-dir for convert-gold and prepare.
CORPUS_FOLDER = "2.0.0-dev.m4-four-book-main-a1fe99e"
ROLE_MANIFEST = "role_labels_v2_provenance_manifest.json"
ASSETS = {
    "gold_v0_1_3.jsonl": (
        BASE + "v2-m3-gold-v0.1.3-dev-v1/gold_v0_1_3.jsonl",
        "7d69af416591b64198bf25806424347366eb2123fdcdcf36ad757d37c4f942b8",
    ),
    CORPUS_ARCHIVE: (
        BASE + "v2-m4-four-book-dev-v1/" + CORPUS_ARCHIVE,
        "074ff89686fe3649089329f7858505f7a68d228d0284a83394a0c0b5a547a592",
    ),
    "role_labels_v2.jsonl": (
        BASE + "v2-role-labels-v2-four-book-dev-v1/role_labels_v2.jsonl",
        "d0f74c2ec9f49ed568ba7a922758357c09f4885648b3bdecfa22b7ab2643c59d",
    ),
    ROLE_MANIFEST: (
        BASE + "v2-role-labels-v2-four-book-dev-v1/" + ROLE_MANIFEST,
        "a02a52249a5e19a98b3928d14d9e143386e5306b9ee9d460b849535b841e3e63",
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
    target = root / CORPUS_FOLDER
    archive_path = root / CORPUS_ARCHIVE
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
            if relative.parts[0] != CORPUS_FOLDER:
                raise ValueError(f"release archive entry outside {CORPUS_FOLDER}/")
            names.add(entry.filename)
        if len(names) > 100 or sum(e.file_size for e in archive.infolist()) > 200 * 1024 * 1024:
            raise ValueError("unexpected release archive size")
        if target.exists():
            for entry in archive.infolist():
                extracted = root / entry.filename
                if not entry.is_dir() and (
                    not extracted.is_file() or extracted.read_bytes() != archive.read(entry)
                ):
                    raise ValueError("existing extracted corpus differs from pinned archive")
        else:
            with tempfile.TemporaryDirectory(dir=root, prefix="extract-") as temporary_dir:
                archive.extractall(temporary_dir)
                (Path(temporary_dir) / CORPUS_FOLDER).rename(target)
    provenance = {
        "schema_version": "0.1",
        "reportable": False,
        "assets": {name: {"url": url, "sha256": digest} for name, (url, digest) in ASSETS.items()},
        "corpus_dir": CORPUS_FOLDER,
        "role_manifest": ROLE_MANIFEST,
        "limitations": [
            "Draft Gold m3_gold_v0.1.3: 311 pending and 30 proposed_test questions; "
            "82 cite CK-12 and need the four-textbook corpus.",
            "26 of the 30 proposed_test questions were previously exposed in M6 diagnostics.",
            "Role labels are mostly model-assigned and have no independent human validation.",
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
        print(f"Corpus: {args.output_dir / CORPUS_FOLDER}")
        print(f"Role manifest: {args.output_dir / ROLE_MANIFEST}")
        return 0
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        parser.exit(2, f"V2 input download failed: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
