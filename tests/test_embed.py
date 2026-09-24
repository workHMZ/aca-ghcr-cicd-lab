from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from app import embed
from app.config import settings
from app.model_manifest import MODEL_NAME, MODEL_REVISION


class FakeEmbedder:
    def __init__(self) -> None:
        self.calls: list[tuple[list[str], int]] = []

    def encode(self, texts: list[str], *, batch_size: int) -> np.ndarray:
        self.calls.append((texts, batch_size))
        return np.tile(np.asarray([[1.0, 0.0]], dtype=np.float32), (len(texts), 1))


@pytest.fixture
def fake_embedder(monkeypatch: pytest.MonkeyPatch) -> FakeEmbedder:
    embedder = FakeEmbedder()
    monkeypatch.setattr(embed, "_EMBEDDER", embedder)
    return embedder


def test_embed_query_adds_e5_prefix(fake_embedder: FakeEmbedder) -> None:
    assert embed.embed_query("  HashMap  ") == [1.0, 0.0]
    assert fake_embedder.calls == [(["query: HashMap"], 1)]


def test_embed_passages_batches_with_passage_prefix(fake_embedder: FakeEmbedder) -> None:
    vectors = embed.embed_passages(["first", " second "])

    assert vectors == [[1.0, 0.0], [1.0, 0.0]]
    assert fake_embedder.calls == [(["passage: first", "passage: second"], settings.embedding_batch_size)]


def test_empty_embedding_inputs_do_not_load_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(embed, "_EMBEDDER", None)
    assert embed.embed_text("") == []
    assert embed.embed_batch([]) == []
    assert embed.is_loaded() is False


def test_embedding_metadata_matches_manifest(fake_embedder: FakeEmbedder) -> None:
    assert embed.get_dimension() == 384
    assert embed.get_model_name() == MODEL_NAME
    assert embed.get_model_revision() == MODEL_REVISION
    assert embed.get_embedding_variant() == "onnx-qint8"
    assert embed.is_loaded() is True


def test_model_dir_prefers_explicit_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(settings, "embedding_model_path", str(tmp_path))
    assert embed.model_dir() == tmp_path


class FakeTokenizer:
    def encode_batch(self, texts: list[str]) -> list[Any]:
        # Two real tokens for the first text, one real token + padding otherwise.
        return [
            SimpleNamespace(ids=[5, 6], attention_mask=[1, 1])
            if index == 0
            else SimpleNamespace(ids=[7, 1], attention_mask=[1, 0])
            for index, _text in enumerate(texts)
        ]


class FakeSession:
    def __init__(self) -> None:
        self.feeds: list[dict[str, np.ndarray]] = []

    def run(self, _outputs: list[str], feeds: dict[str, np.ndarray]) -> list[np.ndarray]:
        self.feeds.append(feeds)
        batch = feeds["input_ids"].shape[0]
        hidden = np.zeros((batch, 2, 2), dtype=np.float32)
        hidden[:, 0, :] = [3.0, 0.0]
        hidden[:, 1, :] = [0.0, 4.0]
        return [hidden]


def _embedder_with(session: FakeSession, input_names: set[str]) -> embed.OnnxEmbedder:
    embedder = object.__new__(embed.OnnxEmbedder)
    embedder._session = session  # type: ignore[attr-defined]
    embedder._input_names = input_names  # type: ignore[attr-defined]
    embedder._tokenizer = FakeTokenizer()  # type: ignore[attr-defined]
    return embedder


def test_onnx_encode_mean_pools_over_attention_mask_and_normalizes() -> None:
    session = FakeSession()
    embedder = _embedder_with(session, {"input_ids", "attention_mask", "token_type_ids"})

    vectors = embedder.encode(["a", "b"], batch_size=8)

    # Row 0 averages both tokens -> (1.5, 2.0) -> (0.6, 0.8); row 1 ignores padding.
    np.testing.assert_allclose(vectors, [[0.6, 0.8], [1.0, 0.0]], rtol=1e-6)
    assert "token_type_ids" in session.feeds[0]


def test_onnx_encode_respects_batch_size_and_optional_inputs() -> None:
    session = FakeSession()
    embedder = _embedder_with(session, {"input_ids", "attention_mask"})

    vectors = embedder.encode(["a", "b", "c"], batch_size=2)

    assert vectors.shape == (3, 2)
    assert len(session.feeds) == 2
    assert "token_type_ids" not in session.feeds[0]


def test_get_embedder_rejects_wrong_dimension(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    class WrongDimension:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            pass

        def encode(self, texts: list[str], *, batch_size: int) -> np.ndarray:
            return np.zeros((len(texts), 3), dtype=np.float32)

    monkeypatch.setattr(embed, "_EMBEDDER", None)
    monkeypatch.setattr(embed, "ensure_model_files", lambda *_args, **_kwargs: tmp_path)
    monkeypatch.setattr(embed, "OnnxEmbedder", WrongDimension)

    with pytest.raises(RuntimeError, match="dimension must be 384"):
        embed.load_model()
    assert embed.is_loaded() is False


def test_load_model_honours_offline_setting(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    captured: dict[str, Any] = {}

    class Loaded:
        def __init__(self, directory: Path, **kwargs: Any) -> None:
            captured.update(directory=directory, **kwargs)

        def encode(self, texts: list[str], *, batch_size: int) -> np.ndarray:
            return np.zeros((len(texts), 384), dtype=np.float32)

    def ensure(directory: Path, variant: str, *, allow_download: bool) -> Path:
        captured.update(variant=variant, allow_download=allow_download)
        return directory

    monkeypatch.setattr(embed, "_EMBEDDER", None)
    monkeypatch.setattr(settings, "embedding_model_path", str(tmp_path))
    monkeypatch.setattr(settings, "embedding_offline", True)
    monkeypatch.setattr(embed, "ensure_model_files", ensure)
    monkeypatch.setattr(embed, "OnnxEmbedder", Loaded)

    embed.load_model()

    assert embed.is_loaded() is True
    assert captured["allow_download"] is False
    assert captured["variant"] == "onnx-qint8"
    assert captured["model_file"] == "model_qint8.onnx"
    assert captured["threads"] == settings.embedding_threads
