"""Installing the pinned textbook PDFs from a Release or a local folder."""

from __future__ import annotations

import hashlib
import io
from pathlib import Path

import pytest

from cs30.v2.catalog import REQUIRED_TEXTBOOK_IDS
from cs30.v2.sources import (
    DEFAULT_RELEASE_TAG,
    SourceInstallError,
    asset_url,
    install_from_directory,
    install_from_release,
    missing_sources,
    pinned_sources,
    sha256sums_text,
)

FIRST, SECOND = REQUIRED_TEXTBOOK_IDS[0], REQUIRED_TEXTBOOK_IDS[1]
PAYLOADS = {FIRST: b"%PDF-first-book\n", SECOND: b"%PDF-second-book\n"}
PINS = {
    textbook_id: hashlib.sha256(payload).hexdigest()
    for textbook_id, payload in PAYLOADS.items()
}


def fake_opener(url: str):
    for textbook_id, payload in PAYLOADS.items():
        if url.endswith(f"{textbook_id}.pdf"):
            return io.BytesIO(payload)
    raise AssertionError(f"unexpected url: {url}")


def test_the_catalogue_is_the_only_list_of_hashes() -> None:
    pins = pinned_sources()

    assert set(pins) == set(REQUIRED_TEXTBOOK_IDS)
    assert all(len(value) == 64 for value in pins.values())
    assert sha256sums_text(pins).splitlines()[0].endswith(
        f"  {sorted(pins)[0]}.pdf"
    )
    assert asset_url(FIRST) == (
        "https://github.com/yshe0376/cs30-personalised-rag/releases/download/"
        f"{DEFAULT_RELEASE_TAG}/{FIRST}.pdf"
    )


def test_downloads_are_installed_under_their_canonical_name(tmp_path: Path) -> None:
    installed = install_from_release(tmp_path, pins=PINS, opener=fake_opener)

    assert [source.status for source in installed] == ["installed", "installed"]
    for textbook_id, payload in PAYLOADS.items():
        assert (tmp_path / f"{textbook_id}.pdf").read_bytes() == payload
    assert missing_sources(tmp_path, pins=PINS) == []
    assert not list(tmp_path.glob(".*.part"))


def test_an_installed_file_is_not_downloaded_again(tmp_path: Path) -> None:
    install_from_release(tmp_path, pins=PINS, opener=fake_opener)

    def refuse(url: str):
        raise AssertionError("should not download an installed source")

    installed = install_from_release(tmp_path, pins=PINS, opener=refuse)

    assert [source.status for source in installed] == [
        "already_installed",
        "already_installed",
    ]


def test_a_download_that_does_not_match_its_pin_is_discarded(tmp_path: Path) -> None:
    with pytest.raises(SourceInstallError) as exc_info:
        install_from_release(
            tmp_path, pins=PINS, opener=lambda url: io.BytesIO(b"%PDF-truncated")
        )

    assert exc_info.value.code == "SOURCE_HASH_MISMATCH"
    assert list(tmp_path.iterdir()) == []


def test_a_different_local_file_is_never_overwritten(tmp_path: Path) -> None:
    target = tmp_path / f"{FIRST}.pdf"
    target.write_bytes(b"%PDF-someone-elses-copy\n")

    with pytest.raises(SourceInstallError) as exc_info:
        install_from_release(tmp_path, pins=PINS, opener=fake_opener)

    assert exc_info.value.code == "LOCAL_FILE_DIFFERS"
    assert target.read_bytes() == b"%PDF-someone-elses-copy\n"
    assert missing_sources(tmp_path, pins=PINS) == [FIRST, SECOND]


def test_a_local_folder_is_matched_by_hash_not_by_file_name(tmp_path: Path) -> None:
    delivery = tmp_path / "wechat"
    delivery.mkdir()
    (delivery / "02-college-physics-2e_-_WEB.pdf").write_bytes(PAYLOADS[FIRST])
    (delivery / "unrelated.pdf").write_bytes(b"%PDF-not-a-pinned-book\n")
    destination = tmp_path / "data" / "raw" / "v2"

    installed, unmatched = install_from_directory(delivery, destination, pins=PINS)

    assert [source.textbook_id for source in installed] == [FIRST]
    assert (destination / f"{FIRST}.pdf").read_bytes() == PAYLOADS[FIRST]
    assert [path.name for path in unmatched] == ["unrelated.pdf"]
    # The second book is still missing, so the script can report it.
    assert missing_sources(destination, pins=PINS) == [SECOND]


def test_a_missing_source_directory_is_an_input_error(tmp_path: Path) -> None:
    with pytest.raises(SourceInstallError) as exc_info:
        install_from_directory(tmp_path / "absent", tmp_path, pins=PINS)

    assert exc_info.value.code == "SOURCE_DIR_NOT_FOUND"
