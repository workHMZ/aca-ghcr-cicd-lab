from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from scripts import ingest


class SearchClient:
    def __init__(self) -> None:
        self.uploaded: list[dict[str, Any]] = []
        self.deleted: list[dict[str, str]] = []

    def merge_or_upload_documents(self, *, documents: list[dict[str, Any]]) -> list[Any]:
        self.uploaded.extend(documents)
        return [SimpleNamespace(succeeded=True) for _ in documents]

    def search(self, **_kwargs: Any) -> list[dict[str, str]]:
        return [{"id": "stale-id"}, {"id": self.uploaded[0]["id"]}]

    def delete_documents(self, *, documents: list[dict[str, str]]) -> list[Any]:
        self.deleted.extend(documents)
        return [SimpleNamespace(succeeded=True) for _ in documents]


class Tokenizer:
    def encode(self, text: str, **_kwargs: Any) -> SimpleNamespace:
        return SimpleNamespace(offsets=[(index, index + 1) for index in range(len(text))])


def _run(
    client: SearchClient, data_dir: Path, embedded: list[str], **overrides: Any
) -> ingest.IngestionStats:
    options: dict[str, Any] = {
        "client": client,
        "data_dir": data_dir,
        "model_name": "intfloat/multilingual-e5-small",
        "model_revision": "revision",
        "model_variant": "onnx-qint8",
        "tokenizer": Tokenizer(),
        "dimension": 2,
        "chunk_tokens": 384,
        "min_chunk_tokens": 8,
        "overlap_tokens": 48,
        "embedding_batch_size": 16,
        "upload_batch_size": 100,
    }
    options.update(overrides)
    return ingest.ingest(**options)


@pytest.fixture
def embedded(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    captured: list[str] = []

    def embed_passages(texts: list[str]) -> list[list[float]]:
        captured.extend(texts)
        return [[1.0, 0.0] for _ in texts]

    monkeypatch.setattr(ingest.embedding, "embed_passages", embed_passages)
    return captured


def test_ingest_uploads_v4_metadata_and_prunes_stale_chunks(tmp_path: Path, embedded: list[str]) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "guide.md").write_text("1、HashMap buckets\nanswer text", encoding="utf-8")
    client = SearchClient()

    stats = _run(client, data_dir, embedded)

    document = client.uploaded[0]
    assert stats.uploaded == 1
    assert document["contentZh"] == document["contentJa"] == document["content"]
    assert document["title"] == "1、HashMap buckets"
    assert (document["pageNumber"], document["pageEnd"]) == (1, 1)
    assert document["embeddingVariant"] == "onnx-qint8"
    assert document["id"] == ingest._stable_document_id("guide.md", 0)
    assert client.deleted == [{"id": "stale-id"}]


def test_ingest_embeds_heading_context_for_continuation_chunks(tmp_path: Path, embedded: list[str]) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "guide.txt").write_text("7、Long question\n" + "x" * 40 + "\n" + "y" * 40, encoding="utf-8")

    _run(SearchClient(), data_dir, embedded, chunk_tokens=48, overlap_tokens=4)

    assert len(embedded) > 1
    assert embedded[1].startswith("7、Long question\n")


def test_ingest_rejects_wrong_vector_dimension(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "guide.txt").write_text("content", encoding="utf-8")
    monkeypatch.setattr(ingest.embedding, "embed_passages", lambda texts: [[1.0] for _ in texts])

    with pytest.raises(RuntimeError, match="dimension mismatch"):
        _run(SearchClient(), data_dir, [])


def test_select_source_files_filters_by_glob_and_suffix(tmp_path: Path) -> None:
    (tmp_path / "notes").mkdir()
    for name in ("book.pdf", "notes/private.md", "readme.txt", "image.png"):
        (tmp_path / name).write_bytes(b"x")

    all_files = [path.relative_to(tmp_path).as_posix() for path in ingest.select_source_files(tmp_path)]
    only_pdf = [path.name for path in ingest.select_source_files(tmp_path, ["*.pdf"])]

    assert all_files == ["book.pdf", "notes/private.md", "readme.txt"]
    assert only_pdf == ["book.pdf"]


def test_upload_batch_reports_indexing_failures() -> None:
    class FailingClient(SearchClient):
        def merge_or_upload_documents(self, *, documents: list[dict[str, Any]]) -> list[Any]:
            return [SimpleNamespace(succeeded=False, key="k", error_message="bad") for _ in documents]

    stats = ingest.IngestionStats()
    with pytest.raises(RuntimeError, match="failed to index"):
        ingest._upload_batch(FailingClient(), [{"id": "k"}], stats)  # type: ignore[arg-type]
    assert stats.failed == 1
