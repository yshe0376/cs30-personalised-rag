"""Package the generated W5 M4 artifacts for downstream team members."""

from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path

M3_FILES = (
    "source_corpus/corpus_manifest.json",
    "source_corpus/openstax_document.json",
)
M5_FILES = (
    "corpus/anomalies.json",
    "corpus/manifest.json",
    "corpus/records.jsonl",
    "corpus/sample_records.jsonl",
    "corpus/schema.json",
    "corpus/statistics.json",
    "corpus/traceback_records.json",
)
ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=Path("artifacts/w5/m4"),
        help="Root containing source_corpus/ and corpus/.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts/w5/m4/handoffs"),
        help="Empty destination for the two handoff packages.",
    )
    parser.add_argument(
        "--delivery-date",
        required=True,
        help="Delivery date recorded in the manifest (YYYY-MM-DD).",
    )
    return parser.parse_args()


def _sha256_bytes(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return "sha256:" + digest.hexdigest()


def _read_object(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return payload


def _require_files(root: Path, relative_paths: tuple[str, ...]) -> list[Path]:
    paths = [root / relative_path for relative_path in relative_paths]
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise FileNotFoundError("missing handoff input(s): " + ", ".join(missing))
    return paths


def _zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=ZIP_TIMESTAMP)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    return info


def _package(
    destination: Path,
    *,
    package_root: str,
    source_root: Path,
    relative_paths: tuple[str, ...],
    readme: str,
) -> dict[str, object]:
    if destination.exists():
        raise FileExistsError(f"refusing to overwrite handoff package: {destination}")

    files = _require_files(source_root, relative_paths)
    checksum_lines = [
        f"{_sha256_file(path).removeprefix('sha256:')}  {relative_path}"
        for path, relative_path in zip(files, relative_paths, strict=True)
    ]
    members: list[dict[str, object]] = []
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        text_files = {
            "README.md": readme.rstrip() + "\n",
            "SHA256SUMS": "\n".join(checksum_lines) + "\n",
        }
        for relative_name, text in text_files.items():
            payload = text.encode("utf-8")
            archive.writestr(_zip_info(f"{package_root}/{relative_name}"), payload)
            members.append(
                {
                    "path": relative_name,
                    "bytes": len(payload),
                    "sha256": _sha256_bytes(payload),
                }
            )
        for path, relative_path in zip(files, relative_paths, strict=True):
            payload = path.read_bytes()
            archive.writestr(_zip_info(f"{package_root}/{relative_path}"), payload)
            members.append(
                {
                    "path": relative_path,
                    "bytes": len(payload),
                    "sha256": _sha256_bytes(payload),
                }
            )

    return {
        "file": destination.name,
        "bytes": destination.stat().st_size,
        "sha256": _sha256_file(destination),
        "members": members,
    }


def package_handoffs(
    artifact_root: Path,
    output_dir: Path,
    *,
    delivery_date: str,
) -> dict[str, object]:
    """Build separate M3 and M5 archives and return their delivery manifest."""

    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"handoff output directory is not empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    source_manifest = _read_object(artifact_root / "source_corpus/corpus_manifest.json")
    chunk_manifest = _read_object(artifact_root / "corpus/manifest.json")
    corpus_version = str(source_manifest["corpus_version"])
    corpus_id = str(chunk_manifest["corpus_id"])
    chunk_config_id = str(chunk_manifest["chunk_config_id"])

    m3_readme = f"""# M3 unified source-corpus handoff

Delivery date: {delivery_date}

Use `source_corpus/openstax_document.json` as the single 34-chapter source
document. Do not load the 34 per-chapter documents as separate documents: they
share one document identity and can overwrite one another downstream.

The companion manifest records the chapter order, separator, source identity,
and corpus version. Verify every file against `SHA256SUMS` before use.

- Corpus version: `{corpus_version}`
- Coordinate owner: M3 retains semantic annotations; normalization binds the
  original chapter-local spans to this unified corpus.
"""
    m5_readme = f"""# M5 retrieval-corpus handoff

Delivery date: {delivery_date}

Use `corpus/records.jsonl` for both dense and BM25 indexing and keep the
companion manifest with every index artifact. The package contains the single
approved W5 M4 configuration, which excludes problem and summary content.

Review every item in `corpus/anomalies.json` before accepting the dense index;
the real MiniLM tokenizer has a 254-content-token ceiling. Verify every file
against `SHA256SUMS` before use.

- Corpus ID: `{corpus_id}`
- Chunk configuration ID: `{chunk_config_id}`
"""

    packages = {
        "m3": _package(
            output_dir / "m3_unified_source_corpus.zip",
            package_root="m3_unified_source_corpus",
            source_root=artifact_root,
            relative_paths=M3_FILES,
            readme=m3_readme,
        ),
        "m5": _package(
            output_dir / "m5_retrieval_corpus.zip",
            package_root="m5_retrieval_corpus",
            source_root=artifact_root,
            relative_paths=M5_FILES,
            readme=m5_readme,
        ),
    }
    manifest: dict[str, object] = {
        "manifest_version": "1.0",
        "delivery_date": delivery_date,
        "source_corpus_version": corpus_version,
        "chunk_corpus_id": corpus_id,
        "chunk_config_id": chunk_config_id,
        "packages": packages,
        "storage_policy": (
            "Generated textbook and retrieval data belongs in the team Google Drive; "
            "only code, tests, and technical documentation belong in GitHub."
        ),
    }
    manifest_path = output_dir / "handoff_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=True) + "\n", encoding="utf-8"
    )
    return manifest


def main() -> None:
    args = parse_args()
    manifest = package_handoffs(
        args.artifact_root,
        args.output_dir,
        delivery_date=args.delivery_date,
    )
    print(
        "Built M3 and M5 handoff packages for "
        f"{manifest['source_corpus_version']} in {args.output_dir}."
    )


if __name__ == "__main__":
    main()
