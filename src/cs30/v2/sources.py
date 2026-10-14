"""Install the pinned v2 textbook sources from GitHub Releases or from disk.

Parsed deliveries are installed from provider-specific archives: OpenStax's
``M2_data_ingestion`` archive and CK-12's ``M2_ck12`` archive. The catalogue
pins every parsed file and its originating PDF. A local file with different
content is never overwritten, and a mismatching file is deleted instead of
installed.
"""

from __future__ import annotations

import os
import shutil
import urllib.error
import urllib.request
import zipfile
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

# M2's OpenStax parsed delivery. The _r1 archive differs from the original
# upload only in its test file; each parsed JSON is byte-identical.
PARSED_RELEASE_TAG = "M2_data_ingestion"
PARSED_ARCHIVE_NAME = "openstax_parser_v1_3_2_r1.zip"
PARSED_ARCHIVE_MEMBERS: dict[str, str] = {
    "openstax_college_physics_2e": (
        "openstax_parser_v1_3_2/college_output/openstax_document.json"
    ),
    "openstax_physics": "openstax_parser_v1_3_2/physics_output/openstax_document.json",
    "openstax_college_physics_ap_2e": (
        "openstax_parser_v1_3_2/ap_output/openstax_document.json"
    ),
    "ck12_peoples_physics_concepts": (
        "ck12_parser_v1_1_0/ck12_output_without_chapter_21/openstax_document.json"
    ),
}
DEFAULT_PARSED_DESTINATION = Path("data/parsed/v2")
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


def parsed_file_name(textbook_id: str) -> str:
    """The local file name of M2's parsed delivery for one textbook."""

    return f"{textbook_id}.json"


def parsed_archive_url(
    *, tag: str = PARSED_RELEASE_TAG, archive_name: str = PARSED_ARCHIVE_NAME
) -> str:
    return f"https://github.com/{RELEASE_REPOSITORY}/releases/download/{tag}/{archive_name}"


def pinned_sources(
    textbook_ids: Sequence[str] = REQUIRED_TEXTBOOK_IDS,
) -> dict[str, str]:
    """Return ``{textbook_id: hex sha256}`` for every book whose PDF is pinned."""

    pins: dict[str, str] = {}
    for textbook_id in textbook_ids:
        expected = get_textbook_spec(textbook_id).expected_source_sha256
        if expected:
            pins[textbook_id] = expected.removeprefix("sha256:")
    return pins


def pinned_parsed_sources(
    textbook_ids: Sequence[str] = REQUIRED_TEXTBOOK_IDS,
) -> dict[str, str]:
    """Return ``{textbook_id: hex sha256}`` for every book whose parse is pinned."""

    pins: dict[str, str] = {}
    for textbook_id in textbook_ids:
        expected = get_textbook_spec(textbook_id).expected_parsed_sha256
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
    file_name: str | None = None,
) -> InstalledSource:
    destination.mkdir(parents=True, exist_ok=True)
    target = destination / (file_name or asset_name(textbook_id))
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
    textbook_id: str,
    expected_sha256: str,
    destination: Path,
    file_name: str | None = None,
) -> InstalledSource | None:
    target = destination / (file_name or asset_name(textbook_id))
    if not target.is_file():
        return None
    present = _hex_digest(target)
    if present != expected_sha256:
        raise SourceInstallError(
            f"{textbook_id}: {target} already exists with SHA-256 {present}; "
            "refusing to overwrite it. Move it aside if it is not the pinned file.",
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
    unsupported = [
        textbook_id
        for textbook_id in resolved
        if not get_textbook_spec(textbook_id).supports_raw
    ]
    if unsupported:
        raise SourceInstallError(
            "raw source installation is unsupported for "
            f"{', '.join(sorted(unsupported))}; use the parsed source format",
            code="RAW_SOURCE_UNSUPPORTED",
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


def _resolved_parsed_pins(pins: Mapping[str, str] | None) -> dict[str, str]:
    resolved = dict(pins) if pins is not None else pinned_parsed_sources()
    if not resolved:
        raise SourceInstallError(
            "the catalogue pins no parsed sources yet", code="NO_PINNED_SOURCES"
        )
    return resolved


def _parsed_delivery_groups(
    resolved: Mapping[str, str],
    *,
    tag: str | None = None,
    archive_name: str | None = None,
    members: Mapping[str, str] = PARSED_ARCHIVE_MEMBERS,
) -> dict[tuple[str, str], dict[str, str]]:
    groups: dict[tuple[str, str], dict[str, str]] = {}
    for textbook_id in resolved:
        spec = get_textbook_spec(textbook_id)
        resolved_tag = spec.parsed_release_tag or tag or PARSED_RELEASE_TAG
        resolved_archive = spec.parsed_archive_name or archive_name or PARSED_ARCHIVE_NAME
        member = members.get(textbook_id) or spec.parsed_archive_member
        if not member:
            raise SourceInstallError(
                f"{textbook_id}: the catalogue has no parsed archive member",
                code="ARCHIVE_MEMBER_MISSING",
            )
        groups.setdefault((resolved_tag, resolved_archive), {})[textbook_id] = member
    return groups


def install_parsed_from_archives(
    archives: Sequence[Path],
    destination: Path = DEFAULT_PARSED_DESTINATION,
    *,
    pins: Mapping[str, str] | None = None,
    members: Mapping[str, str] = PARSED_ARCHIVE_MEMBERS,
) -> list[InstalledSource]:
    """Install parsed sources from one or more M2 release archives.

    Each archive may contain one provider's delivery. A textbook group is
    installed only when the archive contains all pinned members for that
    release, so an OpenStax archive and the separate CK-12 archive can be
    supplied independently.
    """

    resolved = _resolved_parsed_pins(pins)
    if not archives:
        raise SourceInstallError(
            "no source archives were supplied", code="SOURCE_ARCHIVE_NOT_FOUND"
        )
    checked: list[tuple[Path, zipfile.ZipFile, set[str]]] = []
    try:
        for archive in archives:
            if not archive.is_file():
                raise SourceInstallError(
                    f"not a file: {archive}", code="SOURCE_ARCHIVE_NOT_FOUND"
                )
            try:
                bundle = zipfile.ZipFile(archive)
            except zipfile.BadZipFile as exc:
                raise SourceInstallError(
                    f"not a valid zip archive: {archive}", code="SOURCE_ARCHIVE_INVALID"
                ) from exc
            checked.append((archive, bundle, set(bundle.namelist())))

        groups = _parsed_delivery_groups(resolved, members=members)
        matched: set[tuple[str, str]] = set()
        results: dict[str, InstalledSource] = {}
        for archive, bundle, names in checked:
            matched_groups = [
                key
                for key, expected_members in groups.items()
                if names.intersection(expected_members.values())
            ]
            if not matched_groups:
                continue
            for key in matched_groups:
                if key in matched:
                    raise SourceInstallError(
                        f"more than one archive contains members for {key[1]}",
                        code="SOURCE_ARCHIVE_AMBIGUOUS",
                    )
                matched.add(key)
                for textbook_id, member in sorted(groups[key].items()):
                    if member not in names:
                        raise SourceInstallError(
                            f"{textbook_id}: {archive.name} has no member {member}",
                            code="ARCHIVE_MEMBER_MISSING",
                        )
                    expected = resolved[textbook_id]
                    file_name = parsed_file_name(textbook_id)
                    existing = _already_installed(
                        textbook_id, expected, destination, file_name
                    )
                    if existing is not None:
                        results[textbook_id] = existing
                        continue
                    with bundle.open(member) as stream:
                        results[textbook_id] = _install_stream(
                            stream,
                            textbook_id=textbook_id,
                            expected_sha256=expected,
                            destination=destination,
                            description=f"{archive.name}:{member}",
                            file_name=file_name,
                        )

        if not matched:
            raise SourceInstallError(
                "none of the supplied archives contains a pinned parsed source member",
                code="ARCHIVE_MEMBER_MISSING",
            )
        return [results[textbook_id] for textbook_id in sorted(results)]
    finally:
        for _, bundle, _ in checked:
            bundle.close()


def install_parsed_from_archive(
    archive: Path,
    destination: Path = DEFAULT_PARSED_DESTINATION,
    *,
    pins: Mapping[str, str] | None = None,
    members: Mapping[str, str] = PARSED_ARCHIVE_MEMBERS,
) -> list[InstalledSource]:
    """Install the pinned parses present in one copy of an M2 archive."""

    return install_parsed_from_archives(
        (archive,), destination, pins=pins, members=members
    )


def install_parsed_from_release(
    destination: Path = DEFAULT_PARSED_DESTINATION,
    *,
    tag: str | None = None,
    archive_name: str | None = None,
    pins: Mapping[str, str] | None = None,
    members: Mapping[str, str] = PARSED_ARCHIVE_MEMBERS,
    opener: Opener = _default_opener,
) -> list[InstalledSource]:
    """Download each needed M2 delivery archive and install its pinned parses."""

    resolved = _resolved_parsed_pins(pins)
    groups = _parsed_delivery_groups(
        resolved, tag=tag, archive_name=archive_name, members=members
    )
    destination.mkdir(parents=True, exist_ok=True)
    results: dict[str, InstalledSource] = {}
    for (group_tag, group_archive), group_members in groups.items():
        group_pins = {textbook_id: resolved[textbook_id] for textbook_id in group_members}
        existing = {
            textbook_id: _already_installed(
                textbook_id, expected, destination, parsed_file_name(textbook_id)
            )
            for textbook_id, expected in group_pins.items()
        }
        missing = {key for key, value in existing.items() if value is None}
        if not missing:
            results.update({key: value for key, value in existing.items() if value is not None})
            continue

        download = destination / f".{group_archive}.part"
        url = parsed_archive_url(tag=group_tag, archive_name=group_archive)
        try:
            try:
                with closing(opener(url)) as stream, download.open("wb") as handle:
                    shutil.copyfileobj(stream, handle, _READ_CHUNK)
            except urllib.error.URLError as exc:
                raise SourceInstallError(
                    f"cannot download {url}: {exc}", code="SOURCE_DOWNLOAD_FAILED"
                ) from exc
            results.update(
                {
                    source.textbook_id: source
                    for source in install_parsed_from_archives(
                        (download,),
                        destination,
                        pins=group_pins,
                        members=members,
                    )
                }
            )
        finally:
            download.unlink(missing_ok=True)
    return [results[textbook_id] for textbook_id in sorted(results)]


def missing_parsed_sources(
    destination: Path = DEFAULT_PARSED_DESTINATION,
    *,
    pins: Mapping[str, str] | None = None,
) -> list[str]:
    """Pinned textbooks whose parse is not installed with the pinned content."""

    resolved = dict(pins) if pins is not None else pinned_parsed_sources()
    missing: list[str] = []
    for textbook_id, expected in sorted(resolved.items()):
        target = destination / parsed_file_name(textbook_id)
        if not target.is_file() or _hex_digest(target) != expected:
            missing.append(textbook_id)
    return missing
