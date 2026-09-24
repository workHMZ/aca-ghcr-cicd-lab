from __future__ import annotations

import hashlib
import io
from pathlib import Path
from typing import Any

import pytest

from app import model_manifest
from app.config import Settings
from app.model_manifest import ModelFile


def _manifest(monkeypatch: pytest.MonkeyPatch, payloads: dict[str, bytes]) -> None:
    files = {
        name: ModelFile(repo_path=f"onnx/{name}", local_name=name, sha256=hashlib.sha256(data).hexdigest())
        for name, data in payloads.items()
    }
    monkeypatch.setattr(model_manifest, "TOKENIZER_FILE", files["tokenizer.json"])
    monkeypatch.setattr(model_manifest, "MODEL_FILES", {"onnx-qint8": files["model.onnx"]})


def test_settings_literals_match_the_manifest() -> None:
    settings = Settings()
    assert settings.embedding_model_name == model_manifest.MODEL_NAME
    assert settings.embedding_model_revision == model_manifest.MODEL_REVISION
    assert settings.embedding_variant == model_manifest.DEFAULT_VARIANT


def test_every_pinned_file_has_a_sha256() -> None:
    for model_file in (model_manifest.TOKENIZER_FILE, *model_manifest.MODEL_FILES.values()):
        assert len(model_file.sha256) == 64
        int(model_file.sha256, 16)


def test_default_model_dir_is_revision_scoped(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    directory = model_manifest.default_model_dir()
    assert directory.parent == tmp_path / "serverless-rag"
    assert model_manifest.MODEL_REVISION[:12] in directory.name


def test_existing_files_are_accepted_and_optionally_verified(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _manifest(monkeypatch, {"tokenizer.json": b"tok", "model.onnx": b"model"})
    (tmp_path / "tokenizer.json").write_bytes(b"tok")
    (tmp_path / "model.onnx").write_bytes(b"tampered")

    assert model_manifest.ensure_model_files(tmp_path, "onnx-qint8", allow_download=False) == tmp_path
    with pytest.raises(RuntimeError, match="Checksum mismatch"):
        model_manifest.ensure_model_files(tmp_path, "onnx-qint8", allow_download=False, verify=True)


def test_missing_files_fail_when_downloads_are_disabled(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _manifest(monkeypatch, {"tokenizer.json": b"tok", "model.onnx": b"model"})
    with pytest.raises(RuntimeError, match="downloads are disabled"):
        model_manifest.ensure_model_files(tmp_path, "onnx-qint8", allow_download=False)


def test_download_verifies_checksum_and_writes_atomically(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    payloads = {"tokenizer.json": b"tok", "model.onnx": b"model"}
    _manifest(monkeypatch, payloads)
    requested: list[str] = []

    def urlopen(url: str, timeout: int) -> Any:
        requested.append(url)
        return io.BytesIO(payloads[url.rsplit("/", 1)[-1]])

    monkeypatch.setattr(model_manifest.urllib.request, "urlopen", urlopen)

    model_manifest.ensure_model_files(tmp_path, "onnx-qint8", allow_download=True)

    assert (tmp_path / "model.onnx").read_bytes() == b"model"
    assert all(model_manifest.MODEL_REVISION in url for url in requested)
    assert sorted(path.name for path in tmp_path.iterdir()) == ["model.onnx", "tokenizer.json"]


def test_download_rejects_tampered_bytes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _manifest(monkeypatch, {"tokenizer.json": b"tok", "model.onnx": b"model"})
    monkeypatch.setattr(
        model_manifest.urllib.request,
        "urlopen",
        lambda _url, timeout: io.BytesIO(b"evil"),
    )

    with pytest.raises(RuntimeError, match="Checksum mismatch"):
        model_manifest.ensure_model_files(tmp_path, "onnx-qint8", allow_download=True)
    assert list(tmp_path.iterdir()) == []
