"""Install the pinned v2 textbook PDFs from a GitHub Release, or from a folder.

The catalogue already pins each book's PDF SHA-256, so this module never needs a
second list of hashes: it downloads (or copies) a file, hashes it while reading,
and only then puts it in place under its canonical name.  A local file with
different content is never overwritten, and a mismatching download is deleted
instead of installed.
"""

from __future__ import annotations

import os
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable, Mapping, Sequence
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Literal

from cs30.v2.catalog import REQUIRED_TEXTBOOK_IDS, get_textbook_spec
from cs30.v2.errors import InputError
from cs30.v2.ids import sha256_file

RELEASE_REPOSITORY = "yshe0376/cs30-personalised-rag"
DEFAULT_RELEASE_TAG = "v2-sources-openstax-v1"
DEFAULT_DESTINATION = Path("data/raw/v2")
_READ_CHUNK = 1024 * 1024
_TIMEOUT_SECONDS = 120

Opener = Callable[[str], IO[bytes]]
InstallStatus = Literal["installed", "already_installed"]


class SourceInstallError(InputError):
    """A pinned source could not be installed."""

    code = "SOURCE_INSTALL_FAILED"


@dataclass(frozen=True)
class InstalledSource:
    textbook_id: str
    path: Path
    sha256: str
    status: InstallStatus


def asset_name(textbook_id: str) -> str:
    """The canonical Release asset and local file name for one textbook."""

    return f"{textbook_id}.pdf"


def asset_url(textbook_id: str, *, tag: str = DEFAULT_RELEASE_TAG) -> str:
    return (
        f"https://github.com/{RELEASE_REPOSITORY}/releases/download/"
        f"{tag}/{asset_name(textbook_id)}"
    )


def pinned_sources(
    textbook_ids: Sequence[str] = REQUIRED_TEXTBOOK_IDS,
) -> dict[str, str]:
    """Return ``{textbook_id: hex sha256}`` for every book the catalogue pins."""

    pins: dict[str, str] = {}
    for textbook_id in textbook_ids:
        expected = get_textbook_spec(textbook_id).expected_source_sha256
        if expected:
            pins[textbook_id] = expected.removeprefix("sha256:")
    return pins


def sha256sums_text(pins: Mapping[str, str] | None = None) -> str:
    """The ``SHA256SUMS`` body to upload next to the Release assets."""

    resolved = dict(pins) if pins is not None else pinned_sources()
    return "".join(
        f"{resolved[textbook_id]}  {asset_name(textbook_id)}\n"
        for textbook_id in sorted(resolved)
    )


def _hex_digest(path: Path) -> str:
    return sha256_file(path).removeprefix("sha256:")


def _install_stream(
    stream: IO[bytes],
    *,
    textbook_id: str,
    expected_sha256: str,
    destination: Path,
    description: str,
) -> InstalledSource:
    destination.mkdir(parents=True, exist_ok=True)
    target = destination / asset_name(textbook_id)
    partial = destination / f".{target.name}.part"
    try:
        with partial.open("wb") as handle:
            while True:
                block = stream.read(_READ_CHUNK)
                if not block:
                    break
                handle.write(block)
        received = _hex_digest(partial)
        if received != expected_sha256:
            raise SourceInstallError(
                f"{textbook_id}: {description} has SHA-256 {received}, "
                f"but the catalogue pins {expected_sha256}",
                code="SOURCE_HASH_MISMATCH",
            )
        os.replace(partial, target)
    finally:
        partial.unlink(missing_ok=True)
    return InstalledSource(
        textbook_id=textbook_id, path=target, sha256=expected_sha256, status="installed"
    )


def _already_installed(
    textbook_id: str, expected_sha256: str, destination: Path
) -> InstalledSource | None:
    target = destination / asset_name(textbook_id)
    if not target.is_file():
        return None
    present = _hex_digest(target)
    if present != expected_sha256:
        raise SourceInstallError(
            f"{textbook_id}: {target} already exists with SHA-256 {present}; "
            "refusing to overwrite it. Move it aside if it is not the pinned PDF.",
            code="LOCAL_FILE_DIFFERS",
        )
    return InstalledSource(
        textbook_id=textbook_id,
        path=target,
        sha256=expected_sha256,
        status="already_installed",
    )


def _default_opener(url: str) -> IO[bytes]:
    return urllib.request.urlopen(url, timeout=_TIMEOUT_SECONDS)  # noqa: S310 - fixed https host


def install_from_release(
    destination: Path = DEFAULT_DESTINATION,
    *,
    tag: str = DEFAULT_RELEASE_TAG,
    pins: Mapping[str, str] | None = None,
    opener: Opener = _default_opener,
) -> list[InstalledSource]:
    """Download every pinned PDF that is not already installed."""

    resolved = dict(pins) if pins is not None else pinned_sources()
    if not resolved:
        raise SourceInstallError(
            "the catalogue pins no source hashes yet", code="NO_PINNED_SOURCES"
        )
    results: list[InstalledSource] = []
    for textbook_id, expected in sorted(resolved.items()):
        existing = _already_installed(textbook_id, expected, destination)
        if existing is not None:
            results.append(existing)
            continue
        url = asset_url(textbook_id, tag=tag)
        try:
            with closing(opener(url)) as stream:
                results.append(
                    _install_stream(
                        stream,
                        textbook_id=textbook_id,
                        expected_sha256=expected,
                        destination=destination,
                        description=url,
                    )
                )
        except urllib.error.URLError as exc:
            raise SourceInstallError(
                f"{textbook_id}: cannot download {url}: {exc}",
                code="SOURCE_DOWNLOAD_FAILED",
            ) from exc
    return results


def install_from_directory(
    source_dir: Path,
    destination: Path = DEFAULT_DESTINATION,
    *,
    pins: Mapping[str, str] | None = None,
) -> tuple[list[InstalledSource], list[Path]]:
    """Install PDFs already on disk, matching them to the pins by hash.

    Returns the installed sources and the PDFs that matched no pin, so the same
    command can be used to check a delivery before it is uploaded.
    """

    resolved = dict(pins) if pins is not None else pinned_sources()
    if not source_dir.is_dir():
        raise SourceInstallError(
            f"not a directory: {source_dir}", code="SOURCE_DIR_NOT_FOUND"
        )
    by_hash = {expected: textbook_id for textbook_id, expected in resolved.items()}
    results: list[InstalledSource] = []
    unmatched: list[Path] = []
    for candidate in sorted(_pdf_files(source_dir)):
        digest = _hex_digest(candidate)
        textbook_id = by_hash.get(digest)
        if textbook_id is None:
            unmatched.append(candidate)
            continue
        existing = _already_installed(textbook_id, digest, destination)
        if existing is not None:
            results.append(existing)
            continue
        with candidate.open("rb") as stream:
            results.append(
                _install_stream(
                    stream,
                    textbook_id=textbook_id,
                    expected_sha256=digest,
                    destination=destination,
                    description=str(candidate),
                )
            )
    return results, unmatched


def _pdf_files(source_dir: Path) -> Iterable[Path]:
    return (
        path
        for path in source_dir.rglob("*")
        if path.is_file() and path.suffix.lower() == ".pdf"
    )


def missing_sources(
    destination: Path = DEFAULT_DESTINATION,
    *,
    pins: Mapping[str, str] | None = None,
) -> list[str]:
    """Pinned textbooks whose PDF is not installed with the pinned content."""

    resolved = dict(pins) if pins is not None else pinned_sources()
    missing: list[str] = []
    for textbook_id, expected in sorted(resolved.items()):
        target = destination / asset_name(textbook_id)
        if not target.is_file() or _hex_digest(target) != expected:
            missing.append(textbook_id)
    return missing
