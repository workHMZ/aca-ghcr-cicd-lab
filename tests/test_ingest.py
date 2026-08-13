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
    def encode(self, text: str, **_kwargs: Any) -> list[int]:
        return [ord(character) for character in text]

    def decode(self, token_ids: list[int], **_kwargs: Any) -> str:
        return "".join(chr(value) for value in token_ids)


def test_ingest_uploads_metadata_and_prunes_stale_source_chunks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "guide.txt").write_text("HashMap buckets", encoding="utf-8")
    monkeypatch.setattr(ingest.embedding, "embed_batch", lambda texts, **_kwargs: [[1.0, 0.0] for _ in texts])
    client = SearchClient()

    stats = ingest.ingest(
        client=client,  # type: ignore[arg-type]
        data_dir=data_dir,
        model_name="intfloat/multilingual-e5-small",
        model_revision="revision",
        tokenizer=Tokenizer(),
        dimension=2,
        chunk_tokens=384,
        overlap_tokens=48,
        embedding_batch_size=16,
        upload_batch_size=100,
    )

    assert stats.uploaded == 1
    assert client.uploaded[0]["sourceId"]
    assert client.uploaded[0]["embeddingRevision"] == "revision"
    assert client.deleted == [{"id": "stale-id"}]
