"""Pinned development input fetching, without network requests in CI."""

import hashlib
import importlib.util
import io
import zipfile
from pathlib import Path

import pytest


def downloader(monkeypatch, *, unsafe=False):
    path = Path(__file__).resolve().parents[1] / "scripts/fetch_v2_experiment_inputs.py"
    spec = importlib.util.spec_from_file_location("v2_fetch_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("../escape.txt" if unsafe else "records.jsonl", "synthetic records")
    files = {
        "gold_v0_1_1_integrated.jsonl": b"synthetic gold\n",
        "SHA256SUMS.txt": b"synthetic checksum\n",
        "v2_structure_aware_corpus_3book_dev_main_3553825.zip": buffer.getvalue(),
    }
    assets = {
        name: ("https://example.invalid/" + name, hashlib.sha256(data).hexdigest())
        for name, data in files.items()
    }
    monkeypatch.setattr(module, "ASSETS", assets)
    calls = []

    def open_url(url, **kwargs):
        calls.append(url)
        return io.BytesIO(files[url.rsplit("/", 1)[1]])

    monkeypatch.setattr(module.urllib.request, "urlopen", open_url)
    return module, calls


def test_download_extract_and_verified_reuse(tmp_path, monkeypatch):
    module, calls = downloader(monkeypatch)
    manifest = module.fetch(tmp_path)
    assert len(calls) == 3 and manifest["reportable"] is False
    assert (tmp_path / "corpus-release/records.jsonl").read_text() == "synthetic records"
    assert module.fetch(tmp_path) == manifest
    assert len(calls) == 3


def test_changed_download_and_extracted_corpus_are_not_overwritten(tmp_path, monkeypatch):
    module, _ = downloader(monkeypatch)
    module.fetch(tmp_path)
    records = tmp_path / "corpus-release/records.jsonl"
    records.write_text("changed")
    with pytest.raises(ValueError, match="differs from pinned"):
        module.fetch(tmp_path)
    assert records.read_text() == "changed"
    (tmp_path / "gold_v0_1_1_integrated.jsonl").write_text("changed gold")
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        module.fetch(tmp_path)


def test_archive_path_escape_is_rejected(tmp_path, monkeypatch):
    module, _ = downloader(monkeypatch, unsafe=True)
    with pytest.raises(ValueError, match="unsafe"):
        module.fetch(tmp_path)
    assert not (tmp_path.parent / "escape.txt").exists()
