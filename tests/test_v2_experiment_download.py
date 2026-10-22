"""Pinned development input fetching, without network requests in CI."""

import hashlib
import importlib.util
import io
import zipfile
from pathlib import Path

import pytest


def downloader(monkeypatch, *, entry=None):
    path = Path(__file__).resolve().parents[1] / "scripts/fetch_v2_experiment_inputs.py"
    spec = importlib.util.spec_from_file_location("v2_fetch_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(entry or f"{module.CORPUS_FOLDER}/records.jsonl", "synthetic records")
    files = {
        name: buffer.getvalue() if name == module.CORPUS_ARCHIVE else f"synthetic {name}\n".encode()
        for name in module.ASSETS
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
    assert len(calls) == len(module.ASSETS) and manifest["reportable"] is False
    assert manifest["corpus_dir"] == module.CORPUS_FOLDER
    assert (tmp_path / module.ROLE_MANIFEST).is_file()
    assert (tmp_path / module.CORPUS_FOLDER / "records.jsonl").read_text(
        encoding="utf-8"
    ) == "synthetic records"
    assert module.fetch(tmp_path) == manifest
    assert len(calls) == len(module.ASSETS)


def test_changed_download_and_extracted_corpus_are_not_overwritten(tmp_path, monkeypatch):
    module, _ = downloader(monkeypatch)
    module.fetch(tmp_path)
    records = tmp_path / module.CORPUS_FOLDER / "records.jsonl"
    records.write_text("changed")
    with pytest.raises(ValueError, match="differs from pinned"):
        module.fetch(tmp_path)
    assert records.read_text(encoding="utf-8") == "changed"
    records.unlink()
    with pytest.raises(ValueError, match="differs from pinned"):
        module.fetch(tmp_path)
    gold = next(name for name in module.ASSETS if name.startswith("gold_"))
    (tmp_path / gold).write_text("changed gold")
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        module.fetch(tmp_path)


def test_archive_path_escape_is_rejected(tmp_path, monkeypatch):
    module, _ = downloader(monkeypatch, entry="../escape.txt")
    with pytest.raises(ValueError, match="unsafe"):
        module.fetch(tmp_path)
    assert not (tmp_path.parent / "escape.txt").exists()


def test_archive_entry_outside_the_corpus_folder_is_rejected(tmp_path, monkeypatch):
    module, _ = downloader(monkeypatch, entry="records.jsonl")
    with pytest.raises(ValueError, match="outside"):
        module.fetch(tmp_path)
    assert not (tmp_path / "records.jsonl").exists()
